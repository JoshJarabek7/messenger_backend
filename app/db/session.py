from typing import Generator
import logging
from sqlmodel import Session, SQLModel, create_engine, text
from app.core.config import get_settings
from app.models.domain import *

settings = get_settings()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create SQLAlchemy engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # Enable connection health checks
    pool_size=settings.DB_POOL_SIZE,  # Number of connections to maintain
    max_overflow=settings.DB_MAX_OVERFLOW,  # Max extra connections when pool is full
    echo=settings.DB_ECHO_LOG,  # SQL query logging
)


def get_db() -> Generator[Session, None, None]:
    """Get a database session"""
    with Session(engine) as session:
        yield session


def create_db_and_tables() -> None:
    """Create database tables and extensions if they don't exist."""
    try:
        # Create vector extension for PostgreSQL
        if "postgresql" in settings.DATABASE_URL:
            with engine.begin() as conn:
                logger.info("Creating vector extension if it doesn't exist...")
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        # Get list of existing tables
        with engine.connect() as conn:
            existing_tables = engine.dialect.get_table_names(conn)
            logger.info(f"Existing tables: {existing_tables}")

        # Create all tables after ensuring extension exists
        logger.info("Creating database tables...")
        SQLModel.metadata.create_all(engine)

        # Verify tables were created
        with engine.connect() as conn:
            tables_after = engine.dialect.get_table_names(conn)
            logger.info(f"Tables after creation: {tables_after}")

        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating database tables: {str(e)}")
        raise


if __name__ == "__main__":
    create_db_and_tables()
