import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Cookie, WebSocket, WebSocketDisconnect

from app.websocket import WebSocketMessageType, manager

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

                    print(
                        f"Received WebSocket message: {message_type} - {message_data}"
                    )

                    # Handle different message types
                    if message_type == "subscribe":
                        channel_id = message_data.get("channel_id")
                        if channel_id:
                            print("\n🔍 Handling subscription request")
                            print(
                                f"User {user.id} requesting to subscribe to channel {channel_id}"
                            )
                            try:
                                channel_uuid = UUID(channel_id)
                                print(f"Converting channel ID to UUID: {channel_uuid}")

                                # Subscribe to the channel
                                manager.subscribe_to_conversation(user.id, channel_uuid)
                                print(
                                    f"Successfully subscribed user {user.id} to conversation {channel_uuid}"
                                )

                                # Send acknowledgment
                                ack_message = {
                                    "type": "ack",
                                    "data": {
                                        "received_type": "subscribe",
                                        "channel_id": str(channel_uuid),
                                        "timestamp": datetime.now(UTC).isoformat(),
                                    },
                                }
                                print(f"Sending acknowledgment: {ack_message}")
                                await websocket.send_json(ack_message)
                                print("Acknowledgment sent successfully")

                            except ValueError as e:
                                error = f"Invalid channel ID format: {channel_id} - {str(e)}"
                                print(f"Error: {error}")
                                await websocket.send_json(
                                    {
                                        "type": "error",
                                        "data": {"message": error},
                                    }
                                )
                            except Exception as e:
                                error = f"Error subscribing to channel: {str(e)}"
                                print(f"Error: {error}")
                                await websocket.send_json(
                                    {
                                        "type": "error",
                                        "data": {"message": error},
                                    }
                                )

                    elif message_type == "unsubscribe":
                        channel_id = message_data.get("channel_id")
                        if channel_id:
                            print("\n🔍 Handling unsubscribe request")
                            print(
                                f"User {user.id} requesting to unsubscribe from channel {channel_id}"
                            )
                            try:
                                channel_uuid = UUID(channel_id)
                                print(f"Converting channel ID to UUID: {channel_uuid}")

                                # Unsubscribe from the channel
                                manager.unsubscribe_from_conversation(
                                    user.id, channel_uuid
                                )
                                print(
                                    f"Successfully unsubscribed user {user.id} from conversation {channel_uuid}"
                                )

                                # Send acknowledgment
                                ack_message = {
                                    "type": "ack",
                                    "data": {
                                        "received_type": "unsubscribe",
                                        "channel_id": str(channel_uuid),
                                        "timestamp": datetime.now(UTC).isoformat(),
                                    },
                                }
                                print(f"Sending acknowledgment: {ack_message}")
                                await websocket.send_json(ack_message)
                                print("Acknowledgment sent successfully")

                            except ValueError as e:
                                error = f"Invalid channel ID format: {channel_id} - {str(e)}"
                                print(f"Error: {error}")
                                await websocket.send_json(
                                    {
                                        "type": "error",
                                        "data": {"message": error},
                                    }
                                )
                            except Exception as e:
                                error = f"Error unsubscribing from channel: {str(e)}"
                                print(f"Error: {error}")
                                await websocket.send_json(
                                    {
                                        "type": "error",
                                        "data": {"message": error},
                                    }
                                )

                    elif message_type == "verify_subscription":
                        channel_id = message_data.get("channel_id")
                        if channel_id:
                            print("\n🔍 Handling subscription verification request")
                            print(
                                f"User {user.id} verifying subscription to channel {channel_id}"
                            )
                            try:
                                channel_uuid = UUID(channel_id)
                                print(f"Converting channel ID to UUID: {channel_uuid}")

                                # Check if user is subscribed
                                is_subscribed = (
                                    user.id
                                    in manager.conversation_subscriptions.get(
                                        channel_uuid, set()
                                    )
                                )
                                print(
                                    f"Subscription status: {'Subscribed' if is_subscribed else 'Not subscribed'}"
                                )

                                # Send verification response
                                verification_message = {
                                    "type": "ack",
                                    "data": {
                                        "received_type": "verify_subscription",
                                        "channel_id": str(channel_uuid),
                                        "is_subscribed": is_subscribed,
                                        "timestamp": datetime.now(UTC).isoformat(),
                                    },
                                }
                                print(
                                    f"Sending verification response: {verification_message}"
                                )
                                await websocket.send_json(verification_message)
                                print("Verification response sent successfully")

                            except ValueError as e:
                                error = f"Invalid channel ID format: {channel_id} - {str(e)}"
                                print(f"Error: {error}")
                                await websocket.send_json(
                                    {
                                        "type": "error",
                                        "data": {"message": error},
                                    }
                                )
                            except Exception as e:
                                error = f"Error verifying subscription: {str(e)}"
                                print(f"Error: {error}")
                                await websocket.send_json(
                                    {
                                        "type": "error",
                                        "data": {"message": error},
                                    }
                                )

                    elif message_type == WebSocketMessageType.PING:
                        await manager.handle_ping(user.id, connection_id)
                        print(f"\n🔍 Handled ping from user {user.id}")

                    elif message_type == WebSocketMessageType.USER_PRESENCE:
                        is_online = message_data.get("is_online", True)
                        print(
                            f"\n🔍 Handling presence update for user {user.id}: {is_online}"
                        )
                        await manager.handle_presence_update(user.id, is_online)

                    elif message_type == WebSocketMessageType.USER_TYPING:
                        conversation_id = message_data.get("conversation_id")
                        if conversation_id:
                            # Skip temporary conversation IDs
                            if conversation_id.startswith("temp_"):
                                print(
                                    f"\n🔍 Ignoring typing update for temporary conversation {conversation_id}"
                                )
                                # Still send acknowledgment
                                ack_message = {
                                    "type": "ack",
                                    "data": {
                                        "received_type": message_type,
                                        "timestamp": datetime.now(UTC).isoformat(),
                                    },
                                }
                                await websocket.send_json(ack_message)
                                continue

                            try:
                                conversation_uuid = UUID(conversation_id)
                                print(
                                    f"\n🔍 Broadcasting typing update for user {user.id} in conversation {conversation_uuid}"
                                )
                                await manager.broadcast_to_conversation(
                                    conversation_uuid,
                                    WebSocketMessageType.USER_TYPING,
                                    {
                                        "user": {
                                            "id": str(user.id),
                                            "username": user.username,
                                            "display_name": user.display_name,
                                            "avatar_url": user.avatar_url,
                                        },
                                        "conversation_id": str(conversation_uuid),
                                        "is_typing": message_data.get(
                                            "is_typing", True
                                        ),
                                    },
                                )
                            except ValueError as e:
                                error = f"Invalid conversation ID format: {conversation_id} - {str(e)}"
                                print(f"Error: {error}")
                                await websocket.send_json(
                                    {
                                        "type": "error",
                                        "data": {"message": error},
                                    }
                                )
                            except Exception as e:
                                error = f"Error broadcasting typing update: {str(e)}"
                                print(f"Error: {error}")
                                await websocket.send_json(
                                    {
                                        "type": "error",
                                        "data": {"message": error},
                                    }
                                )

                    # Send acknowledgment for other message types
                    if message_type not in [
                        "subscribe",
                        "unsubscribe",
                        "verify_subscription",
                    ]:
                        ack_message = {
                            "type": "ack",
                            "data": {
                                "received_type": message_type,
                                "timestamp": datetime.now(UTC).isoformat(),
                            },
                        }
                        await websocket.send_json(ack_message)

                except json.JSONDecodeError as e:
                    print(f"Error decoding WebSocket message: {e}")
                    await websocket.send_json(
                        {
                            "type": "error",
                            "data": {"message": "Invalid JSON format"},
                        }
                    )
                except Exception as e:
                    print(f"Error handling WebSocket message: {e}")
                    await websocket.send_json(
                        {
                            "type": "error",
                            "data": {"message": str(e)},
                        }
                    )

        except WebSocketDisconnect:
            print(f"WebSocket disconnected for user {user.id}")
            await manager.disconnect(user.id, connection_id)
            await manager.broadcast_presence_update(user.id, False)

    except Exception as e:
        print(f"Error in WebSocket connection: {e}")
        await websocket.close(code=1008, reason=str(e))
        raise
