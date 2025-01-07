from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import auth, websocket, workspaces, messages, search

app = FastAPI()

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

@app.get("/")
async def root():
    return {"message": "Welcome to the Slack Clone API"}
