from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Cookie
from uuid import UUID
from app.websocket_manager import manager, WebSocketMessageType
import json
from typing import Any
from datetime import datetime, timezone, UTC

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    access_token: str = Cookie(...),
):
    try:
        # Connect and authenticate
        print("Attempting to connect WebSocket...")
        user, connection_id = await manager.connect(websocket, access_token)
        print(f"WebSocket connected for user {user.id} with connection {connection_id}")
        
        try:
            while True:
                # Receive and parse message
                raw_data = await websocket.receive_text()
                print(f"Received raw data: {raw_data}")
                try:
                    data = json.loads(raw_data)
                    message_type = data.get("type")
                    message_data = data.get("data", {})
                    
                    print(f"Received WebSocket message: {message_type} - {message_data}")
                    
                    # Handle different message types
                    if message_type == "subscribe_channel":
                        channel_id = message_data.get("channel_id")
                        if channel_id:
                            print(f"Subscribing user {user.id} to channel {channel_id}")
                            try:
                                manager.subscribe_to_channel(user.id, UUID(channel_id))
                                await websocket.send_json({
                                    "type": "subscribed",
                                    "data": {
                                        "channel_id": channel_id
                                    }
                                })
                            except ValueError:
                                print(f"Invalid channel ID format: {channel_id}")
                                await websocket.send_json({
                                    "type": "error",
                                    "data": {
                                        "message": "Invalid channel ID format"
                                    }
                                })
                    
                    elif message_type == "unsubscribe_channel":
                        channel_id = message_data.get("channel_id")
                        if channel_id:
                            print(f"Unsubscribing user {user.id} from channel {channel_id}")
                            try:
                                manager.unsubscribe_from_channel(user.id, UUID(channel_id))
                                await websocket.send_json({
                                    "type": "unsubscribed",
                                    "data": {
                                        "channel_id": channel_id
                                    }
                                })
                            except ValueError:
                                print(f"Invalid channel ID format: {channel_id}")
                                await websocket.send_json({
                                    "type": "error",
                                    "data": {
                                        "message": "Invalid channel ID format"
                                    }
                                })
                    
                    elif message_type == WebSocketMessageType.PING:
                        await manager.handle_ping(user.id, connection_id)
                    
                    # Send acknowledgment
                    await websocket.send_json({
                        "type": "ack",
                        "data": {
                            "received_type": message_type,
                            "timestamp": datetime.now(UTC).isoformat()
                        }
                    })
                
                except json.JSONDecodeError:
                    print(f"Invalid JSON received: {raw_data}")
                    await websocket.send_json({
                        "type": "error",
                        "data": {
                            "message": "Invalid JSON format"
                        }
                    })
                except Exception as e:
                    print(f"Error handling WebSocket message: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "data": {
                            "message": str(e)
                        }
                    })
        
        except WebSocketDisconnect:
            print(f"WebSocket disconnected for user {user.id}")
            await manager.disconnect(user.id, connection_id)
    
    except Exception as e:
        print(f"WebSocket connection error: {e}")
        await websocket.close(code=1008, reason=str(e)) 