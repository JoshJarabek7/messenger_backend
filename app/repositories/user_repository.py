from sqlmodel import Session, select

from app.models.domain import User
from app.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for User domain operations"""

    def __init__(self, db: Session):
        super().__init__(User, db)

    def get_by_email(self, email: str) -> User | None:
        """Get a user by their email"""
        statement = select(User).where(User.email == email)
        result = self.db.exec(statement)
        return result.one_or_none()

    def get_by_username(self, username: str) -> User | None:
        """Get a user by their username"""
        statement = select(User).where(User.username == username)
        result = self.db.exec(statement)
        return result.one_or_none()
