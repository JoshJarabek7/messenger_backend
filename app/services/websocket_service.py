from typing import Generic, TypeVar
from fastapi import Depends
from app.core.websocket import WebSocketManager
from app.db.session import get_db
from sqlmodel import Session
from abc import ABC, abstractmethod
from app.models.schemas.events import (
    AIMessageEvent,
    BaseEvent,
    EventType,
    ChatMessageCreatedEvent,
    ChatMessageDeletedEvent,
    ReactionAddedEvent,
    ReactionRemovedEvent,
    TypingEvent,
    UserUpdatedEvent,
    UserDeletedEvent,
    UserOnlineEvent,
    UserOfflineEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    WorkspaceCreatedEvent,
    WorkspaceUpdatedEvent,
    WorkspaceDeletedEvent,
    WorkspaceMemberAddedEvent,
    WorkspaceMemberRemovedEvent,
    WorkspaceMemberRoleUpdatedEvent,
    ErrorEvent,
)

from fastapi import WebSocket

from app.services.membership_service import (
    get_members_for_conversations,
    get_members_for_message,
    get_relevant_members_for_user,
)

import asyncio
from app.repositories.workspace_repository import WorkspaceRepository


# Generic type variable bound to BaseEvent
T = TypeVar("T", bound=BaseEvent)


class EventHandler(Generic[T], ABC):
    """Base class for event handlers with type safety"""

    def __init__(self, event: T, db: Session, manager: WebSocketManager):
        self.event = event
        self.db = db
        self.manager = manager

    @abstractmethod
    async def get_sockets(self) -> list[WebSocket]:
        """Get the WebSocket connections that should receive this event"""
        raise NotImplementedError

    @abstractmethod
    async def handle_event(self) -> None:
        """Handle the event"""
        raise NotImplementedError


class MessageCreatedEventHandler(EventHandler[ChatMessageCreatedEvent]):
    """Handler for message created events"""

    def __init__(
        self, event: ChatMessageCreatedEvent, db: Session, manager: WebSocketManager
    ):
        super().__init__(event, db, manager)

    async def get_sockets(self) -> list[WebSocket]:
        """Get the sockets for the event"""
        user_ids = get_members_for_conversations(
            self.db,
            ai_conversation_id=self.event.data.ai_conversation_id,
            channel_id=self.event.data.channel_id,
            dm_conversation_id=self.event.data.dm_conversation_id,
        )
        socket_tasks = [self.manager.get_user_socket(user_id) for user_id in user_ids]
        return [
            socket
            for socket in await asyncio.gather(*socket_tasks)
            if socket is not None
        ]

    async def handle_event(self) -> None:
        """Handle a message created event"""
        sockets = await self.get_sockets()
        await asyncio.gather(
            *[socket.send_json(self.event.model_dump_json()) for socket in sockets]
        )


class MessageDeletedEventHandler(EventHandler[ChatMessageDeletedEvent]):
    """Handler for message deleted events"""

    def __init__(
        self, event: ChatMessageDeletedEvent, db: Session, manager: WebSocketManager
    ):
        super().__init__(event, db, manager)

    async def get_sockets(self) -> list[WebSocket]:
        user_ids = get_members_for_conversations(
            self.db,
            ai_conversation_id=self.event.data.ai_conversation_id,
            channel_id=self.event.data.channel_id,
            dm_conversation_id=self.event.data.dm_conversation_id,
        )
        socket_tasks = [self.manager.get_user_socket(user_id) for user_id in user_ids]
        return [
            socket
            for socket in await asyncio.gather(*socket_tasks)
            if socket is not None
        ]

    async def handle_event(self) -> None:
        """Handle a message deleted event"""
        sockets = await self.get_sockets()
        await asyncio.gather(
            *[socket.send_json(self.event.model_dump_json()) for socket in sockets]
        )


