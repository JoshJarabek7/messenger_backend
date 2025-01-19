from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from jose.exceptions import JWTError
from loguru import logger
from openai import AsyncOpenAI
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlmodel import Session

from app.core.config import get_settings
from app.models.domain import User
from app.repositories.user_repository import UserRepository
from app.services.base_service import BaseService
from app.models.schemas.responses.token import Token


class TokenData(BaseModel):
    user_id: UUID
    exp: datetime


class UserService(BaseService):
    """Service for managing user domain operations"""

    def __init__(self, db: Session):
        self.user_repository = UserRepository(db)
        self.pwd_context = CryptContext(
            schemes=["argon2"],
            default="argon2",
            argon2__time_cost=3,
            argon2__memory_cost=65536,
            argon2__parallelism=4,
            deprecated="auto",
        )
        self.oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
        self.openai = AsyncOpenAI(api_key=get_settings().OPENAI_API_KEY)
        self.db = db

    # Authentication methods
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return self.pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        """Generate password hash"""
        return self.pwd_context.hash(password)

    def create_access_token(
        self, user_id: UUID, expires_delta: timedelta | None = None
    ) -> str:
        """Create JWT access token"""
        if expires_delta:
            expire = datetime.now(UTC) + expires_delta
        else:
            expire = datetime.now(UTC) + timedelta(
                minutes=get_settings().JWT_ACCESS_TOKEN_EXPIRE_MINUTES + 1000
            )

        to_encode = {"exp": expire, "sub": str(user_id), "type": "access"}
        encoded_jwt = jwt.encode(
            to_encode,
            get_settings().JWT_SECRET_KEY,
            algorithm=get_settings().JWT_ALGORITHM,
        )
        return encoded_jwt

    def create_refresh_token(self, user_id: UUID) -> str:
        """Create JWT refresh token"""
        expires_delta = timedelta(
            minutes=get_settings().JWT_REFRESH_TOKEN_EXPIRE_MINUTES
        )
        expire = datetime.now(UTC) + expires_delta
        to_encode = {"exp": expire, "sub": str(user_id), "type": "refresh"}
        encoded_jwt = jwt.encode(
            to_encode,
            get_settings().JWT_SECRET_KEY,
            algorithm=get_settings().JWT_ALGORITHM,
        )
        return encoded_jwt

    def authenticate_user(self, email: str, password: str) -> User:
        """Authenticate a user by email and password"""
        user = self.user_repository.get_by_email(email)
        if not user:
            raise HTTPException(status_code=401, detail="User not found.")

        logger.debug(f"User: {user}")

        if not self.verify_password(password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid password.")

        return user

    def verify_token(
        self, token: str, token_type: Literal["access", "refresh"]
    ) -> TokenData:
        if not token:
            raise HTTPException(
                status_code=401, detail=f"No {token_type} token provided"
            )

        try:
            payload = jwt.decode(
                token,
                get_settings().JWT_SECRET_KEY,
                algorithms=[get_settings().JWT_ALGORITHM],
            )

            user_id = payload.get("sub")
            exp = payload.get("exp")
            token_type_received = payload.get("type")

            if user_id is None or exp is None:
                raise HTTPException(
                    status_code=401, detail=f"Invalid {token_type} token format"
                )

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

    def create_tokens(self, user_id: UUID) -> Token:
        return Token(
            access_token=self.create_access_token(user_id),
            refresh_token=self.create_refresh_token(user_id),
            token_type="bearer",
        )

    def refresh_tokens(self, refresh_token: str) -> Token:
        token_data = self.verify_token(refresh_token, "refresh")
        return self.create_tokens(token_data.user_id)

    # User management
    def create_user(
        self,
        email: str,
        password: str,
        username: str,
        full_name: str | None = None,
        display_name: str | None = None,
    ) -> User:
        """Create a new user"""
        # Check if email or username already exists
        if self.user_repository.get_by_email(email):
            raise HTTPException(status_code=400, detail="Email already registered")
        if self.user_repository.get_by_username(username):
            raise HTTPException(status_code=400, detail="Username already taken")

        # Create user
        user_data = {
            "email": email,
            "username": username,
            "full_name": full_name,
            "display_name": display_name,
            "hashed_password": self.get_password_hash(password),
        }
        user = self.user_repository.create(User(**user_data))

        return user

    def get_user(self, user_id: UUID) -> User:
        """Get a user by ID"""
        user = self.user_repository.get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user

    def update_user(
        self,
        user_id: UUID,
        email: str | None = None,
        username: str | None = None,
        full_name: str | None = None,
        display_name: str | None = None,
    ) -> User:
        """Update user details"""
        user = self.get_user(user_id)

        # Check uniqueness if email/username is being updated
        if email and email != user.email:
            if self.user_repository.get_by_email(email):
                raise HTTPException(status_code=400, detail="Email already registered")
            user.email = email

        if username and username != user.username:
            if self.user_repository.get_by_username(username):
                raise HTTPException(status_code=400, detail="Username already taken")
            user.username = username

        if full_name is not None:
            user.full_name = full_name
        if display_name is not None:
            user.display_name = display_name

        return self.user_repository.update(user)

    def delete_user(self, user_id: UUID) -> None:
        """Delete a user and their data"""
        self.user_repository.delete(user_id)

    def get_current_user(self, access_token: str) -> User:
        """Get the current user"""
        token_data = self.verify_token(access_token, "access")
        return self.get_user(token_data.user_id)

    def get_user_by_id(self, user_id: UUID) -> User:
        """Get a user by ID"""
        user = self.user_repository.get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user

    def get_user_by_email(self, email: str) -> User:
        """Get a user by email"""
        user = self.user_repository.get_by_email(email)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user

    def get_user_by_username(self, username: str) -> User:
        """Get a user by username"""
        user = self.user_repository.get_by_username(username)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
