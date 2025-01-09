from fastapi import WebSocket, HTTPException
from typing import Dict, Set, Any
from uuid import UUID, uuid4
from datetime import datetime, UTC, timedelta
from app.utils.auth import auth_utils
from app.managers.user_manager import user_manager
import json
from enum import Enum
from app.models import (
    User, UserSession, Workspace, Conversation, Message, WorkspaceMember, 
    ConversationMember, FileAttachment, Reaction
)
from sqlmodel import Session, select, or_, func
from app.utils.db import get_db
from typing import List
from pydantic import BaseModel

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

"""SESSION MANAGEMENT"""

class SessionManager:
    def update_user_status(self, user_id: UUID, is_online: bool):
        """
        Update the user's status in the database.
        Only marks a user as offline if they have no remaining active sessions.
        """
        engine = get_db()
        with Session(engine) as session:
            try:
                if not is_online:
                    # Check if user has any remaining active sessions
                    active_sessions = session.exec(
                        select(UserSession).where(UserSession.user_id == user_id)
                    ).all()
                    
                    # Only mark as offline if there are no active sessions
                    if not active_sessions:
                        print(f"Marking user {user_id} as offline")
                        user = session.exec(select(User).where(User.id == user_id)).first()
                        if user:
                            user.is_online = is_online
                            session.add(user)
                            session.commit()
                else:
                    # If marking online, update immediately
                    print(f"Marking user {user_id} as online")
                    user = session.exec(select(User).where(User.id == user_id)).first()
                    if user:
                        user.is_online = is_online
                        session.add(user)
                        session.commit()
            except Exception as e:
                print(f"Error updating user status for {user_id}: {e}")
                raise

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
                print(f"Creating session for user {user_id} with session ID {session_id}")
                new_session = UserSession(
                    user_id=user_id,
                    session_id=session_id,
                    connected_at=datetime.now(UTC),
                    last_ping=datetime.now(UTC)
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
                print(f"Deleting session for user {user_id} with session ID {session_id}")
                stmt = select(UserSession).where(
                    UserSession.user_id == user_id,
                    UserSession.session_id == session_id
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
        self.channel_subscriptions: Dict[UUID, Set[UUID]] = {}  # channel_id -> set of user_ids
        self.workspace_subscriptions: Dict[UUID, Set[UUID]] = {}  # workspace_id -> set of user_ids
        self.conversation_subscriptions: Dict[UUID, Set[UUID]] = {}  # conversation_id -> set of user_ids
        self.session_manager = session_manager

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
            
            # Create session and update user status
            self.session_manager.create_user_session(user.id, connection_id)
            self.session_manager.update_user_status(user.id, True)
            
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
            
            # Update session and user status
            self.session_manager.delete_user_session(user_id, connection_id)
            if user_id not in self.active_connections:
                self.session_manager.update_user_status(user_id, False)

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

    async def broadcast_to_channel(self, channel_id: UUID, message_type: WebSocketMessageType, data: Any):
        """
        Broadcast a message to all users subscribed to a channel.
        """
        if channel_id not in self.channel_subscriptions:
            return
        
        message = {
            "type": message_type,
            "data": data
        }
        
        encoded_message = json.dumps(message, cls=UUIDEncoder)
        
        for user_id in self.channel_subscriptions[channel_id]:
            if user_id in self.active_connections:
                for websocket in self.active_connections[user_id].values():
                    try:
                        await websocket.send_text(encoded_message)
                    except Exception as e:
                        print(f"Error sending message to user {user_id}: {e}")

    async def broadcast_to_workspace(self, workspace_id: UUID, message_type: WebSocketMessageType, data: Any):
        """
        Broadcast a message to all users subscribed to a workspace.
        """
        if workspace_id not in self.workspace_subscriptions:
            return
        
        message = {
            "type": message_type,
            "data": data
        }
        
        encoded_message = json.dumps(message, cls=UUIDEncoder)
        
        for user_id in self.workspace_subscriptions[workspace_id]:
            if user_id in self.active_connections:
                for websocket in self.active_connections[user_id].values():
                    try:
                        await websocket.send_text(encoded_message)
                    except Exception as e:
                        print(f"Error sending message to user {user_id}: {e}")

    async def handle_ping(self, user_id: UUID, connection_id: str):
        """Handle ping message from client."""
        self.session_manager.update_user_last_active(user_id)

    async def broadcast_to_users(self, user_ids: list[UUID], message_type: WebSocketMessageType, data: dict):
        """
        Broadcast a message to specific users.
        """
        message = {
            "type": message_type,
            "data": data
        }
        
        encoded_message = json.dumps(message, cls=UUIDEncoder)
        
        for user_id in user_ids:
            if user_id in self.active_connections:
                for websocket in self.active_connections[user_id].values():
                    try:
                        await websocket.send_text(encoded_message)
                    except Exception as e:
                        print(f"Error sending message to user {user_id}: {e}")

    async def broadcast_to_conversation(self, conversation_id: UUID, message_type: WebSocketMessageType, data: Any):
        """
        Broadcast a message to all users in a conversation.
        """
        if conversation_id not in self.conversation_subscriptions:
            return
        
        message = {
            "type": message_type,
            "data": data
        }
        
        encoded_message = json.dumps(message, cls=UUIDEncoder)
        
        for user_id in self.conversation_subscriptions[conversation_id]:
            if user_id in self.active_connections:
                for websocket in self.active_connections[user_id].values():
                    try:
                        await websocket.send_text(encoded_message)
                    except Exception as e:
                        print(f"Error sending message to user {user_id}: {e}")

# Create a global instance
manager = ConnectionManager() 