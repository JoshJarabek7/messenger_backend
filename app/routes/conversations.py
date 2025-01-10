from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlmodel import Session, and_, or_, select

from app.models import ChannelType, Conversation, User
from app.schemas import ConversationInfo
from app.utils.access import get_accessible_conversations, verify_workspace_access
from app.utils.auth import get_current_user
from app.utils.db import get_db
from app.websocket import WebSocketMessageType, manager

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class ConversationCreate(BaseModel):
    name: str | None = None  # Required for channels, optional for DMs
    description: str | None = None  # For channels only
    conversation_type: ChannelType
    participant_id: UUID | None = None  # Required for DMs
    workspace_id: UUID | None = None  # Required for channels


@router.post("", response_model=ConversationInfo)
async def create_conversation(
    data: ConversationCreate,
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Create a new conversation (channel or DM)."""
    with Session(engine) as session:
        if data.conversation_type == ChannelType.DIRECT:
            if not data.participant_id:
                raise HTTPException(
                    status_code=400,
                    detail="participant_id required for DM conversations",
                )

            # Verify that the participant exists
            participant = session.get(User, data.participant_id)
            if not participant:
                raise HTTPException(
                    status_code=404,
                    detail="Participant not found",
                )

            # Check if DM conversation already exists
            existing_conversation = session.exec(
                select(Conversation).where(
                    Conversation.conversation_type == ChannelType.DIRECT,
                    or_(
                        and_(
                            Conversation.participant_1_id == current_user.id,
                            Conversation.participant_2_id == data.participant_id,
                        ),
                        and_(
                            Conversation.participant_1_id == data.participant_id,
                            Conversation.participant_2_id == current_user.id,
                        ),
                    ),
                )
            ).first()

            if existing_conversation:
                # Convert UUIDs to strings in the model dump
                conv_data = existing_conversation.model_dump()
                conv_data["id"] = str(conv_data["id"])
                if conv_data.get("workspace_id"):
                    conv_data["workspace_id"] = str(conv_data["workspace_id"])
                if conv_data.get("participant_1_id"):
                    conv_data["participant_1_id"] = str(conv_data["participant_1_id"])
                    # Load participant 1 data
                    participant_1 = session.get(
                        User, existing_conversation.participant_1_id
                    )
                    if participant_1:
                        conv_data["participant_1"] = {
                            "id": str(participant_1.id),
                            "username": participant_1.username,
                            "display_name": participant_1.display_name,
                            "email": participant_1.email,
                            "avatar_url": participant_1.avatar_url,
                            "is_online": participant_1.is_online,
                        }
                if conv_data.get("participant_2_id"):
                    conv_data["participant_2_id"] = str(conv_data["participant_2_id"])
                    # Load participant 2 data
                    participant_2 = session.get(
                        User, existing_conversation.participant_2_id
                    )
                    if participant_2:
                        conv_data["participant_2"] = {
                            "id": str(participant_2.id),
                            "username": participant_2.username,
                            "display_name": participant_2.display_name,
                            "email": participant_2.email,
                            "avatar_url": participant_2.avatar_url,
                            "is_online": participant_2.is_online,
                        }
                return ConversationInfo.model_validate(conv_data)

            # Create new DM conversation
            conversation = Conversation(
                conversation_type=ChannelType.DIRECT,
                participant_1_id=current_user.id,
                participant_2_id=data.participant_id,
            )
        else:
            # Creating a channel
            if not data.name:
                raise HTTPException(
                    status_code=400, detail="name required for channel conversations"
                )
            if not data.workspace_id:
                raise HTTPException(
                    status_code=400,
                    detail="workspace_id required for channel conversations",
                )

            # Verify workspace access
            verify_workspace_access(session, data.workspace_id, current_user.id)

            conversation = Conversation(
                name=data.name,
                description=data.description,
                conversation_type=data.conversation_type,
                workspace_id=data.workspace_id,
            )

        session.add(conversation)
        session.commit()
        session.refresh(conversation)

        # Convert UUIDs to strings in the model dump
        conv_data = conversation.model_dump()
        conv_data["id"] = str(conv_data["id"])
        if conv_data.get("workspace_id"):
            conv_data["workspace_id"] = str(conv_data["workspace_id"])

        # Load participant data
        if conversation.participant_1_id:
            participant_1 = session.get(User, conversation.participant_1_id)
            if participant_1:
                conv_data["participant_1"] = {
                    "id": str(participant_1.id),
                    "username": participant_1.username,
                    "display_name": participant_1.display_name,
                    "email": participant_1.email,
                    "avatar_url": participant_1.avatar_url,
                    "is_online": participant_1.is_online,
                }

        if conversation.participant_2_id:
            participant_2 = session.get(User, conversation.participant_2_id)
            if participant_2:
                conv_data["participant_2"] = {
                    "id": str(participant_2.id),
                    "username": participant_2.username,
                    "display_name": participant_2.display_name,
                    "email": participant_2.email,
                    "avatar_url": participant_2.avatar_url,
                    "is_online": participant_2.is_online,
                }

        # Notify participants via WebSocket
        if conversation.conversation_type == ChannelType.DIRECT:
            # Subscribe both users to the conversation
            manager.subscribe_to_conversation(current_user.id, conversation.id)
            manager.subscribe_to_conversation(data.participant_id, conversation.id)

            # Send notification to both users
            await manager.broadcast_to_users(
                [current_user.id, data.participant_id],
                WebSocketMessageType.CONVERSATION_CREATED,
                conv_data,
            )

        return ConversationInfo.model_validate(conv_data)


@router.get("/recent", response_model=List[ConversationInfo])
async def get_recent_conversations(
    workspace_id: UUID | None = None,
    conversation_type: ChannelType | None = None,
    limit: int = Query(default=20, le=50),
    current_user: User = Depends(get_current_user),
    engine: Engine = Depends(get_db),
):
    """Get recent conversations (channels or DMs) for the current user."""
    with Session(engine) as session:
        # If workspace specified, verify access
        if workspace_id:
            verify_workspace_access(session, workspace_id, current_user.id)

        # Get accessible conversation IDs
        conversation_ids = get_accessible_conversations(
            session, current_user.id, workspace_id
        )

        # Build query
        query = select(Conversation).where(Conversation.id.in_(conversation_ids))

        # Add type filter if specified
        if conversation_type:
            query = query.where(Conversation.conversation_type == conversation_type)

        # Order by most recent activity and apply limit
        query = query.order_by(Conversation.updated_at.desc()).limit(limit)

        # Execute query
        conversations = session.exec(query).all()

        # Load participant data for each conversation
        result = []
        for conv in conversations:
            conv_data = conv.model_dump()
            conv_data["id"] = str(conv.id)
            if conv_data.get("workspace_id"):
                conv_data["workspace_id"] = str(conv_data["workspace_id"])

            # Load participant data
            if conv.participant_1_id:
                participant_1 = session.get(User, conv.participant_1_id)
                if participant_1:
                    conv_data["participant_1"] = {
                        "id": str(participant_1.id),
                        "username": participant_1.username,
                        "display_name": participant_1.display_name,
                        "email": participant_1.email,
                        "avatar_url": participant_1.avatar_url,
                        "is_online": participant_1.is_online,
                    }

            if conv.participant_2_id:
                participant_2 = session.get(User, conv.participant_2_id)
                if participant_2:
                    conv_data["participant_2"] = {
                        "id": str(participant_2.id),
                        "username": participant_2.username,
                        "display_name": participant_2.display_name,
                        "email": participant_2.email,
                        "avatar_url": participant_2.avatar_url,
                        "is_online": participant_2.is_online,
                    }

            result.append(ConversationInfo.model_validate(conv_data))

        return result
