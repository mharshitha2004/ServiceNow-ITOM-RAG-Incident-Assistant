import asyncio
import importlib.util
import json
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from mcp import Client


# ---------------------------------------------------------
# Path to MCP server
# ---------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent.parent

MCP_SERVER = (
    BACKEND_DIR
    / "mcp_server"
    / "server.py"
)


# =========================================================
# IN-PROCESS MCP CONNECTION
# =========================================================
#
# This used to launch mcp_server/server.py as a brand-new Python
# subprocess (stdio transport) for EVERY tool call. Each spawn is a full
# second Python interpreter importing mcp/pydantic/requests - roughly
# 50 MB of RAM on top of the main app - and on Render's 512 MB free tier
# that spike is what got the instance OOM-killed mid-incident-creation
# (incident created in ServiceNow, but the browser got "Sorry, something
# went wrong").
#
# Now the MCPServer object from server.py is imported ONCE into this
# process and the client talks to it in-process. It is still a real MCP
# client/server pair: same tools, same arguments, same JSON results, the
# client still discovers and calls tools over the MCP protocol - only
# the transport changed (in-memory instead of a stdin/stdout pipe). To
# run the server standalone again (e.g. for Claude Desktop or the MCP
# Inspector), `python mcp_server/server.py` still works exactly as before.
# =========================================================

_server_lock = threading.Lock()
_mcp_server = None


def _get_mcp_server():
    """Imports mcp_server/server.py once and returns its MCPServer.
    Loaded by file path under a unique module name, so it can't collide
    with any other module called "server"."""

    global _mcp_server

    if _mcp_server is None:
        with _server_lock:
            if _mcp_server is None:
                spec = importlib.util.spec_from_file_location(
                    "itom_mcp_server", MCP_SERVER
                )
                module = importlib.util.module_from_spec(spec)
                sys.modules["itom_mcp_server"] = module
                spec.loader.exec_module(module)
                _mcp_server = module.server

    return _mcp_server


@asynccontextmanager
async def _mcp_session():
    """Opens an MCP client session to the in-process server. Cheap - no
    subprocess, no handshake over pipes - so one per call is fine."""

    async with Client(_get_mcp_server(), cache=None) as client:
        yield client


# =========================================================
# HELPER - Extract MCP Text Result
# =========================================================

def _extract_mcp_text(result):
    """
    Extract the text returned by an MCP tool.

    MCP returns a CallToolResult containing content items.
    The server returns JSON as text, so this helper extracts
    that text safely.
    """

    if not result:
        return ""

    # MCP result.content
    content = getattr(result, "content", None)

    if not content:
        return ""

    for item in content:

        text = getattr(item, "text", None)

        if text:
            return text

    return ""


async def _call_tool_json(session, tool_name: str, arguments: dict) -> dict:
    """Calls one MCP tool on an ALREADY-OPEN session and returns its
    JSON response as a dict."""

    result = await session.call_tool(tool_name, arguments=arguments)
    response_text = _extract_mcp_text(result)

    if not response_text:
        return {
            "success": False,
            "message": "No response received from MCP server.",
        }

    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        return {"success": False, "message": response_text}


async def _call_tool_once(tool_name: str, arguments: dict) -> dict:
    """Opens a session, calls one tool, returns its JSON as a dict."""

    async with _mcp_session() as session:
        return await _call_tool_json(session, tool_name, arguments)


# =========================================================
# CREATE INCIDENT
# =========================================================

async def create_incident_via_mcp(
    short_description: str,
    description: str,
    priority: str,
    caller_id: str = "",
    correlation_id: str = "",
):

    """
    Call the create_incident MCP tool.

    caller_id, when provided, is the ServiceNow sys_id of the user
    who should be recorded as the caller on the incident (resolved
    from the logged-in website account via lookup_servicenow_user).

    correlation_id, when provided, makes the call idempotent: if an
    incident with this correlation_id already exists, it is returned
    instead of creating a second one (see create_incident in server.py).

    Returns a Python dictionary containing:
        success
        message
        incident_number
        priority
        sys_id
    """

    if priority not in ["P3", "P4"]:

        raise ValueError(
            f"Priority {priority} is not allowed. "
            "AI-created incidents are restricted "
            "to P3 and P4."
        )

    result = await _call_tool_once(
        "create_incident",
        {
            "short_description": short_description,
            "description": description,
            "priority": priority,
            "caller_id": caller_id,
            "correlation_id": correlation_id,
        },
    )

    result.setdefault("incident_number", "")
    result.setdefault("priority", priority)
    result.setdefault("sys_id", "")

    return result


