from __future__ import annotations

from typing import Any

from sqlalchemy import event

from sqlmodel import Session
from app.core.task_queue import TaskQueue
from app.models.domain import (
    File,
    Message,
    User,
    Reaction,
    Workspace,
    WorkspaceMember,
)
from app.models.schemas.events import (
    ChatMessageData,
    ChatMessageCreatedEvent,
    ChatMessageDeletedEvent,
    EventType,
    FileData,
    ReactionAddedData,
    ReactionAddedEvent,
    ReactionRemovedData,
    ReactionRemovedEvent,
    UserUpdatedEvent,
    UserDeletedData,
    UserDeletedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    WorkspaceCreatedEvent,
    WorkspaceUpdatedEvent,
    WorkspaceDeletedData,
    WorkspaceDeletedEvent,
    WorkspaceMemberAddedData,
    WorkspaceMemberAddedEvent,
    WorkspaceMemberRemovedData,
    WorkspaceMemberRemovedEvent,
    WorkspaceMemberRoleUpdatedData,
    WorkspaceMemberRoleUpdatedEvent,
)
from app.models.schemas.responses.user import UserResponse
from app.models.schemas.responses.workspace import WorkspaceResponse
from app.services.websocket_service import WebSocketService
from app.core.websocket import WebSocketManager


