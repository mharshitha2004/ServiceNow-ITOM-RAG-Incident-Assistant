import mimetypes
import os
import re
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

from rag import answer_question

# ---------------------------------------------------------
# Make the LangGraph agent importable.
#
# agent/ is not a Python package (no __init__.py) - graph.py is
# written to be imported the way agent/test_graph.py does it, by
# running with agent/ itself on sys.path. We do the same thing
# here instead of touching graph.py's own import style.
# ---------------------------------------------------------

AGENT_DIR = Path(__file__).resolve().parent / "agent"

if str(AGENT_DIR) not in sys.path:
    sys.path.append(str(AGENT_DIR))

from graph import graph, analyze_image_evidence  # noqa: E402  (must come after the sys.path patch above)
from langgraph.types import Command  # noqa: E402
from mcp_client import lookup_servicenow_user  # noqa: E402

from auth import (  # noqa: E402
    COOKIE_MAX_AGE_SECONDS,
    COOKIE_NAME,
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    authenticate_user,
    clear_avatar,
    create_session_token,
    create_user,
    decode_session_token,
    get_current_user,
    get_user_by_id,
    public_user,
    set_avatar,
    update_email,
    update_name,
    update_password,
    update_servicenow_username,
)
from conversations import (  # noqa: E402
    append_messages,
    clear_pending,
    create_conversation,
    delete_conversation,
    find_by_pending_thread,
    get_owned,
    list_summaries,
    make_message,
    serialize_detail,
    set_pending,
)
from db import delete_image, load_image, save_image  # noqa: E402

app = FastAPI(title="ServiceNow ITOM Assistant API")

# FRONTEND_ORIGINS is a comma-separated list, e.g.
# "https://your-app.vercel.app,https://staging.your-app.vercel.app"
# Falls back to local dev origins when unset.
_default_origins = "http://localhost:3000,http://127.0.0.1:3000"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", _default_origins).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QuestionRequest(BaseModel):
    question: str
    # Only used when the person is logged in: continue this saved
    # conversation instead of starting a new one.
    conversation_id: Optional[str] = None


class IncidentReplyRequest(BaseModel):
    thread_id: str
    answer: str


class IncidentTurnResponse(BaseModel):
    thread_id: str
    done: bool
    message: str
    awaiting: Optional[str] = None
    options: Optional[List[str]] = None
    # The saved conversation this turn belongs to.
    conversation_id: Optional[str] = None


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    servicenow_username: str = Field(min_length=1)
    name: str = Field(min_length=1)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    servicenow_username: str
    name: str
    has_avatar: bool


class UpdateProfileRequest(BaseModel):
    # All optional: send only the field(s) you want to change.
    email: Optional[EmailStr] = None
    servicenow_username: Optional[str] = Field(default=None, min_length=1)
    name: Optional[str] = Field(default=None, min_length=1)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class ConversationSummary(BaseModel):
    id: str
    kind: str
    title: str
    updated_at: str


class StoredMessage(BaseModel):
    id: str
    role: str
    content: object
    image_id: Optional[str] = None
    awaiting: Optional[str] = None
    options: Optional[List[str]] = None
    created_at: str


class PendingTurn(BaseModel):
    thread_id: str
    awaiting: Optional[str] = None
    options: Optional[List[str]] = None


class ConversationDetail(BaseModel):
    id: str
    kind: str
    title: str
    messages: List[StoredMessage]
    pending: Optional[PendingTurn] = None


# ---------------------------------------------------------
# Optional login
#
# The documentation assistant is usable without an account, so its
# endpoints can't use get_current_user (which raises 401). This
# returns the logged-in user if there is one, else None - a
# logged-out visitor just doesn't get their chats saved.
# ---------------------------------------------------------


def get_optional_user(request: Request) -> Optional[dict]:
    token = request.cookies.get(COOKIE_NAME)

    if not token:
        return None

    user_id = decode_session_token(token)

    if not user_id:
        return None

    return get_user_by_id(user_id)


@app.get("/")
def home():
    return {"message": "ServiceNow ITOM Assistant API is running"}


# ---------------------------------------------------------
# Health check
#
# Deliberately touches nothing (no MongoDB, Pinecone, Gemini or
# ServiceNow) so it answers instantly. Used by Render's health check
# (render.yaml healthCheckPath), by a keep-alive pinger (so the free
# instance doesn't go to sleep), and by the frontend to tell whether the
# server is awake yet.
# ---------------------------------------------------------


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------
# Image uploads (documentation + incident)
# ---------------------------------------------------------
#
# Only these formats are accepted (they're what the frontend's file
# picker offers). Notably SVG is refused: images are served back from
# this API's origin, and an SVG can carry scripts.
# ---------------------------------------------------------

