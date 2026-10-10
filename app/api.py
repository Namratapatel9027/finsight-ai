"""FastAPI service for authenticated, session-isolated RAG requests."""

import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from access_control import normalize_role
from conversation_store import ConversationStore


app = FastAPI(title="FinSolve RAG API", version="1.0.0")
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


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/auth/login", response_model=LoginResponse)
def login(request: LoginRequest):
    """Verify company credentials against hr_data.csv securely."""
    clean_email = request.email.strip().lower()
    clean_password = request.password.strip()

    # Domain restriction check
    if not clean_email.endswith("@fintechco.com"):
        raise HTTPException(
            status_code=400,
            detail="Please use your official company email address (@fintechco.com).",
        )

    project_root = Path(__file__).resolve().parent.parent
    hr_csv_path = project_root / "data" / "hr" / "hr_data.csv"

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

    # 1. Match Email
    matched = hr_df[hr_df["email"].astype(str).str.strip().str.lower() == clean_email]
    if matched.empty:
        raise HTTPException(
            status_code=401,
            detail="Access Denied: Email address is not registered in company records.",
        )

    emp_row = matched.iloc[0]
    dept_raw = str(emp_row.get("department", "General")).strip()
    role_raw = str(emp_row.get("role", dept_raw)).strip()
    name_raw = str(emp_row.get("full_name", emp_row.get("name", "Employee"))).strip()
    user_id = str(emp_row.get("employee_id", clean_email.split("@")[0])).strip()

    # 2. Match Password Securely (Backend Check only)
    # Allows proper department credential: e.g. "Finance@123" or "Sales@123"
    valid_passwords = {f"{dept_raw.capitalize()}@123", f"{dept_raw.title()}@123", f"{dept_raw.lower()}@123"}

    if clean_password not in valid_passwords:
        raise HTTPException(
            status_code=401,
            detail="Incorrect password. Please verify your credentials and try again.",
        )

    # Map department to RBAC role
    # Engineering/Technology -> engineering, Finance -> finance, Marketing -> marketing, HR -> hr, others -> general
    dept_lower = dept_raw.lower()
    if "tech" in dept_lower or "engineer" in dept_lower:
        normalized_role = "engineering"
    elif "finan" in dept_lower:
        normalized_role = "finance"
    elif "market" in dept_lower:
        normalized_role = "marketing"
    elif "hr" in dept_lower:
        normalized_role = "hr"
    else:
        normalized_role = normalize_role(dept_raw)

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
        result = run_rag_question(
            question,
            role=user.role,
            history_messages=history,
        )

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