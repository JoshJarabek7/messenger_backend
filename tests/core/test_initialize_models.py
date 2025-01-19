from unittest.mock import patch, MagicMock
import os

import pytest
from sqlalchemy import MetaData, create_engine
from sqlmodel import SQLModel

from app.core.config import Settings
from app.core.intialize_models import initialize_models


def test_initialize_models():
    """Test model initialization."""
    # Mock SQLModel.metadata to track calls
    mock_metadata = MagicMock()

    # Create a test engine with the correct database name
    test_db_url = os.getenv(
        "TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/test_db"
    )
    test_engine = create_engine(test_db_url)

    with (
        patch.object(SQLModel, "metadata", mock_metadata),
        patch("app.core.intialize_models.engine", test_engine),
    ):
        initialize_models()

        # Verify create_all was called
        mock_metadata.create_all.assert_called_once()

        # Verify it was called with our engine
        args, kwargs = mock_metadata.create_all.call_args
        assert kwargs["bind"].url.database == "test_db"  # Using test database
