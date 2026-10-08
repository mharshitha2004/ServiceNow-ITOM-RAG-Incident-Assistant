import os
from typing import TypedDict, Optional
import json
import re
import sys
from pathlib import Path
from pymongo import MongoClient
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from langgraph.checkpoint.mongodb import MongoDBSaver
from mcp_client import (
    create_incident_full,
    lookup_servicenow_user,  # still used standalone by _resolve_caller_sys_id
    get_incident_status,
    close_incident,
    reopen_incident,
)

# ---------------------------------------------------------
# Make parent Backend directory available
# ---------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

# ---------------------------------------------------------
# Existing RAG and MULTIMODAL
# ---------------------------------------------------------

from rag import answer_question
from multimodal import analyze_image

# ---------------------------------------------------------
# Agent State
# ---------------------------------------------------------

class AgentState(TypedDict, total=False):
    question: str
    intent: str
    response: str

    image_path: str
    image_analysis: str

    # A non-image file attached to an incident report (.txt log or .zip
    # archive) - separate from image_path/image_analysis above since it
    # goes through different handling (text is analyzed by Gemini as
    # text, not vision; an archive isn't analyzed at all, just attached
    # to the incident for a human to open).
    attachment_path: str
    attachment_kind: str      # "text" | "archive"
    attachment_filename: str
    attachment_analysis: str

    # Incident workflow
    troubleshooting_answer: str
    needs_incident: bool
    user_confirmed: bool
    priority: str

    # The ServiceNow username of the logged-in website account that
    # started this conversation (set by main.py from the session, at
    # /incident/start). Used at incident-creation time to resolve a
    # sys_id so the incident's caller field is set correctly.
    caller_username: str

    # NOTE: these two MUST be declared here, or LangGraph will not
    # treat them as valid state channels - any value a node returns
    # for an undeclared key is silently dropped instead of being
    # merged into state. That was causing route_after_incident_confirmation
    # (and route_after_troubleshooting) to always see None/falsy for
    # these fields, so the graph fell through to "end" instead of
    # continuing on to the priority question.
    user_satisfied: bool
    create_incident_requested: bool

    # The most recent incident number mentioned earlier in this saved
    # conversation (set by main.py at /incident/start). Lets follow-ups
    # like "who is the assignee?" or "close it" refer to "the incident we
    # just created" without the person retyping INC0010027.
    last_incident_number: str

# ---------------------------------------------------------
# 1. Classify request
# ---------------------------------------------------------

def classify_request(state: AgentState):

    question = state["question"].lower().strip()

    # -----------------------------------------------------
    # Status check / close request - checked first, since these
    # can easily contain a problem_keyword too (e.g. "status of my
    # incident, Discovery is failing") and would otherwise get
    # misrouted into the troubleshooting flow below.
    # -----------------------------------------------------

    reopen_keywords = [
        "reopen incident", "reopen my incident", "reopen the incident",
        "re-open incident", "re-open my incident", "re-open the incident",
        "reopen ticket", "re-open ticket",
        "not satisfied with this resolution", "not satisfied with the resolution",
        "issue is not resolved", "issue is still not resolved",
        "this is not resolved", "still not fixed", "not actually fixed",
    ]

    if any(keyword in question for keyword in reopen_keywords) or (
        "reopen" in question or "re-open" in question
    ):
        return {
            "intent": "reopen_incident"
        }

    close_keywords = [
        "close incident", "close my incident", "close the incident",
        "close ticket", "close my ticket", "resolve incident",
        "resolve my incident", "mark incident as resolved",
        "mark as resolved", "mark this resolved",
    ]

    # Whole word only: "is my incident closed?" is a status question,
    # not a request to close it (plain `"close" in question` matched it).
    if any(keyword in question for keyword in close_keywords) or (
        re.search(r"\bclose\b", question) and (
            "incident" in question
            or "ticket" in question
            or _extract_incident_number(question)
            # "close it" / "please close this", right after creating one
            or (state.get("last_incident_number") and len(question.split()) <= 5)
        )
    ):
        return {
            "intent": "close_incident"
        }

    status_keywords = [
        "status of my incident", "status of incident", "incident status",
        "what's the status", "whats the status", "update on my incident",
        "where is my incident", "how is my incident", "track my incident",
        "check my incident", "check on my incident",
        # Follow-up questions about an incident's owner/progress. On the
        # Incident Assistant these are never documentation questions -
        # without them, "can I know the assignee name" fell through to
        # the RAG docs search and got an answer about Alert records.
        "assignee", "assigned to", "who is assigned", "who's assigned",
        "whos assigned", "who is working", "who's working", "whos working",
        "who is handling", "who's handling", "whos handling",
        "who is looking", "who's looking", "who picked",
        "assignment group", "work notes", "work note",
        "any update", "any updates", "latest update", "any progress",
        "status of my ticket", "ticket status",
        "is it closed", "is it resolved", "been resolved", "been closed",
        "incident closed", "incident resolved", "ticket closed",
    ]

    # Short follow-ups that only make sense about an incident ("status?",
    # "any news on it?") count when this conversation already has one.
    # Kept to short messages so a real docs question like "how do I
    # update the MID Server config" still goes to documentation.
    follow_up_words = ["status", "update", "progress", "news"]
    is_short_follow_up = (
        bool(state.get("last_incident_number"))
        and len(question.split()) <= 5
    )

    if any(keyword in question for keyword in status_keywords) or (
        "status" in question and (
            "incident" in question
            or _extract_incident_number(question)
        )
    ) or (
        is_short_follow_up
        and any(word in question for word in follow_up_words)
    ):
        return {
            "intent": "status_check"
        }

    # Explicit incident request
    incident_keywords = [
        "create incident",
        "raise incident",
        "open incident",
        "log incident",
        "create a ticket",
        "raise a ticket",
        "open a ticket",
        "report an incident",
        "create a case",
    ]

    # User is reporting an actual problem/issue
    problem_keywords = [
        "is down",
        "down",
        "not working",
        "doesn't work",
        "doesnt work",
        "not responding",
        "failed",
        "failure",
        "error",
        "issue",
        "problem",
        "unable to",
        "cannot",
        "can't",
        "cant",
        "broken",
        "stopped",
        "crashed",
        "unavailable",
        "connection refused",
        "connection failed",
    ]

    # -----------------------------------------------------
    # Explicit request to create an incident
    # -----------------------------------------------------

    if any(keyword in question for keyword in incident_keywords):

        return {
            "intent": "incident"
        }

    # -----------------------------------------------------
    # A screenshot, log file, or archive was attached on the Incident
    # Assistant, so the person is reporting a problem even if their
    # text has no "error"/"failed" keywords. Route it through the
    # incident flow so the attachment is actually analyzed - the
    # documentation branch never looks at image_path/attachment_path.
    # -----------------------------------------------------

    if state.get("image_path") or state.get("attachment_path"):

        return {
            "intent": "problem_report"
        }

    # -----------------------------------------------------
    # User reports a problem, but does NOT explicitly
    # ask for an incident.
    # -----------------------------------------------------

    if any(keyword in question for keyword in problem_keywords):

        return {
            "intent": "problem_report"
        }

    # -----------------------------------------------------
    # Small talk / greeting - this is the Incident Assistant,
    # so it should say so rather than silently answering as
    # if it were the documentation bot.
    # -----------------------------------------------------

    greeting_keywords = [
        "hi", "hello", "hey", "hlo", "yo",
        "good morning", "good afternoon", "good evening",
    ]

    if question in greeting_keywords or len(question) <= 3:

        return {
            "intent": "greeting"
        }

    # -----------------------------------------------------
    # Otherwise treat as documentation request
    # -----------------------------------------------------

    return {
        "intent": "documentation"
    }


