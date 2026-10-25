"""WebSocket fan-out for live ticks, alerts and integrity events."""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger(__name__)
router = APIRouter()


class Broadcaster:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, message: dict) -> None:
        data = json.dumps(message, default=str)
        for ws in list(self._clients):
            try:
                await ws.send_text(data)
            except Exception:
                self._clients.discard(ws)

    def publish(self, message: dict) -> None:
        """Thread-safe broadcast, for code running outside the event loop."""
        if self._loop is not None and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(message), self._loop)


@router.websocket("/ws/live")
async def live(ws: WebSocket) -> None:
    rt = ws.app.state.rt
    await rt.ws.connect(ws)
    try:
        await ws.send_text(json.dumps({"type": "hello", **rt.sim_status()}, default=str))
        while True:
            await ws.receive_text()  # clients don't send anything meaningful; keeps the socket open
    except WebSocketDisconnect:
        pass
    finally:
        rt.ws.disconnect(ws)
