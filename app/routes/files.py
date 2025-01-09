from datetime import datetime
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlmodel import Session, select

from app.models import (
    ChannelType,
    Conversation,
    ConversationMember,
    FileAttachment,
    FileType,
    Message,
    User,
    WorkspaceMember,
)
from app.storage import Storage
from app.utils.auth import get_current_user
from app.utils.db import get_db
from app.websocket import WebSocketMessageType, manager

router = APIRouter(prefix="/api/files", tags=["files"])

# Initialize storage
storage = Storage()


class UploadData(BaseModel):
    url: str
    fields: dict[str, str]


class UploadMetadata(BaseModel):
    s3_key: str
    mime_type: str
    original_filename: str
    file_id: str


class FileUploadResponse(BaseModel):
    upload_data: UploadData
    metadata: UploadMetadata


class FileMetadata(BaseModel):
    id: str
    original_filename: str
    file_type: FileType
    mime_type: str
    file_size: int
    uploaded_at: str
    message_id: str | None = None
    download_url: str | None = None


class UserInfo(BaseModel):
    id: str
    username: str
    display_name: str | None = None
    avatar_url: str | None = None


class FileMetadataWithUser(FileMetadata):
    user: UserInfo
    channel_id: str | None = None
    conversation_id: str | None = None


class CompleteUploadRequest(BaseModel):
    file_size: int


