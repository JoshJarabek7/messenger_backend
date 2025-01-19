from datetime import datetime
from uuid import UUID
from pydantic import EmailStr

from app.core.schema import BaseResponse


class UserResponse(BaseResponse):
    id: UUID
    email: EmailStr
    username: str
    display_name: str
    is_online: bool
    s3_key: str | None
    created_at: datetime
    updated_at: datetime
