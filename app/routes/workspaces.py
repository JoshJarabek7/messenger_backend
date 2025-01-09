import re
from datetime import UTC, datetime
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
    Message,
    User,
    Workspace,
    WorkspaceMember,
)
from app.schemas import ConversationInfo, UserInfo, WorkspaceInfo
from app.storage import Storage
from app.utils.access import get_accessible_conversations, verify_workspace_access
from app.utils.auth import get_current_user
from app.utils.db import get_db

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


class WorkspaceCreate(BaseModel):
    name: str
    description: str | None = None


def generate_unique_slug(name: str, engine: Engine = Depends(get_db)) -> str:
    """Generate a unique slug from the workspace name."""
    # Convert to lowercase and replace spaces/special chars with hyphens
    base_slug = name.lower().strip()
    # Replace spaces with hyphens first
    base_slug = base_slug.replace(" ", "-")
    # Then remove any other special characters
    base_slug = re.sub(r"[^\w\-]", "", base_slug)
    # Replace multiple hyphens with a single hyphen
    base_slug = re.sub(r"-+", "-", base_slug)
    # Remove leading/trailing hyphens
    base_slug = base_slug.strip("-")

    # Try the base slug first
    slug = base_slug
    counter = 1

    with Session(engine) as session:
        # Keep trying with numbered suffixes until we find a unique slug
        while session.exec(select(Workspace).where(Workspace.slug == slug)).first():
            slug = f"{base_slug}-{counter}"
            counter += 1

        return slug


@router.get("", response_model=List[WorkspaceInfo])
async def get_user_workspaces(
    current_user: User = Depends(get_current_user), engine: Engine = Depends(get_db)
):
    """Get all workspaces for the current user."""
    with Session(engine) as session:
        # Get all workspaces where the user is a member
        workspaces = session.exec(
            select(Workspace)
            .join(WorkspaceMember)
            .where(WorkspaceMember.user_id == current_user.id)
            .order_by(Workspace.created_at.desc())
        ).all()

        # Convert UUIDs to strings in the model dump
        workspace_data = []
        for ws in workspaces:
            data = ws.model_dump()
            data["id"] = str(data["id"])
            workspace_data.append(WorkspaceInfo.model_validate(data))

        return workspace_data


