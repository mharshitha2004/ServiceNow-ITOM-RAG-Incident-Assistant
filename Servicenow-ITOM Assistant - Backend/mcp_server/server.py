import asyncio
import os
import sys
import requests
import json

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer


load_dotenv()


def _log(*args) -> None:
    """Log to stderr, never stdout. When this server runs standalone
    over stdio (python mcp_server/server.py), stdout IS the MCP protocol
    channel - a stray print to stdout corrupts it. Inside the FastAPI app
    (in-process, see agent/mcp_client.py) stderr shows up in Render's
    logs just the same."""
    print("[MCP]", *args, file=sys.stderr, flush=True)


# ---------------------------------------------------------
# 1. ServiceNow configuration
# ---------------------------------------------------------

SERVICENOW_INSTANCE_URL = os.getenv("SERVICENOW_INSTANCE_URL")
SERVICENOW_USERNAME = os.getenv("SERVICENOW_USERNAME")
SERVICENOW_PASSWORD = os.getenv("SERVICENOW_PASSWORD")

# Name of the ServiceNow assignment group the round-robin picks members
# from. Must match the group's Name in sys_user_group EXACTLY - on this
# PDI that's "IT Operations Management L1 team". (The old default,
# "IT Operations Management", matched no group, so every incident created
# in production silently got no assignment group and no assignee.)
ITOM_ASSIGNMENT_GROUP_NAME = os.getenv(
    "ITOM_ASSIGNMENT_GROUP_NAME",
    "IT Operations Management L1 team"
).strip()

# Marks an incident as created by this assistant (a stock Incident
# field, no schema changes needed) so the backlog count for round-robin
# only looks at incidents WE created, not a member's other work. Must
# be a value that exists in the instance's Contact type choice list -
# change this if "virtual_agent" isn't one of yours.
ASSISTANT_CONTACT_TYPE = os.getenv("ASSISTANT_CONTACT_TYPE", "virtual_agent")

# Used when the website closes an incident on the caller's behalf.
# Left unset by default on purpose - see _resolve_close_code() below,
# which looks up a real choice from this instance's own Resolution
# code list instead of trusting a hardcoded guess (a guess that
# doesn't exactly match a real choice gets silently dropped by
# ServiceNow, leaving the field blank, which then fails a
# mandatory-field Data Policy on close - exactly the failure this
# was built to avoid). Set this env var to override that lookup with
# a specific value of your own.
INCIDENT_CLOSE_CODE = os.getenv("INCIDENT_CLOSE_CODE", "")

_close_code_cache = {"value": None}


def _resolve_close_code() -> str:
    """A close_code value guaranteed to be a real, active choice on
    this instance's Incident table (see the comment on
    INCIDENT_CLOSE_CODE above for why this exists instead of a
    hardcoded string). Result is cached for the life of this process,
    since the choice list won't change between requests."""

    if INCIDENT_CLOSE_CODE:
        return INCIDENT_CLOSE_CODE

    if _close_code_cache["value"]:
        return _close_code_cache["value"]

    ok, result = _servicenow_get(
        "/api/now/table/sys_choice",
        {
            "sysparm_query": (
                "name=incident^element=close_code^inactive=false"
                "^ORDERBYsequence"
            ),
            "sysparm_fields": "value,label",
            "sysparm_limit": "50",
        },
    )

    if not ok or not result:
        # Nothing to go on - fall back to the common OOB default and
        # let the real ServiceNow error (if any) explain further.
        return "Solved (Permanently)"

    # Prefer a positive/"solved" resolution over things like "Not
    # Solved" or "Duplicate", but any real active choice beats a guess.
    for choice in result:
        label = (choice.get("label") or "").lower()
        if "solved" in label and "not solved" not in label:
            _close_code_cache["value"] = choice.get("value") or choice.get("label")
            return _close_code_cache["value"]

    first = result[0]
    _close_code_cache["value"] = first.get("value") or first.get("label")
    return _close_code_cache["value"]

# Standard out-of-box Incident "state" choice list values.
INCIDENT_STATE_LABELS = {
    "1": "New",
    "2": "In Progress",
    "3": "On Hold",
    "6": "Resolved",
    "7": "Closed",
    "8": "Cancelled",
}

RESOLVED_STATE = "6"
REOPEN_STATE = "2"  # "In Progress" - where a reopened incident goes back to


# ---------------------------------------------------------
# 1b. Shared ServiceNow request helpers
#
# Used by round-robin assignment and the status/close tools below -
# create_incident and lookup_servicenow_user keep their own inline
# request code above/below, unchanged, to stay a minimal diff.
# ---------------------------------------------------------

def _servicenow_configured() -> bool:
    return bool(
        SERVICENOW_INSTANCE_URL and SERVICENOW_USERNAME and SERVICENOW_PASSWORD
    )


