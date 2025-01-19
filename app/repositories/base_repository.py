from typing import Generic, TypeVar
from uuid import UUID

from sqlmodel import Session, SQLModel, select

ModelType = TypeVar("ModelType", bound=SQLModel)


class BaseRepository(Generic[ModelType]):
    """Base repository with common CRUD operations"""

    def __init__(self, model_class: type[ModelType], db: Session):
        """Initialize repository with model class and database session"""
        self.model = model_class
        self.db = db

    def create(self, obj: ModelType) -> ModelType:
        """Create a new record."""
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def get(self, id: UUID) -> ModelType | None:
        """Get a single record by ID."""
        return self.db.get(self.model, id)

    def list(self, *, skip: int = 0, limit: int = 100) -> list[ModelType]:
        """Get a list of records with pagination."""
        stmt = select(self.model).offset(skip).limit(limit)
        result = self.db.execute(stmt)
        return list(result.scalars().all())

    def update(self, obj: ModelType) -> ModelType:
        """Update a record."""
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete(self, id: UUID) -> None:
        """Delete a record by ID."""
        obj = self.db.get(self.model, id)
        if obj:
            self.db.delete(obj)
            self.db.commit()
