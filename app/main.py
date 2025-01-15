import json
import logging
import mimetypes
import re
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum
from os import getenv
from typing import Any, Generator, Optional
from uuid import UUID, uuid4

import boto3
from botocore.exceptions import ClientError
from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from sqlmodel import (
    Field,
    Relationship,
    Session,
    SQLModel,
    and_,
    create_engine,
    delete,
    or_,
    select,
)


class ConversationType(str, Enum):
    """Type of conversation in the system."""

    CHANNEL = "channel"
    DIRECT_MESSAGE = "direct_message"


class WorkspaceRole(str, Enum):
    """User roles within a workspace."""

    ADMIN = "admin"
    MEMBER = "member"
    OWNER = "owner"


class FileType(str, Enum):
    """Types of files that can be uploaded."""

    IMAGE = "image"
    DOCUMENT = "document"
    SPREADSHEET = "spreadsheet"
    PRESENTATION = "presentation"
    PDF = "pdf"
    VIDEO = "video"
    AUDIO = "audio"
    OTHER = "other"

    @classmethod
    def from_mime_type(cls, mime_type: str) -> "FileType":
        """Determine FileType from MIME type."""
        mime_map = {
            "image/": cls.IMAGE,
            "video/": cls.VIDEO,
            "audio/": cls.AUDIO,
            "application/pdf": cls.PDF,
            "application/vnd.ms-excel": cls.SPREADSHEET,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": cls.SPREADSHEET,
            "application/msword": cls.DOCUMENT,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": cls.DOCUMENT,
            "application/vnd.ms-powerpoint": cls.PRESENTATION,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": cls.PRESENTATION,
        }

        for mime_prefix, file_type in mime_map.items():
            if mime_type.startswith(mime_prefix):
                return file_type
        return cls.OTHER

    @classmethod
    def from_filename(cls, filename: str) -> "FileType":
        """Determine FileType from file extension."""
        ext = filename.lower().split(".")[-1] if "." in filename else ""
        ext_map = {
            "pdf": cls.PDF,
            "doc": cls.DOCUMENT,
            "docx": cls.DOCUMENT,
            "xls": cls.SPREADSHEET,
            "xlsx": cls.SPREADSHEET,
            "ppt": cls.PRESENTATION,
            "pptx": cls.PRESENTATION,
            "jpg": cls.IMAGE,
            "jpeg": cls.IMAGE,
            "png": cls.IMAGE,
            "gif": cls.IMAGE,
            "webp": cls.IMAGE,
            "mp4": cls.VIDEO,
            "mov": cls.VIDEO,
            "avi": cls.VIDEO,
            "mp3": cls.AUDIO,
            "wav": cls.AUDIO,
            "ogg": cls.AUDIO,
        }
        return ext_map.get(ext, cls.OTHER)


def get_current_time() -> datetime:
    """Get the current time."""
    return datetime.now(UTC)


class Base(SQLModel):
    """Base model with common configuration."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        json_encoders={
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v),
            str: lambda v: v.get_secret_value() if v else None,
        },
    )


class WorkspaceMember(Base, table=True):
    workspace_id: UUID = Field(foreign_key="workspace.id", primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", primary_key=True)
    role: WorkspaceRole = Field(default=WorkspaceRole.MEMBER, index=True)
    joined_at: datetime = Field(default_factory=get_current_time)
    is_active: bool = Field(default=True, index=True)

    workspace: "Workspace" = Relationship(back_populates="workspace_members")
    user: "User" = Relationship(back_populates="workspace_members")


class ConversationMember(Base, table=True):
    """Association table for conversation members."""

    conversation_id: UUID = Field(foreign_key="conversation.id", primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", primary_key=True)
    joined_at: datetime = Field(default_factory=get_current_time)
    last_read_at: datetime = Field(default_factory=get_current_time)
    is_muted: bool = Field(default=False)
    is_pinned: bool = Field(default=False)

    # Change these relationship names to be consistent
    conversation: "Conversation" = Relationship(back_populates="conversation_members")
    user: "User" = Relationship(back_populates="conversation_members")


class Channel(Base, table=True):
    """Channel model representing public/private channels in a workspace."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=80, index=True)
    description: Optional[str] = Field(default=None, max_length=1000)
    slug: str = Field(index=True, max_length=100)
    is_private: bool = Field(default=False)
    is_archived: bool = Field(default=False, index=True)
    s3_key: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=get_current_time)
    created_by_id: UUID = Field(foreign_key="user.id")
    workspace_id: UUID = Field(foreign_key="workspace.id", index=True)
    conversation_id: UUID = Field(foreign_key="conversation.id", unique=True)

    workspace: "Workspace" = Relationship(back_populates="channels")
    conversation: "Conversation" = Relationship(back_populates="channel")


class Workspace(Base, table=True):
    """Workspace model representing a team/organization workspace."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=100, index=True)
    description: Optional[str] = Field(default=None, max_length=1000)
    slug: str = Field(unique=True, index=True, max_length=100)
    s3_key: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=get_current_time)
    created_by_id: UUID = Field(foreign_key="user.id")
    is_active: bool = Field(default=True, index=True)

    conversations: list["Conversation"] = Relationship(back_populates="workspace")
    workspace_members: list["WorkspaceMember"] = Relationship(
        back_populates="workspace"
    )
    members: list["User"] = Relationship(
        back_populates="workspaces", link_model=WorkspaceMember
    )
    channels: list["Channel"] = Relationship(back_populates="workspace")
    files: list["File"] = Relationship(back_populates="workspace")


class User(Base, table=True):
    """User model representing system users."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: EmailStr = Field(unique=True, index=True)
    username: str = Field(unique=True, index=True, max_length=50)
    hashed_password: str
    display_name: Optional[str] = Field(default=None, max_length=100)
    bio: Optional[str] = Field(default=None, max_length=500)
    s3_key: Optional[str] = Field(default=None)
    is_online: bool = Field(default=False, index=True)
    is_active: bool = Field(default=True, index=True)
    last_active: datetime = Field(default_factory=get_current_time)
    created_at: datetime = Field(default_factory=get_current_time)
    updated_at: datetime = Field(default_factory=get_current_time)

    messages: list["Message"] = Relationship(back_populates="user")
    workspace_members: list["WorkspaceMember"] = Relationship(back_populates="user")
    conversation_members: list["ConversationMember"] = Relationship(
        back_populates="user"
    )
    conversations: list["Conversation"] = Relationship(
        back_populates="members", link_model=ConversationMember
    )
    reactions: list["Reaction"] = Relationship(back_populates="user")
    files: list["File"] = Relationship(back_populates="user")
    workspaces: list["Workspace"] = Relationship(
        back_populates="members", link_model=WorkspaceMember
    )


class Message(Base, table=True):
    """Message model representing chat messages."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    content: Optional[str] = Field(default=None)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    conversation_id: UUID = Field(foreign_key="conversation.id", index=True)
    parent_id: Optional[UUID] = Field(
        default=None, foreign_key="message.id", index=True
    )
    is_edited: bool = Field(default=False)
    is_deleted: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=get_current_time)
    updated_at: datetime = Field(default_factory=get_current_time)

    attachment: Optional["File"] = Relationship(back_populates="message")
    user: User = Relationship(back_populates="messages")
    conversation: "Conversation" = Relationship(back_populates="messages")
    reactions: list["Reaction"] = Relationship(back_populates="message")
    replies: list["Message"] = Relationship()  # For thread replies


class Reaction(Base, table=True):
    """Reaction model for message reactions/emojis."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    emoji: str = Field(max_length=50)
    message_id: UUID = Field(foreign_key="message.id", index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=get_current_time)

    message: Message = Relationship(back_populates="reactions")
    user: User = Relationship(back_populates="reactions")


class File(Base, table=True):
    """File model for uploaded files/attachments."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    original_filename: str = Field(max_length=255)
    file_type: FileType = Field(default=FileType.OTHER)
    mime_type: str = Field(max_length=127)
    file_size: int
    uploaded_at: datetime = Field(default_factory=get_current_time)
    message_id: Optional[UUID] = Field(
        default=None, foreign_key="message.id", index=True
    )
    user_id: UUID = Field(foreign_key="user.id", index=True)
    workspace_id: Optional[UUID] = Field(
        default=None, foreign_key="workspace.id", index=True
    )
    conversation_id: Optional[UUID] = Field(
        default=None, foreign_key="conversation.id", index=True
    )

    message: Optional[Message] = Relationship(back_populates="attachment")
    user: User = Relationship(back_populates="files")
    workspace: Optional[Workspace] = Relationship(back_populates="files")
    conversation: Optional["Conversation"] = Relationship(back_populates="files")


class Conversation(Base, table=True):
    """Conversation model representing channels and direct messages."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, max_length=1000)
    conversation_type: ConversationType = Field(index=True)
    workspace_id: Optional[UUID] = Field(
        default=None, foreign_key="workspace.id", index=True
    )
    created_at: datetime = Field(default_factory=get_current_time)
    updated_at: datetime = Field(default_factory=get_current_time)
    last_message_at: Optional[datetime] = Field(default=None)
    is_archived: bool = Field(default=False, index=True)

    messages: list[Message] = Relationship(back_populates="conversation")
    workspace: Optional[Workspace] = Relationship(back_populates="conversations")
    conversation_members: list["ConversationMember"] = Relationship(
        back_populates="conversation"
    )
    members: list["User"] = Relationship(
        back_populates="conversations", link_model=ConversationMember
    )
    channel: Optional[Channel] = Relationship(back_populates="conversation")
    files: list[File] = Relationship(back_populates="conversation")


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Slack Clone API",
    description="A modern chat application API inspired by Slack",
    version="1.0.0",
)
DB_USER = getenv("DB_USER")
DB_PASSWORD = getenv("DB_PASSWORD")
DB_HOST = getenv("DB_HOST")
DB_PORT = getenv("DB_PORT")
DB_NAME = getenv("DB_NAME")


DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    # CREATE EXTENSION IF NOT EXISTS vector;


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def get_db():
    """Database session dependency."""
    # Create a new session
    with Session(engine) as session:
        try:
            yield session  # FastAPI will use this yielded session
            session.commit()  # Commit any changes if no exceptions occurred
        except:
            session.rollback()  # Roll back changes if an exception occurred
            raise
        finally:
            session.close()  # Always close the session


create_db_and_tables()


# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": app.version}