def _servicenow_get(path: str, params: dict):
    """GET helper. Returns (ok, data_or_error_dict)."""

    url = SERVICENOW_INSTANCE_URL.rstrip("/") + path

    try:
        response = requests.get(
            url,
            auth=(SERVICENOW_USERNAME, SERVICENOW_PASSWORD),
            headers={"Accept": "application/json"},
            params=params,
            timeout=30,
        )
    except requests.exceptions.Timeout:
        return False, {"message": "ServiceNow request timed out."}
    except requests.exceptions.RequestException as e:
        return False, {"message": "Unable to connect to ServiceNow.", "error": str(e)}

    if response.status_code == 200:
        return True, response.json().get("result", [])

    if response.status_code == 401:
        return False, {"message": "ServiceNow authentication failed."}

    return False, {
        "message": "ServiceNow request failed.",
        "http_status": response.status_code,
        "response": response.text[:1000],
    }


def _resolve_display_names(usernames: set) -> dict:
    """Batch user_name -> display name lookup (one query, not one per
    username), for fields like sys_journal_field.sys_created_by that
    store the plain login name instead of a reference to sys_user."""

    usernames = {u for u in usernames if u}

    if not usernames:
        return {}

    ok, result = _servicenow_get(
        "/api/now/table/sys_user",
        {
            "sysparm_query": f"user_nameIN{','.join(usernames)}",
            "sysparm_fields": "user_name,name",
            "sysparm_limit": str(len(usernames)),
        },
    )

    if not ok:
        return {}

    return {
        row.get("user_name", ""): row.get("name", "")
        for row in result
        if row.get("user_name")
    }


_group_cache = {}


def _get_group_sys_id(group_name: str):
    """sys_id of the assignment group. Exact name match first; if that
    finds nothing, falls back to a group whose name STARTS WITH the
    configured name - but only when exactly one group matches, so it can
    never quietly pick the wrong team. Either way, a miss is logged loudly
    instead of silently leaving incidents unassigned. Cached per process
    (group sys_ids don't change)."""

    if group_name in _group_cache:
        return _group_cache[group_name]

    ok, result = _servicenow_get(
        "/api/now/table/sys_user_group",
        {
            "sysparm_query": f"name={group_name}^active=true",
            "sysparm_limit": "1",
            "sysparm_fields": "sys_id,name",
        },
    )

    if not ok:
        _log(f"WARNING: could not look up assignment group '{group_name}': {result}")
        return None  # not cached - may be a transient failure

    if not result:
        ok, result = _servicenow_get(
            "/api/now/table/sys_user_group",
            {
                "sysparm_query": f"nameSTARTSWITH{group_name}^active=true",
                "sysparm_limit": "2",
                "sysparm_fields": "sys_id,name",
            },
        )

        if ok and len(result) == 1:
            _log(
                f"WARNING: no group named exactly '{group_name}'; using "
                f"'{result[0].get('name')}' instead. Set "
                f"ITOM_ASSIGNMENT_GROUP_NAME to that exact name."
            )
        else:
            _log(
                f"WARNING: assignment group '{group_name}' not found in "
                f"ServiceNow - incidents will be created UNASSIGNED. Check "
                f"ITOM_ASSIGNMENT_GROUP_NAME (it must match the group's "
                f"Name exactly)."
            )
            return None

    sys_id = result[0].get("sys_id")
    _group_cache[group_name] = sys_id
    return sys_id


def _get_group_members(group_sys_id: str):
    """Returns [{"sys_id", "user_name", "name"}, ...] for a group."""

    ok, result = _servicenow_get(
        "/api/now/table/sys_user_grmember",
        {
            "sysparm_query": f"group={group_sys_id}",
            "sysparm_fields": "user.sys_id,user.user_name,user.name",
            "sysparm_limit": "200",
        },
    )

    if not ok:
        return []

    members = []

    for row in result:
        sys_id = row.get("user.sys_id")
        if not sys_id:
            continue
        members.append({
            "sys_id": sys_id,
            "user_name": row.get("user.user_name", ""),
            "name": row.get("user.name", ""),
        })

    return members


def _get_backlog_count(user_sys_id: str, group_sys_id: str) -> int:
    """How many open incidents WE created are currently assigned to
    this member (see ASSISTANT_CONTACT_TYPE above)."""

    ok, result = _servicenow_get(
        "/api/now/stats/incident",
        {
            "sysparm_query": (
                f"assigned_to={user_sys_id}"
                f"^assignment_group={group_sys_id}"
                f"^contact_type={ASSISTANT_CONTACT_TYPE}"
                f"^active=true"
            ),
            "sysparm_count": "true",
        },
    )

    if not ok:
        return 0

    try:
        return int(result.get("stats", {}).get("count", 0))
    except (AttributeError, TypeError, ValueError):
        return 0


