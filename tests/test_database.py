"""
tests/test_database.py
──────────────────────
Unit tests for the database layer: Task model + all CRUD helpers.
Uses an in-memory SQLite database — never touches the real .db file.

Run:
    pytest tests/test_database.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.database import Base
from app.database import crud
from app.database.models import Task


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    """Fresh in-memory SQLite session for each test."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _task(**overrides) -> dict:
    """Minimal valid task dict with optional field overrides."""
    base = {
        "title": "Test Task",
        "subject": "Mathematics",
        "due_date": datetime.utcnow() + timedelta(days=3),
        "estimated_hours": 2.0,
        "priority": "medium",
        "description": "A test task.",
    }
    base.update(overrides)
    return base


# ── Task model ────────────────────────────────────────────────────────────────

def test_task_model_defaults(db):
    """A freshly created task should have sensible defaults."""
    task = crud.create_task(db, _task())
    assert task.id is not None
    assert task.status == "pending"
    assert task.is_completed is False
    assert task.created_at is not None
    assert task.updated_at is not None


def test_task_is_overdue_property(db):
    """is_overdue should be True when due_date is in the past and not completed."""
    past = datetime.utcnow() - timedelta(days=1)
    task = crud.create_task(db, _task(due_date=past))
    assert task.is_overdue is True


def test_task_is_not_overdue_when_completed(db):
    """A completed task should never be flagged as overdue."""
    past = datetime.utcnow() - timedelta(days=1)
    task = crud.create_task(db, _task(due_date=past))
    crud.mark_task_complete(db, task.id)
    db.refresh(task)
    assert task.is_overdue is False


def test_sync_status_sets_overdue(db):
    """sync_status() should set status='overdue' for past due pending tasks."""
    past = datetime.utcnow() - timedelta(days=2)
    task = Task(title="Late", due_date=past, estimated_hours=1.0)
    task.sync_status()
    assert task.status == "overdue"


def test_sync_status_sets_completed(db):
    """sync_status() should set status='completed' when is_completed is True."""
    task = Task(title="Done", estimated_hours=1.0, is_completed=True)
    task.sync_status()
    assert task.status == "completed"


# ── CRUD: Create ──────────────────────────────────────────────────────────────

def test_create_task_returns_with_id(db):
    task = crud.create_task(db, _task())
    assert task.id is not None
    assert task.title == "Test Task"


def test_create_task_priority_stored(db):
    task = crud.create_task(db, _task(priority="high"))
    assert task.priority == "high"


# ── CRUD: Read ────────────────────────────────────────────────────────────────

def test_get_task_by_id(db):
    created = crud.create_task(db, _task())
    fetched = crud.get_task(db, created.id)
    assert fetched is not None
    assert fetched.id == created.id


def test_get_task_not_found(db):
    assert crud.get_task(db, 9999) is None


def test_get_all_tasks_returns_all(db):
    crud.create_task(db, _task(title="A"))
    crud.create_task(db, _task(title="B"))
    assert len(crud.get_all_tasks(db)) == 2


def test_get_pending_excludes_completed(db):
    crud.create_task(db, _task(title="Pending"))
    done = crud.create_task(db, _task(title="Done"))
    crud.mark_task_complete(db, done.id)
    pending = crud.get_pending_tasks(db)
    titles = [t.title for t in pending]
    assert "Pending" in titles
    assert "Done" not in titles


def test_get_completed_tasks(db):
    t1 = crud.create_task(db, _task(title="Finish me"))
    crud.create_task(db, _task(title="Still pending"))
    crud.mark_task_complete(db, t1.id)
    completed = crud.get_completed_tasks(db)
    assert len(completed) == 1
    assert completed[0].title == "Finish me"


def test_get_overdue_tasks(db):
    past = datetime.utcnow() - timedelta(days=1)
    future = datetime.utcnow() + timedelta(days=5)
    crud.create_task(db, _task(title="Late", due_date=past))
    crud.create_task(db, _task(title="OnTime", due_date=future))
    overdue = crud.get_overdue_tasks(db)
    titles = [t.title for t in overdue]
    assert "Late" in titles
    assert "OnTime" not in titles


def test_get_overdue_excludes_completed(db):
    past = datetime.utcnow() - timedelta(days=1)
    t = crud.create_task(db, _task(due_date=past))
    crud.mark_task_complete(db, t.id)
    assert crud.get_overdue_tasks(db) == []


# ── CRUD: Update ──────────────────────────────────────────────────────────────

def test_update_task_fields(db):
    task = crud.create_task(db, _task())
    updated = crud.update_task(db, task.id, {"priority": "high", "title": "Updated"})
    assert updated.priority == "high"
    assert updated.title == "Updated"
    assert updated.subject == "Mathematics"   # unchanged


def test_update_task_not_found(db):
    assert crud.update_task(db, 9999, {"title": "X"}) is None


def test_mark_task_complete(db):
    task = crud.create_task(db, _task())
    result = crud.mark_task_complete(db, task.id)
    assert result.is_completed is True
    assert result.status == "completed"


def test_mark_task_complete_not_found(db):
    assert crud.mark_task_complete(db, 9999) is None


# ── CRUD: Delete ──────────────────────────────────────────────────────────────

def test_delete_task(db):
    task = crud.create_task(db, _task())
    assert crud.delete_task(db, task.id) is True
    assert crud.get_task(db, task.id) is None


def test_delete_task_not_found(db):
    assert crud.delete_task(db, 9999) is False


# ── CRUD: tasks_to_dicts ──────────────────────────────────────────────────────

def test_tasks_to_dicts_structure(db):
    crud.create_task(db, _task(title="Dict test"))
    tasks = crud.get_all_tasks(db)
    dicts = crud.tasks_to_dicts(tasks)
    assert len(dicts) == 1
    d = dicts[0]
    for key in ("id", "title", "subject", "due_date", "priority",
                "estimated_hours", "status", "is_completed", "is_overdue"):
        assert key in d, f"Missing key: {key}"


def test_tasks_to_dicts_due_date_is_iso_string(db):
    task = crud.create_task(db, _task())
    d = crud.tasks_to_dicts([task])[0]
    assert isinstance(d["due_date"], str)    # should be ISO string, not datetime
