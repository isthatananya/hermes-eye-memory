"""Tool schemas exposed to Hermes."""

from __future__ import annotations

from typing import Any


def _schema(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": False,
        },
    }


_DATE = {"type": "string", "description": "ISO date or datetime, for example 2024-05-01."}
_LIMIT = {"type": "integer", "minimum": 1, "maximum": 200, "description": "Maximum results to return."}
_CAMERA = {"type": "integer", "minimum": 0, "maximum": 8, "description": "Desktop camera index. Defaults to the plugin setting."}

SCHEMAS: list[dict[str, Any]] = [
    _schema(
        "eye_index",
        "Index a folder of photos into the local visual memory. Extracts EXIF, perceptual hashes, "
        "CLIP or fallback embeddings, thumbnails, and optional OCR. Safe to re-run: unchanged files are skipped.",
        {
            "path": {"type": "string", "description": "Folder to index. Defaults to the configured library_path."},
            "force": {"type": "boolean", "description": "Re-index files even when size and mtime are unchanged."},
            "ocr": {"type": "boolean", "description": "Override OCR for this run. Defaults to the plugin setting."},
            "limit": {"type": "integer", "minimum": 1, "description": "Stop after this many files. Useful for a quick demo."},
            "background": {"type": "boolean", "description": "Run in the background and return immediately. Poll eye_index_status."},
        },
    ),
    _schema(
        "eye_index_status",
        "Show index health: photo and frame counts, OCR coverage, embedding coverage, library dates, "
        "data directory, and the state of any background indexing job.",
        {},
    ),
    _schema(
        "eye_search",
        "Search the photo library with natural language, OCR text, tags, and date filters. "
        "Supports filters such as year:2024, month:2024-05, tag:receipt, is:receipt, has:ocr, has:gps, kind:photo.",
        {
            "query": {"type": "string", "description": "Natural language or keyword query. Empty lists recent media."},
            "limit": _LIMIT,
            "kind": {"type": "string", "enum": ["any", "photo", "frame"], "description": "Restrict to photos or camera frames."},
            "since": _DATE,
            "until": _DATE,
            "folder": {"type": "string", "description": "Only media whose path is inside this folder."},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Require all of these tags."},
            "mode": {
                "type": "string",
                "enum": ["auto", "text", "visual"],
                "description": "auto uses lexical plus visual; text uses OCR and notes only; visual uses image similarity only.",
            },
        },
    ),
    _schema(
        "eye_album",
        "Create a named album from a search or from recent photos. Writes a manifest.json and can copy files "
        "into the album folder. Non-destructive.",
        {
            "name": {"type": "string", "description": "Album name. Defaults to a timestamped name."},
            "query": {"type": "string", "description": "Search query used to select photos. Empty means recent photos."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "description": "Maximum photos in the album."},
            "copy": {"type": "boolean", "description": "Copy image files into the album folder. Defaults to false."},
        },
    ),
    _schema(
        "eye_duplicates",
        "Find near-duplicate and burst photos using perceptual hashes. Returns groups with a suggested best shot "
        "chosen by sharpness, exposure, and resolution.",
        {
            "threshold": {"type": "integer", "minimum": 0, "maximum": 32, "description": "Hamming distance threshold. 6 is strict, 12 is loose."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Maximum duplicate groups to return."},
            "since": _DATE,
            "until": _DATE,
        },
    ),
    _schema(
        "eye_best",
        "Rank photos by local quality scores (sharpness, exposure, resolution) or pick the best shot from a query.",
        {
            "query": {"type": "string", "description": "Optional query to narrow the candidate set."},
            "media_ids": {"type": "array", "items": {"type": "integer"}, "description": "Optional explicit media ids to rank."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Number of best shots to return."},
        },
    ),
    _schema(
        "eye_receipts",
        "Find receipt photos, extract merchant, date, and amount with OCR, and write a PDF, Markdown, or CSV report "
        "under the plugin data directory. Runs fully offline.",
        {
            "since": _DATE,
            "until": _DATE,
            "format": {"type": "string", "enum": ["pdf", "markdown", "csv"], "description": "Report format. Defaults to pdf."},
        },
    ),
    _schema(
        "eye_timeline",
        "Summarize the library by day, month, or year with counts and example photos.",
        {
            "since": _DATE,
            "until": _DATE,
            "bucket": {"type": "string", "enum": ["day", "month", "year"], "description": "Timeline bucket size. Defaults to month."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200, "description": "Maximum buckets to return."},
        },
    ),
    _schema(
        "eye_stats",
        "Return library statistics: totals, OCR and embedding coverage, albums, bytes, date range, and data directory.",
        {},
    ),
    _schema(
        "eye_forget",
        "Remove media from the local index. Original files are never deleted by this tool. Query-based removal is "
        "capped; use media_id or path for a narrower removal. Refuses to remove the whole index unless confirm is true.",
        {
            "media_id": {"type": "integer", "description": "Remove one media id from the index."},
            "path": {"type": "string", "description": "Remove one exact indexed path from the index."},
            "query": {"type": "string", "description": "Remove matching index entries, up to the configured cap."},
            "all": {"type": "boolean", "description": "Remove every indexed item. Requires confirm=true."},
            "confirm": {"type": "boolean", "description": "Required for all=true."},
        },
    ),
    _schema(
        "eye_capture",
        "Capture a photo from the desktop webcam. Webcam access is disabled by default; enable camera_enabled first. "
        "The frame is not stored unless remember=true.",
        {
            "camera_index": _CAMERA,
            "remember": {"type": "boolean", "description": "Index the frame into visual memory. Defaults to false."},
            "note": {"type": "string", "description": "Optional note stored with the frame."},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags for the frame."},
        },
    ),
    _schema(
        "eye_look",
        "Take a quick look through the webcam. Webcam access is disabled by default; enable camera_enabled first. "
        "Returns size, dominant colors, and OCR text. The frame is not stored unless remember=true.",
        {
            "camera_index": _CAMERA,
            "remember": {"type": "boolean", "description": "Store the frame in visual memory. Defaults to false."},
            "ocr": {"type": "boolean", "description": "Run OCR on the frame. Defaults to true."},
        },
    ),
    _schema(
        "eye_read",
        "Point the webcam at text or a receipt and read it with local OCR. Webcam access is disabled by default; "
        "enable camera_enabled first. The frame is not stored unless remember=true.",
        {
            "camera_index": _CAMERA,
            "remember": {"type": "boolean", "description": "Store the frame and OCR text. Defaults to false."},
        },
    ),
    _schema(
        "eye_find",
        "Capture the current webcam view and find visually similar photos already in the library. Webcam access is "
        "disabled by default; enable camera_enabled first.",
        {
            "description": {"type": "string", "description": "What you are looking for, for logging and context."},
            "camera_index": _CAMERA,
            "limit": _LIMIT,
        },
        ["description"],
    ),
    _schema(
        "eye_remember",
        "Attach a note, caption, or tags to one photo, an exact path, or the first match of a query.",
        {
            "note": {"type": "string", "description": "Note to append."},
            "caption": {"type": "string", "description": "Caption to set."},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags to merge into the item."},
            "media_id": {"type": "integer", "description": "Target media id."},
            "path": {"type": "string", "description": "Target exact file path."},
            "query": {"type": "string", "description": "Use the first search result as the target."},
            "all": {"type": "boolean", "description": "Apply to every search result instead of only the first."},
        },
    ),
    _schema(
        "eye_recall",
        "Recall what the camera saw earlier. Searches camera frames and photos by text, OCR, tags, and time.",
        {
            "query": {"type": "string", "description": "What to recall, for example a receipt or a red mug."},
            "limit": _LIMIT,
            "since": _DATE,
            "until": _DATE,
            "kind": {"type": "string", "enum": ["any", "photo", "frame"], "description": "Restrict to photos or camera frames."},
        },
    ),
]


def all_schemas() -> list[dict[str, Any]]:
    return list(SCHEMAS)