def create_incident(
    short_description: str,
    description: str,
    priority: str,
    caller_id: str = "",
    correlation_id: str = "",
):

    """
    Synchronous wrapper so LangGraph
    can call the MCP tool.
    """

    return asyncio.run(
        create_incident_via_mcp(
            short_description,
            description,
            priority,
            caller_id,
            correlation_id,
        )
    )


# =========================================================
# CREATE INCIDENT + CALLER LOOKUP + ATTACHMENTS, ONE SESSION
# =========================================================


async def create_incident_full_via_mcp(
    short_description: str,
    description: str,
    priority: str,
    caller_username: str = "",
    attachments: Optional[list] = None,
    correlation_id: str = "",
):
    """
    attachments: optional list of (file_path, label) tuples, attached
    best-effort after the incident is created - one failing never
    blocks the incident response or the other attachments.

    correlation_id: pass the LangGraph thread_id here. If this exact
    incident flow already created an incident (e.g. the server crashed
    after ServiceNow saved it but before the browser got the answer),
    the existing incident is returned instead of a duplicate.

    Returns a dict:
        caller_sys_id: "" if no caller_username was given, or the
            lookup failed (incident creation is never blocked by this).
        caller_lookup_warning: None, or why the lookup didn't resolve.
        incident: the create_incident result dict.
        attachment_results: [{"label": ..., "result": dict | None,
                               "error": str | None}, ...], one entry
            per item in `attachments`, in order.
    """

    if priority not in ["P3", "P4"]:
        raise ValueError(
            f"Priority {priority} is not allowed. "
            "AI-created incidents are restricted to P3 and P4."
        )

    caller_sys_id = ""
    caller_lookup_warning = None
    attachment_results = []

    async with _mcp_session() as session:

        # ---- 1. Resolve caller (optional) ----
        if caller_username:
            lookup_result = await _call_tool_json(
                session,
                "lookup_servicenow_user",
                {"username": caller_username},
            )

            if lookup_result.get("success"):
                caller_sys_id = lookup_result.get("sys_id", "")
            else:
                caller_lookup_warning = (
                    f"Could not resolve ServiceNow caller for "
                    f"'{caller_username}': {lookup_result}"
                )

        # ---- 2. Create the incident (or find the one already created) ----
        incident_result = await _call_tool_json(
            session,
            "create_incident",
            {
                "short_description": short_description,
                "description": description,
                "priority": priority,
                "caller_id": caller_sys_id,
                "correlation_id": correlation_id,
            },
        )

        incident_result.setdefault("incident_number", "")
        incident_result.setdefault("priority", priority)
        incident_result.setdefault("sys_id", "")

        # ---- 3. Attach any provided files ----
        # attach_incident_file skips a file that's already attached under
        # the same name, so re-running this after a crash doesn't attach
        # the same screenshot twice.
        incident_success = incident_result.get("success", False)
        incident_sys_id = incident_result.get("sys_id", "")

        for file_path, label in (attachments or []):

            if not incident_success:
                attachment_results.append({
                    "label": label,
                    "result": None,
                    "error": "Incident creation failed - skipping attachment.",
                })
                continue

            if not incident_sys_id:
                attachment_results.append({
                    "label": label,
                    "result": None,
                    "error": (
                        "Incident was created but ServiceNow did not "
                        "return a sys_id - skipping attachment."
                    ),
                })
                continue

            if not Path(file_path).is_file():
                # e.g. the temp upload was wiped by a restart before a retry.
                attachment_results.append({
                    "label": label,
                    "result": None,
                    "error": f"Attachment file no longer exists: {file_path}",
                })
                continue

            try:
                attach_result = await _call_tool_json(
                    session,
                    "attach_incident_file",
                    {
                        "incident_sys_id": incident_sys_id,
                        "file_path": str(Path(file_path).resolve()),
                    },
                )
                attachment_results.append({
                    "label": label,
                    "result": attach_result,
                    "error": None,
                })
            except Exception as attachment_error:
                attachment_results.append({
                    "label": label,
                    "result": None,
                    "error": str(attachment_error),
                })

    return {
        "caller_sys_id": caller_sys_id,
        "caller_lookup_warning": caller_lookup_warning,
        "incident": incident_result,
        "attachment_results": attachment_results,
    }


def create_incident_full(
    short_description: str,
    description: str,
    priority: str,
    caller_username: str = "",
    attachments: Optional[list] = None,
    correlation_id: str = "",
):
    """Synchronous wrapper so LangGraph can call this."""

    return asyncio.run(
        create_incident_full_via_mcp(
            short_description,
            description,
            priority,
            caller_username,
            attachments,
            correlation_id,
        )
    )