# CORS middleware configuration
origins = [
    "http://localhost:5173",  # Dev frontend
    "http://localhost:3000",  # Prod frontend
    "http://frontend:3000",  # Docker frontend
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

router = APIRouter(prefix="/api")

pwd_context = CryptContext(
    schemes=["argon2"],
    default="argon2",
    argon2__time_cost=3,
    argon2__memory_cost=65536,
    argon2__parallelism=4,
    deprecated="auto",
)

BUCKET_NAME = getenv("AWS_S3_BUCKET_NAME")
AWS_REGION = getenv("AWS_REGION")
AWS_ACCESS_KEY_ID = getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = getenv("AWS_SECRET_ACCESS_KEY")

# JWT Configuration
SECRET_KEY = getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    # Fallback to a default key for development
    SECRET_KEY = "your-super-secret-key-for-jwt-that-should-be-very-long-and-secure"


ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


async def broadcast_event(event_type: str, data: dict, db: Session):
    """Broadcast an event to all connected WebSocket clients."""
    await ws.broadcast_to_users(
        {"message_type": event_type, **data}, set(ws.active_connections.keys())
    )


def name_to_slug(name: str) -> str:
    # Convert to lowercase
    slug = name.lower()
    # Replace non-alphanumeric characters with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    # Trim leading and trailing hyphens
    slug = slug.strip("-")
    return slug


""" ERROR CLASSES """


class APIError(HTTPException):
    """Base API error class with predefined status codes and messages."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(status_code=status_code, detail=detail)


class NotFoundError(APIError):
    """Resource not found error."""

    def __init__(self, resource: str, resource_id: Optional[str] = None):
        detail = f"{resource} not found"
        if resource_id:
            detail = f"{resource} with id {resource_id} not found"
        super().__init__(status_code=404, detail=detail)


class UnauthorizedError(APIError):
    """Authentication error."""

    def __init__(self, detail: str = "Not authenticated"):
        super().__init__(status_code=401, detail=detail)


class ForbiddenError(APIError):
    """Authorization error."""

    def __init__(self, detail: str = "Not authorized to perform this action"):
        super().__init__(status_code=403, detail=detail)


class ConflictError(APIError):
    """Resource conflict error."""

    def __init__(self, detail: str):
        super().__init__(status_code=409, detail=detail)


class ValidationError(APIError):
    """Input validation error."""

    def __init__(self, detail: str):
        super().__init__(status_code=400, detail=detail)


# Common error messages
def WORKSPACE_NOT_FOUND(id):
    return NotFoundError("Workspace", str(id))


def CHANNEL_NOT_FOUND(id):
    return NotFoundError("Channel", str(id))


def CONVERSATION_NOT_FOUND(id):
    return NotFoundError("Conversation", str(id))


def USER_NOT_FOUND(id):
    return NotFoundError("User", str(id))


def MESSAGE_NOT_FOUND(id):
    return NotFoundError("Message", str(id))


def NOT_WORKSPACE_MEMBER():
    return ForbiddenError("Not a member of this workspace")


def NOT_CHANNEL_MEMBER():
    return ForbiddenError("Not a member of this channel")


def NOT_CONVERSATION_PARTICIPANT():
    return ForbiddenError("Not a participant in this conversation")


def ADMIN_REQUIRED():
    return ForbiddenError("Admin access required for this action")


def USER_EXISTS(field):
    return ConflictError(f"A user with this {field} already exists")


def ALREADY_MEMBER(resource):
    return ConflictError(f"Already a member of this {resource}")


def INVALID_CREDENTIALS():
    return UnauthorizedError("Invalid email or password")


def INVALID_TOKEN():
    return UnauthorizedError("Invalid or expired token")


def MISSING_TOKEN():
    return UnauthorizedError("No authentication token provided")


"""REQUEST AND RESPONSE MODELS"""


class GetUserResponse(BaseModel):
    id: UUID
    username: str
    email: str
    display_name: str
    s3_key: str | None
    is_online: bool


class UserCreateRequest(BaseModel):
    username: str
    email: str
    display_name: str
    password: str


class GetWorkspaceResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    slug: str
    role: WorkspaceRole


class GetChannelResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    slug: str
    workspace_id: UUID


class ConversationResponse(BaseModel):
    id: UUID
    conversation_type: ConversationType
    messages: list[str]
    message_parents: dict[str, str | None]
    users_typing: set[str]
    user_id: UUID | None = None
    channel_id: UUID | None = None


class MessageResponse(BaseModel):
    id: UUID
    user_id: UUID
    content: str | None
    file_id: UUID | None
    reactions: set[str]
    children: list[str] | None
    parent_id: UUID | None
    conversation_id: UUID  # Added
    created_at: datetime  # Added
    updated_at: datetime  # Added


class MessageCreateRequest(BaseModel):
    content: str | None = None
    file_id: UUID | None = None  # Changed to single file_id
    parent_id: UUID | None = None


class DirectMessageCreateRequest(BaseModel):
    user_id: UUID
    content: str
    file_id: UUID | None = None
    parent_id: UUID | None = None


class GetMessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    user_id: UUID
    content: str
    file_id: UUID | None  # Changed to single file_id
    created_at: datetime
    updated_at: datetime
    parent_id: UUID | None


class GetReactionResponse(BaseModel):
    id: UUID
    message_id: UUID
    user_id: UUID
    emoji: str


class ReactionResponse(BaseModel):
    id: UUID
    user_id: UUID
    emoji: str


class ReactionCreateRequest(BaseModel):
    message_id: UUID
    emoji: str


class ChannelResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    slug: str
    workspace_id: UUID
    conversation_id: str


class ChannelCreateRequest(BaseModel):
    name: str
    description: str | None = None
    workspace_id: UUID


class ChannelUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class FileResponse(BaseModel):
    id: UUID
    original_filename: str
    file_type: FileType
    mime_type: str
    file_size: int
    message_id: UUID | None
    user_id: UUID
    workspace_id: UUID | None
    conversation_id: UUID | None
    # Removed s3_key from response since it's the same as id


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: UUID
    exp: datetime


""" MANAGER CLASSES """


class Storage:
    def __init__(self):
        self.s3_client = boto3.client(
            "s3",
            region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        )
        self.configure_cors()

    def configure_cors(self):
        """Configure CORS for the S3 bucket"""
        cors_configuration = {
            "CORSRules": [
                {
                    "AllowedHeaders": ["*"],
                    "AllowedMethods": ["GET", "PUT", "POST", "DELETE"],
                    "AllowedOrigins": ["*"],
                    "ExposeHeaders": ["ETag"],
                }
            ]
        }
        try:
            self.s3_client.put_bucket_cors(
                Bucket=BUCKET_NAME, CORSConfiguration=cors_configuration
            )
            logging.info("Successfully configured CORS for S3 bucket")
        except ClientError as e:
            logging.error(f"Error configuring CORS for S3 bucket: {e}")
            # Don't raise the error as this is not critical for operation

    def get_upload_details(
        self, filename: str, content_type: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Generate upload details including presigned URL and file metadata

        :param filename: Original filename from user
        :param content_type: Optional MIME type (if known)
        :return: Dictionary containing upload details and file metadata
        """
        # Generate a UUID for the S3 key
        s3_key = str(uuid4())

        # Determine content type
        if not content_type:
            content_type = (
                mimetypes.guess_type(filename)[0] or "application/octet-stream"
            )

        # Generate the presigned POST URL
        conditions = [
            {"bucket": BUCKET_NAME},
            ["starts-with", "$key", s3_key],
            ["starts-with", "$Content-Type", content_type.split("/")[0]],
            ["content-length-range", 1, 100 * 1024 * 1024],  # 100MB max
        ]

        try:
            response = self.s3_client.generate_presigned_post(
                BUCKET_NAME,
                s3_key,
                Fields={
                    "Content-Type": content_type,
                },
                Conditions=conditions,
                ExpiresIn=3600,
            )

            return {
                "upload_data": response,
                "metadata": {
                    "s3_key": s3_key,
                    "mime_type": content_type,
                    "original_filename": filename,
                },
            }
        except ClientError as e:
            logging.error(f"Error generating presigned URL: {e}")
            raise

    def create_presigned_url(
        self, s3_key: str, expiration: int = 3600
    ) -> Optional[str]:
        """
        Generate a presigned URL to read an S3 object

        :param s3_key: The key of the object in S3
        :param expiration: Time in seconds for the presigned URL to remain valid
        :return: Presigned URL as string. If error, returns None.
        """
        try:
            response = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": BUCKET_NAME, "Key": s3_key},
                ExpiresIn=expiration,
            )
            return response
        except ClientError as e:
            logging.error(f"Error generating presigned URL: {e}")
            return None

    def delete_file(self, s3_key: str) -> bool:
        """
        Delete a file from S3

        :param s3_key: The key of the object in S3
        :return: True if successful, False otherwise
        """
        try:
            self.s3_client.delete_object(Bucket=BUCKET_NAME, Key=s3_key)
            return True
        except ClientError as e:
            logging.error(f"Error deleting file: {e}")
            return False

    def upload_file(self, file_data: bytes, s3_key: str, content_type: str) -> bool:
        """
        Upload a file to S3 from the server

        :param file_data: The file contents
        :param s3_key: The key to store the file under in S3
        :param content_type: The content type of the file
        :return: True if successful, False otherwise
        """
        try:
            self.s3_client.put_object(
                Bucket=BUCKET_NAME, Key=s3_key, Body=file_data, ContentType=content_type
            )
            return True
        except ClientError as e:
            logging.error(f"Error uploading file to S3: {e}")
            return False


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

    def get_user_by_id(self, user_id: UUID, db: Session) -> User:
        """Get a user by their ID."""
        try:
            user = db.exec(select(User).where(User.id == user_id)).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            # Generate pre-signed URL for avatar if it exists
            if user.s3_key:
                storage = Storage()
                user.s3_key = storage.create_presigned_url(user.s3_key)

            return user
        except Exception:
            raise

    def get_user_by_email(self, email: str, db: Session) -> User | None:
        """Get a user by their email."""
        return db.exec(select(User).where(User.email == email)).first()

    def get_user_by_username(self, username: str, db: Session) -> User | None:
        """Get a user by their username."""
        return db.exec(select(User).where(User.username == username)).first()

    def create_user(
        self,
        email: EmailStr,
        username: str,
        password: str,
        display_name: str | None = None,
        db: Session = None,
    ) -> User:
        """
        Create a new user with proper password hashing.
        Raises UserExistsError if email or username already exists.
        """
        try:
            # Check if email exists
            if self.get_user_by_email(email, db):
                raise UserExistsError("A user with this email already exists")

            # Check if username exists
            if self.get_user_by_username(username, db):
                raise UserExistsError("A user with this username already exists")

            # Create new user with hashed password
            user = User(
                email=email,
                username=username,
                hashed_password=self._hash_password(password),
                display_name=display_name or username,
                is_online=True,
                last_active=datetime.now(UTC),
            )

            db.add(user)
            db.commit()
            db.refresh(user)

            return user
        except Exception:
            raise

    def authenticate_user(self, email: str, password: str, db: Session) -> User | None:
        """Authenticate a user by email and password."""
        user = self.get_user_by_email(email, db)
        if not user:
            return None
        if not self.verify_password(password, user.hashed_password):
            return None
        return user

    def join_workspace(
        self,
        user_id: UUID,
        workspace_id: UUID,
        auto_join_public: bool = True,
        db: Session = None,
    ):
        """
        Add a user to a workspace.
        Optionally auto-join all public channels.
        """
        try:
            # Check if user is already a member
            existing_member = db.exec(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == workspace_id,
                    WorkspaceMember.user_id == user_id,
                )
            ).first()

            if existing_member:
                return  # Already a member

            # Add to workspace
            member = WorkspaceMember(
                workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER
            )
            db.add(member)
            db.commit()
        except Exception:
            raise


