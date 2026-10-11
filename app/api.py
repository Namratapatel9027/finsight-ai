"""FastAPI service for authenticated, session-isolated RAG requests."""

import json
import math
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd
from groq import RateLimitError
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from access_control import normalize_role
from conversation_store import ConversationStore
from fastapi.middleware.cors import CORSMiddleware

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"

# The CSV uses "Technology" for the knowledge base's "engineering" folder.
# Departments without a corresponding data folder are not allowed to sign in.
CSV_DEPARTMENT_ROLES = {
    "engineering": "engineering",
    "technology": "engineering",
    "finance": "finance",
    "hr": "hr",
    "marketing": "marketing",
    "general": "employee",
}
DEMO_PASSWORD = "pass@123"

app = FastAPI(title="FinSolve RAG API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_sessions = ConversationStore()
_bearer = HTTPBearer(auto_error=False)

# Dynamic store for authenticated sessions
_active_user_tokens: dict[str, "AuthenticatedUser"] = {}


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    role: str
    name: str = "Demo User"
    department: str = "General"
    email: str = ""


class ChatRequest(BaseModel):
    session_id: UUID
    question: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    answer: str
    standalone_question: str
    intent: str
    sources: list[str]


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=1, max_length=100)


class LoginResponse(BaseModel):
    access_token: str
    name: str
    role: str
    department: str
    email: str


def _load_identities():
    """Read configured identities plus active logged-in sessions."""
    configured_tokens = os.getenv("FINSOLVE_API_TOKENS")
    identities = {}

    if configured_tokens:
        try:
            token_map = json.loads(configured_tokens)
            if isinstance(token_map, dict):
                for token, record in token_map.items():
                    if isinstance(token, str) and token and isinstance(record, dict):
                        user_id = record.get("user_id", "").strip()
                        if user_id:
                            identities[token] = AuthenticatedUser(
                                user_id=user_id,
                                role=normalize_role(record.get("role")),
                                name=record.get("name", user_id.capitalize()),
                                department=record.get("role", "general").capitalize(),
                                email=record.get("email", ""),
                            )
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

    identities.update(_active_user_tokens)
    return identities


