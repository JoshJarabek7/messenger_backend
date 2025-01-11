import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routes import (
    auth,
    channels,
    conversations,
    files,
    messages,
    search,
    users,
    websocket,
    workspaces,
)
from app.utils.db import create_db_and_tables
from app.utils.errors import APIError

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Slack Clone API",
    description="A modern chat application API inspired by Slack",
    version="1.0.0",
)


# Create database tables at startup
@app.on_event("startup")
async def startup_event():
    try:
        create_db_and_tables()
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        raise


# CORS middleware configuration
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,  # Cache preflight requests for 1 hour
)


# Global exception handler
@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": app.version}


# Include routers
app.include_router(auth.router)
app.include_router(websocket.router)
app.include_router(workspaces.router)
app.include_router(messages.router)
app.include_router(search.router)
app.include_router(channels.router)
app.include_router(users.router)
app.include_router(files.router)
app.include_router(conversations.router)


@app.get("/")
async def root():
    return {
        "app": "Slack Clone API",
        "version": app.version,
        "docs_url": "/docs",
        "redoc_url": "/redoc",
    }
