from uuid import UUID
from datetime import datetime
from pydantic import BaseModel

from app.core.schema import BaseResponse


class MessageResponse(BaseResponse):
    id: UUID
    content: str
    created_at: datetime
    updated_at: datetime
    user_id: UUID | None = None
    parent_id: UUID | None = None
    ai_conversation_id: UUID | None = None
    channel_id: UUID | None = None
    dm_conversation_id: UUID | None = None

    class Config:
        from_attributes = True


class AIConversationResponse(BaseResponse):
    id: UUID
    created_at: datetime
    updated_at: datetime
    user_id: UUID
    messages: list[MessageResponse] = []

    class Config:
        from_attributes = True