MAX_IMAGE_BYTES = 10 * 1024 * 1024

ALLOWED_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _read_image_upload(image: UploadFile) -> tuple[bytes, str]:
    """Validate an uploaded image and return (bytes, content_type)."""

    content_type = (image.content_type or "").lower()

    if not content_type:
        guessed, _ = mimetypes.guess_type(image.filename or "")
        content_type = guessed or ""

    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PNG, JPEG, WebP or GIF images can be attached.",
        )

    data = image.file.read(MAX_IMAGE_BYTES + 1)

    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="That image is too large (10 MB maximum).",
        )

    return data, content_type


# ---------------------------------------------------------
# Incident attachments (images, .txt log files, .zip archives)
# ---------------------------------------------------------
#
# The incident flow accepts a broader set of files than the plain
# documentation image upload above: a screenshot (handled exactly the
# same way as ALLOWED_IMAGE_TYPES/_read_image_upload), a .txt log file
# (read and analyzed by Gemini as text), or a .zip archive (not
# analyzed - no text to extract - just attached to the incident as-is
# for a human to open). Kept separate from the image-only helper
# above, which /ask/multimodal still uses unchanged.
# ---------------------------------------------------------

MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024  # logs/archives can run larger than a screenshot

ALLOWED_TEXT_TYPES = {
    "text/plain": ".txt",
}

ALLOWED_ARCHIVE_TYPES = {
    "application/zip": ".zip",
    "application/x-zip-compressed": ".zip",  # common from Windows-originated uploads
}


def _read_incident_attachment(file: UploadFile) -> tuple[bytes, str, str]:
    """Validate an incident attachment (image, .txt, or .zip) and
    return (bytes, extension, kind), where kind is
    "image" | "text" | "archive"."""

    content_type = (file.content_type or "").lower()
    filename = (file.filename or "").lower()

    if not content_type or content_type == "application/octet-stream":
        guessed, _ = mimetypes.guess_type(file.filename or "")
        content_type = guessed or content_type

    if content_type in ALLOWED_IMAGE_TYPES:
        kind = "image"
        extension = ALLOWED_IMAGE_TYPES[content_type]
        max_bytes = MAX_IMAGE_BYTES

    elif content_type in ALLOWED_TEXT_TYPES or filename.endswith(".txt"):
        kind = "text"
        extension = ".txt"
        max_bytes = MAX_ATTACHMENT_BYTES

    elif content_type in ALLOWED_ARCHIVE_TYPES or filename.endswith(".zip"):
        kind = "archive"
        extension = ".zip"
        max_bytes = MAX_ATTACHMENT_BYTES

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Only PNG, JPEG, WebP, GIF images, .txt log files, "
                "or .zip archives can be attached."
            ),
        )

    data = file.file.read(max_bytes + 1)

    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"That file is too large ({max_bytes // (1024 * 1024)} MB maximum).",
        )

    return data, extension, kind


# ---------------------------------------------------------
# Documentation assistant
# ---------------------------------------------------------
#
# If the person is logged in, each question + answer is saved to a
# conversation they can reopen later from the history sidebar. Pass
# conversation_id to keep adding to an existing conversation; leave
# it out to start a new one. The response always includes the
# conversation_id that was used (or null when nothing was saved).
# ---------------------------------------------------------


def _existing_conversation(
    user: Optional[dict],
    kind: str,
    conversation_id: Optional[str],
) -> Optional[dict]:
    if not user or not conversation_id:
        return None

    return get_owned(conversation_id, user["_id"], kind)


def _save_documentation_turn(
    user: dict,
    existing: Optional[dict],
    question: str,
    answer,
    image: Optional[tuple[bytes, str]] = None,
) -> str:
    conversation = existing or create_conversation(
        user["_id"], "documentation", question
    )

    image_id = None

    if image is not None:
        data, content_type = image
        image_id = save_image(
            data,
            filename="attachment",
            content_type=content_type,
            user_id=user["_id"],
        )

    append_messages(
        conversation["_id"],
        [
            make_message("user", question, image_id=image_id),
            make_message("assistant", answer),
        ],
    )

    return conversation["_id"]


