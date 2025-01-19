from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class BaseResponse(BaseModel):
    """Base response model with configuration for SQLModel serialization"""

    model_config = ConfigDict(
        from_attributes=True,  # Allows conversion from SQLModel/SQLAlchemy ORM models
        arbitrary_types_allowed=True,  # Allows for more complex types
        json_encoders={
            datetime: lambda dt: dt.isoformat(),  # Custom JSON encoder for datetime
            UUID: lambda u: str(u),  # Custom JSON encoder for UUIDs
        },
    )