def authenticate_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="A valid bearer token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    identities = _load_identities()
    authenticated_user = None
    for token, identity in identities.items():
        if secrets.compare_digest(credentials.credentials, token):
            authenticated_user = identity
            break

    if authenticated_user is None:
        raise HTTPException(
            status_code=401,
            detail="Session expired or invalid token. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return authenticated_user


def run_rag_question(question, role, history_messages):
    """Load the model-backed pipeline only when a chat request arrives."""
    from rag import answer_question

    return answer_question(
        question,
        role=role,
        history_messages=history_messages,
    )


def format_rate_limit_retry(error: RateLimitError) -> tuple[str, int | None]:
    """Return a safe, human-readable retry delay from Groq's 429 response."""
    response = getattr(error, "response", None)
    headers = response.headers if response is not None else {}
    retry_seconds = None

    retry_ms = headers.get("retry-after-ms")
    retry_after = headers.get("retry-after")
    for value, multiplier in ((retry_ms, 0.001), (retry_after, 1)):
        try:
            retry_seconds = max(1, math.ceil(float(value) * multiplier))
            break
        except (TypeError, ValueError):
            continue

    if retry_seconds is None:
        retry_text = headers.get("x-ratelimit-reset-tokens", "")
        if not retry_text:
            message = str(error)
            match = re.search(r"try again in\s+((?:\d+(?:\.\d+)?[hms])+)", message, re.IGNORECASE)
            retry_text = match.group(1) if match else ""

        parts = re.findall(r"(\d+(?:\.\d+)?)([hms])", retry_text, re.IGNORECASE)
        if parts:
            factors = {"h": 3600, "m": 60, "s": 1}
            retry_seconds = max(
                1,
                math.ceil(sum(float(value) * factors[unit.lower()] for value, unit in parts)),
            )

    if retry_seconds is None:
        return "a short while", None

    minutes, seconds = divmod(retry_seconds, 60)
    if minutes:
        retry_label = f"{minutes} minute{'s' if minutes != 1 else ''}"
        if seconds:
            retry_label += f" {seconds} second{'s' if seconds != 1 else ''}"
    else:
        retry_label = f"{seconds} second{'s' if seconds != 1 else ''}"
    return retry_label, retry_seconds


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/auth/login", response_model=LoginResponse)
def login(request: LoginRequest):
    """Verify demo credentials and department access against hr_data.csv."""
    clean_email = request.email.strip().lower()
    clean_password = request.password.strip()

    # Domain restriction check
    if not clean_email.endswith("@fintechco.com"):
        raise HTTPException(
            status_code=400,
            detail="Please use your official company email address (@fintechco.com).",
        )

    hr_csv_path = PROJECT_ROOT / "data" / "hr" / "hr_data.csv"

    if not hr_csv_path.exists():
        raise HTTPException(
            status_code=500,
            detail="Authentication directory service is currently unreachable.",
        )

    try:
        hr_df = pd.read_csv(hr_csv_path)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access employee directory: {e}",
        )

    required_columns = {"email", "department"}
    if not required_columns.issubset(hr_df.columns):
        raise HTTPException(
            status_code=500,
            detail="Employee directory must contain email and department columns.",
        )

    # Match email case-insensitively, then only allow CSV departments represented
    # by one of the five department folders under data/.
    matched = hr_df[hr_df["email"].astype(str).str.strip().str.lower() == clean_email]
    if matched.empty:
        raise HTTPException(
            status_code=401,
            detail="Access Denied: Email address is not registered in company records.",
        )

    if not secrets.compare_digest(clean_password, DEMO_PASSWORD):
        raise HTTPException(
            status_code=401,
            detail="Incorrect password. For this demo, use the shared password pass@123.",
        )

    matched = matched.copy()
    matched["_access_role"] = matched["department"].map(
        lambda value: CSV_DEPARTMENT_ROLES.get(str(value).strip().casefold())
    )
    eligible = matched[matched["_access_role"].notna()]
    if eligible.empty:
        raise HTTPException(
            status_code=403,
            detail="Access is available only to Engineering/Technology, Finance, HR, Marketing, and General departments.",
        )

    # Some demo CSV emails repeat across departments. The login form has one
    # email field, so bind a duplicate email to its first supported CSV row.
    emp_row = eligible.iloc[0]
    dept_raw = str(emp_row.get("department", "General")).strip()
    role_raw = str(emp_row.get("role", dept_raw)).strip()
    name_raw = str(emp_row.get("full_name", emp_row.get("name", "Employee"))).strip()
    user_id = str(emp_row.get("employee_id", clean_email.split("@")[0])).strip()
    normalized_role = emp_row["_access_role"]

    token = f"finsolve-{uuid4().hex}"
    authenticated_user = AuthenticatedUser(
        user_id=user_id,
        role=normalized_role,
        name=name_raw,
        department=dept_raw,
        email=clean_email,
    )
    _active_user_tokens[token] = authenticated_user

    return LoginResponse(
        access_token=token,
        name=name_raw,
        role=role_raw,
        department=dept_raw,
        email=clean_email,
    )


@app.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    user: AuthenticatedUser = Depends(authenticate_user),
):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question cannot be blank.")

    with _sessions.use_session(user.user_id, str(request.session_id)) as history:
        try:
            result = run_rag_question(
                question,
                role=user.role,
                history_messages=history,
            )
        except RateLimitError as error:
            retry_label, retry_seconds = format_rate_limit_retry(error)
            detail = f"AI request limit exceeded. Please try again in {retry_label}."
            headers = {"Retry-After": str(retry_seconds)} if retry_seconds else None
            raise HTTPException(status_code=429, detail=detail, headers=headers) from error

    if result.get("access_denied"):
        raise HTTPException(status_code=403, detail=result["answer"])

    sources = list(
        dict.fromkeys(
            item.get("metadata", {}).get("source", "unknown")
            for item in result.get("results", [])
        )
    )
    return ChatResponse(
        answer=result["answer"],
        standalone_question=result["standalone_question"],
        intent=result["intent"],
        sources=sources,
    )


# Serve the plain HTML application and its assets from the same origin as the
# API. This avoids frontend/API port and CORS configuration errors in local use.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