@router.get("/{workspace_id}/channels", response_model=List[ConversationInfo])
async def get_workspace_channels(
    workspace_id: UUID,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Get all channels in a workspace that the user has access to."""
    with Session(engine) as session:
        # Verify workspace access
        verify_workspace_access(session, workspace_id, current_user.id)

        # Get accessible conversation IDs
        conversation_ids = get_accessible_conversations(
            session, current_user.id, workspace_id
        )

        # Get channels
        channels = session.exec(
            select(Conversation)
            .where(
                Conversation.id.in_(conversation_ids),
                Conversation.conversation_type != ChannelType.DIRECT,
            )
            .order_by(Conversation.created_at.desc())
        ).all()

        # Convert UUIDs to strings in the model dump
        channel_data = []
        for channel in channels:
            data = channel.model_dump()
            data["id"] = str(data["id"])
            if data.get("workspace_id"):
                data["workspace_id"] = str(data["workspace_id"])
            channel_data.append(ConversationInfo.model_validate(data))

        return channel_data


@router.post("", response_model=WorkspaceInfo)
async def create_workspace(
    workspace: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Create a new workspace and make the current user its owner."""
    with Session(engine) as session:
        # Check if workspace with same name exists
        existing_workspace = session.exec(
            select(Workspace).where(Workspace.name == workspace.name)
        ).first()
        if existing_workspace:
            raise HTTPException(
                status_code=400, detail="A workspace with this name already exists"
            )

        # Generate a unique slug
        slug = generate_unique_slug(workspace.name, engine)

        # Create the workspace
        new_workspace = Workspace(
            name=workspace.name,
            description=workspace.description,
            created_by_id=current_user.id,
            slug=slug,
            created_at=datetime.now(UTC),
        )
        session.add(new_workspace)
        session.commit()
        session.refresh(new_workspace)

        # Add the creator as a member
        workspace_member = WorkspaceMember(
            workspace_id=new_workspace.id, user_id=current_user.id, role="owner"
        )
        session.add(workspace_member)
        session.commit()

        # Create a default "general" channel
        general_channel = Conversation(
            name="General",
            description="General discussion",
            workspace_id=new_workspace.id,
            conversation_type=ChannelType.PUBLIC,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(general_channel)
        session.commit()
        session.refresh(general_channel)

        # Add creator to the channel
        channel_member = ConversationMember(
            conversation_id=general_channel.id,
            user_id=current_user.id,
            is_admin=True,
            joined_at=datetime.now(UTC),
        )
        session.add(channel_member)
        session.commit()

        # Convert workspace ID to string for response
        new_workspace.id = str(new_workspace.id)

        return WorkspaceInfo.model_validate(new_workspace.model_dump())


@router.post("/{workspace_id}/join")
async def join_workspace(
    workspace_id: UUID,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Join a workspace."""
    with Session(engine) as session:
        # Check if workspace exists
        workspace = session.exec(
            select(Workspace).where(Workspace.id == workspace_id)
        ).first()
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Check if already a member
        existing_member = session.exec(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == current_user.id,
            )
        ).first()

        if existing_member:
            raise HTTPException(
                status_code=400, detail="Already a member of this workspace"
            )

        # Add user as member
        member = WorkspaceMember(
            workspace_id=workspace_id,
            user_id=current_user.id,
            role="member",
            joined_at=datetime.now(UTC),
        )
        session.add(member)

        # Add user to all public channels in the workspace
        public_channels = session.exec(
            select(Conversation).where(
                Conversation.workspace_id == workspace_id,
                Conversation.conversation_type == ChannelType.PUBLIC,
            )
        ).all()

        for channel in public_channels:
            channel_member = ConversationMember(
                channel_id=channel.id,
                user_id=current_user.id,
                joined_at=datetime.now(UTC),
            )
            session.add(channel_member)

        session.commit()

        return {"id": str(workspace.id), "name": workspace.name, "slug": workspace.slug}


@router.get("/exists/{name}")
async def check_workspace_exists(name: str, engine: Engine = Depends(get_db)):
    """Check if a workspace with the given name exists."""
    with Session(engine) as session:
        existing_workspace = session.exec(
            select(Workspace).where(Workspace.name == name)
        ).first()

        return {"exists": existing_workspace is not None}


@router.get("/{workspace_id}", response_model=WorkspaceInfo)
async def get_workspace(
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Get a workspace by ID."""
    with Session(engine) as session:
        verify_workspace_access(session, workspace_id, user.id)
        workspace = session.exec(
            select(Workspace).where(Workspace.id == workspace_id)
        ).first()
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Convert the model to a dict and convert UUIDs to strings
        workspace_dict = workspace.model_dump()
        workspace_dict["id"] = str(workspace_dict["id"])
        workspace_dict["created_by_id"] = str(workspace_dict["created_by_id"])

        return WorkspaceInfo.model_validate(workspace_dict)


@router.get("/{workspace_id}/members", response_model=List[UserInfo])
async def get_workspace_members(
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    with Session(engine) as session:
        verify_workspace_access(session, workspace_id, user.id)
        members = session.exec(
            select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)
        ).all()
        return [UserInfo.model_validate(member.model_dump()) for member in members]


@router.get("/{workspace_id}/members/{user_id}")
async def get_workspace_member_status(
    workspace_id: UUID,
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Get a member's status in a workspace."""
    with Session(engine) as session:
        verify_workspace_access(session, workspace_id, current_user.id)
        member = session.exec(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        ).first()

        if not member:
            raise HTTPException(status_code=404, detail="Member not found")

        return {
            "is_admin": member.role in ["admin", "owner"],
            "role": member.role,
            "joined_at": member.joined_at,
        }


@router.get("/{workspace_id}/admins", response_model=List[UserInfo])
async def get_workspace_admins(
    workspace_id: UUID,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Get all admins of a workspace."""
    with Session(engine) as session:
        verify_workspace_access(session, workspace_id, current_user.id)
        admins = session.exec(
            select(User, WorkspaceMember)
            .join(WorkspaceMember, User.id == WorkspaceMember.user_id)
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.role.in_(["admin", "owner"]),
            )
        ).all()
        storage = Storage()

        return [
            UserInfo.model_validate(
                {
                    "id": str(admin[0].id),
                    "username": admin[0].username,
                    "display_name": admin[0].display_name,
                    "email": admin[0].email,
                    "avatar_url": storage.create_presigned_url(admin[0].avatar_url)
                    if admin[0].avatar_url
                    else None,
                    "is_online": admin[0].is_online,
                }
            )
            for admin in admins
        ]


@router.get("/{workspace_id}/files")
async def get_workspace_files(
    workspace_id: UUID,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Get all files in a workspace."""
    with Session(engine) as session:
        verify_workspace_access(session, workspace_id, current_user.id)
        # Get all channels in the workspace
        channels = session.exec(
            select(Conversation).where(
                Conversation.workspace_id == workspace_id,
                Conversation.conversation_type != ChannelType.DIRECT,
            )
        ).all()

        channel_ids = [channel.id for channel in channels]

        # Get all files from messages in these channels
        files = session.exec(
            select(FileAttachment)
            .join(Message, FileAttachment.message_id == Message.id)
            .where(Message.conversation_id.in_(channel_ids))
            .order_by(FileAttachment.uploaded_at.desc())
        ).all()
        storage = Storage()

        return [
            {
                "id": str(file.id),
                "original_filename": file.original_filename,
                "file_type": file.file_type,
                "mime_type": file.mime_type,
                "file_size": file.file_size,
                "uploaded_at": file.uploaded_at,
                "download_url": storage.create_presigned_url(file.s3_key),
            }
            for file in files
        ]