@app.post("/ask")
def ask_question(
    request: QuestionRequest,
    current_user: Optional[dict] = Depends(get_optional_user),
):
    existing = _existing_conversation(
        current_user, "documentation", request.conversation_id
    )

    answer = answer_question(request.question)

    conversation_id = None

    if current_user:
        conversation_id = _save_documentation_turn(
            current_user, existing, request.question, answer
        )

    return {
        "answer": answer,
        "conversation_id": conversation_id,
    }


# ---------------------------------------------------------
# Auth (register / login / logout / me)
# ---------------------------------------------------------
#
# Sessions are a JWT stored in an httpOnly cookie - the browser sends
# it automatically on every request (as long as the frontend fetches
# with credentials: 'include'), and it can't be read from JS, which
# is more resistant to XSS than storing the token in localStorage.
#
# Registration doubles as account linking: the ServiceNow username
# the person gives us is validated against the PDI right away (via
# the same lookup_servicenow_user MCP tool the incident flow uses
# later to resolve the caller), so a typo'd or nonexistent ServiceNow
# account is rejected up front instead of silently failing when an
# incident finally gets created.
# ---------------------------------------------------------


def _set_session_cookie(response: Response, user_id: str) -> None:
    token = create_session_token(user_id)

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
        max_age=COOKIE_MAX_AGE_SECONDS,
        path="/",
    )


@app.post("/auth/register", response_model=UserResponse)
def register(request: RegisterRequest, response: Response):
    lookup_result = lookup_servicenow_user(request.servicenow_username)

    if not isinstance(lookup_result, dict) or not lookup_result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                lookup_result.get("message")
                if isinstance(lookup_result, dict)
                else "Could not verify that ServiceNow username."
            ),
        )

    user_doc = create_user(
        email=request.email,
        password=request.password,
        servicenow_username=request.servicenow_username,
        # User-entered, not the ServiceNow lookup's name - more reliable
        # (the lookup can return an empty/unexpected name depending on
        # how the instance's sys_user record is filled in) and gives
        # people control over how they're displayed.
        name=request.name,
    )

    _set_session_cookie(response, user_doc["_id"])

    return public_user(user_doc)


@app.post("/auth/login", response_model=UserResponse)
def login(request: LoginRequest, response: Response):
    user_doc = authenticate_user(request.email, request.password)

    _set_session_cookie(response, user_doc["_id"])

    return public_user(user_doc)


@app.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
    )

    return {"message": "Logged out."}


@app.get("/auth/me", response_model=UserResponse)
def me(current_user: dict = Depends(get_current_user)):
    return public_user(current_user)


# ---------------------------------------------------------
# Profile: email / ServiceNow username / password / avatar
# ---------------------------------------------------------
#
# Changing the ServiceNow username re-runs the same lookup_servicenow_user
# validation used at registration, so it can't be pointed at a username
# that doesn't exist on the instance - and the resolved display name is
# refreshed at the same time, since it drives the avatar's initials.
# ---------------------------------------------------------


@app.patch("/auth/profile", response_model=UserResponse)
def update_profile(
    request: UpdateProfileRequest,
    current_user: dict = Depends(get_current_user),
):
    user_doc = current_user

    if request.email is not None:
        user_doc = update_email(current_user["_id"], request.email)

    if request.servicenow_username is not None:

        lookup_result = lookup_servicenow_user(request.servicenow_username)

        if not isinstance(lookup_result, dict) or not lookup_result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    lookup_result.get("message")
                    if isinstance(lookup_result, dict)
                    else "Could not verify that ServiceNow username."
                ),
            )

        # Only verifies the username is real; no longer overwrites the
        # account's display name - that's user-owned now (see `name`
        # below), not silently re-derived from ServiceNow on every
        # username change.
        user_doc = update_servicenow_username(
            current_user["_id"],
            request.servicenow_username,
        )

    if request.name is not None:
        user_doc = update_name(current_user["_id"], request.name)

    return public_user(user_doc)