# ---------------------------------------------------------
# 1b. Greeting → canned incident-assistant response
# ---------------------------------------------------------

def handle_greeting(state: AgentState):

    return {
        "response": (
            "Hi! I'm the Incident Assistant. Describe the issue you're "
            "seeing (e.g. \"MID Server is down\" or \"Discovery failed\") "
            "and I'll check documentation first, then offer to create a "
            "ServiceNow incident if it's still unresolved."
        )
    }


# ---------------------------------------------------------
# 2. Documentation → Existing RAG
# ---------------------------------------------------------

def handle_documentation(state: AgentState):

    question = state["question"]

    print("\n[LangGraph] Documentation request detected.")
    print("[LangGraph] Sending question to existing RAG...")

    answer = answer_question(question)

    return {
        "response": answer
    }

# ---------------------------------------------------------
# 3. Multimodal Image Analysis
# ---------------------------------------------------------

def analyze_image_evidence(image_path: str) -> str:

    print("\n[LangGraph] Sending image to multimodal LLM...")

    try:
        from google import genai
        from PIL import Image
        import os

        # Use the same Gemini API key that your existing RAG uses
        client = genai.Client(
            api_key=os.getenv("GEMINI_API_KEY")
        )

        image = Image.open(image_path)

        prompt = """
You are a ServiceNow ITOM technical support assistant.

Analyze the uploaded screenshot, error message, log image,
or technical evidence.

Extract only information that is clearly visible in the image.

Focus on:

1. Error messages
2. Error codes
3. Service names
4. MID Server names
5. Hostnames
6. URLs
7. Configuration information
8. Stack traces
9. Relevant technical details

Do not invent information that is not visible.

Return a concise technical summary that can be used by
another AI system for ServiceNow troubleshooting.
"""

        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=[
                prompt,
                image
            ]
        )

        analysis = response.text.strip()

        print("\n" + "=" * 70)
        print("IMAGE ANALYSIS")
        print("=" * 70)
        print(analysis)

        return analysis

    except Exception as e:

        print("\n[LangGraph] Image analysis failed:")
        print(str(e))

        return (
            "Image analysis could not be completed. "
            "Continue troubleshooting using the user's text "
            "and available ServiceNow documentation."
        )

# ---------------------------------------------------------
# 3b. Multimodal Log File Analysis
# ---------------------------------------------------------

# Keeps the prompt (and therefore cost/latency) bounded even for a
# large log file - this is meant to catch the relevant error, not
# ingest an entire log verbatim.
_LOG_TEXT_MAX_CHARS = 8000


