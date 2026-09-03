"""
app/agent/state.py
──────────────────
Defines AgentState — the shared whiteboard that flows through every node
in the LangGraph workflow.

Each field is either:
  - Updated by a node returning a partial dict  (messages, study_plan, error)
  - Read by nodes/tools to make decisions       (tasks, available_hours)
"""

from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    Shared state passed between every node in the agent graph.

    Fields
    ------
    messages        : full conversation history (user + AI + tool turns).
                      `add_messages` is a LangGraph reducer — it appends
                      new messages rather than overwriting the list.
    tasks           : snapshot of task dicts loaded for the current turn.
                      Populated by the API layer before graph invocation.
    study_plan      : the most recently generated study plan as a string.
                      Updated whenever create_study_plan or replan runs.
    available_hours : study hours per day the student declared for this turn.
    error           : optional error message surfaced to the caller when
                      something goes wrong inside the graph.
    """

    # Conversation history — LangGraph appends automatically via the reducer
    messages: Annotated[list, add_messages]

    # Tasks snapshot passed in at invocation time
    tasks: list[dict]

    # Latest study plan output (may be empty string if none generated yet)
    study_plan: str

    # Daily available study hours declared by the student
    available_hours: float

    # Optional error string — empty when everything is fine
    error: str
