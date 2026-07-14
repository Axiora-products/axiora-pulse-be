"""
app/services/auth_service.py
────────────────────────────────────────────────────────────────────────────────
Authentication service — fully database-backed using async SQLAlchemy.

Replaces the previous in-memory user store.

Operations:
  register()    → hash password, generate OTP, persist user, dispatch OTP
  verify_otp()  → validate OTP + expiry, set registerMFA=True, return JWT
  resend_otp()  → generate new OTP, update DB, redispatch OTP
  login()       → verify credentials, return JWT

OTP delivery is routed through otp_dispatcher which detects email vs phone
automatically — auth_service never needs to know the channel used.
"""
import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    generate_otp,
    hash_password_async,
    otp_expiry,
    verify_password_async,
)
from app.core.config import settings
from app.db.models import User
from app.models.auth_models import (
    LoginSuccessResponse,
    RegisterResponse,
    ResendOTPRequest,
    UserLoginRequest,
    UserRegisterRequest,
    VerifyOTPRequest,
    VerifyOTPResponse,
)
from app.services.otp_dispatcher import dispatch_otp

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_user_by_id(db: AsyncSession, user_id: int) -> User:
    """Fetch a user by PK. Raises 404 if not found."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


async def _get_user_by_username(db: AsyncSession, username: str) -> User | None:
    """Fetch a user by username (email). Returns None if not found."""
    result = await db.execute(select(User).where(User.username == username.lower().strip()))
    return result.scalar_one_or_none()


def _to_register_response(user: User) -> RegisterResponse:
    return RegisterResponse(
        userid=user.id,
        username=user.username,
        registerMFA=user.register_mfa,
    )


# ── Auth Service ───────────────────────────────────────────────────────────────

class AuthService:
    """Handles all user authentication operations against the PostgreSQL database."""

    # ── Register ───────────────────────────────────────────────────────────────

    async def register(
        self, request: UserRegisterRequest, db: AsyncSession
    ) -> RegisterResponse:
        """Create a new user, generate OTP, and trigger the OTP email.

        Raises:
            HTTPException 409 if the username is already registered.
        """
        username = request.username.lower().strip()

        existing = await _get_user_by_username(db, username)
        if existing is not None:
            logger.warning("Duplicate registration attempt for: %s", username)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            )

        otp = generate_otp()
        expiry = otp_expiry()

        user = User(
            role="user",
            username=username,
            password=await hash_password_async(request.password),
            register_otp=otp,
            register_otp_expiry=expiry,
            register_mfa=False,
        )
        db.add(user)
        await db.flush()        # Flush to get the auto-generated id
        await db.refresh(user)  # Populate id from DB

        logger.info("New user registered: %s (id=%s)", username, user.id)

        # Dispatch OTP — if delivery fails we still commit the user record
        # so they can use /resendOTP without re-registering.
        result = await dispatch_otp(username, otp)
        if not result.success:
            logger.warning(
                "OTP dispatch failed after registration for %s: %s",
                username, result.error
            )
            # Do not raise — user is saved; client can call /resendOTP.

        return _to_register_response(user)

    # ── Verify OTP ─────────────────────────────────────────────────────────────

    async def verify_otp(
        self, request: VerifyOTPRequest, db: AsyncSession
    ) -> VerifyOTPResponse:
        """Validate the OTP for a given flow.

        Returns a VerifyOTPResponse with status "success" or "failed".
        On success: sets registerMFA=True and includes a signed JWT.
        On failure: returns HTTP 200 with status="failed" and an error message
                    (keeps user on MFA page for retry).
        """
        user = await _get_user_by_id(db, request.id)

        # ── Expiry check (run first to avoid wasting attempts on expired OTP) ──
        now = datetime.now(tz=timezone.utc)
        expiry = user.register_otp_expiry
        if expiry is not None and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)

        if user.register_otp is None:
            logger.warning("No active OTP found for user id=%s", request.id)
            return VerifyOTPResponse(status="failed", message="OTP is wrong")

        if expiry is None or now > expiry:
            logger.warning("Expired OTP attempt for user id=%s", request.id)
            # Clear expired OTP
            user.register_otp = None
            user.register_otp_expiry = None
            user.register_otp_attempts = 0
            return VerifyOTPResponse(status="failed", message="OTP is expired !")

        # ── OTP match check ────────────────────────────────────────────────────
        if user.register_otp != request.otp:
            user.register_otp_attempts += 1
            logger.warning(
                "Wrong OTP attempt %s/3 for user id=%s",
                user.register_otp_attempts, request.id
            )
            if user.register_otp_attempts >= 3:
                # Invalidate OTP on 3rd failure
                user.register_otp = None
                user.register_otp_expiry = None
                user.register_otp_attempts = 0
                return VerifyOTPResponse(
                    status="failed",
                    message="Too many failed attempts. OTP has been invalidated. Please resend OTP."
                )
            return VerifyOTPResponse(status="failed", message="OTP is wrong")

        # ── Success — mark MFA complete, clear OTP, issue JWT ─────────────────
        user.register_mfa = True
        user.register_otp = None
        user.register_otp_expiry = None
        user.register_otp_attempts = 0

        token = create_access_token(data={"sub": str(user.id), "username": user.username})
        logger.info("OTP verified for user id=%s (%s)", user.id, user.username)

        return VerifyOTPResponse(
            status="success",
            message="OTP Validated Successfully !",
            jwt=token,
        )

    # ── Resend OTP ─────────────────────────────────────────────────────────────

    async def resend_otp(
        self, request: ResendOTPRequest, db: AsyncSession
    ) -> RegisterResponse:
        """Generate a fresh OTP, update the user record, and resend the email.

        Raises:
            HTTPException 404 if the user id is not found.
            HTTPException 400 if MFA is already completed (no need to resend).
        """
        user = await _get_user_by_id(db, request.id)

        if user.register_mfa:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="MFA already verified for this account.",
            )

        otp = generate_otp()
        expiry = otp_expiry()

        user.register_otp = otp
        user.register_otp_expiry = expiry
        user.register_otp_attempts = 0

        logger.info("OTP regenerated for user id=%s (%s)", user.id, user.username)

        result = await dispatch_otp(user.username, otp)
        if not result.success:
            logger.error(
                "Resend OTP dispatch failed for user id=%s: %s", user.id, result.error
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    result.error
                    or "Failed to deliver OTP. Please try again."
                ),
            )

        return _to_register_response(user)

    # ── Login ──────────────────────────────────────────────────────────────────

    async def login(
        self, request: UserLoginRequest, db: AsyncSession
    ) -> LoginSuccessResponse:
        """Authenticate a user and issue a signed JWT access token.

        Raises:
            HTTPException 401 if credentials are invalid.
            HTTPException 403 if MFA has not been completed yet.
        """
        username = request.username.lower().strip()
        user = await _get_user_by_username(db, username)

        # Deliberately generic error — do not reveal whether the username exists.
        if user is None or not await verify_password_async(request.password, user.password):
            logger.warning("Failed login attempt for username: %s", username)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.register_mfa:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account not verified. Please complete OTP verification.",
            )

        token = create_access_token(data={"sub": str(user.id), "username": user.username})
        logger.info("Login successful for user: %s (id=%s)", username, user.id)

        return LoginSuccessResponse(
            jwt=token,
            expires_in_minutes=settings.access_token_expire_minutes,
        )


# ── Module-level singleton ─────────────────────────────────────────────────────
auth_service = AuthService()
