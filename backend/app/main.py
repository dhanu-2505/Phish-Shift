import logging
import json
import os
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import mysql.connector
from argon2.exceptions import HashingError
from fastapi import Depends, FastAPI, HTTPException, Path as PathParameter, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

from app import database
from app.auth import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    DUMMY_PASSWORD_HASH,
    clear_auth_cookie,
    get_current_user,
    hash_session_token,
    hash_password,
    issue_csrf_token,
    new_session,
    normalize_email,
    require_csrf,
    set_auth_cookies,
    set_csrf_cookie,
    verify_password,
)
from app.database import (
    DatabaseConfigurationError,
    check_database_connection,
    get_scan_result,
    get_user_scan_summary,
    list_scan_results,
    save_scan_result,
)
from app.model import ModelUnavailableError, load_model_bundle, predict_message


logger = logging.getLogger(__name__)
app = FastAPI(title="PhishShift Database API", version="0.1.0")


def get_frontend_origins() -> list[str]:
    configured_origins = os.getenv("FRONTEND_ORIGINS", "").strip()
    if os.getenv("APP_ENV", "development").strip().lower() == "production":
        if not configured_origins:
            raise RuntimeError("FRONTEND_ORIGINS must be configured in production.")
        origins = [origin.strip() for origin in configured_origins.split(",") if origin.strip()]
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme != "https"
                or not parsed.netloc
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
                or "*" in origin
            ):
                raise RuntimeError(
                    "Production FRONTEND_ORIGINS must contain exact HTTPS origins."
                )
        return origins

    return [
        origin.strip()
        for origin in (
            configured_origins
            or "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if origin.strip()
    ]


EVALUATION_REPORT = Path(
    os.getenv(
        "MODEL_EVALUATION_REPORT",
        str(Path(__file__).resolve().parents[2] / "reports" / "model_evaluation.json"),
    )
)
frontend_origins = get_frontend_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Accept", "Content-Type", "X-CSRF-Token"],
)


class PredictionRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    record_kind: Literal["user", "verification"] = "user"

    @field_validator("message")
    @classmethod
    def message_must_contain_non_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must contain non-whitespace characters.")
        return value


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=12, max_length=128)
    confirm_password: SecretStr = Field(min_length=12, max_length=128)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name cannot be blank.")
        return normalized

    @field_validator("email")
    @classmethod
    def normalize_and_validate_email(cls, value: str) -> str:
        normalized = normalize_email(value)
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized

    @model_validator(mode="after")
    def passwords_must_match(self):
        if self.password.get_secret_value() != self.confirm_password.get_secret_value():
            raise ValueError("Passwords do not match.")
        return self


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_and_validate_email(cls, value: str) -> str:
        normalized = normalize_email(value)
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized


def _public_user(user: dict) -> dict:
    return {"id": user["id"], "name": user["name"], "email": user["email"]}


@app.get("/api/auth/csrf")
def csrf_token(response: Response):
    token = issue_csrf_token()
    set_csrf_cookie(response, token)
    return {"csrf_token": token}


@app.post("/api/auth/register")
def register(
    request: RegisterRequest,
    response: Response,
    _csrf: None = Depends(require_csrf),
):
    session_token, session_hash, expires_at = new_session()
    try:
        password_hash = hash_password(request.password.get_secret_value())
        user = database.create_user_and_session(
            request.name,
            request.email,
            password_hash,
            session_hash,
            expires_at,
        )
    except mysql.connector.IntegrityError as exc:
        if exc.errno == 1062:
            raise HTTPException(
                status_code=409,
                detail="An account with this email already exists.",
            ) from exc
        logger.warning("Account registration failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Account registration is temporarily unavailable.",
        ) from exc
    except (DatabaseConfigurationError, mysql.connector.Error, HashingError) as exc:
        logger.warning("Account registration failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Account registration is temporarily unavailable.",
        ) from exc

    set_auth_cookies(response, session_token)
    return {"user": _public_user(user)}


@app.post("/api/auth/login")
def login(
    request: LoginRequest,
    response: Response,
    _csrf: None = Depends(require_csrf),
):
    try:
        user = database.get_user_by_email(request.email)
    except (DatabaseConfigurationError, mysql.connector.Error) as exc:
        logger.warning("Login lookup failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Authentication service is temporarily unavailable.",
        ) from exc

    password = request.password.get_secret_value()
    if user is None:
        verify_password(DUMMY_PASSWORD_HASH, password)
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    if not verify_password(user["password_hash"], password):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")

    session_token, session_hash, expires_at = new_session()
    try:
        database.create_user_session(user["id"], session_hash, expires_at)
    except (DatabaseConfigurationError, mysql.connector.Error) as exc:
        logger.warning("Session creation failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Authentication service is temporarily unavailable.",
        ) from exc
    set_auth_cookies(response, session_token)
    return {"user": _public_user(user)}


@app.get("/api/auth/me")
def current_user(user: dict = Depends(get_current_user)):
    return {"user": _public_user(user), "expires_in": SESSION_TTL_SECONDS}


