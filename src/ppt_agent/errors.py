from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class PptAgentError(Exception):
    code: str
    message_zh: str
    next_action: str
    retryable: bool = False
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message_zh
