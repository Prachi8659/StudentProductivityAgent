# 📚 Student Productivity Agent

An agentic AI application that helps students manage academic tasks, prioritise their workload, and automatically build — and rebuild — study plans based on available time.

---

## Problem Statement

Students often struggle to manage multiple assignments, exams, and deadlines across different subjects. They need help answering three key questions:

1. **What do I need to do?** — Keep track of tasks and deadlines in one place.
2. **What should I do first?** — Prioritise work intelligently, not arbitrarily.
3. **How do I fit everything in?** — Create a realistic schedule and adjust it when life changes.

This application answers all three questions through a conversational AI agent that can be asked in plain English.

---

## Key Features

| Feature | Description |
|---|---|
| **Natural-language task entry** | "I have a Python assignment due Friday, 2 hours" |
| **Intelligent prioritisation** | Deterministic scoring: overdue → deadline proximity → explicit priority → effort |
| **Study plan generation** | Day-by-day schedule respecting available hours and deadlines |
| **Automatic re-planning** | Adjusts the plan when time or task status changes |
| **Task dashboard** | Visual overview of pending, overdue, and completed tasks |
| **SQLite persistence** | All tasks stored locally — no cloud account needed |
| **Configurable LLM** | Works with OpenAI, Anthropic, or Groq via a single env variable |

---

## Why This Qualifies as an Agentic AI System

A plain chatbot answers questions. An **agent** observes its environment, decides what actions to take, executes those actions, and adapts based on the results.

This application demonstrates all four properties:

1. **Perceive** — the agent reads the student's natural-language message and the current list of tasks from the database.
2. **Reason** — the LLM (via a detailed system prompt) decides which tool to call and in what order, without the user specifying the steps.
3. **Act** — the agent calls real tools (`add_task`, `prioritize_tasks`, `create_study_plan`, `replan`) that read and write a persistent database.
4. **Adapt** — when the student says "I couldn't finish — replan for 1 hour tomorrow", the agent checks current task state and generates a revised schedule rather than repeating the old one.

The LangGraph **ReAct loop** (Reason → Act → Observe → Reason …) is the mechanism that makes this possible: the LLM can call multiple tools in sequence within a single user turn before producing a final answer.

---

## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Backend / API | **FastAPI** + **Uvicorn** | REST API the frontend calls |
| Agent orchestration | **LangGraph** | ReAct loop managing tool calls and state |
| LLM integration | **LangChain** | Tool binding, message formatting, provider abstraction |
| LLM provider | OpenAI / Anthropic / Groq | Configurable via `.env` |
| Database | **SQLite** + **SQLAlchemy** | Local persistent task storage |
| Frontend | **Streamlit** | Browser-based UI |
| Config | **python-dotenv** | Loads secrets from `.env` |
| Tests | **pytest** | 90 deterministic tests, no LLM required |

---

## Agent Workflow

```
Student message
      │
      ▼
 ┌──────────────┐
 │  assistant   │  ← LLM reads the message + system prompt
 │   (LLM)      │    decides which tool(s) to call
 └──────┬───────┘
        │ tool_calls?
   ┌────┴────┐
  yes        no
   │          │
   ▼          ▼
 ┌──────┐    END  ← Final plain-text reply returned to student
 │ tools│
 │      │  • add_task
 │      │  • list_tasks
 │      │  • get_task_by_id
 │      │  • complete_task
 │      │  • delete_task
 │      │  • prioritize_tasks
 │      │  • create_study_plan
 │      │  • replan
 └──┬───┘
    │  tool results injected as messages
    └──────────────► back to assistant
```

The loop repeats until the LLM produces a final text answer. A single student message may trigger multiple tool calls (e.g., add a task, then immediately create a study plan).

### Prioritization algorithm (deterministic, no LLM)

| Factor | Score |
|---|---|
| Overdue | +100 |
| Priority: high | +30 |
| Priority: medium | +20 |
| Priority: low | +10 |
| Urgency (due in 0–7 days, linear) | +0 to +40 |
| Effort (per estimated hour) | −0.5 |

Tasks are ranked by descending score. The LLM receives the ranked list and explains the ordering in plain language.

---

## Project Structure

