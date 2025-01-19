from pydantic import BaseModel

from uuid import UUID
from datetime import datetime


class WorkspaceResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    slug: str
    s3_key: str | None = None
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat()}
