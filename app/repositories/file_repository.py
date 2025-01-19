from uuid import UUID

from sqlmodel import Session, select

from app.models.domain import File
from app.models.types.file_type import FileType
from app.repositories.base_repository import BaseRepository


class FileRepository(BaseRepository[File]):
    """Repository for File domain operations"""

    def __init__(self, db: Session):
        super().__init__(File, db)

    def create_file(
        self,
        name: str,
        file_type: FileType,
        mime_type: str,
        file_size: int,
        user_id: UUID,
        s3_key: UUID,
        workspace_id: UUID | None = None,
        channel_id: UUID | None = None,
        dm_conversation_id: UUID | None = None,
        ai_conversation_id: UUID | None = None,
        message_id: UUID | None = None,
    ) -> File:
        """Create a new file record with all necessary metadata"""
        file = File(
            id=s3_key,
            name=name,
            file_type=file_type,
            mime_type=mime_type,
            file_size=file_size,
            user_id=user_id,
            workspace_id=workspace_id,
            channel_id=channel_id,
            dm_conversation_id=dm_conversation_id,
            ai_conversation_id=ai_conversation_id,
        )
        return self.create(file)

    def get_by_s3_key(self, s3_key: str) -> File | None:
        """Get a file by its S3 key"""
        statement = select(File).where(File.id == s3_key)
        result = self.db.exec(statement)
        return result.one_or_none()
