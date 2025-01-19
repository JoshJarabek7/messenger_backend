from unittest.mock import patch, MagicMock

import pytest
from sqlmodel import Session, text
from sqlalchemy.sql.elements import TextClause

from app.core.config import Settings, get_settings
from app.db.session import create_db_and_tables, engine, get_db


def test_get_db():
    """Test database session creation."""
    db = next(get_db())
    assert isinstance(db, Session)
    assert db.bind == engine


def test_create_db_and_tables_sqlite():
    """Test database creation with SQLite."""
    # Mock settings to use SQLite
    mock_settings = Settings(
        DATABASE_URL="sqlite:///./test.db",
        DB_POOL_SIZE=5,
        DB_MAX_OVERFLOW=10,
        DB_ECHO_LOG=False,
    )

    # Mock engine to avoid actual database operations
    mock_engine = MagicMock()
    mock_engine.begin.return_value.__enter__.return_value = MagicMock()

    with (
        patch("app.db.session.settings", mock_settings),
        patch("app.db.session.engine", mock_engine),
    ):
        create_db_and_tables()
        # Should not try to create vector extension for SQLite
        mock_engine.begin.assert_not_called()


def test_create_db_and_tables_postgres():
    """Test database creation with PostgreSQL."""
    # Mock settings to use PostgreSQL
    mock_settings = Settings(
        DATABASE_URL="postgresql://postgres:postgres@localhost:5432/test_db",
        DB_POOL_SIZE=5,
        DB_MAX_OVERFLOW=10,
        DB_ECHO_LOG=False,
    )

    # Mock engine and connection
    mock_conn = MagicMock()
    mock_engine = MagicMock()
    mock_engine.begin.return_value.__enter__.return_value = mock_conn

    with (
        patch("app.db.session.settings", mock_settings),
        patch("app.db.session.engine", mock_engine),
        patch("app.db.session.SQLModel.metadata.create_all"),
    ):
        create_db_and_tables()

        # Should try to create vector extension
        assert mock_conn.execute.call_count == 1
        call_args = mock_conn.execute.call_args[0][0]
        assert isinstance(call_args, TextClause)
        assert call_args.text == "CREATE EXTENSION IF NOT EXISTS vector"

        # Should create tables after extension
        assert mock_engine.begin.call_count == 1


def test_engine_configuration():
    """Test database engine configuration."""
    settings = get_settings()

    # Test engine configuration
    assert engine.url.database == settings.DATABASE_URL.split("/")[-1].split("?")[0]
    assert engine.url.host == "localhost"
    assert engine.echo == settings.DB_ECHO_LOG

    # Verify engine is properly configured
    assert engine.dialect.name in ["postgresql", "sqlite"]
