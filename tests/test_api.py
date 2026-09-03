"""
tests/test_api.py
──────────────────
Integration tests for all FastAPI routes.
Uses TestClient + shared in-memory SQLite (StaticPool) so every thread
sees the same database tables.

Run:
    pytest tests/test_api.py -v
"""

import pytest
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.api.app import create_app
from app.database.database import Base, get_db


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """
    TestClient wired to a shared in-memory SQLite database.

    StaticPool makes all connections (including FastAPI's thread-pool
    connections) share the same in-memory DB, so tables created by
    create_all() are visible to every session in the test.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    @asynccontextmanager
    async def noop_lifespan(app):
        yield   # skip init_db() so the real .db file is never touched

    app = create_app(lifespan=noop_lifespan)
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c

    Base.metadata.drop_all(bind=engine)


# ── Payload helper ────────────────────────────────────────────────────────────

def _payload(**overrides) -> dict:
    """Return a valid task creation payload."""
    future = (datetime.utcnow() + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")
    base = {
        "title": "API Test Task",
        "subject": "Physics",
        "due_date": future,
        "estimated_hours": 3.0,
        "priority": "medium",
        "description": "",
    }
    base.update(overrides)
    return base


# ── Health ────────────────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ── Task creation ─────────────────────────────────────────────────────────────

def test_create_task_returns_201(client):
    r = client.post("/tasks/", json=_payload())
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "API Test Task"
    assert data["is_completed"] is False
    assert data["status"] == "pending"
    assert "id" in data
    assert "updated_at" in data


def test_create_task_missing_title_returns_422(client):
    payload = _payload()
    del payload["title"]
    r = client.post("/tasks/", json=payload)
    assert r.status_code == 422


def test_create_task_invalid_priority_returns_422(client):
    r = client.post("/tasks/", json=_payload(priority="urgent"))
    assert r.status_code == 422


# ── Task listing ──────────────────────────────────────────────────────────────

def test_list_pending_tasks(client):
    client.post("/tasks/", json=_payload(title="P1"))
    client.post("/tasks/", json=_payload(title="P2"))
    r = client.get("/tasks/")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_list_all_tasks_includes_completed(client):
    t = client.post("/tasks/", json=_payload()).json()
    client.post(f"/tasks/{t['id']}/complete")
    r = client.get("/tasks/all")
    assert r.status_code == 200
    assert len(r.json()) == 1    # completed task visible in /all


def test_list_completed_tasks(client):
    t = client.post("/tasks/", json=_payload()).json()
    client.post(f"/tasks/{t['id']}/complete")
    r = client.get("/tasks/completed")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["is_completed"] is True


def test_list_overdue_tasks(client):
    past = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    client.post("/tasks/", json=_payload(due_date=past))
    r = client.get("/tasks/overdue")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_list_overdue_excludes_completed(client):
    past = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    t = client.post("/tasks/", json=_payload(due_date=past)).json()
    client.post(f"/tasks/{t['id']}/complete")
    r = client.get("/tasks/overdue")
    assert r.json() == []


# ── Single task ───────────────────────────────────────────────────────────────

def test_get_task_by_id(client):
    created = client.post("/tasks/", json=_payload()).json()
    r = client.get(f"/tasks/{created['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_get_task_not_found(client):
    assert client.get("/tasks/9999").status_code == 404


# ── Update ────────────────────────────────────────────────────────────────────

def test_patch_task_fields(client):
    created = client.post("/tasks/", json=_payload()).json()
    r = client.patch(f"/tasks/{created['id']}", json={"priority": "high", "title": "Updated"})
    assert r.status_code == 200
    data = r.json()
    assert data["priority"] == "high"
    assert data["title"] == "Updated"


def test_patch_task_not_found(client):
    assert client.patch("/tasks/9999", json={"title": "X"}).status_code == 404


def test_patch_task_no_fields_returns_400(client):
    created = client.post("/tasks/", json=_payload()).json()
    r = client.patch(f"/tasks/{created['id']}", json={})
    assert r.status_code == 400


# ── Complete ──────────────────────────────────────────────────────────────────

def test_complete_task(client):
    created = client.post("/tasks/", json=_payload()).json()
    r = client.post(f"/tasks/{created['id']}/complete")
    assert r.status_code == 200
    assert r.json()["is_completed"] is True
    assert r.json()["status"] == "completed"


def test_complete_task_not_found(client):
    assert client.post("/tasks/9999/complete").status_code == 404


def test_completed_task_absent_from_pending_list(client):
    created = client.post("/tasks/", json=_payload()).json()
    client.post(f"/tasks/{created['id']}/complete")
    pending = client.get("/tasks/").json()
    ids = [t["id"] for t in pending]
    assert created["id"] not in ids


# ── Delete ────────────────────────────────────────────────────────────────────

def test_delete_task(client):
    created = client.post("/tasks/", json=_payload()).json()
    r = client.delete(f"/tasks/{created['id']}")
    assert r.status_code == 204
    assert client.get(f"/tasks/{created['id']}").status_code == 404


def test_delete_task_not_found(client):
    assert client.delete("/tasks/9999").status_code == 404


# ── Agent endpoint ────────────────────────────────────────────────────────────

def test_agent_chat_no_llm_key_returns_503(client, monkeypatch):
    """
    When no LLM API key is configured the endpoint should return 503
    with a helpful message — not a traceback.
    """
    import app.api.routes.agent as agent_module
    monkeypatch.setattr(agent_module, "OPENAI_API_KEY", "")
    monkeypatch.setattr(agent_module, "LLM_PROVIDER", "openai")
    r = client.post("/agent/chat", json={"message": "Hello", "available_hours": 2.0})
    assert r.status_code == 503
    assert "OPENAI_API_KEY" in r.json()["detail"]


def test_agent_chat_endpoint_exists(client):
    """The /agent/chat endpoint must exist (not 404/405).
    A 200 means the agent responded, 503 means missing config,
    500 means the agent encountered a runtime error (e.g. LLM call failed
    in the test environment) — all three confirm the endpoint is wired up."""
    r = client.post("/agent/chat", json={"message": "Hello", "available_hours": 2.0})
    assert r.status_code not in (404, 405), (
        f"Endpoint returned {r.status_code} — route is not registered"
    )


def test_agent_chat_invalid_payload_returns_422(client):
    """Sending an empty message must fail validation."""
    r = client.post("/agent/chat", json={"message": "", "available_hours": 2.0})
    assert r.status_code == 422
