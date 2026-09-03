"""
app/database/database.py
────────────────────────
Sets up the SQLAlchemy engine and session for SQLite.

Usage (in other modules):
    from app.database.database import get_db, Base

    # Get a DB session (use as a FastAPI dependency or a plain context manager)
    db = next(get_db())
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config.settings import DATABASE_URL

# connect_args is required for SQLite to allow cross-thread usage with FastAPI
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

# Each call to SessionLocal() gives a fresh database session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """All ORM models inherit from this class."""
    pass


def get_db():
    """
    FastAPI dependency that yields a database session and ensures it is
    closed when the request is finished.

    Example:
        @app.get("/tasks")
        def list_tasks(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Create all tables defined in ORM models.
    Call this once at application startup.
    """
    # Import models here so SQLAlchemy registers them with Base.metadata
    from app.database import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
