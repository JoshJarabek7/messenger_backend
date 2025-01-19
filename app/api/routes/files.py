from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session
from app.db.session import get_db

from app.api.dependencies import get_current_user
from app.models.domain import File as DBFile, User
from app.repositories.file_repository import FileRepository
from app.services.file_service import FileService
from app.services.user_service import UserService
from pydantic import BaseModel

router = APIRouter(prefix="/api/files", tags=["files"])


class DownloadFileResponse(BaseModel):
    url: str


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    workspace_id: UUID | None = None,
    channel_id: UUID | None = None,
    dm_conversation_id: UUID | None = None,
    ai_conversation_id: UUID | None = None,
    message_id: UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DBFile:
    """Upload a file"""
    file_service = FileService(
        db=db,
        file_repository=FileRepository(db),
        openai=UserService(db).openai,
    )
    return await file_service.upload_file(
        file=file,
        user_id=current_user.id,
        workspace_id=workspace_id,
        channel_id=channel_id,
        dm_conversation_id=dm_conversation_id,
        ai_conversation_id=ai_conversation_id,
        message_id=message_id,
    )


@router.get("/{file_id}")
async def get_file(
    file_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DBFile:
    """Get file metadata"""
    file_service = FileService(
        db=db,
        file_repository=FileRepository(db),
        openai=UserService(db).openai,
    )
    return file_service.get_file(file_id)


@router.get("/{file_id}/download", response_model=DownloadFileResponse)
async def download_file(
    file_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DownloadFileResponse:
    """Get file download URL"""
    file_service = FileService(
        db=db,
        file_repository=FileRepository(db),
        openai=UserService(db).openai,
    )
    url = file_service.get_download_url(file_id)
    return DownloadFileResponse(url=url)


@router.delete("/{file_id}")
async def delete_file(
    file_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Delete a file"""
    file_service = FileService(
        db=db,
        file_repository=FileRepository(db),
        openai=UserService(db).openai,
    )

    # Get file to check ownership
    file = file_service.get_file(file_id)
    if file.user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to delete this file"
        )

    file_service.delete_file(file_id)
    return {"message": "File deleted successfully"}
