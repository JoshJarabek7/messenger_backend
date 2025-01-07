from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from uuid import UUID
from app.websocket_manager import manager, WebSocketMessageType
import json
from typing import Any
from datetime import datetime, timezone, UTC

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
    channel_id: UUID | None = Query(None),
    workspace_id: UUID | None = Query(None)
):
    try:
        # Connect and authenticate
        user, connection_id = await manager.connect(websocket, token)
        
        # Subscribe to channel and/or workspace if provided
        if channel_id:
            manager.subscribe_to_channel(user.id, channel_id)
        if workspace_id:
            manager.subscribe_to_workspace(user.id, workspace_id)
        
        try:
            while True:
                # Receive and parse message
                raw_data = await websocket.receive_text()
                try:
                    data = json.loads(raw_data)
                    message_type = data.get("type")
                    message_data = data.get("data", {})
                    
                    # Handle different message types
                    if message_type == WebSocketMessageType.PING:
                        await manager.handle_ping(user.id, connection_id)
                    
                    elif message_type == WebSocketMessageType.MESSAGE_SENT:
                        await manager.handle_message(user.id, message_data)
                    
                    elif message_type == WebSocketMessageType.REACTION_SENT:
                        await manager.handle_reaction(user.id, message_data)
                    
                    elif message_type == WebSocketMessageType.USER_TYPING:
                        await manager.handle_typing(user.id, message_data)
                    
                    # Send acknowledgment
                    await websocket.send_json({
                        "type": "ack",
                        "data": {
                            "received_type": message_type,
                            "timestamp": datetime.now(UTC).isoformat()
                        }
                    })
                
                except json.JSONDecodeError:
                    await websocket.send_json({
                        "type": "error",
                        "data": {
                            "message": "Invalid JSON format"
                        }
                    })
                except KeyError as e:
                    await websocket.send_json({
                        "type": "error",
                        "data": {
                            "message": f"Missing required field: {str(e)}"
                        }
                    })
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "data": {
                            "message": str(e)
                        }
                    })
        
        except WebSocketDisconnect:
            # Clean up on disconnect
            if channel_id:
                manager.unsubscribe_from_channel(user.id, channel_id)
            if workspace_id:
                manager.unsubscribe_from_workspace(user.id, workspace_id)
            await manager.disconnect(user.id, connection_id)
    
    except Exception as e:
        # Handle connection/authentication errors
        await websocket.close(code=1008, reason=str(e)) 