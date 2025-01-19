from datetime import datetime
from uuid import UUID

from app.core.schema import BaseResponse
from app.models.schemas.responses.reaction import ReactionResponse


class MessageResponse(BaseResponse):
    id: UUID
    content: str | None = None
    user_id: UUID | None = None
    channel_id: UUID | None = None
    dm_conversation_id: UUID | None = None
    ai_conversation_id: UUID | None = None
    parent_id: UUID | None = None
    is_ai_generated: bool = False
    created_at: datetime
    updated_at: datetime
    reactions: list[ReactionResponse] = []
    thread_count: int = 0