class ReactionAddedEventHandler(EventHandler[ReactionAddedEvent]):
    """Handler for reaction added events"""

    def __init__(
        self, event: ReactionAddedEvent, db: Session, manager: WebSocketManager
    ):
        super().__init__(event, db, manager)

    async def get_sockets(self) -> list[WebSocket]:
        """Get the sockets for the event"""
        user_ids = get_members_for_message(self.event.data.message_id, self.db)
        socket_tasks = [self.manager.get_user_socket(user_id) for user_id in user_ids]
        return [
            socket
            for socket in await asyncio.gather(*socket_tasks)
            if socket is not None
        ]

    async def handle_event(self) -> None:
        """Handle a reaction added event"""
        sockets = await self.get_sockets()
        await asyncio.gather(
            *[socket.send_json(self.event.model_dump_json()) for socket in sockets]
        )


class ReactionRemovedEventHandler(EventHandler[ReactionRemovedEvent]):
    """Handler for reaction removed events"""

    def __init__(
        self, event: ReactionRemovedEvent, db: Session, manager: WebSocketManager
    ):
        super().__init__(event, db, manager)

    async def get_sockets(self) -> list[WebSocket]:
        """Get the sockets for the event"""
        user_ids = get_members_for_message(self.event.data.message_id, self.db)
        socket_tasks = [self.manager.get_user_socket(user_id) for user_id in user_ids]
        return [
            socket
            for socket in await asyncio.gather(*socket_tasks)
            if socket is not None
        ]

    async def handle_event(self) -> None:
        """Handle a reaction removed event"""
        sockets = await self.get_sockets()
        await asyncio.gather(
            *[socket.send_json(self.event.model_dump_json()) for socket in sockets]
        )


class TypingEventHandler(EventHandler[TypingEvent]):
    """Handler for typing events"""

    def __init__(self, event: TypingEvent, db: Session, manager: WebSocketManager):
        super().__init__(event, db, manager)

    async def get_sockets(self) -> list[WebSocket]:
        """Get the sockets for the event"""
        user_ids = get_members_for_conversations(
            self.db,
            ai_conversation_id=self.event.data.ai_conversation_id,
            channel_id=self.event.data.channel_id,
            dm_conversation_id=self.event.data.dm_conversation_id,
        )
        socket_tasks = [self.manager.get_user_socket(user_id) for user_id in user_ids]
        return [
            socket
            for socket in await asyncio.gather(*socket_tasks)
            if socket is not None
        ]

    async def handle_event(self) -> None:
        """Handle a typing event"""
        sockets = await self.get_sockets()
        await asyncio.gather(
            *[socket.send_json(self.event.model_dump_json()) for socket in sockets]
        )


class UserUpdatedEventHandler(EventHandler[UserUpdatedEvent]):
    """Handler for user updated events"""

    def __init__(self, event: UserUpdatedEvent, db: Session, manager: WebSocketManager):
        super().__init__(event, db, manager)

    async def get_sockets(self) -> list[WebSocket]:
        """Get the sockets for the event"""
        user_ids = get_relevant_members_for_user(self.event.data.id, self.db)
        socket_tasks = [self.manager.get_user_socket(user_id) for user_id in user_ids]
        return [
            socket
            for socket in await asyncio.gather(*socket_tasks)
            if socket is not None
        ]

    async def handle_event(self) -> None:
        """Handle a user updated event"""
        sockets = await self.get_sockets()
        await asyncio.gather(
            *[socket.send_json(self.event.model_dump_json()) for socket in sockets]
        )


class UserDeletedEventHandler(EventHandler[UserDeletedEvent]):
    """Handler for user deleted events"""

    def __init__(self, event: UserDeletedEvent, db: Session, manager: WebSocketManager):
        super().__init__(event, db, manager)

    async def get_sockets(self) -> list[WebSocket]:
        """Get the sockets for the event"""
        user_ids = get_relevant_members_for_user(self.event.data.id, self.db)
        socket_tasks = [self.manager.get_user_socket(user_id) for user_id in user_ids]
        return [
            socket
            for socket in await asyncio.gather(*socket_tasks)
            if socket is not None
        ]

    async def handle_event(self) -> None:
        """Handle a user deleted event"""
        sockets = await self.get_sockets()
        await asyncio.gather(
            *[socket.send_json(self.event.model_dump_json()) for socket in sockets]
        )


