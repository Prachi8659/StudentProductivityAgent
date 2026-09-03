"""
frontend/app.py
───────────────
Student Productivity Agent — Streamlit UI

Run with:
    streamlit run frontend/app.py

Tabs
────
  📊 Dashboard   — summary stats (pending / overdue / completed counts)
  📋 My Tasks    — add, view (pending / overdue / completed), complete, delete
  🤖 Study Agent — natural-language chat with the AI agent
"""

from __future__ import annotations

import streamlit as st
from datetime import datetime

# ── Page config (must be the very first Streamlit call) ───────────────────────
st.set_page_config(
    page_title="Student Productivity Agent",
    page_icon="📚",
    layout="wide",
)

# ── Backend connection check ──────────────────────────────────────────────────
_import_error: str = ""
try:
    import api_client          # Streamlit adds frontend/ to sys.path[0];
                               # api_client.py then adds the project root so
                               # all subsequent `from app.*` imports resolve.
    BACKEND_AVAILABLE = True
except Exception as _exc:
    BACKEND_AVAILABLE = False
    _import_error = str(_exc)

# ── Page header ───────────────────────────────────────────────────────────────
st.title("📚 Student Productivity Agent")
st.caption("Manage your tasks and get AI-powered study plans.")

if not BACKEND_AVAILABLE:
    st.error(
        "⚠️ Cannot import the API client. "
        "Make sure you are running Streamlit from the project root: "
        "`streamlit run frontend/app.py`"
    )
    if _import_error:
        st.code(_import_error, language="text")
    st.stop()