def setup_events(session: Session) -> None:
    """Setup SQLAlchemy event listeners"

    There are two types of events:
        - Database manipulation
        - WebSocket events

    """

    # Initialize services
    websocket_service = WebSocketService(db=session, manager=WebSocketManager())
    task_queue = TaskQueue()

    """
    WEBSOCKET EVENTS
    """

    """ Chat Message Events """

    # Creation
    @event.listens_for(target=Message, identifier="after_insert")
    def handle_message_created(m: Any, c: Any, target: Message) -> None:
        """Handle message created event"""
        chat_message_created_data = ChatMessageData.model_validate(
            Message.model_dump(target)
        )
        chat_message_created_event = ChatMessageCreatedEvent(
            type=EventType.MESSAGE_CREATED,
            data=chat_message_created_data,
        )
        task_queue.enqueue(websocket_service.handle_event(chat_message_created_event))

    # Deletion
    @event.listens_for(target=Message, identifier="after_delete")
    def handle_message_deleted(_m, _c, target: Message) -> None:
        """Handle message deleted event"""
        chat_message_deleted_data = ChatMessageData.model_validate(
            Message.model_dump(target)
        )
        chat_message_deleted_event = ChatMessageDeletedEvent(
            type=EventType.MESSAGE_DELETED,
            data=chat_message_deleted_data,
        )
        task_queue.enqueue(websocket_service.handle_event(chat_message_deleted_event))

    """ Reaction Events """

    # Addition
    @event.listens_for(target=Reaction, identifier="after_insert")
    def handle_reaction_created(_m, _c, target: Reaction) -> None:
        """Handle reaction added event"""
        reaction_added_data = ReactionAddedData.model_validate(
            Reaction.model_dump(target)
        )
        reaction_added_event = ReactionAddedEvent(
            type=EventType.REACTION_ADDED,
            data=reaction_added_data,
        )
        task_queue.enqueue(websocket_service.handle_event(reaction_added_event))

    @event.listens_for(target=Reaction, identifier="after_delete")
    def handle_reaction_deleted(_m, _c, target: Reaction) -> None:
        """Handle reaction deleted event"""
        reaction_removed_data = ReactionRemovedData(
            id=target.id, message_id=target.message_id, user_id=target.user_id
        )
        reaction_removed_event = ReactionRemovedEvent(
            type=EventType.REACTION_REMOVED,
            data=reaction_removed_data,
        )
        task_queue.enqueue(websocket_service.handle_event(reaction_removed_event))

    """ User Events """

    @event.listens_for(target=User, identifier="after_update")
    def handle_user_updated(_m: Any, _c: Any, target: User) -> None:
        """Handle user updated event"""
        user_updated_data = UserResponse(
            id=target.id,
            email=target.email,
            username=target.username,
            display_name=target.display_name,
            is_online=target.is_online,
            s3_key=target.s3_key,
            created_at=target.created_at,
            updated_at=target.updated_at,
        )
        user_updated_event = UserUpdatedEvent(
            type=EventType.USER_UPDATED, data=user_updated_data
        )
        task_queue.enqueue(websocket_service.handle_event(user_updated_event))

    @event.listens_for(target=User, identifier="after_delete")
    def handle_user_deleted(_m: Any, _c: Any, target: User) -> None:
        """Handle user deleted event"""
        user_deleted_data = UserDeletedData(id=target.id)
        user_deleted_event = UserDeletedEvent(
            type=EventType.USER_DELETED, data=user_deleted_data
        )
        task_queue.enqueue(websocket_service.handle_event(user_deleted_event))

    @event.listens_for(target=File, identifier="after_insert")
    def handle_file_created(_m: Any, _c: Any, target: File) -> None:
        """Handle file created event"""
        file_created_data = FileData.model_validate(File.model_dump(target))
        file_created_event = FileCreatedEvent(
            type=EventType.FILE_CREATED,
            data=file_created_data,
        )
        task_queue.enqueue(websocket_service.handle_event(file_created_event))

    @event.listens_for(target=File, identifier="after_delete")
    def handle_file_deleted(mapper: Any, connection: Any, target: File) -> None:
        """Handle file deleted event"""
        file_deleted_data = FileData.model_validate(File.model_dump(target))
        file_deleted_event = FileDeletedEvent(
            type=EventType.FILE_DELETED,
            data=file_deleted_data,
        )
        task_queue.enqueue(websocket_service.handle_event(file_deleted_event))

    """ Workspace Events """

    @event.listens_for(target=Workspace, identifier="after_insert")
    def handle_workspace_created(_m: Any, _c: Any, target: Workspace) -> None:
        """Handle workspace created event"""
        workspace_created_data = WorkspaceResponse(
            id=target.id,
            name=target.name,
            slug=target.slug,
            created_by_id=target.created_by_id,
            created_at=target.created_at,
            updated_at=target.updated_at,
        )
        workspace_created_event = WorkspaceCreatedEvent(
            type=EventType.WORKSPACE_CREATED,
            data=workspace_created_data,
        )
        task_queue.enqueue(websocket_service.handle_event(workspace_created_event))

    @event.listens_for(target=Workspace, identifier="after_update")
    def handle_workspace_updated(_m: Any, _c: Any, target: Workspace) -> None:
        """Handle workspace updated event"""
        workspace_updated_data = WorkspaceResponse(
            id=target.id,
            name=target.name,
            slug=target.slug,
            created_by_id=target.created_by_id,
            created_at=target.created_at,
            updated_at=target.updated_at,
        )
        workspace_updated_event = WorkspaceUpdatedEvent(
            type=EventType.WORKSPACE_UPDATED,
            data=workspace_updated_data,
        )
        task_queue.enqueue(websocket_service.handle_event(workspace_updated_event))

    @event.listens_for(target=Workspace, identifier="after_delete")
    def handle_workspace_deleted(_m: Any, _c: Any, target: Workspace) -> None:
        """Handle workspace deleted event"""
        workspace_deleted_data = WorkspaceDeletedData(id=target.id)
        workspace_deleted_event = WorkspaceDeletedEvent(
            type=EventType.WORKSPACE_DELETED,
            data=workspace_deleted_data,
        )
        task_queue.enqueue(websocket_service.handle_event(workspace_deleted_event))

    @event.listens_for(target=WorkspaceMember, identifier="after_insert")
    def handle_workspace_member_added(
        _m: Any, _c: Any, target: WorkspaceMember
    ) -> None:
        """Handle workspace member added event"""
        workspace_member_added_data = WorkspaceMemberAddedData.model_validate(
            WorkspaceMember.model_dump(target)
        )
        workspace_member_added_event = WorkspaceMemberAddedEvent(
            type=EventType.WORKSPACE_MEMBER_ADDED,
            data=workspace_member_added_data,
        )
        task_queue.enqueue(websocket_service.handle_event(workspace_member_added_event))

    @event.listens_for(target=WorkspaceMember, identifier="after_update")
    def handle_workspace_member_updated(
        _m: Any, _c: Any, target: WorkspaceMember
    ) -> None:
        """Handle workspace member update event (for role changes)"""
        workspace_member_updated_data = WorkspaceMemberRoleUpdatedData.model_validate(
            WorkspaceMember.model_dump(target)
        )
        workspace_member_updated_event = WorkspaceMemberRoleUpdatedEvent(
            type=EventType.WORKSPACE_MEMBER_UPDATED,
            data=workspace_member_updated_data,
        )
        task_queue.enqueue(
            websocket_service.handle_event(workspace_member_updated_event)
        )

    @event.listens_for(target=WorkspaceMember, identifier="after_delete")
    def handle_workspace_member_removed(
        _m: Any, _c: Any, target: WorkspaceMember
    ) -> None:
        """Handle workspace member removed event"""
        workspace_member_removed_data = WorkspaceMemberRemovedData(
            user_id=target.user_id, workspace_id=target.workspace_id
        )
        workspace_member_removed_event = WorkspaceMemberRemovedEvent(
            type=EventType.WORKSPACE_MEMBER_REMOVED,
            data=workspace_member_removed_data,
        )
        task_queue.enqueue(
            websocket_service.handle_event(workspace_member_removed_event)
        )
