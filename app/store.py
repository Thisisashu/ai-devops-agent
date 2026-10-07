"""In-memory store for request records."""
from __future__ import annotations

from typing import Dict, Optional

from app.models import RequestRecord


_store: Dict[str, RequestRecord] = {}


def save(record: RequestRecord) -> None:
    _store[record.request_id] = record


def get(request_id: str) -> Optional[RequestRecord]:
    return _store.get(request_id)


def all_records() -> Dict[str, RequestRecord]:
    return dict(_store)
