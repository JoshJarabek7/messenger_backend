from datetime import datetime
from uuid import UUID

from app.core.schema import BaseResponse

from app.models.schemas.responses.message import MessageResponse
from app.models.schemas.responses.user import UserResponse


class DirectMessageConversationResponse(BaseResponse):
    """Response model for direct message conversations."""

    id: UUID
    user1_id: UUID
    user2_id: UUID
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse] | None = None
    user1: UserResponse | None = None
    user2: UserResponse | None = None
