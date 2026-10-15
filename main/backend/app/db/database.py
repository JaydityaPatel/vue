from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if "sqlite" in settings.database_url else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    # Import models so they register on Base.metadata before create_all
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    # Add cached-token accounting to existing SQLite databases. create_all only
    # creates missing tables and does not alter tables already in use.
    inspector = inspect(engine)
    if "llm_call_logs" in inspector.get_table_names() and "cached_input_tokens" not in {
        column["name"] for column in inspector.get_columns("llm_call_logs")
    }:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE llm_call_logs ADD COLUMN cached_input_tokens INTEGER"))
    migrations = {
        "turn_scores": {
            "tests_passed": "INTEGER", "tests_total": "INTEGER",
            "complexity_correct": "BOOLEAN", "edge_cases_identified": "JSON",
        },
        "session_reports": {"coding_breakdown": "JSON", "dimension_breakdown": "JSON"},
    }
    tables = set(inspector.get_table_names())
    for table, columns in migrations.items():
        if table not in tables:
            continue
        existing = {column["name"] for column in inspector.get_columns(table)}
        for name, kind in columns.items():
            if name not in existing:
                with engine.begin() as connection:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {kind}"))
