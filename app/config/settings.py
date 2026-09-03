"""
app/config/settings.py
──────────────────────
Central place to load and expose all environment variables.
Every other module imports from here instead of reading os.environ directly.
"""

import os
from dotenv import load_dotenv

# Load variables from the .env file (if it exists) into os.environ
load_dotenv()


# ── LLM ───────────────────────────────────────────────────────────────────────
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./student_productivity.db")

# ── API Server ────────────────────────────────────────────────────────────────
API_HOST: str = os.getenv("API_HOST", "127.0.0.1")
API_PORT: int = int(os.getenv("API_PORT", "8000"))

# ── App ───────────────────────────────────────────────────────────────────────
DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
