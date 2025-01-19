from __future__ import annotations

from typing import Dict
from uuid import UUID
from fastapi import WebSocket
from app.core.meta import SingletonMeta


class WebSocketManager(metaclass=SingletonMeta):
    """Manages WebSocket connections for real-time communication.

    This class is responsible for maintaining active WebSocket connections
    and provides methods for basic connection management. It uses the Singleton
    pattern to ensure only one instance exists across the application.
    """

    def __init__(self):
        """Initialize the WebSocket manager with an empty connections dict."""
        self._connections: Dict[UUID, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: UUID) -> None:
        """Connect a new WebSocket for a user.

        Args:
            websocket: The WebSocket connection to manage
            user_id: The ID of the user who owns this connection
        """
        await websocket.accept()
        self._connections[user_id] = websocket

    async def disconnect(self, user_id: UUID) -> None:
        """Disconnect and remove a user's WebSocket connection.

        Args:
            user_id: The ID of the user whose connection to remove
        """
        if websocket := self._connections.get(user_id):
            try:
                await websocket.close()
            except Exception:
                pass  # Ignore errors during close
            self._connections.pop(user_id, None)

    async def get_user_socket(self, user_id: UUID) -> WebSocket | None:
        """Get a user's WebSocket connection if it exists.

        Args:
            user_id: The ID of the user whose connection to retrieve

        Returns:
            The user's WebSocket connection if found, None otherwise
        """
        return self._connections.get(user_id)

    async def send_json(self, user_id: UUID, message: dict) -> None:
        """Send a JSON message to a specific user.

        Args:
            user_id: The ID of the user to send the message to
            message: The message to send as a JSON-serializable dict
        """
        if websocket := self._connections.get(user_id):
            try:
                await websocket.send_json(message)
            except Exception:
                await self.disconnect(user_id)

    async def broadcast(self, message: dict, exclude: set[UUID] | None = None) -> None:
        """Broadcast a message to all connected users except excluded ones.

        Args:
            message: The message to broadcast as a JSON-serializable dict
            exclude: Optional set of user IDs to exclude from the broadcast
        """
        exclude = exclude or set()
        for user_id, websocket in self._connections.items():
            if user_id not in exclude:
                try:
                    await websocket.send_json(message)
                except Exception:
                    await self.disconnect(user_id)

    def is_user_online(self, user_id: UUID) -> bool:
        """Check if a user has an active connection.

        Args:
            user_id: The ID of the user to check

        Returns:
            True if the user has an active connection, False otherwise
        """
        return user_id in self._connections

    def get_online_users(self) -> set[UUID]:
        """Get the set of currently connected user IDs.

        Returns:
            A set of UUIDs representing the connected users
        """
        return set(self._connections.keys())
