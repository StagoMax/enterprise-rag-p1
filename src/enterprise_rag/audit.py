import threading
from pathlib import Path

from enterprise_rag.models import AuditEvent


class JsonlAuditStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._events: list[AuditEvent] = []
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: AuditEvent) -> None:
        line = event.model_dump_json() + "\n"
        with self._lock:
            self._events.append(event)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line)

    def recent(self, limit: int = 100) -> list[AuditEvent]:
        with self._lock:
            return list(reversed(self._events[-limit:]))

