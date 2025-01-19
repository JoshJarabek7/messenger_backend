import asyncio
import os
from typing import AsyncGenerator, Generator, Any

from fastapi.websockets import WebSocketState
import pytest
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from starlette.types import Receive, Scope, Send
from loguru import logger
from sqlalchemy import create_engine, text
from sqlmodel import Session, SQLModel

from httpx import ASGITransport, AsyncClient
import pytest_boto_mock

# Import all models to ensure they are registered with SQLModel
from app.models.domain import *
from app.models.domain import User, Workspace, Channel

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.services.user_service import UserService
from app.services.workspace_service import WorkspaceService

# Test user constants
TEST_USER_EMAIL = "test@example.com"
TEST_USER_USERNAME = "testuser"
TEST_USER_PASSWORD = "testpassword123"
TEST_USER_DISPLAY_NAME = "Test User"

# Load environment variables
load_dotenv("../.env.TEST")

# Test database URL (using PostgreSQL for pgvector support)
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/test_db"
)

# Test S3 settings
TEST_BUCKET_NAME = "test-bucket"
TEST_AWS_REGION = "us-east-1"
TEST_AWS_ACCESS_KEY = "testing"
TEST_AWS_SECRET_KEY = "testing"

# Override settings for testing
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["JWT_SECRET_KEY"] = "test_secret_key"
os.environ["OPENAI_API_KEY"] = "test_api_key"
os.environ["AWS_ACCESS_KEY_ID"] = TEST_AWS_ACCESS_KEY
os.environ["AWS_SECRET_ACCESS_KEY"] = TEST_AWS_SECRET_KEY
os.environ["AWS_REGION_NAME"] = TEST_AWS_REGION
os.environ["AWS_S3_BUCKET_NAME"] = TEST_BUCKET_NAME

logger.info(f"TEST_DATABASE_URL: {TEST_DATABASE_URL}")
logger.info(f"JWT_SECRET_KEY: {os.environ['JWT_SECRET_KEY']}")
logger.info(f"OPENAI_API_KEY: {os.environ['OPENAI_API_KEY']}")
logger.info(f"AWS_S3_BUCKET_NAME: {os.environ['AWS_S3_BUCKET_NAME']}")

