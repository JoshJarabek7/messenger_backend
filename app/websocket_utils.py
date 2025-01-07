from fastapi import WebSocket, HTTPException
from uuid import UUID
from app.models import (
    User, UserSession, Workspace, Channel, Message, WorkspaceMember, 
    ChannelMember, FileAttachment, Reaction
)
from sqlmodel import Session, select, or_, func
from app.db import get_db
from datetime import datetime, UTC, timedelta
from enum import Enum
from typing import List
from passlib.context import CryptContext
from pydantic import EmailStr, BaseModel

# Password hashing configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class PermissionError(Exception):
    """Raised when a user doesn't have required permissions"""
    pass

class UserExistsError(Exception):
    """Raised when trying to create a user that already exists"""
    pass

class WorkspaceRole(str, Enum):
    ADMIN = "admin"
    MEMBER = "member"

"""
Should update DB with last active time and is_online status when a user connects to the websocket
Should update DB with last active time and is_online status when a user disconnects from the websocket

Store nested Workspace, Channels, Users

Different types of inputs, like sent message, reactions, etc.
"""


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

"""USER MANAGEMENT"""

class UserManager:
    def _hash_password(self, password: str) -> str:
        """Hash a password using bcrypt."""
        return pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)

    def get_user_by_id(self, user_id: UUID) -> User:
        """Get a user by their ID."""
        engine = get_db()
        with Session(engine) as session:
            try:
                print(f"Fetching user by ID {user_id}")
                user = session.exec(
                    select(User).where(User.id == user_id)
                ).first()
                if not user:
                    raise HTTPException(status_code=404, detail="User not found")
                return user
            except Exception as e:
                print(f"Error fetching user by ID {user_id}: {e}")
                raise

    def get_user_by_email(self, email: str) -> User | None:
        """Get a user by their email."""
        engine = get_db()
        with Session(engine) as session:
            return session.exec(
                select(User).where(User.email == email)
            ).first()

    def get_user_by_username(self, username: str) -> User | None:
        """Get a user by their username."""
        engine = get_db()
        with Session(engine) as session:
            return session.exec(
                select(User).where(User.username == username)
            ).first()

    def create_user(self, email: EmailStr, username: str, password: str, display_name: str | None = None) -> User:
        """
        Create a new user with proper password hashing.
        Raises UserExistsError if email or username already exists.
        """
        engine = get_db()
        with Session(engine) as session:
            # Check if email exists
            if self.get_user_by_email(email):
                raise UserExistsError("A user with this email already exists")
            
            # Check if username exists
            if self.get_user_by_username(username):
                raise UserExistsError("A user with this username already exists")
            
            # Create new user with hashed password
            user = User(
                email=email,
                username=username,
                hashed_password=self._hash_password(password),
                display_name=display_name or username,
                is_online=True,
                last_active=datetime.now(UTC)
            )
            
            session.add(user)
            session.commit()
            session.refresh(user)
            return user

    def join_workspace(self, user_id: UUID, workspace_id: UUID, auto_join_public: bool = True):
        """
        Add a user to a workspace.
        Optionally auto-join all public channels.
        """
        engine = get_db()
        with Session(engine) as session:
            # Check if user is already a member
            existing_member = session.exec(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == workspace_id,
                    WorkspaceMember.user_id == user_id
                )
            ).first()
            
            if existing_member:
                return  # Already a member
            
            # Add to workspace
            member = WorkspaceMember(
                workspace_id=workspace_id,
                user_id=user_id,
                role=WorkspaceRole.MEMBER
            )
            session.add(member)
            session.commit()
            
            if auto_join_public:
                # Get all public channels in workspace
                public_channels = session.exec(
                    select(Channel).where(
                        Channel.workspace_id == workspace_id,
                        Channel.channel_type == "public"
                    )
                ).all()
                
                # Add user to all public channels
                for channel in public_channels:
                    channel_member = ChannelMember(
                        channel_id=channel.id,
                        user_id=user_id,
                        is_admin=False
                    )
                    session.add(channel_member)
                
                session.commit()

    def leave_workspace(self, user_id: UUID, workspace_id: UUID):
        """Remove a user from a workspace and all its channels."""
        engine = get_db()
        with Session(engine) as session:
            # First remove from all channels in the workspace
            channels = session.exec(
                select(Channel).where(Channel.workspace_id == workspace_id)
            ).all()
            
            for channel in channels:
                session.exec(
                    select(ChannelMember)
                    .where(
                        ChannelMember.channel_id == channel.id,
                        ChannelMember.user_id == user_id
                    )
                    .delete()
                )
            
            # Then remove from workspace
            session.exec(
                select(WorkspaceMember)
                .where(
                    WorkspaceMember.workspace_id == workspace_id,
                    WorkspaceMember.user_id == user_id
                )
                .delete()
            )
            
            session.commit()

    def delete_user(self, user_id: UUID):
        """Delete a user and clean up all their memberships."""
        engine = get_db()
        with Session(engine) as session:
            # Delete all channel memberships
            session.exec(
                select(ChannelMember)
                .where(ChannelMember.user_id == user_id)
                .delete()
            )
            
            # Delete all workspace memberships
            session.exec(
                select(WorkspaceMember)
                .where(WorkspaceMember.user_id == user_id)
                .delete()
            )
            
            # Delete all sessions
            session.exec(
                select(UserSession)
                .where(UserSession.user_id == user_id)
                .delete()
            )
            
            # Finally delete the user
            user = session.exec(select(User).where(User.id == user_id)).first()
            if user:
                session.delete(user)
                session.commit()

    def update_user(self, user_id: UUID, updates: dict):
        """Update user information."""
        engine = get_db()
        with Session(engine) as session:
            user = session.exec(select(User).where(User.id == user_id)).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Handle password updates separately to ensure hashing
            if "password" in updates:
                updates["hashed_password"] = self._hash_password(updates.pop("password"))
            
            # Check email/username uniqueness if being updated
            if "email" in updates:
                existing = self.get_user_by_email(updates["email"])
                if existing and existing.id != user_id:
                    raise UserExistsError("A user with this email already exists")
            
            if "username" in updates:
                existing = self.get_user_by_username(updates["username"])
                if existing and existing.id != user_id:
                    raise UserExistsError("A user with this username already exists")
            
            for key, value in updates.items():
                setattr(user, key, value)
            
            session.add(user)
            session.commit()
            session.refresh(user)
            return user

    def authenticate_user(self, email: str, password: str) -> User | None:
        """Authenticate a user by email and password."""
        user = self.get_user_by_email(email)
        if not user:
            return None
        if not self.verify_password(password, user.hashed_password):
            return None
        return user

