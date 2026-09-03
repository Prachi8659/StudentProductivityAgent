"""
app/agent/llm.py
────────────────
Provider-agnostic LLM factory.

Supported providers (set LLM_PROVIDER in .env):
  - groq      → uses langchain-groq        (default / recommended)
  - openai    → uses langchain-openai
  - anthropic → uses langchain-anthropic   (pip install langchain-anthropic)

Each provider reads its API key from the matching environment variable so
no secret is ever hard-coded here.
"""

from app.config.settings import (
    LLM_PROVIDER,
    LLM_MODEL,
    GROQ_API_KEY,
    OPENAI_API_KEY,
    ANTHROPIC_API_KEY,
)


def get_llm():
    """
    Return a LangChain BaseChatModel for the configured provider.

    Raises
    ------
    ValueError
        When the provider is unsupported or the required API key is missing.
        The error message explains exactly which .env variable to set.
    """

    if LLM_PROVIDER == "groq":
        if not GROQ_API_KEY:
            raise ValueError(
                "GROQ_API_KEY is not set. "
                "Add it to your .env file: GROQ_API_KEY=gsk_..."
                "\nGet a free key at https://console.groq.com"
            )
        from langchain_groq import ChatGroq
        return ChatGroq(model=LLM_MODEL, temperature=0, groq_api_key=GROQ_API_KEY)

    if LLM_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY is not set. "
                "Add it to your .env file: OPENAI_API_KEY=sk-..."
            )
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=LLM_MODEL, temperature=0)

    if LLM_PROVIDER == "anthropic":
        if not ANTHROPIC_API_KEY:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. "
                "Add it to your .env file: ANTHROPIC_API_KEY=..."
            )
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=LLM_MODEL, temperature=0)

    raise ValueError(
        f"Unsupported LLM_PROVIDER='{LLM_PROVIDER}'. "
        "Choose one of: groq, openai, anthropic"
    )