def analyze_log_text(file_path: str, filename: str) -> str:

    print(f"\n[LangGraph] Sending log file '{filename}' to LLM for analysis...")

    try:
        from google import genai
        import os

        client = genai.Client(
            api_key=os.getenv("GEMINI_API_KEY")
        )

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            log_text = f.read(_LOG_TEXT_MAX_CHARS)

        prompt = f"""
You are a ServiceNow ITOM technical support assistant.

Analyze the attached log file excerpt below (filename: {filename}).

Extract only information that is clearly present in the text.

Focus on:

1. Error messages and stack traces
2. Error codes
3. Service names
4. MID Server names
5. Hostnames
6. URLs
7. Configuration information
8. Timestamps of relevant events
9. Any other technical detail relevant to troubleshooting

Do not invent information that is not present in the log.

Return a concise technical summary that can be used by another AI
system for ServiceNow troubleshooting.

LOG FILE CONTENT:
{log_text}
"""

        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt
        )

        analysis = response.text.strip()

        print("\n" + "=" * 70)
        print("LOG FILE ANALYSIS")
        print("=" * 70)
        print(analysis)

        return analysis

    except Exception as e:

        print("\n[LangGraph] Log file analysis failed:")
        print(str(e))

        return (
            "Log file analysis could not be completed. "
            "Continue troubleshooting using the user's text "
            "and available ServiceNow documentation."
        )

# ----------------------------------------------------------
# 4. Incident / Problem → Existing RAG first and MULTIMODAL
# ----------------------------------------------------------

def handle_incident(state: AgentState):

    question = state["question"]
    image_path = state.get("image_path")
    attachment_path = state.get("attachment_path")
    attachment_kind = state.get("attachment_kind", "")
    attachment_filename = state.get("attachment_filename", "")

    print("\n[LangGraph] Problem/incident request detected.")

    # ---------------------------------------------------------
    # Analyze image if provided
    # ---------------------------------------------------------

    image_analysis = ""

    if image_path:

        print("\n[LangGraph] Image evidence detected.")

        image_analysis = analyze_image_evidence(
            image_path
        )

    # ---------------------------------------------------------
    # Analyze a .txt log file if provided. A .zip archive is not
    # analyzed - there's no text to extract - it's just noted here
    # and attached to the incident as-is later, in create_incident_node.
    # ---------------------------------------------------------

    attachment_analysis = ""

    if attachment_path and attachment_kind == "text":

        print(f"\n[LangGraph] Log file evidence detected: {attachment_filename}")

        attachment_analysis = analyze_log_text(
            attachment_path,
            attachment_filename
        )

    elif attachment_path and attachment_kind == "archive":

        print(f"\n[LangGraph] Archive attached: {attachment_filename}")

        attachment_analysis = (
            f"An archive ('{attachment_filename}') was attached. Its "
            "contents were not analyzed automatically - it has been "
            "attached to the incident for the assigned agent to review."
        )

    # -----------------------------------------------------
    # Build enhanced question for RAG
    # -----------------------------------------------------

    rag_question = question

    if image_analysis:

        rag_question = f"""
        User reported issue:

        {question}

        Additional technical information extracted from the
        user-provided image:

        {image_analysis}

        Use both the user's issue and the image-derived information
        when searching the ServiceNow documentation.
        """

    if attachment_kind == "text" and attachment_analysis:

        rag_question = f"""
        {rag_question}

        Additional technical information extracted from an
        attached log file ({attachment_filename}):

        {attachment_analysis}

        Use this information too when searching the ServiceNow
        documentation.
        """

    # -----------------------------------------------------
    # Existing RAG
    # -----------------------------------------------------

    print("\n[LangGraph] Checking ServiceNow documentation first...")

    rag_answer = answer_question(rag_question)

    # -----------------------------------------------------
    # Final troubleshooting response
    # -----------------------------------------------------

    response_text = (
        "I checked the available ServiceNow documentation "
        "for the reported issue.\n\n"
        f"{rag_answer}"
    )

    if image_analysis:

        response_text += (
            "\n\n"
            "I also analyzed the image you provided and "
            "used the extracted technical information "
            "during troubleshooting."
        )

    if attachment_kind == "text" and attachment_analysis:

        response_text += (
            "\n\n"
            f"I also reviewed the attached log file "
            f"({attachment_filename}) and used the extracted "
            "technical information during troubleshooting."
        )

    elif attachment_kind == "archive":

        response_text += (
            "\n\n"
            f"I've noted the attached archive ({attachment_filename}) - "
            "it'll be attached to the incident for review if one is "
            "created."
        )

    response_text += (
        "\n\n"
        "Are you satisfied with the troubleshooting information "
        "provided above, or would you like me to create a "
        "ServiceNow incident for this issue?"
    )

    return {
        "troubleshooting_answer": rag_answer,
        "image_analysis": image_analysis,
        "attachment_analysis": attachment_analysis,
        "needs_incident": True,
        "user_confirmed": False,
        "priority": state.get("priority", ""),
        "response": response_text,
    }
# ---------------------------------------------------------
# 5. Ask user whether the troubleshooting information
#    was sufficient
# ---------------------------------------------------------

