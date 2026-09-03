"""
tests/test_prioritizer.py
──────────────────────────
Unit tests for the deterministic prioritization engine.
No database, no LLM required — all pure-function tests.

Run:
    pytest tests/test_prioritizer.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.agent.prioritizer import (
    score_task,
    rank_tasks,
    explain_priority,
    build_priority_summary,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime(2026, 9, 3, 12, 0, 0)   # fixed reference time for tests


def _task(**overrides) -> dict:
    base = {
        "id": 1,
        "title": "Test Task",
        "subject": "Science",
        "due_date": (_now() + timedelta(days=5)).isoformat(),
        "priority": "medium",
        "estimated_hours": 2.0,
        "status": "pending",
        "is_completed": False,
        "is_overdue": False,
    }
    base.update(overrides)
    return base


# ── score_task ────────────────────────────────────────────────────────────────

def test_overdue_task_scores_highest():
    """An overdue task must outscore any non-overdue task."""
    overdue = _task(is_overdue=True, status="overdue", due_date=(_now() - timedelta(days=1)).isoformat())
    normal  = _task(priority="high", due_date=(_now() + timedelta(days=1)).isoformat())
    assert score_task(overdue, _now()) > score_task(normal, _now())


def test_high_priority_beats_low():
    """High-priority task should score more than a low-priority task with the same deadline."""
    high = _task(priority="high")
    low  = _task(priority="low")
    assert score_task(high, _now()) > score_task(low, _now())


def test_imminent_deadline_adds_urgency():
    """Task due tomorrow should score higher than same task due in 10 days."""
    soon = _task(due_date=(_now() + timedelta(days=1)).isoformat())
    late = _task(due_date=(_now() + timedelta(days=10)).isoformat())
    assert score_task(soon, _now()) > score_task(late, _now())


def test_large_effort_reduces_score():
    """A 10-hour task should score lower than a 1-hour task with the same deadline/priority."""
    big   = _task(estimated_hours=10.0)
    small = _task(estimated_hours=1.0)
    assert score_task(small, _now()) > score_task(big, _now())


def test_no_due_date_scores_priority_only():
    """Task without a due date should still score based on priority."""
    t = _task(due_date=None)
    s = score_task(t, _now())
    assert s > 0


def test_score_returns_float():
    """score_task must return a float (or int coercible to float)."""
    s = score_task(_task(), _now())
    assert isinstance(s, (int, float))


# ── rank_tasks ────────────────────────────────────────────────────────────────

def test_rank_tasks_order():
    """Ranked list should be sorted descending by score."""
    tasks = [
        _task(id=1, priority="low",  due_date=(_now() + timedelta(days=6)).isoformat()),
        _task(id=2, priority="high", due_date=(_now() + timedelta(days=1)).isoformat()),
        _task(id=3, priority="medium", due_date=(_now() + timedelta(days=3)).isoformat()),
    ]
    ranked = rank_tasks(tasks, _now())
    scores = [t["_score"] for t in ranked]
    assert scores == sorted(scores, reverse=True)


def test_rank_tasks_excludes_completed():
    """Completed tasks must not appear in the ranked list."""
    tasks = [
        _task(id=1, is_completed=False),
        _task(id=2, is_completed=True),
    ]
    ranked = rank_tasks(tasks, _now())
    ids = [t["id"] for t in ranked]
    assert 2 not in ids


def test_rank_tasks_adds_score_key():
    """Each ranked task dict must have a '_score' key added."""
    tasks = [_task()]
    ranked = rank_tasks(tasks, _now())
    assert "_score" in ranked[0]


def test_rank_tasks_empty_list():
    """rank_tasks should return an empty list when given no tasks."""
    assert rank_tasks([], _now()) == []


def test_rank_tasks_overdue_first():
    """An overdue task must appear at the top of the ranked list."""
    tasks = [
        _task(id=1, priority="high", due_date=(_now() + timedelta(days=1)).isoformat()),
        _task(id=2, is_overdue=True, status="overdue",
              due_date=(_now() - timedelta(days=1)).isoformat()),
    ]
    ranked = rank_tasks(tasks, _now())
    assert ranked[0]["id"] == 2


# ── explain_priority ──────────────────────────────────────────────────────────

def test_explain_overdue_task():
    """Explanation for an overdue task should mention 'overdue'."""
    t = _task(is_overdue=True, status="overdue",
              due_date=(_now() - timedelta(days=2)).isoformat())
    explanation = explain_priority(t, _now())
    assert "overdue" in explanation.lower()


def test_explain_due_today():
    """Explanation for a task due today should say 'today'."""
    t = _task(due_date=(_now() + timedelta(hours=3)).isoformat())
    explanation = explain_priority(t, _now())
    assert "today" in explanation.lower() or "tomorrow" in explanation.lower()


def test_explain_returns_string():
    """explain_priority should always return a non-empty string."""
    result = explain_priority(_task(), _now())
    assert isinstance(result, str)
    assert len(result) > 0


# ── build_priority_summary ────────────────────────────────────────────────────

def test_build_summary_no_tasks():
    """Summary with no tasks should report all caught up."""
    result = build_priority_summary([], available_hours=2.0, now=_now())
    assert "no pending" in result.lower() or "caught up" in result.lower()


def test_build_summary_contains_task_title():
    """Summary should include the task title."""
    tasks = [_task(title="Write Report")]
    result = build_priority_summary(tasks, available_hours=2.0, now=_now())
    assert "Write Report" in result


def test_build_summary_time_pressure_warning():
    """If total work exceeds available hours a warning should be present."""
    tasks = [
        _task(id=1, estimated_hours=5.0),
        _task(id=2, estimated_hours=5.0),
    ]
    result = build_priority_summary(tasks, available_hours=2.0, now=_now())
    assert "⚠️" in result or "only" in result.lower()


def test_build_summary_time_fits_note():
    """If work fits in available time a positive note should be present."""
    tasks = [_task(estimated_hours=1.0)]
    result = build_priority_summary(tasks, available_hours=5.0, now=_now())
    assert "✅" in result or "fits" in result.lower()


def test_build_summary_excludes_completed():
    """Completed tasks should not appear in the priority summary."""
    tasks = [
        _task(id=1, title="Active"),
        _task(id=2, title="Done", is_completed=True),
    ]
    result = build_priority_summary(tasks, available_hours=3.0, now=_now())
    assert "Done" not in result
    assert "Active" in result