"""WORKSPACE MANAGEMENT"""

class WorkspaceManager:
    def _check_workspace_admin(self, session: Session, workspace_id: UUID, user_id: UUID) -> bool:
        """Check if user is an admin of the workspace"""
        member = session.exec(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.role == WorkspaceRole.ADMIN
            )
        ).first()
        return member is not None

    def get_workspace_by_id(self, workspace_id: UUID) -> Workspace:
        """Get a workspace by its ID."""
        engine = get_db()
        with Session(engine) as session:
            workspace = session.exec(
                select(Workspace).where(Workspace.id == workspace_id)
            ).first()
            if not workspace:
                raise HTTPException(status_code=404, detail="Workspace not found")
            return workspace

    def create_workspace(self, workspace: Workspace, creator_id: UUID):
        """Create a new workspace and set creator as admin."""
        engine = get_db()
        with Session(engine) as session:
            # Set creator
            workspace.created_by_id = creator_id
            session.add(workspace)
            session.commit()
            session.refresh(workspace)
            
            # Add creator as admin
            member = WorkspaceMember(
                workspace_id=workspace.id,
                user_id=creator_id,
                role=WorkspaceRole.ADMIN
            )
            session.add(member)
            session.commit()

    def delete_workspace(self, workspace_id: UUID, user_id: UUID):
        """Delete a workspace if user is admin."""
        engine = get_db()
        with Session(engine) as session:
            if not self._check_workspace_admin(session, workspace_id, user_id):
                raise PermissionError("Only workspace admins can delete workspaces")
            
            workspace = session.exec(
                select(Workspace).where(Workspace.id == workspace_id)
            ).first()
            if not workspace:
                raise HTTPException(status_code=404, detail="Workspace not found")
            
            session.delete(workspace)
            session.commit()

    def update_workspace(self, workspace_id: UUID, updates: dict, user_id: UUID):
        """Update workspace if user is admin."""
        engine = get_db()
        with Session(engine) as session:
            if not self._check_workspace_admin(session, workspace_id, user_id):
                raise PermissionError("Only workspace admins can update workspaces")
            
            workspace = session.exec(
                select(Workspace).where(Workspace.id == workspace_id)
            ).first()
            if not workspace:
                raise HTTPException(status_code=404, detail="Workspace not found")
            
            for key, value in updates.items():
                setattr(workspace, key, value)
            
            session.add(workspace)
            session.commit()
            session.refresh(workspace)
            return workspace