def _pick_assignee():
    """Returns (assignment_group_sys_id, assignee_dict_or_None).

    assignee is the group member with the smallest backlog (see
    _get_backlog_count), ties broken by user_name for a deterministic,
    unbiased pick. Returns (None, None) if the group can't be found,
    and (group_sys_id, None) if the group has no members - either way
    the incident still gets created, just without an owner.
    """

    if not ITOM_ASSIGNMENT_GROUP_NAME:
        return None, None

    group_sys_id = _get_group_sys_id(ITOM_ASSIGNMENT_GROUP_NAME)

    if not group_sys_id:
        return None, None

    members = _get_group_members(group_sys_id)

    if not members:
        _log(
            f"WARNING: assignment group '{ITOM_ASSIGNMENT_GROUP_NAME}' has "
            "no members - incident will get the group but no Assigned to."
        )
        return group_sys_id, None

    for member in members:
        member["_backlog"] = _get_backlog_count(member["sys_id"], group_sys_id)

    members.sort(key=lambda m: (m["_backlog"], m["user_name"]))

    return group_sys_id, members[0]


# ---------------------------------------------------------
# 2. MCP Server
# ---------------------------------------------------------

server = MCPServer(
    name="ServiceNow ITOM Assistant"
)

# ---------------------------------------------------------
# 3. Create Incident MCP Tool
# ---------------------------------------------------------

