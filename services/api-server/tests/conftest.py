import os
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

from app.agents.model_gateway import ModelCircuitBreaker, ModelRateLimiter  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.db.session import get_db_session  # noqa: E402
from app.main import app  # noqa: E402

AUTH_HEADERS = {"Authorization": "Bearer dev-engineer-token"}


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def override_db_session(db_session: Session) -> Generator[None, None, None]:
    ModelCircuitBreaker.clear()
    ModelRateLimiter.clear()

    def _get_db_session() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = _get_db_session
    try:
        yield
    finally:
        ModelCircuitBreaker.clear()
        ModelRateLimiter.clear()
        app.dependency_overrides.clear()