class AuthUtils:
    def create_access_token(self, user_id: UUID) -> str:
        """Create a new access token."""
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        expire = datetime.now(UTC) + expires_delta

        to_encode = {"sub": str(user_id), "exp": expire, "type": "access"}
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    def create_refresh_token(self, user_id: UUID) -> str:
        """Create a new refresh token."""
        expires_delta = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        expire = datetime.now(UTC) + expires_delta

        to_encode = {"sub": str(user_id), "exp": expire, "type": "refresh"}
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    def create_tokens(self, user_id: UUID) -> Token:
        """Create both access and refresh tokens."""
        return Token(
            access_token=self.create_access_token(user_id),
            refresh_token=self.create_refresh_token(user_id),
            token_type="bearer",
        )

    def verify_token(self, token: str, token_type: str = "access") -> TokenData:
        """Verify a token and return its data."""
        if not token:
            raise HTTPException(status_code=401, detail="No token provided")

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

            user_id = payload.get("sub")
            exp = payload.get("exp")
            token_type_received = payload.get("type")

            if user_id is None or exp is None:
                raise HTTPException(status_code=401, detail="Invalid token format")

            if token_type_received != token_type:
                raise HTTPException(
                    status_code=401, detail=f"Invalid token type. Expected {token_type}"
                )

            return TokenData(
                user_id=UUID(user_id), exp=datetime.fromtimestamp(exp, UTC)
            )
        except JWTError as e:
            logger.error(f"JWT Error during {token_type} token verification:", str(e))
            raise HTTPException(status_code=401, detail="Could not validate token")

    def refresh_tokens(self, refresh_token: str) -> Token:
        """Create new access and refresh tokens using a refresh token."""
        token_data = self.verify_token(refresh_token, "refresh")
        return self.create_tokens(token_data.user_id)

    async def get_current_user(self, access_token: str = Cookie(None)) -> User:
        """Get the current user from a token stored in cookies."""
        token_data = self.verify_token(access_token)
        user_manager = UserManager()
        user = user_manager.get_user_by_id(token_data.user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")

        return user


# Dependency for protected routes
async def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Get the current user from the access token in cookies."""

    access_token = request.cookies.get("access_token")

    if not access_token:
        raise HTTPException(status_code=401, detail="No access token provided")

    try:
        auth_utils = AuthUtils()
        token_data = auth_utils.verify_token(access_token, "access")

        user_manager = UserManager()

        user = user_manager.get_user_by_id(token_data.user_id, db)
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")

        return user
    except Exception as e:
        logger.error("Error in get_current_user: %s", str(e))
        raise


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[UUID, WebSocket] = {}
        self.user_typing: dict[
            UUID, set[UUID]
        ] = {}  # conversation_id -> set of user_ids

    async def connect(self, websocket: WebSocket, user_id: UUID):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: UUID):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

        # Remove user from all typing indicators
        for typing_users in self.user_typing.values():
            typing_users.discard(user_id)

    async def broadcast_to_users(self, message: dict, user_ids: set[UUID]):
        """Broadcast a message to specific users"""
        for user_id in user_ids:
            if user_id in self.active_connections:
                try:
                    websocket = self.active_connections[user_id]
                    await websocket.send_json(message)
                except Exception as e:
                    logger.error(f"Error sending message to user {user_id}: {e}")
                    # If there was an error sending, remove the connection
                    self.disconnect(user_id)

    def get_relevant_users_for_user(self, user_id: UUID, db: Session) -> set[UUID]:
        """Get all users who should receive updates about this user"""
        relevant_users = set()

        # Add users from shared workspaces
        workspace_members = db.exec(
            select(WorkspaceMember).where(WorkspaceMember.user_id == user_id)
        ).all()

        for member in workspace_members:
            # Get all other members of this workspace
            other_members = db.exec(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == member.workspace_id,
                    WorkspaceMember.user_id != user_id,
                    WorkspaceMember.is_active == True,
                )
            ).all()
            relevant_users.update(m.user_id for m in other_members)

        # Add users from direct message conversations
        # First get all conversations the user is in
        user_conversations = select(ConversationMember.conversation_id).where(
            ConversationMember.user_id == user_id
        )

        # Then get all other members of those conversations
        dm_members = db.exec(
            select(ConversationMember)
            .join(Conversation)
            .where(
                and_(
                    Conversation.conversation_type == ConversationType.DIRECT_MESSAGE,
                    ConversationMember.user_id != user_id,
                    ConversationMember.conversation_id.in_(user_conversations),
                )
            )
        ).all()

        relevant_users.update(m.user_id for m in dm_members)

        return relevant_users

    async def broadcast_user_event(
        self, event_type: str, user_id: UUID, data: dict, db: Session
    ):
        """Broadcast a user event to all relevant users"""
        relevant_users = self.get_relevant_users_for_user(user_id, db)
        message = {"message_type": event_type, **data}
        await self.broadcast_to_users(message, relevant_users)

    async def broadcast_workspace_event(
        self, event_type: str, workspace_id: UUID, data: dict, db: Session
    ):
        """Broadcast a workspace event to all workspace members"""
        workspace_users = db.exec(
            select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)
        ).all()
        user_ids = {member.user_id for member in workspace_users}
        message = {"message_type": event_type, **data}
        await self.broadcast_to_users(message, user_ids)

    async def broadcast_channel_event(
        self, event_type: str, channel_id: UUID, data: dict, db: Session
    ):
        """Broadcast a channel event to all workspace members"""
        channel = db.exec(select(Channel).where(Channel.id == channel_id)).first()
        if not channel:
            return

        workspace_users = db.exec(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == channel.workspace_id
            )
        ).all()
        user_ids = {member.user_id for member in workspace_users}
        message = {"message_type": event_type, **data}
        await self.broadcast_to_users(message, user_ids)

    async def broadcast_conversation_event(
        self, event_type: str, conversation_id: UUID, data: dict, db: Session
    ):
        """Broadcast a conversation event to all conversation members"""
        conversation_users = db.exec(
            select(ConversationMember).where(
                ConversationMember.conversation_id == conversation_id
            )
        ).all()
        user_ids = {member.user_id for member in conversation_users}
        message = {"message_type": event_type, **data}
        await self.broadcast_to_users(message, user_ids)

    async def handle_user_online(self, user_id: UUID, db: Session):
        """Handle user coming online and broadcast to relevant users"""
        # First update the user's status in the database
        user = db.exec(select(User).where(User.id == user_id)).first()
        if not user:
            logger.error(f"User {user_id} not found")
            return

        user.is_online = True
        user.last_active = datetime.now(UTC)
        db.commit()

        # Get all users who should receive this update
        relevant_users = self.get_relevant_users_for_user(user_id, db)

        # Broadcast the online status to all relevant users
        message = {
            "user_id": str(user_id),
            "timestamp": datetime.now(UTC).isoformat(),
            "user": {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "display_name": user.display_name,
                "s3_key": user.s3_key,
                "is_online": True,
            },
        }
        await self.broadcast_to_users(
            {"message_type": "user_online", **message}, relevant_users
        )

    async def handle_user_offline(self, user_id: UUID, db: Session):
        message = {
            "user_id": str(user_id),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        await self.broadcast_user_event("user_offline", user_id, message, db)

    async def handle_user_typing(
        self, user_id: UUID, conversation_id: UUID, db: Session
    ):
        if conversation_id not in self.user_typing:
            self.user_typing[conversation_id] = set()

        self.user_typing[conversation_id].add(user_id)

        message = {
            "user_id": str(user_id),
            "conversation_id": str(conversation_id),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        await self.broadcast_conversation_event(
            event_type="user_is_typing",
            conversation_id=conversation_id,
            data=message,
            db=db,
        )

    async def handle_user_stopped_typing(
        self, user_id: UUID, conversation_id: UUID, db: Session
    ):
        if conversation_id in self.user_typing:
            self.user_typing[conversation_id].discard(user_id)

        message = {
            "user_id": str(user_id),
            "conversation_id": str(conversation_id),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        await self.broadcast_conversation_event(
            event_type="user_stopped_typing",
            conversation_id=conversation_id,
            data=message,
            db=db,
        )


# Create a global instance
ws = ConnectionManager()

""" AUTH ROUTES """


@router.post("/auth/register", response_model=GetUserResponse)
async def create_user(
    response: Response, user_data: UserCreateRequest, db: Session = Depends(get_db)
):
    user_manager = UserManager()
    user = user_manager.create_user(
        email=user_data.email,
        username=user_data.username,
        password=user_data.password,
        display_name=user_data.display_name,
        db=db,
    )

    auth_utils = AuthUtils()
    tokens = auth_utils.create_tokens(user.id)

    # Set cookies without domain restriction for development

    response.set_cookie(
        key="access_token",
        value=tokens.access_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=60 * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
        path="/",
    )

    return GetUserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        s3_key=user.s3_key,
        is_online=True,
    )


class UserLoginRequest(BaseModel):
    email: str
    password: str


@router.get("/auth/verify")
async def verify(user: User = Depends(get_current_user)):
    return {"message": "User verified"}


@router.post("/auth/login", response_model=GetUserResponse)
async def login(
    response: Response, user_data: UserLoginRequest, db: Session = Depends(get_db)
):
    user_manager = UserManager()
    user = user_manager.authenticate_user(user_data.email, user_data.password, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    auth_utils = AuthUtils()
    tokens = auth_utils.create_tokens(user.id)

    # Set cookies without domain restriction for development

    response.set_cookie(
        key="access_token",
        value=tokens.access_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=60 * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
        path="/",
    )

    # Send user online event
    await ws.broadcast_user_event("user_online", user.id, {"user_id": str(user.id)}, db)

    return GetUserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        s3_key=user.s3_key,
        is_online=True,
    )


@router.post("/auth/logout")
async def logout(
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    db_user = db.exec(select(User).where(User.id == user.id)).first()
    db_user.is_online = False
    db.commit()

    # Send user offline event
    await ws.broadcast_user_event(
        "user_offline", user.id, {"user_id": str(user.id)}, db
    )

    return {"message": "Logged out successfully"}


@router.get("/auth/refresh", response_model=GetUserResponse)
async def refresh(response: Response, user: User = Depends(get_current_user)):
    auth_utils = AuthUtils()
    tokens = auth_utils.create_tokens(user.id)
    response.set_cookie(
        key="access_token",
        value=tokens.access_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=60 * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
        path="/",
    )
    return GetUserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        s3_key=user.s3_key,
        is_online=True,
    )


""" USER ROUTES """


@router.get("/user/me", response_model=GetUserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return GetUserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        s3_key=user.s3_key,
        is_online=True,
    )


@router.get("/user/{user_id}", response_model=GetUserResponse)
async def get_user(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_manager = UserManager()
    user = user_manager.get_user_by_id(user_id, db)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return GetUserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        s3_key=user.s3_key,
        is_online=user.is_online,
    )


@router.get("/user/username-exists/{username}")
async def does_username_exist(username: str, db: Session = Depends(get_db)):
    user_manager = UserManager()
    return {"exists": user_manager.get_user_by_username(username, db) is not None}


@router.get("/user/email-exists/{email}")
async def does_email_exist(email: str, db: Session = Depends(get_db)):
    # We're using a string because it won't be an email while they're typing
    user_manager = UserManager()
    return {"exists": user_manager.get_user_by_email(email, db) is not None}


class UserUpdateRequest(BaseModel):
    display_name: str | None
    bio: str | None
    email: EmailStr | None
    username: str | None


@router.put("/user/me", response_model=GetUserResponse)
async def update_me(
    updates: UserUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    this_user = db.exec(select(User).where(User.id == user.id)).first()
    if this_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    this_user.display_name = updates.display_name or this_user.display_name
    this_user.bio = updates.bio or this_user.bio
    this_user.email = updates.email or this_user.email
    this_user.username = updates.username or this_user.username
    db.commit()

    # Send user updated event
    await ws.broadcast_user_event(
        "user_updated",
        this_user.id,
        {
            "user_id": str(this_user.id),
            "user": {
                "id": str(this_user.id),
                "username": this_user.username,
                "email": this_user.email,
                "display_name": this_user.display_name,
                "s3_key": this_user.s3_key,
                "is_online": this_user.is_online,
            },
        },
        db,
    )

    return GetUserResponse(
        id=this_user.id,
        username=this_user.username,
        email=this_user.email,
        display_name=this_user.display_name,
        s3_key=this_user.s3_key,
        is_online=True,
    )


@router.delete("/user/me")
async def delete_me(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # TODO: Send out websocket message to all users that the user has deleted their account
    # TODO: Cascade delete all of the user's data

    this_user = db.exec(select(User).where(User.id == user.id)).first()
    if this_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(this_user)
    db.commit()
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"message": "User deleted successfully"}


""" WORKSPACE ROUTES """


class WorkspaceResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    slug: str
    s3_key: str | None = None
    created_at: str
    created_by_id: str
    is_active: bool
    files: set[str]
    conversations: set[str]
    admins: set[str]
    members: set[str]

    model_config = ConfigDict(from_attributes=True)


class WorkspaceCreateRequest(BaseModel):
    name: str
    description: str | None = None


class WorkspaceUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    s3_key: str | None = None


class WorkspaceManager:
    def __init__(self, db: Session):
        self.db = db

    def get_workspace(self, workspace_id: str) -> WorkspaceResponse | None:
        query = (
            select(Workspace)
            .options(
                selectinload(Workspace.files),
                selectinload(Workspace.conversations),
                selectinload(Workspace.members).selectinload(User.workspace_members),
            )
            .where(Workspace.id == workspace_id)
        )
        result = self.db.exec(query)
        workspace = result.one_or_none()
        if not workspace:
            return None

        member_ids = set()
        admin_ids = set()

        for member in workspace.members:
            for wm in member.workspace_member:
                if wm.workspace_id == workspace_id:
                    member_role = wm.role
                    member_ids.add(str(member.id))
                    if member_role in (WorkspaceRole.ADMIN, WorkspaceRole.OWNER):
                        admin_ids.add(str(member.id))

        return WorkspaceResponse(
            id=str(workspace.id),
            name=workspace.name,
            description=workspace.description,
            slug=workspace.slug,
            s3_key=workspace.s3_key,
            created_at=workspace.created_at.isoformat(),
            created_by_id=str(workspace.created_by_id),
            is_active=workspace.is_active,
            files=member_ids,
            conversations=member_ids,
            admins=admin_ids,
            members=member_ids,
        )

    def get_workspaces(self, user: User) -> list[WorkspaceResponse]:
        query = (
            select(Workspace)
            .join(WorkspaceMember)
            .where(WorkspaceMember.user_id == user.id)
            .options(
                selectinload(Workspace.files),
                selectinload(Workspace.conversations),
                selectinload(Workspace.members).selectinload(User.workspace_members),
            )
        )
        result = self.db.exec(query)

        workspaces = result.all()

        workspace_responses = []
        for workspace in workspaces:
            member_ids = set()
            admin_ids = set()
            for member in workspace.members:
                for wm in member.workspace_members:
                    if wm.workspace_id == workspace.id:
                        member_role = wm.role
                        member_ids.add(str(member.id))
                        if member_role in (WorkspaceRole.ADMIN, WorkspaceRole.OWNER):
                            admin_ids.add(str(member.id))
            workspace_responses.append(
                WorkspaceResponse(
                    id=str(workspace.id),
                    name=workspace.name,
                    description=workspace.description,
                    slug=workspace.slug,
                    s3_key=workspace.s3_key,
                    created_at=workspace.created_at.isoformat(),
                    created_by_id=str(workspace.created_by_id),
                    is_active=workspace.is_active,
                    files={str(file.id) for file in workspace.files},
                    conversations={str(conv.id) for conv in workspace.conversations},
                    admins=admin_ids,
                    members=member_ids,
                )
            )
        return workspace_responses

    def create_workspace(
        self, workspace_create: WorkspaceCreateRequest, user: User
    ) -> WorkspaceResponse:
        slug = name_to_slug(workspace_create.name)
        existing_workspace = self.db.exec(
            select(Workspace).where(Workspace.slug == slug)
        ).first()
        if existing_workspace:
            raise HTTPException(
                status_code=400, detail="Workspace with this name already exists"
            )

        new_workspace = Workspace(
            name=workspace_create.name,
            description=workspace_create.description,
            slug=slug,
            created_by_id=user.id,
        )

        self.db.add(new_workspace)
        self.db.commit()
        self.db.refresh(new_workspace)

        self.db.add(
            WorkspaceMember(
                workspace_id=new_workspace.id,
                user_id=user.id,
                role=WorkspaceRole.OWNER,
            )
        )
        self.db.commit()
        return self.get_workspace(new_workspace.id)

    def verify_workspace_read_permission(self, workspace_id: str, user: User) -> bool:
        query = (
            select(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .where(WorkspaceMember.user_id == user.id)
        )
        result = self.db.exec(query)
        return result.first() is not None

    def verify_workspace_update_permission(self, workspace_id: str, user: User) -> bool:
        query = (
            select(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .where(WorkspaceMember.user_id == user.id)
            .where(WorkspaceMember.role.in_([WorkspaceRole.ADMIN, WorkspaceRole.OWNER]))
        )
        result = self.db.exec(query)
        return result.first() is not None

    def verify_workspace_delete_permission(self, workspace_id: str, user: User) -> bool:
        query = (
            select(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .where(WorkspaceMember.user_id == user.id)
            .where(WorkspaceMember.role.in_([WorkspaceRole.OWNER]))
        )
        result = self.db.exec(query)
        return result.first() is not None

    def verify_unique_workspace_slug(self, slug: str) -> bool:
        query = select(Workspace).where(Workspace.slug == slug)
        result = self.db.exec(query)
        return result.first() is None

    def update_workspace(
        self, workspace_id: str, workspace_update: WorkspaceUpdateRequest, user: User
    ) -> WorkspaceResponse:
        workspace = self.db.exec(
            select(Workspace).where(Workspace.id == workspace_id)
        ).first()
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        if workspace_update.name:
            slug = name_to_slug(workspace_update.name)
            if not self.verify_unique_workspace_slug(slug):
                raise HTTPException(
                    status_code=400, detail="Workspace with this name already exists"
                )
            workspace.slug = slug

        workspace.name = workspace_update.name or workspace.name
        workspace.description = workspace_update.description or workspace.description
        self.db.commit()
        return self.get_workspace(workspace_id)


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Get workspace with all necessary relationships preloaded
    workspace = db.exec(
        select(Workspace)
        .options(
            selectinload(Workspace.workspace_members),
            selectinload(Workspace.channels),
            selectinload(Workspace.files),
        )
        .where(Workspace.id == workspace_id)
    ).first()

    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Check if user is a member
    member = next(
        (m for m in workspace.workspace_members if m.user_id == user.id), None
    )
    if member is None:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get admin and member IDs
    member_ids = [str(m.user_id) for m in workspace.workspace_members]
    admin_ids = [
        str(m.user_id)
        for m in workspace.workspace_members
        if m.role in [WorkspaceRole.ADMIN, WorkspaceRole.OWNER]
    ]

    return WorkspaceResponse(
        id=str(workspace.id),
        name=workspace.name,
        description=workspace.description,
        slug=workspace.slug,
        role=member.role,
        created_at=workspace.created_at.isoformat(),
        created_by_id=str(workspace.created_by_id),
        is_active=workspace.is_active,
        files=[str(f.id) for f in workspace.files],
        conversations=[str(c.id) for c in workspace.channels],  # Include channel IDs
        admins=admin_ids,
        members=member_ids,
    )


@router.get("/workspaces", response_model=list[WorkspaceResponse])
async def get_workspaces(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    workspace_manager = WorkspaceManager(db)
    return workspace_manager.get_workspaces(user)


@router.post("/workspaces", response_model=WorkspaceResponse)
async def create_workspace(
    workspace_data: WorkspaceCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = Workspace(
        id=uuid4(),
        name=workspace_data.name,
        description=workspace_data.description,
        slug=name_to_slug(workspace_data.name),
        created_by_id=user.id,
        created_at=datetime.now(timezone.utc),
        is_active=True,
    )
    db.add(workspace)

    # Add creator as owner
    workspace_member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=user.id,
        role=WorkspaceRole.OWNER,
    )
    db.add(workspace_member)

    # Create general channel and its conversation
    general_conversation = Conversation(
        conversation_type=ConversationType.CHANNEL,
        workspace_id=workspace.id,
        name="general",  # Add name for the conversation
        description="General discussion channel",  # Add description for the conversation
    )
    db.add(general_conversation)
    db.commit()
    db.refresh(general_conversation)

    general_channel = Channel(
        id=uuid4(),
        name="general",
        description="General discussion channel",
        slug="general",
        workspace_id=workspace.id,
        created_by_id=user.id,
        conversation_id=general_conversation.id,
    )
    db.add(general_channel)

    # Add owner to the general channel's conversation
    conversation_member = ConversationMember(
        conversation_id=general_conversation.id,
        user_id=user.id,
        joined_at=datetime.now(UTC),
    )
    db.add(conversation_member)
    db.commit()

    # Send workspace created event
    await ws.broadcast_workspace_event(
        "workspace_created",
        workspace.id,
        {
            "workspace_id": str(workspace.id),
            "workspace": {
                "id": str(workspace.id),
                "name": workspace.name,
                "description": workspace.description,
                "slug": workspace.slug,
            },
        },
        db,
    )

    return WorkspaceResponse(
        id=str(workspace.id),
        name=workspace.name,
        description=workspace.description,
        slug=workspace.slug,
        role=WorkspaceRole.OWNER,
        created_at=workspace.created_at.isoformat(),
        created_by_id=str(workspace.created_by_id),
        is_active=workspace.is_active,
        files=[],
        conversations=[
            str(general_conversation.id)
        ],  # Include the general conversation
        admins=[str(user.id)],
        members=[str(user.id)],
    )


@router.put("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: UUID,
    workspace_data: WorkspaceCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.exec(select(Workspace).where(Workspace.id == workspace_id)).first()
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Check if user is admin or owner
    member = db.exec(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    ).first()
    if member is None or member.role not in [WorkspaceRole.ADMIN, WorkspaceRole.OWNER]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Update workspace
    workspace.name = workspace_data.name
    workspace.description = workspace_data.description
    workspace.slug = name_to_slug(workspace_data.name)
    db.commit()

    # Send workspace updated event
    await ws.broadcast_workspace_event(
        "workspace_updated",
        workspace.id,
        {
            "workspace_id": str(workspace.id),
            "workspace": {
                "id": str(workspace.id),
                "name": workspace.name,
                "description": workspace.description,
                "slug": workspace.slug,
            },
        },
        db,
    )

    return WorkspaceResponse(
        id=str(workspace.id),
        name=workspace.name,
        description=workspace.description,
        slug=workspace.slug,
        role=member.role,
        created_at=workspace.created_at.isoformat(),
        created_by_id=str(workspace.created_by_id),
        is_active=workspace.is_active,
        files=[],
        conversations=[],
        admins=[],
        members=[str(user.id)],
    )


@router.delete("/workspaces/{workspace_id}")
async def delete_workspace(
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.exec(select(Workspace).where(Workspace.id == workspace_id)).first()
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Check if user is owner
    member = db.exec(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    ).first()
    if member is None or member.role != WorkspaceRole.OWNER:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get all files in workspace to delete from S3
    files = db.exec(select(File).where(File.workspace_id == workspace_id)).all()
    storage = Storage()
    for file in files:
        # Delete from S3
        try:
            storage.delete_file(file.s3_key)
        except Exception as e:
            logger.error(f"Failed to delete file {file.s3_key} from S3: {e}")

    # Get all conversations in the workspace (both channels and DMs)
    conversations = db.exec(
        select(Conversation).where(Conversation.workspace_id == workspace_id)
    ).all()

    for conversation in conversations:
        # Delete all messages and their reactions
        messages = db.exec(
            select(Message).where(Message.conversation_id == conversation.id)
        ).all()
        for message in messages:
            # Delete message reactions
            db.exec(delete(Reaction).where(Reaction.message_id == message.id))
            # Delete message
            db.delete(message)

        # Delete conversation members
        db.exec(
            delete(ConversationMember).where(
                ConversationMember.conversation_id == conversation.id
            )
        )

        # Delete associated channel if it exists
        channel = db.exec(
            select(Channel).where(Channel.conversation_id == conversation.id)
        ).first()
        if channel:
            db.delete(channel)

        # Delete conversation
        db.delete(conversation)

    # Delete workspace members
    db.exec(delete(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id))

    # Delete workspace files
    db.exec(delete(File).where(File.workspace_id == workspace_id))

    # Finally delete workspace
    db.delete(workspace)
    db.commit()

    # Send workspace deleted event
    await ws.broadcast_workspace_event(
        "workspace_deleted",
        workspace_id,
        {
            "workspace_id": str(workspace_id),
        },
        db,
    )

    return {"message": "Workspace deleted successfully"}


""" SEARCH ROUTES """


class SearchType(Enum):
    WORKSPACES = "workspaces"
    USERS = "users"


class WorkspaceSearchResult(BaseModel):
    id: UUID
    name: str
    description: str | None
    slug: str
    s3_key: str | None


class UserSearchResult(BaseModel):
    id: UUID
    username: str
    display_name: str
    email: str
    s3_key: str | None
    is_online: bool


class SearchManager:
    def __init__(self, db: Session):
        self.db = db

    def search_workspaces(self, query: str) -> list[WorkspaceSearchResult]:
        query = select(Workspace).where(Workspace.name.ilike(f"%{query}%"))
        result = self.db.exec(query)
        return [
            WorkspaceSearchResult(
                id=workspace.id,
                name=workspace.name,
                description=workspace.description,
                slug=workspace.slug,
                s3_key=workspace.s3_key,
            )
            for workspace in result
        ]

    def search_users(self, query: str) -> list[GetUserResponse]:
        # Should search by username, display name, and email
        query = select(User).where(
            (User.username.ilike(f"%{query}%"))
            | (User.display_name.ilike(f"%{query}%"))
            | (User.email.ilike(f"%{query}%"))
        )
        result = self.db.exec(query)
        return [
            UserSearchResult(
                id=user.id,
                username=user.username,
                display_name=user.display_name,
                email=user.email,
                s3_key=user.s3_key,
                is_online=user.is_online,
            )
            for user in result
        ]


@router.get(
    "/search/{type}", response_model=list[WorkspaceSearchResult | UserSearchResult]
)
async def search(type: SearchType, query: str, db: Session = Depends(get_db)):
    search_manager = SearchManager(db)
    if type == SearchType.WORKSPACES:
        return search_manager.search_workspaces(query)
    elif type == SearchType.USERS:
        return search_manager.search_users(query)


""" MESSAGE ROUTES """


class MessageManager:
    def __init__(self, db: Session):
        self.db = db

    def verify_message_read_permission(self, message_id: str, user: User) -> bool:
        query = (
            select(Message)
            .where(Message.id == message_id)
            .where(Message.conversation.members.contains(user))
        )
        result = self.db.exec(query)
        return result.first() is not None

    def get_message(self, message_id: str) -> MessageResponse:
        query = select(Message).where(Message.id == message_id)
        result = self.db.exec(query).first()
        if not result:
            raise HTTPException(status_code=404, detail="Message not found")
        return MessageResponse(
            id=result.id,
            user_id=str(result.user_id),
            content=result.content,
            file_id=str(result.attachment.id) if result.attachment else None,
            reactions=result.reactions,
            children=[str(reply.id) for reply in result.replies],
            parent_id=str(result.parent_id) if result.parent_id else None,
            conversation_id=result.conversation_id,
            created_at=result.created_at,
            updated_at=result.updated_at,
        )


""" CHANNEL ROUTES """


class ChannelManager:
    def __init__(self, db: Session):
        self.db = db

    def verify_channel_read_permission(self, channel_id: UUID, user: User) -> bool:
        """Verify if a user has permission to read a channel."""
        query = (
            select(Channel)
            .join(Channel.workspace)
            .join(WorkspaceMember)
            .where(
                Channel.id == channel_id,
                WorkspaceMember.user_id == user.id,
                WorkspaceMember.is_active == True,
            )
        )
        result = self.db.exec(query)
        return result.first() is not None

    def verify_channel_write_permission(self, channel_id: UUID, user: User) -> bool:
        """Verify if a user has permission to modify a channel."""
        query = (
            select(Channel)
            .join(Channel.workspace)
            .join(WorkspaceMember)
            .where(
                Channel.id == channel_id,
                WorkspaceMember.user_id == user.id,
                WorkspaceMember.role.in_([WorkspaceRole.ADMIN, WorkspaceRole.OWNER]),
                WorkspaceMember.is_active == True,
            )
        )
        result = self.db.exec(query)
        return result.first() is not None

    def get_channel(self, channel_id: UUID) -> Optional[Channel]:
        """Get a channel by ID with its conversation and workspace preloaded."""
        query = (
            select(Channel)
            .options(
                selectinload(Channel.conversation), selectinload(Channel.workspace)
            )
            .where(Channel.id == channel_id)
        )
        return self.db.exec(query).first()

    def create_channel(
        self,
        name: str,
        workspace_id: UUID,
        description: Optional[str] = None,
        created_by_id: UUID = None,
        is_private: bool = False,
    ) -> Channel:
        # Get all workspace members first
        workspace_members = self.db.exec(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.is_active == True,
            )
        ).all()

        # First create the conversation
        conversation = Conversation(
            id=uuid4(),  # Explicitly create the ID
            conversation_type=ConversationType.CHANNEL,
            workspace_id=workspace_id,
            name=name,  # Mirror the channel name in conversation
            description=description,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)

        # Create the channel
        channel = Channel(
            id=uuid4(),  # Explicitly create the ID
            name=name,
            description=description,
            slug=self._generate_slug(name),
            workspace_id=workspace_id,
            created_by_id=created_by_id,
            conversation_id=conversation.id,
            is_private=is_private,
            created_at=datetime.now(UTC),
        )
        self.db.add(channel)

        # Add all workspace members to the conversation if the channel is public
        if not is_private:
            for workspace_member in workspace_members:
                conversation_member = ConversationMember(
                    conversation_id=conversation.id,
                    user_id=workspace_member.user_id,
                    joined_at=datetime.now(UTC),
                )
                self.db.add(conversation_member)
        else:
            # For private channels, at least add the creator
            if created_by_id:
                conversation_member = ConversationMember(
                    conversation_id=conversation.id,
                    user_id=created_by_id,
                    joined_at=datetime.now(UTC),
                )
                self.db.add(conversation_member)

        self.db.commit()
        self.db.refresh(channel)
        return channel

    def update_channel(self, channel_id: UUID, updates: dict, user: User) -> Channel:
        """Update a channel's information."""
        channel = self.get_channel(channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")

        if not self.verify_channel_write_permission(channel_id, user):
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to modify this channel",
            )

        # Update channel fields
        if "name" in updates:
            channel.name = updates["name"]
            channel.slug = self._generate_slug(updates["name"])
            # Also update the conversation name to keep them in sync
            channel.conversation.name = updates["name"]

        if "description" in updates:
            channel.description = updates["description"]
            channel.conversation.description = updates["description"]

        self.db.commit()
        self.db.refresh(channel)
        return channel

    def delete_channel(self, channel_id: UUID, user: User) -> None:
        """Delete a channel and its associated conversation."""
        channel = self.get_channel(channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")

        if not self.verify_channel_write_permission(channel_id, user):
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to delete this channel",
            )

        # Delete associated conversation members
        self.db.exec(
            delete(ConversationMember).where(
                ConversationMember.conversation_id == channel.conversation_id
            )
        )

        # Delete associated messages and their reactions
        messages = self.db.exec(
            select(Message).where(Message.conversation_id == channel.conversation_id)
        ).all()

        for message in messages:
            # Delete reactions
            self.db.exec(delete(Reaction).where(Reaction.message_id == message.id))
            # Delete message
            self.db.delete(message)

        # Delete associated files
        self.db.exec(
            delete(File).where(File.conversation_id == channel.conversation_id)
        )

        # Delete the conversation
        self.db.delete(channel.conversation)

        # Delete the channel
        self.db.delete(channel)
        self.db.commit()

    def _generate_slug(self, name: str) -> str:
        """Generate a URL-friendly slug from a channel name."""
        # Convert to lowercase and replace spaces/special chars with hyphens
        slug = "".join(c if c.isalnum() else "-" for c in name.lower())
        # Remove consecutive hyphens and trim
        slug = "-".join(filter(None, slug.split("-")))
        return slug

    def _add_workspace_members_to_conversation(
        self, workspace_id: UUID, conversation_id: UUID
    ) -> None:
        """Add all active workspace members to a conversation."""
        workspace_members = self.db.exec(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.is_active == True,
            )
        ).all()

        for member in workspace_members:
            conversation_member = ConversationMember(
                conversation_id=conversation_id,
                user_id=member.user_id,
                joined_at=datetime.now(UTC),
            )
            self.db.add(conversation_member)


