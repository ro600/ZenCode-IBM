"""
conftest.py — shared pytest fixtures for PRISM test suite.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db

TEST_DATABASE_URL = "sqlite:///./test_prism.db"


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(
        TEST_DATABASE_URL, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(db_engine):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = TestingSessionLocal()
    yield session
    session.close()


def _make_client(db_engine, raise_server_exceptions: bool = True):
    def override_get_db():
        TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


@pytest.fixture
def client(db_engine):
    with _make_client(db_engine) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client_no_raise(db_engine):
    """Client that returns 500 instead of re-raising server exceptions."""
    with _make_client(db_engine, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()