@app.post("/auth/password")
def change_password(
    request: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    update_password(
        current_user["_id"],
        request.current_password,
        request.new_password,
    )

    return {"message": "Password updated."}


@app.post("/auth/avatar", response_model=UserResponse)
def upload_avatar(
    image: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    data, content_type = _read_image_upload(image)

    old_user_doc = get_user_by_id(current_user["_id"])
    old_avatar_id = (old_user_doc or {}).get("avatar_image_id")

    image_id = save_image(
        data,
        filename="avatar",
        content_type=content_type,
        user_id=current_user["_id"],
    )

    user_doc = set_avatar(current_user["_id"], image_id)

    # Best-effort cleanup of the previous photo - not worth failing the
    # request over if this doesn't succeed.
    if old_avatar_id:
        try:
            delete_image(old_avatar_id)
        except Exception:
            pass

    return public_user(user_doc)


@app.delete("/auth/avatar", response_model=UserResponse)
def remove_avatar(current_user: dict = Depends(get_current_user)):
    old_user_doc = get_user_by_id(current_user["_id"])
    old_avatar_id = (old_user_doc or {}).get("avatar_image_id")

    user_doc = clear_avatar(current_user["_id"])

    if old_avatar_id:
        try:
            delete_image(old_avatar_id)
        except Exception:
            pass

    return public_user(user_doc)


@app.get("/auth/avatar")
def get_avatar(current_user: dict = Depends(get_current_user)):
    user_doc = get_user_by_id(current_user["_id"])
    avatar_id = (user_doc or {}).get("avatar_image_id")

    if not avatar_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No avatar set.",
        )

    stored = load_image(avatar_id)

    if not stored:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No avatar set.",
        )

    return Response(
        content=stored["data"],
        media_type=stored["content_type"],
        headers={
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ---------------------------------------------------------
# Incident assistant (LangGraph + MCP), exposed over HTTP
# ---------------------------------------------------------
#
# The graph is stateful and turn-based: a call can come back either
# finished ("done": true, "message" is the final answer) or paused
# on a question ("done": false, "awaiting" says what kind of answer
# is expected, "options" gives suggested replies). The frontend
# calls /incident/start once per new conversation, then /incident/reply
# for every follow-up, always passing back the same thread_id.
#
# Both endpoints require a logged-in session: they need to know who's
# creating the incident so it lands in ServiceNow with the right
# caller, and creating incidents shouldn't be anonymous.
#
# Every turn is also saved to the person's conversation history. The
# saved conversation remembers which LangGraph thread (if any) is
# currently waiting for an answer, so /incident/reply can find the
# right conversation from thread_id alone - and refuses thread ids
# that belong to someone else.
# ---------------------------------------------------------

UPLOAD_DIR = Path(tempfile.gettempdir()) / "itom_assistant_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------
# Documentation assistant with image support
# ---------------------------------------------------------
#
# Same behavior as /ask, plus an optional screenshot / pasted image.
# The image goes through the same Gemini analysis the incident flow
# uses, and what it extracts is added to the question before the
# documentation search runs. Like /ask, this does not require login.
# The temporary file used for analysis is deleted right away; for
# logged-in users the image is also saved (GridFS) so it shows up in
# their history.
# ---------------------------------------------------------


@app.post("/ask/multimodal")
def ask_question_multimodal(
    question: str = Form(...),
    image: Optional[UploadFile] = File(None),
    conversation_id: Optional[str] = Form(None),
    current_user: Optional[dict] = Depends(get_optional_user),
):
    existing = _existing_conversation(
        current_user, "documentation", conversation_id
    )

    rag_question = question
    image_upload: Optional[tuple[bytes, str]] = None

    if image is not None:
        image_upload = _read_image_upload(image)
        image_bytes, image_type = image_upload

        saved_path = UPLOAD_DIR / f"{uuid.uuid4()}{ALLOWED_IMAGE_TYPES[image_type]}"
        saved_path.write_bytes(image_bytes)

        try:
            image_analysis = analyze_image_evidence(str(saved_path))
        finally:
            saved_path.unlink(missing_ok=True)

        rag_question = f"""
User question:

{question}

Additional technical information extracted from the
user-provided image:

{image_analysis}

Use both the user's question and the image-derived information
when searching the ServiceNow documentation.
"""

    answer = answer_question(rag_question)

    saved_conversation_id = None

    if current_user:
        saved_conversation_id = _save_documentation_turn(
            current_user, existing, question, answer, image_upload
        )

    return {
        "answer": answer,
        "conversation_id": saved_conversation_id,
    }


def _shape_turn(
    thread_id: str,
    result: dict,
    conversation_id: Optional[str] = None,
) -> IncidentTurnResponse:

    interrupts = result.get("__interrupt__")

    if interrupts:
        payload = interrupts[0].value or {}

        return IncidentTurnResponse(
            thread_id=thread_id,
            done=False,
            message=payload.get("message", ""),
            awaiting=payload.get("type"),
            options=payload.get("options"),
            conversation_id=conversation_id,
        )

    return IncidentTurnResponse(
        thread_id=thread_id,
        done=True,
        message=result.get("response", ""),
        conversation_id=conversation_id,
    )


def _pending_of(turn: IncidentTurnResponse) -> Optional[dict]:
    """What to remember on the conversation: the thread that is waiting
    for an answer, or None once the incident flow has finished."""

    if turn.done:
        return None

    return {
        "thread_id": turn.thread_id,
        "awaiting": turn.awaiting,
        "options": turn.options,
    }


# A thread whose last run died partway through a step (server restart,
# memory-limit kill, an exception in a node) has no question waiting to
# be answered - asking the person for P3/P4 again would be misleading,
# because the priority they already picked is saved on the thread and
# would be used anyway. Instead it's offered as a single "Retry", which
# resumes the step that was interrupted. Safe to repeat: the incident
# step is idempotent (see correlation_id in mcp_server/server.py).
RETRY_PENDING_TYPE = "retry"
RETRY_OPTION = "Retry"


def _retry_pending(thread_id: str) -> dict:
    return {
        "thread_id": thread_id,
        "awaiting": RETRY_PENDING_TYPE,
        "options": [RETRY_OPTION],
    }


def _has_live_interrupt(snapshot) -> bool:
    """True when the thread is paused on an interrupt() (i.e. really
    waiting for the person's answer)."""

    if getattr(snapshot, "interrupts", None):
        return True

    return any(
        getattr(task, "interrupts", None)
        for task in (getattr(snapshot, "tasks", None) or ())
    )


_INCIDENT_NUMBER_IN_TEXT = re.compile(r"\bINC\d{4,}\b", re.IGNORECASE)


def _last_incident_number(conversation: Optional[dict]) -> str:
    """Most recent incident number that appeared in this saved conversation
    (e.g. "Incident Number: INC0010027" from the creation message). Lets a
    follow-up like "who is the assignee?" refer to it without retyping."""

    if not conversation:
        return ""

    for message in reversed(conversation.get("messages", [])):
        found = _INCIDENT_NUMBER_IN_TEXT.findall(str(message.get("content", "")))
        if found:
            return found[-1].upper()

    return ""


def _assistant_message(turn: IncidentTurnResponse) -> dict:
    return make_message(
        "assistant",
        turn.message,
        awaiting=turn.awaiting,
        options=turn.options,
    )


@app.post("/incident/start", response_model=IncidentTurnResponse)
def incident_start(
    question: str = Form(...),
    image: Optional[UploadFile] = File(None),
    conversation_id: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
):
    # Fail early (404) if they asked to continue a conversation that
    # isn't theirs / doesn't exist, before running the graph.
    existing = _existing_conversation(current_user, "incident", conversation_id)

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    graph_input = {
        "question": question,
        # Threaded through to create_incident_node, which resolves it
        # to a ServiceNow sys_id (via lookup_servicenow_user) only if
        # and when an incident actually gets created.
        "caller_username": current_user["servicenow_username"],
        "last_incident_number": _last_incident_number(existing),
    }

    image_upload: Optional[tuple[bytes, str]] = None

    if image is not None:

        data, extension, kind = _read_incident_attachment(image)
        saved_path = UPLOAD_DIR / f"{thread_id}{extension}"
        saved_path.write_bytes(data)

        if kind == "image":
            # Unchanged behavior - image_upload is what gets saved to
            # chat history below (as a viewable thumbnail).
            content_type = next(
                ct for ct, ext in ALLOWED_IMAGE_TYPES.items() if ext == extension
            )
            image_upload = (data, content_type)
            graph_input["image_path"] = str(saved_path)

        else:
            # .txt / .zip - analyzed (text) or just attached (archive)
            # by the graph, not shown as a chat thumbnail.
            graph_input["attachment_path"] = str(saved_path)
            graph_input["attachment_kind"] = kind
            graph_input["attachment_filename"] = image.filename or f"attachment{extension}"

    try:
        result = graph.invoke(graph_input, config=config)
    except Exception:
        # Nothing was saved to this conversation's "pending" for this
        # attempt yet (that only happens below, once graph.invoke
        # succeeds) - so there's no stale state to clear here, unlike
        # /incident/reply. Still worth a clean error instead of an
        # unhandled 500, so the frontend can show something sensible
        # and reset its own thread state rather than getting stuck.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Something went wrong starting this incident report. "
                "Please try again."
            ),
        )

    turn = _shape_turn(thread_id, result)

    # ---- save to history ----

    conversation = existing or create_conversation(
        current_user["_id"], "incident", question
    )

    image_id = None

    if image_upload is not None:
        data, content_type = image_upload
        image_id = save_image(
            data,
            filename="attachment",
            content_type=content_type,
            user_id=current_user["_id"],
        )

    append_messages(
        conversation["_id"],
        [
            make_message("user", question, image_id=image_id),
            _assistant_message(turn),
        ],
        pending=_pending_of(turn),
    )

    turn.conversation_id = conversation["_id"]

    return turn


