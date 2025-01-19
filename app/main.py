from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    ai,
    auth,
    channels,
    conversations,
    dashboard,
    files,
    messages,
    users,
    websocket,
    workspaces,
)
from app.core.config import get_settings
from app.db.session import create_db_and_tables
from loguru import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI app."""
    try:
        logger.info("Starting up database...")
        create_db_and_tables()
        logger.info("Database startup completed")
        yield
    except Exception as e:
        logger.error(f"Error during startup: {str(e)}")
        raise
    finally:
        logger.info("Shutting down...")


app = FastAPI(
    title="Slack Clone API",
    description="A modern chat application API with AI capabilities",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(workspaces.router)
app.include_router(channels.router)
app.include_router(conversations.router)
app.include_router(messages.router)
app.include_router(files.router)
app.include_router(ai.router)
app.include_router(websocket.router)
app.include_router(dashboard.router)


@app.get("/health")
async def root() -> dict[str, str]:
    """Root endpoint"""
    return {
        "message": "Welcome to the Slack Clone API. Please refer to /docs for API documentation."
    }
