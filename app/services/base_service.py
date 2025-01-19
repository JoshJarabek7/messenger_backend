from typing import Generic, TypeVar

from sqlmodel import SQLModel, Session

ModelType = TypeVar("ModelType", bound=SQLModel)


class BaseService(Generic[ModelType]):
    """Base service with common operations"""

    def __init__(self, db: Session):
        self.db = db
