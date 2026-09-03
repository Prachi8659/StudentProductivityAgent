"""
app/api/schemas.py
──────────────────
Pydantic v2 schemas for request and response validation.
"""

from datetime import datetime
from pydantic import BaseModel, Field


# ── Task schemas ──────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    """Body expected when creating a new task (POST /tasks)."""
    title: str = Field(..., min_length=1, max_length=255)
    subject: str = Field(default="", max_length=100)
    due_date: datetime
    estimated_hours: float = Field(..., gt=0)
    priority: str = Field(default="medium", pattern="^(high|medium|low)$")
    description: str = Field(default="")


class TaskUpdate(BaseModel):
    """Body for partially updating an existing task (PATCH /tasks/{id})."""
    title: str | None = Field(default=None, max_length=255)
    subject: str | None = Field(default=None, max_length=100)
    due_date: datetime | None = None
    estimated_hours: float | None = Field(default=None, gt=0)
    priority: str | None = Field(default=None, pattern="^(high|medium|low)$")
    description: str | None = None
    is_completed: bool | None = None
    status: str | None = Field(default=None, pattern="^(pending|completed|overdue)$")


class TaskResponse(BaseModel):
    """Shape of a task object returned by the API."""
    id: int
    title: str
    subject: str | None
    due_date: datetime | None
    estimated_hours: float
    priority: str
    description: str | None
    status: str
    is_completed: bool
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Agent / chat schemas ──────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """Body expected when sending a message to the agent (POST /agent/chat)."""
    message: str = Field(..., min_length=1)
    available_hours: float = Field(default=2.0, gt=0)


class ChatResponse(BaseModel):
    """Response returned after the agent processes a message."""
    reply: str
    error: str | None = None
