"""
app/agent/prioritizer.py
────────────────────────
Deterministic task prioritization engine.

No LLM is involved here — priority is calculated from objective factors
so the ranking is consistent and explainable.

Scoring model (higher score = do this sooner)
─────────────────────────────────────────────
Factor                              Weight
──────────────────────────────────  ──────
Overdue                             +100
Explicit priority (high/med/low)    +30 / +20 / +10
Deadline urgency (days until due)   +40 → +0  (linear, 0-7 day window)
Effort (estimated_hours)            small penalty — high effort slightly
                                    deprioritised when time is scarce

The final numeric score is used only for sorting.
A human-readable reason is generated alongside each ranked task.

Public API
──────────
  score_task(task_dict, now) -> float
  rank_tasks(task_dicts, now) -> list[dict]          # sorted, score added
  explain_priority(ranked_task) -> str               # one-sentence reason
  build_priority_summary(task_dicts, available_hours) -> str   # full report
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


# ── Scoring constants ─────────────────────────────────────────────────────────

_SCORE_OVERDUE = 100
_SCORE_PRIORITY = {"high": 30, "medium": 20, "low": 10}
_URGENCY_WINDOW_DAYS = 7       # tasks due within this window get urgency points
_URGENCY_MAX_SCORE = 40        # max points for urgency
_EFFORT_PENALTY_PER_HOUR = 0.5 # small deduction per estimated hour


def _utcnow() -> datetime:
    """Return the current UTC time as a naive datetime (matches DB storage)."""
    return datetime.utcnow()


# ── Core scoring ──────────────────────────────────────────────────────────────

def score_task(task: dict[str, Any], now: datetime | None = None) -> float:
    """
    Return a numeric priority score for a single task dict.

    Higher score = higher priority = should be done sooner.

    Parameters
    ----------
    task : task dict as returned by crud.tasks_to_dicts()
    now  : reference datetime (defaults to utcnow; injectable for testing)
    """
    if now is None:
        now = _utcnow()

    score = 0.0

    # 1. Overdue bonus
    if task.get("is_overdue") or task.get("status") == "overdue":
        score += _SCORE_OVERDUE

    # 2. Explicit priority
    priority = (task.get("priority") or "medium").lower()
    score += _SCORE_PRIORITY.get(priority, _SCORE_PRIORITY["medium"])

    # 3. Deadline urgency
    due_date_raw = task.get("due_date")
    if due_date_raw:
        # due_date may be an ISO string (from tasks_to_dicts) or a datetime
        if isinstance(due_date_raw, str):
            try:
                due_dt = datetime.fromisoformat(due_date_raw)
            except ValueError:
                due_dt = None
        elif isinstance(due_date_raw, datetime):
            due_dt = due_date_raw
        else:
            due_dt = None

        if due_dt is not None:
            days_remaining = (due_dt - now).total_seconds() / 86_400
            if days_remaining < 0:
                # Already overdue — the overdue bonus covers this
                pass
            elif days_remaining <= _URGENCY_WINDOW_DAYS:
                # Linear scale: 0 days left → full urgency, 7 days → 0 urgency
                urgency_ratio = 1.0 - (days_remaining / _URGENCY_WINDOW_DAYS)
                score += urgency_ratio * _URGENCY_MAX_SCORE

    # 4. Effort penalty (large tasks slightly deprioritised under time pressure)
    hours = float(task.get("estimated_hours") or 1.0)
    score -= hours * _EFFORT_PENALTY_PER_HOUR

    return round(score, 2)


# ── Ranking ───────────────────────────────────────────────────────────────────

def rank_tasks(
    tasks: list[dict[str, Any]],
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """
    Return the same task dicts sorted by descending priority score.
    Each dict gets a '_score' key added for transparency.

    Only non-completed tasks are ranked (completed tasks are excluded).
    """
    if now is None:
        now = _utcnow()

    pending = [t for t in tasks if not t.get("is_completed", False)]

    for task in pending:
        task["_score"] = score_task(task, now)

    return sorted(pending, key=lambda t: t["_score"], reverse=True)


# ── Human-readable explanation ────────────────────────────────────────────────

def explain_priority(task: dict[str, Any], now: datetime | None = None) -> str:
    """
    Return a one-sentence explanation of why a task has its priority.

    Examples
    --------
    "This task is overdue — it was due 2 days ago."
    "Due in 1 day with high priority."
    "Due in 3 days and estimated to take 4 hours."
    """
    if now is None:
        now = _utcnow()

    reasons = []

    # Overdue
    if task.get("is_overdue") or task.get("status") == "overdue":
        due_date_raw = task.get("due_date")
        days_ago = ""
        if due_date_raw:
            try:
                due_dt = datetime.fromisoformat(due_date_raw) if isinstance(due_date_raw, str) else due_date_raw
                delta = int((now - due_dt).total_seconds() / 86_400)
                days_ago = f" — it was due {delta} day{'s' if delta != 1 else ''} ago"
            except (ValueError, TypeError):
                pass
        return f"This task is overdue{days_ago}."

    # Deadline proximity
    due_date_raw = task.get("due_date")
    if due_date_raw:
        try:
            due_dt = datetime.fromisoformat(due_date_raw) if isinstance(due_date_raw, str) else due_date_raw
            days_left = (due_dt - now).total_seconds() / 86_400
            if days_left < 1:
                reasons.append("due today")
            elif days_left < 2:
                reasons.append("due tomorrow")
            else:
                reasons.append(f"due in {int(days_left)} days")
        except (ValueError, TypeError):
            pass

    # Priority label
    priority = (task.get("priority") or "medium").lower()
    if priority == "high":
        reasons.append("marked high priority")

    # Effort
    hours = float(task.get("estimated_hours") or 1.0)
    if hours >= 3:
        reasons.append(f"estimated {hours:.0f} hours of effort")

    if not reasons:
        return "This task is next in the queue."

    return " and ".join(reasons).capitalize() + "."


# ── Full priority report ──────────────────────────────────────────────────────

def build_priority_summary(
    tasks: list[dict[str, Any]],
    available_hours: float = 0.0,
    now: datetime | None = None,
) -> str:
    """
    Build a complete, human-readable priority report for all pending tasks.

    Parameters
    ----------
    tasks           : list of task dicts (may include completed — they are filtered)
    available_hours : student's available study hours (used for time-pressure note)
    now             : reference datetime (defaults to utcnow)

    Returns
    -------
    A multi-line string ready to be returned to the student.
    """
    if now is None:
        now = _utcnow()

    ranked = rank_tasks(tasks, now)

    if not ranked:
        return "✅ You have no pending tasks right now. Great work!"

    total_hours = sum(float(t.get("estimated_hours") or 1.0) for t in ranked)

    lines = ["📋 **Your tasks, ranked by priority:**\n"]

    for i, task in enumerate(ranked, start=1):
        title = task.get("title", "Untitled")
        subject = task.get("subject", "")
        subject_str = f" ({subject})" if subject else ""
        hours = float(task.get("estimated_hours") or 1.0)
        due_raw = task.get("due_date")
        due_str = ""
        if due_raw:
            try:
                due_dt = datetime.fromisoformat(due_raw) if isinstance(due_raw, str) else due_raw
                due_str = f", due {due_dt.strftime('%a %d %b')}"
            except (ValueError, TypeError):
                pass

        status_icon = "🔴" if task.get("status") == "overdue" else (
            "🔴" if task.get("priority") == "high" else
            "🟡" if task.get("priority") == "medium" else "🟢"
        )
        reason = explain_priority(task, now)
        lines.append(
            f"{i}. {status_icon} **{title}**{subject_str} — {hours:.1f}h{due_str}\n"
            f"   _{reason}_\n"
        )

    # Time pressure note
    if available_hours > 0:
        if total_hours > available_hours:
            deficit = total_hours - available_hours
            lines.append(
                f"\n⚠️ You have **{total_hours:.1f}h** of pending work but only "
                f"**{available_hours:.1f}h** available. "
                f"Focus on the top tasks — {deficit:.1f}h will need to carry over."
            )
        else:
            lines.append(
                f"\n✅ Total pending work ({total_hours:.1f}h) fits within your "
                f"available time ({available_hours:.1f}h)."
            )

    return "\n".join(lines)