"""CHANNEL MANAGEMENT"""

class ChannelManager:
    def _check_workspace_admin(self, session: Session, workspace_id: UUID, user_id: UUID) -> bool:
        """Check if user is an admin of the workspace"""
        member = session.exec(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.role == WorkspaceRole.ADMIN
            )
        ).first()
        return member is not None

    def _check_channel_member(self, session: Session, channel_id: UUID, user_id: UUID) -> bool:
        """Check if user is a member of the channel"""
        member = session.exec(
            select(ChannelMember).where(
                ChannelMember.channel_id == channel_id,
                ChannelMember.user_id == user_id
            )
        ).first()
        return member is not None

    def get_channel_by_id(self, channel_id: UUID, user_id: UUID) -> Channel:
        """Get a channel by its ID if user is a member."""
        engine = get_db()
        with Session(engine) as session:
            channel = session.exec(
                select(Channel).where(Channel.id == channel_id)
            ).first()
            if not channel:
                raise HTTPException(status_code=404, detail="Channel not found")
            
            # For public channels, allow viewing without membership
            if channel.channel_type != "public":
                if not self._check_channel_member(session, channel_id, user_id):
                    raise PermissionError("You must be a member to view this channel")
            
            return channel
    
    def create_channel(self, channel: Channel, user_id: UUID):
        """Create channel if user is workspace admin."""
        engine = get_db()
        with Session(engine) as session:
            if not self._check_workspace_admin(session, channel.workspace_id, user_id):
                raise PermissionError("Only workspace admins can create channels")
            
            session.add(channel)
            session.commit()
            session.refresh(channel)
            
            # Add creator as channel member
            member = ChannelMember(
                channel_id=channel.id,
                user_id=user_id,
                is_admin=True
            )
            session.add(member)
            session.commit()
            return channel

    def delete_channel(self, channel_id: UUID, user_id: UUID):
        """Delete channel if user is workspace admin."""
        engine = get_db()
        with Session(engine) as session:
            channel = session.exec(
                select(Channel).where(Channel.id == channel_id)
            ).first()
            if not channel:
                raise HTTPException(status_code=404, detail="Channel not found")
            
            if not self._check_workspace_admin(session, channel.workspace_id, user_id):
                raise PermissionError("Only workspace admins can delete channels")
            
            session.delete(channel)
            session.commit()
    
    def update_channel(self, channel_id: UUID, updates: dict, user_id: UUID):
        """Update channel if user is workspace admin."""
        engine = get_db()
        with Session(engine) as session:
            channel = session.exec(
                select(Channel).where(Channel.id == channel_id)
            ).first()
            if not channel:
                raise HTTPException(status_code=404, detail="Channel not found")
            
            if not self._check_workspace_admin(session, channel.workspace_id, user_id):
                raise PermissionError("Only workspace admins can update channels")
            
            for key, value in updates.items():
                setattr(channel, key, value)
            
            session.add(channel)
            session.commit()
            session.refresh(channel)
            return channel

