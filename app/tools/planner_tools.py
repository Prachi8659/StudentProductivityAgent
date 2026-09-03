"""
app/tools/planner_tools.py
──────────────────────────
LangChain @tool functions for study planning and re-planning.

These tools give the agent the ability to reason about *how* a student
should spend their available study time.  All scheduling logic is
deterministic — no LLM is involved in the calculations.

Scheduling algorithm
────────────────────
1. Fetch all pending tasks from the database.
2. Rank them using the prioritizer (deadline + priority + effort).
3. Walk through the ranked list and assign work to time slots.
4. Each day has `available_hours` of capacity.
5. If a task is larger than a single day's capacity it is split across days.
6. Stop scheduling when all tasks are placed or we run out of days
   (MAX_PLAN_DAYS).
7. Any tasks that don't fit are reported as "overflow".

Tools
─────
  prioritize_tasks  — rank pending tasks and explain the ordering
  create_study_plan — generate a day-by-day study schedule
  replan            — regenerate the plan after circumstances change
"""

from __future__ import annotations

from datetime import datetime, timedelta

from langchain_core.tools import tool

from app.database.database import SessionLocal
from app.database import crud
from app.agent.prioritizer import rank_tasks, build_priority_summary, explain_priority

# Maximum number of days the planner will schedule into the future
MAX_PLAN_DAYS = 14


# ── Session helper ────────────────────────────────────────────────────────────

def _get_session():
    return SessionLocal()


# ── Core scheduling function ──────────────────────────────────────────────────

def _build_schedule(
    available_hours_per_day: float,
    start_date: datetime | None = None,
    context_note: str = "",
) -> str:
    """
    Internal scheduler — called by both create_study_plan and replan.

    Returns a formatted multi-line study plan string.
    """
    if start_date is None:
        start_date = datetime.utcnow()

    # Normalise to the start of the given day
    today = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

    db = _get_session()
    try:
        pending = crud.get_pending_tasks(db)
        task_dicts = crud.tasks_to_dicts(pending)
    finally:
        db.close()

    if not task_dicts:
        return "✅ No pending tasks to schedule — you're all caught up!"

    ranked = rank_tasks(task_dicts, now=today)
    total_work_hours = sum(float(t.get("estimated_hours") or 1.0) for t in ranked)

    # ── Slot allocation ────────────────────────────────────────────────────────
    # day_plan: {day_offset: [(task_title, subject, hours_allocated)]}
    day_plan: dict[int, list[tuple[str, str, float]]] = {}
    overflow: list[dict] = []

    for task in ranked:
        remaining = float(task.get("estimated_hours") or 1.0)
        day = 0

        while remaining > 0 and day < MAX_PLAN_DAYS:
            # How much capacity is left on this day?
            used = sum(h for _, _, h in day_plan.get(day, []))
            free = available_hours_per_day - used

            if free <= 0:
                day += 1
                continue

            # Respect due-date: don't schedule past the deadline
            due_raw = task.get("due_date")
            if due_raw:
                try:
                    due_dt = datetime.fromisoformat(due_raw) if isinstance(due_raw, str) else due_raw
                    due_day_offset = (due_dt.date() - today.date()).days
                    if day > due_day_offset:
                        # Can't fit before deadline — mark overflow and move on
                        overflow.append(task)
                        break
                except (ValueError, TypeError):
                    pass

            allocate = min(remaining, free)
            if day not in day_plan:
                day_plan[day] = []
            day_plan[day].append((
                task.get("title", "Task"),
                task.get("subject", ""),
                allocate,
            ))
            remaining -= allocate

            if remaining > 0:
                day += 1     # spill to next day

        else:
            if remaining > 0:
                overflow.append(task)

    # ── Format output ──────────────────────────────────────────────────────────
    lines = []

    if context_note:
        lines.append(f"🔄 {context_note}\n")

    lines.append(
        f"📅 **Study Plan** — {available_hours_per_day:.1f}h/day "
        f"starting {today.strftime('%A, %d %b %Y')}\n"
    )

    if not day_plan:
        lines.append("⚠️ No tasks could be scheduled within your available time.")
    else:
        for day_offset in sorted(day_plan.keys()):
            date = today + timedelta(days=day_offset)
            sessions = day_plan[day_offset]
            day_total = sum(h for _, _, h in sessions)
            lines.append(f"**{date.strftime('%A, %d %b')}** ({day_total:.1f}h)")
            for title, subject, hours in sessions:
                subj_str = f" [{subject}]" if subject else ""
                lines.append(f"  • {title}{subj_str} — {hours:.1f}h")
            lines.append("")   # blank line between days

    # Time summary
    if total_work_hours <= available_hours_per_day * MAX_PLAN_DAYS:
        lines.append(f"⏱ Total work: {total_work_hours:.1f}h across {len(day_plan)} day(s).")
    else:
        lines.append(
            f"⏱ Total work: {total_work_hours:.1f}h — "
            f"more than {MAX_PLAN_DAYS} days of {available_hours_per_day:.1f}h capacity."
        )

    # Overflow warning
    if overflow:
        overflow_titles = ", ".join(f"**{t.get('title', 'Task')}**" for t in overflow)
        lines.append(
            f"\n⚠️ The following task(s) could not be fully scheduled before their "
            f"deadline or within {MAX_PLAN_DAYS} days: {overflow_titles}. "
            "Consider negotiating deadlines or increasing available hours."
        )

    return "\n".join(lines)


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def prioritize_tasks(available_hours_per_day: float) -> str:
    """
    Analyse all pending tasks and rank them by priority.

    Takes into account:
    - Whether the task is overdue
    - Deadline proximity (tasks due sooner score higher)
    - Explicit priority (high / medium / low)
    - Estimated effort (very large tasks slightly deprioritised)

    Parameters
    ----------
    available_hours_per_day : how many hours per day the student can study

    Returns a prioritised list with a brief reason for each task's ranking.
    """
    db = _get_session()
    try:
        pending = crud.get_pending_tasks(db)
        task_dicts = crud.tasks_to_dicts(pending)
    finally:
        db.close()

    return build_priority_summary(task_dicts, available_hours=available_hours_per_day)


