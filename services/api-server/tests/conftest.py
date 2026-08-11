import os
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["DEEPSEEK_API_KEY"] = ""
os.environ["APP_ENV"] = "test"
os.environ["AUTH_JWT_SECRET"] = "test-harness-jwt-secret-32-characters-min"

from app.agents.model_gateway import ModelCircuitBreaker, ModelRateLimiter  # noqa: E402
from app.cache.query_cache import query_cache  # noqa: E402
from app.core.config import clear_runtime_settings  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.db.session import get_db_session  # noqa: E402
from app.main import app  # noqa: E402
from app.security.saml_rate_limit import reset_saml_rate_limiter  # noqa: E402

AUTH_HEADERS = {"Authorization": "Bearer dev-engineer-token"}


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    # Keep each test isolated while sharing one in-memory SQLite connection
    # across TestClient's worker thread and the test thread.
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
        engine.dispose()


@pytest.fixture(autouse=True)
def override_db_session(db_session: Session) -> Generator[None, None, None]:
    clear_runtime_settings()
    ModelCircuitBreaker.clear()
    ModelRateLimiter.clear()
    query_cache.clear_memory()
    query_cache._redis = None
    query_cache._redis_failed = True
    reset_saml_rate_limiter()

    def _get_db_session() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = _get_db_session
    try:
        yield
    finally:
        clear_runtime_settings()
        ModelCircuitBreaker.clear()
        ModelRateLimiter.clear()
        query_cache.clear_memory()
        query_cache._redis = None
        query_cache._redis_failed = True
        reset_saml_rate_limiter()
        app.dependency_overrides.clear()