@app.post("/incident/reply", response_model=IncidentTurnResponse)
def incident_reply(
    request: IncidentReplyRequest,
    current_user: dict = Depends(get_current_user),
):
    # The thread must be one of this person's own, and still waiting
    # for an answer. Anything else is a 404 - including someone else's
    # thread id, and threads that were lost when the server restarted.
    conversation = find_by_pending_thread(request.thread_id, current_user["_id"])

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "That incident conversation is no longer active. "
                "Please start a new one."
            ),
        )

    config = {"configurable": {"thread_id": request.thread_id}}

    # caller_username was already set on this thread's state back at
    # /incident/start and survives across turns via the checkpointer -
    # no need to pass it again here.
    try:
        result = graph.invoke(Command(resume=request.answer), config=config)
    except Exception as error:
        print(f"[incident/reply] graph failed for thread {request.thread_id}: {error!r}")

        # The graph crashed partway through this turn (e.g. mid
        # incident-creation). Its checkpoint is now stuck past the
        # last interrupt() it actually completed, with no live
        # interrupt() left to receive a future reply. Asking for P3/P4
        # again here would be a trap: the priority already picked is
        # locked into the thread, so a different answer would be
        # ignored (that's how a P4 once got created after someone
        # answered P3). So the thread is kept, but only as a "Retry" -
        # which re-runs the step that failed. That's safe because
        # incident creation is idempotent per thread (correlation_id):
        # if ServiceNow already saved the incident, the retry returns it.
        try:
            snapshot = graph.get_state(config)

            if snapshot.next and not _has_live_interrupt(snapshot):
                set_pending(conversation["_id"], _retry_pending(request.thread_id))
            elif not snapshot.next:
                clear_pending(conversation["_id"])
        except Exception:
            clear_pending(conversation["_id"])

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Something went wrong continuing this incident. "
                "Use Retry to try that step again - it won't create "
                "a duplicate incident."
            ),
        )

    turn = _shape_turn(request.thread_id, result, conversation["_id"])

    append_messages(
        conversation["_id"],
        [
            make_message("user", request.answer),
            _assistant_message(turn),
        ],
        pending=_pending_of(turn),
    )

    return turn


