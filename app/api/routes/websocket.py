import traceback

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import ValidationError
from sqlmodel import Session

from app.api.dependencies import get_current_user, get_db
from app.core.events import EventType
from app.models.domain import User
from app.models.schemas.events import BaseEvent, ErrorData, UserPresenceData, ErrorEvent
from app.services.websocket_service import WebSocketService, UserOnlineEvent
from app.core.websocket import WebSocketManager
from loguru import logger

router = APIRouter(tags=["websocket"])


async def get_ws_user(
    websocket: WebSocket,
    db: Session = Depends(get_db),
) -> User:
    """Get current user from WebSocket connection using the access token cookie"""
    access_token = websocket.cookies.get("access_token")
    if not access_token:
        raise WebSocketDisconnect(code=1008, reason="No access token cookie provided")

    try:
        user = await get_current_user(access_token, db)
        if not user:
            raise WebSocketDisconnect(code=1008, reason="Invalid token")
        return user
    except HTTPException:
        raise WebSocketDisconnect(code=1008, reason="Invalid token")


@router.websocket("/api/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    user: User = Depends(get_ws_user),
    db: Session = Depends(get_db),
) -> None:
    """WebSocket endpoint for real-time communication."""
    websocket_manager = WebSocketManager()

    try:
        # Connect user
        await websocket_manager.connect(websocket, user.id)
        websocket_service = WebSocketService(db, websocket_manager)
        # Keep a timer that sends an online event every 10 seconds so that we don't get flooded with events from all clients
        user.is_online = True
        db.add(user)
        db.commit()
        await websocket_service.handle_event(
            UserOnlineEvent(
                type=EventType.USER_ONLINE,
                data=UserPresenceData(id=user.id, is_online=True),
            )
        )

        # Listen for messages
        while True:
            try:
                message: BaseEvent = await websocket.receive_json()
                await websocket_service.handle_event(message)

            except WebSocketDisconnect:
                if user:  # Only try to disconnect if user exists
                    await websocket_manager.disconnect(user.id)
                    user.is_online = False
                    db.add(user)
                    db.commit()
                    db.refresh(user)
                    # This will trigger a db event listener that will send a user offline event
                break
            except ValidationError as e:
                logger.error(
                    f"Validation error processing message: {e}\n\n{traceback.format_exc()}"
                )
                error_data = ErrorData(
                    error=str(e),
                    human_readable_error=f"There was an error validating {message.type}.",
                    user_id=user.id,
                )
                await websocket_service.handle_event(
                    ErrorEvent(
                        type=EventType.ERROR,
                        data=error_data,
                    )
                )

            except ValueError as e:
                logger.error(
                    f"Value error processing message: {e}\n\n{traceback.format_exc()}"
                )
                error_data = ErrorData(
                    error=str(e),
                    human_readable_error=f"There was a value error processing {message.type}.",
                    user_id=user.id,
                )
                await websocket_service.handle_event(
                    ErrorEvent(
                        type=EventType.ERROR,
                        data=error_data,
                    )
                )

            except Exception as e:
                logger.error(
                    f"Unknown error processing message: {e}\n\n{traceback.format_exc()}"
                )
                error_data = ErrorData(
                    error=str(e),
                    human_readable_error=f"There was an unknown error processing {message.type}.",
                    user_id=user.id,
                )
                await websocket_service.handle_event(
                    ErrorEvent(
                        type=EventType.ERROR,
                        data=error_data,
                    )
                )
    except Exception as e:
        # Ensure we disconnect on any error
        if user:  # Only try to disconnect if user exists
            await websocket_manager.disconnect(user.id)
            user.is_online = False
            db.add(user)
            db.commit()
            db.refresh(user)
        logger.error(
            f"Unknown error in websocket endpoint: {e}\n\n{traceback.format_exc()}"
        )
        raise e