class UserOnlineEventHandler(EventHandler[UserOnlineEvent]):
    """Handler for user online events"""

    def __init__(self, event: UserOnlineEvent, db: Session, manager: WebSocketManager):
        super().__init__(event, db, manager)

    async def get_sockets(self) -> list[WebSocket]:
        """Get the sockets for the event"""
        user_ids = get_relevant_members_for_user(self.event.data.id, self.db)
        socket_tasks = [self.manager.get_user_socket(user_id) for user_id in user_ids]
        return [
            socket
            for socket in await asyncio.gather(*socket_tasks)
            if socket is not None
        ]

    async def handle_event(self) -> None:
        """Handle a user online event"""
        sockets = await self.get_sockets()
        await asyncio.gather(
            *[socket.send_json(self.event.model_dump_json()) for socket in sockets]
        )


class UserOfflineEventHandler(EventHandler[UserOfflineEvent]):
    """Handler for user offline events"""

    def __init__(self, event: UserOfflineEvent, db: Session, manager: WebSocketManager):
        super().__init__(event, db, manager)

    async def get_sockets(self) -> list[WebSocket]:
        """Get the sockets for the event"""
        user_ids = get_relevant_members_for_user(self.event.data.id, self.db)
        socket_tasks = [self.manager.get_user_socket(user_id) for user_id in user_ids]
        return [
            socket
            for socket in await asyncio.gather(*socket_tasks)
            if socket is not None
        ]

    async def handle_event(self) -> None:
        """Handle a user offline event"""
        sockets = await self.get_sockets()
        await asyncio.gather(
            *[socket.send_json(self.event.model_dump_json()) for socket in sockets]
        )


class AIMessageHandler(EventHandler[AIMessageEvent]):
    """Handler for AI message started events"""

    def __init__(self, event: AIMessageEvent, db: Session, manager: WebSocketManager):
        super().__init__(event, db, manager)

    async def get_sockets(self) -> list[WebSocket]:
        """Get the sockets for the event"""
        user_socket = await self.manager.get_user_socket(self.event.data.user_id)
        if user_socket:
            return [user_socket]
        return []

    async def handle_event(self) -> None:
        """Handle an AI message event"""
        sockets = await self.get_sockets()
        await asyncio.gather(
            *[socket.send_json(self.event.model_dump_json()) for socket in sockets]
        )


class FileCreatedEventHandler(EventHandler[FileCreatedEvent]):
    """Handler for file created events"""

    def __init__(self, event: FileCreatedEvent, db: Session, manager: WebSocketManager):
        super().__init__(event, db, manager)

    async def get_sockets(self) -> list[WebSocket]:
        """Get the sockets for the event"""
        user_ids = get_members_for_conversations(
            self.db,
            ai_conversation_id=self.event.data.ai_conversation_id,
            channel_id=self.event.data.channel_id,
            dm_conversation_id=self.event.data.dm_conversation_id,
        )
        socket_tasks = [self.manager.get_user_socket(user_id) for user_id in user_ids]
        return [
            socket
            for socket in await asyncio.gather(*socket_tasks)
            if socket is not None
        ]

    async def handle_event(self) -> None:
        """Handle a file created event"""
        sockets = await self.get_sockets()
        await asyncio.gather(
            *[socket.send_json(self.event.model_dump_json()) for socket in sockets]
        )


class FileDeletedEventHandler(EventHandler[FileDeletedEvent]):
    """Handler for file deleted events"""

    def __init__(self, event: FileDeletedEvent, db: Session, manager: WebSocketManager):
        super().__init__(event, db, manager)

    async def get_sockets(self) -> list[WebSocket]:
        """Get the sockets for the event"""
        user_ids = get_members_for_conversations(
            self.db,
            ai_conversation_id=self.event.data.ai_conversation_id,
            channel_id=self.event.data.channel_id,
            dm_conversation_id=self.event.data.dm_conversation_id,
        )
        socket_tasks = [self.manager.get_user_socket(user_id) for user_id in user_ids]
        return [
            socket
            for socket in await asyncio.gather(*socket_tasks)
            if socket is not None
        ]

    async def handle_event(self) -> None:
        """Handle a file deleted event"""
        sockets = await self.get_sockets()
        await asyncio.gather(
            *[socket.send_json(self.event.model_dump_json()) for socket in sockets]
        )


