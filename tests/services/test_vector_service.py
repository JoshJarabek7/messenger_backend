from uuid import UUID, uuid4
from unittest.mock import MagicMock, patch

from moto import mock_aws
import pytest
from sqlmodel import Session

from app.models.domain import Message, User, File, Workspace, Channel
from app.models.types.file_type import FileType
from app.services.embedding_service import EmbeddingService
from app.services.vector_service import VectorService
from app.services.workspace_service import WorkspaceService
from app.services.file_service import FileService
from app.repositories.file_repository import FileRepository
from app.repositories.vector_repository import VectorRepository
import boto3
from tests.conftest import (
    TEST_AWS_REGION,
    TEST_AWS_ACCESS_KEY,
    TEST_AWS_SECRET_KEY,
    TEST_BUCKET_NAME,
)


@pytest.fixture
def mock_s3():
    with mock_aws():
        s3 = boto3.client(
            "s3",
            region_name=TEST_AWS_REGION,
            aws_access_key_id=TEST_AWS_ACCESS_KEY,
            aws_secret_access_key=TEST_AWS_SECRET_KEY,
        )

        # For us-east-1, we need to create bucket without location constraint
        if TEST_AWS_REGION == "us-east-1":
            s3.create_bucket(Bucket=TEST_BUCKET_NAME)
        else:
            s3.create_bucket(
                Bucket=TEST_BUCKET_NAME,
                CreateBucketConfiguration={"LocationConstraint": TEST_AWS_REGION},
            )
        yield s3


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service that returns fixed embeddings."""
    mock = MagicMock()
    mock.generate_embedding.return_value = [0.1] * 1536  # OpenAI uses 1536 dimensions
    mock.chunk_text.return_value = ["Test chunk"]
    return mock


@pytest.fixture
def vector_service(db: Session, mock_embedding_service) -> VectorService:
    return VectorService(db, mock_embedding_service)


@pytest.fixture
def test_message_with_content(
    db: Session,
    test_user_in_db: User,
    test_workspace_in_db: Workspace,
    test_channel_in_db: Channel,
) -> Message:
    """Create a test message with content."""
    workspace_service = WorkspaceService(db)
    message = Message(
        content="Test message content for vector search",
        user_id=test_user_in_db.id,
        channel_id=test_channel_in_db.id,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


@pytest.fixture
def test_file_with_content(
    db: Session,
    test_user_in_db: User,
    test_workspace_in_db: Workspace,
    mock_s3,
    mock_openai,
) -> File:
    """Create a test file with content."""
    file_service = FileService(
        db=db,
        file_repository=FileRepository(db),
        openai=mock_openai,
    )
    file = File(
        name="test.txt",
        file_type=FileType.DOCUMENT,
        mime_type="text/plain",
        file_size=100,
        user_id=test_user_in_db.id,
        workspace_id=test_workspace_in_db.id,
    )
    db.add(file)
    db.commit()
    db.refresh(file)
    return file


def test_index_message(
    vector_service: VectorService,
    test_message_with_content: Message,
    test_workspace_in_db: Workspace,
    mock_embedding_service: MagicMock,
):
    """Test indexing a message."""
    # Index the message
    vector_service.index_message(test_message_with_content)

    # Verify embedding was generated
    mock_embedding_service.generate_embedding.assert_called_once_with(
        test_message_with_content.content
    )

    # Verify the message was indexed by searching for it
    assert test_message_with_content.channel_id is not None  # Ensure channel_id exists
    results = vector_service.search_messages(
        query="test message content",
        workspace_ids=[test_workspace_in_db.id],
        channel_ids=[test_message_with_content.channel_id],
    )

    assert len(results) > 0
    assert results[0][0].id == test_message_with_content.id
    assert results[0][1] > 0.7  # Check similarity score


def test_index_user(
    vector_service: VectorService,
    test_user_in_db: User,
    mock_embedding_service: MagicMock,
):
    """Test indexing a user."""
    # Index the user
    vector_service.index_user(test_user_in_db)

    # Verify embedding was generated with full user text
    mock_embedding_service.generate_embedding.assert_called_with(
        f"{test_user_in_db.display_name} {test_user_in_db.username}"
    )

    # Verify the user was indexed by searching for them
    results = vector_service.search_users(
        query=test_user_in_db.display_name,
    )

    assert len(results) > 0
    assert results[0][0].id == test_user_in_db.id
    assert results[0][1] > 0.7  # Check similarity score


def test_index_file(
    vector_service: VectorService,
    test_file_with_content: File,
    test_workspace_in_db: Workspace,
    mock_embedding_service: MagicMock,
):
    """Test indexing a file."""
    content = "Test file content for vector search"
    # Index the file
    vector_service.index_file(test_file_with_content, content)

    # Verify chunking and embedding was done
    mock_embedding_service.chunk_text.assert_called_once_with(content)
    mock_embedding_service.generate_embedding.assert_called()

    # Verify the file was indexed by searching for it
    results = vector_service.search_files(
        query="test file content",
        workspace_ids=[test_workspace_in_db.id],
    )

    assert len(results) > 0
    assert results[0][0].id == test_file_with_content.id
    assert results[0][1] > 0.7  # Check similarity score


def test_search_messages(
    vector_service: VectorService,
    test_message_with_content: Message,
    test_workspace_in_db: Workspace,
    mock_embedding_service: MagicMock,
):
    """Test searching messages."""
    # Index the message
    vector_service.index_message(test_message_with_content)

    # Mock the embedding service to return the same embedding for search
    mock_embedding_service.generate_embedding.return_value = [0.1] * 1536

    # Search for messages
    assert test_message_with_content.channel_id is not None  # Ensure channel_id exists
    results = vector_service.search_messages(
        query="test message content",
        workspace_ids=[test_workspace_in_db.id],
        channel_ids=[test_message_with_content.channel_id],
    )

    # Verify results
    assert len(results) == 1
    assert results[0][0].id == test_message_with_content.id
    assert results[0][1] > 0.7  # Check similarity score


def test_search_users(
    vector_service: VectorService,
    test_user_in_db: User,
    mock_embedding_service: MagicMock,
):
    """Test searching users."""
    # Index the user
    vector_service.index_user(test_user_in_db)

    # Mock the embedding service to return the same embedding for search
    mock_embedding_service.generate_embedding.return_value = [0.1] * 1536

    # Search for users
    results = vector_service.search_users(
        query=test_user_in_db.display_name,
    )

    # Verify results
    assert len(results) == 1
    assert results[0][0].id == test_user_in_db.id
    assert results[0][1] > 0.7  # Check similarity score


def test_search_files(
    vector_service: VectorService,
    test_file_with_content: File,
    test_workspace_in_db: Workspace,
    mock_embedding_service: MagicMock,
):
    """Test searching files."""
    content = "Test file content for vector search"
    # Index the file
    vector_service.index_file(test_file_with_content, content)

    # Mock the embedding service to return the same embedding for search
    mock_embedding_service.generate_embedding.return_value = [0.1] * 1536

    # Search for files
    results = vector_service.search_files(
        query="test file content",
        workspace_ids=[test_workspace_in_db.id],
    )

    # Verify results
    assert len(results) == 1
    assert results[0][0].id == test_file_with_content.id
    assert results[0][1] > 0.7  # Check similarity score


def test_get_context_for_rag(
    vector_service: VectorService,
    test_message_with_content: Message,
    test_file_with_content: File,
    test_user_in_db: User,
    test_workspace_in_db: Workspace,
    mock_embedding_service: MagicMock,
):
    """Test getting context for RAG."""
    # Index all content first
    vector_service.index_message(test_message_with_content)
    vector_service.index_file(
        test_file_with_content, "Test file content for vector search"
    )
    vector_service.index_user(test_user_in_db)

    # Test getting context with all types
    results = vector_service.get_context_for_rag(
        query="test content",
        workspace_ids=[test_workspace_in_db.id],
        include_messages=True,
        include_users=True,
        include_files=True,
    )
    assert len(results) > 0

    # Test getting context with only messages
    results = vector_service.get_context_for_rag(
        query="test content",
        workspace_ids=[test_workspace_in_db.id],
        include_messages=True,
        include_users=False,
        include_files=False,
    )
    assert len(results) > 0
    assert all(r[2] == "message" for r in results)

    # Test getting context with only files
    results = vector_service.get_context_for_rag(
        query="test content",
        workspace_ids=[test_workspace_in_db.id],
        include_messages=False,
        include_users=False,
        include_files=True,
    )
    assert len(results) > 0
    assert all(r[2] == "file" for r in results)

    # Test getting context with limit per type
    results = vector_service.get_context_for_rag(
        query="test content",
        workspace_ids=[test_workspace_in_db.id],
        limit_per_type=1,
    )
    message_results = [r for r in results if r[2] == "message"]
    file_results = [r for r in results if r[2] == "file"]
    user_results = [r for r in results if r[2] == "user"]
    assert len(message_results) <= 1
    assert len(file_results) <= 1
    assert len(user_results) <= 1
