from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import auth, websocket, workspaces, messages, search, channels, users, direct_messages
from app.db import create_db_and_tables

app = FastAPI()

# Create database tables at startup
create_db_and_tables()

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth)
app.include_router(websocket)
app.include_router(workspaces)
app.include_router(messages)
app.include_router(search)
app.include_router(channels)
app.include_router(users)
app.include_router(direct_messages)

@app.get("/")
async def root():
    return {"message": "Welcome to the Slack Clone API"}
