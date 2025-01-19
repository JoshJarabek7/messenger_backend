from io import BytesIO
from unittest.mock import AsyncMock
from typing import Any, Generator
import boto3
import pytest
from fastapi import HTTPException, UploadFile
from sqlmodel import Session
from moto import mock_aws

from app.models.domain import (
    File,
    User,
    Workspace,
    Channel,
    DirectMessageConversation,
    AIConversation,
)
from app.models.types.file_type import FileType
from app.repositories.file_repository import FileRepository
from app.repositories.direct_message_repository import DirectMessageRepository
from app.services.file_service import FileService
from app.services.workspace_service import WorkspaceService
from app.services.direct_message_service import DirectMessageService
from app.services.ai_conversation_service import AIConversationService
from app.core.config import get_settings
from tests.conftest import (
    TEST_AWS_REGION,
    TEST_AWS_ACCESS_KEY,
    TEST_AWS_SECRET_KEY,
    TEST_BUCKET_NAME,
)
import nltk


@pytest.fixture(autouse=True, scope="session")
def download_nltk_data():
    """Download required NLTK data."""
    nltk.download("punkt")
    nltk.download("punkt_tab")
    nltk.download("tokenizers/punkt/english.pickle")


@pytest.fixture
def file_repository(db: Session):
    return FileRepository(db)


@pytest.fixture
def s3(mocker) -> Generator[Any, None, None]:
    """Create a mock S3 client"""
    with mock_aws():
        real_s3 = boto3.client(
            "s3",
            region_name=TEST_AWS_REGION,
            aws_access_key_id=TEST_AWS_ACCESS_KEY,
            aws_secret_access_key=TEST_AWS_SECRET_KEY,
        )

        # Create bucket without location constraint for us-east-1
        real_s3.create_bucket(Bucket=TEST_BUCKET_NAME)

        # Create a proper mock that maintains the real S3 methods but allows assertions
        mock_s3 = mocker.MagicMock()

        # Copy all the real methods to our mock
        for attr in dir(real_s3):
            if not attr.startswith("_"):
                setattr(mock_s3, attr, getattr(real_s3, attr))

        # Special handling for upload_fileobj - make it both work and be assertable
        upload_fileobj = mocker.MagicMock()
        upload_fileobj.side_effect = real_s3.upload_fileobj  # Makes it actually work
        mock_s3.upload_fileobj = upload_fileobj  # Makes it assertable

        yield mock_s3


@pytest.fixture
def file_service(db: Session, file_repository, s3, mock_openai):
    service = FileService(db, file_repository, mock_openai, s3_client=s3)
    return service


@pytest.fixture
def mock_openai():
    return AsyncMock()


@pytest.fixture
def test_file():
    content = b"test file content"
    file = BytesIO(content)
    return UploadFile(
        filename="test.txt",
        file=file,
    )


@pytest.fixture
def test_workspace_in_db(db: Session, test_user_in_db: User) -> Workspace:
    """Create a test workspace in the database."""
    workspace_service = WorkspaceService(db)
    workspace = workspace_service.create_workspace(
        name="Test Workspace",
        description="Test workspace description",
        created_by_id=test_user_in_db.id,
    )
    return workspace


@pytest.fixture
def test_channel_in_db(
    db: Session, test_workspace_in_db: Workspace, test_user_in_db: User
) -> Channel:
    """Create a test channel in the database."""
    workspace_service = WorkspaceService(db)
    channel = workspace_service.create_channel(
        workspace_id=test_workspace_in_db.id,
        name="test-channel",
        description="Test channel",
        created_by_id=test_user_in_db.id,
    )
    return channel


@pytest.fixture
def test_dm_conversation_in_db(
    db: Session, test_user_in_db: User, test_other_user_in_db: User
) -> DirectMessageConversation:
    """Create a test DM conversation in the database."""
    dm_service = DirectMessageService(DirectMessageRepository(db))
    conversation = dm_service.get_or_create_conversation(
        user1_id=test_user_in_db.id,
        user2_id=test_other_user_in_db.id,
    )
    return conversation


