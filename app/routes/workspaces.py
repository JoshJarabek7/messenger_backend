import re
from datetime import UTC, datetime
from typing import List, Optional
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
from app.websocket import WebSocketMessageType, manager

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


class WorkspaceCreate(BaseModel):
    name: str
    description: str | None = None


class WorkspaceUpdate(BaseModel):
    name: str
    description: Optional[str] = None
    icon_url: Optional[str] = None


class MemberUpdate(BaseModel):
    role: str


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
                conversation_id=channel.id,
                user_id=current_user.id,
                joined_at=datetime.now(UTC),
            )
            session.add(channel_member)

        session.commit()

        # Get all workspace members to notify them
        workspace_members = session.exec(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id != current_user.id,
            )
        ).all()
        member_ids = [m.user_id for m in workspace_members]

        # Initialize storage for avatar URL
        storage = Storage()

        # Broadcast workspace_member_added event to all workspace members
        message_data = {
            "workspace_id": str(workspace_id),
            "user_id": str(current_user.id),
            "role": "member",
            "user": {
                "id": str(current_user.id),
                "username": current_user.username,
                "display_name": current_user.display_name,
                "email": current_user.email,
                "avatar_url": storage.create_presigned_url(current_user.avatar_url)
                if current_user.avatar_url
                else None,
            },
        }
        await manager.broadcast_to_users(
            member_ids,
            WebSocketMessageType.WORKSPACE_MEMBER_ADDED,
            message_data,
        )

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


