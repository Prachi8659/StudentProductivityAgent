"""
app/api/routes/tasks.py
───────────────────────
FastAPI router for task management endpoints.

Endpoints
---------
  POST   /tasks              → create a new task
  GET    /tasks              → list all pending tasks
  GET    /tasks/all          → list every task (pending + completed + overdue)
  GET    /tasks/completed    → list completed tasks
  GET    /tasks/overdue      → list overdue tasks
  GET    /tasks/{id}         → get one task by ID
  PATCH  /tasks/{id}         → update fields on a task
  POST   /tasks/{id}/complete → mark a task as done
  DELETE /tasks/{id}         → delete a task
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database import crud
from app.api.schemas import TaskCreate, TaskUpdate, TaskResponse

router = APIRouter(prefix="/tasks", tags=["Tasks"])


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    """Create and persist a new academic task."""
    task_data = payload.model_dump()
    return crud.create_task(db, task_data)


# ── Read ──────────────────────────────────────────────────────────────────────

@router.get("/all", response_model=list[TaskResponse])
def list_all_tasks(db: Session = Depends(get_db)):
    """Return every task (pending, completed, and overdue), ordered by due date."""
    return crud.get_all_tasks(db)


@router.get("/completed", response_model=list[TaskResponse])
def list_completed_tasks(db: Session = Depends(get_db)):
    """Return all completed tasks, most recently completed first."""
    return crud.get_completed_tasks(db)


@router.get("/overdue", response_model=list[TaskResponse])
def list_overdue_tasks(db: Session = Depends(get_db)):
    """Return tasks that are past their deadline and not yet completed."""
    return crud.get_overdue_tasks(db)


@router.get("/", response_model=list[TaskResponse])
def list_tasks(db: Session = Depends(get_db)):
    """Return all pending (incomplete) tasks, ordered by due date."""
    return crud.get_pending_tasks(db)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, db: Session = Depends(get_db)):
    """Return a single task by its ID."""
    task = crud.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


# ── Update ────────────────────────────────────────────────────────────────────

@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db)):
    """Partially update a task's fields."""
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided to update.")
    task = crud.update_task(db, task_id, updates)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@router.post("/{task_id}/complete", response_model=TaskResponse)
def complete_task(task_id: int, db: Session = Depends(get_db)):
    """Mark a task as completed."""
    task = crud.mark_task_complete(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    """Permanently delete a task."""
    deleted = crud.delete_task(db, task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found.")
