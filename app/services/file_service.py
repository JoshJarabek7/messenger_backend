from typing import Any
from uuid import UUID, uuid4

import boto3
from fastapi import HTTPException, UploadFile
from loguru import logger
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.core.file_parser import FileParser
from app.models.domain import File
from app.models.types.file_type import FileType
from app.repositories.file_repository import FileRepository
from app.services.base_service import BaseService
from app.services.embedding_service import EmbeddingService
from app.services.vector_service import VectorService
from sqlmodel import Session


class FileService(BaseService):
    """Service for managing file domain operations"""

    def __init__(
        self,
        db: Session,
        file_repository: FileRepository,
        openai: AsyncOpenAI,
        s3_client: Any | None = None,
    ) -> None:
        self.db: Session = db
        self.file_repository: FileRepository = file_repository
        self.s3: Any = s3_client or boto3.client(
            "s3",
            aws_access_key_id=get_settings().AWS_ACCESS_KEY_ID,
            aws_secret_access_key=get_settings().AWS_SECRET_ACCESS_KEY,
            region_name=get_settings().AWS_REGION_NAME,
        )
        self.openai = openai

    async def upload_file(
        self,
        file: UploadFile,
        user_id: UUID,
        workspace_id: UUID | None = None,
        channel_id: UUID | None = None,
        dm_conversation_id: UUID | None = None,
        ai_conversation_id: UUID | None = None,
        message_id: UUID | None = None,
    ) -> File:
        """Upload a file to S3 and create database record"""
        try:
            # Read file content and detect type
            content = await file.read()
            mime_type = FileParser.detect_mime_type(content)
            file_type = FileType.from_mime_type(mime_type)
            file_id = uuid4()

            # Create file record first so we have the ID
            db_file = self.file_repository.create_file(
                name=file.filename or "File",
                file_type=file_type,
                mime_type=mime_type,
                file_size=len(content),
                user_id=user_id,
                s3_key=file_id,  # This will be used as both the file ID and S3 key
                workspace_id=workspace_id,
                channel_id=channel_id,
                dm_conversation_id=dm_conversation_id,
                ai_conversation_id=ai_conversation_id,
                message_id=message_id,
            )

            # Reset file position after reading
            file.file.seek(0)

            # Upload to S3 using the file ID as the key
            try:
                self.s3.upload_fileobj(
                    file.file,
                    get_settings().AWS_S3_BUCKET_NAME,
                    str(db_file.id),  # Use file.id as S3 key
                    ExtraArgs={"ContentType": mime_type},
                )
            except Exception as e:
                # If S3 upload fails, delete the file record and raise
                self.file_repository.delete(db_file.id)
                raise e

            # Create embeddings if appropriate
            if FileParser.should_parse(mime_type):
                await self._create_embeddings(db_file, content, mime_type)

            return db_file

        except Exception as e:
            logger.error(f"Error uploading file: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="An error occurred while uploading the file",
            )

    def get_file(self, file_id: UUID) -> File:
        """Get a file by ID"""
        file = self.file_repository.get(file_id)
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        return file

    def delete_file(self, file_id: UUID) -> None:
        """Delete a file and its S3 object"""
        file = self.get_file(file_id)

        try:
            # Delete from S3 (synchronous operation)
            self.s3.delete_object(
                Bucket=get_settings().AWS_S3_BUCKET_NAME,
                Key=str(file.id),  # Use file.id as S3 key
            )
        except Exception as e:
            logger.error(f"Error deleting file from S3: {str(e)}")

        # Delete from database (this will cascade to embeddings)
        self.file_repository.delete(file_id)

    def get_download_url(self, file_id: UUID) -> str:
        """Generate a pre-signed download URL for a file"""
        file = self.get_file(file_id)

        try:
            # Generate presigned URL (synchronous operation)
            url = self.s3.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": get_settings().AWS_S3_BUCKET_NAME,
                    "Key": str(file.id),  # Use file.id as S3 key
                },
                ExpiresIn=3600,  # URL valid for 1 hour
            )
            return url
        except Exception as e:
            logger.error(f"Error generating presigned URL: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Could not generate download URL",
            )

    async def _create_embeddings(
        self, file: File, content: bytes, mime_type: str
    ) -> None:
        """Create embeddings for file content"""
        try:
            extracted_text = FileParser.parse_file(content, mime_type)
            if extracted_text:
                vector_service = VectorService(
                    db=self.db, embedding_service=EmbeddingService()
                )
                vector_service.index_file(
                    file=file,
                    content=extracted_text,
                )
        except Exception as e:
            logger.error(f"Error creating embeddings for file {file.id}: {str(e)}")