# ---------------------------------------------------------
# Conversation history
# ---------------------------------------------------------
#
# Powers the history sidebar. All of these require login and only
# ever touch the logged-in person's own conversations.
# ---------------------------------------------------------


@app.get("/conversations", response_model=List[ConversationSummary])
def list_conversations(
    kind: Literal["documentation", "incident"] = Query(...),
    current_user: dict = Depends(get_current_user),
):
    return list_summaries(current_user["_id"], kind)


@app.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
):
    doc = get_owned(conversation_id, current_user["_id"])

    pending = doc.get("pending")

    if pending and doc["kind"] == "incident":
        # An incident thread can only be resumed if the graph still
        # remembers it. Its state lives in memory, so it's gone after a
        # server restart - in that case the conversation is still
        # readable, just no longer waiting on an answer.
        snapshot = graph.get_state(
            {"configurable": {"thread_id": pending["thread_id"]}}
        )

        if not snapshot.next:
            clear_pending(conversation_id)
            pending = None

        elif (
            not _has_live_interrupt(snapshot)
            and pending.get("awaiting") != RETRY_PENDING_TYPE
        ):
            # The server died mid-step (e.g. while creating the incident),
            # so the saved "waiting for P3/P4" is stale. Offer Retry instead.
            pending = _retry_pending(pending["thread_id"])
            set_pending(conversation_id, pending)

    return serialize_detail(doc, pending)


@app.delete("/conversations/{conversation_id}")
def remove_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
):
    delete_conversation(conversation_id, current_user["_id"])

    return {"message": "Conversation deleted."}


@app.get("/images/{image_id}")
def get_image(
    image_id: str,
    current_user: dict = Depends(get_current_user),
):
    stored = load_image(image_id)

    # Same 404 whether the image doesn't exist or belongs to someone else.
    if not stored or stored["user_id"] != current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found.",
        )

    return Response(
        content=stored["data"],
        media_type=stored["content_type"],
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )