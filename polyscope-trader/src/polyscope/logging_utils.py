"""Structured logging with secret redaction."""

from __future__ import annotations

import logging
import re
from typing import Any

_SECRET_PATTERNS = (
    re.compile(r"(?i)(private[_-]?key|secret|passphrase|api[_-]?key)\s*[:=]\s*\S+"),
    re.compile(r"0x[a-fA-F0-9]{64}"),
)


def redact_message(message: str) -> str:
    out = message
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub("<redacted>", out)
    return out


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        original = record.msg
        if isinstance(record.msg, str):
            record.msg = redact_message(record.msg)
        formatted = super().format(record)
        record.msg = original
        return redact_message(formatted)


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        RedactingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(level)


def safe_extra(**kwargs: Any) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in kwargs.items():
        if value is None:
            safe[key] = None
            continue
        text = str(value)
        if "key" in key.lower() or "secret" in key.lower() or "pass" in key.lower():
            safe[key] = "<redacted>"
        else:
            safe[key] = redact_message(text)
    return safe