def ask_user_satisfaction(state: AgentState):

    print("\n" + "=" * 70)
    print("TROUBLESHOOTING RESULT")
    print("=" * 70)

    print(state["response"])

    # -------------------------------------------------------------
    # interrupt() pauses the graph here and hands control back to
    # whoever is running it (CLI loop or the FastAPI /incident/reply
    # endpoint). The value passed in becomes the payload the caller
    # sees; whatever the caller resumes with (Command(resume=...))
    # is returned right here, as if input() had returned it.
    # -------------------------------------------------------------

    choice = interrupt({
        "type": "satisfaction",
        "message": state["response"],
        "options": [
            "Yes - the information is sufficient",
            "No - I still need assistance",
        ],
    })

    choice = str(choice).strip().lower()

    if choice in ("1", "yes", "y", "yes - the information is sufficient"):

        return {
            "user_satisfied": True,
            "needs_incident": False,
            "response": (
                "Great. I'm glad the troubleshooting information "
                "was helpful. No incident will be created."
            )
        }

    return {
        "user_satisfied": False,
        "response": (
            "Understood. Since the troubleshooting information "
            "did not resolve the issue, we can create a "
            "ServiceNow incident if you would like."
        )
    }
# ---------------------------------------------------------
# 6. Ask whether user wants an incident
# ---------------------------------------------------------

def ask_create_incident(state: AgentState):

    print("\n" + "=" * 70)
    print("INCIDENT ESCALATION")
    print("=" * 70)

    print(
        "\nWould you like me to create a ServiceNow incident "
        "for this issue?"
    )

    choice = interrupt({
        "type": "confirm_incident",
        "message": (
            "Would you like me to create a ServiceNow incident "
            "for this issue?"
        ),
        "options": ["Yes", "No"],
    })

    choice = str(choice).strip().lower()

    if choice in ("1", "yes", "y"):

        return {
            "create_incident_requested": True,
            "needs_incident": True,
            "response": (
                "Understood. I can create an incident. "
                "Only P3 and P4 incidents can be created "
                "through this AI assistant."
            )
        }

    return {
        "create_incident_requested": False,
        "needs_incident": False,
        "response": (
            "Understood. No incident will be created."
        )
    }


# ---------------------------------------------------------
# 7. Ask for priority
# ---------------------------------------------------------

def ask_priority(state: AgentState):

    print("\n" + "=" * 70)
    print("INCIDENT PRIORITY")
    print("=" * 70)

    print("\nSelect incident priority:")
    print("P3 - Medium priority")
    print("P4 - Low priority")
    print("P1/P2 - Not allowed through AI Assistant")

    priority = interrupt({
        "type": "priority",
        "message": "Select incident priority (P3 or P4).",
        "options": ["P3", "P4"],
    })

    priority = str(priority).strip().upper()

    return {
        "priority": priority
    }


# ---------------------------------------------------------
# 8. Validate priority
# ---------------------------------------------------------

def validate_priority(state: AgentState):

    priority = state.get("priority", "").upper()

    if priority in ["P1", "P2"]:

        return {
            "response": (
                f"Incident creation blocked.\n\n"
                f"{priority} incidents cannot be created through "
                "this AI assistant.\n\n"
                "Only P3 and P4 incidents can be created through "
                "this interface. P1 and P2 incidents must follow "
                "the standard ServiceNow incident management "
                "and approval process."
            ),
            "needs_incident": False
        }

    if priority in ["P3", "P4"]:

        return {
            "needs_incident": True
        }

    return {
        "response": (
            "Invalid priority.\n\n"
            "Only P3 and P4 incidents can be created through "
            "this AI assistant."
        ),
        "needs_incident": False
    }


# ---------------------------------------------------------
# 8b. Shared: attach a local file to an already-created incident
# ---------------------------------------------------------

def _log_attachment_result(
    label: str,
    result: Optional[dict],
    error: Optional[str],
) -> None:
    """Logs the outcome of one best-effort attachment attempt. The
    actual attach_incident_file MCP call now happens inside
    create_incident_full() (mcp_client.py) as part of one shared
    session with the lookup + create_incident calls, instead of its
    own separate subprocess spawn - this only prints what came back,
    same messages _attach_file_to_incident used to print itself."""

    print("\n" + "=" * 70)
    print(f"ATTACHMENT: {label}")
    print("=" * 70)

    if error:
        print(f"\n[LangGraph] WARNING: {label} attachment failed.")
        print(f"[LangGraph] Attachment error: {error}")
        return

    print("\n[LangGraph] Attachment MCP response:")
    print(result)

    if isinstance(result, dict):

        if result.get("success"):
            print(f"\n[LangGraph] {label} attached successfully.")
        else:
            print(
                f"\n[LangGraph] WARNING: Incident was created, but "
                f"{label} attachment failed."
            )
            print(
                "[LangGraph] Attachment error:",
                result.get("message", "Unknown attachment error.")
            )

    else:
        print("\n[LangGraph] Attachment response received.")


