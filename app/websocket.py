import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, Set
from uuid import UUID, uuid4

from fastapi import WebSocket
from sqlmodel import Session, select

from app.managers.user_manager import user_manager
from app.models import (
    User,
    UserSession,
)
from app.storage import Storage
from app.utils.auth import auth_utils
from app.utils.db import get_db

# Initialize storage
storage = Storage()


class PermissionError(Exception):
    """Raised when a user doesn't have required permissions"""

    pass


class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class WebSocketMessageType(str, Enum):
    MESSAGE_SENT = "message_sent"
    REACTION_SENT = "reaction_sent"
    MESSAGE_DELETED = "message_deleted"
    REACTION_DELETED = "reaction_deleted"
    THREAD_REPLY = "thread_reply"
    USER_TYPING = "user_typing"
    USER_PRESENCE = "user_presence"
    PING = "ping"
    FILE_DELETED = "file_deleted"
    CONVERSATION_CREATED = "conversation_created"
    CONVERSATION_DELETED = "conversation_deleted"
    CHANNEL_CREATED = "channel_created"
    CHANNEL_DELETED = "channel_deleted"
    WORKSPACE_DELETED = "workspace_deleted"
    WORKSPACE_MEMBER_LEFT = "workspace_member_left"
    WORKSPACE_MEMBER_ADDED = "workspace_member_added"


"""SESSION MANAGEMENT"""


class SessionManager:
    def update_user_last_active(self, user_id: UUID):
        """
        Update the user's last active time in the database.
        """
        engine = get_db()
        with Session(engine) as session:
            try:
                print(f"Updating last active time for user {user_id}")
                user = session.exec(select(User).where(User.id == user_id)).first()
                if user:
                    user.last_active = datetime.now(UTC)
                    session.add(user)
                    session.commit()
            except Exception as e:
                print(f"Error updating last active time for {user_id}: {e}")
                raise

    def create_user_session(self, user_id: UUID, session_id: str):
        """
        Create a new user session in the database.
        """
        engine = get_db()
        with Session(engine) as session:
            try:
                print(
                    f"Creating session for user {user_id} with session ID {session_id}"
                )
                new_session = UserSession(
                    user_id=user_id,
                    session_id=session_id,
                    connected_at=datetime.now(UTC),
                    last_ping=datetime.now(UTC),
                )
                session.add(new_session)
                session.commit()
            except Exception as e:
                print(f"Error creating session for {user_id}: {e}")
                raise

    def delete_user_session(self, user_id: UUID, session_id: str):
        """
        Delete a user session from the database.
        """
        engine = get_db()
        with Session(engine) as session:
            try:
                print(
                    f"Deleting session for user {user_id} with session ID {session_id}"
                )
                stmt = select(UserSession).where(
                    UserSession.user_id == user_id, UserSession.session_id == session_id
                )
                user_session = session.exec(stmt).first()
                if user_session:
                    session.delete(user_session)
                    session.commit()
            except Exception as e:
                print(f"Error deleting session for {user_id}: {e}")
                raise


# Create a global instance
session_manager = SessionManager()


