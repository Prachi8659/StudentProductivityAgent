"""
app/database/models.py
──────────────────────
SQLAlchemy ORM models (database table definitions).

Models
------
  - Task : one academic task the student needs to complete
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text
from app.database.database import Base


class Task(Base):
    """
    Represents one academic task a student needs to complete.

    Columns
    -------
    id              : auto-incrementing primary key
    title           : short name, e.g. "Write essay draft"
    description     : optional longer notes
    subject         : course/subject, e.g. "Mathematics"
    due_date        : deadline (datetime)
    priority        : "high" | "medium" | "low"  — set by agent or user
    estimated_hours : expected effort in hours
    status          : "pending" | "completed" | "overdue"
    is_completed    : kept for backward compat; True when status=="completed"
    created_at      : row creation timestamp
    updated_at      : last modification timestamp
    """

    __tablename__ = "tasks"

    id: int = Column(Integer, primary_key=True, index=True)
    title: str = Column(String(255), nullable=False)
    description: str = Column(Text, nullable=True, default="")
    subject: str = Column(String(100), nullable=True, default="")
    due_date: datetime = Column(DateTime, nullable=True)
    priority: str = Column(String(20), default="medium")       # high | medium | low
    estimated_hours: float = Column(Float, default=1.0)
    status: str = Column(String(20), default="pending")        # pending | completed | overdue
    is_completed: bool = Column(Boolean, default=False)        # derived from status
    created_at: datetime = Column(DateTime, default=datetime.utcnow)
    updated_at: datetime = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # ── convenience properties ────────────────────────────────────────────────

    @property
    def is_overdue(self) -> bool:
        """True if the task is past its due date and not yet completed."""
        if self.due_date is None or self.is_completed:
            return False
        return datetime.utcnow() > self.due_date

    def sync_status(self) -> None:
        """
        Keep `status` and `is_completed` in sync.
        Call this before committing any status change.
        """
        if self.is_completed:
            self.status = "completed"
        elif self.is_overdue:
            self.status = "overdue"
        else:
            self.status = "pending"

    def __repr__(self) -> str:
        return (
            f"<Task id={self.id} title='{self.title}' "
            f"priority='{self.priority}' status='{self.status}'>"
        )