@router.post("/upload-url", response_model=FileUploadResponse)
async def get_upload_url(
    filename: str,
    message_id: UUID | None = None,
    content_type: str | None = None,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Generate a pre-signed URL for file upload."""
    try:
        # Get upload details from storage service
        upload_details = storage.get_upload_details(filename, content_type)

        with Session(engine) as session:
            # Create file attachment record
            file_attachment = FileAttachment(
                original_filename=filename,
                s3_key=upload_details["metadata"]["s3_key"],
                mime_type=upload_details["metadata"]["mime_type"],
                file_type=FileType.from_mime_type(
                    upload_details["metadata"]["mime_type"]
                ),
                file_size=0,  # Will be updated after upload
                message_id=message_id,
                user_id=current_user.id,
                upload_completed=False,
            )
            session.add(file_attachment)
            session.commit()
            session.refresh(file_attachment)

            return {
                "upload_data": {
                    "url": upload_details["upload_data"]["url"],
                    "fields": upload_details["upload_data"]["fields"],
                },
                "metadata": {
                    "s3_key": upload_details["metadata"]["s3_key"],
                    "mime_type": upload_details["metadata"]["mime_type"],
                    "original_filename": upload_details["metadata"][
                        "original_filename"
                    ],
                    "file_id": str(file_attachment.id),
                },
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/complete-upload/{file_id}", response_model=FileMetadata)
async def complete_upload(
    file_id: UUID,
    request: CompleteUploadRequest,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Mark a file upload as complete and notify relevant channels."""
    with Session(engine) as session:
        file_attachment = session.exec(
            select(FileAttachment).where(FileAttachment.id == file_id)
        ).first()

        if not file_attachment:
            raise HTTPException(status_code=404, detail="File not found")

        if file_attachment.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized")

        # Update file size and mark as completed
        file_attachment.file_size = request.file_size
        file_attachment.upload_completed = True
        session.add(file_attachment)

        # If attached to a message, get message details for notification
        if file_attachment.message_id:
            message = session.exec(
                select(Message).where(Message.id == file_attachment.message_id)
            ).first()

            if message and message.channel_id:
                # Create file metadata for notification
                file_data = {
                    "id": str(file_attachment.id),
                    "original_filename": file_attachment.original_filename,
                    "file_type": file_attachment.file_type,
                    "mime_type": file_attachment.mime_type,
                    "file_size": request.file_size,
                    "message_id": str(message.id),
                    "uploaded_at": file_attachment.uploaded_at.isoformat(),
                }

                # Broadcast file upload completion to channel
                await manager.broadcast_to_channel(
                    message.channel_id,
                    WebSocketMessageType.MESSAGE_SENT,
                    {"type": "file_uploaded", "data": file_data},
                )

        session.commit()
        session.refresh(file_attachment)

        # Generate download URL
        download_url = storage.create_presigned_url(file_attachment.s3_key)

        return FileMetadata(
            id=str(file_attachment.id),
            original_filename=file_attachment.original_filename,
            file_type=file_attachment.file_type,
            mime_type=file_attachment.mime_type,
            file_size=file_attachment.file_size,
            uploaded_at=file_attachment.uploaded_at.isoformat(),
            message_id=str(file_attachment.message_id)
            if file_attachment.message_id
            else None,
            download_url=download_url,
        )


@router.get("/download/{file_id}", response_model=FileMetadata)
async def get_download_url(
    file_id: UUID,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Get a pre-signed download URL for a file."""
    with Session(engine) as session:
        file_attachment = session.exec(
            select(FileAttachment).where(FileAttachment.id == file_id)
        ).first()

        if not file_attachment:
            raise HTTPException(status_code=404, detail="File not found")

        if not file_attachment.upload_completed:
            raise HTTPException(status_code=400, detail="File upload not completed")

        # Generate download URL
        download_url = storage.create_presigned_url(file_attachment.s3_key)
        if not download_url:
            raise HTTPException(
                status_code=500, detail="Failed to generate download URL"
            )

        return FileMetadata(
            id=str(file_attachment.id),
            original_filename=file_attachment.original_filename,
            file_type=file_attachment.file_type,
            mime_type=file_attachment.mime_type,
            file_size=file_attachment.file_size,
            uploaded_at=file_attachment.uploaded_at.isoformat(),
            message_id=str(file_attachment.message_id)
            if file_attachment.message_id
            else None,
            download_url=download_url,
        )


@router.delete("/{file_id}")
async def delete_file(
    file_id: UUID,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Delete a file attachment."""
    with Session(engine) as session:
        file_attachment = session.exec(
            select(FileAttachment).where(FileAttachment.id == file_id)
        ).first()

        if not file_attachment:
            raise HTTPException(status_code=404, detail="File not found")

        if file_attachment.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized")

        # Delete from storage
        if not storage.delete_file(file_attachment.s3_key):
            raise HTTPException(
                status_code=500, detail="Failed to delete file from storage"
            )

        # If attached to a message, notify channel
        if file_attachment.message_id:
            message = session.exec(
                select(Message).where(Message.id == file_attachment.message_id)
            ).first()

            if message and message.channel_id:
                await manager.broadcast_to_channel(
                    message.channel_id,
                    WebSocketMessageType.MESSAGE_DELETED,
                    {
                        "type": "file_deleted",
                        "data": {
                            "file_id": str(file_id),
                            "message_id": str(message.id),
                        },
                    },
                )

        # Delete from database
        session.delete(file_attachment)
        session.commit()
        return {"status": "deleted"}


@router.get("/message/{message_id}", response_model=List[FileMetadata])
async def get_message_files(
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Get all files attached to a message."""
    with Session(engine) as session:
        files = session.exec(
            select(FileAttachment).where(
                FileAttachment.message_id == message_id,
                FileAttachment.upload_completed.is_(True),
            )
        ).all()

        result = []
        for file in files:
            download_url = storage.create_presigned_url(file.s3_key)
            result.append(
                FileMetadata(
                    id=str(file.id),
                    original_filename=file.original_filename,
                    file_type=file.file_type,
                    mime_type=file.mime_type,
                    file_size=file.file_size,
                    uploaded_at=file.uploaded_at.isoformat(),
                    message_id=str(message_id),
                    download_url=download_url,
                )
            )

        return result


@router.get("/channel/{channel_id}/files", response_model=List[FileMetadataWithUser])
async def get_channel_files(
    channel_id: UUID,
    limit: int = 50,
    before: datetime | None = None,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Get all files in a channel with sender information."""
    with Session(engine) as session:
        # Check channel exists and user has access
        channel = session.exec(
            select(Conversation).where(Conversation.id == channel_id)
        ).first()

        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")

        # For non-public channels, verify membership
        if channel.conversation_type != ChannelType.PUBLIC:
            member = session.exec(
                select(Conversation)
                .join(ConversationMember)
                .where(
                    Conversation.id == channel_id,
                    ConversationMember.user_id == current_user.id,
                )
            ).first()
            if not member:
                raise HTTPException(
                    status_code=403, detail="Not authorized to view this channel"
                )

        # Build query for files
        query = (
            select(FileAttachment, User)
            .join(Message, FileAttachment.message_id == Message.id)
            .join(User, FileAttachment.user_id == User.id)
            .where(
                Message.conversation_id == channel_id,
                FileAttachment.upload_completed.is_(True),
            )
            .order_by(FileAttachment.uploaded_at.desc())
        )

        if before:
            query = query.where(FileAttachment.uploaded_at < before)

        query = query.limit(limit)

        # Execute query
        results = session.exec(query).all()

        # Format response
        response = []
        for file_attachment, user in results:
            download_url = storage.create_presigned_url(file_attachment.s3_key)
            response.append(
                FileMetadataWithUser(
                    id=str(file_attachment.id),
                    original_filename=file_attachment.original_filename,
                    file_type=file_attachment.file_type,
                    mime_type=file_attachment.mime_type,
                    file_size=file_attachment.file_size,
                    uploaded_at=file_attachment.uploaded_at.isoformat(),
                    message_id=str(file_attachment.message_id),
                    download_url=download_url,
                    user=UserInfo(
                        id=str(user.id),
                        username=user.username,
                        display_name=user.display_name,
                        avatar_url=user.avatar_url,
                    ),
                    channel_id=str(channel_id),
                )
            )

        return response


@router.get(
    "/conversation/{conversation_id}/files", response_model=List[FileMetadataWithUser]
)
async def get_conversation_files(
    conversation_id: UUID,
    limit: int = 50,
    before: datetime | None = None,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Get all files in a conversation with sender information."""
    with Session(engine) as session:
        # Check conversation exists and user is a participant
        conversation = session.exec(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.conversation_type == ChannelType.DIRECT,
                (Conversation.participant_1_id == current_user.id)
                | (Conversation.participant_2_id == current_user.id),
            )
        ).first()

        if not conversation:
            raise HTTPException(
                status_code=404, detail="Conversation not found or not authorized"
            )

        # Build query for files
        query = (
            select(FileAttachment, User)
            .join(Message, FileAttachment.message_id == Message.id)
            .join(User, FileAttachment.user_id == User.id)
            .where(
                Message.conversation_id == conversation_id,
                FileAttachment.upload_completed.is_(True),
            )
            .order_by(FileAttachment.uploaded_at.desc())
        )

        if before:
            query = query.where(FileAttachment.uploaded_at < before)

        query = query.limit(limit)

        # Execute query
        results = session.exec(query).all()

        # Format response
        response = []
        for file_attachment, user in results:
            download_url = storage.create_presigned_url(file_attachment.s3_key)
            response.append(
                FileMetadataWithUser(
                    id=str(file_attachment.id),
                    original_filename=file_attachment.original_filename,
                    file_type=file_attachment.file_type,
                    mime_type=file_attachment.mime_type,
                    file_size=file_attachment.file_size,
                    uploaded_at=file_attachment.uploaded_at.isoformat(),
                    message_id=str(file_attachment.message_id),
                    download_url=download_url,
                    user=UserInfo(
                        id=str(user.id),
                        username=user.username,
                        display_name=user.display_name,
                        avatar_url=user.avatar_url,
                    ),
                    conversation_id=str(conversation_id),
                )
            )

        return response


@router.get(
    "/workspace/{workspace_id}/files", response_model=List[FileMetadataWithUser]
)
async def get_workspace_files(
    workspace_id: UUID,
    limit: int = 50,
    before: datetime | None = None,
    file_type: FileType | None = None,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Get all files in a workspace with sender information, optionally filtered by file type."""
    with Session(engine) as session:
        # Check workspace membership
        member = session.exec(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == current_user.id,
            )
        ).first()

        if not member:
            raise HTTPException(
                status_code=403, detail="Not a member of this workspace"
            )

        # Get accessible channels in workspace
        accessible_channels = session.exec(
            select(Conversation).where(
                Conversation.workspace_id == workspace_id,
                (
                    (Conversation.conversation_type == ChannelType.PUBLIC)
                    | (
                        Conversation.id.in_(
                            select(ConversationMember.conversation_id).where(
                                ConversationMember.user_id == current_user.id
                            )
                        )
                    )
                ),
            )
        ).all()

        channel_ids = [channel.id for channel in accessible_channels]

        # Build query for files
        query = (
            select(FileAttachment, User)
            .join(Message, FileAttachment.message_id == Message.id)
            .join(User, FileAttachment.user_id == User.id)
            .where(
                Message.conversation_id.in_(channel_ids),
                FileAttachment.upload_completed.is_(True),
            )
            .order_by(FileAttachment.uploaded_at.desc())
        )

        if before:
            query = query.where(FileAttachment.uploaded_at < before)

        if file_type:
            query = query.where(FileAttachment.file_type == file_type)

        query = query.limit(limit)

        # Execute query
        results = session.exec(query).all()

        # Format response
        response = []
        for file_attachment, user in results:
            download_url = storage.create_presigned_url(file_attachment.s3_key)
            response.append(
                FileMetadataWithUser(
                    id=str(file_attachment.id),
                    original_filename=file_attachment.original_filename,
                    file_type=file_attachment.file_type,
                    mime_type=file_attachment.mime_type,
                    file_size=file_attachment.file_size,
                    uploaded_at=file_attachment.uploaded_at.isoformat(),
                    message_id=str(file_attachment.message_id),
                    download_url=download_url,
                    user=UserInfo(
                        id=str(user.id),
                        username=user.username,
                        display_name=user.display_name,
                        avatar_url=user.avatar_url,
                    ),
                    channel_id=str(file_attachment.message.conversation_id)
                    if file_attachment.message.conversation_id
                    else None,
                )
            )

        return response
