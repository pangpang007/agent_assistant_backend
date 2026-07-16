import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.base import Base
from app.models.team import Team
from app.models.user import User

TEST_DATABASE_URL = settings.database_url.replace("tangyuan_db", "tangyuan_test")


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        from app.core.seed import seed_preset_data

        await seed_preset_data(session)
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        email="test@example.com",
        username="testuser",
        password_hash=hash_password("TestPass123"),
        account_type="personal",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def team_owner(db_session: AsyncSession) -> User:
    user = User(
        email="owner@example.com",
        username="teamowner",
        password_hash=hash_password("TestPass123"),
        account_type="team",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    team = Team(
        name="Test Team",
        owner_id=user.id,
        invite_code="ABC123",
    )
    db_session.add(team)
    await db_session.commit()
    await db_session.refresh(team)

    user.team_id = team.id
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(test_user: User) -> dict:
    token, _ = create_access_token(
        user_id=str(test_user.id),
        email=test_user.email,
        account_type=test_user.account_type,
        team_id=None,
        username=test_user.username,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def owner_headers(team_owner: User) -> dict:
    token, _ = create_access_token(
        user_id=str(team_owner.id),
        email=team_owner.email,
        account_type=team_owner.account_type,
        team_id=str(team_owner.team_id),
        username=team_owner.username,
    )
    return {"Authorization": f"Bearer {token}"}
