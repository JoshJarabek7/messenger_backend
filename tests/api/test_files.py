from io import BytesIO
from uuid import UUID, uuid4
from typing import Any, Generator

import pytest
import boto3
from fastapi import UploadFile
from fastapi.datastructures import Headers
from httpx import AsyncClient
from sqlmodel import Session
from moto import mock_aws

from app.models.domain import User, File, Workspace, Channel
from app.models.types.file_type import FileType
from app.services.file_service import FileService
from app.repositories.file_repository import FileRepository
from app.core.config import get_settings
from tests.conftest import (
    TEST_AWS_REGION,
    TEST_AWS_ACCESS_KEY,
    TEST_AWS_SECRET_KEY,
    TEST_BUCKET_NAME,
)


@pytest.fixture
def app(test_app):
    return test_app


@pytest.fixture
def s3(mocker) -> Generator[Any, None, None]:
    """Create a mock S3 client"""
    with mock_aws():
        s3 = boto3.client(
            "s3",
            region_name=TEST_AWS_REGION,
            aws_access_key_id=TEST_AWS_ACCESS_KEY,
            aws_secret_access_key=TEST_AWS_SECRET_KEY,
        )
        # Create the bucket with the name from settings
        s3.create_bucket(Bucket=TEST_BUCKET_NAME)

        # Create a new mock with all the original methods
        mock_s3 = mocker.MagicMock()
        for attr in dir(s3):
            if not attr.startswith("_"):
                setattr(mock_s3, attr, getattr(s3, attr))

        # Add the mock upload_fileobj method
        mock_s3.upload_fileobj = mocker.MagicMock()

        yield mock_s3


@pytest.fixture
def test_file() -> UploadFile:
    """Create a test file for upload."""
    content = b"Test file content"
    return UploadFile(
        filename="test.txt",
        file=BytesIO(content),
        size=len(content),
        headers=Headers({"content-type": "text/plain"}),
    )


@pytest.fixture
def test_file_in_db(
    db: Session,
    test_user_in_db: User,
    test_workspace_in_db: Workspace,
    s3,
    mock_openai,
) -> File:
    """Create a test file in the database and S3."""
    file_service = FileService(
        db=db,
        file_repository=FileRepository(db),
        openai=mock_openai,
        s3_client=s3,
    )
    file_id = uuid4()
    file = File(
        id=file_id,  # Set the ID explicitly
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

    # Upload a test file to S3
    content = b"Test file content"
    s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key=str(file.id),
        Body=content,
        ContentType="text/plain",
    )

    return file


@pytest.fixture(autouse=True)
def mock_s3_for_app(mocker, app):
    """Mock S3 client for the FastAPI app"""
    with mock_aws():
        s3 = boto3.client(
            "s3",
            region_name=TEST_AWS_REGION,
            aws_access_key_id=TEST_AWS_ACCESS_KEY,
            aws_secret_access_key=TEST_AWS_SECRET_KEY,
        )
        s3.create_bucket(Bucket=TEST_BUCKET_NAME)

        # Create a new mock with all the original methods
        mock_s3 = mocker.MagicMock()
        for attr in dir(s3):
            if not attr.startswith("_"):
                setattr(mock_s3, attr, getattr(s3, attr))

        # Mock boto3.client to return our mock
        mock_boto3 = mocker.patch("boto3.client")
        mock_boto3.return_value = mock_s3

        yield mock_s3


@pytest.mark.asyncio
async def test_upload_file(
    client: AsyncClient,
    test_file: UploadFile,
    test_workspace_in_db: Workspace,
):
    """Test uploading a file."""
    # Test uploading to workspace
    files = {"file": (test_file.filename, test_file.file, test_file.content_type)}
    response = await client.post(
        "/api/files/upload",
        files=files,
        params={"workspace_id": str(test_workspace_in_db.id)},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "test.txt"
    assert data["file_type"] == "document"
    assert data["mime_type"] == "text/plain"
    assert data["workspace_id"] == str(test_workspace_in_db.id)
    assert UUID(data["id"])


@pytest.mark.asyncio
async def test_upload_file_to_channel(
    client: AsyncClient,
    test_file: UploadFile,
    test_workspace_in_db: Workspace,
    test_channel_in_db: Channel,
):
    """Test uploading a file to a channel."""
    files = {"file": (test_file.filename, test_file.file, test_file.content_type)}
    response = await client.post(
        "/api/files/upload",
        files=files,
        params={
            "workspace_id": str(test_workspace_in_db.id),
            "channel_id": str(test_channel_in_db.id),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "test.txt"
    assert data["channel_id"] == str(test_channel_in_db.id)
    assert UUID(data["id"])


@pytest.mark.asyncio
async def test_get_file(client: AsyncClient, test_file_in_db: File):
    """Test getting file metadata."""
    response = await client.get(f"/api/files/{test_file_in_db.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_file_in_db.id)
    assert data["name"] == test_file_in_db.name
    assert data["file_type"] == test_file_in_db.file_type.value
    assert data["mime_type"] == test_file_in_db.mime_type


@pytest.mark.asyncio
async def test_get_file_not_found(client: AsyncClient):
    """Test getting a non-existent file."""
    response = await client.get(f"/api/files/{UUID(int=0)}")
    assert response.status_code == 404
    assert response.json()["detail"] == "File not found"


@pytest.mark.asyncio
async def test_get_file_download_url(client: AsyncClient, test_file_in_db: File):
    """Test getting file download URL."""
    response = await client.get(f"/api/files/{test_file_in_db.id}/download")
    assert response.status_code == 200
    data = response.json()
    assert "url" in data
    assert data["url"].startswith("https://")


@pytest.mark.asyncio
async def test_get_file_download_url_not_found(client: AsyncClient):
    """Test getting download URL for a non-existent file."""
    response = await client.get(f"/api/files/{UUID(int=0)}/download")
    assert response.status_code == 404
    assert response.json()["detail"] == "File not found"


@pytest.mark.asyncio
async def test_delete_file(
    client: AsyncClient,
    test_file_in_db: File,
):
    """Test deleting a file."""
    response = await client.delete(f"/api/files/{test_file_in_db.id}")
    assert response.status_code == 200
    assert response.json()["message"] == "File deleted successfully"

    # Verify file is deleted
    response = await client.get(f"/api/files/{test_file_in_db.id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_file_not_found(client: AsyncClient):
    """Test deleting a non-existent file."""
    response = await client.delete(f"/api/files/{UUID(int=0)}")
    assert response.status_code == 404
    assert response.json()["detail"] == "File not found"


@pytest.mark.asyncio
async def test_delete_file_unauthorized(
    client: AsyncClient,
    test_file_in_db: File,
    test_other_user_in_db: User,
):
    """Test deleting another user's file."""
    # Change file owner to other user
    test_file_in_db.user_id = test_other_user_in_db.id

    response = await client.delete(f"/api/files/{test_file_in_db.id}")
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to delete this file"
