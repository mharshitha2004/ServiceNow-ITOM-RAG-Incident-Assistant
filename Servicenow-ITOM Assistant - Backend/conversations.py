"""
Saved chat history for the documentation and incident assistants.

A conversation document looks like:

    {
      "_id": "<uuid>",
      "user_id": "<owner's user _id>",
      "kind": "documentation" | "incident",
      "title": "first question, shortened",
      "messages": [
        {
          "id": "<uuid>",
          "role": "user" | "assistant",
          "content": "...",
          "image_id": "<GridFS id>",        # optional, user screenshots
          "awaiting": "priority",           # optional, incident questions
          "options": ["P3", "P4"],          # optional, incident questions
          "created_at": <datetime>
        }
      ],
      # Incident only: the LangGraph thread that is currently paused
      # waiting for the person's answer, or None when nothing is waiting.
      "pending": {"thread_id": "...", "awaiting": "...", "options": [...]},
      "created_at": <datetime>,
      "updated_at": <datetime>
    }

Every read and write here is scoped by user_id, so one person can never
see or modify another person's conversations - a conversation that
belongs to someone else is indistinguishable from one that doesn't exist.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import HTTPException, status

from db import conversations_collection, delete_image

TITLE_MAX_CHARS = 60
LIST_LIMIT = 100

# Lets append_messages() tell "leave pending alone" apart from
# "set pending to None".
_UNSET: Any = object()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    # PyMongo hands datetimes back naive (but in UTC). Mark them as UTC so
    # browsers don't misread them as local time.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _title_from(text: str) -> str:
    cleaned = " ".join(text.split())

    if not cleaned:
        return "New conversation"

    if len(cleaned) <= TITLE_MAX_CHARS:
        return cleaned

    return cleaned[: TITLE_MAX_CHARS - 1].rstrip() + "…"


# ---------------------------------------------------------
# Building / saving
# ---------------------------------------------------------


def make_message(
    role: str,
    content: Any,
    *,
    image_id: Optional[str] = None,
    awaiting: Optional[str] = None,
    options: Optional[List[str]] = None,
) -> dict:
    message: dict = {
        "id": str(uuid.uuid4()),
        "role": role,
        "content": content,
        "created_at": _now(),
    }

    if image_id:
        message["image_id"] = image_id
    if awaiting:
        message["awaiting"] = awaiting
    if options:
        message["options"] = options

    return message


def create_conversation(user_id: str, kind: str, first_text: str) -> dict:
    now = _now()

    doc = {
        "_id": str(uuid.uuid4()),
        "user_id": user_id,
        "kind": kind,
        "title": _title_from(first_text),
        "messages": [],
        "pending": None,
        "created_at": now,
        "updated_at": now,
    }

    conversations_collection.insert_one(doc)

    return doc


def append_messages(
    conversation_id: str,
    messages: List[dict],
    *,
    pending: Any = _UNSET,
) -> None:
    """Callers must already have verified ownership (get_owned)."""

    update: dict = {
        "$push": {"messages": {"$each": messages}},
        "$set": {"updated_at": _now()},
    }

    if pending is not _UNSET:
        update["$set"]["pending"] = pending

    conversations_collection.update_one({"_id": conversation_id}, update)


def clear_pending(conversation_id: str) -> None:
    conversations_collection.update_one(
        {"_id": conversation_id},
        {"$set": {"pending": None}},
    )


def set_pending(conversation_id: str, pending: Optional[dict]) -> None:
    conversations_collection.update_one(
        {"_id": conversation_id},
        {"$set": {"pending": pending}},
    )


# ---------------------------------------------------------
# Reading
# ---------------------------------------------------------


def get_owned(
    conversation_id: str,
    user_id: str,
    kind: Optional[str] = None,
) -> dict:
    query: dict = {"_id": conversation_id, "user_id": user_id}

    if kind:
        query["kind"] = kind

    doc = conversations_collection.find_one(query)

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    return doc


def find_by_pending_thread(thread_id: str, user_id: str) -> Optional[dict]:
    return conversations_collection.find_one(
        {
            "user_id": user_id,
            "kind": "incident",
            "pending.thread_id": thread_id,
        }
    )


def list_summaries(user_id: str, kind: str) -> List[dict]:
    cursor = (
        conversations_collection.find(
            {"user_id": user_id, "kind": kind},
            {"title": 1, "kind": 1, "updated_at": 1},
        )
        .sort("updated_at", -1)
        .limit(LIST_LIMIT)
    )

    return [serialize_summary(doc) for doc in cursor]


def delete_conversation(conversation_id: str, user_id: str) -> None:
    doc = get_owned(conversation_id, user_id)

    for message in doc.get("messages", []):
        image_id = message.get("image_id")
        if image_id:
            delete_image(image_id)

    conversations_collection.delete_one({"_id": conversation_id})


# ---------------------------------------------------------
# Serialization (Mongo document -> JSON-safe dict)
# ---------------------------------------------------------


def serialize_summary(doc: dict) -> dict:
    return {
        "id": doc["_id"],
        "kind": doc["kind"],
        "title": doc["title"],
        "updated_at": _iso(doc["updated_at"]),
    }


def serialize_message(message: dict) -> dict:
    return {
        "id": message["id"],
        "role": message["role"],
        "content": message["content"],
        "image_id": message.get("image_id"),
        "awaiting": message.get("awaiting"),
        "options": message.get("options"),
        "created_at": _iso(message["created_at"]),
    }


def serialize_detail(doc: dict, pending: Optional[dict]) -> dict:
    return {
        "id": doc["_id"],
        "kind": doc["kind"],
        "title": doc["title"],
        "messages": [serialize_message(m) for m in doc.get("messages", [])],
        "pending": pending,
    }