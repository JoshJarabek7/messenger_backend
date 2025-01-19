from datetime import datetime
from uuid import UUID

from app.core.schema import BaseResponse


class ReactionResponse(BaseResponse):
    """Response model for reactions."""

    id: UUID
    emoji: str
    user_id: UUID
    message_id: UUID
    created_at: datetime
    updated_at: datetime
