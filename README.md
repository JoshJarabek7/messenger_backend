# Slack Clone Backend

A modern real-time chat backend built with FastAPI and WebSockets, providing the API for the Slack clone frontend.

Frontend repository: [messenger_frontend](https://github.com/JoshJarabek7/messenger_frontend)

## Features

- Real-time WebSocket communication
- RESTful API endpoints for chat functionality
- User authentication and session management
- Direct messaging support
- User and workspace search capabilities
- PostgreSQL database integration
- Async request handling
- WebSocket broadcast system

## Prerequisites

- Python 3.12+
- PostgreSQL 15+
- Docker and Docker Compose (for development)

## Getting Started

### Using Docker (Recommended)

1. Copy the environment template:
```bash
cp .env.DEV.example .env.DEV
```

2. Start the services:
```bash
docker compose -f docker-compose.dev.yml up --build
```

The API will be available at http://localhost:8000

### Manual Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables:
Create a `.env` file in the root directory with:
```env
DB_USER=
DB_PASSWORD=
DB_HOST=
DB_PORT=
DB_NAME=
JWT_SECRET_KEY=
CORS_ORIGINS=
```

3. Start the development server:
```bash
./start.sh
# or
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Project Structure

- `/app/` - Main application package
  - `/routes/` - API route handlers
  - `/models/` - SQLAlchemy models
  - `/schemas/` - Pydantic schemas for request/response validation
  - `/dependencies/` - FastAPI dependencies and utilities
  - `/websocket_utils.py` - WebSocket handling utilities

## API Documentation

Once the server is running, view the interactive API documentation at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Development Notes

- Uses FastAPI for high-performance async API
- WebSocket connections for real-time messaging
- PostgreSQL for persistent storage
- JWT-based authentication
- SQLModel for database ORM

## Dependencies

Main dependencies used in this project:
- FastAPI - Web framework
- Uvicorn - ASGI server
- SQLModel/SQLAlchemy - Database ORM
- Passlib - Password hashing
- Python-Jose - JWT handling
- Psycopg2 - PostgreSQL adapter
- Python-dotenv - Environment management

## License

MIT
