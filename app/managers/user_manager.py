from fastapi import HTTPException
from typing import Dict, Set
from uuid import UUID
from datetime import datetime, UTC
from sqlmodel import Session, select
from app.models import User, WorkspaceMember
from app.utils.db import get_db
from typing import List
from passlib.context import CryptContext
from pydantic import EmailStr
from enum import Enum

# Password hashing configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class WorkspaceRole(str, Enum):
    ADMIN = "admin"
    MEMBER = "member"

class UserExistsError(Exception):
    """Raised when trying to create a user that already exists"""
    pass

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
            try:
                print(f"Checking if email exists: {email}")
                # Check if email exists
                if self.get_user_by_email(email):
                    raise UserExistsError("A user with this email already exists")
                
                print(f"Checking if username exists: {username}")
                # Check if username exists
                if self.get_user_by_username(username):
                    raise UserExistsError("A user with this username already exists")
                
                print("Creating new user")
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
                print(f"User created successfully with ID: {user.id}")
                return user
            except Exception as e:
                print(f"Error in create_user: {str(e)}")
                raise

    def authenticate_user(self, email: str, password: str) -> User | None:
        """Authenticate a user by email and password."""
        user = self.get_user_by_email(email)
        if not user:
            return None
        if not self.verify_password(password, user.hashed_password):
            return None
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

# Create a global instance
user_manager = UserManager() 