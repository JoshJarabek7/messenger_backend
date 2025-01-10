from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.models import ChannelType, Conversation, FileAttachment, Message, User
from app.storage import Storage
from app.utils.auth import get_current_user
from app.utils.db import get_db
from app.websocket import WebSocketMessageType, manager

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

# Initialize storage
storage = Storage()


class CreateDMRequest(BaseModel):
    participant_id: UUID


def get_presigned_avatar_url(avatar_url: Optional[str]) -> Optional[str]:
    """Helper function to get presigned URL for avatar"""
    if not avatar_url:
        return None
    return storage.create_presigned_url(avatar_url)


@router.get("/recent")
async def get_recent_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get recent conversations for the current user."""
    conversations_data = []
    direct_message_count = 0
    channel_count = 0

    print(f"\n=== Loading Recent Conversations for User {current_user.id} ===")

    # Get all conversations the user is a member of
    with Session(db) as session:
        # First, let's check direct messages specifically
        direct_messages = session.exec(
            select(Conversation).where(
                Conversation.conversation_type == ChannelType.DIRECT,
                (Conversation.participant_1_id == current_user.id)
                | (Conversation.participant_2_id == current_user.id),
            )
        ).all()
        print("\nDirect message check:")
        print(
            f"Found {len(direct_messages)} direct messages where user is participant 1 or 2"
        )

        # Now check conversations through membership
        member_conversations = session.exec(
            select(Conversation)
            .join(Conversation.members)
            .where(User.id == current_user.id)
            .order_by(Conversation.updated_at.desc())
        ).all()
        print("\nMember conversations check:")
        print(f"Found {len(member_conversations)} conversations through membership")

        # Combine and deduplicate conversations
        conversation_ids = set()
        conversations = []
        for conv in direct_messages + member_conversations:
            if conv.id not in conversation_ids:
                conversation_ids.add(conv.id)
                conversations.append(conv)

        print(f"\nTotal unique conversations found: {len(conversations)}")
        print("Conversation types found:")
        for conv_type in set(conv.conversation_type for conv in conversations):
            count = sum(
                1 for conv in conversations if conv.conversation_type == conv_type
            )
            print(f"- {conv_type}: {count}")

        for conv in conversations:
            print(f"\nProcessing conversation {conv.id}:")
            print(f"- Type: {conv.conversation_type}")
            print(f"- Name: {conv.name}")
            print(f"- Workspace ID: {conv.workspace_id}")
            print(f"- Participant 1 ID: {conv.participant_1_id}")
            print(f"- Participant 2 ID: {conv.participant_2_id}")
            print(f"- Member count: {len(conv.members)}")

            # Get last message in conversation
            last_message = session.exec(
                select(Message)
                .where(Message.conversation_id == conv.id)
                .order_by(Message.created_at.desc())
                .limit(1)
            ).first()

            if last_message:
                print(f"- Last message found: {last_message.id}")
            else:
                print("- No last message found")

            last_message_data = None
            if last_message:
                last_message_data = {
                    "id": last_message.id,
                    "content": last_message.content,
                    "created_at": last_message.created_at,
                    "user": {
                        "id": last_message.user.id,
                        "username": last_message.user.username,
                        "display_name": last_message.user.display_name,
                        "avatar_url": get_presigned_avatar_url(
                            last_message.user.avatar_url
                        ),
                    },
                }

            # For direct messages, get participant info
            if conv.conversation_type == ChannelType.DIRECT:
                direct_message_count += 1
                participant_1 = None
                participant_2 = None

                print("- Processing Direct Message participants:")
                for member in conv.members:
                    if member.id == current_user.id:
                        participant_1 = member
                        print(
                            f"  * Found participant 1 (current user): {member.username}"
                        )
                    else:
                        participant_2 = member
                        print(f"  * Found participant 2: {member.username}")

                if not participant_1 or not participant_2:
                    print("  ! Missing participants, skipping conversation")
                    continue

                conversation_data = {
                    "id": conv.id,
                    "conversation_type": conv.conversation_type,
                    "created_at": conv.created_at,
                    "updated_at": conv.updated_at,
                    "name": None,
                    "description": None,
                    "workspace_id": conv.workspace_id,
                    "participant_1": {
                        "id": participant_1.id,
                        "username": participant_1.username,
                        "display_name": participant_1.display_name,
                        "avatar_url": get_presigned_avatar_url(
                            participant_1.avatar_url
                        ),
                        "is_online": manager.is_user_online(participant_1.id),
                        "email": participant_1.email,
                    },
                    "participant_2": {
                        "id": participant_2.id,
                        "username": participant_2.username,
                        "display_name": participant_2.display_name,
                        "avatar_url": get_presigned_avatar_url(
                            participant_2.avatar_url
                        ),
                        "is_online": manager.is_user_online(participant_2.id),
                        "email": participant_2.email,
                    },
                    "last_message": last_message_data if last_message_data else None,
                }
            else:
                channel_count += 1
                print("- Processing Channel conversation")
                # For other conversation types (channels)
                conversation_data = {
                    "id": conv.id,
                    "conversation_type": conv.conversation_type,
                    "created_at": conv.created_at,
                    "updated_at": conv.updated_at,
                    "name": conv.name,
                    "description": conv.description,
                    "workspace_id": conv.workspace_id,
                    "last_message": last_message_data if last_message_data else None,
                }

            conversations_data.append(conversation_data)
            print(f"✓ Successfully processed conversation {conv.id}")

    print("\n=== Conversation Summary ===")
    print(f"Total conversations processed: {len(conversations_data)}")
    print(f"Direct Messages: {direct_message_count}")
    print(f"Channels: {channel_count}")
    print("===========================\n")

    return conversations_data


@router.post("/")
async def create_conversation(
    request: CreateDMRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new direct message conversation."""
    print("\n=== Creating DM Conversation ===")
    print(f"Current user: {current_user.id}")
    print(f"Participant: {request.participant_id}")

    with Session(db) as session:
        # First check if a DM conversation already exists
        existing_conversation = session.exec(
            select(Conversation).where(
                Conversation.conversation_type == ChannelType.DIRECT,
                (
                    (Conversation.participant_1_id == current_user.id)
                    & (Conversation.participant_2_id == request.participant_id)
                )
                | (
                    (Conversation.participant_1_id == request.participant_id)
                    & (Conversation.participant_2_id == current_user.id)
                ),
            )
        ).first()

        if existing_conversation:
            print(f"Found existing conversation: {existing_conversation.id}")
            return {
                "id": existing_conversation.id,
                "conversation_type": existing_conversation.conversation_type,
                "created_at": existing_conversation.created_at,
                "updated_at": existing_conversation.updated_at,
                "workspace_id": existing_conversation.workspace_id,
            }

        # Get the participant user
        participant = session.get(User, request.participant_id)
        if not participant:
            raise HTTPException(status_code=404, detail="Participant not found")

        # Create new conversation
        conversation = Conversation(
            conversation_type=ChannelType.DIRECT,
            participant_1_id=current_user.id,
            participant_2_id=request.participant_id,
        )
        session.add(conversation)

        # Add both users as members
        conversation.members.append(current_user)
        conversation.members.append(participant)

        session.commit()
        session.refresh(conversation)

        print(f"Created new conversation: {conversation.id}")

        # Prepare conversation data for broadcast
        conversation_data = {
            "id": conversation.id,
            "conversation_type": conversation.conversation_type,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "workspace_id": conversation.workspace_id,
            "participant_1": {
                "id": str(current_user.id),
                "username": current_user.username,
                "display_name": current_user.display_name,
                "avatar_url": get_presigned_avatar_url(current_user.avatar_url),
                "is_online": manager.is_user_online(current_user.id),
                "email": current_user.email,
            },
            "participant_2": {
                "id": str(participant.id),
                "username": participant.username,
                "display_name": participant.display_name,
                "avatar_url": get_presigned_avatar_url(participant.avatar_url),
                "is_online": manager.is_user_online(participant.id),
                "email": participant.email,
            },
        }

        # Broadcast to both participants
        await manager.broadcast_to_users(
            [current_user.id, participant.id],
            WebSocketMessageType.CONVERSATION_CREATED,
            conversation_data,
        )

        return {
            "id": conversation.id,
            "conversation_type": conversation.conversation_type,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "workspace_id": conversation.workspace_id,
        }


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a conversation and all its messages and files."""
    print(f"\n=== Deleting Conversation {conversation_id} ===")
    print(f"Requested by user: {current_user.id}")

    with Session(db) as session:
        # Get the conversation
        conversation = session.get(Conversation, conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Check if user has permission to delete
        if conversation.conversation_type == ChannelType.DIRECT:
            if current_user.id not in [
                conversation.participant_1_id,
                conversation.participant_2_id,
            ]:
                raise HTTPException(
                    status_code=403, detail="Not authorized to delete this conversation"
                )
        else:
            # For channels, check if user is a member
            if current_user not in conversation.members:
                raise HTTPException(
                    status_code=403, detail="Not authorized to delete this conversation"
                )

        # Get all participants for notification
        participant_ids = [member.id for member in conversation.members]

        # Get all messages with their file attachments
        messages = session.exec(
            select(Message).where(Message.conversation_id == conversation_id)
        ).all()

        # Delete all file attachments from S3 and database
        for message in messages:
            file_attachments = session.exec(
                select(FileAttachment).where(FileAttachment.message_id == message.id)
            ).all()

            for attachment in file_attachments:
                # Delete from S3
                try:
                    storage.delete_file(attachment.s3_key)
                except Exception as e:
                    print(f"Error deleting file {attachment.s3_key} from S3: {e}")

                # Delete from database
                session.delete(attachment)

            # Delete the message
            session.delete(message)

        # Delete the conversation
        session.delete(conversation)
        session.commit()

        print(f"Successfully deleted conversation {conversation_id}")

        # Notify all participants
        await manager.broadcast_to_users(
            participant_ids,
            WebSocketMessageType.CONVERSATION_DELETED,
            {
                "id": str(conversation_id),
                "conversation_type": conversation.conversation_type,
            },
        )

        return {"status": "success", "message": "Conversation deleted successfully"}
