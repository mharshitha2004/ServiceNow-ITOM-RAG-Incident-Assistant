import os
import uuid
from typing import Optional

import gridfs
from pymongo import MongoClient
from pymongo.collection import Collection

# ---------------------------------------------------------
# MongoDB configuration
#
# MONGODB_URI defaults to a local MongoDB instance. Set both of these
# in the backend .env for anything beyond local dev.
# ---------------------------------------------------------

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "itom_assistant")

_client = MongoClient(MONGODB_URI)
_db = _client[MONGODB_DB_NAME]

users_collection: Collection = _db["users"]

# One account per email address.
users_collection.create_index("email", unique=True)

# ---------------------------------------------------------
# Saved chat history
#
# One document per conversation (documentation or incident), holding
# its messages. See conversations.py for the document shape.
# ---------------------------------------------------------

conversations_collection: Collection = _db["conversations"]

conversations_collection.create_index(
    [("user_id", 1), ("kind", 1), ("updated_at", -1)]
)

# ---------------------------------------------------------
# Chat images (screenshots people attach)
#
# Stored in GridFS, which lives inside the same MongoDB - no extra
# service to run. Each file records which user owns it, so the
# /images/{id} endpoint can refuse anyone else.
# ---------------------------------------------------------

_image_fs = gridfs.GridFS(_db, collection="chat_images")


def save_image(
    data: bytes,
    *,
    filename: str,
    content_type: str,
    user_id: str,
) -> str:
    image_id = str(uuid.uuid4())

    _image_fs.put(
        data,
        _id=image_id,
        filename=filename,
        content_type=content_type,
        user_id=user_id,
    )

    return image_id


def load_image(image_id: str) -> Optional[dict]:
    try:
        stored = _image_fs.get(image_id)
    except gridfs.errors.NoFile:
        return None

    return {
        "data": stored.read(),
        "content_type": stored.content_type or "application/octet-stream",
        "user_id": getattr(stored, "user_id", None),
    }


def delete_image(image_id: str) -> None:
    _image_fs.delete(image_id)