"""
app/api/v1/auth.py
────────────────────────────────────────────────────────────────────────────────
Authentication router: register, verifyOTP, resendOTP, and login endpoints.

Token strategy:
  - JWT is returned in the response body on verifyOTP success and login.
  - This allows SPA / mobile clients to store and send it as a Bearer token.
"""
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import limiter
from app.db.database import get_db
from app.models.auth_models import (
    LoginSuccessResponse,
    RegisterResponse,
    ResendOTPRequest,
    UserLoginRequest,
    UserRegisterRequest,
    VerifyOTPRequest,
    VerifyOTPResponse,
)
from app.services.auth_service import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


# ── Register ───────────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description=(
        "Creates a new user account. "
        "The password is hashed with PBKDF2-HMAC-SHA256. "
        "A 6-digit OTP is generated and sent to the provided email. "
        "Returns the user record — MFA is not yet complete at this stage."
    ),
)
@limiter.limit("5/minute")
async def register(
    request: Request,
    payload: UserRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    return await auth_service.register(payload, db)


# ── Verify OTP ─────────────────────────────────────────────────────────────────

@router.post(
    "/verifyOTP",
    response_model=VerifyOTPResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify OTP and complete MFA",
    description=(
        "Validates the 6-digit OTP submitted by the user. "
        "On success: sets registerMFA=True and returns a signed JWT. "
        "On failure: returns status='failed' with a descriptive message "
        "so the client can keep the user on the MFA page."
    ),
)
@limiter.limit("5/minute")
async def verify_otp(
    request: Request,
    payload: VerifyOTPRequest,
    db: AsyncSession = Depends(get_db),
) -> VerifyOTPResponse:
    return await auth_service.verify_otp(payload, db)


# ── Resend OTP ─────────────────────────────────────────────────────────────────

@router.post(
    "/resendOTP",
    response_model=RegisterResponse,
    status_code=status.HTTP_200_OK,
    summary="Resend OTP",
    description=(
        "Generates a new 6-digit OTP and sends it to the registered email. "
        "Invalidates the previous OTP. "
        "Returns the same payload as /register so the client can stay on the MFA page."
    ),
)
@limiter.limit("3/minute")
async def resend_otp(
    request: Request,
    payload: ResendOTPRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    return await auth_service.resend_otp(payload, db)


# ── Login ──────────────────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=LoginSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Login and obtain a JWT access token",
    description=(
        "Authenticates a user with username (email) and password. "
        "Requires that OTP MFA has been completed (registerMFA=True). "
        "Returns a signed JWT access token in the response body."
    ),
)
@limiter.limit("5/minute")
async def login(
    request: Request,
    payload: UserLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginSuccessResponse:
    return await auth_service.login(payload, db)