@server.tool()
def create_incident(
    short_description: str,
    description: str,
    priority: str = "P4",
    caller_id: str = "",
    correlation_id: str = "",
) -> str:

    """
    Create a ServiceNow incident.

    The AI assistant is allowed to create only P3 and P4
    incidents. P1 and P2 incidents are rejected.

    caller_id, when provided, is the sys_id of the ServiceNow user
    who should be recorded as the caller on the incident (resolved
    from the logged-in website account via lookup_servicenow_user).
    When omitted, the incident is created with no caller set.

    correlation_id, when provided, makes this call idempotent: it is
    stored in the incident's standard correlation_id field, and if an
    incident with the same correlation_id already exists, that incident
    is returned instead of creating a second one. The assistant passes
    its conversation thread id here, so a retry after a crash or a lost
    response can never create a duplicate incident.

    Returns structured JSON containing:
    - incident_number
    - sys_id
    - priority
    - success
    - already_existed (true when an existing incident was returned)
    """

    # -----------------------------------------------------
    # Normalize priority
    # -----------------------------------------------------

    priority = priority.strip().upper()

    # -----------------------------------------------------
    # Safety restriction
    # -----------------------------------------------------

    if priority not in ["P3", "P4"]:

        return json.dumps({
            "success": False,
            "message": (
                "Incident creation rejected. "
                "The AI assistant can only create P3 or P4 incidents."
            ),
            "priority": priority,
            "incident_number": "",
            "sys_id": ""
        })

    # -----------------------------------------------------
    # Check configuration
    # -----------------------------------------------------

    if not SERVICENOW_INSTANCE_URL:
        return json.dumps({
            "success": False,
            "message": "Error: SERVICENOW_INSTANCE_URL is not configured.",
            "incident_number": "",
            "sys_id": ""
        })

    if not SERVICENOW_USERNAME:
        return json.dumps({
            "success": False,
            "message": "Error: SERVICENOW_USERNAME is not configured.",
            "incident_number": "",
            "sys_id": ""
        })

    if not SERVICENOW_PASSWORD:
        return json.dumps({
            "success": False,
            "message": "Error: SERVICENOW_PASSWORD is not configured.",
            "incident_number": "",
            "sys_id": ""
        })

    # -----------------------------------------------------
    # Convert P3/P4 to impact + urgency
    #
    # This instance recalculates the "priority" field from
    # impact x urgency via a business rule on save - sending
    # "priority" directly gets silently overwritten by that
    # calculation. So instead of setting priority, we set the
    # impact/urgency pair that the *standard* ServiceNow priority
    # matrix resolves to the priority we actually want:
    #
    #   Impact \ Urgency   1-High   2-Medium   3-Low
    #   1-High             1-Crit   2-High     3-Mod
    #   2-Medium           2-High   3-Mod      4-Low
    #   3-Low              3-Mod    4-Low      4-Low
    #
    # P3 (Moderate) -> Impact 2-Medium, Urgency 2-Medium
    # P4 (Low)      -> Impact 3-Low,    Urgency 3-Low
    #
    # We still send "priority" too, in case a differently configured
    # instance doesn't recalculate it - harmless either way, since
    # it agrees with what impact/urgency resolve to.
    # -----------------------------------------------------

    priority_mapping = {
        "P3": {"priority": "3", "impact": "2", "urgency": "2"},
        "P4": {"priority": "4", "impact": "3", "urgency": "3"},
    }

    servicenow_fields = priority_mapping[priority]

    correlation_id = (correlation_id or "").strip()

    # -----------------------------------------------------
    # Idempotency: was this exact request already fulfilled?
    #
    # The FastAPI process can die (e.g. a memory-limit restart) AFTER
    # ServiceNow has saved the incident but BEFORE the answer reaches
    # the browser. When the person retries, the same correlation_id comes
    # back, and we hand them the incident that already exists.
    # -----------------------------------------------------

    if correlation_id:
        ok, existing = _servicenow_get(
            "/api/now/table/incident",
            {
                "sysparm_query": f"correlation_id={correlation_id}",
                "sysparm_fields": "number,sys_id,assigned_to.name,correlation_id",
                "sysparm_limit": "1",
            },
        )

        # Double-check the field really matched: ServiceNow ignores an
        # invalid query term by default and returns ALL rows instead.
        if ok:
            existing = [
                row for row in existing
                if row.get("correlation_id") == correlation_id
            ]

        if ok and existing:
            match = existing[0]
            _log(
                f"create_incident: {match.get('number')} already exists for "
                f"correlation_id {correlation_id} - returning it, not creating "
                "a duplicate."
            )
            return json.dumps({
                "success": True,
                "message": "Incident created successfully.",
                "incident_number": match.get("number", ""),
                "priority": priority,
                "sys_id": match.get("sys_id", ""),
                "assigned_to": match.get("assigned_to.name", ""),
                "already_existed": True,
            })

        if not ok:
            # Can't tell whether it exists. Creating anyway risks a
            # duplicate; refusing risks a lost incident. A failed GET
            # almost always means the POST would fail too, so stop here
            # and let the person retry.
            return json.dumps({
                "success": False,
                "message": (
                    "Couldn't reach ServiceNow to create the incident. "
                    "Please try again in a moment."
                ),
                "error": existing,
                "incident_number": "",
                "sys_id": ""
            })

    # -----------------------------------------------------
    # ServiceNow Incident API
    # -----------------------------------------------------

    url = (
        SERVICENOW_INSTANCE_URL.rstrip("/")
        + "/api/now/table/incident"
    )

    payload = {
        "short_description": short_description,
        "description": description,
        "priority": servicenow_fields["priority"],
        "impact": servicenow_fields["impact"],
        "urgency": servicenow_fields["urgency"],
        # Marks this incident as assistant-created, so backlog counts
        # below (and future status look-ups) can find it.
        "contact_type": ASSISTANT_CONTACT_TYPE,
    }

    if correlation_id:
        payload["correlation_id"] = correlation_id
        payload["correlation_display"] = "ITOM AI Assistant"

    # -----------------------------------------------------
    # Backlog-balanced assignment
    #
    # Picks whichever member of ITOM_ASSIGNMENT_GROUP_NAME currently
    # has the fewest open, assistant-created incidents. If the group
    # can't be found or has no members, the incident is still created,
    # just unassigned - a misconfigured group should never block
    # incident creation.
    # -----------------------------------------------------

    assignment_group_sys_id, assignee = _pick_assignee()

    if assignment_group_sys_id:
        payload["assignment_group"] = assignment_group_sys_id

    if assignee:
        payload["assigned_to"] = assignee["sys_id"]

    # Only set caller_id when we actually resolved one - an empty
    # string would clear/ignore the field on ServiceNow's side anyway,
    # but leaving it out entirely keeps the payload clean.
    if caller_id:
        payload["caller_id"] = caller_id

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    try:

        response = requests.post(
            url,
            auth=(
                SERVICENOW_USERNAME,
                SERVICENOW_PASSWORD
            ),
            headers=headers,
            json=payload,
            timeout=30
        )

        # -------------------------------------------------
        # Successfully created
        # -------------------------------------------------

        if response.status_code == 201:

            data = response.json()

            result = data.get("result", {})

            incident_number = result.get(
                "number",
                ""
            )

            sys_id = result.get(
                "sys_id",
                ""
            )

            return json.dumps({
                "success": True,
                "message": "Incident created successfully.",
                "incident_number": incident_number,
                "priority": priority,
                "sys_id": sys_id,
                "assigned_to": assignee.get("name", "") if assignee else "",
                "already_existed": False,
            })

        # -------------------------------------------------
        # Authentication failure
        # -------------------------------------------------

        if response.status_code == 401:

            return json.dumps({
                "success": False,
                "message": (
                    "ServiceNow authentication failed. "
                    "Please verify the configured credentials."
                ),
                "incident_number": "",
                "sys_id": ""
            })

        # -------------------------------------------------
        # Other errors
        # -------------------------------------------------

        return json.dumps({
            "success": False,
            "message": (
                "Failed to create incident."
            ),
            "http_status": response.status_code,
            "response": response.text[:1000],
            "incident_number": "",
            "sys_id": ""
        })

    except requests.exceptions.Timeout:

        return json.dumps({
            "success": False,
            "message": (
                "ServiceNow request timed out. "
                "Please try again."
            ),
            "incident_number": "",
            "sys_id": ""
        })

    except requests.exceptions.RequestException as e:

        return json.dumps({
            "success": False,
            "message": (
                "Unable to connect to ServiceNow."
            ),
            "error": str(e),
            "incident_number": "",
            "sys_id": ""
        })


