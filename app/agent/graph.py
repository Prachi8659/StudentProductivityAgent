"""
app/agent/graph.py
──────────────────
LangGraph workflow for the Student Productivity Agent.

Architecture — ReAct (Reason + Act) loop
─────────────────────────────────────────
  START
    │
    ▼
  ┌─────────────┐
  │  assistant  │  ← LLM decides what to do next (call a tool or reply)
  └──────┬──────┘
         │
    tool_calls?
    ┌────┴────┐
   yes        no
    │          │
    ▼          ▼
  ┌──────┐   END
  │ tools│   (LLM produced a final answer)
  └──┬───┘
     │  tool results injected into messages
     └──────────────────► back to assistant

The loop continues until the LLM stops calling tools and emits a plain
text reply — that reply is the agent's final response to the student.

System prompt
─────────────
A detailed system prompt is prepended to every conversation.  It tells the
LLM what tools exist, how to behave, and what output format is expected.
This is the key to making the agent useful with minimal fine-tuning.
"""

from __future__ import annotations

from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from app.agent.state import AgentState
from app.agent.llm import get_llm
from app.tools import ALL_TOOLS


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a Student Productivity Agent — a focused, friendly AI \
assistant that helps students manage academic tasks and study time.

TODAY'S DATE: {today}

YOUR CAPABILITIES (use these tools when relevant):
  • add_task           — create a new task from natural language
  • list_tasks         — show all pending tasks
  • get_task_by_id     — look up a specific task
  • complete_task      — mark a task as done
  • delete_task        — remove a task permanently
  • prioritize_tasks   — rank tasks by urgency/priority and explain why
  • create_study_plan  — build a day-by-day schedule based on available hours
  • replan             — regenerate the plan when circumstances change

BEHAVIOUR RULES:
1. ALWAYS call the appropriate tool before answering questions about tasks,
   priorities, or study plans. Do not make up task data from memory.
2. When a student describes a task in natural language, extract:
     title, subject, due_date, estimated_hours, priority (infer if not stated)
   and immediately call add_task.
3. For "what should I do first / what's most urgent?" → call prioritize_tasks.
4. For "create a plan / schedule my week" → call create_study_plan.
5. For re-planning after a change → call replan with the reason.
6. After completing tool calls, summarise the result clearly and concisely
   in plain language. Do not just repeat the raw tool output verbatim.
7. If the student mentions they couldn't finish a task, do NOT mark it
   complete. Instead, call replan to adjust the schedule.
8. Be encouraging but realistic. Warn students clearly when there is more
   work than available time.
9. Keep responses focused. Do not ask clarifying questions unless
   absolutely necessary — infer reasonable defaults (priority=medium,
   estimated_hours=2 if not stated).
10. If a required tool fails, explain the problem clearly and suggest
    what the student can do.

PRIORITY INFERENCE GUIDE (when the student doesn't state priority):
  • "urgent", "important", "critical", "exam", "final" → high
  • "easy", "optional", "extra credit"                 → low
  • Everything else                                     → medium

OUTPUT FORMAT:
  • Use plain sentences for confirmations and advice.
  • Use bullet points or numbered lists only when showing multiple items.
  • Keep responses under 200 words unless the student asks for detail.
  • Never output raw JSON or Python dicts.
"""


def _make_system_message() -> SystemMessage:
    """Build the system message with today's date injected."""
    from datetime import datetime
    today = datetime.utcnow().strftime("%A, %d %B %Y")
    return SystemMessage(content=SYSTEM_PROMPT.format(today=today))


# ── Nodes ─────────────────────────────────────────────────────────────────────

def assistant_node(state: AgentState) -> dict:
    """
    Core LLM node.

    Prepends the system prompt on the first turn (when there is only one
    message — the user's), then invokes the LLM with the full message
    history including any tool results from previous iterations.

    Returns a dict updating only 'messages' in the state.
    """
    llm = get_llm()
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    messages = list(state["messages"])

    # Inject system prompt if it's not already there
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [_make_system_message()] + messages

    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


# ── Routing logic ─────────────────────────────────────────────────────────────

def _should_continue(state: AgentState) -> str:
    """
    Decide what to do after the assistant node runs.

    Returns
    -------
    "tools"  — the LLM called one or more tools; run ToolNode next
    "end"    — the LLM produced a final text reply; we're done
    """
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "end"


# ── Graph construction ────────────────────────────────────────────────────────

def build_graph():
    """
    Assemble and compile the LangGraph StateGraph.

    The graph implements the ReAct loop:
      assistant → (tool_calls?) → tools → assistant → … → END

    Returns
    -------
    A compiled LangGraph runnable.
    """
    graph = StateGraph(AgentState)

    # Nodes
    graph.add_node("assistant", assistant_node)
    graph.add_node("tools", ToolNode(ALL_TOOLS))

    # Entry point
    graph.add_edge(START, "assistant")

    # Conditional routing after the assistant node
    graph.add_conditional_edges(
        "assistant",
        _should_continue,
        {
            "tools": "tools",
            "end": END,
        },
    )

    # After tools run, always return to the assistant
    graph.add_edge("tools", "assistant")

    return graph.compile()


# Module-level compiled graph — import this wherever the graph is invoked
agent_graph = build_graph()
