"""Hermes tool handlers."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable

from . import actions, camera, config, db, embeddings, indexer, schemas, search

logger = logging.getLogger(__name__)

_CTX: Any = None
_JOB_LOCK = threading.Lock()
_JOB: dict[str, Any] = {
    "running": False,
    "status": "idle",
    "done": 0,
    "total": 0,
    "current": "",
    "counts": {},
    "started_at": None,
    "finished_at": None,
    "summary": None,
}


def set_context(ctx: Any) -> None:
    global _CTX
    _CTX = ctx
    config.set_context(ctx)


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _str(params: dict[str, Any], key: str, default: str = "") -> str:
    value = params.get(key, default)
    return str(value).strip() if value is not None else default


def _int(params: dict[str, Any], key: str, default: int | None = None) -> int | None:
    value = params.get(key, default)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bool(params: dict[str, Any], key: str, default: bool = False) -> bool:
    value = params.get(key, default)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off", ""}
    return bool(value)


def _tags(params: dict[str, Any], key: str = "tags") -> list[str]:
    value = params.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple)):
        return [str(part).strip() for part in value if str(part).strip()]
    return []


def _guard(handler: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[..., str]:
    def wrapped(params=None, **kwargs):
        try:
            return _json(handler(params or {}))
        except Exception as exc:  # keep tool failures readable to the agent
            logger.exception("eye tool failed")
            return _json({"ok": False, "error": str(exc)})

    return wrapped


def _progress(info: dict[str, Any]) -> None:
    with _JOB_LOCK:
        _JOB.update(
            done=int(info.get("done", 0)),
            total=int(info.get("total", 0)),
            current=str(info.get("current", "")),
            counts=info.get("counts", {}),
        )


def _run_index_job(path: str, force: bool, run_ocr: bool | None, limit: int | None) -> None:
    try:
        result = indexer.index_folder(
            path,
            force=force,
            run_ocr=run_ocr,
            progress=_progress,
            limit=limit,
        )
        status = "done" if result.get("ok") else "error"
    except Exception as exc:
        logger.exception("background index failed")
        result = {"ok": False, "error": str(exc)}
        status = "error"
    with _JOB_LOCK:
        _JOB.update(running=False, status=status, finished_at=db.now_iso(), summary=result)


@_guard
def _eye_index(params: dict[str, Any]) -> dict[str, Any]:
    path = _str(params, "path") or config.library_path()
    if not path:
        return {
            "ok": False,
            "error": "no library path configured. Set library_path in the plugin config or pass path.",
        }
    force = _bool(params, "force")
    run_ocr = params.get("ocr")
    if run_ocr is not None:
        run_ocr = _bool(params, "ocr", True)
    limit = _int(params, "limit")
    background = _bool(params, "background")

    if background:
        with _JOB_LOCK:
            if _JOB["running"]:
                return {"ok": False, "error": "an indexing job is already running", "job": dict(_JOB)}
            _JOB.update(
                running=True,
                status="starting",
                done=0,
                total=0,
                current="",
                counts={},
                started_at=db.now_iso(),
                finished_at=None,
                summary=None,
            )
        thread = threading.Thread(
            target=_run_index_job,
            args=(path, force, run_ocr, limit),
            daemon=True,
            name="eye-memory-index",
        )
        thread.start()
        return {"ok": True, "status": "started", "library": path, "background": True}

    result = indexer.index_folder(path, force=force, run_ocr=run_ocr, limit=limit, progress=_progress)
    return result


@_guard
def _eye_index_status(params: dict[str, Any]) -> dict[str, Any]:
    conn = db.connect()
    stats = db.stats(conn)
    conn.close()
    embedder = embeddings.get_embedder()
    with _JOB_LOCK:
        job = dict(_JOB)
    return {
        "ok": True,
        "library_path": config.library_path(),
        "stats": stats,
        "job": job,
        "embedding": {
            "configured": config.embedding_backend(),
            "loaded_backend": embedder.backend,
            "semantic": embedder.semantic,
            "note": "CLIP loads lazily on the first image. If it fails, the fallback visual vector is used.",
        },
        "camera": camera.status(),
    }


@_guard
def _eye_search(params: dict[str, Any]) -> dict[str, Any]:
    return search.search(
        _str(params, "query"),
        limit=_int(params, "limit", config.max_results()),
        kind=_str(params, "kind") or None,
        since=_str(params, "since") or None,
        until=_str(params, "until") or None,
        folder=_str(params, "folder") or None,
        tags=_tags(params),
        mode=_str(params, "mode", "auto") or "auto",
    )


@_guard
def _eye_album(params: dict[str, Any]) -> dict[str, Any]:
    return actions.make_album(
        name=_str(params, "name"),
        query=_str(params, "query"),
        limit=_int(params, "limit", 200) or 200,
        copy_files=_bool(params, "copy"),
    )


@_guard
def _eye_duplicates(params: dict[str, Any]) -> dict[str, Any]:
    return search.duplicate_groups(
        threshold=_int(params, "threshold", 6) or 6,
        limit=_int(params, "limit", 20) or 20,
        since=_str(params, "since") or None,
        until=_str(params, "until") or None,
    )


@_guard
def _eye_best(params: dict[str, Any]) -> dict[str, Any]:
    ids = params.get("media_ids")
    media_ids = [int(value) for value in ids] if isinstance(ids, list) else None
    return search.best_shots(
        query=_str(params, "query"),
        media_ids=media_ids,
        limit=_int(params, "limit", 10) or 10,
    )


@_guard
def _eye_receipts(params: dict[str, Any]) -> dict[str, Any]:
    return actions.receipt_report(
        since=_str(params, "since") or None,
        until=_str(params, "until") or None,
        fmt=_str(params, "format", "pdf") or "pdf",
    )


@_guard
def _eye_timeline(params: dict[str, Any]) -> dict[str, Any]:
    return search.timeline(
        since=_str(params, "since") or None,
        until=_str(params, "until") or None,
        bucket=_str(params, "bucket", "month") or "month",
        limit=_int(params, "limit", 24) or 24,
    )


@_guard
def _eye_stats(params: dict[str, Any]) -> dict[str, Any]:
    conn = db.connect()
    stats = db.stats(conn)
    conn.close()
    return {"ok": True, "stats": stats, "camera": camera.status()}


@_guard
def _eye_forget(params: dict[str, Any]) -> dict[str, Any]:
    return actions.forget(
        media_id=_int(params, "media_id"),
        path=_str(params, "path") or None,
        query=_str(params, "query"),
        all_items=_bool(params, "all"),
        confirm=_bool(params, "confirm"),
    )


def _camera_disabled() -> dict[str, Any] | None:
    if config.camera_enabled():
        return None
    return {
        "ok": False,
        "error": "camera tools are disabled. Set camera_enabled=true in the plugin settings "
        "or HERMES_EYE_MEMORY_CAMERA_ENABLED=true to allow webcam access.",
    }


@_guard
def _eye_capture(params: dict[str, Any]) -> dict[str, Any]:
    disabled = _camera_disabled()
    if disabled:
        return disabled
    return camera.capture(
        index=_int(params, "camera_index"),
        remember=_bool(params, "remember", False),
        note=_str(params, "note"),
        tags=_tags(params) or None,
    )


@_guard
def _eye_look(params: dict[str, Any]) -> dict[str, Any]:
    disabled = _camera_disabled()
    if disabled:
        return disabled
    return camera.look(
        index=_int(params, "camera_index"),
        remember=_bool(params, "remember", False),
        run_ocr=_bool(params, "ocr", True),
    )


@_guard
def _eye_read(params: dict[str, Any]) -> dict[str, Any]:
    disabled = _camera_disabled()
    if disabled:
        return disabled
    return camera.read(
        index=_int(params, "camera_index"),
        remember=_bool(params, "remember", False),
    )


@_guard
def _eye_find(params: dict[str, Any]) -> dict[str, Any]:
    disabled = _camera_disabled()
    if disabled:
        return disabled
    description = _str(params, "description")
    if not description:
        return {"ok": False, "error": "description is required"}
    return camera.find(
        description=description,
        index=_int(params, "camera_index"),
        limit=_int(params, "limit", 10) or 10,
    )


@_guard
def _eye_remember(params: dict[str, Any]) -> dict[str, Any]:
    return actions.remember(
        note=_str(params, "note"),
        caption=_str(params, "caption"),
        tags=_tags(params),
        media_id=_int(params, "media_id"),
        path=_str(params, "path") or None,
        query=_str(params, "query"),
        apply_all=_bool(params, "all"),
    )


@_guard
def _eye_recall(params: dict[str, Any]) -> dict[str, Any]:
    return search.search(
        _str(params, "query"),
        limit=_int(params, "limit", config.max_results()),
        kind=_str(params, "kind") or None,
        since=_str(params, "since") or None,
        until=_str(params, "until") or None,
    )


_HANDLERS: dict[str, Callable[..., str]] = {
    "eye_index": _eye_index,
    "eye_index_status": _eye_index_status,
    "eye_search": _eye_search,
    "eye_album": _eye_album,
    "eye_duplicates": _eye_duplicates,
    "eye_best": _eye_best,
    "eye_receipts": _eye_receipts,
    "eye_timeline": _eye_timeline,
    "eye_stats": _eye_stats,
    "eye_forget": _eye_forget,
    "eye_capture": _eye_capture,
    "eye_look": _eye_look,
    "eye_read": _eye_read,
    "eye_find": _eye_find,
    "eye_remember": _eye_remember,
    "eye_recall": _eye_recall,
}


def tool_specs() -> list[tuple[dict[str, Any], Callable[..., str]]]:
    return [(schema, _HANDLERS[schema["name"]]) for schema in schemas.all_schemas()]