class WorkspaceCreatedEventHandler(EventHandler[WorkspaceCreatedEvent]):
    """Handler for workspace created events"""

    def __init__(
        self, event: WorkspaceCreatedEvent, db: Session, manager: WebSocketManager
    ):
        super().__init__(event, db, manager)

    async def get_sockets(self) -> list[WebSocket]:
        """Get the sockets for the event"""
        sockets = await self.manager.get_user_socket(self.event.data.created_by_id)
        return [sockets] if sockets else []

    async def handle_event(self) -> None:
        """Handle a workspace created event"""
        sockets = await self.get_sockets()
        await asyncio.gather(
            *[socket.send_json(self.event.model_dump_json()) for socket in sockets]
        )


class WorkspaceUpdatedEventHandler(EventHandler[WorkspaceUpdatedEvent]):
    """Handler for workspace updated events"""

    def __init__(
        self, event: WorkspaceUpdatedEvent, db: Session, manager: WebSocketManager
    ):
        super().__init__(event, db, manager)

    async def get_sockets(self) -> list[WebSocket]:
        """Get the sockets for the event"""
        workspace_repository = WorkspaceRepository(self.db)
        if workspace := workspace_repository.get(self.event.data.id):
            if members := workspace.members:
                return [
                    socket
                    for socket in await asyncio.gather(
                        *[self.manager.get_user_socket(member.id) for member in members]
                    )
                    if socket is not None
                ]
        return []

    async def handle_event(self) -> None:
        """Handle a workspace updated event"""
        sockets = await self.get_sockets()
        await asyncio.gather(
            *[socket.send_json(self.event.model_dump_json()) for socket in sockets]
        )


class WorkspaceDeletedEventHandler(EventHandler[WorkspaceDeletedEvent]):
    """Handler for workspace deleted events"""

    def __init__(
        self, event: WorkspaceDeletedEvent, db: Session, manager: WebSocketManager
    ):
        super().__init__(event, db, manager)

    async def get_sockets(self) -> list[WebSocket]:
        """Get the sockets for the event"""
        workspace_repository = WorkspaceRepository(self.db)
        if workspace := workspace_repository.get(self.event.data.id):
            if members := workspace.members:
                return [
                    socket
                    for socket in await asyncio.gather(
                        *[self.manager.get_user_socket(member.id) for member in members]
                    )
                    if socket is not None
                ]
        return []

    async def handle_event(self) -> None:
        """Handle a workspace deleted event"""
        sockets = await self.get_sockets()
        await asyncio.gather(
            *[socket.send_json(self.event.model_dump_json()) for socket in sockets]
        )


class WorkspaceMemberAddedEventHandler(EventHandler[WorkspaceMemberAddedEvent]):
    """Handler for workspace member added events"""

    def __init__(
        self, event: WorkspaceMemberAddedEvent, db: Session, manager: WebSocketManager
    ):
        super().__init__(event, db, manager)

    async def get_sockets(self) -> list[WebSocket]:
        """Get the sockets for the event"""
        workspace_repository = WorkspaceRepository(self.db)
        if workspace := workspace_repository.get(self.event.data.workspace_id):
            if members := workspace.members:
                return [
                    socket
                    for socket in await asyncio.gather(
                        *[self.manager.get_user_socket(member.id) for member in members]
                    )
                    if socket is not None
                ]
        return []

    async def handle_event(self) -> None:
        """Handle a workspace member added event"""
        sockets = await self.get_sockets()
        await asyncio.gather(
            *[socket.send_json(self.event.model_dump_json()) for socket in sockets]
        )


class WorkspaceMemberRemovedEventHandler(EventHandler[WorkspaceMemberRemovedEvent]):
    """Handler for workspace member removed events"""

    def __init__(
        self, event: WorkspaceMemberRemovedEvent, db: Session, manager: WebSocketManager
    ):
        super().__init__(event, db, manager)

    async def get_sockets(self) -> list[WebSocket]:
        """Get the sockets for the event"""
        workspace_repository = WorkspaceRepository(self.db)
        if workspace := workspace_repository.get(self.event.data.workspace_id):
            if members := workspace.members:
                return [
                    socket
                    for socket in await asyncio.gather(
                        *[self.manager.get_user_socket(member.id) for member in members]
                    )
                    if socket is not None
                ]
        return []

    async def handle_event(self) -> None:
        """Handle a workspace member removed event"""
        sockets = await self.get_sockets()
        await asyncio.gather(
            *[socket.send_json(self.event.model_dump_json()) for socket in sockets]
        )


