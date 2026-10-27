import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime, timedelta, timezone

import mysql.connector
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from dotenv import load_dotenv
from fastapi import HTTPException, Request

from app import database


load_dotenv(database.ENV_FILE, override=False)
SESSION_COOKIE_NAME = "phishshift_session"
CSRF_COOKIE_NAME = "phishshift_csrf"
SESSION_TTL_SECONDS = int(os.getenv("AUTH_SESSION_TTL_SECONDS", "28800"))
CSRF_TTL_SECONDS = 3600
password_hasher = PasswordHasher(type=Type.ID)
DUMMY_PASSWORD_HASH = password_hasher.hash(secrets.token_urlsafe(32))


def _session_secret() -> bytes:
    value = os.getenv("SESSION_SECRET", "")
    if len(value) < 64:
        raise RuntimeError("SESSION_SECRET must contain at least 64 characters.")
    return value.encode("utf-8")


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def new_session() -> tuple[str, str, datetime]:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
        seconds=SESSION_TTL_SECONDS
    )
    return token, token_hash, expires_at


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def issue_csrf_token() -> str:
    issued_at = str(int(time.time()))
    nonce = secrets.token_urlsafe(24)
    payload = f"{issued_at}.{nonce}"
    signature = hmac.new(_session_secret(), payload.encode("ascii"), hashlib.sha256)
    return f"{payload}.{signature.hexdigest()}"


def validate_csrf_token(token: str) -> bool:
    try:
        issued_at, nonce, supplied_signature = token.split(".", maxsplit=2)
        timestamp = int(issued_at)
        current_time = time.time()
        if (
            not nonce
            or current_time - timestamp > CSRF_TTL_SECONDS
            or timestamp > current_time + 30
        ):
            return False
        payload = f"{issued_at}.{nonce}"
        expected = hmac.new(
            _session_secret(), payload.encode("ascii"), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(supplied_signature, expected)
    except (ValueError, RuntimeError):
        return False


def require_csrf(request: Request) -> None:
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
    header_token = request.headers.get("X-CSRF-Token", "")
    if (
        not cookie_token
        or not header_token
        or not hmac.compare_digest(cookie_token, header_token)
        or not validate_csrf_token(header_token)
    ):
        raise HTTPException(status_code=403, detail="CSRF validation failed.")


def cookie_is_secure() -> bool:
    return os.getenv("APP_ENV", "development").lower() == "production" or (
        os.getenv("AUTH_COOKIE_SECURE", "").lower() == "true"
    )


def cookie_samesite() -> str:
    value = os.getenv("AUTH_COOKIE_SAMESITE", "lax").lower()
    if value not in {"strict", "lax", "none"}:
        raise RuntimeError("AUTH_COOKIE_SAMESITE must be strict, lax, or none.")
    if value == "none" and not cookie_is_secure():
        raise RuntimeError("SameSite=None cookies require Secure cookies.")
    return value


def set_auth_cookies(response, session_token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=cookie_is_secure(),
        samesite=cookie_samesite(),
        path="/",
    )
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")


def set_csrf_cookie(response, token: str) -> None:
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        max_age=CSRF_TTL_SECONDS,
        httponly=True,
        secure=cookie_is_secure(),
        samesite=cookie_samesite(),
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


def clear_auth_cookie(response) -> None:
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        httponly=True,
        secure=cookie_is_secure(),
        samesite=cookie_samesite(),
        path="/",
    )
    response.delete_cookie(
        CSRF_COOKIE_NAME,
        httponly=True,
        secure=cookie_is_secure(),
        samesite=cookie_samesite(),
        path="/",
    )


def get_current_user(request: Request) -> dict:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        user = database.get_session_user(hash_session_token(token))
    except (database.DatabaseConfigurationError, mysql.connector.Error) as exc:
        raise HTTPException(
            status_code=503,
            detail="Authentication service is temporarily unavailable.",
        ) from exc
    if user is None:
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
    return user
