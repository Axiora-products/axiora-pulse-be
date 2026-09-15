"""Extended user-profile ("user_details") operations — one row per User, 1:1 on user_id."""
import logging
import secrets

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timezone import now_ist, to_ist
from app.db.models import User, UserDetails
from app.models.user_details_models import CreateUserDetailsRequest, UpdateUserDetailsRequest, UserDetailsResponse
from app.services.s3_storage_service import s3_storage_service

logger = logging.getLogger(__name__)

_PROFILE_ID_PREFIX = "AXR"
_PROFILE_ID_MAX_ATTEMPTS = 10


async def _generate_unique_profile_id(db: AsyncSession) -> str:
    """Generate a profile id like 'AXR-847291', retrying on the rare collision."""
    for _ in range(_PROFILE_ID_MAX_ATTEMPTS):
        candidate = f"{_PROFILE_ID_PREFIX}-{secrets.randbelow(900000) + 100000}"
        existing = await db.execute(select(UserDetails.id).where(UserDetails.profile_id == candidate))
        if existing.scalar_one_or_none() is None:
            return candidate
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Could not generate a unique profile ID. Please try again.",
    )


async def _get_by_user_id(db: AsyncSession, user_id: int) -> UserDetails | None:
    result = await db.execute(select(UserDetails).where(UserDetails.user_id == user_id))
    return result.scalar_one_or_none()


async def _create_skeleton_profile(
    db: AsyncSession,
    *,
    user: User,
    profile_status: str = "Active",
) -> UserDetails:
    """Create a minimal ``user_details`` row for a user who has none yet.

    Used at sign-in time (so every login leaves a profile behind for admins
    to manage) and by the admin status endpoint (so a user can be deactivated
    even before they have completed onboarding). Returns the created row.
    """
    email = user.username.lower().strip()
    display_name = (user.display_name or "").strip()

    first_name = email.split("@", 1)[0]
    last_name = ""
    if display_name:
        parts = display_name.split(None, 1)
        first_name = parts[0]
        if len(parts) > 1:
            last_name = parts[1]

    record = UserDetails(
        profile_id=await _generate_unique_profile_id(db),
        user_id=user.id,
        first_name=first_name[:100],
        last_name=last_name[:100],
        email=email,
        mobile_number=None,
        profile_status=profile_status,
        created_at=now_ist(),
        updated_at=now_ist(),
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    logger.info("Created skeleton user_details profile_id=%s for user_id=%s", record.profile_id, user.id)
    return record


class UserDetailsService:
    @staticmethod
    def _proxy_avatar(response: UserDetailsResponse) -> UserDetailsResponse:
        """Replace the raw stored avatar_url with a server-proxied URL that works cross-origin."""
        if response.avatar_url and response.user_id:
            response.avatar_url = s3_storage_service.get_proxy_avatar_url(
                response.user_id, response.avatar_url
            )
        return response

    async def upsert(
        self, payload: CreateUserDetailsRequest, current_user: User, db: AsyncSession
    ) -> tuple[UserDetailsResponse, bool]:
        """Create the extended profile if none exists yet, otherwise overwrite it with
        the given fields. Returns (response, created) — created=True only on insert."""
        existing = await _get_by_user_id(db, current_user.id)
        # users.username is the login email — fall back to it when no email is given.
        email = str(payload.email).lower().strip() if payload.email else current_user.username.lower().strip()

        if existing is not None:
            existing.first_name = payload.first_name.strip()
            existing.last_name = payload.last_name.strip()
            existing.email = email
            existing.mobile_number = payload.mobile_number
            existing.date_of_birth = payload.date_of_birth
            existing.gender = payload.gender
            existing.nationality = payload.nationality
            existing.communication_preferences = payload.communication_preferences
            existing.updated_at = now_ist()
            await db.flush()
            await db.refresh(existing)
            logger.info("Upserted (updated) user_details profile_id=%s for user_id=%s", existing.profile_id, current_user.id)
            return self._proxy_avatar(UserDetailsResponse.model_validate(existing)), False

        profile_id = await _generate_unique_profile_id(db)
        registered_at = to_ist(current_user.created_at)
        record = UserDetails(
            profile_id=profile_id,
            user_id=current_user.id,
            first_name=payload.first_name.strip(),
            last_name=payload.last_name.strip(),
            email=email,
            mobile_number=payload.mobile_number,
            date_of_birth=payload.date_of_birth,
            gender=payload.gender,
            nationality=payload.nationality,
            communication_preferences=payload.communication_preferences,
            avatar_url=payload.avatar_url,
            created_at=registered_at,
            updated_at=registered_at,
        )
        db.add(record)
        await db.flush()
        await db.refresh(record)
        logger.info("Upserted (created) user_details profile_id=%s for user_id=%s", profile_id, current_user.id)
        return self._proxy_avatar(UserDetailsResponse.model_validate(record)), True

    async def get_own(self, current_user: User, db: AsyncSession) -> UserDetailsResponse:
        record = await _get_by_user_id(db, current_user.id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
        return self._proxy_avatar(UserDetailsResponse.model_validate(record))

    async def update_own(
        self, payload: UpdateUserDetailsRequest, current_user: User, db: AsyncSession
    ) -> UserDetailsResponse:
        record = await _get_by_user_id(db, current_user.id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")

        updates = payload.model_dump(exclude_unset=True)
        for field, value in updates.items():
            if field == "email" and value is not None:
                value = str(value).lower().strip()
            elif field in ("first_name", "last_name") and value is not None:
                value = value.strip()
            setattr(record, field, value)

        record.updated_at = now_ist()
        await db.flush()
        await db.refresh(record)
        logger.info("Updated user_details profile_id=%s for user_id=%s", record.profile_id, current_user.id)
        return self._proxy_avatar(UserDetailsResponse.model_validate(record))

    async def set_status_by_user_id(
        self, user_id: int, profile_status: str, db: AsyncSession
    ) -> UserDetailsResponse:
        """Admin action: set a user's profile_status (Active/Inactive/Suspended) by user_id.

        If the user has no ``user_details`` row yet, a minimal profile is
        created automatically so that the status can be set regardless of
        whether the user has completed onboarding.
        """
        record = await _get_by_user_id(db, user_id)

        if record is None:
            # Verify the user actually exists before creating a skeleton profile.
            user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found.",
                )

            record = await _create_skeleton_profile(
                db, user=user, profile_status=profile_status
            )
            logger.info(
                "Admin created skeleton profile_id=%s (user_id=%s) with profile_status=%s",
                record.profile_id, user_id, profile_status,
            )
            return self._proxy_avatar(UserDetailsResponse.model_validate(record))

        record.profile_status = profile_status
        record.updated_at = now_ist()
        await db.flush()
        await db.refresh(record)
        logger.info(
            "Admin set profile_status=%s for profile_id=%s (user_id=%s)",
            profile_status, record.profile_id, user_id,
        )
        return self._proxy_avatar(UserDetailsResponse.model_validate(record))

    @staticmethod
    async def touch_last_login(user_id: int, db: AsyncSession) -> None:
        """Stamp last_login_date (IST) on successful login.

        If the user has no ``user_details`` row yet, a skeleton profile is
        created first so that every login leaves a profile behind.
        """
        record = await _get_by_user_id(db, user_id)
        if record is None:
            user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
            if user is None:
                return
            record = await _create_skeleton_profile(db, user=user)
        record.last_login_date = now_ist()


user_details_service = UserDetailsService()