class ConnectionManager:
    def __init__(self):
        # Singleton instance
        self.active_connections: Dict[UUID, Dict[str, WebSocket]] = {}
        self.channel_subscriptions: Dict[
            UUID, Set[UUID]
        ] = {}  # channel_id -> set of user_ids
        self.workspace_subscriptions: Dict[
            UUID, Set[UUID]
        ] = {}  # workspace_id -> set of user_ids
        self.conversation_subscriptions: Dict[
            UUID, Set[UUID]
        ] = {}  # conversation_id -> set of user_ids
        self.session_manager = session_manager

    def is_user_online(self, user_id: UUID) -> bool:
        """Check if a user has any active connections."""
        return user_id in self.active_connections and bool(
            self.active_connections[user_id]
        )

    async def connect(self, websocket: WebSocket, token: str) -> tuple[User, str]:
        """
        Connect and authenticate a WebSocket connection.
        Returns the authenticated user and a unique connection ID.
        """
        await websocket.accept()

        try:
            # Verify token and get user
            token_data = auth_utils.verify_token(token)
            user = user_manager.get_user_by_id(token_data.user_id)

            # Generate a unique connection ID
            connection_id = str(uuid4())

            # Initialize user's connections if not exists
            if user.id not in self.active_connections:
                self.active_connections[user.id] = {}

            # Store the connection
            self.active_connections[user.id][connection_id] = websocket

            # Create session
            self.session_manager.create_user_session(user.id, connection_id)

            # Broadcast presence update
            await self.broadcast_presence_update(user.id, True)

            return user, connection_id

        except Exception as e:
            await websocket.close(code=1008, reason=str(e))
            raise

    async def disconnect(self, user_id: UUID, connection_id: str):
        """
        Disconnect a WebSocket connection.
        """
        if user_id in self.active_connections:
            # Remove the specific connection
            self.active_connections[user_id].pop(connection_id, None)

            # If no more connections, clean up user entry
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

            # Delete session
            self.session_manager.delete_user_session(user_id, connection_id)

            # If user has no more active connections, broadcast offline status
            if user_id not in self.active_connections:
                await self.broadcast_presence_update(user_id, False)

    async def broadcast_presence_update(self, user_id: UUID, is_online: bool):
        """
        Broadcast a user's presence update to all connected users.
        """
        print(f"Broadcasting presence update for user {user_id}: {is_online}")

        # Get user details for the broadcast
        user = user_manager.get_user_by_id(user_id)
        if not user:
            print(f"User {user_id} not found")
            return

        # Get pre-signed URL for avatar if it exists
        avatar_url = (
            storage.create_presigned_url(user.avatar_url) if user.avatar_url else None
        )

        # Prepare presence update message
        presence_message = {
            "type": WebSocketMessageType.USER_PRESENCE,
            "data": {
                "user": {
                    "id": str(user.id),
                    "username": user.username,
                    "display_name": user.display_name,
                    "avatar_url": avatar_url,
                    "is_online": is_online,
                }
            },
        }

        # Broadcast to all connected users
        for user_connections in self.active_connections.values():
            for connection in user_connections.values():
                try:
                    await connection.send_json(presence_message)
                except Exception as e:
                    print(f"Error sending presence update: {e}")

    async def handle_ping(self, user_id: UUID, connection_id: str):
        """Handle ping message from client."""
        self.session_manager.update_user_last_active(user_id)

    def get_active_users(self) -> list[UUID]:
        """Get list of currently active user IDs."""
        return list(self.active_connections.keys())

    def subscribe_to_channel(self, user_id: UUID, channel_id: UUID):
        """Subscribe a user to a channel."""
        if channel_id not in self.channel_subscriptions:
            self.channel_subscriptions[channel_id] = set()
        self.channel_subscriptions[channel_id].add(user_id)

    def subscribe_to_workspace(self, user_id: UUID, workspace_id: UUID):
        """Subscribe a user to a workspace."""
        if workspace_id not in self.workspace_subscriptions:
            self.workspace_subscriptions[workspace_id] = set()
        self.workspace_subscriptions[workspace_id].add(user_id)

    def unsubscribe_from_channel(self, user_id: UUID, channel_id: UUID):
        """Unsubscribe a user from a channel."""
        if channel_id in self.channel_subscriptions:
            self.channel_subscriptions[channel_id].discard(user_id)

    def unsubscribe_from_workspace(self, user_id: UUID, workspace_id: UUID):
        """Unsubscribe a user from a workspace."""
        if workspace_id in self.workspace_subscriptions:
            self.workspace_subscriptions[workspace_id].discard(user_id)

    def subscribe_to_conversation(self, user_id: UUID, conversation_id: UUID):
        """Subscribe a user to a conversation."""
        if conversation_id not in self.conversation_subscriptions:
            self.conversation_subscriptions[conversation_id] = set()
        self.conversation_subscriptions[conversation_id].add(user_id)

    def unsubscribe_from_conversation(self, user_id: UUID, conversation_id: UUID):
        """Unsubscribe a user from a conversation."""
        if conversation_id in self.conversation_subscriptions:
            self.conversation_subscriptions[conversation_id].discard(user_id)

    async def broadcast_to_channel(
        self, channel_id: UUID, message_type: WebSocketMessageType, data: Any
    ):
        """
        Broadcast a message to all users subscribed to a channel.
        """
        if channel_id not in self.channel_subscriptions:
            return

        message = {"type": message_type, "data": data}

        encoded_message = json.dumps(message, cls=UUIDEncoder)

        for user_id in self.channel_subscriptions[channel_id]:
            if user_id in self.active_connections:
                for websocket in self.active_connections[user_id].values():
                    try:
                        await websocket.send_text(encoded_message)
                    except Exception as e:
                        print(f"Error sending message to user {user_id}: {e}")

    async def broadcast_to_workspace(
        self, workspace_id: UUID, message_type: WebSocketMessageType, data: Any
    ):
        """
        Broadcast a message to all users subscribed to a workspace.
        """
        if workspace_id not in self.workspace_subscriptions:
            return

        message = {"type": message_type, "data": data}

        encoded_message = json.dumps(message, cls=UUIDEncoder)

        for user_id in self.workspace_subscriptions[workspace_id]:
            if user_id in self.active_connections:
                for websocket in self.active_connections[user_id].values():
                    try:
                        await websocket.send_text(encoded_message)
                    except Exception as e:
                        print(f"Error sending message to user {user_id}: {e}")

    async def broadcast_to_users(
        self, user_ids: list[UUID], message_type: WebSocketMessageType, data: dict
    ):
        """
        Broadcast a message to specific users.
        """
        message = {"type": message_type, "data": data}

        encoded_message = json.dumps(message, cls=UUIDEncoder)

        for user_id in user_ids:
            if user_id in self.active_connections:
                for websocket in self.active_connections[user_id].values():
                    try:
                        await websocket.send_text(encoded_message)
                    except Exception as e:
                        print(f"Error sending message to user {user_id}: {e}")

    async def broadcast_to_conversation(
        self, conversation_id: UUID, message_type: WebSocketMessageType, data: Any
    ):
        """Broadcast a message to all users subscribed to a conversation."""
        print(f"\n🔍 Broadcasting to conversation {conversation_id}")
        print(f"Message type: {message_type}")
        print(f"Data: {data}")

        # Log all conversation subscriptions
        print("\nAll conversation subscriptions:")
        for conv_id, user_ids in self.conversation_subscriptions.items():
            print(f"Conversation {conv_id}: {len(user_ids)} subscribers")
            print(f"Subscribed users: {user_ids}")

        # Get subscribers for this conversation
        subscribers = self.conversation_subscriptions.get(conversation_id, set())
        print(f"\nSubscribers for conversation {conversation_id}: {subscribers}")

        # Log active connections
        print("\nActive connections:")
        for user_id, connections in self.active_connections.items():
            print(f"User {user_id}: {len(connections)} connections")

        # Prepare message
        message = {
            "type": message_type,
            "data": data,
        }
        encoded_message = json.dumps(message, cls=UUIDEncoder)

        # Broadcast to subscribers
        for user_id in subscribers:
            if user_id in self.active_connections:
                connections = self.active_connections[user_id]
                print(f"\nSending to user {user_id} ({len(connections)} connections)")
                for connection_id, websocket in connections.items():
                    try:
                        print(f"Sending via connection {connection_id}")
                        await websocket.send_text(encoded_message)
                        print(f"Successfully sent to connection {connection_id}")
                    except Exception as e:
                        print(f"Error sending to connection {connection_id}: {e}")
            else:
                print(f"User {user_id} has no active connections")

        print("\nBroadcast complete\n")


# Create a global instance
manager = ConnectionManager()
