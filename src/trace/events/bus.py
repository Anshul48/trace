import asyncio
from typing import Callable, Dict, List, Any
from trace.core.schemas import Event

class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Event], Any]]] = {}

    def subscribe(self, event_name: str, callback: Callable[[Event], Any]):
        if event_name not in self._subscribers:
            self._subscribers[event_name] = []
        if callback not in self._subscribers[event_name]:
            self._subscribers[event_name].append(callback)

    async def publish(self, event: Event):
        if event.name in self._subscribers:
            for callback in self._subscribers[event.name]:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)

# Global event bus instance
event_bus = EventBus()