"""MESSAGE MANAGEMENT"""

class MessageWithReplies(BaseModel):
    """Message with additional metadata about replies."""
    message: Message
    reply_count: int
    latest_reply: datetime | None

class MessageManager:
    def _check_channel_member(self, session: Session, channel_id: UUID, user_id: UUID) -> bool:
        """Check if user is a member of the channel"""
        member = session.exec(
            select(ChannelMember).where(
                ChannelMember.channel_id == channel_id,
                ChannelMember.user_id == user_id
            )
        ).first()
        return member is not None

    def _enrich_messages_with_reply_data(self, session: Session, messages: List[Message]) -> List[MessageWithReplies]:
        """Add reply count and latest reply time to messages."""
        if not messages:
            return []

        # Get reply counts and latest reply times for all messages in one query
        reply_stats = session.exec(
            select(
                Message.parent_id,
                func.count(Message.id).label("reply_count"),
                func.max(Message.created_at).label("latest_reply")
            )
            .where(Message.parent_id.in_([msg.id for msg in messages]))
            .group_by(Message.parent_id)
        ).all()

        # Convert to dict for O(1) lookup
        reply_data = {
            str(stats[0]): {"count": stats[1], "latest": stats[2]}
            for stats in reply_stats
        }

        # Combine messages with their reply data
        return [
            MessageWithReplies(
                message=message,
                reply_count=reply_data.get(str(message.id), {}).get("count", 0),
                latest_reply=reply_data.get(str(message.id), {}).get("latest", None)
            )
            for message in messages
        ]

    def get_channel_messages(
        self,
        channel_id: UUID,
        user_id: UUID,
        limit: int = 50,
        before_timestamp: datetime | None = None,
        after_timestamp: datetime | None = None,
        thread_id: UUID | None = None
    ) -> List[MessageWithReplies]:
        """
        Get paginated messages from a channel.
        
        Args:
            channel_id: The channel to get messages from
            user_id: The user requesting messages
            limit: Maximum number of messages to return
            before_timestamp: Get messages before this timestamp (for scrolling up)
            after_timestamp: Get messages after this timestamp (for scrolling down/new messages)
            thread_id: If set, get messages from a specific thread
        
        Returns:
            List of messages with reply counts, ordered by creation time
        """
        engine = get_db()
        with Session(engine) as session:
            channel = session.exec(select(Channel).where(Channel.id == channel_id)).first()
            if not channel:
                raise HTTPException(status_code=404, detail="Channel not found")
            
            # Check access for non-public channels
            if channel.channel_type != "public":
                if not self._check_channel_member(session, channel_id, user_id):
                    raise PermissionError("You must be a member to view messages in this channel")
            
            # Build base query
            query = select(Message).where(
                Message.channel_id == channel_id,
                Message.parent_id == thread_id  # None for main channel, UUID for thread
            )
            
            # Add timestamp filters
            if before_timestamp:
                query = query.where(Message.created_at < before_timestamp)
            if after_timestamp:
                query = query.where(Message.created_at > after_timestamp)
            
            # Order by timestamp
            # For scrolling up (before_timestamp): get most recent messages first
            # For scrolling down (after_timestamp): get oldest messages first
            if before_timestamp or not after_timestamp:
                query = query.order_by(Message.created_at.desc())
            else:
                query = query.order_by(Message.created_at.asc())
            
            # Apply limit
            query = query.limit(limit)
            
            # Execute query
            messages = session.exec(query).all()
            
            # Reverse the order for before_timestamp queries to maintain chronological order
            if before_timestamp or not after_timestamp:
                messages.reverse()
            
            # Add reply counts and latest reply times
            return self._enrich_messages_with_reply_data(session, messages)

    def get_message_by_id(self, message_id: UUID, user_id: UUID) -> MessageWithReplies:
        """Get a message if user has access to the channel."""
        engine = get_db()
        with Session(engine) as session:
            message = session.exec(
                select(Message).where(Message.id == message_id)
            ).first()
            if not message:
                raise HTTPException(status_code=404, detail="Message not found")
            
            channel = session.exec(
                select(Channel).where(Channel.id == message.channel_id)
            ).first()
            
            # For public channels, allow viewing without membership
            if channel.channel_type != "public":
                if not self._check_channel_member(session, message.channel_id, user_id):
                    raise PermissionError("You must be a member to view messages in this channel")
            
            # Add reply data
            return self._enrich_messages_with_reply_data(session, [message])[0]

    def get_thread_messages(
        self,
        thread_id: UUID,
        user_id: UUID,
        limit: int = 50,
        before_timestamp: datetime | None = None
    ) -> List[Message]:
        """
        Get paginated messages from a thread.
        This is a convenience wrapper around get_channel_messages.
        """
        # First get the parent message to get its channel
        engine = get_db()
        with Session(engine) as session:
            parent_message = session.exec(
                select(Message).where(Message.id == thread_id)
            ).first()
            if not parent_message:
                raise HTTPException(status_code=404, detail="Thread not found")
            
            # Use get_channel_messages with thread_id
            return self.get_channel_messages(
                channel_id=parent_message.channel_id,
                user_id=user_id,
                limit=limit,
                before_timestamp=before_timestamp,
                thread_id=thread_id
            )

    def create_message(self, message: Message, user_id: UUID):
        """Create message if user is channel member."""
        engine = get_db()
        with Session(engine) as session:
            if not self._check_channel_member(session, message.channel_id, user_id):
                raise PermissionError("You must be a member to send messages to this channel")
            
            message.user_id = user_id
            session.add(message)
            session.commit()
            session.refresh(message)
            return message

    def delete_message(self, message_id: UUID, user_id: UUID):
        """Delete message if user is author or workspace admin."""
        engine = get_db()
        with Session(engine) as session:
            message = session.exec(
                select(Message).where(Message.id == message_id)
            ).first()
            if not message:
                raise HTTPException(status_code=404, detail="Message not found")
            
            channel = session.exec(
                select(Channel).where(Channel.id == message.channel_id)
            ).first()
            
            # Allow deletion if user is message author or workspace admin
            if message.user_id != user_id and not self._check_workspace_admin(session, channel.workspace_id, user_id):
                raise PermissionError("Only message authors or workspace admins can delete messages")
            
            session.delete(message)
            session.commit()

