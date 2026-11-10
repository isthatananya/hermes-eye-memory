"""Folder indexing and single-image ingestion."""

from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageOps

from . import config, db, exif, ocr
from .embeddings import Embedder, get_embedder
from .hashing import color_caption, dhash, exposure_penalty, sharpness

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".heic",
    ".heif",
}
MAX_FILE_BYTES = 80 * 1024 * 1024
THUMB_SIZE = (360, 360)

try:  # Optional HEIC support when the extra is installed
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception:  # pragma: no cover - optional dependency
    pass


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def _thumb_name(path: Path) -> str:
    digest = hashlib.sha1(str(path.resolve()).encode("utf-8", "surrogatepass")).hexdigest()[:20]
    return digest + ".jpg"


def _save_thumb(img: Image.Image, path: Path) -> str:
    thumb = img.convert("RGB").copy()
    thumb.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
    target = db.thumbs_dir() / _thumb_name(path)
    thumb.save(target, format="JPEG", quality=82, optimize=True)
    return str(target)


def _quality(img: Image.Image) -> float:
    sharp = sharpness(img)
    penalty = exposure_penalty(img)
    normalized = min(1.0, sharp / 800.0)
    return round(max(0.0, normalized * (1.0 - penalty)), 4)


def _file_time(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def iter_images(root: Path) -> list[Path]:
    resolved_root = root.resolve()
    data_root = db.data_dir().resolve()
    results: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(resolved_root):
        current = Path(dirpath)
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not name.startswith(".")
            and not _is_within(current / name, data_root)
            and name not in {"node_modules", "__pycache__", ".git", ".venv", "venv"}
        )
        for filename in sorted(filenames):
            if filename.startswith("."):
                continue
            path = current / filename
            if is_supported(path):
                results.append(path)
    return results


def index_file(
    path: Path,
    *,
    conn=None,
    embedder: Embedder | None = None,
    force: bool = False,
    run_ocr: bool | None = None,
    source: str = "folder",
    kind: str = "photo",
    note: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Index one image. Returns a small status dictionary."""
    path = Path(path).expanduser().resolve()
    own_conn = conn is None
    conn = conn or db.connect()
    embedder = embedder or get_embedder()
    if run_ocr is None:
        run_ocr = config.ocr_enabled()

    def finish(payload: dict[str, Any]) -> dict[str, Any]:
        if own_conn:
            conn.close()
        return payload

    try:
        stat = path.stat()
    except OSError as exc:
        return finish({"status": "error", "path": str(path), "error": str(exc)})

    if stat.st_size > MAX_FILE_BYTES:
        return finish({"status": "skipped", "path": str(path), "reason": "too large"})

    existing = db.get_by_path(conn, str(path))
    if (
        existing
        and not force
        and existing["size"] == stat.st_size
        and abs(float(existing["mtime"] or 0) - stat.st_mtime) < 1.0
        and existing["embedding"] is not None
    ):
        return finish({"status": "skipped", "path": str(path), "id": int(existing["id"]), "reason": "unchanged"})

    started = time.time()
    try:
        with Image.open(path) as raw:
            img = ImageOps.exif_transpose(raw)
            img.load()
            width, height = img.size
            info = exif.read_exif(raw)
            phash = dhash(img)
            vector = embedder.embed_image(img)
            quality = _quality(img)
            thumb_path = _save_thumb(img, path)
            visual_caption = color_caption(img, count=5)
            ocr_text = ""
            auto_tags: list[str] = []
            stem = path.stem.lower()
            if "receipt" in stem:
                auto_tags.append("receipt")
            if "screenshot" in stem:
                auto_tags.append("screenshot")
            if run_ocr:
                try:
                    result = ocr.ocr_image(img)
                    ocr_text = result.get("text", "") or ""
                    if ocr.looks_like_receipt(ocr_text):
                        auto_tags.append("receipt")
                except Exception as exc:
                    logger.warning("OCR skipped for %s: %s", path, exc)
    except Exception as exc:
        logger.warning("failed to index %s: %s", path, exc)
        return finish({"status": "error", "path": str(path), "error": str(exc)})

    existing_tags = db.tags_list(existing) if existing else []
    merged_tags: list[str] = []
    for tag in existing_tags + (tags or []) + auto_tags:
        tag = str(tag).strip()
        if tag and tag not in merged_tags:
            merged_tags.append(tag)

    media_id = db.upsert_media(
        conn,
        path=str(path),
        source=source,
        kind=kind,
        file_name=path.name,
        ext=path.suffix.lower(),
        size=stat.st_size,
        mtime=stat.st_mtime,
        width=width,
        height=height,
        taken_at=info.get("taken_at"),
        gps_lat=info.get("gps_lat"),
        gps_lon=info.get("gps_lon"),
        camera=info.get("camera"),
        quality=quality,
        ocr_text=ocr_text,
        caption=(existing["caption"] if existing and existing["caption"] else visual_caption),
        note=note or (existing["note"] if existing else "") or "",
        tags=merged_tags,
        phash=phash,
        embedding=vector.tobytes(),
        embedding_dim=int(vector.shape[0]),
        embedding_backend=embedder.backend if embedder.semantic else "fallback",
        thumb_path=thumb_path,
        indexed_at=db.now_iso(),
    )

    return finish({
        "status": "indexed",
        "id": media_id,
        "path": str(path),
        "width": width,
        "height": height,
        "taken_at": info.get("taken_at") or _file_time(path),
        "ocr": bool(ocr_text),
        "tags": merged_tags,
        "quality": quality,
        "seconds": round(time.time() - started, 3),
    })


def index_folder(
    root: str | Path | None = None,
    *,
    force: bool = False,
    run_ocr: bool | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    target = Path(root or config.library_path()).expanduser()
    if not target.exists():
        return {"ok": False, "error": f"library path does not exist: {target}"}
    if not target.is_dir():
        return {"ok": False, "error": f"library path is not a folder: {target}"}

    started = time.time()
    files = iter_images(target)
    if limit:
        files = files[: int(limit)]

    conn = db.connect()
    embedder = get_embedder()
    counts = {"indexed": 0, "skipped": 0, "error": 0}
    errors: list[dict[str, str]] = []
    total = len(files)

    for index, path in enumerate(files, start=1):
        try:
            result = index_file(
                path,
                conn=conn,
                embedder=embedder,
                force=force,
                run_ocr=run_ocr,
            )
            status = result.get("status", "error")
            counts[status] = counts.get(status, 0) + 1
            if status == "error" and len(errors) < 20:
                errors.append({"path": result.get("path", ""), "error": result.get("error", "")})
        except Exception as exc:
            counts["error"] += 1
            if len(errors) < 20:
                errors.append({"path": str(path), "error": str(exc)})

        if progress and (index == total or index % 10 == 0):
            progress(
                {
                    "done": index,
                    "total": total,
                    "current": str(path),
                    "counts": dict(counts),
                }
            )

    stats = db.stats(conn)
    conn.close()
    return {
        "ok": True,
        "library": str(target.resolve()),
        "files": total,
        "counts": counts,
        "errors": errors,
        "seconds": round(time.time() - started, 2),
        "backend": embedder.backend if embedder.semantic else "fallback",
        "stats": stats,
    }


def remove_missing(conn=None) -> dict[str, Any]:
    own_conn = conn is None
    conn = conn or db.connect()
    removed = 0
    for row in db.all_media(conn):
        if not Path(row["path"]).exists():
            db.delete_media(conn, int(row["id"]))
            removed += 1
    if own_conn:
        conn.close()
    return {"ok": True, "removed": removed}
