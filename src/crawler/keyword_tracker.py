"""src/crawler/keyword_tracker.py – Trackt Keyword + Seite für Stepstone-Rotation."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("job-hunter")

TRACKER_PATH = Path("./data/stepstone_keyword_tracker.json")


def _load() -> dict:
    if TRACKER_PATH.exists():
        try:
            return json.loads(TRACKER_PATH.read_text())
        except Exception:
            pass
    return {}


def _save(data: dict) -> None:
    TRACKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRACKER_PATH.write_text(json.dumps(data, indent=2))


def get_next(all_keywords: list[str], max_pages: int = 5) -> list[tuple[str, int]]:
    """Gibt die nächsten (keyword, page) Tupel zurück die gescrapt werden sollen.
    Round-robin durch alle Keywords bis target erreicht."""
    data = _load()
    completed = set(data.get("completed", []))
    remaining = [kw for kw in all_keywords if kw not in completed]
    if not remaining:
        data["completed"] = []
        _save(data)
        remaining = all_keywords

    tasks = []
    for kw in remaining:
        current_page = 1
        tasks.append((kw, current_page))
        if len(tasks) >= 3:
            break
    return tasks


def advance() -> None:
    """Erhöht Seite oder wechselt zum nächsten Keyword."""
    data = _load()
    current_kw = data.get("current_keyword")
    current_page = data.get("current_page", 1)
    max_pages = 5

    if current_page < max_pages:
        data["current_page"] = current_page + 1
    else:
        # Alle Seiten für dieses Keyword fertig
        completed = set(data.get("completed", []))
        if current_kw:
            completed.add(current_kw)
            data["completed"] = list(completed)
        data["current_keyword"] = None
        data["current_page"] = 1

    data["last_scraped"] = datetime.utcnow().isoformat()
    _save(data)


def set_current(keyword: str) -> None:
    """Setzt das aktuelle Keyword (falls noch keins gesetzt)."""
    data = _load()
    if not data.get("current_keyword"):
        data["current_keyword"] = keyword
        data["current_page"] = 1
        _save(data)


def get_status() -> dict:
    return _load()