class WorkspaceMemberRoleUpdatedEventHandler(
    EventHandler[WorkspaceMemberRoleUpdatedEvent]
):
    """Handler for workspace member role updated events"""

    def __init__(
        self,
        event: WorkspaceMemberRoleUpdatedEvent,
        db: Session,
        manager: WebSocketManager,
    ):
        super().__init__(event, db, manager)

    async def get_sockets(self) -> list[WebSocket]:
        """Get the sockets for the event"""
        workspace_repository = WorkspaceRepository(self.db)
        if workspace := workspace_repository.get(self.event.data.workspace_id):
            if members := workspace.members:
                return [
                    socket
                    for socket in await asyncio.gather(
                        *[self.manager.get_user_socket(member.id) for member in members]
                    )
                    if socket is not None
                ]
        return []

    async def handle_event(self) -> None:
        """Handle a workspace member role updated event"""
        sockets = await self.get_sockets()
        await asyncio.gather(
            *[socket.send_json(self.event.model_dump_json()) for socket in sockets]
        )


class ErrorEventHandler(EventHandler[ErrorEvent]):
    """Handler for error events"""

    def __init__(self, event: ErrorEvent, db: Session, manager: WebSocketManager):
        super().__init__(event, db, manager)

    async def get_sockets(self) -> list[WebSocket]:
        """Get the sockets for the event"""
        user_socket = await self.manager.get_user_socket(self.event.data.user_id)
        return [user_socket] if user_socket else []

    async def handle_event(self) -> None:
        """Handle an error event"""
        sockets = await self.get_sockets()
        await asyncio.gather(
            *[socket.send_json(self.event.model_dump_json()) for socket in sockets]
        )


event_router = {
    EventType.MESSAGE_CREATED: MessageCreatedEventHandler,
    EventType.MESSAGE_DELETED: MessageDeletedEventHandler,
    EventType.REACTION_ADDED: ReactionAddedEventHandler,
    EventType.REACTION_REMOVED: ReactionRemovedEventHandler,
    EventType.TYPING_STARTED: TypingEventHandler,
    EventType.TYPING_STOPPED: TypingEventHandler,
    EventType.USER_UPDATED: UserUpdatedEventHandler,
    EventType.USER_DELETED: UserDeletedEventHandler,
    EventType.USER_ONLINE: UserOnlineEventHandler,
    EventType.USER_OFFLINE: UserOfflineEventHandler,
    EventType.AI_MESSAGE_STARTED: AIMessageHandler,
    EventType.AI_MESSAGE_CHUNK: AIMessageHandler,
    EventType.AI_MESSAGE_COMPLETED: AIMessageHandler,
    EventType.AI_ERROR: AIMessageHandler,
    EventType.FILE_CREATED: FileCreatedEventHandler,
    EventType.FILE_DELETED: FileDeletedEventHandler,
    EventType.WORKSPACE_CREATED: WorkspaceCreatedEventHandler,
    EventType.WORKSPACE_UPDATED: WorkspaceUpdatedEventHandler,
    EventType.WORKSPACE_DELETED: WorkspaceDeletedEventHandler,
    EventType.WORKSPACE_MEMBER_ADDED: WorkspaceMemberAddedEventHandler,
    EventType.WORKSPACE_MEMBER_REMOVED: WorkspaceMemberRemovedEventHandler,
    EventType.WORKSPACE_MEMBER_UPDATED: WorkspaceMemberRoleUpdatedEventHandler,
    EventType.ERROR: ErrorEventHandler,
}


def get_event_handler(event: EventType) -> type[EventHandler]:
    """Get the event handler for an event"""
    try:
        return event_router[event]
    except KeyError:
        raise ValueError(f"No event handler found for event type: {event}")


class WebSocketService:
    """Service for handling WebSocket events"""

    def __init__(
        self,
        db: Session = Depends(get_db),
        manager: WebSocketManager = WebSocketManager(),
    ):
        self.db = db
        self.manager = manager

    async def handle_event(self, event: BaseEvent) -> None:
        """Handle an event"""
        handler_class = get_event_handler(event.type)
        handler = handler_class(event, self.db, self.manager)
        await handler.handle_event()
