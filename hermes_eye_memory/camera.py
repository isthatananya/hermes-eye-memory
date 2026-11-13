"""Desktop webcam capture and visual recall."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from . import config, db, indexer, ocr, search
from .embeddings import get_embedder
from .hashing import dominant_colors

logger = logging.getLogger(__name__)


def _cv2():
    try:
        import cv2

        return cv2
    except Exception:
        return None


def available() -> bool:
    return _cv2() is not None


def _open(index: int):
    cv2 = _cv2()
    if cv2 is None:
        return None
    backends = []
    if hasattr(cv2, "CAP_DSHOW"):
        backends.append(cv2.CAP_DSHOW)
    backends.append(0)
    for backend in backends:
        try:
            capture = cv2.VideoCapture(index, backend) if backend else cv2.VideoCapture(index)
            if capture is not None and capture.isOpened():
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                return capture
            if capture is not None:
                capture.release()
        except Exception as exc:
            logger.warning("camera backend %s failed: %s", backend, exc)
    return None


def grab_frame(index: int | None = None) -> tuple[np.ndarray | None, str | None]:
    cv2 = _cv2()
    if cv2 is None:
        return None, "opencv-python is not installed. Install it with: pip install opencv-python"
    camera_index = config.camera_index() if index is None else int(index)
    capture = _open(camera_index)
    if capture is None:
        return None, f"could not open camera index {camera_index}. Try a different camera_index."
    frame = None
    try:
        for _ in range(8):
            ok, candidate = capture.read()
            if ok and candidate is not None:
                frame = candidate
    finally:
        capture.release()
    if frame is None:
        return None, "camera opened but returned no frames"
    return frame, None


def _to_pil(frame: np.ndarray) -> Image.Image:
    cv2 = _cv2()
    return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))


def _write_frame(frame: np.ndarray, path: Path) -> bool:
    cv2 = _cv2()
    try:
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        if not ok:
            return False
        path.write_bytes(encoded.tobytes())
        return True
    except Exception as exc:
        logger.warning("failed to write frame: %s", exc)
        return False


def _frame_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return db.frames_dir() / f"frame-{stamp}.jpg"


def _describe(img: Image.Image, text: str) -> str:
    colors = ", ".join(dominant_colors(img, 3))
    parts = [f"{img.width}x{img.height}", f"dominant colors {colors}"]
    if text.strip():
        parts.append("text: " + " ".join(text.split())[:200])
    return "; ".join(parts)


def capture(
    *,
    index: int | None = None,
    remember: bool = False,
    note: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    frame, error = grab_frame(index)
    if error:
        return {"ok": False, "error": error}
    assert frame is not None
    img = _to_pil(frame)
    path = _frame_path()
    if not _write_frame(frame, path):
        return {"ok": False, "error": "failed to save camera frame"}

    if not remember:
        return {
            "ok": True,
            "path": str(path),
            "width": img.width,
            "height": img.height,
            "description": _describe(img, ""),
            "indexed": False,
        }

    result = indexer.index_file(
        path,
        source="camera",
        kind="frame",
        note=note,
        tags=tags or ["camera"],
        run_ocr=config.ocr_enabled(),
    )
    result["description"] = _describe(img, result.get("ocr_text", "") if isinstance(result, dict) else "")
    result["ok"] = result.get("status") != "error"
    result.pop("ocr_text", None)
    return result


def look(*, index: int | None = None, remember: bool = False, run_ocr: bool = True) -> dict[str, Any]:
    frame, error = grab_frame(index)
    if error:
        return {"ok": False, "error": error}
    assert frame is not None
    img = _to_pil(frame)
    text = ""
    lines: list[str] = []
    if run_ocr:
        result = ocr.ocr_image(img)
        text = result.get("text", "") or ""
        lines = result.get("lines", []) or []

    payload: dict[str, Any] = {
        "ok": True,
        "width": img.width,
        "height": img.height,
        "description": _describe(img, text),
        "ocr": text,
        "lines": lines[:20],
        "colors": dominant_colors(img, 4),
    }

    if remember:
        path = _frame_path()
        if _write_frame(frame, path):
            indexed = indexer.index_file(
                path,
                source="camera",
                kind="frame",
                tags=["camera", "look"],
                run_ocr=run_ocr,
            )
            payload["path"] = str(path)
            payload["media_id"] = indexed.get("id")
            payload["indexed"] = indexed.get("status") == "indexed"
        else:
            payload["indexed"] = False
    return payload


def read(*, index: int | None = None, remember: bool = False) -> dict[str, Any]:
    frame, error = grab_frame(index)
    if error:
        return {"ok": False, "error": error}
    assert frame is not None
    img = _to_pil(frame)
    result = ocr.ocr_image(img)
    text = result.get("text", "") or ""
    is_receipt = ocr.looks_like_receipt(text)
    fields = ocr.extract_receipt_fields(text) if is_receipt else {}

    payload: dict[str, Any] = {
        "ok": True,
        "text": text,
        "lines": (result.get("lines", []) or [])[:40],
        "available": result.get("available", True),
        "is_receipt": is_receipt,
        "receipt": fields,
    }

    if remember:
        path = _frame_path()
        if _write_frame(frame, path):
            indexed = indexer.index_file(
                path,
                source="camera",
                kind="frame",
                tags=["camera", "read"] + (["receipt"] if is_receipt else []),
                run_ocr=True,
            )
            payload["path"] = str(path)
            payload["media_id"] = indexed.get("id")
    return payload


def find(*, description: str, index: int | None = None, limit: int = 10) -> dict[str, Any]:
    if not description.strip():
        return {"ok": False, "error": "description is required"}
    frame, error = grab_frame(index)
    if error:
        return {"ok": False, "error": error}
    assert frame is not None
    img = _to_pil(frame)
    embedder = get_embedder()
    vector = embedder.embed_image(img)
    matches = search.find_similar(vector, limit=limit, kind="photo")
    matches["description"] = description
    matches["captured"] = {"width": img.width, "height": img.height, "colors": dominant_colors(img, 3)}
    matches["backend"] = embedder.backend if embedder.semantic else "fallback"
    return matches


def status() -> dict[str, Any]:
    return {
        "enabled": config.camera_enabled(),
        "opencv": available(),
        "camera_index": config.camera_index(),
        "hint": "Camera tools are off by default. Set camera_enabled=true to allow webcam access. "
        "If capture fails, set camera_index to 1 or 2, or close other apps using the webcam.",
    }