# ---------------------------------------------------------
# 9. Create Incident through MCP
# ---------------------------------------------------------
def create_incident_node(state: AgentState, config: RunnableConfig):

    priority = state.get("priority", "P4")

    # One conversation thread can create at most one incident, so the
    # thread id doubles as an idempotency key (stored in the incident's
    # correlation_id). If this node runs a second time for the same
    # thread - because the server died after ServiceNow saved the
    # incident but before this node finished and checkpointed - the MCP
    # tool returns the incident that already exists instead of making a
    # duplicate.
    thread_id = (config or {}).get("configurable", {}).get("thread_id", "")

    # ---------------------------------------------------------
    # Hard safety rule
    # ---------------------------------------------------------

    if priority not in ["P3", "P4"]:

        return {
            "response": (
                "Incident creation blocked.\n\n"
                f"Priority {priority} cannot be created through "
                "the AI assistant. Only P3 and P4 incidents "
                "are allowed."
            ),
            "needs_incident": False,
        }

    question = state["question"]

    troubleshooting_answer = state.get(
        "troubleshooting_answer",
        ""
    )

    image_analysis = state.get(
        "image_analysis",
        ""
    )

    image_path = state.get(
        "image_path",
        None
    )

    attachment_analysis = state.get(
        "attachment_analysis",
        ""
    )

    attachment_path = state.get(
        "attachment_path",
        None
    )

    attachment_kind = state.get(
        "attachment_kind",
        ""
    )

    attachment_filename = state.get(
        "attachment_filename",
        ""
    )

    print("\n" + "=" * 70)
    print("CREATING INCIDENT")
    print("=" * 70)

    print("\n[LangGraph] Calling MCP create_incident...")
    print(f"[LangGraph] Priority: {priority}")

    caller_username = state.get("caller_username", "")

    if caller_username:
        print(
            f"[LangGraph] Resolving ServiceNow caller for "
            f"'{caller_username}'..."
        )

    # ---------------------------------------------------------
    # Build incident description
    # ---------------------------------------------------------

    description = (
        f"Reported issue:\n"
        f"{question}\n\n"
        f"Troubleshooting information retrieved by AI:\n"
        f"{troubleshooting_answer}"
    )

    # ---------------------------------------------------------
    # Add Gemini image analysis ONLY when image exists
    # ---------------------------------------------------------

    if image_analysis:

        description += (
            "\n\n"
            "Image Evidence:\n"
            f"{image_analysis}"
        )

    # ---------------------------------------------------------
    # Add log file / archive evidence, when provided
    # ---------------------------------------------------------

    if attachment_kind == "text" and attachment_analysis:

        description += (
            "\n\n"
            f"Log File Evidence ({attachment_filename}):\n"
            f"{attachment_analysis}"
        )

    elif attachment_kind == "archive":

        description += (
            "\n\n"
            f"Attached Archive ({attachment_filename}):\n"
            "A zip archive has been attached to this incident. Its "
            "contents were not analyzed automatically - please review "
            "the attachment directly."
        )

    # ---------------------------------------------------------
    # Resolve caller + create the incident + attach any files, all
    # on ONE shared MCP session (see create_incident_full in
    # mcp_client.py for why this is one call instead of up to three).
    # ---------------------------------------------------------

    attachments = []

    if image_path:
        attachments.append((image_path, "image"))

    if attachment_path:
        attachments.append(
            (attachment_path, attachment_filename or attachment_kind or "attachment")
        )

    full_result = create_incident_full(
        short_description=question[:160],
        description=description,
        priority=priority,
        caller_username=caller_username,
        attachments=attachments,
        correlation_id=thread_id,
    )

    caller_sys_id = full_result["caller_sys_id"]
    caller_lookup_warning = full_result["caller_lookup_warning"]
    result = full_result["incident"]

    if caller_sys_id:
        print(f"[LangGraph] Resolved caller sys_id: {caller_sys_id}")
    elif caller_lookup_warning:
        print(f"[LangGraph] WARNING: {caller_lookup_warning}")

    # ---------------------------------------------------------
    # IMPORTANT:
    # mcp_client.create_incident_full() already returns the incident
    # as a Python dictionary (create_incident_full_via_mcp always
    # fills success/incident_number/priority/sys_id, even on failure).
    # ---------------------------------------------------------

    print("\n[LangGraph] MCP create_incident response:")
    print(result)

    # ---------------------------------------------------------
    # Extract incident information
    # ---------------------------------------------------------

    incident_success = result.get(
        "success",
        False
    )

    incident_message = result.get(
        "message",
        "Incident creation completed."
    )

    incident_number = result.get(
        "incident_number",
        ""
    )

    incident_sys_id = result.get(
        "sys_id",
        ""
    )

    assigned_to = result.get(
        "assigned_to",
        ""
    )

    # ---------------------------------------------------------
    # Print returned incident details
    # ---------------------------------------------------------

    print("\n[LangGraph] Incident creation result:")
    print(f"[LangGraph] Success: {incident_success}")
    print(f"[LangGraph] Incident Number: {incident_number}")
    print(f"[LangGraph] Sys ID: {incident_sys_id}")

    # ---------------------------------------------------------
    # Log the outcome of any attachments (already performed inside
    # create_incident_full, on the same session as above).
    # ---------------------------------------------------------

    for attachment_outcome in full_result["attachment_results"]:
        _log_attachment_result(
            attachment_outcome["label"],
            attachment_outcome["result"],
            attachment_outcome["error"],
        )

    # ---------------------------------------------------------
    # Final response
    # ---------------------------------------------------------

    if incident_success:

        # Two trailing spaces + newline is a markdown hard line break.
        # A bare "\n" gets collapsed into one paragraph by the chat's
        # markdown renderer, which is why this used to print on one line.
        final_response = (
            f"{incident_message}  \n"
            f"Incident Number: {incident_number}  \n"
            f"Priority: {priority}  \n"
        )

        if assigned_to:
            final_response += f"Assigned to: {assigned_to}  \n"

        final_response += f"Sys ID: {incident_sys_id}"

    else:

        final_response = incident_message

    return {
        "response": final_response,
        "needs_incident": False,
        "user_confirmed": True,
    }


