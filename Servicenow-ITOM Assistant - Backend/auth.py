import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import HTTPException, Request, status

from db import users_collection

# ---------------------------------------------------------
# JWT / session configuration
# ---------------------------------------------------------

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_HOURS = 24 * 7  # 1 week

COOKIE_NAME = "session_token"
COOKIE_MAX_AGE_SECONDS = JWT_EXPIRES_HOURS * 3600

# ---------------------------------------------------------
# Cookie attributes: local dev vs. production
#
# Locally, frontend and backend are both on http://localhost, so a
# same-site "lax" cookie without "secure" works fine. In production
# they're almost always on two different domains (e.g. a Vercel
# frontend + a Render/Railway backend) - a cross-site cookie like
# that REQUIRES samesite="none" and secure=True, or the browser
# silently refuses to store it at all. Set ENVIRONMENT=production
# in the backend .env once you deploy; both sides also need to be
# served over HTTPS for "secure" cookies to actually get sent.
# ---------------------------------------------------------

IS_PRODUCTION = os.getenv("ENVIRONMENT", "development").lower() == "production"

COOKIE_SAMESITE = "none" if IS_PRODUCTION else "lax"
COOKIE_SECURE = IS_PRODUCTION


def _require_secret() -> str:
    if not JWT_SECRET_KEY:
        raise RuntimeError(
            "JWT_SECRET_KEY is not configured. Set it in the backend .env."
        )
    return JWT_SECRET_KEY


# ---------------------------------------------------------
# Password hashing
# ---------------------------------------------------------


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


# ---------------------------------------------------------
# JWT session tokens
# ---------------------------------------------------------


def create_session_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRES_HOURS),
    }
    return jwt.encode(payload, _require_secret(), algorithm=JWT_ALGORITHM)


def decode_session_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, _require_secret(), algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


# ---------------------------------------------------------
# User CRUD
# ---------------------------------------------------------


def create_user(
    email: str,
    password: str,
    servicenow_username: str,
    name: str = "",
) -> dict:
    normalized_email = email.lower().strip()

    if users_collection.find_one({"email": normalized_email}):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user_doc = {
        "_id": str(uuid.uuid4()),
        "email": normalized_email,
        "password_hash": hash_password(password),
        "servicenow_username": servicenow_username.strip(),
        # From the ServiceNow user record resolved at registration - used
        # for the avatar's initials until/unless a photo is uploaded.
        "name": name.strip(),
        "avatar_image_id": None,
        "created_at": datetime.now(timezone.utc),
    }

    users_collection.insert_one(user_doc)

    return user_doc


def update_email(user_id: str, new_email: str) -> dict:
    normalized_email = new_email.lower().strip()

    existing = users_collection.find_one({"email": normalized_email})

    if existing and existing["_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    users_collection.update_one(
        {"_id": user_id},
        {"$set": {"email": normalized_email}},
    )

    return get_user_by_id(user_id)


def update_servicenow_username(user_id: str, new_username: str) -> dict:
    """Caller (main.py) must already have re-validated new_username against
    ServiceNow via lookup_servicenow_user, same as at registration. Only
    the linked username changes - the account's display name is
    user-owned (see update_name) and isn't touched here."""

    users_collection.update_one(
        {"_id": user_id},
        {"$set": {"servicenow_username": new_username.strip()}},
    )

    return get_user_by_id(user_id)


def update_name(user_id: str, name: str) -> dict:
    users_collection.update_one(
        {"_id": user_id},
        {"$set": {"name": name.strip()}},
    )

    return get_user_by_id(user_id)


def update_password(user_id: str, current_password: str, new_password: str) -> dict:
    user_doc = get_user_by_id(user_id)

    if not user_doc or not verify_password(current_password, user_doc["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect.",
        )

    users_collection.update_one(
        {"_id": user_id},
        {"$set": {"password_hash": hash_password(new_password)}},
    )

    return get_user_by_id(user_id)


def set_avatar(user_id: str, image_id: str) -> dict:
    users_collection.update_one(
        {"_id": user_id},
        {"$set": {"avatar_image_id": image_id}},
    )

    return get_user_by_id(user_id)


def clear_avatar(user_id: str) -> dict:
    users_collection.update_one(
        {"_id": user_id},
        {"$set": {"avatar_image_id": None}},
    )

    return get_user_by_id(user_id)


def authenticate_user(email: str, password: str) -> dict:
    user_doc = users_collection.find_one({"email": email.lower().strip()})

    if not user_doc or not verify_password(password, user_doc["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    return user_doc


def get_user_by_id(user_id: str) -> Optional[dict]:
    return users_collection.find_one({"_id": user_id})


# ---------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------


def get_current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )

    user_id = decode_session_token(token)

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid. Please log in again.",
        )

    user_doc = get_user_by_id(user_id)

    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account no longer exists.",
        )

    return user_doc


def public_user(user_doc: dict) -> dict:
    """Shape a Mongo user document into the JSON-safe dict returned to the client."""

    return {
        "id": user_doc["_id"],
        "email": user_doc["email"],
        "servicenow_username": user_doc["servicenow_username"],
        "name": user_doc.get("name", ""),
        "has_avatar": bool(user_doc.get("avatar_image_id")),
    }