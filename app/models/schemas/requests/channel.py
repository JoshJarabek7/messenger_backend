from uuid import UUID

from pydantic import BaseModel


class CreateChannelRequest(BaseModel):
    name: str
    description: str | None = None


class UpdateChannelRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class CreateChannelMessageRequest(BaseModel):
    content: str
    parent_id: UUID | None = None