```
student-productivity-agent/
│
├── main.py                        # Entry point — starts FastAPI via uvicorn
│
├── app/
│   ├── api/                       # HTTP layer
│   │   ├── app.py                 #   FastAPI factory with lifespan hook
│   │   ├── schemas.py             #   Pydantic request/response models
│   │   └── routes/
│   │       ├── tasks.py           #   8 task CRUD endpoints
│   │       └── agent.py           #   POST /agent/chat — invokes LangGraph
│   │
│   ├── agent/                     # AI agent layer
│   │   ├── graph.py               #   LangGraph ReAct graph (build_graph)
│   │   ├── state.py               #   AgentState TypedDict
│   │   ├── llm.py                 #   Provider-agnostic LLM factory
│   │   └── prioritizer.py        #   Deterministic task scoring engine
│   │
│   ├── tools/                     # LangChain @tool functions
│   │   ├── task_tools.py          #   add/list/get/complete/delete task
│   │   └── planner_tools.py      #   prioritize/plan/replan
│   │
│   ├── database/                  # Persistence layer
│   │   ├── database.py            #   SQLAlchemy engine, session, init_db
│   │   ├── models.py              #   Task ORM model
│   │   └── crud.py                #   All DB queries in one place
│   │
│   └── config/
│       └── settings.py            #   Reads all env vars from .env
│
├── frontend/
│   ├── app.py                     # Streamlit UI (Dashboard / Tasks / Agent)
│   └── api_client.py              # HTTP wrapper for all backend calls
│
├── tests/
│   ├── test_database.py           # 22 CRUD unit tests
│   ├── test_prioritizer.py        # 19 prioritization unit tests
│   ├── test_api.py                # 22 API route integration tests
│   └── test_agent.py              # 27 tool + graph tests
│
├── requirements.txt               # Pinned Python dependencies
├── pytest.ini                     # Test config (excludes LLM tests by default)
├── .env.example                   # Template for environment variables
├── .gitignore                     # Excludes .env, *.db, __pycache__, etc.
└── README.md                      # This file
```

---

## Environment Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd student-productivity-agent
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> **Python 3.11+** is recommended. The project is tested on Python 3.14.

### 4. Configure environment variables

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Open `.env` and set your LLM API key:

```dotenv
# Minimum required change:
OPENAI_API_KEY=sk-your-key-here

# Everything else has sensible defaults and can be left as-is:
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
DATABASE_URL=sqlite:///./student_productivity.db
API_HOST=127.0.0.1
API_PORT=8000
DEBUG=True
```

**The application will not start the agent without a valid API key.** It will return a clear `503` error explaining which key is missing.

---

## Running the Application

You need **two terminals** open simultaneously.

### Terminal 1 — Backend API

```bash
python main.py
```

The server starts at:

| URL | Purpose |
|---|---|
| `http://127.0.0.1:8000` | API root |
| `http://127.0.0.1:8000/health` | Health check |
| `http://127.0.0.1:8000/docs` | Swagger UI (interactive API explorer) |
| `http://127.0.0.1:8000/redoc` | ReDoc API docs |

### Terminal 2 — Frontend

```bash
streamlit run frontend/app.py
```

The UI opens automatically at `http://localhost:8501`.

> **Important:** run this command from the project root directory, not from inside `frontend/`.

---

## Running Tests

```bash
# Run all tests (no LLM or internet required)
pytest

# Verbose output
pytest -v

# Individual test files
pytest tests/test_database.py -v
pytest tests/test_prioritizer.py -v
pytest tests/test_api.py -v
pytest tests/test_agent.py -v

# Run the optional real-LLM end-to-end test (requires API key in .env)
pytest -m llm -v
```

Expected result (no API key needed):

```
90 passed, 1 deselected in ~2s
```

---

## Example Agent Conversations

These four scenarios demonstrate the core agentic behaviour.

### Demo 1 — Add a task

```
You:   I have a Python assignment due Friday. It will take 2 hours.

Agent: ✅ Task added (#1): Python assignment — Programming
       Due: Friday, 05 Sep 2026 | Est: 2.0h | Priority: medium
```

### Demo 2 — Prioritise

```
You:   What should I work on first?

Agent: Your Python assignment should come first.
       It's due in 2 days and estimated to take 2 hours.
```

### Demo 3 — Generate a study plan

```
You:   I have 3 hours available tomorrow. Create my study plan.

Agent: 📅 Study Plan — 3.0h/day starting Friday, 04 Sep 2026

       Friday, 04 Sep (2.0h)
         • Python assignment [Programming] — 2.0h

       ⏱ Total work: 2.0h across 1 day.
```