# ---------------------------------------------------------
# 4. Look Up ServiceNow User MCP Tool
# ---------------------------------------------------------

@server.tool()
def lookup_servicenow_user(username: str) -> str:

    """
    Look up a ServiceNow user by their user_name (login name).

    Used to resolve the sys_id of the website account's linked
    ServiceNow user, so it can be passed as caller_id to
    create_incident.

    Returns structured JSON containing:
    - success
    - sys_id
    - name
    - user_name
    """

    username = (username or "").strip()

    if not username:
        return json.dumps({
            "success": False,
            "message": "Username is required.",
            "sys_id": ""
        })

    if not SERVICENOW_INSTANCE_URL:
        return json.dumps({
            "success": False,
            "message": "Error: SERVICENOW_INSTANCE_URL is not configured.",
            "sys_id": ""
        })

    if not SERVICENOW_USERNAME:
        return json.dumps({
            "success": False,
            "message": "Error: SERVICENOW_USERNAME is not configured.",
            "sys_id": ""
        })

    if not SERVICENOW_PASSWORD:
        return json.dumps({
            "success": False,
            "message": "Error: SERVICENOW_PASSWORD is not configured.",
            "sys_id": ""
        })

    url = (
        SERVICENOW_INSTANCE_URL.rstrip("/")
        + "/api/now/table/sys_user"
    )

    params = {
        "sysparm_query": f"user_name={username}",
        "sysparm_limit": "1",
        "sysparm_fields": "sys_id,user_name,name"
    }

    headers = {
        "Accept": "application/json"
    }

    try:

        response = requests.get(
            url,
            auth=(
                SERVICENOW_USERNAME,
                SERVICENOW_PASSWORD
            ),
            headers=headers,
            params=params,
            timeout=30
        )

        if response.status_code == 200:

            data = response.json()

            results = data.get("result", [])

            if not results:

                return json.dumps({
                    "success": False,
                    "message": (
                        f"No ServiceNow user found with username "
                        f"'{username}'."
                    ),
                    "sys_id": ""
                })

            match = results[0]

            return json.dumps({
                "success": True,
                "message": "User found.",
                "sys_id": match.get("sys_id", ""),
                "name": match.get("name", ""),
                "user_name": match.get("user_name", "")
            })

        if response.status_code == 401:

            return json.dumps({
                "success": False,
                "message": (
                    "ServiceNow authentication failed while "
                    "looking up user."
                ),
                "sys_id": ""
            })

        return json.dumps({
            "success": False,
            "message": "Failed to look up ServiceNow user.",
            "http_status": response.status_code,
            "response": response.text[:1000],
            "sys_id": ""
        })

    except requests.exceptions.Timeout:

        return json.dumps({
            "success": False,
            "message": "ServiceNow user lookup timed out.",
            "sys_id": ""
        })

    except requests.exceptions.RequestException as e:

        return json.dumps({
            "success": False,
            "message": "Unable to connect to ServiceNow for user lookup.",
            "error": str(e),
            "sys_id": ""
        })


# ---------------------------------------------------------
# 5. Get Incident Status MCP Tool
# ---------------------------------------------------------

