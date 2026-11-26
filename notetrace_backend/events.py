import asyncio
import json
from typing import AsyncGenerator, Set

class EventBroker:
    def __init__(self):
        self.subscribers: Set[asyncio.Queue] = set()

    async def subscribe(self) -> AsyncGenerator[str, None]:
        q = asyncio.Queue(maxsize=100)
        self.subscribers.add(q)
        try:
            # Send initial ping
            yield "event: ping\ndata: {}\n\n"
            while True:
                try:
                    data = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield data
                except asyncio.TimeoutError:
                    # Heartbeat comment to keep Wi-Fi/mobile sockets open without closing
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            self.subscribers.discard(q)

    def publish(self, event_type: str, data: dict):
        payload = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        for q in list(self.subscribers):
            try:
                q.put_nowait(payload)
            except (asyncio.QueueFull, Exception):
                pass

broker = EventBroker()

def notify_update(event_type: str, data: dict):
    broker.publish(event_type, data)
