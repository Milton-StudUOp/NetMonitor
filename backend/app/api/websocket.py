import json
import asyncio
from typing import List
import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.config import get_settings
from app.database import async_session_factory
from app.services.auth_service import authenticate_token

logger = structlog.get_logger()


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket, *, accept: bool = True):
        if accept:
            await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("ws_client_connected", total_connections=len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("ws_client_disconnected", total_connections=len(self.active_connections))

    async def broadcast(self, event_type: str, data: dict):
        message = json.dumps({"event": event_type, "data": data})
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/monitoring")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    if not get_settings().AUTH_DISABLED:
        try:
            auth_message = await asyncio.wait_for(websocket.receive_json(), timeout=5)
        except (asyncio.TimeoutError, ValueError, WebSocketDisconnect):
            await websocket.close(code=4401)
            return
        token = auth_message.get("token", "") if isinstance(auth_message, dict) and auth_message.get("type") == "authenticate" else ""
        async with async_session_factory() as db:
            if not token or not await authenticate_token(db, token):
                await websocket.close(code=4401)
                return
            await db.commit()
    await manager.connect(websocket, accept=False)
    await websocket.send_text(json.dumps({"event": "authenticated"}))
    try:
        while True:
            # Keep connection alive & listen for client ping/messages
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"event": "pong"}))
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error("ws_error", error_type=type(e).__name__)
        manager.disconnect(websocket)
