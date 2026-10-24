import os

# Must be set before the app is imported.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["REDIS_ENABLED"] = "false"
os.environ["SECRET_KEY"] = "test-secret-key-with-enough-length-1234567890"

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import cache
from app.config import settings
from app.database import Base, get_db
from app.enums import Role
from app.main import app
from app.models import User
from app.security import hash_password


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def redis_on(monkeypatch):
    """Turn caching and rate limiting on, backed by an in-memory fake Redis."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(settings, "redis_enabled", True)
    monkeypatch.setattr(cache, "_client", fake)
    yield fake
    fake.flushall()


def make_user(db, email, role=Role.AGENT, password="password123"):
    user = User(email=email, full_name=email.split("@")[0], hashed_password=hash_password(password), role=role.value)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login(client, email, password="password123"):
    res = client.post("/auth/login", data={"username": email, "password": password})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture()
def agent(db_session, client):
    user = make_user(db_session, "agent1@example.com")
    return user, login(client, user.email)


@pytest.fixture()
def agent2(db_session, client):
    user = make_user(db_session, "agent2@example.com")
    return user, login(client, user.email)


@pytest.fixture()
def admin(db_session, client):
    user = make_user(db_session, "admin@example.com", Role.ADMIN)
    return user, login(client, user.email)


def new_lead(client, headers, **overrides):
    payload = {"name": "Asha Rao", "email": "asha@acme.com", "company": "Acme", "source": "website"}
    payload.update(overrides)
    res = client.post("/leads", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()
