from functools import lru_cache
from os import getenv
from typing import Generator

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

DB_USER = getenv("DB_USER")
DB_PASSWORD = getenv("DB_PASSWORD")
DB_HOST = getenv("DB_HOST")
DB_PORT = getenv("DB_PORT")
DB_NAME = getenv("DB_NAME")


DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
print(DATABASE_URL)
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


@lru_cache
def get_db() -> Engine:
    return engine
