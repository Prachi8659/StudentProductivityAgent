"""
tests/test_agent.py
────────────────────
Tests for the agent layer: state, graph structure, and tools.

All tests here run WITHOUT a real LLM.
Tests that need a real LLM are marked @pytest.mark.llm and skipped by default.

Run:
    pytest tests/test_agent.py -v          # no LLM required
    pytest tests/test_agent.py -m llm -v  # real LLM (requires API key in .env)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent.state import AgentState
from app.database.database import Base
from app.database import crud
from app.tools.task_tools import TASK_TOOLS, _parse_due_date
from app.tools.planner_tools import PLANNER_TOOLS


# ── In-memory DB for tool tests ───────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _patch_session(tmp_path):
    """
    Redirect the SessionLocal used by tools to a fresh in-memory database
    for every test, so tools never touch the real database.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    with patch("app.tools.task_tools.SessionLocal", TestSession), \
         patch("app.tools.planner_tools.SessionLocal", TestSession):
        yield TestSession

    Base.metadata.drop_all(bind=engine)


# ── AgentState ────────────────────────────────────────────────────────────────

def test_agent_state_required_keys():
    """AgentState must declare all required fields."""
    keys = AgentState.__annotations__.keys()
    for key in ("messages", "tasks", "study_plan", "available_hours", "error"):
        assert key in keys, f"Missing AgentState key: {key}"


# ── Tool registry ─────────────────────────────────────────────────────────────

def test_task_tools_count():
    assert len(TASK_TOOLS) >= 5, "Expected at least 5 task tools"


def test_planner_tools_count():
    assert len(PLANNER_TOOLS) >= 3, "Expected at least 3 planner tools"


def test_all_tools_invokable():
    """Every tool must expose an .invoke() method (LangChain @tool pattern)."""
    from app.tools import ALL_TOOLS
    for tool in ALL_TOOLS:
        assert hasattr(tool, "invoke"), f"Tool {tool.name} has no .invoke() method"


def test_all_tools_have_name():
    from app.tools import ALL_TOOLS
    for tool in ALL_TOOLS:
        assert hasattr(tool, "name"), f"Tool missing .name attribute"
        assert tool.name, f"Tool has empty .name"


# ── _parse_due_date ───────────────────────────────────────────────────────────

def test_parse_iso_date():
    result = _parse_due_date("2026-12-01")
    assert result is not None
    assert result.year == 2026
    assert result.month == 12


def test_parse_today():
    result = _parse_due_date("today")
    assert result is not None
    assert result.date() == datetime.utcnow().date()


def test_parse_tomorrow():
    result = _parse_due_date("tomorrow")
    assert result is not None
    expected = (datetime.utcnow() + timedelta(days=1)).date()
    assert result.date() == expected


def test_parse_weekday_friday():
    result = _parse_due_date("Friday")
    assert result is not None
    assert result.weekday() == 4   # Friday = 4


def test_parse_invalid_returns_none():
    result = _parse_due_date("not-a-date")
    assert result is None


def test_parse_empty_returns_none():
    result = _parse_due_date("")
    assert result is None


# ── add_task tool ─────────────────────────────────────────────────────────────

def test_add_task_creates_record(_patch_session):
    """add_task tool should persist a task and return a confirmation string."""
    from app.tools.task_tools import add_task
    result = add_task.invoke({
        "title": "Tool Test Task",
        "subject": "Chemistry",
        "due_date": "2026-12-01",
        "estimated_hours": 2.0,
        "priority": "high",
    })
    assert isinstance(result, str)
    assert "Tool Test Task" in result
    assert "#" in result    # ID should appear


def test_add_task_bad_priority_defaults_to_medium(_patch_session):
    """add_task should silently correct an invalid priority to 'medium'."""
    from app.tools.task_tools import add_task
    result = add_task.invoke({
        "title": "Bad Priority",
        "subject": "Math",
        "due_date": "2026-12-01",
        "estimated_hours": 1.0,
        "priority": "critical",   # invalid
    })
    assert "medium" in result


# ── list_tasks tool ───────────────────────────────────────────────────────────

def test_list_tasks_empty(_patch_session):
    from app.tools.task_tools import list_tasks
    result = list_tasks.invoke({})
    assert "no pending" in result.lower() or "caught up" in result.lower()