"""CHANNEL MEMBER MANAGEMENT"""

class ChannelMemberManager:
    def _check_workspace_admin(self, session: Session, workspace_id: UUID, user_id: UUID) -> bool:
        """Check if user is an admin of the workspace"""
        member = session.exec(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.role == WorkspaceRole.ADMIN
            )
        ).first()
        return member is not None

    def add_member(self, channel_id: UUID, user_id: UUID, added_by_id: UUID, is_admin: bool = False):
        """Add a member to a channel."""
        engine = get_db()
        with Session(engine) as session:
            channel = session.exec(select(Channel).where(Channel.id == channel_id)).first()
            if not channel:
                raise HTTPException(status_code=404, detail="Channel not found")
            
            # For private channels, only workspace admins can add members
            if channel.channel_type == "private":
                if not self._check_workspace_admin(session, channel.workspace_id, added_by_id):
                    raise PermissionError("Only workspace admins can add members to private channels")
            
            # For public channels, any member can add other members
            elif not self._check_channel_member(session, channel_id, added_by_id):
                raise PermissionError("Only channel members can add other members")
            
            member = ChannelMember(
                channel_id=channel_id,
                user_id=user_id,
                is_admin=is_admin
            )
            session.add(member)
            session.commit()

    def remove_member(self, channel_id: UUID, user_id: UUID, removed_by_id: UUID):
        """Remove a member from a channel."""
        engine = get_db()
        with Session(engine) as session:
            channel = session.exec(select(Channel).where(Channel.id == channel_id)).first()
            if not channel:
                raise HTTPException(status_code=404, detail="Channel not found")
            
            # Allow workspace admins or self-removal
            if user_id != removed_by_id and not self._check_workspace_admin(session, channel.workspace_id, removed_by_id):
                raise PermissionError("Only workspace admins can remove other members")
            
            member = session.exec(
                select(ChannelMember).where(
                    ChannelMember.channel_id == channel_id,
                    ChannelMember.user_id == user_id
                )
            ).first()
            if member:
                session.delete(member)
                session.commit()

