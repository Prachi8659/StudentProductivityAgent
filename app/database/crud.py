"""
app/database/crud.py
────────────────────
CRUD helper functions — thin wrappers around SQLAlchemy queries.

Every database interaction in the application goes through these
functions so no module ever writes raw ORM queries directly.
"""

from datetime import datetime
from sqlalchemy.orm import Session
from app.database.models import Task


# ── helpers ───────────────────────────────────────────────────────────────────

def _refresh_status(db: Session, task: Task) -> Task:
    """
    Re-evaluate and persist the status field, then return the task.
    Called after any change that could affect overdue state.
    """
    task.sync_status()
    task.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(task)
    return task


# ── Create ────────────────────────────────────────────────────────────────────

def create_task(db: Session, task_data: dict) -> Task:
    """
    Insert a new Task row and return the created object.
    Accepts the same field names as the Task model.
    """
    # Ensure is_completed and status are consistent from the start
    task_data.setdefault("status", "pending")
    task_data.setdefault("is_completed", False)
    task = Task(**task_data)
    task.sync_status()
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


# ── Read ──────────────────────────────────────────────────────────────────────

def get_task(db: Session, task_id: int) -> Task | None:
    """Return a single Task by primary key, or None if not found."""
    return db.query(Task).filter(Task.id == task_id).first()


def get_all_tasks(db: Session) -> list[Task]:
    """Return every task ordered by due_date (earliest first, nulls last)."""
    return (
        db.query(Task)
        .order_by(Task.due_date.asc().nullslast())
        .all()
    )


def get_pending_tasks(db: Session) -> list[Task]:
    """Return tasks that are not completed, ordered by due_date."""
    return (
        db.query(Task)
        .filter(Task.is_completed == False)  # noqa: E712
        .order_by(Task.due_date.asc().nullslast())
        .all()
    )


def get_completed_tasks(db: Session) -> list[Task]:
    """Return only completed tasks, most recently updated first."""
    return (
        db.query(Task)
        .filter(Task.is_completed == True)  # noqa: E712
        .order_by(Task.updated_at.desc())
        .all()
    )


def get_overdue_tasks(db: Session) -> list[Task]:
    """
    Return tasks whose due_date is in the past and that are not completed.
    Also updates their status to 'overdue' in the database.
    """
    now = datetime.utcnow()
    tasks = (
        db.query(Task)
        .filter(Task.is_completed == False, Task.due_date < now)  # noqa: E712
        .order_by(Task.due_date.asc())
        .all()
    )
    for task in tasks:
        if task.status != "overdue":
            task.status = "overdue"
    if tasks:
        db.commit()
    return tasks


# ── Update ────────────────────────────────────────────────────────────────────

def update_task(db: Session, task_id: int, updates: dict) -> Task | None:
    """
    Apply a dict of field updates to an existing Task.
    Automatically re-syncs status after the update.
    """
    task = get_task(db, task_id)
    if task is None:
        return None
    for field, value in updates.items():
        setattr(task, field, value)
    return _refresh_status(db, task)


def mark_task_complete(db: Session, task_id: int) -> Task | None:
    """Mark a task as completed and update its status."""
    task = get_task(db, task_id)
    if task is None:
        return None
    task.is_completed = True
    task.status = "completed"
    task.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(task)
    return task


# ── Delete ────────────────────────────────────────────────────────────────────

def delete_task(db: Session, task_id: int) -> bool:
    """Delete a task by ID. Returns True if deleted, False if not found."""
    task = get_task(db, task_id)
    if task is None:
        return False
    db.delete(task)
    db.commit()
    return True


# ── Utility ───────────────────────────────────────────────────────────────────

def tasks_to_dicts(tasks: list[Task]) -> list[dict]:
    """
    Convert a list of Task ORM objects to plain dicts the agent can read.
    Avoids passing SQLAlchemy objects outside the database layer.
    """
    result = []
    for t in tasks:
        result.append({
            "id": t.id,
            "title": t.title,
            "subject": t.subject or "",
            "description": t.description or "",
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "priority": t.priority,
            "estimated_hours": t.estimated_hours,
            "status": t.status,
            "is_completed": t.is_completed,
            "is_overdue": t.is_overdue,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        })
    return result