@app.post("/api/auth/logout")
def logout(
    request: Request,
    response: Response,
    user: dict = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
):
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    try:
        database.delete_user_session(hash_session_token(token))
    except (DatabaseConfigurationError, mysql.connector.Error) as exc:
        logger.warning("Logout session revocation failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Logout could not be completed. Please retry.",
        ) from exc
    clear_auth_cookie(response)
    return {"status": "ok"}


@app.get("/health/db")
def database_health():
    try:
        check_database_connection()
    except (DatabaseConfigurationError, mysql.connector.Error) as exc:
        logger.warning("Database health check failed (%s).", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "detail": (
                    "Database connection could not be verified. "
                    "Check the local database configuration and server status."
                ),
            },
        )
    return {"status": "ok", "database": "phishshift_db"}


@app.get("/health/model")
def model_health():
    try:
        bundle = load_model_bundle()
    except ModelUnavailableError as exc:
        logger.warning("Model health check failed (%s).", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "detail": "Trained model is unavailable."},
        )
    metadata = bundle["metadata"]
    return {
        "status": "ok",
        "model_name": metadata["model_name"],
        "model_version": metadata["model_version"],
    }


@app.get("/health/ready")
def readiness_health():
    try:
        check_database_connection()
        load_model_bundle()
    except (DatabaseConfigurationError, mysql.connector.Error, ModelUnavailableError) as exc:
        logger.warning("Readiness check failed (%s).", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "detail": "Application is not ready."},
        )
    return {"status": "ok"}


@app.post("/api/predict")
def predict(
    request: PredictionRequest,
    current_user: dict = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
):
    try:
        result = predict_message(request.message)
    except ModelUnavailableError as exc:
        logger.warning("Prediction unavailable (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Trained model is unavailable.",
        ) from exc

    try:
        scan_id = save_scan_result(
            current_user["id"],
            request.message,
            result["predicted_label"],
            result["risk_score"],
            result["explanation"],
            request.record_kind,
        )
    except (DatabaseConfigurationError, mysql.connector.Error) as exc:
        logger.warning("Could not persist prediction (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Prediction history could not be saved.",
        ) from exc

    return {"scan_id": scan_id, **result}


@app.get("/api/scans")
def scan_history(
    page: int = Query(default=1, ge=1, le=1_000_000),
    page_size: int = Query(default=10, ge=1, le=100),
    label: Literal["Safe Email", "Phishing Email"] | None = Query(default=None),
    sort_by: Literal["created_at", "risk_score"] = Query(default="created_at"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
    current_user: dict = Depends(get_current_user),
):
    offset = (page - 1) * page_size
    try:
        items, total = list_scan_results(
            current_user["id"],
            page_size,
            offset,
            label,
            sort_by,
            sort_order,
        )
    except (DatabaseConfigurationError, mysql.connector.Error) as exc:
        logger.warning("Could not read scan history (%s).", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "detail": "Scan history is temporarily unavailable.",
            },
        )
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }


@app.get("/api/dashboard/summary")
def dashboard_summary(current_user: dict = Depends(get_current_user)):
    try:
        return get_user_scan_summary(current_user["id"])
    except (DatabaseConfigurationError, mysql.connector.Error) as exc:
        logger.warning("Could not read dashboard summary (%s).", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "detail": "Dashboard scan statistics are temporarily unavailable.",
            },
        )


@app.get("/api/scans/{scan_id}")
def scan_detail(
    scan_id: int = PathParameter(gt=0),
    current_user: dict = Depends(get_current_user),
):
    try:
        scan = get_scan_result(scan_id, current_user["id"])
    except (DatabaseConfigurationError, mysql.connector.Error) as exc:
        logger.warning("Could not read scan detail (%s).", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "detail": "Scan details are temporarily unavailable.",
            },
        )
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found.")
    return scan


@app.get("/api/model/evaluation")
def model_evaluation(current_user: dict = Depends(get_current_user)):
    del current_user
    try:
        report = json.loads(EVALUATION_REPORT.read_text(encoding="utf-8"))
        metadata = report["metadata"]
        evaluation = report["evaluation"]
        return {
            "model_name": metadata["model_name"],
            "model_version": metadata["model_version"],
            "dataset_name": metadata["dataset_name"],
            "dataset_source": metadata["dataset_source"],
            "dataset_license": metadata["dataset_license"],
            "trained_at_utc": metadata["trained_at_utc"],
            "dataset_counts": metadata["dataset_counts"],
            "class_counts_after_deduplication": metadata[
                "class_counts_after_deduplication"
            ],
            "training_rows": metadata["training_rows"],
            "test_rows": metadata["test_rows"],
            "test_size_fraction": metadata["test_size_fraction"],
            "random_state": metadata["random_state"],
            "positive_class": metadata["positive_class"],
            "precision": evaluation["precision"],
            "recall": evaluation["recall"],
            "f1_score": evaluation["f1_score"],
            "false_positive_rate": evaluation["false_positive_rate"],
            "confusion_matrix_labels": evaluation["confusion_matrix_labels"],
            "confusion_matrix": evaluation["confusion_matrix"],
            "false_positive_analysis": evaluation["false_positive_analysis"],
        }
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.error("Model evaluation report unavailable (%s).", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "detail": "Model evaluation report is unavailable.",
            },
        )