@server.tool()
def get_incident_status(incident_number: str = "", caller_id: str = "") -> str:

    """
    Look up the status of an incident (or the caller's own open
    incidents, if no number is given).

    incident_number:
        A specific incident to look up (e.g. "INC0010021"). If empty,
        this instead returns every open, assistant-created incident
        for caller_id, most recent first, so the caller doesn't need
        to know their own incident number.

    caller_id:
        sys_id of the ServiceNow user asking. When incident_number is
        given, this is only used so the answer can't be someone else's
        incident.

    Returns structured JSON containing:
    - success
    - incidents: a list, each with number, state, priority,
      short_description, assigned_to, opened_at, close_notes,
      close_code, and work_notes (a merged, oldest-first list of both
      the internal Work notes and customer-visible Comments fields,
      each as {value, created_by, created_on, customer_visible})
    """

    if not _servicenow_configured():
        return json.dumps({
            "success": False,
            "message": "ServiceNow is not configured.",
            "incidents": []
        })

    incident_number = (incident_number or "").strip()
    caller_id = (caller_id or "").strip()

    fields = (
        "sys_id,number,state,priority,short_description,"
        "assigned_to.name,opened_at,close_notes,close_code"
    )

    if incident_number:
        query = f"number={incident_number}"
        if caller_id:
            # Prevents one caller from looking up someone else's incident
            # just by guessing/knowing its number.
            query += f"^caller_id={caller_id}"
    elif caller_id:
        query = (
            f"caller_id={caller_id}"
            f"^contact_type={ASSISTANT_CONTACT_TYPE}"
            f"^active=true^ORDERBYDESC opened_at"
        )
    else:
        return json.dumps({
            "success": False,
            "message": "Provide an incident_number or a caller_id.",
            "incidents": []
        })

    ok, result = _servicenow_get(
        "/api/now/table/incident",
        {
            "sysparm_query": query,
            "sysparm_fields": fields,
            "sysparm_limit": "5",
        },
    )

    if not ok:
        return json.dumps({
            "success": False,
            "message": result.get("message", "Failed to look up incident status."),
            "incidents": []
        })

    if not result:
        return json.dumps({
            "success": True,
            "message": (
                f"No incident found matching '{incident_number}'."
                if incident_number
                else "No open incidents found for this caller."
            ),
            "incidents": []
        })

    incidents = []
    raw_journals = []  # (row, journal_entries) - display names resolved after this loop

    all_usernames = set()

    for row in result:
        journal_ok, journal = _servicenow_get(
            "/api/now/table/sys_journal_field",
            {
                "sysparm_query": (
                    f"element_id={row.get('sys_id', '')}"
                    # Work notes are internal-only in ServiceNow; agents
                    # often update callers through Comments instead, which
                    # is the customer-visible field - so both are fetched
                    # and merged, oldest first, rather than just work_notes.
                    f"^elementINwork_notes,comments"
                    f"^ORDERBYsys_created_on"
                ),
                "sysparm_fields": "value,sys_created_by,sys_created_on,element",
                "sysparm_limit": "50",
            },
        )

        entries = journal if journal_ok else []
        raw_journals.append((row, entries))

        for entry in entries:
            username = entry.get("sys_created_by", "")
            if username:
                all_usernames.add(username)

    # sys_journal_field.sys_created_by is a plain login username (e.g.
    # "abraham.lincoln"), not a reference field - resolved here to display
    # names in one batched query, so notes read the same way "assigned_to"
    # already does ("Abraham Lincoln"), not as raw usernames.
    display_names = _resolve_display_names(all_usernames)

    for row, entries in raw_journals:
        state_code = row.get("state", "")

        work_notes = [
            {
                "value": entry.get("value", ""),
                "created_by": display_names.get(
                    entry.get("sys_created_by", ""),
                    entry.get("sys_created_by", ""),
                ),
                "created_on": entry.get("sys_created_on", ""),
                "customer_visible": entry.get("element") == "comments",
            }
            for entry in entries
        ]

        incidents.append({
            "number": row.get("number", ""),
            "state": INCIDENT_STATE_LABELS.get(state_code, state_code),
            "priority": row.get("priority", ""),
            "short_description": row.get("short_description", ""),
            "assigned_to": row.get("assigned_to.name", ""),
            "opened_at": row.get("opened_at", ""),
            "close_notes": row.get("close_notes", ""),
            "close_code": row.get("close_code", ""),
            "work_notes": work_notes,
        })

    return json.dumps({
        "success": True,
        "message": "Incident(s) found.",
        "incidents": incidents
    })


# ---------------------------------------------------------
# 6. Close Incident MCP Tool
# ---------------------------------------------------------

@server.tool()
def close_incident(
    incident_number: str,
    resolution_notes: str,
    caller_id: str = "",
) -> str:

    """
    Close an incident on the caller's behalf.

    incident_number:
        The incident to close (e.g. "INC0010021").

    resolution_notes:
        What resolved the issue, provided by the caller. Stored as
        the incident's close_notes.

    caller_id:
        sys_id of the ServiceNow user asking. When set, this is
        verified against the incident's own caller before closing it,
        so one caller can never close someone else's incident.

    Returns structured JSON containing:
    - success
    - message
    - incident_number
    """

    incident_number = (incident_number or "").strip()
    resolution_notes = (resolution_notes or "").strip()
    caller_id = (caller_id or "").strip()

    if not incident_number:
        return json.dumps({
            "success": False,
            "message": "An incident number is required.",
            "incident_number": ""
        })

    if not resolution_notes:
        return json.dumps({
            "success": False,
            "message": "Resolution notes are required to close an incident.",
            "incident_number": incident_number
        })

    if not _servicenow_configured():
        return json.dumps({
            "success": False,
            "message": "ServiceNow is not configured.",
            "incident_number": incident_number
        })

    query = f"number={incident_number}"
    if caller_id:
        query += f"^caller_id={caller_id}"

    ok, result = _servicenow_get(
        "/api/now/table/incident",
        {
            "sysparm_query": query,
            "sysparm_fields": "sys_id,state",
            "sysparm_limit": "1",
        },
    )

    if not ok:
        return json.dumps({
            "success": False,
            "message": result.get("message", "Failed to look up the incident."),
            "incident_number": incident_number
        })

    if not result:
        return json.dumps({
            "success": False,
            "message": (
                f"No incident '{incident_number}' found for this caller."
            ),
            "incident_number": incident_number
        })

    sys_id = result[0].get("sys_id")

    if result[0].get("state") == RESOLVED_STATE:
        return json.dumps({
            "success": True,
            "message": f"{incident_number} is already resolved.",
            "incident_number": incident_number
        })

    url = SERVICENOW_INSTANCE_URL.rstrip("/") + f"/api/now/table/incident/{sys_id}"

    try:

        response = requests.patch(
            url,
            auth=(SERVICENOW_USERNAME, SERVICENOW_PASSWORD),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            json={
                "state": RESOLVED_STATE,
                "close_notes": resolution_notes,
                "close_code": _resolve_close_code(),
            },
            timeout=30,
        )

        if response.status_code == 200:
            return json.dumps({
                "success": True,
                "message": f"{incident_number} has been closed.",
                "incident_number": incident_number
            })

        _log(
            f"close_incident FAILED for {incident_number}: "
            f"HTTP {response.status_code} - {response.text[:500]}"
        )

        return json.dumps({
            "success": False,
            "message": "Failed to close the incident.",
            "http_status": response.status_code,
            "response": response.text[:1000],
            "incident_number": incident_number
        })

    except requests.exceptions.Timeout:

        return json.dumps({
            "success": False,
            "message": "ServiceNow request timed out while closing the incident.",
            "incident_number": incident_number
        })

    except requests.exceptions.RequestException as e:

        return json.dumps({
            "success": False,
            "message": "Unable to connect to ServiceNow.",
            "error": str(e),
            "incident_number": incident_number
        })


