"""
app/api/routes/agent.py
───────────────────────
FastAPI router for the AI agent endpoint.

Endpoint
--------
  POST /agent/chat → invoke the LangGraph agent and return its reply
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage

from app.api.schemas import ChatRequest, ChatResponse
from app.agent.graph import agent_graph
from app.agent.state import AgentState
from app.config.settings import LLM_PROVIDER, OPENAI_API_KEY, ANTHROPIC_API_KEY, GROQ_API_KEY

router = APIRouter(prefix="/agent", tags=["Agent"])


def _check_llm_config() -> str | None:
    """
    Return an error string if the LLM is not properly configured,
    or None if everything looks fine.
    """
    if LLM_PROVIDER == "openai" and not OPENAI_API_KEY:
        return (
            "OPENAI_API_KEY is not set. "
            "Add it to your .env file: OPENAI_API_KEY=sk-..."
        )
    if LLM_PROVIDER == "anthropic" and not ANTHROPIC_API_KEY:
        return (
            "ANTHROPIC_API_KEY is not set. "
            "Add it to your .env file: ANTHROPIC_API_KEY=..."
        )
    if LLM_PROVIDER == "groq" and not GROQ_API_KEY:
        return (
            "GROQ_API_KEY is not set. "
            "Add it to your .env file: GROQ_API_KEY=..."
        )
    return None


def _extract_final_reply(result: AgentState) -> str:
    """
    Pull the last AI message text out of the graph result.

    The agent may have run multiple tool calls internally before producing
    a final answer.  We want only the last assistant turn that contains
    plain text (no tool_calls).
    """
    messages = result.get("messages", [])

    # Walk backwards to find the last AI message with plain text content
    for msg in reversed(messages):
        # AIMessage with no tool_calls = final reply
        if hasattr(msg, "content") and not getattr(msg, "tool_calls", None):
            content = msg.content
            if isinstance(content, str) and content.strip():
                return content.strip()
            # Some providers return content as a list of dicts
            if isinstance(content, list):
                texts = [
                    c.get("text", "") for c in content
                    if isinstance(c, dict) and c.get("type") == "text"
                ]
                combined = " ".join(texts).strip()
                if combined:
                    return combined

    return "I processed your request but could not generate a response. Please try again."


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    """
    Send a message to the Student Productivity Agent and get a response.

    The agent will:
    1. Understand the student's intent.
    2. Call the appropriate tools (task management, prioritization, planning).
    3. Return a clear, actionable response.

    Error handling
    ──────────────
    - Missing LLM config  → 503 with setup instructions
    - LLM provider errors → 502 with a description
    - Unexpected errors   → 500
    """
    # ── Pre-flight: check LLM is configured ───────────────────────────────────
    config_error = _check_llm_config()
    if config_error:
        raise HTTPException(status_code=503, detail=config_error)

    # ── Build initial agent state ──────────────────────────────────────────────
    initial_state: AgentState = {
        "messages": [HumanMessage(content=payload.message)],
        "tasks": [],           # tools fetch tasks themselves via SessionLocal
        "study_plan": "",
        "available_hours": payload.available_hours,
        "error": "",
    }

    # ── Invoke the LangGraph agent ─────────────────────────────────────────────
    try:
        result = agent_graph.invoke(initial_state)
    except ValueError as exc:
        # Typically raised when the LLM key is wrong / provider misconfigured
        raise HTTPException(
            status_code=503,
            detail=f"LLM configuration error: {exc}. Check your .env file.",
        ) from exc
    except Exception as exc:
        # Catch-all — surface a clean error instead of a raw traceback
        error_msg = str(exc)
        # Friendly message for common auth failures
        if "api_key" in error_msg.lower() or "authentication" in error_msg.lower():
            raise HTTPException(
                status_code=503,
                detail=(
                    f"LLM authentication failed ({LLM_PROVIDER}). "
                    "Check that your API key in .env is correct."
                ),
            ) from exc
        raise HTTPException(
            status_code=500,
            detail=f"Agent error: {error_msg}",
        ) from exc

    # ── Extract and return the final reply ────────────────────────────────────
    reply = _extract_final_reply(result)
    agent_error = result.get("error", "") or None

    return ChatResponse(reply=reply, error=agent_error)
