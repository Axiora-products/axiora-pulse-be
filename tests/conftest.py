import os
import pytest
import pytest_asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from httpx import AsyncClient, ASGITransport

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://test:test@localhost:5432/axiora_test",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
os.environ.setdefault("OTP_EXPIRE_MINUTES", "10")

from app.db.models import Base, User
from app.core.security import hash_password_async
from main import app
from app.db.database import get_db
from app.core.dependencies import get_current_user
from app.core.limiter import limiter

# Disable rate limiting during tests
limiter.enabled = False

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

@pytest_asyncio.fixture
async def test_engine():
    # Prefer a PostgreSQL test database when TEST_DATABASE_URL is provided.
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    async_session = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session
        # Clear out tables after each test to ensure test isolation
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()

@pytest_asyncio.fixture
async def normal_user(db_session: AsyncSession) -> User:
    user = User(
        username="user@axiorapulse.com",
        password=await hash_password_async("Test@12345"),
        role="user",
        register_mfa=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    user = User(
        username="admin@axiorapulse.com",
        password=await hash_password_async("Test@12345"),
        role="admin",
        register_mfa=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    # Set default database override
    async def _override_get_db():
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_db] = _override_get_db
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
        
    # Clean up overrides
    app.dependency_overrides.clear()
