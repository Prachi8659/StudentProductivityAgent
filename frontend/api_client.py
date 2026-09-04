"""
frontend/api_client.py
──────────────────────
Thin HTTP client the Streamlit pages use to talk to the FastAPI backend.

All requests go through here so pages never import `requests` directly
and error handling is consistent across the whole UI.
"""

import sys
import os

# Ensure the project root (one level above this file's directory) is on
# sys.path so that `from app.config.settings import ...` works regardless
# of how Streamlit was launched. Streamlit inserts the *script* directory
# (frontend/) as sys.path[0], which can shadow the project-root `app` package.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import requests


# ── Backend configuration ────────────────────────────────────────────────────
# In production (Render), BACKEND_URL is set as an environment variable.
# For local development, it falls back to the local FastAPI server.
BASE_URL = os.getenv(
    "BACKEND_URL",
    "http://127.0.0.1:8000"
).rstrip("/")

_TIMEOUT = 60  # seconds — agent calls can take a moment


def _handle(response: requests.Response) -> dict | list:
    """Raise a clear RuntimeError on non-2xx responses, otherwise return JSON."""
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        try:
            detail = response.json().get("detail", str(exc))
        except Exception:
            detail = str(exc)
        raise RuntimeError(
            f"API error {response.status_code}: {detail}"
        ) from exc

    # 204 No Content has no body
    if response.status_code == 204:
        return {}

    return response.json()


# ── Task endpoints ────────────────────────────────────────────────────────────

def get_tasks() -> list[dict]:
    """Fetch all pending (incomplete) tasks."""
    return _handle(
        requests.get(
            f"{BASE_URL}/tasks/",
            timeout=_TIMEOUT
        )
    )


def get_all_tasks() -> list[dict]:
    """Fetch every task regardless of status."""
    return _handle(
        requests.get(
            f"{BASE_URL}/tasks/all",
            timeout=_TIMEOUT
        )
    )


def get_completed_tasks() -> list[dict]:
    """Fetch tasks that have been marked complete."""
    return _handle(
        requests.get(
            f"{BASE_URL}/tasks/completed",
            timeout=_TIMEOUT
        )
    )


def get_overdue_tasks() -> list[dict]:
    """Fetch tasks that are past their deadline."""
    return _handle(
        requests.get(
            f"{BASE_URL}/tasks/overdue",
            timeout=_TIMEOUT
        )
    )


def create_task(payload: dict) -> dict:
    """Create a new task. Payload must match TaskCreate schema."""
    return _handle(
        requests.post(
            f"{BASE_URL}/tasks/",
            json=payload,
            timeout=_TIMEOUT
        )
    )


def update_task(task_id: int, payload: dict) -> dict:
    """Partially update task fields."""
    return _handle(
        requests.patch(
            f"{BASE_URL}/tasks/{task_id}",
            json=payload,
            timeout=_TIMEOUT
        )
    )


def complete_task(task_id: int) -> dict:
    """Mark a task as completed."""
    return _handle(
        requests.post(
            f"{BASE_URL}/tasks/{task_id}/complete",
            timeout=_TIMEOUT
        )
    )


def delete_task(task_id: int) -> None:
    """Delete a task permanently."""
    _handle(
        requests.delete(
            f"{BASE_URL}/tasks/{task_id}",
            timeout=_TIMEOUT
        )
    )


# ── Agent endpoint ───────────────────────────────────────────────────────────

def chat_with_agent(message: str, available_hours: float) -> str:
    """
    Send a message to the LangGraph agent and return its text reply.
    Raises RuntimeError on HTTP errors (surfaced in the UI as st.error).
    """
    payload = {
        "message": message,
        "available_hours": available_hours
    }

    data = _handle(
        requests.post(
            f"{BASE_URL}/agent/chat",
            json=payload,
            timeout=_TIMEOUT
        )
    )

    return data.get("reply", "")