# ---------------------------------------------------------
# 9b. Shared helpers for status check / close
# ---------------------------------------------------------

_INCIDENT_NUMBER_PATTERN = re.compile(r"\bINC\d{4,}\b", re.IGNORECASE)


def _extract_incident_number(text: str) -> str:
    match = _INCIDENT_NUMBER_PATTERN.search(text or "")
    return match.group(0).upper() if match else ""


def _incident_number_for(state: AgentState) -> str:
    """The incident the person means: one typed in this message, else the
    last one this conversation created or talked about."""

    return (
        _extract_incident_number(state.get("question", ""))
        or state.get("last_incident_number", "")
    )


def _format_mcp_failure(result, fallback: str) -> str:
    """Turns a failed close_incident/reopen_incident result into an
    actionable chat message, instead of just the generic "Failed to
    ... the incident." that used to be all the user ever saw - the
    real reason (HTTP status + ServiceNow's own error text, when
    present) was already being captured by the MCP tool, just never
    surfaced past this point."""

    if not isinstance(result, dict):
        return fallback

    message = result.get("message", fallback)
    http_status = result.get("http_status")
    raw_response = result.get("response")

    if not http_status:
        return message

    detail = ""

    if raw_response:
        try:
            parsed = json.loads(raw_response)
            error = parsed.get("error") or {}
            error_message = error.get("message") or ""
            error_detail = error.get("detail") or ""

            if error_message and error_detail and error_detail != error_message:
                detail = f"{error_message} ({error_detail})"
            else:
                detail = error_message or error_detail
        except (json.JSONDecodeError, AttributeError, TypeError):
            detail = str(raw_response)[:300]

    if detail:
        return f"{message} ServiceNow said: {detail}"

    return f"{message} (ServiceNow returned HTTP {http_status}.)"


def _resolve_caller_sys_id(caller_username: str) -> str:
    """Same lookup create_incident_node does, kept separate here so a
    failed lookup can't accidentally break incident creation - only
    status/close, which already require a caller to do anything useful."""

    if not caller_username:
        return ""

    try:
        result = lookup_servicenow_user(caller_username)

        if isinstance(result, dict) and result.get("success"):
            return result.get("sys_id", "")

    except Exception as lookup_error:

        print(
            "[LangGraph] WARNING: ServiceNow caller lookup failed: "
            f"{lookup_error}"
        )

    return ""


def _format_incident_status(incident: dict) -> str:
    """Turns one get_incident_status() incident dict into the kind of
    summary the caller actually asked for: state, who's on it, and
    their latest work notes / the resolution if it's closed."""

    lines = [
        f"**{incident.get('number', '')}** — {incident.get('state', '')}",
        f"*{incident.get('short_description', '')}*",
        "",
    ]

    assigned_to = incident.get("assigned_to", "")

    if assigned_to:
        lines.append(f"Assigned to **{assigned_to}**.")
    else:
        lines.append("Not yet assigned to anyone.")

    close_notes = incident.get("close_notes", "")

    if incident.get("state") in ("Resolved", "Closed") and close_notes:

        lines.append("")
        lines.append(f"**Resolution:** {close_notes}")

    else:

        work_notes = incident.get("work_notes", [])

        if work_notes:

            lines.append("")
            lines.append("Latest updates:")

            for note in work_notes[-3:]:

                author = note.get("created_by", "") or assigned_to or "Someone"
                internal_tag = " *(internal)*" if not note.get("customer_visible") else ""

                lines.append(
                    f"- **{author}**{internal_tag}: \"{note.get('value', '')}\""
                )

        else:

            lines.append("No updates have been added yet.")

    return "\n".join(lines)


# ---------------------------------------------------------
# 9c. Status check
# ---------------------------------------------------------

def handle_status_check(state: AgentState):

    caller_sys_id = _resolve_caller_sys_id(state.get("caller_username", ""))
    incident_number = _incident_number_for(state)

    result = get_incident_status(
        incident_number=incident_number,
        caller_id=caller_sys_id,
    )

    if not isinstance(result, dict) or not result.get("success"):

        message = (
            result.get("message", "I couldn't look up the incident status.")
            if isinstance(result, dict)
            else "I couldn't look up the incident status."
        )

        return {"response": message}

    incidents = result.get("incidents", [])

    if not incidents:

        return {
            "response": (
                f"I couldn't find an incident matching '{incident_number}'."
                if incident_number
                else "I don't see any open incidents for your account."
            )
        }

    if len(incidents) == 1:
        return {"response": _format_incident_status(incidents[0])}

    # -----------------------------------------------------
    # Multiple open incidents and no number was given - ask which one.
    # -----------------------------------------------------

    numbers = [inc["number"] for inc in incidents]

    choice = interrupt({
        "type": "select_incident",
        "message": (
            "You have a few open incidents - which one would you like "
            "the status of?"
        ),
        "options": numbers,
    })

    choice = str(choice).strip().upper()

    chosen = next(
        (inc for inc in incidents if inc["number"].upper() == choice),
        None,
    )

    if not chosen:

        return {
            "response": (
                f"I didn't recognize '{choice}' as one of your open "
                "incidents. Please try again with the exact number."
            )
        }

    return {"response": _format_incident_status(chosen)}


