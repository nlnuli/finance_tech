from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from pymysql.err import IntegrityError

from .model import storage
from .schemas import AuthRequest, AuthResponse, LoginRequest, UserResponse
from .security import (
    create_access_token,
    decode_access_token,
    is_valid_email,
    normalize_email,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)


def public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "display_name": user.get("display_name"),
        "created_at": user["created_at"],
        "updated_at": user.get("updated_at"),
    }


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    user_id = str(payload.get("sub") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = storage.get_user(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


@router.post("/register", response_model=AuthResponse)
def register(request: AuthRequest) -> dict:
    email = normalize_email(request.email)
    if not is_valid_email(email):
        raise HTTPException(status_code=422, detail="Invalid email")
    try:
        user = storage.create_user(
            email=email,
            password=request.password,
            display_name=request.display_name,
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Email already registered") from exc

    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user": public_user(user),
    }


@router.post("/login", response_model=AuthResponse)
def login(request: LoginRequest) -> dict:
    user = storage.get_user_by_email(request.email)
    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user": public_user(user),
    }


@router.get("/me", response_model=UserResponse)
def me(user: dict = Depends(current_user)) -> dict:
    return public_user(user)
