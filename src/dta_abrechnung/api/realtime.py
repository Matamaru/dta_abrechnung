from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(slots=True, frozen=True)
class RealtimeEvent:
    channel: str
    event_type: str
    tenant_id: str
    payload: dict[str, object]
    emitted_at: datetime


class RealtimeBroker:
    def __init__(self) -> None:
        self._subscriptions: dict[str, set[asyncio.Queue[RealtimeEvent]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, channel: str) -> asyncio.Queue[RealtimeEvent]:
        queue: asyncio.Queue[RealtimeEvent] = asyncio.Queue()
        async with self._lock:
            self._subscriptions[channel].add(queue)
        return queue

    async def unsubscribe(self, channel: str, queue: asyncio.Queue[RealtimeEvent]) -> None:
        async with self._lock:
            subscribers = self._subscriptions.get(channel)
            if not subscribers:
                return
            subscribers.discard(queue)
            if not subscribers:
                self._subscriptions.pop(channel, None)

    async def publish(self, event: RealtimeEvent) -> None:
        async with self._lock:
            subscribers = tuple(self._subscriptions.get(event.channel, ()))
        for queue in subscribers:
            await queue.put(event)

    @staticmethod
    def make_event(channel: str, event_type: str, tenant_id: str, payload: dict[str, object]) -> RealtimeEvent:
        return RealtimeEvent(
            channel=channel,
            event_type=event_type,
            tenant_id=tenant_id,
            payload=payload,
            emitted_at=datetime.now(UTC),
        )
