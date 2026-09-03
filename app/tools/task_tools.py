"""
app/tools/task_tools.py
───────────────────────
LangChain @tool functions for managing student tasks.

These are the actions the LangGraph agent calls when it decides to
interact with the task database.  Each tool opens its own short-lived
database session so it can be called from any context (agent, tests, CLI).

Tools
─────
  add_task        — create and persist a new task
  list_tasks      — fetch and summarise all pending tasks
  get_task_by_id  — look up one task by numeric ID
  complete_task   — mark a task as done
  delete_task     — permanently remove a task
"""

from __future__ import annotations

from datetime import datetime

from langchain_core.tools import tool

from app.database.database import SessionLocal
from app.database import crud


# ── Session helper ────────────────────────────────────────────────────────────

def _get_session():
    """Open and return a new database session. Caller must close it."""
    return SessionLocal()


# ── Date parsing helper ───────────────────────────────────────────────────────

_DATE_FORMATS = [
    "%Y-%m-%d",           # 2026-09-05
    "%Y-%m-%dT%H:%M:%S",  # 2026-09-05T23:59:00
    "%d/%m/%Y",           # 05/09/2026
    "%d %B %Y",           # 05 September 2026
    "%B %d %Y",           # September 05 2026
    "%d %b %Y",           # 05 Sep 2026
]

# Map day names / relative words to offsets from today
_RELATIVE_DAYS = {
    "today": 0,
    "tomorrow": 1,
    "monday": None, "tuesday": None, "wednesday": None,
    "thursday": None, "friday": None, "saturday": None, "sunday": None,
}

_WEEKDAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _parse_due_date(raw: str) -> datetime | None:
    """
    Parse a due-date string into a datetime.

    Accepts ISO dates, common formats, day names (Monday, Friday …),
    and relative words (today, tomorrow).

    Returns None if parsing fails so the caller can decide what to do.
    """
    if not raw:
        return None

    clean = raw.strip()

    # ── Relative / day-name resolution ────────────────────────────────────────
    lower = clean.lower()
    now = datetime.utcnow()

    if lower == "today":
        return now.replace(hour=23, minute=59, second=0, microsecond=0)

    if lower == "tomorrow":
        from datetime import timedelta
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(hour=23, minute=59, second=0, microsecond=0)

    if lower in _WEEKDAY_MAP:
        from datetime import timedelta
        target_weekday = _WEEKDAY_MAP[lower]
        current_weekday = now.weekday()
        days_ahead = (target_weekday - current_weekday) % 7
        if days_ahead == 0:          # "next" occurrence if same day
            days_ahead = 7
        target = now + timedelta(days=days_ahead)
        return target.replace(hour=23, minute=59, second=0, microsecond=0)

    # ── Explicit format parsing ────────────────────────────────────────────────
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(clean, fmt)
        except ValueError:
            continue

    return None


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def add_task(
    title: str,
    subject: str,
    due_date: str,
    estimated_hours: float,
    priority: str = "medium",
    description: str = "",
) -> str:
    """
    Add a new academic task to the student's task list.

    Parameters
    ----------
    title           : short name, e.g. "Write essay draft"
    subject         : course or subject, e.g. "English Literature"
    due_date        : when it is due — ISO date (2026-09-10), day name
                      (Friday), or relative word (today, tomorrow)
    estimated_hours : expected effort in hours, e.g. 2.5
    priority        : "high", "medium", or "low" (default: "medium")
    description     : optional extra notes

    Returns a confirmation message with the assigned task ID.
    """
    # Validate priority
    priority = priority.lower().strip()
    if priority not in ("high", "medium", "low"):
        priority = "medium"

    # Parse due date
    due_dt = _parse_due_date(due_date)
    due_str = due_dt.strftime("%A, %d %b %Y") if due_dt else due_date

    db = _get_session()
    try:
        task = crud.create_task(db, {
            "title": title,
            "subject": subject,
            "due_date": due_dt,
            "estimated_hours": float(estimated_hours),
            "priority": priority,
            "description": description,
        })
        return (
            f"✅ Task added (ID #{task.id}): **{task.title}** — {task.subject}\n"
            f"   Due: {due_str} | Est: {task.estimated_hours:.1f}h | Priority: {task.priority}"
        )
    except Exception as exc:
        return f"❌ Failed to add task: {exc}"
    finally:
        db.close()