# =========================================================
# LOOKUP SERVICENOW USER
# =========================================================

async def lookup_servicenow_user_via_mcp(username: str):

    """
    Call the lookup_servicenow_user MCP tool.

    Returns a Python dictionary containing:
        success
        message
        sys_id
        name
        user_name
    """

    if not username:

        raise ValueError(
            "Username is required for a ServiceNow user lookup."
        )

    result = await _call_tool_once(
        "lookup_servicenow_user",
        {"username": username},
    )
    result.setdefault("sys_id", "")
    return result


def lookup_servicenow_user(username: str):

    """
    Synchronous wrapper so it can be called from FastAPI route
    handlers and from the LangGraph agent without either needing
    to manage an event loop.
    """

    return asyncio.run(
        lookup_servicenow_user_via_mcp(username)
    )


# =========================================================
# GET INCIDENT STATUS
# =========================================================

async def get_incident_status_via_mcp(
    incident_number: str = "",
    caller_id: str = "",
):

    """
    Call the get_incident_status MCP tool.

    Returns a Python dictionary containing:
        success
        message
        incidents: a list of {number, state, priority,
        short_description, assigned_to, opened_at, close_notes,
        close_code, work_notes}
    """

    result = await _call_tool_once(
        "get_incident_status",
        {
            "incident_number": incident_number,
            "caller_id": caller_id,
        },
    )
    result.setdefault("incidents", [])
    return result


def get_incident_status(incident_number: str = "", caller_id: str = ""):

    """
    Synchronous wrapper so it can be called from FastAPI route
    handlers and from the LangGraph agent without either needing
    to manage an event loop.
    """

    return asyncio.run(
        get_incident_status_via_mcp(incident_number, caller_id)
    )


# =========================================================
# CLOSE INCIDENT
# =========================================================

async def close_incident_via_mcp(
    incident_number: str,
    resolution_notes: str,
    caller_id: str = "",
):

    """
    Call the close_incident MCP tool.

    Returns a Python dictionary containing:
        success
        message
        incident_number
    """

    result = await _call_tool_once(
        "close_incident",
        {
            "incident_number": incident_number,
            "resolution_notes": resolution_notes,
            "caller_id": caller_id,
        },
    )
    result.setdefault("incident_number", incident_number)
    return result


def close_incident(
    incident_number: str,
    resolution_notes: str,
    caller_id: str = "",
):

    """
    Synchronous wrapper so it can be called from FastAPI route
    handlers and from the LangGraph agent without either needing
    to manage an event loop.
    """

    return asyncio.run(
        close_incident_via_mcp(incident_number, resolution_notes, caller_id)
    )


# =========================================================
# REOPEN INCIDENT
# =========================================================

async def reopen_incident_via_mcp(
    incident_number: str,
    reason: str,
    caller_id: str = "",
):

    """
    Call the reopen_incident MCP tool.

    Returns a Python dictionary containing:
        success
        message
        incident_number
    """

    result = await _call_tool_once(
        "reopen_incident",
        {
            "incident_number": incident_number,
            "reason": reason,
            "caller_id": caller_id,
        },
    )
    result.setdefault("incident_number", incident_number)
    return result


def reopen_incident(
    incident_number: str,
    reason: str,
    caller_id: str = "",
):

    """
    Synchronous wrapper so it can be called from FastAPI route
    handlers and from the LangGraph agent without either needing
    to manage an event loop.
    """

    return asyncio.run(
        reopen_incident_via_mcp(incident_number, reason, caller_id)
    )


# =========================================================
# ATTACHMENT
# =========================================================

async def attach_incident_file_via_mcp(
    incident_sys_id: str,
    file_path: str,
):

    """
    Call the attach_incident_file MCP tool.

    Returns a Python dictionary containing:
        success
        message
        file_name
        attachment_sys_id
    """

    if not incident_sys_id:

        raise ValueError(
            "Incident sys_id is required "
            "for attachment."
        )

    if not file_path:

        raise ValueError(
            "File path is required "
            "for attachment."
        )

    file = Path(file_path)

    if not file.is_file():

        raise FileNotFoundError(
            f"Attachment file not found: {file_path}"
        )

    return await _call_tool_once(
        "attach_incident_file",
        {
            "incident_sys_id": incident_sys_id,
            "file_path": str(file.resolve()),
        },
    )


def attach_incident_file(
    incident_sys_id: str,
    file_path: str,
):

    """
    Synchronous wrapper so LangGraph
    can call the attachment MCP tool.
    """

    return asyncio.run(
        attach_incident_file_via_mcp(
            incident_sys_id,
            file_path,
        )
    )
