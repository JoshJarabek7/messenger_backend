from datetime import datetime, timedelta, UTC
from fastapi import HTTPException, Cookie, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from uuid import UUID
from app.models import User
from app.websocket import UserManager
from os import getenv
# JWT Configuration
SECRET_KEY = getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    print("FALLING BACK")
    # Fallback to a default key for development
    SECRET_KEY = "your-super-secret-key-for-jwt-that-should-be-very-long-and-secure"
    print("WARNING: Using default JWT_SECRET_KEY. In production, set this via environment variable.")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str

class TokenData(BaseModel):
    user_id: UUID
    exp: datetime

class AuthUtils:
    def __init__(self):
        self.user_manager = UserManager()

    def create_access_token(self, user_id: UUID) -> str:
        """Create a new access token."""
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        expire = datetime.now(UTC) + expires_delta
        
        to_encode = {
            "sub": str(user_id),
            "exp": expire,
            "type": "access"
        }
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    def create_refresh_token(self, user_id: UUID) -> str:
        """Create a new refresh token."""
        expires_delta = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        expire = datetime.now(UTC) + expires_delta
        
        to_encode = {
            "sub": str(user_id),
            "exp": expire,
            "type": "refresh"
        }
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    def create_tokens(self, user_id: UUID) -> Token:
        """Create both access and refresh tokens."""
        return Token(
            access_token=self.create_access_token(user_id),
            refresh_token=self.create_refresh_token(user_id),
            token_type="bearer"
        )

    def verify_token(self, token: str, token_type: str = "access") -> TokenData:
        """Verify a token and return its data."""
        if not token:
            raise HTTPException(
                status_code=401,
                detail="No token provided"
            )

        try:
            print(f"Verifying {token_type} token:", token)
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            print("Token payload:", payload)
            user_id = payload.get("sub")
            exp = payload.get("exp")
            token_type_received = payload.get("type")
            
            print(f"Token details - user_id: {user_id}, exp: {exp}, type: {token_type_received}")
            
            if user_id is None or exp is None:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid token format"
                )
            
            if token_type_received != token_type:
                raise HTTPException(
                    status_code=401,
                    detail=f"Invalid token type. Expected {token_type}"
                )
            
            return TokenData(
                user_id=UUID(user_id),
                exp=datetime.fromtimestamp(exp, UTC)
            )
        except JWTError as e:
            print(f"JWT Error during {token_type} token verification:", str(e))
            raise HTTPException(
                status_code=401,
                detail="Could not validate token"
            )

    def refresh_tokens(self, refresh_token: str) -> Token:
        """Create new access and refresh tokens using a refresh token."""
        token_data = self.verify_token(refresh_token, "refresh")
        return self.create_tokens(token_data.user_id)

    async def get_current_user(self, access_token: str = Cookie(None)) -> User:
        """Get the current user from a token stored in cookies."""
        token_data = self.verify_token(access_token)
        print(token_data)
        user = self.user_manager.get_user_by_id(token_data.user_id)
        if user is None:
            raise HTTPException(
                status_code=401,
                detail="User not found"
            )
        
        return user

# Create a global instance
auth_utils = AuthUtils()

# Dependency for protected routes
async def get_current_user(request: Request) -> User:
    """Get the current user from the access token in cookies."""
    access_token = request.cookies.get("access_token")
    print("Access token from cookies:", access_token)
    
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="No access token provided"
        )
    
    try:
        token_data = auth_utils.verify_token(access_token, "access")
        print("Token data after verification:", token_data)
        
        user = auth_utils.user_manager.get_user_by_id(token_data.user_id)
        if user is None:
            raise HTTPException(
                status_code=401,
                detail="User not found"
            )
        
        return user
    except Exception as e:
        print("Error in get_current_user:", str(e))
        raise 