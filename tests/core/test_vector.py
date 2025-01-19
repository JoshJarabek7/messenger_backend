from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from openai.types.create_embedding_response import CreateEmbeddingResponse, Usage
from openai.types.embedding import Embedding

from app.core.vector import (
    vectorize,
    vectorize_file_prompt,
    vectorize_message_prompt,
    vectorize_user_prompt,
)


@pytest.fixture
def mock_embedding_response() -> CreateEmbeddingResponse:
    """Create a mock embedding response."""
    return CreateEmbeddingResponse(
        data=[
            Embedding(
                embedding=[0.1] * 1536,
                index=0,
                object="embedding",
            )
        ],
        model="text-embedding-3-large",
        object="list",
        usage=Usage(
            prompt_tokens=10,
            total_tokens=10,
        ),
    )


def test_vectorize(mock_embedding_response: CreateEmbeddingResponse):
    """Test text vectorization."""
    with patch(
        "app.core.vector.client.embeddings.create", return_value=mock_embedding_response
    ):
        embedding = vectorize("test text")
        assert len(embedding) == 1536
        assert all(x == 0.1 for x in embedding)


def test_vectorize_message_prompt():
    """Test message prompt vectorization."""
    user_id = uuid4()
    display_name = "Test User"
    username = "testuser"
    email = "test@example.com"
    created_at = datetime.now(UTC)
    content = "Test message content"

    prompt = vectorize_message_prompt(
        user_id=user_id,
        display_name=display_name,
        username=username,
        email=email,
        created_at=created_at,
        content=content,
    )

    # Verify all components are included in the prompt
    assert str(user_id) in prompt
    assert display_name in prompt
    assert username in prompt
    assert email in prompt
    assert str(created_at) in prompt
    assert content in prompt


def test_vectorize_user_prompt():
    """Test user prompt vectorization."""
    display_name = "Test User"
    username = "testuser"
    email = "test@example.com"

    prompt = vectorize_user_prompt(
        display_name=display_name,
        username=username,
        email=email,
    )

    # Verify all components are included in the prompt
    assert display_name in prompt
    assert username in prompt
    assert email in prompt


def test_vectorize_file_prompt():
    """Test file prompt vectorization."""
    name = "test.txt"
    size = 1024
    file_type = "text/plain"
    created_at = datetime.now(UTC)
    content = "Test file content"

    prompt = vectorize_file_prompt(
        name=name,
        size=size,
        type=file_type,
        created_at=created_at,
        content=content,
    )

    # Verify all components are included in the prompt
    assert name in prompt
    assert str(size) in prompt
    assert file_type in prompt
    assert str(created_at) in prompt
    assert content in prompt
