"""Unit tests for app/services/user_details_service.py.

Covers UPSERT (create + update), get_own, update_own, admin status set, and the
last-login touch helper.
"""
import pytest
from fastapi import HTTPException
from unittest.mock import patch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password_async
from app.db.models import Role, User, UserDetails
from app.models.user_details_models import (
    CreateUserDetailsRequest,
    UpdateUserDetailsRequest,
)
from app.services.user_details_service import (
    UserDetailsService,
    _generate_unique_profile_id,
    _get_by_user_id,
)

service = UserDetailsService()


# ── Helpers ──────────────────────────────────────────────────────────────────

async def create_user(db_session: AsyncSession, *, username: str) -> User:
    member_role = (await db_session.execute(select(Role).where(Role.name == "member"))).scalar_one_or_none()
    if member_role is None:
        member_role = Role(name="member", description="Paid subscription user")
        db_session.add(member_role)
        await db_session.flush()
    user = User(
        username=username,
        password=await hash_password_async("Test@12345"),
        register_mfa=True,
        role=member_role,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _create_payload(**overrides) -> CreateUserDetailsRequest:
    base = dict(
        first_name="John",
        last_name="Doe",
        mobile_number="9876543210",
        communication_preferences=["Email"],
        gender="Male",
        nationality="Indian",
        date_of_birth="1990-01-01",
    )
    base.update(overrides)
    return CreateUserDetailsRequest(**base)


# ── _generate_unique_profile_id ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_unique_profile_id_uses_prefix(db_session: AsyncSession):
    user = await create_user(db_session, username="profile-prefix@example.com")
    pid = await _generate_unique_profile_id(db_session)
    assert pid.startswith("AXR-")
    assert len(pid.split("-")[1]) == 6


@pytest.mark.asyncio
async def test_generate_unique_profile_id_retries_on_collision(db_session: AsyncSession):
    user = await create_user(db_session, username="profile-collide@example.com")
    # Force the first `secrets.randbelow` to produce a value that collides with an
    # existing record, then succeed on a later attempt.
    first = await _generate_unique_profile_id(db_session)
    existing = UserDetails(
        profile_id=first,
        user_id=user.id,
        first_name="A",
        last_name="B",
        email="x@example.com",
        mobile_number="9876543210",
    )
    db_session.add(existing)
    await db_session.commit()

    with patch("app.services.user_details_service.secrets.randbelow", side_effect=[int(first.split("-")[1]) - 100000, 500000]):
        pid = await _generate_unique_profile_id(db_session)
    assert pid != first


# ── upsert ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_creates_new_profile(db_session: AsyncSession):
    user = await create_user(db_session, username="upsert-new@example.com")
    resp, created = await service.upsert(_create_payload(), user, db_session)
    assert created is True
    assert resp.first_name == "John"
    assert resp.email == "upsert-new@example.com"  # defaulted to username? no—payload has no email
    await db_session.flush()


@pytest.mark.asyncio
async def test_upsert_creates_profile_uses_provided_email(db_session: AsyncSession):
    user = await create_user(db_session, username="upsert-email@example.com")
    payload = _create_payload(email="john@example.com")
    resp, created = await service.upsert(payload, user, db_session)
    assert created is True
    assert resp.email == "john@example.com"


@pytest.mark.asyncio
async def test_upsert_updates_existing_profile(db_session: AsyncSession):
    user = await create_user(db_session, username="upsert-update@example.com")
    await service.upsert(_create_payload(first_name="John"), user, db_session)

    resp, created = await service.upsert(_create_payload(first_name="Jane"), user, db_session)
    assert created is False
    assert resp.first_name == "Jane"


@pytest.mark.asyncio
async def test_upsert_new_falls_back_to_username_email(db_session: AsyncSession):
    user = await create_user(db_session, username="once@example.com")
    payload = _create_payload(email=None)
    resp, created = await service.upsert(payload, user, db_session)
    assert created is True
    assert resp.email == "once@example.com"


# ── get_own ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_own_raises_404_when_missing(db_session: AsyncSession):
    user = await create_user(db_session, username="get-own-missing@example.com")
    with pytest.raises(HTTPException) as exc:
        await service.get_own(user, db_session)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_own_returns_profile(db_session: AsyncSession):
    user = await create_user(db_session, username="get-own@example.com")
    await service.upsert(_create_payload(), user, db_session)
    resp = await service.get_own(user, db_session)
    assert resp.profile_id.startswith("AXR-")
    assert resp.user_id == user.id


# ── update_own ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_own_raises_404_when_missing(db_session: AsyncSession):
    user = await create_user(db_session, username="update-own-missing@example.com")
    with pytest.raises(HTTPException) as exc:
        await service.update_own(UpdateUserDetailsRequest(first_name="X"), user, db_session)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_own_partial_update(db_session: AsyncSession):
    user = await create_user(db_session, username="update-own@example.com")
    await service.upsert(_create_payload(first_name="John"), user, db_session)

    resp = await service.update_own(
        UpdateUserDetailsRequest(last_name="Updated"), user, db_session
    )
    assert resp.last_name == "Updated"
    assert resp.first_name == "John"  # unchanged


# ── set_status_by_user_id ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_status_raises_404_when_missing(db_session: AsyncSession):
    with pytest.raises(HTTPException) as exc:
        await service.set_status_by_user_id(999999, "Suspended", db_session)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_set_status_raises_404_when_user_missing(db_session: AsyncSession):
    with pytest.raises(HTTPException) as exc:
        await service.set_status_by_user_id(123456, "Inactive", db_session)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_set_status_creates_skeleton_profile_when_user_has_none(db_session: AsyncSession):
    user = await create_user(db_session, username="no-profile-status@example.com")

    resp = await service.set_status_by_user_id(user.id, "Inactive", db_session)

    assert resp.user_id == user.id
    assert resp.profile_status == "Inactive"
    assert resp.mobile_number is None

    saved = await _get_by_user_id(db_session, user.id)
    assert saved is not None
    assert saved.profile_status == "Inactive"
    assert saved.email == user.username


@pytest.mark.asyncio
async def test_set_status_revisits_skeleton_profile_without_duplicate(db_session: AsyncSession):
    user = await create_user(db_session, username="revisit-skeleton@example.com")

    first = await service.set_status_by_user_id(user.id, "Suspended", db_session)
    second = await service.set_status_by_user_id(user.id, "Active", db_session)

    assert first.profile_id == second.profile_id
    assert second.profile_status == "Active"
    assert (_get_by_user_id(db_session, user.id) is not None)


@pytest.mark.asyncio
async def test_set_status_updates_profile(db_session: AsyncSession):
    user = await create_user(db_session, username="set-status@example.com")
    await service.upsert(_create_payload(), user, db_session)

    resp = await service.set_status_by_user_id(user.id, "Suspended", db_session)
    assert resp.profile_status == "Suspended"


# ── touch_last_login ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_touch_last_login_creates_profile_and_stamps_date(db_session: AsyncSession):
    user = await create_user(db_session, username="touch-create@example.com")
    await service.touch_last_login(user.id, db_session)

    record = await _get_by_user_id(db_session, user.id)
    assert record is not None
    assert record.profile_status == "Active"
    assert record.email == user.username
    assert record.last_login_date is not None


@pytest.mark.asyncio
async def test_touch_last_login_noop_for_missing_user(db_session: AsyncSession):
    await service.touch_last_login(999999, db_session)
    assert await _get_by_user_id(db_session, 999999) is None


@pytest.mark.asyncio
async def test_touch_last_login_sets_date(db_session: AsyncSession):
    user = await create_user(db_session, username="touch@example.com")
    await service.upsert(_create_payload(), user, db_session)

    record = await _get_by_user_id(db_session, user.id)
    assert record.last_login_date is None
    await service.touch_last_login(user.id, db_session)
    record = await _get_by_user_id(db_session, user.id)
    assert record.last_login_date is not None


# ── _get_by_user_id ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_by_user_id_returns_none_when_absent(db_session: AsyncSession):
    assert await _get_by_user_id(db_session, -1) is None