# Create engine for tests
engine = create_engine(
    TEST_DATABASE_URL,
    echo=False,
    future=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Set up the test database with required extensions."""
    # Create vector extension at session scope
    with engine.begin() as conn:
        conn.execute(text("DROP EXTENSION IF EXISTS vector CASCADE"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an instance of the default event loop for each test case."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
def db() -> Generator[Session, None, None]:
    """Create a fresh database for each test."""
    with engine.begin() as conn:
        # Drop all tables
        SQLModel.metadata.drop_all(conn)
        # Create all tables
        SQLModel.metadata.create_all(conn)

    with Session(engine) as session:
        yield session


@pytest.fixture(scope="function")
def test_app(db: Session) -> FastAPI:
    """Create a fresh FastAPI app for testing"""
    from app.main import app

    def override_get_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return app


@pytest.fixture
async def make_client(test_app: FastAPI):
    """
    Factory fixture to create AsyncClient instances with optional custom headers.
    Uses ASGI transport to avoid real HTTP connections.
    """

    async def _make_client(headers: dict[str, Any] | None = None) -> AsyncClient:
        client = AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        )
        if headers:
            client.headers.update(headers)
        return client

    return _make_client


@pytest.fixture(scope="function")
async def client(
    test_app: FastAPI, test_user_in_db: User
) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_current_user() -> User:
        return test_user_in_db

    test_app.dependency_overrides[get_current_user] = override_get_current_user
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture(scope="function")
def test_settings():
    """Return test settings."""
    return get_settings()


@pytest.fixture(scope="function")
def mock_openai(mocker):
    """Mock OpenAI client."""
    mock = mocker.patch("openai.OpenAI")
    mock_instance = mocker.MagicMock()

    # Mock chat completions
    mock_instance.chat.completions.create = mocker.MagicMock()

    # Mock embeddings with proper structure
    mock_embedding_response = mocker.MagicMock()
    mock_embedding_response.data = [mocker.MagicMock(embedding=[0.1] * 1536)]
    mock_instance.embeddings.create.return_value = mock_embedding_response

    mock.return_value = mock_instance
    return mock_instance


@pytest.fixture(scope="function")
def mock_openai_stream():
    """Mock OpenAI streaming response."""

    class StreamIterator:
        def __init__(self):
            self.chunks = [
                type(
                    "Choice",
                    (),
                    {
                        "choices": [
                            type(
                                "Delta",
                                (),
                                {"delta": type("Content", (), {"content": "Test "})},
                            )
                        ]
                    },
                ),
                type(
                    "Choice",
                    (),
                    {
                        "choices": [
                            type(
                                "Delta",
                                (),
                                {"delta": type("Content", (), {"content": "response"})},
                            )
                        ]
                    },
                ),
                type(
                    "Choice",
                    (),
                    {
                        "choices": [
                            type(
                                "Delta",
                                (),
                                {
                                    "delta": type("Content", (), {"content": None}),
                                    "finish_reason": "stop",
                                },
                            )
                        ]
                    },
                ),
            ]
            self.index = 0

        def __iter__(self):
            return self

        def __next__(self):
            if self.index >= len(self.chunks):
                raise StopIteration
            chunk = self.chunks[self.index]
            self.index += 1
            return chunk

    return StreamIterator()


@pytest.fixture(scope="function", autouse=True)
def clean_db(db: Session) -> Generator[None, Any, None]:
    yield None
    db.rollback()  # Roll back any pending transactions
    for table in reversed(SQLModel.metadata.sorted_tables):
        db.execute(text(f"TRUNCATE TABLE {table.name} CASCADE"))
    db.commit()


@pytest.fixture
def test_user_in_db(db: Session) -> User:
    """Create a test user in the database."""
    user_service = UserService(db)
    try:
        return user_service.create_user(
            email=TEST_USER_EMAIL,
            username=TEST_USER_USERNAME,
            password=TEST_USER_PASSWORD,
            display_name=TEST_USER_DISPLAY_NAME,
        )
    except HTTPException as e:
        if "Email already registered" in str(e.detail):
            return user_service.get_user_by_email(TEST_USER_EMAIL)
        raise


@pytest.fixture
def test_other_user_in_db(db: Session, user_service: UserService) -> User:
    """Create another test user in the database."""
    user_data = {
        "email": "other@test.com",
        "username": "other_test_user",
        "display_name": "Other Test User",
        "password": TEST_USER_PASSWORD,
    }
    return user_service.create_user(**user_data)


@pytest.fixture
def user_service(db: Session) -> UserService:
    """Create a UserService instance."""
    return UserService(db)


@pytest.fixture
def test_channel_in_db(
    db: Session,
    test_user_in_db: User,
    test_workspace_in_db: Workspace,
) -> Channel:
    """Create a test channel in the database."""
    workspace_service = WorkspaceService(db)
    channel = workspace_service.create_channel(
        workspace_id=test_workspace_in_db.id,
        name="test-channel",
        description="Test Channel",
        created_by_id=test_user_in_db.id,
    )
    return channel


@pytest.fixture
def test_workspace_in_db(
    db: Session,
    test_user_in_db: User,
) -> Workspace:
    """Create a test workspace in the database."""
    workspace_service = WorkspaceService(db)
    workspace = workspace_service.create_workspace(
        name="Test Workspace",
        created_by_id=test_user_in_db.id,
        description="Test Workspace Description",
    )
    return workspace


@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    """Override settings for testing"""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", TEST_AWS_ACCESS_KEY)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", TEST_AWS_SECRET_KEY)
    monkeypatch.setenv("AWS_REGION_NAME", TEST_AWS_REGION)
    monkeypatch.setenv("AWS_S3_BUCKET_NAME", TEST_BUCKET_NAME)

    # Force reload settings
    settings = get_settings()
    settings.AWS_ACCESS_KEY_ID = TEST_AWS_ACCESS_KEY
    settings.AWS_SECRET_ACCESS_KEY = TEST_AWS_SECRET_KEY
    settings.AWS_REGION_NAME = TEST_AWS_REGION
    settings.AWS_S3_BUCKET_NAME = TEST_BUCKET_NAME

    return settings


class MockWebSocket(WebSocket):
    """Mock WebSocket for testing."""

    def __init__(self):
        # Initialize with dummy scope, receive, send functions
        scope: Scope = {
            "type": "websocket",
            "path": "/ws",
            "headers": [],
        }

        def receive():
            return {"type": "websocket.connect"}

        def send(message):
            return None

        super().__init__(scope=scope, receive=receive, send=send)

        self.sent_messages: list[dict[str, Any]] = []
        self._client_state = WebSocketState.DISCONNECTED
        self.application_state = WebSocketState.DISCONNECTED
        self._message_counter = 0
        self._should_disconnect = False
        self._cookies: dict[str, str] = {}
        self._connected = False
        self._message_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def __aenter__(self) -> "MockWebSocket":
        """Enter the async context manager."""
        await self.accept()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the async context manager."""
        await self.close()

    @property
    def cookies(self) -> dict[str, str]:
        return self._cookies

    @cookies.setter
    def cookies(self, value: dict[str, str]) -> None:
        self._cookies = value

    async def accept(self, subprotocol: str | None = None) -> None:
        self._client_state = WebSocketState.CONNECTED
        self.application_state = WebSocketState.CONNECTED
        self._connected = True

    async def receive(self) -> dict[str, Any]:
        if self._should_disconnect:
            return {"type": "websocket.disconnect", "code": 1000}

        if not self._connected:
            self._connected = True
            return {"type": "websocket.connect"}

        # Wait for a message in the queue
        try:
            message = await asyncio.wait_for(self._message_queue.get(), timeout=0.1)
            return {"type": "websocket.receive", "text": message}
        except asyncio.TimeoutError:
            # If no message is available, send a ping
            return {"type": "websocket.receive", "text": '{"type": "ping", "data": {}}'}

    async def receive_json(self) -> Any:
        if self._should_disconnect:
            raise WebSocketDisconnect(code=1000)

        # Wait for a message in the queue
        try:
            message = await asyncio.wait_for(self._message_queue.get(), timeout=0.1)
            return message
        except asyncio.TimeoutError:
            # If no message is available, send a ping
            return {"type": "ping", "data": {}}

    async def send_json(self, data: Any) -> None:
        self.sent_messages.append(data)

    async def close(self, code: int = 1000) -> None:
        self._client_state = WebSocketState.DISCONNECTED
        self.application_state = WebSocketState.DISCONNECTED
        self._should_disconnect = True
        self._connected = False

    @property
    def client_state(self) -> WebSocketState:
        return self._client_state

    @client_state.setter
    def client_state(self, value: WebSocketState) -> None:
        self._client_state = value

    @property
    def application_state(self) -> WebSocketState:
        return self._application_state

    @application_state.setter
    def application_state(self, value: WebSocketState) -> None:
        self._application_state = value
