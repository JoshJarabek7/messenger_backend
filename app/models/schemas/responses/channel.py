from datetime import datetime
from uuid import UUID

from app.core.schema import BaseResponse


class ChannelResponse(BaseResponse):
    id: UUID
    name: str
    description: str | None = None
    workspace_id: UUID
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime
