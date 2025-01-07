from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Set, Any
from uuid import UUID
from datetime import datetime, UTC
from app.websocket_utils import SessionManager, UserManager, UserSessionManager
from app.auth_utils import auth_utils
from app.models import User, Message, Reaction
import json
from enum import Enum

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

class ConnectionManager:
    def __init__(self):
        # Singleton instance
        self.active_connections: Dict[UUID, Dict[str, WebSocket]] = {}  # user_id -> {connection_id: websocket}
        self.channel_subscribers: Dict[UUID, Set[UUID]] = {}  # channel_id -> set of user_ids
        self.workspace_subscribers: Dict[UUID, Set[UUID]] = {}  # workspace_id -> set of user_ids
        self.conversation_subscribers: Dict[UUID, Set[UUID]] = {}  # conversation_id -> set of user_ids
        self.session_manager = SessionManager()
        self.user_manager = UserManager()
        self.user_session_manager = UserSessionManager()

    async def connect(self, websocket: WebSocket, token: str) -> tuple[User, str]:
        """
        Authenticate and connect a websocket.
        Returns (user, connection_id) tuple.
        """
        try:
            # Verify token and get user
            print("Verifying token...")
            token_data = auth_utils.verify_token(token)
            user = self.user_manager.get_user_by_id(token_data.user_id)
            print(f"User verified: {user.id}")
            
            # Accept connection
            await websocket.accept()
            
            # Generate unique connection ID
            connection_id = f"{user.id}-{datetime.now(UTC).timestamp()}"
            
            # Store connection
            if user.id not in self.active_connections:
                self.active_connections[user.id] = {}
            self.active_connections[user.id][connection_id] = websocket
            print(f"Connection stored for user {user.id} with connection ID {connection_id}")
            
            # Create session and update user status
            self.session_manager.create_user_session(user.id, connection_id)
            self.session_manager.update_user_status(user.id, True)
            print(f"Session created and user status updated for user {user.id}")
            
            return user, connection_id
        except Exception as e:
            print(f"Error during WebSocket connection: {e}")
            raise

    async def disconnect(self, user_id: UUID, connection_id: str):
        """Handle websocket disconnection."""
        # Remove connection
        if user_id in self.active_connections:
            self.active_connections[user_id].pop(connection_id, None)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        
        # Delete session and update user status if no active connections
        self.session_manager.delete_user_session(user_id, connection_id)
        if user_id not in self.active_connections:
            self.session_manager.update_user_status(user_id, False)

    def subscribe_to_channel(self, user_id: UUID, channel_id: UUID):
        """Subscribe a user to channel updates."""
        print(f"Adding user {user_id} to channel {channel_id} subscribers")
        if channel_id not in self.channel_subscribers:
            self.channel_subscribers[channel_id] = set()
        self.channel_subscribers[channel_id].add(user_id)
        print(f"Channel {channel_id} subscribers: {self.channel_subscribers[channel_id]}")

    def subscribe_to_workspace(self, user_id: UUID, workspace_id: UUID):
        """Subscribe a user to workspace updates."""
        if workspace_id not in self.workspace_subscribers:
            self.workspace_subscribers[workspace_id] = set()
        self.workspace_subscribers[workspace_id].add(user_id)

    def unsubscribe_from_channel(self, user_id: UUID, channel_id: UUID):
        """Unsubscribe a user from channel updates."""
        if channel_id in self.channel_subscribers:
            self.channel_subscribers[channel_id].discard(user_id)
            if not self.channel_subscribers[channel_id]:
                del self.channel_subscribers[channel_id]

    def unsubscribe_from_workspace(self, user_id: UUID, workspace_id: UUID):
        """Unsubscribe a user from workspace updates."""
        if workspace_id in self.workspace_subscribers:
            self.workspace_subscribers[workspace_id].discard(user_id)
            if not self.workspace_subscribers[workspace_id]:
                del self.workspace_subscribers[workspace_id]

    def subscribe_to_conversation(self, user_id: UUID, conversation_id: UUID):
        """Subscribe a user to conversation updates."""
        print(f"Adding user {user_id} to conversation {conversation_id} subscribers")
        if conversation_id not in self.conversation_subscribers:
            self.conversation_subscribers[conversation_id] = set()
        self.conversation_subscribers[conversation_id].add(user_id)
        print(f"Conversation {conversation_id} subscribers: {self.conversation_subscribers[conversation_id]}")

    def unsubscribe_from_conversation(self, user_id: UUID, conversation_id: UUID):
        """Unsubscribe a user from conversation updates."""
        if conversation_id in self.conversation_subscribers:
            self.conversation_subscribers[conversation_id].discard(user_id)
            if not self.conversation_subscribers[conversation_id]:
                del self.conversation_subscribers[conversation_id]

    async def broadcast_to_channel(self, channel_id: UUID, message_type: WebSocketMessageType, data: Any):
        """Broadcast a message to all subscribers of a channel."""
        if channel_id not in self.channel_subscribers:
            print(f"No subscribers for channel {channel_id}")
            return
        
        payload = {
            "type": message_type,
            "data": data
        }
        
        print(f"Broadcasting to channel {channel_id}: {payload}")
        json_payload = json.dumps(payload, cls=UUIDEncoder)
        
        for user_id in self.channel_subscribers[channel_id]:
            print(f"Sending to user {user_id}")
            if user_id in self.active_connections:
                for websocket in self.active_connections[user_id].values():
                    try:
                        await websocket.send_text(json_payload)
                        print(f"Successfully sent to user {user_id}")
                    except Exception as e:
                        print(f"Error sending to user {user_id}: {e}")

    async def broadcast_to_workspace(self, workspace_id: UUID, message_type: WebSocketMessageType, data: Any):
        """Broadcast a message to all subscribers of a workspace."""
        if workspace_id not in self.workspace_subscribers:
            return
        
        payload = {
            "type": message_type,
            "data": data
        }
        
        json_payload = json.dumps(payload)
        for user_id in self.workspace_subscribers[workspace_id]:
            if user_id in self.active_connections:
                for websocket in self.active_connections[user_id].values():
                    await websocket.send_json(json_payload)

    async def handle_ping(self, user_id: UUID, connection_id: str):
        """Handle ping message and update last seen."""
        self.user_session_manager.update_last_ping(connection_id)
        self.session_manager.update_user_last_active(user_id)

    async def handle_message(self, user_id: UUID, data: dict):
        """Handle new message."""
        try:
            # Create message
            print(f"Creating message for user {user_id} in channel {data['channel_id']}")
            message = Message(
                content=data["content"],
                channel_id=data["channel_id"],
                parent_id=data.get("parent_id")  # Optional for thread replies
            )
            created_message = self.message_manager.create_message(message, user_id)
            print(f"Message created with ID {created_message.id}")
            
            # Broadcast to channel
            await self.broadcast_to_channel(
                message.channel_id,
                WebSocketMessageType.MESSAGE_SENT if not message.parent_id else WebSocketMessageType.THREAD_REPLY,
                created_message.dict()
            )
            print(f"Message broadcasted to channel {message.channel_id}")
        except Exception as e:
            print(f"Error handling message: {e}")
            raise

    async def handle_reaction(self, user_id: UUID, data: dict):
        """Handle new reaction."""
        # Create reaction
        reaction = Reaction(
            emoji=data["emoji"],
            message_id=data["message_id"],
            user_id=user_id
        )
        created_reaction = self.reaction_manager.add_reaction(reaction, user_id)
        
        # Get channel ID from message
        message = self.message_manager.get_message_by_id(data["message_id"], user_id)
        
        # Broadcast to channel
        await self.broadcast_to_channel(
            message.channel_id,
            WebSocketMessageType.REACTION_SENT,
            created_reaction.dict()
        )

    async def handle_typing(self, user_id: UUID, data: dict):
        """Handle typing indicator."""
        await self.broadcast_to_channel(
            data["channel_id"],
            WebSocketMessageType.USER_TYPING,
            {
                "user_id": str(user_id),
                "channel_id": str(data["channel_id"]),
                "timestamp": datetime.now(UTC).isoformat()
            }
        )

    async def broadcast_to_users(self, user_ids: list[UUID], message_type: WebSocketMessageType, data: dict):
        """Broadcast a message to specific users."""
        message = {
            "type": message_type,
            "data": data
        }
        for user_id in user_ids:
            if str(user_id) in self.active_connections:
                websocket = self.active_connections[str(user_id)]
                await websocket.send_json(message)

    async def broadcast_to_conversation(self, conversation_id: UUID, message_type: WebSocketMessageType, data: Any):
        """Broadcast a message to all subscribers of a conversation."""
        if conversation_id not in self.conversation_subscribers:
            print(f"No subscribers for conversation {conversation_id}")
            return
        
        payload = {
            "type": message_type,
            "data": data
        }
        
        print(f"Broadcasting to conversation {conversation_id}: {payload}")
        json_payload = json.dumps(payload, cls=UUIDEncoder)
        
        for user_id in self.conversation_subscribers[conversation_id]:
            print(f"Sending to user {user_id}")
            if user_id in self.active_connections:
                for websocket in self.active_connections[user_id].values():
                    try:
                        await websocket.send_text(json_payload)
                        print(f"Successfully sent to user {user_id}")
                    except Exception as e:
                        print(f"Error sending to user {user_id}: {e}")

# Create global instance
manager = ConnectionManager() 