# ── Helper: check backend is reachable ───────────────────────────────────────
@st.cache_data(ttl=5)
def _backend_healthy() -> bool:
    import requests
    try:
        r = requests.get(f"{api_client.BASE_URL}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


if not _backend_healthy():
    st.error(
        "⚠️ Cannot reach the FastAPI backend. "
        "Start it first with: `python main.py`"
    )
    st.stop()


# ── Utility helpers ───────────────────────────────────────────────────────────

def _priority_icon(priority: str) -> str:
    return {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(priority, "⚪")


def _status_badge(task: dict) -> str:
    if task.get("is_completed"):
        return "✅ Completed"
    due_raw = task.get("due_date")
    if due_raw:
        try:
            due_dt = datetime.fromisoformat(due_raw)
            if due_dt < datetime.utcnow():
                return "🚨 Overdue"
        except (ValueError, TypeError):
            pass
    return "⏳ Pending"


def _format_due(task: dict) -> str:
    due_raw = task.get("due_date")
    if not due_raw:
        return "No deadline"
    try:
        due_dt = datetime.fromisoformat(due_raw)
        days_left = (due_dt.date() - datetime.utcnow().date()).days
        label = due_dt.strftime("%a %d %b")
        if task.get("is_completed"):
            return label
        if days_left < 0:
            return f"{label} (**{abs(days_left)}d overdue**)"
        if days_left == 0:
            return f"{label} (**today**)"
        if days_left == 1:
            return f"{label} (**tomorrow**)"
        return f"{label} (in {days_left}d)"
    except (ValueError, TypeError):
        return due_raw[:10] if due_raw else "—"


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_dash, tab_tasks, tab_agent = st.tabs(["📊 Dashboard", "📋 My Tasks", "🤖 Study Agent"])


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — DASHBOARD
# ════════════════════════════════════════════════════════════════════════════
with tab_dash:
    st.subheader("Overview")

    try:
        all_tasks = api_client.get_all_tasks()
    except RuntimeError as e:
        st.error(str(e))
        all_tasks = []

    pending   = [t for t in all_tasks if not t.get("is_completed")]
    completed = [t for t in all_tasks if t.get("is_completed")]
    now_str   = datetime.utcnow().isoformat()
    overdue   = [
        t for t in pending
        if t.get("due_date") and t["due_date"] < now_str
    ]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total tasks",   len(all_tasks))
    c2.metric("Pending",       len(pending),   delta=None)
    c3.metric("Overdue 🚨",    len(overdue),   delta=f"-{len(overdue)}" if overdue else None, delta_color="inverse")
    c4.metric("Completed ✅",  len(completed))

    if pending:
        st.divider()
        st.subheader("What to work on next")
        # Show top-3 pending tasks ordered by due date
        sorted_pending = sorted(
            pending,
            key=lambda t: t.get("due_date") or "9999",
        )[:3]
        for t in sorted_pending:
            icon = _priority_icon(t["priority"])
            badge = _status_badge(t)
            due   = _format_due(t)
            st.markdown(
                f"{icon} **{t['title']}** — {t.get('subject','—')}  \n"
                f"&nbsp;&nbsp;&nbsp;{badge} | Due: {due} | Est: {t['estimated_hours']:.1f}h"
            )
    else:
        st.success("🎉 No pending tasks — you're all caught up!")


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — TASK MANAGER
# ════════════════════════════════════════════════════════════════════════════
with tab_tasks:

    # ── Add task form ─────────────────────────────────────────────────────────
    with st.expander("➕ Add a New Task", expanded=True):
        with st.form("add_task_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                title    = st.text_input("Task title *", placeholder="e.g. Write essay draft")
                subject  = st.text_input("Subject",      placeholder="e.g. English Literature")
                priority = st.selectbox("Priority", ["medium", "high", "low"])
            with col2:
                due_date         = st.date_input("Due date *")
                estimated_hours  = st.number_input(
                    "Estimated hours *", min_value=0.5, max_value=24.0, value=2.0, step=0.5
                )
                description = st.text_area("Notes (optional)", height=68)

            submitted = st.form_submit_button("Add Task", use_container_width=True)

        if submitted:
            if not title:
                st.warning("Please enter a task title.")
            else:
                try:
                    api_client.create_task({
                        "title":           title,
                        "subject":         subject or "",
                        "due_date":        f"{due_date}T23:59:00",
                        "estimated_hours": estimated_hours,
                        "priority":        priority,
                        "description":     description,
                    })
                    st.success(f"✅ Task '{title}' added!")
                    st.rerun()
                except RuntimeError as e:
                    st.error(str(e))

    st.divider()

    # ── Task sub-tabs ─────────────────────────────────────────────────────────
    sub_pending, sub_overdue, sub_completed = st.tabs(
        ["⏳ Pending", "🚨 Overdue", "✅ Completed"]
    )

    def _render_task_row(task: dict, show_actions: bool = True) -> None:
        """Render one task card with optional complete / delete buttons."""
        with st.container(border=True):
            col_info, col_done, col_del = st.columns([7, 1, 1])
            with col_info:
                icon  = _priority_icon(task["priority"])
                due   = _format_due(task)
                subj  = task.get("subject") or "—"
                st.markdown(f"**{icon} {task['title']}** — {subj}")
                st.caption(
                    f"Due: {due}  |  Est: {task['estimated_hours']:.1f}h  |  "
                    f"Priority: {task['priority']}  |  ID: #{task['id']}"
                )
                if task.get("description"):
                    st.caption(f"📝 {task['description']}")
            if show_actions:
                with col_done:
                    if st.button("✅", key=f"done_{task['id']}", help="Mark complete"):
                        try:
                            api_client.complete_task(task["id"])
                            st.rerun()
                        except RuntimeError as e:
                            st.error(str(e))
                with col_del:
                    if st.button("🗑️", key=f"del_{task['id']}", help="Delete task"):
                        try:
                            api_client.delete_task(task["id"])
                            st.rerun()
                        except RuntimeError as e:
                            st.error(str(e))

    # Pending
    with sub_pending:
        try:
            pending_tasks = api_client.get_tasks()
        except RuntimeError as e:
            st.error(str(e))
            pending_tasks = []

        if not pending_tasks:
            st.info("No pending tasks. Add one above!")
        else:
            st.caption(f"{len(pending_tasks)} pending task(s)")
            for task in pending_tasks:
                _render_task_row(task)

    # Overdue
    with sub_overdue:
        try:
            overdue_tasks = api_client.get_overdue_tasks()
        except RuntimeError as e:
            st.error(str(e))
            overdue_tasks = []

        if not overdue_tasks:
            st.success("No overdue tasks. 🎉")
        else:
            st.warning(f"⚠️ You have {len(overdue_tasks)} overdue task(s). Address these first!")
            for task in overdue_tasks:
                _render_task_row(task)

    # Completed
    with sub_completed:
        try:
            completed_tasks = api_client.get_completed_tasks()
        except RuntimeError as e:
            st.error(str(e))
            completed_tasks = []

        if not completed_tasks:
            st.info("No completed tasks yet.")
        else:
            st.caption(f"{len(completed_tasks)} completed task(s)")
            for task in completed_tasks:
                _render_task_row(task, show_actions=False)


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — STUDY AGENT
# ════════════════════════════════════════════════════════════════════════════
with tab_agent:
    col_chat, col_help = st.columns([3, 1])

    with col_chat:
        st.subheader("Chat with Your Study Agent")

        available_hours = st.slider(
            "Available study hours today",
            min_value=0.5, max_value=12.0, value=2.0, step=0.5,
            help="This is passed to the agent so it can plan around your available time.",
        )

        # Initialise chat history in session state
        if "chat_messages" not in st.session_state:
            st.session_state.chat_messages = []

        # Render previous messages
        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # Chat input
        if user_input := st.chat_input("Ask the agent…  e.g. 'I have a Python assignment due Friday, 2 hours'"):
            # Display user message
            st.session_state.chat_messages.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.markdown(user_input)

            # Call the backend agent
            with st.chat_message("assistant"):
                with st.spinner("Thinking…"):
                    try:
                        reply = api_client.chat_with_agent(user_input, available_hours)
                    except RuntimeError as e:
                        reply = f"❌ {e}"
                st.markdown(reply)
                st.session_state.chat_messages.append(
                    {"role": "assistant", "content": reply}
                )

        # Clear chat button
        if st.session_state.chat_messages:
            if st.button("🗑️ Clear chat history", use_container_width=True):
                st.session_state.chat_messages = []
                st.rerun()

    # ── Help panel ────────────────────────────────────────────────────────────
    with col_help:
        st.subheader("💡 Example prompts")
        examples = [
            "I have a Python assignment due Friday. It will take 2 hours.",
            "I have a Math exam on Monday, needs 4 hours to prepare.",
            "What should I work on first?",
            "Create a study plan for tomorrow. I have 3 hours.",
            "Show me all my tasks.",
            "I couldn't finish the Python assignment. I only have 1 hour tomorrow. Replan my schedule.",
            "Mark task #2 as complete.",
            "Delete task #3.",
        ]
        for ex in examples:
            if st.button(ex, use_container_width=True, key=f"ex_{hash(ex)}"):
                # Inject the example as if the user typed it
                st.session_state.chat_messages.append({"role": "user", "content": ex})
                with st.spinner("Thinking…"):
                    try:
                        reply = api_client.chat_with_agent(ex, available_hours)
                    except RuntimeError as e:
                        reply = f"❌ {e}"
                st.session_state.chat_messages.append(
                    {"role": "assistant", "content": reply}
                )
                st.rerun()
