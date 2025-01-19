from datetime import UTC, datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session

from app.models.domain import (
    Channel,
    File,
    FileEmbedding,
    Message,
    MessageEmbedding,
    User,
    UserEmbedding,
    Workspace,
    WorkspaceMember,
)
from app.repositories.vector_repository import VectorRepository


@pytest.fixture
def vector_repository(db: Session) -> VectorRepository:
    return VectorRepository(db)


@pytest.fixture
def test_embedding() -> list[float]:
    return [0.1] * 1536  # Standard OpenAI embedding size


@pytest.fixture
def test_user(vector_repository) -> User:
    user = User(
        id=uuid4(),
        email="test@example.com",
        username="test_user",
        display_name="Test User",
        hashed_password="test_password",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    vector_repository.db.add(user)
    vector_repository.db.commit()
    return user


@pytest.fixture
def test_workspace(vector_repository, test_user) -> Workspace:
    workspace = Workspace(
        id=uuid4(),
        name="Test Workspace",
        description="Test Description",
        slug="test-workspace",
        created_by_id=test_user.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    vector_repository.db.add(workspace)
    vector_repository.db.commit()
    return workspace


@pytest.fixture
def test_channel(vector_repository, test_workspace, test_user) -> Channel:
    channel = Channel(
        id=uuid4(),
        name="test-channel",
        description="Test Channel",
        slug="test-channel",
        workspace_id=test_workspace.id,
        created_by_id=test_user.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    vector_repository.db.add(channel)
    vector_repository.db.commit()
    return channel


@pytest.fixture
def test_message(vector_repository, test_channel, test_user) -> Message:
    message = Message(
        id=uuid4(),
        content="Test message content",
        channel_id=test_channel.id,
        user_id=test_user.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    vector_repository.db.add(message)
    vector_repository.db.commit()
    return message


@pytest.fixture
def test_file(vector_repository, test_workspace, test_user) -> File:
    file = File(
        id=uuid4(),
        name="test_file.txt",
        mime_type="text/plain",
        file_size=100,
        workspace_id=test_workspace.id,
        user_id=test_user.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    vector_repository.db.add(file)
    vector_repository.db.commit()
    return file


def test_store_message_embedding(
    vector_repository: VectorRepository, test_message: Message
):
    content = test_message.content or "Test message content"
    embedding = vector_repository.store_message_embedding(
        message_id=test_message.id, content=content, embedding=[0.1] * 1536
    )
    assert embedding is not None
    assert embedding.message_id == test_message.id
    assert embedding.content == content
    assert len(embedding.embedding) == 1536


def test_store_user_embedding(vector_repository: VectorRepository, test_user: User):
    embedding = vector_repository.store_user_embedding(
        user_id=test_user.id, content="Test user bio", embedding=[0.1] * 1536
    )
    assert embedding is not None
    assert embedding.user_id == test_user.id
    assert embedding.content == "Test user bio"
    assert len(embedding.embedding) == 1536


def test_store_file_chunk_embedding(
    vector_repository: VectorRepository, test_file: File
):
    embedding = vector_repository.store_file_chunk_embedding(
        file_id=test_file.id, content="Test file content", embedding=[0.1] * 1536
    )
    assert embedding is not None
    assert embedding.file_id == test_file.id
    assert embedding.content == "Test file content"
    assert len(embedding.embedding) == 1536


def test_find_similar_messages(
    vector_repository: VectorRepository,
    test_workspace: Workspace,
    test_message: Message,
):
    content = test_message.content or "Test message content"
    # Store test embedding
    vector_repository.store_message_embedding(
        message_id=test_message.id, content=content, embedding=[0.1] * 1536
    )

    # Search for similar messages
    results = vector_repository.find_similar_messages(
        embedding=[0.1] * 1536,
        workspace_ids=[test_workspace.id],
        min_similarity=0.7,
        limit=10,
    )

    assert len(results) == 1
    message, similarity = results[0]
    assert message.id == test_message.id
    assert similarity > 0.7


def test_find_similar_users(vector_repository: VectorRepository, test_user: User):
    # Store test embedding
    vector_repository.store_user_embedding(
        user_id=test_user.id, content="Test user bio", embedding=[0.1] * 1536
    )

    # Search for similar users
    results = vector_repository.find_similar_users(
        embedding=[0.1] * 1536, min_similarity=0.7, limit=10
    )

    assert len(results) == 1
    user, similarity = results[0]
    assert user.id == test_user.id
    assert similarity > 0.7


def test_find_similar_files(
    vector_repository: VectorRepository, test_workspace: Workspace, test_file: File
):
    # Store test embedding
    vector_repository.store_file_chunk_embedding(
        file_id=test_file.id, content="Test file content", embedding=[0.1] * 1536
    )

    # Search for similar files
    results = vector_repository.find_similar_files(
        embedding=[0.1] * 1536,
        workspace_ids=[test_workspace.id],
        min_similarity=0.7,
        limit=10,
    )

    assert len(results) == 1
    file, similarity, content = results[0]
    assert file.id == test_file.id
    assert similarity > 0.7
    assert content == "Test file content"


def test_find_file_chunks(
    vector_repository: VectorRepository, test_workspace: Workspace, test_file: File
):
    # Store test embedding
    vector_repository.store_file_chunk_embedding(
        file_id=test_file.id, content="Test file content", embedding=[0.1] * 1536
    )

    # Search for file chunks
    results = vector_repository.find_file_chunks(
        workspace_ids=[test_workspace.id],
        embedding=[0.1] * 1536,
        min_similarity=0.7,
        limit=10,
    )

    assert len(results) == 1
    file, chunks = results[0]
    assert file.id == test_file.id
    assert len(chunks) == 1
    content, similarity = chunks[0]
    assert content == "Test file content"
    assert similarity > 0.7


def test_get_mixed_chunks_for_rag(
    vector_repository: VectorRepository,
    test_workspace: Workspace,
    test_message: Message,
    test_file: File,
):
    content = test_message.content or "Test message content"
    # Store test embeddings
    vector_repository.store_message_embedding(
        message_id=test_message.id, content=content, embedding=[0.1] * 1536
    )
    vector_repository.store_file_chunk_embedding(
        file_id=test_file.id, content="Test file content", embedding=[0.1] * 1536
    )

    # Search for mixed chunks
    results = vector_repository.get_mixed_chunks_for_rag(
        workspace_ids=[test_workspace.id],
        embedding=[0.1] * 1536,
        min_similarity=0.7,
        limit=10,
    )

    assert len(results) == 2  # One message chunk and one file chunk
    for result in results:
        assert result[0] in [content, "Test file content"]
        assert result[1] > 0.7
        assert result[2] in ["message", "file"]