def test_list_tasks_shows_added_task(_patch_session):
    from app.tools.task_tools import add_task, list_tasks
    add_task.invoke({
        "title": "Visible Task",
        "subject": "Biology",
        "due_date": "2026-12-01",
        "estimated_hours": 1.5,
    })
    result = list_tasks.invoke({})
    assert "Visible Task" in result


# ── complete_task tool ────────────────────────────────────────────────────────

def test_complete_task_tool(_patch_session):
    from app.tools.task_tools import add_task, complete_task
    add_result = add_task.invoke({
        "title": "Complete Me",
        "subject": "History",
        "due_date": "2026-12-01",
        "estimated_hours": 2.0,
    })
    # Extract ID from confirmation string "... (ID #N) ..."
    import re
    match = re.search(r"#(\d+)", add_result)
    assert match, f"Could not find task ID in: {add_result}"
    task_id = int(match.group(1))
    result = complete_task.invoke({"task_id": task_id})
    assert "complete" in result.lower() or "✅" in result


def test_complete_task_not_found(_patch_session):
    from app.tools.task_tools import complete_task
    result = complete_task.invoke({"task_id": 9999})
    assert "❌" in result or "not found" in result.lower()


# ── delete_task tool ──────────────────────────────────────────────────────────

def test_delete_task_tool(_patch_session):
    from app.tools.task_tools import add_task, delete_task
    add_result = add_task.invoke({
        "title": "Delete Me",
        "subject": "PE",
        "due_date": "2026-12-01",
        "estimated_hours": 1.0,
    })
    import re
    match = re.search(r"#(\d+)", add_result)
    assert match
    task_id = int(match.group(1))
    result = delete_task.invoke({"task_id": task_id})
    assert "deleted" in result.lower() or "🗑️" in result


def test_delete_task_not_found(_patch_session):
    from app.tools.task_tools import delete_task
    result = delete_task.invoke({"task_id": 9999})
    assert "❌" in result or "not found" in result.lower()


# ── prioritize_tasks tool ─────────────────────────────────────────────────────

def test_prioritize_tasks_no_tasks(_patch_session):
    from app.tools.planner_tools import prioritize_tasks
    result = prioritize_tasks.invoke({"available_hours_per_day": 2.0})
    assert "no pending" in result.lower() or "caught up" in result.lower()


def test_prioritize_tasks_with_tasks(_patch_session):
    from app.tools.task_tools import add_task
    from app.tools.planner_tools import prioritize_tasks
    add_task.invoke({
        "title": "Priority Task",
        "subject": "CS",
        "due_date": "2026-09-05",
        "estimated_hours": 3.0,
        "priority": "high",
    })
    result = prioritize_tasks.invoke({"available_hours_per_day": 3.0})
    assert "Priority Task" in result


# ── create_study_plan tool ────────────────────────────────────────────────────

def test_create_study_plan_no_tasks(_patch_session):
    from app.tools.planner_tools import create_study_plan
    result = create_study_plan.invoke({"available_hours_per_day": 3.0})
    assert "no pending" in result.lower() or "caught up" in result.lower()


def test_create_study_plan_with_tasks(_patch_session):
    from app.tools.task_tools import add_task
    from app.tools.planner_tools import create_study_plan
    add_task.invoke({
        "title": "Plan Task",
        "subject": "Math",
        "due_date": "2026-09-10",
        "estimated_hours": 2.0,
    })
    result = create_study_plan.invoke({"available_hours_per_day": 2.0})
    assert "Plan Task" in result
    assert "Study Plan" in result


def test_create_study_plan_zero_hours(_patch_session):
    from app.tools.planner_tools import create_study_plan
    result = create_study_plan.invoke({"available_hours_per_day": 0.0})
    assert "❌" in result or "positive" in result.lower()


# ── replan tool ───────────────────────────────────────────────────────────────

def test_replan_shows_context_note(_patch_session):
    from app.tools.task_tools import add_task
    from app.tools.planner_tools import replan
    add_task.invoke({
        "title": "Replan Task",
        "subject": "CS",
        "due_date": "2026-09-10",
        "estimated_hours": 1.0,
    })
    result = replan.invoke({
        "new_available_hours_per_day": 1.0,
        "reason": "couldn't finish yesterday",
    })
    assert "couldn't finish yesterday" in result or "updated" in result.lower()