"""FILE ATTACHMENT MANAGEMENT"""

class FileAttachmentManager:
    def create_attachment(self, attachment: FileAttachment, user_id: UUID):
        """Create a file attachment if user has access to the channel."""
        engine = get_db()
        with Session(engine) as session:
            message = session.exec(select(Message).where(Message.id == attachment.message_id)).first()
            if not message:
                raise HTTPException(status_code=404, detail="Message not found")
            
            if not self._check_channel_member(session, message.channel_id, user_id):
                raise PermissionError("You must be a member to attach files to this channel")
            
            attachment.user_id = user_id
            session.add(attachment)
            session.commit()
            session.refresh(attachment)
            return attachment

    def delete_attachment(self, attachment_id: UUID, user_id: UUID):
        """Delete a file attachment if user is author or admin."""
        engine = get_db()
        with Session(engine) as session:
            attachment = session.exec(select(FileAttachment).where(FileAttachment.id == attachment_id)).first()
            if not attachment:
                raise HTTPException(status_code=404, detail="Attachment not found")
            
            message = session.exec(select(Message).where(Message.id == attachment.message_id)).first()
            channel = session.exec(select(Channel).where(Channel.id == message.channel_id)).first()
            
            if attachment.user_id != user_id and not self._check_workspace_admin(session, channel.workspace_id, user_id):
                raise PermissionError("Only attachment authors or workspace admins can delete attachments")
            
            session.delete(attachment)
            session.commit()

"""REACTION MANAGEMENT"""

class ReactionManager:
    def add_reaction(self, reaction: Reaction, user_id: UUID):
        """Add a reaction to a message if user has access."""
        engine = get_db()
        with Session(engine) as session:
            message = session.exec(select(Message).where(Message.id == reaction.message_id)).first()
            if not message:
                raise HTTPException(status_code=404, detail="Message not found")
            
            if not self._check_channel_member(session, message.channel_id, user_id):
                raise PermissionError("You must be a member to react to messages in this channel")
            
            # Check if user already reacted with this emoji
            existing = session.exec(
                select(Reaction).where(
                    Reaction.message_id == reaction.message_id,
                    Reaction.user_id == user_id,
                    Reaction.emoji == reaction.emoji
                )
            ).first()
            
            if existing:
                raise HTTPException(status_code=400, detail="You already reacted with this emoji")
            
            reaction.user_id = user_id
            session.add(reaction)
            session.commit()
            session.refresh(reaction)
            return reaction

    def remove_reaction(self, reaction_id: UUID, user_id: UUID):
        """Remove a reaction if user is the author."""
        engine = get_db()
        with Session(engine) as session:
            reaction = session.exec(select(Reaction).where(Reaction.id == reaction_id)).first()
            if not reaction:
                raise HTTPException(status_code=404, detail="Reaction not found")
            
            if reaction.user_id != user_id:
                raise PermissionError("Only reaction authors can remove their reactions")
            
            session.delete(reaction)
            session.commit()

"""USER SESSION MANAGEMENT"""

