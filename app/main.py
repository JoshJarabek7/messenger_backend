from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.routes import auth, websocket, workspaces, messages, search, channels, users, files, conversations
from app.utils.db import create_db_and_tables
from app.utils.errors import APIError
import logging
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Slack Clone API",
    description="A modern chat application API inspired by Slack",
    version="1.0.0"
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
origins = [
    "http://localhost:5173",  # Dev frontend
    "http://localhost:4173",  # Preview frontend
    *os.getenv("CORS_ORIGINS", "").split(",")  # Additional origins from env
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler
@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": app.version
    }

# Include routers
app.include_router(auth)
app.include_router(websocket)
app.include_router(workspaces)
app.include_router(messages)
app.include_router(search)
app.include_router(channels)
app.include_router(users)
app.include_router(files)
app.include_router(conversations)

@app.get("/")
async def root():
    return {
        "app": "Slack Clone API",
        "version": app.version,
        "docs_url": "/docs",
        "redoc_url": "/redoc"
    }
