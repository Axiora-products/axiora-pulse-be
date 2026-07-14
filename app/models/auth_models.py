"""
app/models/auth_models.py
────────────────────────────────────────────────────────────────────────────────
Pydantic request/response models for all authentication endpoints.

Endpoints covered:
  POST /register    → UserRegisterRequest  → RegisterResponse
  POST /verifyOTP   → VerifyOTPRequest     → VerifyOTPResponse
  POST /resendOTP   → ResendOTPRequest     → RegisterResponse
  POST /login       → UserLoginRequest     → LoginSuccessResponse
"""
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, field_validator


# ── Request Models ─────────────────────────────────────────────────────────────

class UserRegisterRequest(BaseModel):
    """Payload for POST /api/v1/auth/register."""
    username: EmailStr          # email address used as the unique username
    password: str

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        """Enforce password policy using standard Python str methods only."""
        errors = []

        if len(value) < 8:
            errors.append("at least 8 characters")

        if not any(c.isupper() for c in value):
            errors.append("at least one uppercase letter")

        if not any(c.islower() for c in value):
            errors.append("at least one lowercase letter")

        if not any(c.isdigit() for c in value):
            errors.append("at least one digit")

        _special = set("!@#$%^&*()_+-=[]{}|;':\",./<>?")
        if not any(c in _special for c in value):
            errors.append("at least one special character (!@#$%^&*...)")

        if errors:
            raise ValueError("Password must contain: " + ", ".join(errors))

        return value


class UserLoginRequest(BaseModel):
    """Payload for POST /api/v1/auth/login."""
    username: EmailStr
    password: str


class VerifyOTPRequest(BaseModel):
    """Payload for POST /api/v1/auth/verifyOTP."""
    id: int
    otp: int
    flow: Literal["register"]   # extensible for future flows (e.g. "login")


class ResendOTPRequest(BaseModel):
    """Payload for POST /api/v1/auth/resendOTP."""
    id: int
    flow: Literal["register"]


# ── Response Models ────────────────────────────────────────────────────────────

class RegisterResponse(BaseModel):
    """Returned after successful registration or OTP resend."""
    userid: int
    username: str
    registerMFA: bool


class VerifyOTPResponse(BaseModel):
    """Returned after OTP verification attempt."""
    status: str                     # "success" | "failed"
    message: str
    jwt: Optional[str] = None       # Present only on success


class LoginSuccessResponse(BaseModel):
    """Returned on successful login."""
    status: str = "success"
    message: str = "Login successful."
    jwt: str
    token_type: str = "bearer"
    expires_in_minutes: int