# ---------------------------------------------------------
# 6b. Reopen Incident MCP Tool
# ---------------------------------------------------------

@server.tool()
def reopen_incident(
    incident_number: str,
    reason: str,
    caller_id: str = "",
) -> str:

    """
    Reopen an incident that was Resolved or Closed, because the caller
    says the issue isn't actually fixed.

    incident_number:
        The incident to reopen (e.g. "INC0010023").

    reason:
        Why the caller isn't satisfied with the resolution. Added as a
        work note on the incident (not stored as new close_notes - the
        original resolution stays on the record as history).

    caller_id:
        sys_id of the ServiceNow user asking. When set, this is
        verified against the incident's own caller before reopening
        it, so one caller can never reopen someone else's incident.

    Returns structured JSON containing:
    - success
    - message
    - incident_number
    """

    incident_number = (incident_number or "").strip()
    reason = (reason or "").strip()
    caller_id = (caller_id or "").strip()

    if not incident_number:
        return json.dumps({
            "success": False,
            "message": "An incident number is required.",
            "incident_number": ""
        })

    if not reason:
        return json.dumps({
            "success": False,
            "message": "Let me know what's still wrong so I can note it on the incident.",
            "incident_number": incident_number
        })

    if not _servicenow_configured():
        return json.dumps({
            "success": False,
            "message": "ServiceNow is not configured.",
            "incident_number": incident_number
        })

    query = f"number={incident_number}"
    if caller_id:
        query += f"^caller_id={caller_id}"

    ok, result = _servicenow_get(
        "/api/now/table/incident",
        {
            "sysparm_query": query,
            "sysparm_fields": "sys_id,state",
            "sysparm_limit": "1",
        },
    )

    if not ok:
        return json.dumps({
            "success": False,
            "message": result.get("message", "Failed to look up the incident."),
            "incident_number": incident_number
        })

    if not result:
        return json.dumps({
            "success": False,
            "message": (
                f"No incident '{incident_number}' found for this caller."
            ),
            "incident_number": incident_number
        })

    sys_id = result[0].get("sys_id")
    current_state = result[0].get("state")

    if current_state not in (RESOLVED_STATE, "7"):  # 7 = Closed
        return json.dumps({
            "success": True,
            "message": (
                f"{incident_number} isn't resolved or closed, so there's "
                "nothing to reopen - it's still active."
            ),
            "incident_number": incident_number
        })

    url = SERVICENOW_INSTANCE_URL.rstrip("/") + f"/api/now/table/incident/{sys_id}"

    try:

        response = requests.patch(
            url,
            auth=(SERVICENOW_USERNAME, SERVICENOW_PASSWORD),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            json={
                "state": REOPEN_STATE,
                # A plain PATCH to work_notes appends a new journal
                # entry rather than overwriting history - it does not
                # touch the original close_notes/close_code, which stay
                # on the record as the prior resolution attempt.
                "work_notes": (
                    "Reopened via AI Assistant - caller not satisfied "
                    f"with the resolution: {reason}"
                ),
            },
            timeout=30,
        )

        if response.status_code == 200:
            return json.dumps({
                "success": True,
                "message": f"{incident_number} has been reopened.",
                "incident_number": incident_number
            })

        _log(
            f"reopen_incident FAILED for {incident_number}: "
            f"HTTP {response.status_code} - {response.text[:500]}"
        )

        return json.dumps({
            "success": False,
            "message": "Failed to reopen the incident.",
            "http_status": response.status_code,
            "response": response.text[:1000],
            "incident_number": incident_number
        })

    except requests.exceptions.Timeout:

        return json.dumps({
            "success": False,
            "message": "ServiceNow request timed out while reopening the incident.",
            "incident_number": incident_number
        })

    except requests.exceptions.RequestException as e:

        return json.dumps({
            "success": False,
            "message": "Unable to connect to ServiceNow.",
            "error": str(e),
            "incident_number": incident_number
        })