# ---------------------------------------------------------
# 9d. Close incident
# ---------------------------------------------------------

def handle_close_incident(state: AgentState):

    caller_sys_id = _resolve_caller_sys_id(state.get("caller_username", ""))
    incident_number = _incident_number_for(state)

    if not incident_number:

        lookup = get_incident_status(caller_id=caller_sys_id)

        open_incidents = (
            lookup.get("incidents", [])
            if isinstance(lookup, dict) and lookup.get("success")
            else []
        )

        if not open_incidents:

            return {
                "response": "I don't see any open incidents to close for your account."
            }

        if len(open_incidents) == 1:

            incident_number = open_incidents[0]["number"]

        else:

            numbers = [inc["number"] for inc in open_incidents]

            choice = interrupt({
                "type": "select_incident",
                "message": (
                    "Which incident would you like to close?"
                ),
                "options": numbers + ["cancel"],
            })

            choice = str(choice).strip().upper()

            if choice == "CANCEL":
                return {"response": "Okay, I won't close anything."}

            if choice not in [n.upper() for n in numbers]:

                return {
                    "response": (
                        f"I didn't recognize '{choice}' as one of your open "
                        "incidents. Please try again."
                    )
                }

            incident_number = choice

    resolution_notes = interrupt({
        "type": "resolution_notes",
        "message": (
            f"What resolved {incident_number}? I'll add this as the "
            "resolution notes before closing it."
        ),
        "options": None,
    })

    resolution_notes = str(resolution_notes).strip()

    if resolution_notes.lower() == "cancel":
        return {"response": "Okay, I won't close anything."}

    result = close_incident(
        incident_number=incident_number,
        resolution_notes=resolution_notes,
        caller_id=caller_sys_id,
    )

    if isinstance(result, dict) and result.get("success"):
        return {"response": result.get("message", f"{incident_number} has been closed.")}

    message = _format_mcp_failure(result, "I couldn't close that incident.")

    return {"response": message}


# ---------------------------------------------------------
# 9e. Reopen incident
# ---------------------------------------------------------

def handle_reopen_incident(state: AgentState):

    caller_sys_id = _resolve_caller_sys_id(state.get("caller_username", ""))
    incident_number = _incident_number_for(state)

    # Unlike close_incident's "no number given" case, this can't fall
    # back to listing the caller's incidents - get_incident_status only
    # looks at active ones, and a resolved/closed incident is exactly
    # what reopening needs to find. So it just asks directly instead.
    if not incident_number:

        answer = interrupt({
            "type": "incident_number",
            "message": (
                "Which incident would you like reopened? "
                "(e.g. INC0010023)"
            ),
            "options": None,
        })

        answer = str(answer).strip()

        if answer.lower() == "cancel":
            return {"response": "Okay, I won't reopen anything."}

        incident_number = _extract_incident_number(answer) or answer.upper()

    reason = interrupt({
        "type": "reopen_reason",
        "message": (
            f"What's still wrong with {incident_number}? I'll add this "
            "as a note before reopening it."
        ),
        "options": None,
    })

    reason = str(reason).strip()

    if reason.lower() == "cancel":
        return {"response": "Okay, I won't reopen anything."}

    result = reopen_incident(
        incident_number=incident_number,
        reason=reason,
        caller_id=caller_sys_id,
    )

    if isinstance(result, dict) and result.get("success"):
        return {"response": result.get("message", f"{incident_number} has been reopened.")}

    message = _format_mcp_failure(result, "I couldn't reopen that incident.")

    return {"response": message}


# ---------------------------------------------------------
# 10. Routing after classification
# ---------------------------------------------------------

def route_request(state: AgentState):

    intent = state["intent"]

    if intent in ["incident", "problem_report"]:
        return "incident"

    if intent == "greeting":
        return "greeting"

    if intent == "status_check":
        return "status_check"

    if intent == "close_incident":
        return "close_incident"

    if intent == "reopen_incident":
        return "reopen_incident"

    return "documentation"


# ---------------------------------------------------------
# 11. Routing after troubleshooting
# ---------------------------------------------------------

def route_after_troubleshooting(state: AgentState):

    # User is satisfied → END
    if state.get("user_satisfied") is True:
        return "end"

    # User still needs help → ask about incident
    return "ask_incident"


# ---------------------------------------------------------
# 12. Routing after incident confirmation
# ---------------------------------------------------------

def route_after_incident_confirmation(state: AgentState):

    if state.get("create_incident_requested") is True:
        return "priority"

    return "end"


# ---------------------------------------------------------
# 13. Routing after priority
# ---------------------------------------------------------

def route_after_priority(state: AgentState):

    priority = state.get("priority", "").upper()

    if priority in ["P3", "P4"]:
        return "create_incident"

    return "blocked"


# ---------------------------------------------------------
# 14. Block incident
# ---------------------------------------------------------

