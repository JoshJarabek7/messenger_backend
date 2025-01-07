from sqlmodel import Session, SQLModel
from app.db import get_db

def cleanup_database():
    """Delete all data from all tables."""
    engine = get_db()
    
    with Session(engine) as session:
        # Use CASCADE to handle foreign key constraints
        session.execute("""
            DROP TABLE IF EXISTS reaction CASCADE;
            DROP TABLE IF EXISTS file_attachment CASCADE;
            DROP TABLE IF EXISTS message CASCADE;
            DROP TABLE IF EXISTS channel_member CASCADE;
            DROP TABLE IF EXISTS workspace_member CASCADE;
            DROP TABLE IF EXISTS user_session CASCADE;
            DROP TABLE IF EXISTS channel CASCADE;
            DROP TABLE IF EXISTS workspace CASCADE;
            DROP TABLE IF EXISTS user CASCADE;
        """)
        session.commit()
        
        # Recreate tables
        SQLModel.metadata.create_all(engine)
        print("Database cleanup complete!")

if __name__ == "__main__":
    cleanup_database() 