@pytest.fixture
def test_ai_conversation_in_db(db: Session, test_user_in_db: User) -> AIConversation:
    """Create a test AI conversation in the database."""
    ai_service = AIConversationService(db)
    conversation = ai_service.get_or_create_conversation(test_user_in_db.id)
    return conversation


@pytest.mark.asyncio
async def test_upload_file_success(
    file_service: FileService, test_file: UploadFile, test_user_in_db: User, s3
):
    file = await file_service.upload_file(
        file=test_file,
        user_id=test_user_in_db.id,
    )

    # Verify file was created in database
    assert file.id is not None
    assert file.user_id == test_user_in_db.id
    assert file.name == test_file.filename

    # Verify file was uploaded to S3
    s3.upload_fileobj.assert_called_once()

    # Verify file exists in S3
    response = s3.list_objects_v2(Bucket=TEST_BUCKET_NAME)
    assert len(response.get("Contents", [])) == 1


@pytest.mark.asyncio
async def test_upload_file_with_workspace(
    file_service: FileService,
    test_file: UploadFile,
    test_user_in_db: User,
    test_workspace_in_db: Workspace,
):
    # Upload file with workspace
    file = await file_service.upload_file(
        file=test_file,
        user_id=test_user_in_db.id,
        workspace_id=test_workspace_in_db.id,
    )

    assert file.workspace_id == test_workspace_in_db.id
    file_service.s3.upload_fileobj.assert_called_once()


@pytest.mark.asyncio
async def test_upload_file_with_channel(
    file_service: FileService,
    test_file: UploadFile,
    test_user_in_db: User,
    test_workspace_in_db: Workspace,
    test_channel_in_db: Channel,
):
    # Upload file with channel
    file = await file_service.upload_file(
        file=test_file,
        user_id=test_user_in_db.id,
        workspace_id=test_workspace_in_db.id,
        channel_id=test_channel_in_db.id,
    )

    assert file.workspace_id == test_workspace_in_db.id
    assert file.channel_id == test_channel_in_db.id
    file_service.s3.upload_fileobj.assert_called_once()


@pytest.mark.asyncio
async def test_upload_file_with_dm_conversation(
    file_service: FileService,
    test_file: UploadFile,
    test_user_in_db: User,
    test_dm_conversation_in_db: DirectMessageConversation,
):
    # Upload file with DM conversation
    file = await file_service.upload_file(
        file=test_file,
        user_id=test_user_in_db.id,
        dm_conversation_id=test_dm_conversation_in_db.id,
    )

    assert file.dm_conversation_id == test_dm_conversation_in_db.id
    file_service.s3.upload_fileobj.assert_called_once()


@pytest.mark.asyncio
async def test_upload_file_with_ai_conversation(
    file_service: FileService,
    test_file: UploadFile,
    test_user_in_db: User,
    test_ai_conversation_in_db: AIConversation,
):
    # Upload file with AI conversation
    file = await file_service.upload_file(
        file=test_file,
        user_id=test_user_in_db.id,
        ai_conversation_id=test_ai_conversation_in_db.id,
    )

    assert file.ai_conversation_id == test_ai_conversation_in_db.id
    file_service.s3.upload_fileobj.assert_called_once()


@pytest.mark.asyncio
async def test_upload_file_s3_error(
    file_service: FileService, test_file: UploadFile, test_user_in_db: User, s3, mocker
):
    # Mock upload_fileobj to raise an error
    s3.upload_fileobj = mocker.Mock(side_effect=Exception("S3 upload failed"))

    with pytest.raises(HTTPException) as exc_info:
        await file_service.upload_file(
            file=test_file,
            user_id=test_user_in_db.id,
        )
    assert exc_info.value.status_code == 500
    assert "error occurred while uploading" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_get_file_success(
    file_service: FileService, test_file: UploadFile, test_user_in_db: User
):
    # Upload a file first
    file = await file_service.upload_file(
        file=test_file,
        user_id=test_user_in_db.id,
    )

    # Get the file
    retrieved = file_service.get_file(file.id)
    assert retrieved.id == file.id
    assert retrieved.name == file.name