class UserSessionManager:
    def create_session(self, user_id: UUID, session_id: str):
        """Create a new user session."""
        engine = get_db()
        with Session(engine) as session:
            user_session = UserSession(
                user_id=user_id,
                session_id=session_id
            )
            session.add(user_session)
            session.commit()
            session.refresh(user_session)
            return user_session

    def delete_session(self, session_id: str):
        """Delete a user session."""
        engine = get_db()
        with Session(engine) as session:
            user_session = session.exec(
                select(UserSession).where(UserSession.session_id == session_id)
            ).first()
            if user_session:
                session.delete(user_session)
                session.commit()

    def update_last_ping(self, session_id: str):
        """Update the last ping time for a session."""
        engine = get_db()
        with Session(engine) as session:
            user_session = session.exec(
                select(UserSession).where(UserSession.session_id == session_id)
            ).first()
            if user_session:
                user_session.last_ping = datetime.now(UTC)
                session.add(user_session)
                session.commit()

    def get_active_sessions(self, user_id: UUID) -> List[UserSession]:
        """Get all active sessions for a user."""
        engine = get_db()
        with Session(engine) as session:
            return session.exec(
                select(UserSession).where(UserSession.user_id == user_id)
            ).all()

    def cleanup_stale_sessions(self, max_age_minutes: int = 15):
        """Remove sessions that haven't pinged in the specified time."""
        engine = get_db()
        with Session(engine) as session:
            cutoff = datetime.now(UTC) - timedelta(minutes=max_age_minutes)
            stale_sessions = session.exec(
                select(UserSession).where(UserSession.last_ping < cutoff)
            ).all()
            
            for stale_session in stale_sessions:
                session.delete(stale_session)
            session.commit()

"""SEARCH FUNCTIONALITY"""

class SearchManager:
    def search_workspaces(self, query: str, limit: int = 20) -> List[Workspace]:
        """Search for workspaces by name or slug."""
        engine = get_db()
        with Session(engine) as session:
            workspaces = session.exec(
                select(Workspace)
                .where(or_(
                    Workspace.name.contains(query),
                    Workspace.slug.contains(query)
                ))
                .limit(limit)
            ).all()
            return workspaces

    def search_users(self, query: str, workspace_id: UUID | None = None, limit: int = 20) -> List[User]:
        """Search for users, optionally within a specific workspace."""
        engine = get_db()
        with Session(engine) as session:
            if workspace_id:
                # Search within workspace members
                users = session.exec(
                    select(User)
                    .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
                    .where(
                        WorkspaceMember.workspace_id == workspace_id,
                        or_(
                            User.username.contains(query),
                            User.display_name.contains(query),
                            User.email.contains(query)
                        )
                    )
                    .limit(limit)
                ).all()
            else:
                # Search all users
                users = session.exec(
                    select(User)
                    .where(or_(
                        User.username.contains(query),
                        User.display_name.contains(query),
                        User.email.contains(query)
                    ))
                    .limit(limit)
                ).all()
            return users

    def search_channels(self, query: str, workspace_id: UUID, user_id: UUID, limit: int = 20) -> List[Channel]:
        """Search for channels in a workspace that the user has access to."""
        engine = get_db()
        with Session(engine) as session:
            # Get all channels where:
            # 1. Channel is in the workspace
            # 2. Channel name matches query
            # 3. Channel is either:
            #    a. Public
            #    b. User is a member
            channels = session.exec(
                select(Channel)
                .where(
                    Channel.workspace_id == workspace_id,
                    Channel.name.contains(query),
                    or_(
                        Channel.channel_type == "public",
                        Channel.id.in_(
                            select(ChannelMember.channel_id)
                            .where(ChannelMember.user_id == user_id)
                        )
                    )
                )
                .limit(limit)
            ).all()
            return channels

    def search_messages(self, query: str, channel_id: UUID, user_id: UUID, limit: int = 20) -> List[Message]:
        """Search for messages in a channel that the user has access to."""
        engine = get_db()
        with Session(engine) as session:
            channel = session.exec(select(Channel).where(Channel.id == channel_id)).first()
            if not channel:
                raise HTTPException(status_code=404, detail="Channel not found")
            
            # Check access for non-public channels
            if channel.channel_type != "public":
                if not self._check_channel_member(session, channel_id, user_id):
                    raise PermissionError("You must be a member to search messages in this channel")
            
            messages = session.exec(
                select(Message)
                .where(
                    Message.channel_id == channel_id,
                    Message.content.contains(query)
                )
                .order_by(Message.created_at.desc())
                .limit(limit)
            ).all()
            return messages
