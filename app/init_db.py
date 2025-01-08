from sqlmodel import SQLModel, create_engine
from app.models import *  # This will import all models
from app.utils.db import DATABASE_URL

def init_db():
    """Initialize the database and create all tables."""
    print("Creating database engine...")
    engine = create_engine(DATABASE_URL, echo=True)
    
    print("Creating all tables...")
    SQLModel.metadata.create_all(engine)
    print("Database initialization completed!")

if __name__ == "__main__":
    init_db() 