@router.get("/channels/{channel_id}", response_model=ChannelResponse)
async def get_channel(
    channel_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    channel_manager = ChannelManager(db)
    if not channel_manager.verify_channel_read_permission(channel_id, user):
        raise HTTPException(
            status_code=403, detail="You do not have permission to view this channel"
        )
    channel = channel_manager.get_channel(channel_id)

    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    return ChannelResponse(
        id=channel.id,
        name=channel.name,
        description=channel.description,
        slug=channel.slug,
        workspace_id=channel.workspace_id,
        conversation_id=str(channel.conversation_id),
    )


@router.post("/workspaces/{workspace_id}/channels", response_model=ChannelResponse)
async def create_channel(
    workspace_id: UUID,
    channel_data: ChannelCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # First, verify that the workspace exists and is active
    workspace = db.exec(select(Workspace).where(Workspace.id == workspace_id)).first()
    if workspace is None:
        logger.error(f"Workspace {workspace_id} not found")
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Verify that the user has permission to create channels in this workspace
    member = db.exec(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    ).first()
    if member is None:
        logger.error(f"User {user.id} is not a member of workspace {workspace_id}")
        raise HTTPException(
            status_code=403, detail="Not authorized - Not a workspace member"
        )

    # Get all workspace members for later use
    workspace_members = db.exec(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.is_active == True,
        )
    ).all()

    # Verify the channel name doesn't already exist
    channel_slug = name_to_slug(channel_data.name)
    existing_channel = db.exec(
        select(Channel).where(
            Channel.workspace_id == workspace_id,
            Channel.slug == channel_slug,
            Channel.is_archived == False,
        )
    ).first()
    if existing_channel:
        logger.error(
            f"Channel with slug {channel_slug} already exists in workspace {workspace_id}"
        )
        raise HTTPException(
            status_code=409, detail="A channel with this name already exists"
        )

    try:
        # Create the conversation first
        conversation = Conversation(
            id=uuid4(),
            conversation_type=ConversationType.CHANNEL,
            workspace_id=workspace_id,
            name=channel_data.name,
            description=channel_data.description,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

        # Create the channel
        channel = Channel(
            id=uuid4(),
            name=channel_data.name,
            description=channel_data.description,
            slug=channel_slug,
            workspace_id=workspace_id,
            created_by_id=user.id,
            conversation_id=conversation.id,
            is_private=False,  # Default to public channels
        )
        db.add(channel)
        db.commit()
        db.refresh(channel)

        # Add members to the conversation
        members_added = 0
        for workspace_member in workspace_members:
            conversation_member = ConversationMember(
                conversation_id=conversation.id,
                user_id=workspace_member.user_id,
                joined_at=datetime.now(UTC),
            )
            db.add(conversation_member)
            members_added += 1

        db.commit()

        # Send channel created event
        try:
            await ws.broadcast_workspace_event(
                "channel_created",
                workspace_id,
                {
                    "channel_id": str(channel.id),
                    "channel": {
                        "id": str(channel.id),
                        "name": channel.name,
                        "description": channel.description,
                        "slug": channel.slug,
                        "workspace_id": str(workspace_id),
                        "conversation_id": str(conversation.id),
                    },
                },
                db,
            )
        except Exception as e:
            logger.error(f"Failed to broadcast channel creation event: {str(e)}")

        return ChannelResponse(
            id=channel.id,
            name=channel.name,
            description=channel.description,
            slug=channel.slug,
            workspace_id=workspace_id,
            conversation_id=str(conversation.id),
        )

    except Exception as e:
        logger.error(f"Error during channel creation: {str(e)}")
        # Roll back any partial changes
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to create channel: {str(e)}"
        )


@router.put("/channels/{channel_id}", response_model=GetChannelResponse)
async def update_channel(
    channel_id: UUID,
    channel_data: ChannelCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    channel = db.exec(select(Channel).where(Channel.id == channel_id)).first()
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")

    # Check if user is admin or owner of workspace
    member = db.exec(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == channel.workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    ).first()
    if member is None or member.role not in [WorkspaceRole.ADMIN, WorkspaceRole.OWNER]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Update channel
    channel.name = channel_data.name
    channel.description = channel_data.description
    channel.slug = name_to_slug(channel_data.name)
    db.commit()

    # Send channel updated event
    await ws.broadcast_channel_event(
        "channel_updated",
        {
            "channel_id": str(channel.id),
            "updates": {
                "name": channel.name,
                "description": channel.description,
                "slug": channel.slug,
            },
        },
        db,
    )

    return GetChannelResponse(
        id=channel.id,
        name=channel.name,
        description=channel.description,
        slug=channel.slug,
        workspace_id=channel.workspace_id,
    )


@router.delete("/channels/{channel_id}")
async def delete_channel(
    channel_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Get channel and workspace_id before deletion
    channel = db.get(Channel, channel_id)
    if not channel:
        raise CHANNEL_NOT_FOUND(channel_id)

    # Store workspace_id for broadcasting
    workspace_id = channel.workspace_id

    # Verify user has permission to delete channel
    channel_manager = ChannelManager(db)
    if not channel_manager.verify_channel_write_permission(channel_id, user):
        raise ForbiddenError("You do not have permission to delete this channel")

    # Delete channel
    channel_manager.delete_channel(channel_id, user)

    # Broadcast channel deleted event to all workspace members
    await ws.broadcast_workspace_event(
        "channel_deleted", workspace_id, {"channel_id": str(channel_id)}, db
    )

    return {"status": "success"}


@router.get("/workspaces/{workspace_id}/channels", response_model=list[ChannelResponse])
async def get_workspace_channels(
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all channels in a workspace."""
    # Verify workspace exists and user has access
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise NotFoundError("Workspace", str(workspace_id))

    # Check if user is a member using workspace_members relationship
    if not any(member.user_id == user.id for member in workspace.workspace_members):
        raise ForbiddenError("You are not a member of this workspace")

    # Get all channels in workspace with their conversations preloaded
    channels = db.exec(
        select(Channel)
        .options(selectinload(Channel.conversation))
        .where(Channel.workspace_id == workspace_id)
        .where(Channel.is_archived.is_(False))
    ).all()

    # Convert to response model format
    return [
        ChannelResponse(
            id=channel.id,
            name=channel.name,
            description=channel.description,
            slug=channel.slug,
            workspace_id=channel.workspace_id,
            conversation_id=str(channel.conversation_id),
        )
        for channel in channels
    ]


""" CONVERSATION ROUTES """


class ConversationManager:
    def __init__(self, db: Session):
        self.db = db

    def verify_conversation_access(self, conversation_id: UUID, user: User) -> bool:
        """Verify if a user has access to a conversation."""
        return True

    def get_conversation(self, conversation_id: UUID) -> Optional[Conversation]:
        """Get a conversation by ID with messages and members preloaded."""
        query = (
            select(Conversation)
            .options(
                selectinload(Conversation.messages).selectinload(Message.replies),
                selectinload(Conversation.conversation_members),
                selectinload(Conversation.channel),
            )
            .where(Conversation.id == conversation_id)
        )
        return self.db.exec(query).first()

    def get_channel_conversation(self, channel_id: UUID) -> Optional[Conversation]:
        """Get the conversation associated with a channel."""
        query = select(Conversation).join(Channel).where(Channel.id == channel_id)
        return self.db.exec(query).first()

    def create_direct_message(
        self, from_user_id: UUID, to_user_id: UUID
    ) -> Conversation:
        """Create or get a direct message conversation between two users."""
        # Check if DM conversation already exists
        existing_conv = self._find_direct_message_conversation(from_user_id, to_user_id)
        if existing_conv:
            return existing_conv

        # Create new conversation
        conversation = Conversation(
            id=uuid4(),
            conversation_type=ConversationType.DIRECT_MESSAGE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.db.add(conversation)

        # Add both users as members
        for user_id in [from_user_id, to_user_id]:
            member = ConversationMember(
                conversation_id=conversation.id,
                user_id=user_id,
                joined_at=datetime.now(UTC),
            )
            self.db.add(member)

        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def _find_direct_message_conversation(
        self, user1_id: UUID, user2_id: UUID
    ) -> Optional[Conversation]:
        """Find an existing direct message conversation between two users."""
        query = (
            select(Conversation)
            .join(ConversationMember)
            .where(
                and_(
                    Conversation.conversation_type == ConversationType.DIRECT_MESSAGE,
                    ConversationMember.user_id.in_([user1_id, user2_id]),
                )
            )
            .group_by(Conversation.id)
            .having(func.count(ConversationMember.user_id) == 2)
        )
        return self.db.exec(query).first()

    def get_direct_messages(self, user: User) -> list[Conversation]:
        """Get all direct message conversations for a user."""
        query = (
            select(Conversation)
            .join(ConversationMember)
            .options(
                selectinload(Conversation.messages),
                selectinload(Conversation.conversation_members).selectinload(
                    ConversationMember.user
                ),
            )
            .where(
                ConversationMember.user_id == user.id,
                Conversation.conversation_type == ConversationType.DIRECT_MESSAGE,
            )
            .order_by(Conversation.last_message_at.desc())
        )
        return self.db.exec(query).all()

    def add_member(self, conversation_id: UUID, user_id: UUID) -> None:
        """Add a member to a conversation."""
        # Check if already a member
        existing = self.db.exec(
            select(ConversationMember).where(
                ConversationMember.conversation_id == conversation_id,
                ConversationMember.user_id == user_id,
            )
        ).first()

        if not existing:
            member = ConversationMember(
                conversation_id=conversation_id,
                user_id=user_id,
                joined_at=datetime.now(UTC),
            )
            self.db.add(member)
            self.db.commit()

    def remove_member(self, conversation_id: UUID, user_id: UUID) -> None:
        """Remove a member from a conversation."""
        self.db.exec(
            delete(ConversationMember).where(
                ConversationMember.conversation_id == conversation_id,
                ConversationMember.user_id == user_id,
            )
        )
        self.db.commit()

    def get_messages(
        self, conversation_id: UUID, limit: int = 50, before_id: Optional[UUID] = None
    ) -> list[Message]:
        """Get messages from a conversation with pagination."""
        query = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
        )

        if before_id:
            message = self.db.get(Message, before_id)
            if message:
                query = query.where(Message.created_at < message.created_at)

        query = query.limit(limit)
        return self.db.exec(query).all()

    def send_message(
        self,
        conversation_id: UUID,
        user_id: UUID,
        content: Optional[str] = None,
        file_id: Optional[UUID] = None,
        parent_id: Optional[UUID] = None,
    ) -> Message:
        """Send a message in a conversation."""
        message = Message(
            id=uuid4(),
            conversation_id=conversation_id,
            user_id=user_id,
            content=content,
            parent_id=parent_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.db.add(message)

        if file_id:
            # Update the file to link it to this message
            file = self.db.get(File, file_id)
            if file:
                file.message_id = message.id

        # Update conversation's last_message_at
        conversation = self.db.get(Conversation, conversation_id)
        if conversation:
            conversation.last_message_at = message.created_at

        self.db.commit()
        self.db.refresh(message)
        return message


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation_manager = ConversationManager(db)
    conversation = conversation_manager.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Build a map of messages with their parent IDs
    message_map = {
        str(msg.id): {
            "id": str(msg.id),
            "parent_id": str(msg.parent_id) if msg.parent_id else None,
        }
        for msg in conversation.messages
    }

    return ConversationResponse(
        id=conversation.id,
        conversation_type=conversation.conversation_type,
        messages=[msg["id"] for msg in message_map.values()],
        message_parents={
            msg_id: msg["parent_id"]
            for msg_id, msg in message_map.items()
            if msg["parent_id"]
        },
        users_typing=set(),
        user_id=conversation.members[0].id
        if conversation.conversation_type == ConversationType.DIRECT_MESSAGE
        else None,
        channel_id=conversation.channel.id if conversation.channel else None,
    )


@router.get("/dm/all", response_model=list[ConversationResponse])
async def get_direct_messages(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation_manager = ConversationManager(db)
    conversations = conversation_manager.get_direct_messages(user)

    responses = []
    for conv in conversations:
        # Get all messages for the conversation
        messages = db.exec(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at)
        ).all()

        # Build message parents map
        message_parents = {}
        for msg in messages:
            if msg.parent_id:
                message_parents[str(msg.id)] = str(msg.parent_id)

        # Find the other user in the DM
        other_member = next(
            (
                member
                for member in conv.conversation_members
                if member.user_id != user.id
            ),
            None,
        )

        responses.append(
            ConversationResponse(
                id=conv.id,
                conversation_type=conv.conversation_type,
                messages=[str(msg.id) for msg in messages],
                message_parents=message_parents,
                users_typing=set(),
                user_id=other_member.user_id if other_member else None,
                channel_id=None,
            )
        )

    return responses


@router.post("/dm", response_model=ConversationResponse)
async def create_direct_message(
    dm: DirectMessageCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation_manager = ConversationManager(db)
    conversation = conversation_manager.create_direct_message(user.id, dm.user_id)

    # If initial message content is provided, create it
    if dm.content:
        message = Message(
            id=uuid4(),
            conversation_id=conversation.id,
            user_id=user.id,
            content=dm.content,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(message)
        db.commit()

    # Get all messages for the conversation
    messages = db.exec(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at)
    ).all()

    # Build message parents map
    message_parents = {}
    for msg in messages:
        if msg.parent_id:
            message_parents[str(msg.id)] = str(msg.parent_id)

    # Send conversation created event
    await ws.broadcast_conversation_event(
        "conversation_created",
        conversation.id,
        {
            "conversation_id": str(conversation.id),
            "conversation": {
                "id": str(conversation.id),
                "conversation_type": ConversationType.DIRECT_MESSAGE.value,
                "messages": [str(msg.id) for msg in messages],
                "message_parents": message_parents,
                "users_typing": set(),
                "user_id": str(dm.user_id),
                "channel_id": None,
                "name": None,
                "description": None,
            },
        },
        db,
    )

    return ConversationResponse(
        id=conversation.id,
        conversation_type=conversation.conversation_type,
        messages=[str(msg.id) for msg in messages],
        message_parents=message_parents,
        users_typing=set(),
        user_id=dm.user_id,
        channel_id=None,
    )


@router.post("/messages", response_model=MessageResponse)
async def send_message(
    message: MessageCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation_manager = ConversationManager(db)
    new_message = conversation_manager.send_message(message, user)

    # Send message sent event
    await ws.broadcast_conversation_event(
        event_type="message_sent",
        conversation_id=new_message.conversation_id,
        data={
            "message_id": str(new_message.id),
            "conversation_id": str(new_message.conversation_id),
            "user_id": str(new_message.user_id),
            "content": new_message.content,
            "file_id": str(new_message.attachment_id)
            if new_message.attachment_id
            else None,
            "parent_id": str(new_message.parent_id) if new_message.parent_id else None,
            "created_at": new_message.created_at.isoformat(),
            "updated_at": new_message.updated_at.isoformat(),
        },
        db=db,
    )

    logger.info(
        f"New message sent: id={new_message.id}, content={new_message.content}, parent_id={new_message.parent_id}"
    )

    return MessageResponse(
        id=new_message.id,
        user_id=new_message.user_id,
        content=new_message.content,
        file_id=new_message.attachment_id,
        reactions=set(),
        children=[],
        parent_id=new_message.parent_id,
        conversation_id=new_message.conversation_id,
        created_at=new_message.created_at,
        updated_at=new_message.updated_at,
    )


@router.get("/message/{message_id}", response_model=GetMessageResponse)
async def get_message(
    message_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    message = db.exec(
        select(Message)
        .options(selectinload(Message.attachment))
        .where(Message.id == message_id)
    ).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    logger.info(
        f"Getting message: id={message.id}, content={message.content}, parent_id={message.parent_id}"
    )

    return GetMessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        user_id=message.user_id,
        content=message.content,
        file_id=message.attachment.id if message.attachment else None,
        created_at=message.created_at,
        updated_at=message.updated_at,
        parent_id=message.parent_id,
    )


""" REACTION ROUTES """


class ReactionManager:
    def __init__(self, db: Session = Depends(get_db)):
        self.db = db

    def verify_reaction_permission(self, message_id: UUID, user: User) -> bool:
        query = (
            select(Message)
            .join(Conversation)
            .join(ConversationMember)
            .where(Message.id == message_id)
            .where(ConversationMember.user_id == user.id)
        )
        result = self.db.exec(query)
        return result.first() is not None

    def add_reaction(self, reaction: ReactionCreateRequest, user: User) -> Reaction:
        # Check if message exists
        message = self.db.exec(
            select(Message).where(Message.id == reaction.message_id)
        ).first()
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        # Check if user already reacted with this emoji
        existing_reaction = self.db.exec(
            select(Reaction)
            .where(Reaction.message_id == reaction.message_id)
            .where(Reaction.user_id == user.id)
            .where(Reaction.emoji == reaction.emoji)
        ).first()
        if existing_reaction:
            raise HTTPException(
                status_code=400, detail="You have already reacted with this emoji"
            )

        new_reaction = Reaction(
            message_id=reaction.message_id, user_id=user.id, emoji=reaction.emoji
        )
        self.db.add(new_reaction)
        self.db.commit()
        self.db.refresh(new_reaction)
        return new_reaction

    def remove_reaction(self, reaction_id: UUID, user: User) -> None:
        reaction = self.db.exec(
            select(Reaction).where(Reaction.id == reaction_id)
        ).first()
        if not reaction:
            raise HTTPException(status_code=404, detail="Reaction not found")

        if reaction.user_id != user.id:
            raise HTTPException(
                status_code=403, detail="You can only remove your own reactions"
            )

        self.db.delete(reaction)
        self.db.commit()


@router.post("/messages/{message_id}/reactions", response_model=ReactionResponse)
async def add_reaction(
    message_id: UUID,
    reaction_data: ReactionCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    message = db.exec(select(Message).where(Message.id == message_id)).first()
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")

    # Check if user is member of conversation
    member = db.exec(
        select(ConversationMember).where(
            ConversationMember.conversation_id == message.conversation_id,
            ConversationMember.user_id == user.id,
        )
    ).first()
    if member is None:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Check if reaction already exists
    existing_reaction = db.exec(
        select(Reaction).where(
            Reaction.message_id == message_id,
            Reaction.user_id == user.id,
            Reaction.emoji == reaction_data.emoji,
        )
    ).first()
    if existing_reaction is not None:
        raise HTTPException(status_code=400, detail="Reaction already exists")

    # Create reaction
    reaction = Reaction(
        id=uuid4(),
        message_id=message_id,
        user_id=user.id,
        emoji=reaction_data.emoji,
    )
    db.add(reaction)
    db.commit()

    # Send reaction added event
    await ws.broadcast_conversation_event(
        event_type="reaction_added",
        conversation_id=message.conversation_id,
        data={
            "message_id": str(message_id),
            "reaction": {
                "id": str(reaction.id),
                "emoji": reaction.emoji,
                "user_id": str(user.id),
            },
        },
        db=db,
    )

    return ReactionResponse(
        id=reaction.id,
        message_id=message_id,
        user_id=user.id,
        emoji=reaction.emoji,
    )


@router.delete("/messages/{message_id}/reactions/{reaction_id}")
async def remove_reaction(
    message_id: UUID,
    reaction_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    reaction = db.exec(select(Reaction).where(Reaction.id == reaction_id)).first()
    if reaction is None:
        raise HTTPException(status_code=404, detail="Reaction not found")

    # Check if user is author of reaction
    if reaction.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Delete reaction
    db.delete(reaction)
    db.commit()

    # Get the message
    message = db.exec(select(Message).where(Message.id == message_id)).first()

    # Send reaction removed event
    await ws.broadcast_conversation_event(
        event_type="reaction_removed",
        conversation_id=message.conversation_id,
        data={
            "message_id": str(message_id),
            "reaction_id": str(reaction_id),
        },
        db=db,
    )

    return {"message": "Reaction removed successfully"}


""" FILE ROUTES """


class FileManager:
    def __init__(self, db: Session = Depends(get_db)):
        self.db = db

    def verify_file_access(self, file_id: UUID, user: User) -> bool:
        query = (
            select(File)
            .where(File.id == file_id)
            .where(
                or_(
                    File.user_id == user.id,
                    File.workspace_id.in_(
                        select(Workspace.id)
                        .join(WorkspaceMember)
                        .where(WorkspaceMember.user_id == user.id)
                    ),
                    File.conversation_id.in_(
                        select(Conversation.id)
                        .join(ConversationMember)
                        .where(ConversationMember.user_id == user.id)
                    ),
                )
            )
        )
        result = self.db.exec(query)
        return result.first() is not None

    def get_file(self, file_id: UUID) -> File:
        query = select(File).where(File.id == file_id)
        result = self.db.exec(query)
        return result.first()

    async def create_file(
        self,
        file_data: UploadFile,
        user: User,
        workspace_id: UUID | None = None,
        conversation_id: UUID | None = None,
        message_id: UUID | None = None,
    ) -> File:
        # Verify permissions first
        if workspace_id:
            workspace_member = self.db.exec(
                select(WorkspaceMember)
                .where(WorkspaceMember.workspace_id == workspace_id)
                .where(WorkspaceMember.user_id == user.id)
            ).first()
            if not workspace_member:
                raise HTTPException(
                    status_code=403, detail="You do not have access to this workspace"
                )

        if conversation_id:
            conversation_member = self.db.exec(
                select(ConversationMember)
                .where(ConversationMember.conversation_id == conversation_id)
                .where(ConversationMember.user_id == user.id)
            ).first()
            if not conversation_member:
                raise HTTPException(
                    status_code=403,
                    detail="You do not have access to this conversation",
                )

        # Read file content
        file_content = await file_data.read()
        file_size = len(file_content)

        # Create file record first to get the ID
        new_file = File(
            original_filename=file_data.filename,
            file_type=FileType.from_filename(file_data.filename),
            mime_type=file_data.content_type,
            file_size=file_size,
            user_id=user.id,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            message_id=message_id,
        )
        self.db.add(new_file)
        self.db.commit()
        self.db.refresh(new_file)

        # Use the file ID as the S3 key
        storage = Storage()
        if not storage.upload_file(
            file_content, str(new_file.id), file_data.content_type
        ):
            # If S3 upload fails, delete the database record
            self.db.delete(new_file)
            self.db.commit()
            raise HTTPException(status_code=500, detail="Failed to upload file to S3")

        return new_file

    def delete_file(self, file_id: UUID, user: User) -> None:
        file = self.get_file(file_id)
        if not file:
            raise HTTPException(status_code=404, detail="File not found")

        # Only file owner or workspace admin can delete files
        can_delete = file.user_id == user.id
        if file.workspace_id:
            workspace_role = self.db.exec(
                select(WorkspaceMember)
                .where(WorkspaceMember.workspace_id == file.workspace_id)
                .where(WorkspaceMember.user_id == user.id)
                .where(
                    WorkspaceMember.role.in_([WorkspaceRole.ADMIN, WorkspaceRole.OWNER])
                )
            ).first()
            can_delete = can_delete or bool(workspace_role)

        if not can_delete:
            raise HTTPException(
                status_code=403, detail="You do not have permission to delete this file"
            )

        self.db.delete(file)
        self.db.commit()


@router.get("/files/{file_id}", response_model=FileResponse)
async def get_file(
    file_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    file_manager = FileManager(db)

    # Verify access
    if not file_manager.verify_file_access(file_id, user):
        raise ForbiddenError("You don't have access to this file")

    # Get file
    file = file_manager.get_file(file_id)
    if not file:
        raise NotFoundError("File", str(file_id))

    return file


@router.post("/files", response_model=FileResponse)
async def upload_file(
    file: UploadFile,
    workspace_id: UUID | None = None,
    conversation_id: UUID | None = None,
    message_id: UUID | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    file_manager = FileManager(db)
    return await file_manager.create_file(
        file, user, workspace_id, conversation_id, message_id
    )


@router.delete("/files/{file_id}")
async def delete_file(
    file_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    file_manager = FileManager(db)
    file_manager.delete_file(file_id, user)
    return {"message": "File deleted successfully"}


@router.post("/workspaces/{workspace_id}/members/{user_id}")
async def add_workspace_member(
    workspace_id: UUID,
    user_id: UUID,
    role: WorkspaceRole,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.exec(select(Workspace).where(Workspace.id == workspace_id)).first()
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Check if current user is admin or owner
    current_member = db.exec(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == current_user.id,
        )
    ).first()
    if current_member is None or current_member.role not in [
        WorkspaceRole.ADMIN,
        WorkspaceRole.OWNER,
    ]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Check if user exists
    user = db.exec(select(User).where(User.id == user_id)).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if user is already a member
    existing_member = db.exec(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    ).first()
    if existing_member is not None:
        raise HTTPException(status_code=400, detail="User is already a member")

    # Add member
    member = WorkspaceMember(
        workspace_id=workspace_id,
        user_id=user_id,
        role=role,
    )
    db.add(member)
    db.commit()

    # Send user joined workspace event
    await ws.broadcast_user_event(
        "user_joined_workspace",
        user.id,
        {
            "workspace_id": str(workspace_id),
            "user_id": str(user_id),
            "role": role.value,
            "user": {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "display_name": user.display_name,
                "s3_key": user.s3_key,
                "is_online": user.is_online,
            },
        },
        db,
    )

    return {"message": "Member added successfully"}


@router.delete("/workspaces/{workspace_id}/members/{user_id}")
async def remove_workspace_member(
    workspace_id: UUID,
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.exec(select(Workspace).where(Workspace.id == workspace_id)).first()
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Check if current user is admin or owner
    current_member = db.exec(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == current_user.id,
        )
    ).first()
    if current_member is None or current_member.role not in [
        WorkspaceRole.ADMIN,
        WorkspaceRole.OWNER,
    ]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Check if user exists and is a member
    member = db.exec(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    ).first()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    # Cannot remove owner
    if member.role == WorkspaceRole.OWNER:
        raise HTTPException(status_code=403, detail="Cannot remove owner")

    # If target is admin and current user is not owner, deny
    if (
        member.role == WorkspaceRole.ADMIN
        and current_member.role != WorkspaceRole.OWNER
    ):
        raise HTTPException(
            status_code=403, detail="Only workspace owner can remove admins"
        )

    # Get all channels in workspace
    channels = db.exec(
        select(Channel).where(Channel.workspace_id == workspace_id)
    ).all()

    storage = Storage()
    deleted_message_ids = set()
    deleted_file_ids = set()
    deleted_reaction_data = []  # Store message_id and reaction_id pairs

    # Process each channel
    for channel in channels:
        # Get all messages by the member in this channel
        messages = db.exec(
            select(Message)
            .join(Conversation)
            .where(
                Message.user_id == user_id, Conversation.id == channel.conversation_id
            )
        ).all()

        for message in messages:
            # Delete message files from S3 and database
            if message.attachment:
                try:
                    storage.delete_file(str(message.attachment.id))
                    deleted_file_ids.add(message.attachment.id)
                    db.delete(message.attachment)
                except Exception as e:
                    logger.error(
                        f"Failed to delete file {message.attachment.id} from S3: {e}"
                    )

            # Delete all reactions to this message
            db.exec(delete(Reaction).where(Reaction.message_id == message.id))

            # Get and delete all replies to this message
            replies = db.exec(
                select(Message).where(Message.parent_id == message.id)
            ).all()
            for reply in replies:
                # Delete reply files
                if reply.attachment:
                    try:
                        storage.delete_file(str(reply.attachment.id))
                        deleted_file_ids.add(reply.attachment.id)
                        db.delete(reply.attachment)
                    except Exception as e:
                        logger.error(
                            f"Failed to delete file {reply.attachment.id} from S3: {e}"
                        )

                # Delete reply reactions
                db.exec(delete(Reaction).where(Reaction.message_id == reply.id))
                deleted_message_ids.add(reply.id)
                db.delete(reply)

            deleted_message_ids.add(message.id)
            db.delete(message)

        # Get all reactions by the member in this channel's conversation
        reactions = db.exec(
            select(Reaction)
            .join(Message)
            .join(Conversation)
            .where(
                Reaction.user_id == user_id, Conversation.id == channel.conversation_id
            )
        ).all()

        # Delete member's reactions and store data for websocket events
        for reaction in reactions:
            deleted_reaction_data.append(
                {
                    "message_id": str(reaction.message_id),
                    "reaction_id": str(reaction.id),
                }
            )
            db.delete(reaction)

        # Remove member from channel's conversation
        db.exec(
            delete(ConversationMember).where(
                ConversationMember.conversation_id == channel.conversation_id,
                ConversationMember.user_id == user_id,
            )
        )

    # Delete any workspace files owned by the member
    workspace_files = db.exec(
        select(File).where(File.workspace_id == workspace_id, File.user_id == user_id)
    ).all()

    for file in workspace_files:
        try:
            storage.delete_file(str(file.id))
            deleted_file_ids.add(file.id)
            db.delete(file)
        except Exception as e:
            logger.error(f"Failed to delete file {file.id} from S3: {e}")

    # Finally remove the member from workspace
    db.delete(member)
    db.commit()

    # Send websocket events
    # 1. Message deletion events
    for message_id in deleted_message_ids:
        await ws.broadcast_workspace_event(
            "message_deleted",
            workspace_id,
            {
                "message_id": str(message_id),
                "workspace_id": str(workspace_id),
            },
            db,
        )

    # 2. File deletion events
    for file_id in deleted_file_ids:
        await ws.broadcast_workspace_event(
            "file_deleted",
            workspace_id,
            {
                "file_id": str(file_id),
                "workspace_id": str(workspace_id),
            },
            db,
        )

    # 3. Reaction removal events
    for reaction_data in deleted_reaction_data:
        await ws.broadcast_workspace_event(
            "reaction_removed",
            workspace_id,
            {
                "message_id": reaction_data["message_id"],
                "reaction_id": reaction_data["reaction_id"],
                "workspace_id": str(workspace_id),
            },
            db,
        )

    # 4. Member removal event
    await ws.broadcast_workspace_event(
        "member_removed",
        workspace_id,
        {
            "workspace_id": str(workspace_id),
            "user_id": str(user_id),
        },
        db,
    )

    return {"message": "Member removed successfully"}


@router.delete("/workspaces/{workspace_id}/admins/{user_id}")
async def remove_workspace_admin(
    workspace_id: UUID,
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.exec(select(Workspace).where(Workspace.id == workspace_id)).first()
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Check if current user is owner
    current_member = db.exec(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == current_user.id,
            WorkspaceMember.role == WorkspaceRole.OWNER,
        )
    ).first()
    if current_member is None:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Check if target user exists and is an admin
    admin_member = db.exec(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.role == WorkspaceRole.ADMIN,
        )
    ).first()
    if admin_member is None:
        raise HTTPException(status_code=404, detail="Admin not found")

    # Get all channels in workspace
    channels = db.exec(
        select(Channel).where(Channel.workspace_id == workspace_id)
    ).all()

    storage = Storage()
    deleted_message_ids = set()
    deleted_file_ids = set()
    deleted_reaction_data = []  # Store message_id and reaction_id pairs

    # Process each channel
    for channel in channels:
        # Get all messages by the admin in this channel
        messages = db.exec(
            select(Message)
            .join(Conversation)
            .where(
                Message.user_id == user_id, Conversation.id == channel.conversation_id
            )
        ).all()

        for message in messages:
            # Delete message files from S3 and database
            if message.attachment:
                try:
                    storage.delete_file(str(message.attachment.id))
                    deleted_file_ids.add(message.attachment.id)
                    db.delete(message.attachment)
                except Exception as e:
                    logger.error(
                        f"Failed to delete file {message.attachment.id} from S3: {e}"
                    )

            # Delete all reactions to this message
            db.exec(delete(Reaction).where(Reaction.message_id == message.id))

            # Get and delete all replies to this message
            replies = db.exec(
                select(Message).where(Message.parent_id == message.id)
            ).all()
            for reply in replies:
                # Delete reply files
                if reply.attachment:
                    try:
                        storage.delete_file(str(reply.attachment.id))
                        deleted_file_ids.add(reply.attachment.id)
                        db.delete(reply.attachment)
                    except Exception as e:
                        logger.error(
                            f"Failed to delete file {reply.attachment.id} from S3: {e}"
                        )

                # Delete reply reactions
                db.exec(delete(Reaction).where(Reaction.message_id == reply.id))
                deleted_message_ids.add(reply.id)
                db.delete(reply)

            deleted_message_ids.add(message.id)
            db.delete(message)

        # Get all reactions by the admin in this channel's conversation
        reactions = db.exec(
            select(Reaction)
            .join(Message)
            .join(Conversation)
            .where(
                Reaction.user_id == user_id, Conversation.id == channel.conversation_id
            )
        ).all()

        # Delete admin's reactions and store data for websocket events
        for reaction in reactions:
            deleted_reaction_data.append(
                {
                    "message_id": str(reaction.message_id),
                    "reaction_id": str(reaction.id),
                }
            )
            db.delete(reaction)

        # Remove admin from channel's conversation
        db.exec(
            delete(ConversationMember).where(
                ConversationMember.conversation_id == channel.conversation_id,
                ConversationMember.user_id == user_id,
            )
        )

    # Delete any workspace files owned by the admin
    workspace_files = db.exec(
        select(File).where(File.workspace_id == workspace_id, File.user_id == user_id)
    ).all()

    for file in workspace_files:
        try:
            storage.delete_file(str(file.id))
            deleted_file_ids.add(file.id)
            db.delete(file)
        except Exception as e:
            logger.error(f"Failed to delete file {file.id} from S3: {e}")

    # Finally remove the admin from workspace
    db.delete(admin_member)
    db.commit()

    # Send websocket events
    # 1. Message deletion events
    for message_id in deleted_message_ids:
        await ws.broadcast_workspace_event(
            "message_deleted",
            workspace_id,
            {
                "message_id": str(message_id),
                "workspace_id": str(workspace_id),
            },
            db,
        )

    # 2. File deletion events
    for file_id in deleted_file_ids:
        await ws.broadcast_workspace_event(
            "file_deleted",
            workspace_id,
            {
                "file_id": str(file_id),
                "workspace_id": str(workspace_id),
            },
            db,
        )

    # 3. Reaction removal events
    for reaction_data in deleted_reaction_data:
        await ws.broadcast_workspace_event(
            "reaction_removed",
            workspace_id,
            {
                "message_id": reaction_data["message_id"],
                "reaction_id": reaction_data["reaction_id"],
                "workspace_id": str(workspace_id),
            },
            db,
        )

    # 4. Admin removal event
    await ws.broadcast_workspace_event(
        "admin_removed",
        workspace_id,
        {
            "workspace_id": str(workspace_id),
            "user_id": str(user_id),
        },
        db,
    )

    return {"message": "Admin removed successfully"}


class UpdateMemberRoleRequest(BaseModel):
    role: WorkspaceRole


@router.patch("/workspaces/{workspace_id}/members/{user_id}")
async def update_workspace_member_role(
    workspace_id: UUID,
    user_id: UUID,
    role_request: UpdateMemberRoleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.exec(select(Workspace).where(Workspace.id == workspace_id)).first()
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Check if current user is owner
    current_member = db.exec(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == current_user.id,
            WorkspaceMember.role == WorkspaceRole.OWNER,
        )
    ).first()
    if current_member is None:
        raise HTTPException(
            status_code=403,
            detail="Not authorized - only workspace owner can change roles",
        )

    # Check if user exists and is a member
    member = db.exec(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    ).first()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    # Cannot change owner's role
    if member.role == WorkspaceRole.OWNER:
        raise HTTPException(status_code=403, detail="Cannot change owner's role")

    # Cannot set role to owner
    if role_request.role == WorkspaceRole.OWNER:
        raise HTTPException(status_code=400, detail="Cannot set role to owner")

    # Update role
    old_role = member.role
    member.role = role_request.role
    db.commit()

    # Send workspace role updated event
    await ws.broadcast_workspace_event(
        "workspace_role_updated",
        workspace_id,
        {
            "workspace_id": str(workspace_id),
            "user_id": str(user_id),
            "old_role": old_role.value,
            "new_role": role_request.role.value,
        },
        db,
    )

    return {
        "message": "Role updated successfully",
        "user_id": str(user_id),
        "old_role": old_role.value,
        "new_role": role_request.role.value,
    }


@router.post(
    "/conversations/{conversation_id}/messages", response_model=GetMessageResponse
)
async def create_message(
    conversation_id: UUID,
    message_data: MessageCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = db.exec(
        select(Conversation).where(Conversation.id == conversation_id)
    ).first()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if user is member of conversation
    member = db.exec(
        select(ConversationMember).where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id == user.id,
        )
    ).first()
    if member is None:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Create message
    now = datetime.now(UTC)
    message = Message(
        id=uuid4(),
        conversation_id=conversation_id,
        user_id=user.id,
        content=message_data.content,
        parent_id=message_data.parent_id,
        created_at=now,
        updated_at=now,
    )
    db.add(message)

    # Add file attachments if any
    if message_data.file_id:
        file = db.exec(select(File).where(File.id == message_data.file_id)).first()
        if file is None:
            raise HTTPException(
                status_code=404, detail=f"File {message_data.file_id} not found"
            )
        file.message_id = message.id

    db.commit()

    # Send message sent event with full message data
    await ws.broadcast_conversation_event(
        event_type="message_sent",
        conversation_id=message.conversation_id,
        data={
            "message_id": str(message.id),
            "conversation_id": str(conversation_id),
            "user_id": str(message.user_id),
            "content": message.content,
            "parent_id": str(message.parent_id) if message.parent_id else None,
            "created_at": message.created_at.isoformat(),
            "updated_at": message.updated_at.isoformat(),
            "file_id": str(message_data.file_id) if message_data.file_id else None,
        },
        db=db,
    )

    return GetMessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        user_id=message.user_id,
        content=message.content,
        file_id=message_data.file_id,
        created_at=message.created_at,
        updated_at=message.updated_at,
        parent_id=message.parent_id,
    )


@router.delete("/messages/{message_id}")
async def delete_message(
    message_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    message = db.exec(select(Message).where(Message.id == message_id)).first()
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")

    # Check if user is author
    if message.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Delete message
    db.delete(message)
    db.commit()

    # Send message deleted event
    await ws.broadcast_conversation_event(
        event_type="message_deleted",
        conversation_id=message.conversation_id,
        data={
            "message_id": str(message_id),
            "conversation_id": str(message.conversation_id),
        },
        db=db,
    )

    return {"message": "Message deleted successfully"}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Get conversation
    conversation = db.exec(
        select(Conversation).where(Conversation.id == conversation_id)
    ).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check permissions
    if conversation.channel_id:
        channel = db.exec(
            select(Channel).where(Channel.id == conversation.channel_id)
        ).first()
        if channel:
            member = db.exec(
                select(WorkspaceMember).where(
                    and_(
                        WorkspaceMember.workspace_id == channel.workspace_id,
                        WorkspaceMember.user_id == user.id,
                    )
                )
            ).first()
            if not member or member.role not in [
                WorkspaceRole.ADMIN,
                WorkspaceRole.OWNER,
            ]:
                raise HTTPException(status_code=403, detail="Not authorized")
    else:
        member = db.exec(
            select(ConversationMember).where(
                and_(
                    ConversationMember.conversation_id == conversation_id,
                    ConversationMember.user_id == user.id,
                )
            )
        ).first()
        if not member:
            raise HTTPException(status_code=403, detail="Not authorized")

    # Delete files from S3
    files = db.exec(select(File).where(File.conversation_id == conversation_id)).all()
    storage = Storage()
    for file in files:
        try:
            storage.delete_file(file.s3_key)
        except Exception as e:
            logger.error(f"Failed to delete file {file.s3_key} from S3: {e}")

    # Delete all messages and reactions
    messages = db.exec(
        select(Message).where(Message.conversation_id == conversation_id)
    ).all()
    for message in messages:
        db.exec(delete(Reaction).where(Reaction.message_id == message.id))
        db.delete(message)

    # Delete conversation members and files
    db.exec(
        delete(ConversationMember).where(
            ConversationMember.conversation_id == conversation_id
        )
    )
    db.exec(delete(File).where(File.conversation_id == conversation_id))

    # Delete conversation
    db.delete(conversation)
    db.commit()

    # Send event
    await ws.broadcast_conversation_event(
        event_type="conversation_deleted",
        conversation_id=conversation_id,
        data={"conversation_id": str(conversation_id)},
        db=db,
    )

    return {"message": "Conversation deleted successfully"}


@router.get("/files/{file_id}/download")
async def get_file_download_url(
    file_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a presigned URL for downloading a file."""
    file_manager = FileManager(db)

    # Verify access
    if not file_manager.verify_file_access(file_id, user):
        raise ForbiddenError("You don't have access to this file")

    # Get file
    file = file_manager.get_file(file_id)
    if not file:
        raise NotFoundError("File", str(file_id))

    # Get presigned URL
    storage = Storage()
    presigned_url = storage.create_presigned_url(file.id)
    if not presigned_url:
        raise APIError(500, "Failed to generate download URL")

    return {"s3_url": presigned_url}


@router.get("/workspaces/{workspace_id}/channels/exists")
async def check_channel_exists(
    workspace_id: UUID,
    name: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Verify user has access to workspace
    workspace = db.exec(select(Workspace).where(Workspace.id == workspace_id)).first()
    if not workspace:
        raise WORKSPACE_NOT_FOUND(workspace_id)

    member = db.exec(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    ).first()
    if not member:
        raise NOT_WORKSPACE_MEMBER()

    # Check if channel exists with this name
    channel_slug = name_to_slug(name)
    channel = db.exec(
        select(Channel).where(
            Channel.workspace_id == workspace_id,
            Channel.slug == channel_slug,
        )
    ).first()

    return {"exists": channel is not None}


@router.get("/workspaces/exists/{name}")
async def check_workspace_exists(
    name: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Convert name to slug
    workspace_slug = name_to_slug(name)

    # Check if workspace exists with this slug
    workspace = db.exec(
        select(Workspace).where(
            Workspace.slug == workspace_slug,
        )
    ).first()

    return {"exists": workspace is not None}


@router.post("/workspaces/{workspace_id}/join")
async def join_workspace(
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Get workspace
    workspace = db.exec(select(Workspace).where(Workspace.id == workspace_id)).first()
    if not workspace:
        raise NotFoundError("Workspace", str(workspace_id))

    # Check if user is already a member
    existing_member = db.exec(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    ).first()
    if existing_member:
        raise ConflictError("You are already a member of this workspace")

    # Add user as member
    member = WorkspaceMember(
        workspace_id=workspace_id,
        user_id=user.id,
        role=WorkspaceRole.MEMBER,
    )
    db.add(member)

    # Auto-join all public channels
    channels = db.exec(
        select(Channel).where(
            Channel.workspace_id == workspace_id,
            Channel.is_private.is_(False),
            Channel.is_archived.is_(False),
        )
    ).all()

    for channel in channels:
        conversation_member = ConversationMember(
            conversation_id=channel.conversation_id,
            user_id=user.id,
        )
        db.add(conversation_member)

    db.commit()

    # Send user joined workspace event
    await ws.broadcast_user_event(
        "user_joined_workspace",
        user.id,
        {
            "workspace_id": str(workspace_id),
            "user_id": str(user.id),
            "role": WorkspaceRole.MEMBER.value,
            "user": {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "display_name": user.display_name,
                "s3_key": user.s3_key,
                "is_online": user.is_online,
            },
        },
        db,
    )

    return {"message": "Successfully joined workspace"}


@router.post("/workspaces/{workspace_id}/leave")
async def leave_workspace(
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Get workspace
    workspace = db.exec(select(Workspace).where(Workspace.id == workspace_id)).first()
    if not workspace:
        raise NotFoundError("Workspace", str(workspace_id))

    # Check if user is a member
    member = db.exec(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    ).first()
    if not member:
        raise ConflictError("You are not a member of this workspace")

    # Cannot leave if you're the owner
    if member.role == WorkspaceRole.OWNER:
        raise ForbiddenError("Workspace owner cannot leave the workspace")

    storage = Storage()
    deleted_message_ids = set()
    deleted_file_ids = set()
    deleted_reaction_data = []  # Store message_id and reaction_id pairs

    # Get all channels in workspace
    channels = db.exec(
        select(Channel).where(Channel.workspace_id == workspace_id)
    ).all()

    # Process each channel
    for channel in channels:
        # Get all messages by the user in this channel
        messages = db.exec(
            select(Message)
            .join(Conversation)
            .where(
                Message.user_id == user.id, Conversation.id == channel.conversation_id
            )
        ).all()

        for message in messages:
            # Delete message files from S3 and database
            if message.attachment:
                try:
                    storage.delete_file(str(message.attachment.id))
                    deleted_file_ids.add(message.attachment.id)
                    db.delete(message.attachment)
                except Exception as e:
                    logger.error(
                        f"Failed to delete file {message.attachment.id} from S3: {e}"
                    )

            # Delete all reactions to this message
            db.exec(delete(Reaction).where(Reaction.message_id == message.id))

            # Get and delete all replies to this message
            replies = db.exec(
                select(Message).where(Message.parent_id == message.id)
            ).all()
            for reply in replies:
                # Delete reply files
                if reply.attachment:
                    try:
                        storage.delete_file(str(reply.attachment.id))
                        deleted_file_ids.add(reply.attachment.id)
                        db.delete(reply.attachment)
                    except Exception as e:
                        logger.error(
                            f"Failed to delete file {reply.attachment.id} from S3: {e}"
                        )

                # Delete reply reactions
                db.exec(delete(Reaction).where(Reaction.message_id == reply.id))
                deleted_message_ids.add(reply.id)
                db.delete(reply)

            deleted_message_ids.add(message.id)
            db.delete(message)

        # Get all reactions by the user in this channel's conversation
        reactions = db.exec(
            select(Reaction)
            .join(Message)
            .join(Conversation)
            .where(
                Reaction.user_id == user.id, Conversation.id == channel.conversation_id
            )
        ).all()

        # Delete user's reactions and store data for websocket events
        for reaction in reactions:
            deleted_reaction_data.append(
                {
                    "message_id": str(reaction.message_id),
                    "reaction_id": str(reaction.id),
                }
            )
            db.delete(reaction)

        # Remove from channel's conversation
        db.exec(
            delete(ConversationMember).where(
                ConversationMember.conversation_id == channel.conversation_id,
                ConversationMember.user_id == user.id,
            )
        )

    # Delete any workspace files owned by the user
    workspace_files = db.exec(
        select(File).where(File.workspace_id == workspace_id, File.user_id == user.id)
    ).all()

    for file in workspace_files:
        try:
            storage.delete_file(str(file.id))
            deleted_file_ids.add(file.id)
            db.delete(file)
        except Exception as e:
            logger.error(f"Failed to delete file {file.id} from S3: {e}")

    # Remove workspace member
    db.delete(member)
    db.commit()

    # Send websocket events
    # 1. Message deletion events
    for message_id in deleted_message_ids:
        await ws.broadcast_workspace_event(
            "message_deleted",
            workspace_id,
            {
                "message_id": str(message_id),
                "workspace_id": str(workspace_id),
            },
            db,
        )

    # 2. File deletion events
    for file_id in deleted_file_ids:
        await ws.broadcast_workspace_event(
            "file_deleted",
            workspace_id,
            {
                "file_id": str(file_id),
                "workspace_id": str(workspace_id),
            },
            db,
        )

    # 3. Reaction removal events
    for reaction_data in deleted_reaction_data:
        await ws.broadcast_workspace_event(
            "reaction_removed",
            workspace_id,
            {
                "message_id": reaction_data["message_id"],
                "reaction_id": reaction_data["reaction_id"],
                "workspace_id": str(workspace_id),
            },
            db,
        )

    # 4. Member left event
    await ws.broadcast_workspace_event(
        "user_left_workspace",
        workspace_id,
        {
            "workspace_id": str(workspace_id),
            "user_id": str(user.id),
        },
        db,
    )

    return {"message": "Successfully left workspace"}


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    access_token: str = Cookie(...),
    db: Session = Depends(get_db),
):
    try:
        # Get token from cookies
        if not access_token:
            await websocket.close(code=4001, reason="No authentication token provided")
            return

        # Verify token and get user
        try:
            auth_utils = AuthUtils()
            token_data = auth_utils.verify_token(access_token)
            user_id = token_data.user_id
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            await websocket.close(code=4002, reason="Invalid authentication token")
            return

        # Accept connection and add to connection manager
        await ws.connect(websocket, user_id)

        try:
            while True:
                # Wait for messages from the client
                data = await websocket.receive_text()
                try:
                    message = json.loads(data)
                    if not isinstance(message, dict) or "message_type" not in message:
                        logger.error(f"Invalid message format: {message}")
                        continue

                    message_type = message["message_type"]

                    if message_type == "user_online":
                        await ws.handle_user_online(user_id, db)
                    elif message_type == "user_is_typing":
                        if "conversation_id" not in message:
                            logger.error(
                                "Missing conversation_id in user_typing message"
                            )
                            continue
                        await ws.handle_user_typing(
                            user_id, UUID(message["conversation_id"]), db
                        )
                    elif message_type == "user_stopped_typing":
                        if "conversation_id" not in message:
                            logger.error(
                                "Missing conversation_id in user_stopped_typing message"
                            )
                            continue
                        await ws.handle_user_stopped_typing(
                            user_id, UUID(message["conversation_id"]), db
                        )

                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON message: {data}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                # Process message if needed
                # For now, we're only handling server->client communication
        except WebSocketDisconnect:
            logger.warning(f"WebSocket disconnected for user {user_id}")
            ws.disconnect(user_id)
            await ws.handle_user_offline(user_id, db)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.close(code=4000)


app.include_router(router)
