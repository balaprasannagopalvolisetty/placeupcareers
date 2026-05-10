"""
PlaceUp Career Backend — Shared Dependencies
Provides database client and LLM client as FastAPI dependencies.
"""

from functools import lru_cache
from app.config import settings


@lru_cache()
def get_settings():
    """Return cached settings instance."""
    return settings


def get_db():
    """Get database client based on configured backend.

    Yields the appropriate database client (SQLite or Firestore)
    based on the DATABASE_BACKEND environment variable.
    """
    if settings.database_backend == "postgres":
        from app.db.postgres import PostgresClient
        client = PostgresClient()
    elif settings.database_backend == "firestore":
        from app.db.firebase import FirestoreClient
        client = FirestoreClient()
    else:
        from app.db.local_db import SQLiteClient
        client = SQLiteClient()

    try:
        yield client
    finally:
        pass  # Connection cleanup if needed


def get_llm_client():
    """Get the configured LLM client (Groq or OpenAI).

    Returns an Instructor-patched client ready for structured outputs.
    """
    import instructor

    if settings.llm_provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        return instructor.from_openai(client)
    else:
        from groq import Groq
        client = Groq(api_key=settings.groq_api_key)
        return instructor.from_groq(client, mode=instructor.Mode.JSON)