@router.get("/{workspace_id}/members")
async def get_workspace_members(
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    with Session(engine) as session:
        verify_workspace_access(session, workspace_id, user.id)
        members = session.exec(
            select(User, WorkspaceMember)
            .join(WorkspaceMember, User.id == WorkspaceMember.user_id)
            .where(WorkspaceMember.workspace_id == workspace_id)
        ).all()
        storage = Storage()

        # Organize members by role
        owner_ids = []
        admin_ids = []
        member_ids = []
        users = {}

        for member in members:
            user_data = {
                "id": str(member[0].id),
                "username": member[0].username,
                "display_name": member[0].display_name,
                "email": member[0].email,
                "avatar_url": storage.create_presigned_url(member[0].avatar_url)
                if member[0].avatar_url
                else None,
            }
            users[str(member[0].id)] = user_data

            if member[1].role == "owner":
                owner_ids.append(str(member[0].id))
            elif member[1].role == "admin":
                admin_ids.append(str(member[0].id))
            else:
                member_ids.append(str(member[0].id))

        return {
            "users": users,
            "owner_ids": owner_ids,
            "admin_ids": admin_ids,
            "member_ids": member_ids,
        }


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


@router.put("/{workspace_id}", response_model=WorkspaceInfo)
async def update_workspace(
    workspace_id: UUID,
    workspace_update: WorkspaceUpdate,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Update a workspace's settings."""
    with Session(engine) as session:
        # Verify the user is an admin or owner
        member = session.exec(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == current_user.id,
            )
        ).first()

        if not member or member.role not in ["admin", "owner"]:
            raise HTTPException(
                status_code=403,
                detail="You must be an admin or owner to update workspace settings",
            )

        # Check if the new name is already taken (if name is being changed)
        workspace = session.exec(
            select(Workspace).where(Workspace.id == workspace_id)
        ).first()
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        if workspace.name != workspace_update.name:
            existing_workspace = session.exec(
                select(Workspace).where(
                    Workspace.name == workspace_update.name,
                    Workspace.id != workspace_id,
                )
            ).first()
            if existing_workspace:
                raise HTTPException(
                    status_code=400, detail="A workspace with this name already exists"
                )

        # Update the workspace
        for field, value in workspace_update.model_dump(exclude_unset=True).items():
            setattr(workspace, field, value)

        session.add(workspace)
        session.commit()
        session.refresh(workspace)

        # Convert the model to a dict and convert UUIDs to strings
        workspace_dict = workspace.model_dump()
        workspace_dict["id"] = str(workspace_dict["id"])
        workspace_dict["created_by_id"] = str(workspace_dict["created_by_id"])

        return WorkspaceInfo.model_validate(workspace_dict)


@router.patch("/{workspace_id}/members/{user_id}")
async def update_workspace_member(
    workspace_id: UUID,
    user_id: UUID,
    member_update: MemberUpdate,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Update a workspace member's role."""
    with Session(engine) as session:
        # Verify the current user is an admin or owner
        current_member = session.exec(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == current_user.id,
            )
        ).first()

        if not current_member or current_member.role not in ["admin", "owner"]:
            raise HTTPException(
                status_code=403,
                detail="You must be an admin or owner to update member roles",
            )

        # Get the target member
        member = session.exec(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        ).first()

        if not member:
            raise HTTPException(status_code=404, detail="Member not found")

        # Prevent owners from being demoted
        if member.role == "owner":
            raise HTTPException(
                status_code=403,
                detail="Workspace owner's role cannot be changed",
            )

        # Update the member's role
        member.role = member_update.role
        session.add(member)
        session.commit()
        session.refresh(member)

        return {
            "role": member.role,
            "joined_at": member.joined_at,
        }


@router.post("/{workspace_id}/leave")
async def leave_workspace(
    workspace_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Leave a workspace. If the user is the owner, delete the entire workspace."""
    print(f"\n=== User {current_user.id} leaving workspace {workspace_id} ===")
    storage = Storage()

    with Session(db) as session:
        # Get the workspace and check membership
        workspace = session.get(Workspace, workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Get the user's role in the workspace
        member = session.exec(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == current_user.id,
            )
        ).first()

        if not member:
            raise HTTPException(
                status_code=403, detail="You are not a member of this workspace"
            )

        # Check if there are any other owners
        other_owners = session.exec(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id != current_user.id,
                WorkspaceMember.role == "owner",
            )
        ).all()

        # If user is the owner and there are no other owners, delete the entire workspace
        if workspace.created_by_id == current_user.id and not other_owners:
            print(
                f"User is workspace owner and no other owners exist, deleting workspace {workspace_id}"
            )

            # Delete all files from S3
            file_attachments = session.exec(
                select(FileAttachment)
                .join(Message)
                .join(Conversation)
                .where(Conversation.workspace_id == workspace_id)
            ).all()

            for attachment in file_attachments:
                try:
                    storage.delete_file(attachment.s3_key)
                except Exception as e:
                    print(f"Error deleting file {attachment.s3_key} from S3: {e}")
                session.delete(attachment)

            # Delete all messages in workspace conversations
            messages = session.exec(
                select(Message)
                .join(Conversation)
                .where(Conversation.workspace_id == workspace_id)
            ).all()
            for message in messages:
                session.delete(message)

            # Delete all conversations in the workspace
            conversations = session.exec(
                select(Conversation).where(Conversation.workspace_id == workspace_id)
            ).all()
            for conversation in conversations:
                session.delete(conversation)

            # Delete the workspace itself
            session.delete(workspace)
            session.commit()

            # Notify all workspace members about deletion
            workspace_members = [member.user_id for member in workspace.members]
            message_data = {
                "type": WebSocketMessageType.WORKSPACE_DELETED,
                "data": {"workspace_id": str(workspace_id)},
            }
            await manager.broadcast_to_users(workspace_members, message_data)
        else:
            # For owners with other owners, admins, and regular members, just remove their membership
            print(f"User is {member.role}, removing from workspace {workspace_id}")
            session.delete(member)
            session.commit()

            # Get remaining members before sending notifications
            remaining_members = session.exec(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == workspace_id,
                    WorkspaceMember.user_id != current_user.id,
                )
            ).all()

            # Notify remaining workspace members about the user leaving
            workspace_members = [m.user_id for m in remaining_members]
            message_data = {
                "type": WebSocketMessageType.WORKSPACE_MEMBER_LEFT,
                "data": {
                    "workspace_id": str(workspace_id),
                    "user_id": str(current_user.id),
                    "role": member.role,  # Include the role in the notification
                },
            }
            await manager.broadcast_to_users(
                workspace_members,
                WebSocketMessageType.WORKSPACE_MEMBER_LEFT,
                message_data,
            )

        return {"status": "success"}
