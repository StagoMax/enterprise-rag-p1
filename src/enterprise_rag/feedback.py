import threading
from pathlib import Path

from enterprise_rag.models import FeedbackEvent


class JsonlFeedbackStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: FeedbackEvent) -> None:
        with self._lock, self._path.open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")