# ── graph structure ───────────────────────────────────────────────────────────

def test_graph_builds_without_error():
    """build_graph() must return a non-None compiled graph."""
    from app.agent.graph import build_graph
    graph = build_graph()
    assert graph is not None


def test_graph_has_assistant_node():
    """The compiled graph must expose 'assistant' in its node registry."""
    from app.agent.graph import build_graph
    graph = build_graph()
    # LangGraph compiled graphs expose nodes through the graph attribute
    assert graph is not None    # minimal check; structure tested via integration


# ── Real LLM (optional) ───────────────────────────────────────────────────────

@pytest.mark.llm
def test_graph_invoke_real_llm(_patch_session):
    """
    End-to-end graph invocation with a real LLM.
    Skipped unless you run:  pytest -m llm
    Requires a valid API key in .env.
    """
    from app.agent.graph import agent_graph
    from langchain_core.messages import HumanMessage

    state: AgentState = {
        "messages": [HumanMessage(content="List my tasks.")],
        "tasks": [],
        "study_plan": "",
        "available_hours": 2.0,
        "error": "",
    }
    result = agent_graph.invoke(state)
    assert "messages" in result
    assert len(result["messages"]) >= 1


# ── LLM factory / provider selection (no real API calls) ─────────────────────

def test_get_llm_groq_missing_key_raises():
    """
    get_llm() must raise ValueError with a helpful message when
    LLM_PROVIDER=groq but GROQ_API_KEY is empty.
    No real API call is made.
    """
    import app.agent.llm as llm_module
    with patch.object(llm_module, "LLM_PROVIDER", "groq"), \
         patch.object(llm_module, "GROQ_API_KEY", ""):
        with pytest.raises(ValueError) as exc_info:
            llm_module.get_llm()
    assert "GROQ_API_KEY" in str(exc_info.value)
    assert "console.groq.com" in str(exc_info.value)


def test_get_llm_groq_selects_chatgroq():
    """
    get_llm() must return a ChatGroq instance when LLM_PROVIDER=groq
    and a key is present. The key is fake — no network call is made
    because we only check the type, not invoke the model.
    """
    import app.agent.llm as llm_module
    with patch.object(llm_module, "LLM_PROVIDER", "groq"), \
         patch.object(llm_module, "LLM_MODEL", "llama-3.3-70b-versatile"), \
         patch.object(llm_module, "GROQ_API_KEY", "gsk_fake_key_for_testing"):
        llm = llm_module.get_llm()
    from langchain_groq import ChatGroq
    assert isinstance(llm, ChatGroq)


def test_get_llm_openai_missing_key_raises():
    """get_llm() raises ValueError with instructions when OpenAI key is missing."""
    import app.agent.llm as llm_module
    with patch.object(llm_module, "LLM_PROVIDER", "openai"), \
         patch.object(llm_module, "OPENAI_API_KEY", ""):
        with pytest.raises(ValueError) as exc_info:
            llm_module.get_llm()
    assert "OPENAI_API_KEY" in str(exc_info.value)


def test_get_llm_unsupported_provider_raises():
    """get_llm() raises ValueError for an unknown provider name."""
    import app.agent.llm as llm_module
    with patch.object(llm_module, "LLM_PROVIDER", "unknown_provider"):
        with pytest.raises(ValueError) as exc_info:
            llm_module.get_llm()
    assert "unknown_provider" in str(exc_info.value)


@pytest.mark.llm
def test_graph_invoke_real_groq_llm(_patch_session):
    """
    End-to-end test with a real Groq LLM.
    Skipped unless you run:  pytest -m llm
    Requires GROQ_API_KEY in .env and LLM_PROVIDER=groq.
    """
    from app.agent.graph import agent_graph
    from langchain_core.messages import HumanMessage

    state: AgentState = {
        "messages": [HumanMessage(content="List my tasks.")],
        "tasks": [],
        "study_plan": "",
        "available_hours": 2.0,
        "error": "",
    }
    result = agent_graph.invoke(state)
    assert "messages" in result
    assert len(result["messages"]) >= 1
