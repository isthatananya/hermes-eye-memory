"""Configuration helpers.

Settings live under ``plugins.entries.hermes-eye-memory.settings`` and are read
through ``ctx.get_config``. Environment variables are a fallback for tests and
CLI use outside a running gateway.
"""

from __future__ import annotations

import os
from typing import Any

_CTX: Any = None


def set_context(ctx: Any) -> None:
    global _CTX
    _CTX = ctx


def get(key: str, default: Any = None) -> Any:
    if _CTX is not None:
        try:
            return _CTX.get_config(key, default=default)
        except Exception:
            pass
    env_key = "HERMES_EYE_MEMORY_" + key.upper()
    aliases = [env_key]
    if key == "library_path":
        aliases.insert(0, "HERMES_EYE_MEMORY_LIBRARY")
    for name in aliases:
        value = os.environ.get(name)
        if value is not None:
            return value
    return default


def library_path() -> str:
    return str(get("library_path", "") or "")


def ocr_enabled() -> bool:
    value = get("ocr_enabled", True)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def embedding_backend() -> str:
    value = str(get("embedding_backend", "clip") or "clip").strip().lower()
    return value if value in {"clip", "fallback"} else "clip"


def camera_enabled() -> bool:
    value = get("camera_enabled", False)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off", ""}
    return bool(value)


def camera_index() -> int:
    try:
        return int(get("camera_index", 0))
    except (TypeError, ValueError):
        return 0


def max_results() -> int:
    try:
        return max(1, min(200, int(get("max_results", 20))))
    except (TypeError, ValueError):
        return 20


def max_forget_query() -> int:
    try:
        return max(1, min(200, int(get("max_forget_query", 20))))
    except (TypeError, ValueError):
        return 20
