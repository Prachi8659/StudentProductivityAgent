"""
app/api/app.py
──────────────
Creates and configures the FastAPI application instance.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.routes import tasks, agent
from app.database.database import init_db


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Run startup logic before the app starts accepting requests."""
    init_db()
    yield


def create_app(lifespan=_lifespan) -> FastAPI:
    """
    Build and return the configured FastAPI app.

    Parameters
    ----------
    lifespan : an async context manager used for startup/shutdown.
               Overridable in tests to prevent touching the real database.
    """
    app = FastAPI(
        title="Student Productivity Agent API",
        description=(
            "Backend API for managing academic tasks and interacting with "
            "the AI study-planning agent."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(tasks.router)
    app.include_router(agent.router)

    @app.get("/health", tags=["Health"])
    def health():
        """Quick endpoint to confirm the API is running."""
        return {"status": "ok"}

    return app


# Module-level app instance used by uvicorn
app = create_app()