def block_incident(state: AgentState):

    priority = state.get("priority", "")

    # -------------------------------------------------------------
    # Instead of ending the whole conversation here, interrupt and
    # give the user a chance to correct their answer. The graph's
    # checkpointer already keeps everything gathered so far (the
    # question, image analysis, draft incident description) attached
    # to this thread_id, so nothing is lost by looping back.
    # -------------------------------------------------------------

    new_priority = interrupt({
        "type": "priority",
        "message": (
            f"{priority} incidents can't be created through this "
            "assistant - only P3 and P4 can. P1/P2 issues must go "
            "through the standard ServiceNow process.\n\n"
            "Reply with P3 or P4 to continue, or 'cancel' to stop here."
        ),
        "options": ["P3", "P4", "cancel"],
    })

    new_priority = str(new_priority).strip().upper()

    if new_priority == "CANCEL":
        return {
            "response": (
                "No incident was created. Let me know if you'd like to "
                "try again."
            ),
            "priority": new_priority,
        }

    return {
        "priority": new_priority
    }


def route_after_block(state: AgentState):

    if state.get("priority", "").upper() == "CANCEL":
        return "end"

    return "validate_priority"


# ---------------------------------------------------------
# 15. Build LangGraph
# ---------------------------------------------------------

graph_builder = StateGraph(AgentState)


# ---------------------------------------------------------
# Nodes
# ---------------------------------------------------------

graph_builder.add_node(
    "classify",
    classify_request
)

graph_builder.add_node(
    "documentation",
    handle_documentation
)

graph_builder.add_node(
    "greeting",
    handle_greeting
)

graph_builder.add_node(
    "status_check",
    handle_status_check
)

graph_builder.add_node(
    "close_incident",
    handle_close_incident
)

graph_builder.add_node(
    "reopen_incident",
    handle_reopen_incident
)

graph_builder.add_node(
    "incident",
    handle_incident
)

graph_builder.add_node(
    "satisfaction",
    ask_user_satisfaction
)

graph_builder.add_node(
    "ask_incident",
    ask_create_incident
)

graph_builder.add_node(
    "priority",
    ask_priority
)

graph_builder.add_node(
    "validate_priority",
    validate_priority
)

graph_builder.add_node(
    "create_incident",
    create_incident_node
)

graph_builder.add_node(
    "blocked",
    block_incident
)


# ---------------------------------------------------------
# START → classify
# ---------------------------------------------------------

graph_builder.add_edge(
    START,
    "classify"
)


# ---------------------------------------------------------
# classify → documentation / incident
# ---------------------------------------------------------

graph_builder.add_conditional_edges(
    "classify",
    route_request,
    {
        "documentation": "documentation",
        "incident": "incident",
        "greeting": "greeting",
        "status_check": "status_check",
        "close_incident": "close_incident",
        "reopen_incident": "reopen_incident",
    }
)

graph_builder.add_edge(
    "greeting",
    END
)

graph_builder.add_edge(
    "status_check",
    END
)

graph_builder.add_edge(
    "close_incident",
    END
)

graph_builder.add_edge(
    "reopen_incident",
    END
)


# ---------------------------------------------------------
# Incident → satisfaction
# ---------------------------------------------------------

graph_builder.add_edge(
    "incident",
    "satisfaction"
)


# ---------------------------------------------------------
# Satisfaction → END / incident confirmation
# ---------------------------------------------------------

graph_builder.add_conditional_edges(
    "satisfaction",
    route_after_troubleshooting,
    {
        "end": END,
        "ask_incident": "ask_incident",
    }
)


# ---------------------------------------------------------
# Incident confirmation → END / priority
# ---------------------------------------------------------

graph_builder.add_conditional_edges(
    "ask_incident",
    route_after_incident_confirmation,
    {
        "end": END,
        "priority": "priority",
    }
)


# ---------------------------------------------------------
# Priority → validation
# ---------------------------------------------------------

graph_builder.add_edge(
    "priority",
    "validate_priority"
)


# ---------------------------------------------------------
# Validation → create / blocked
# ---------------------------------------------------------

graph_builder.add_conditional_edges(
    "validate_priority",
    route_after_priority,
    {
        "create_incident": "create_incident",
        "blocked": "blocked",
    }
)


# ---------------------------------------------------------
# Documentation → END
# ---------------------------------------------------------

graph_builder.add_edge(
    "documentation",
    END
)


# ---------------------------------------------------------
# Create incident → END
# ---------------------------------------------------------

graph_builder.add_edge(
    "create_incident",
    END
)


# ---------------------------------------------------------
# Blocked → re-validate the corrected priority, or END on cancel
# ---------------------------------------------------------

graph_builder.add_conditional_edges(
    "blocked",
    route_after_block,
    {
        "end": END,
        "validate_priority": "validate_priority",
    }
)


# ---------------------------------------------------------
# Compile
# ---------------------------------------------------------
#
# A checkpointer is required so that interrupt()/Command(resume=...)
# can work across separate calls (e.g. separate HTTP requests from
# the frontend). MongoDBSaver persists that state in the same
# MongoDB instance used for user accounts (different collections -
# "checkpoints" / "checkpoint_writes" by default, no collision with
# "users"), so an in-progress incident conversation survives a
# backend restart/redeploy and works correctly even if you run more
# than one backend instance behind a load balancer. This replaces
# the in-memory MemorySaver used during local development, which
# loses all state on every restart and doesn't share state across
# instances.
# ---------------------------------------------------------

_CHECKPOINT_MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
_CHECKPOINT_MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "itom_assistant")

_checkpoint_client = MongoClient(_CHECKPOINT_MONGODB_URI)

graph = graph_builder.compile(
    checkpointer=MongoDBSaver(
        _checkpoint_client,
        db_name=_CHECKPOINT_MONGODB_DB_NAME,
    )
)