### Demo 4 — Re-plan

```
You:   I couldn't finish the Python assignment and now I only have
       1 hour tomorrow. Replan my schedule.

Agent: 🔄 Plan updated (couldn't finish Python assignment)

       📅 Study Plan — 1.0h/day starting Saturday, 05 Sep 2026

       Saturday, 05 Sep (1.0h)
         • Python assignment [Programming] — 1.0h

       ⏱ Total work: 2.0h across 2 day(s).
       ⚠️ Remaining work will carry over to Sunday.
```

Other useful prompts:

- `"Show me all my tasks"`
- `"Mark task #2 as complete"`
- `"Delete task #3"`
- `"I have a Math exam Monday — 4 hours to prepare"`
- `"What are my overdue tasks?"`

---

## Using Groq (Recommended — Free)

Groq is the recommended LLM provider for this project because it offers a **free tier** with generous rate limits and fast inference.

### 1. Get a Groq API key

1. Go to [https://console.groq.com](https://console.groq.com) and sign in (or create a free account).
2. Navigate to **API Keys** and create a new key.
3. Copy the key — it starts with `gsk_`.

### 2. Configure your `.env` file

```dotenv
LLM_PROVIDER=groq
LLM_MODEL=llama-3.3-70b-versatile
GROQ_API_KEY=gsk_your_actual_key_here
```

> **Security:** Never commit your `.env` file. It is already listed in `.gitignore`. Only `.env.example` (which contains no real keys) should be committed.

### 3. Run the application

```bash
# Terminal 1 — backend
python main.py

# Terminal 2 — frontend
streamlit run frontend/app.py
```

### Supported Groq models

| Model | Speed | Notes |
|---|---|---|
| `llama-3.3-70b-versatile` | Fast | Recommended — best reasoning |
| `llama-3.1-8b-instant` | Very fast | Good for simple tasks |
| `gemma2-9b-it` | Fast | Google Gemma 2 |

Change `LLM_MODEL` in `.env` to switch between them — no code changes needed.

---

## Switching LLM Providers

Change two lines in `.env` — no code changes needed.

```dotenv
# Anthropic Claude
LLM_PROVIDER=anthropic
LLM_MODEL=claude-3-5-haiku-20241022
ANTHROPIC_API_KEY=your-key-here
```

```dotenv
# Groq (fast inference)
LLM_PROVIDER=groq
LLM_MODEL=llama-3.1-8b-instant
GROQ_API_KEY=your-key-here
```

Then install the matching LangChain package:

```bash
pip install langchain-anthropic   # for Anthropic
pip install langchain-groq        # for Groq
```

---

## API Reference (summary)

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/tasks/` | Create a task |
| `GET` | `/tasks/` | List pending tasks |
| `GET` | `/tasks/all` | List all tasks |
| `GET` | `/tasks/completed` | List completed tasks |
| `GET` | `/tasks/overdue` | List overdue tasks |
| `GET` | `/tasks/{id}` | Get one task |
| `PATCH` | `/tasks/{id}` | Update task fields |
| `POST` | `/tasks/{id}/complete` | Mark complete |
| `DELETE` | `/tasks/{id}` | Delete a task |
| `POST` | `/agent/chat` | Send message to AI agent |

Full interactive documentation: `http://127.0.0.1:8000/docs`

---

## Deployment Preparation

The application is designed for local use but can be deployed with minor changes:

1. **Database** — swap `sqlite:///./student_productivity.db` for a `postgresql://` URL in `.env`. SQLAlchemy supports both with no code changes.
2. **Secrets** — use environment variables or a secrets manager (AWS Secrets Manager, Azure Key Vault) instead of a `.env` file.
3. **Server** — replace `uvicorn --reload` with a production WSGI server: `gunicorn -k uvicorn.workers.UvicornWorker app.api.app:app`.
4. **Frontend** — deploy Streamlit to [Streamlit Community Cloud](https://streamlit.io/cloud) by pointing it at the deployed API URL.
5. **CORS** — add `CORSMiddleware` to `app/api/app.py` if the frontend and backend are on different domains.

---

## Contributing

1. Fork the repository and create a feature branch.
2. Make changes — keep functions small and well-commented.
3. Run `pytest` and confirm all tests pass before opening a PR.
4. Never commit `.env` or `*.db` files (both are in `.gitignore`).