@tool
def create_study_plan(available_hours_per_day: float) -> str:
    """
    Build a concrete day-by-day study schedule for all pending tasks.

    The plan:
    - Starts from today
    - Assigns tasks to days in priority order
    - Respects the student's daily available hours
    - Splits large tasks across multiple days when needed
    - Warns if any task cannot be completed before its deadline

    Parameters
    ----------
    available_hours_per_day : how many hours per day the student can study

    Returns the full study plan as a formatted string.
    """
    if available_hours_per_day <= 0:
        return "❌ Please provide a positive number of available study hours per day."

    try:
        return _build_schedule(available_hours_per_day)
    except Exception as exc:
        return f"❌ Could not generate study plan: {exc}"


@tool
def replan(new_available_hours_per_day: float, reason: str = "") -> str:
    """
    Regenerate the study plan after the student's schedule changes.

    Call this when the student says they have more or less time than before,
    a task ran over, or a deadline has shifted.

    Parameters
    ----------
    new_available_hours_per_day : the student's updated daily study hours
    reason                      : optional explanation shown at the top of
                                  the plan, e.g. "couldn't finish Python assignment"

    Returns the updated study plan as a formatted string.
    """
    if new_available_hours_per_day <= 0:
        return "❌ Please provide a positive number of available study hours per day."

    context = f"Plan updated ({reason})" if reason else "Plan updated with new schedule"

    try:
        return _build_schedule(new_available_hours_per_day, context_note=context)
    except Exception as exc:
        return f"❌ Could not regenerate study plan: {exc}"


# Convenience list — imported by app/tools/__init__.py
PLANNER_TOOLS = [prioritize_tasks, create_study_plan, replan]