# ---------------------------------------------------------
# 7. Attach File to ServiceNow Incident MCP Tool
# ---------------------------------------------------------

@server.tool()
def attach_incident_file(
    incident_sys_id: str,
    file_path: str
) -> str:

    """
    Attach a local file to an existing ServiceNow incident.

    incident_sys_id:
        ServiceNow sys_id of the incident.

    file_path:
        Full local path of the file to attach.
    """

    # -----------------------------------------------------
    # Validate sys_id
    # -----------------------------------------------------

    if not incident_sys_id:
        return json.dumps({
            "success": False,
            "message": "Incident sys_id is missing."
        })

    # -----------------------------------------------------
    # Validate file
    # -----------------------------------------------------

    if not file_path:
        return json.dumps({
            "success": False,
            "message": "File path is missing."
        })

    if not os.path.isfile(file_path):
        return json.dumps({
            "success": False,
            "message": f"File not found: {file_path}"
        })

    # -----------------------------------------------------
    # Check ServiceNow configuration
    # -----------------------------------------------------

    if not SERVICENOW_INSTANCE_URL:
        return json.dumps({
            "success": False,
            "message": "SERVICENOW_INSTANCE_URL is not configured."
        })

    if not SERVICENOW_USERNAME:
        return json.dumps({
            "success": False,
            "message": "SERVICENOW_USERNAME is not configured."
        })

    if not SERVICENOW_PASSWORD:
        return json.dumps({
            "success": False,
            "message": "SERVICENOW_PASSWORD is not configured."
        })

    # -----------------------------------------------------
    # Prepare attachment
    # -----------------------------------------------------

    file_name = os.path.basename(file_path)

    # Skip if this exact file is already on the incident - happens when a
    # crashed incident flow is retried (create_incident returns the
    # existing incident, then the attachment step runs again).
    ok, already_attached = _servicenow_get(
        "/api/now/attachment",
        {
            "sysparm_query": (
                f"table_name=incident^table_sys_id={incident_sys_id}"
                f"^file_name={file_name}"
            ),
            "sysparm_limit": "1",
            "sysparm_fields": "sys_id,file_name,table_sys_id",
        },
    )

    if ok:
        already_attached = [
            row for row in already_attached
            if row.get("file_name") == file_name
            and row.get("table_sys_id") == incident_sys_id
        ]

    if ok and already_attached:
        return json.dumps({
            "success": True,
            "message": "File was already attached.",
            "file_name": file_name,
            "attachment_sys_id": already_attached[0].get("sys_id", ""),
        })

    url = (
        SERVICENOW_INSTANCE_URL.rstrip("/")
        + "/api/now/attachment/file"
    )

    params = {
        "table_name": "incident",
        "table_sys_id": incident_sys_id,
        "file_name": file_name
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": _get_file_content_type(file_path)
    }

    try:

        with open(file_path, "rb") as file:

            response = requests.post(
                url,
                auth=(
                    SERVICENOW_USERNAME,
                    SERVICENOW_PASSWORD
                ),
                params=params,
                headers=headers,
                data=file,
                timeout=60
            )

        # -------------------------------------------------
        # Attachment successfully created
        # -------------------------------------------------

        if response.status_code in [200, 201]:

            data = response.json()

            result = data.get("result", {})

            return json.dumps({
                "success": True,
                "message": "File attached successfully.",
                "file_name": file_name,
                "attachment_sys_id": result.get(
                    "sys_id",
                    ""
                )
            })

        # -------------------------------------------------
        # Authentication failure
        # -------------------------------------------------

        if response.status_code == 401:

            return json.dumps({
                "success": False,
                "message": (
                    "ServiceNow authentication failed "
                    "while uploading the attachment."
                )
            })

        # -------------------------------------------------
        # Other errors
        # -------------------------------------------------

        return json.dumps({
            "success": False,
            "message": "Failed to attach file.",
            "http_status": response.status_code,
            "response": response.text[:1000]
        })

    except requests.exceptions.Timeout:

        return json.dumps({
            "success": False,
            "message": "Attachment upload timed out."
        })

    except requests.exceptions.RequestException as e:

        return json.dumps({
            "success": False,
            "message": "Unable to upload attachment to ServiceNow.",
            "error": str(e)
        })


# ---------------------------------------------------------
# Helper: File Content Type
# ---------------------------------------------------------

def _get_file_content_type(file_path):

    extension = os.path.splitext(file_path)[1].lower()

    content_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".txt": "text/plain",
        ".log": "text/plain",
        ".pdf": "application/pdf"
    }

    return content_types.get(
        extension,
        "application/octet-stream"
    )
# ---------------------------------------------------------
# 6. Start MCP server
# ---------------------------------------------------------

async def main():

    await server.run_stdio_async()


if __name__ == "__main__":

    asyncio.run(main())