@tool
def list_tasks() -> str:
    """
    Retrieve all pending (incomplete) tasks from the database.

    Returns a formatted summary so the agent can reason about what the
    student still needs to do.  Overdue tasks are flagged clearly.
    """
    db = _get_session()
    try:
        tasks = crud.get_pending_tasks(db)
        if not tasks:
            return "📭 No pending tasks found. You're all caught up!"

        now = datetime.utcnow()
        lines = [f"📋 You have {len(tasks)} pending task(s):\n"]
        total_hours = 0.0

        for t in tasks:
            overdue_flag = ""
            due_str = "no deadline"
            if t.due_date:
                days_left = (t.due_date - now).days
                due_str = t.due_date.strftime("%a %d %b")
                if days_left < 0:
                    overdue_flag = " 🚨 OVERDUE"
                elif days_left == 0:
                    overdue_flag = " ⚡ DUE TODAY"
                elif days_left == 1:
                    overdue_flag = " ⚠️ DUE TOMORROW"

            icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(t.priority, "⚪")
            lines.append(
                f"  {icon} #{t.id} **{t.title}** ({t.subject or '—'})"
                f" | {t.estimated_hours:.1f}h | Due: {due_str}{overdue_flag}"
            )
            total_hours += t.estimated_hours or 0

        lines.append(f"\n⏱ Total estimated effort: {total_hours:.1f}h")
        return "\n".join(lines)
    except Exception as exc:
        return f"❌ Could not retrieve tasks: {exc}"
    finally:
        db.close()


@tool
def get_task_by_id(task_id: int) -> str:
    """
    Look up a single task by its numeric ID and return its details.

    Parameters
    ----------
    task_id : the integer ID shown in task listings (e.g. 3)
    """
    db = _get_session()
    try:
        task = crud.get_task(db, task_id)
        if task is None:
            return f"❌ No task found with ID #{task_id}."

        due_str = task.due_date.strftime("%A, %d %b %Y") if task.due_date else "no deadline"
        return (
            f"📌 Task #{task.id}: **{task.title}**\n"
            f"   Subject: {task.subject or '—'}\n"
            f"   Due: {due_str}\n"
            f"   Priority: {task.priority} | Est: {task.estimated_hours:.1f}h\n"
            f"   Status: {task.status}\n"
            f"   Notes: {task.description or '—'}"
        )
    except Exception as exc:
        return f"❌ Could not retrieve task #{task_id}: {exc}"
    finally:
        db.close()


@tool
def complete_task(task_id: int) -> str:
    """
    Mark a specific task as completed.

    Parameters
    ----------
    task_id : the integer ID of the task to mark complete
    """
    db = _get_session()
    try:
        task = crud.mark_task_complete(db, task_id)
        if task is None:
            return f"❌ No task found with ID #{task_id}."
        return (
            f"✅ Marked as complete: **{task.title}** (ID #{task.id})\n"
            f"   Well done! 🎉"
        )
    except Exception as exc:
        return f"❌ Could not complete task #{task_id}: {exc}"
    finally:
        db.close()


@tool
def delete_task(task_id: int) -> str:
    """
    Permanently delete a task from the database.

    Parameters
    ----------
    task_id : the integer ID of the task to delete
    """
    db = _get_session()
    try:
        # Fetch title before deleting for a friendlier confirmation
        task = crud.get_task(db, task_id)
        if task is None:
            return f"❌ No task found with ID #{task_id}."
        title = task.title
        crud.delete_task(db, task_id)
        return f"🗑️ Deleted task #{task_id}: **{title}**"
    except Exception as exc:
        return f"❌ Could not delete task #{task_id}: {exc}"
    finally:
        db.close()


# Convenience list — imported by app/tools/__init__.py
TASK_TOOLS = [add_task, list_tasks, get_task_by_id, complete_task, delete_task]
