from uuid import UUID

from pydantic import BaseModel


class CreateReactionRequest(BaseModel):
    reaction_type: str


class DeleteReactionRequest(BaseModel):
    reaction_id: UUID
