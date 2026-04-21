from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from typing import Any


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
    )


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    **fields: Any,
) -> None:
    payload = {"event": event, **_sanitize_mapping(fields)}
    logger.log(
        level,
        json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
            sort_keys=True,
        ),
    )


def _sanitize_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _sanitize_value(item) for key, item in value.items()}


def _sanitize_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:200]
    if isinstance(value, Mapping):
        return _sanitize_mapping(value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_sanitize_value(item) for item in list(value)[:20]]
    return str(value)[:200]


__all__ = ["configure_logging", "log_event"]