@pytest.mark.asyncio
async def test_get_file_not_found(
    file_service: FileService, test_file: UploadFile, test_user_in_db: User
):
    # Upload and delete a file to get a valid but non-existent ID
    file = await file_service.upload_file(
        file=test_file,
        user_id=test_user_in_db.id,
    )
    file_id = file.id
    file_service.delete_file(file_id)

    with pytest.raises(HTTPException) as exc_info:
        file_service.get_file(file_id)
    assert exc_info.value.status_code == 404
    assert "File not found" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_delete_file_success(
    file_service: FileService, test_file: UploadFile, test_user_in_db: User, s3
):
    # Upload a file first
    file = await file_service.upload_file(
        file=test_file,
        user_id=test_user_in_db.id,
    )

    # Delete the file
    file_service.delete_file(file.id)

    # Verify file is deleted from database
    with pytest.raises(HTTPException) as exc_info:
        file_service.get_file(file.id)
    assert exc_info.value.status_code == 404

    # Verify file is deleted from S3
    response = s3.list_objects_v2(Bucket=TEST_BUCKET_NAME)
    assert not response.get("Contents", [])


@pytest.mark.asyncio
async def test_delete_file_s3_error(
    file_service: FileService, test_file: UploadFile, test_user_in_db: User, s3, mocker
):
    # Upload a file first
    file = await file_service.upload_file(
        file=test_file,
        user_id=test_user_in_db.id,
    )

    # Mock delete_object to raise an error
    s3.delete_object = mocker.MagicMock(side_effect=Exception("S3 error"))

    # Delete should still succeed (we don't want S3 errors to block deletion)
    file_service.delete_file(file.id)

    # Verify file is deleted from database
    with pytest.raises(HTTPException) as exc_info:
        file_service.get_file(file.id)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_download_url_success(
    file_service: FileService, test_file: UploadFile, test_user_in_db: User, s3, mocker
):
    # Upload a file first
    file = await file_service.upload_file(
        file=test_file,
        user_id=test_user_in_db.id,
    )

    # Mock the presigned URL
    expected_url = f"https://{TEST_BUCKET_NAME}.s3.amazonaws.com/{file.id}"
    s3.generate_presigned_url = mocker.MagicMock(return_value=expected_url)

    # Get download URL
    url = file_service.get_download_url(file.id)

    # Verify URL was generated
    assert url == expected_url
    s3.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": TEST_BUCKET_NAME, "Key": str(file.id)},
        ExpiresIn=3600,
    )


@pytest.mark.asyncio
async def test_get_download_url_s3_error(
    file_service: FileService, test_file: UploadFile, test_user_in_db: User, s3, mocker
):
    # Upload a file first
    file = await file_service.upload_file(
        file=test_file,
        user_id=test_user_in_db.id,
    )

    # Mock generate_presigned_url to raise an error
    s3.generate_presigned_url = mocker.MagicMock(side_effect=Exception("S3 error"))

    with pytest.raises(HTTPException) as exc_info:
        file_service.get_download_url(file.id)
    assert exc_info.value.status_code == 500
    assert "Could not generate download URL" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_create_embeddings_success(
    file_service: FileService, test_file: UploadFile, test_user_in_db: User, mocker
):
    """Test creating embeddings for a file."""
    # Mock FileParser static methods
    mocker.patch("app.core.file_parser.FileParser.should_parse", return_value=True)
    mocker.patch(
        "app.core.file_parser.FileParser.parse_file", return_value="Test content"
    )
    mocker.patch(
        "app.core.file_parser.FileParser.detect_mime_type", return_value="text/plain"
    )

    # Mock vector service
    mock_vector_service = mocker.Mock()
    mock_vector_service.index_file = mocker.Mock()
    mocker.patch(
        "app.services.file_service.VectorService", return_value=mock_vector_service
    )

    # Mock S3 operations
    file_service.s3.upload_fileobj = mocker.Mock()

    # Upload file
    file = await file_service.upload_file(file=test_file, user_id=test_user_in_db.id)

    # Verify vector service was called
    mock_vector_service.index_file.assert_called_once()

    # Verify file was created with correct mime type
    assert file.mime_type == "text/plain"
