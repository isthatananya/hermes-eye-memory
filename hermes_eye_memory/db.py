"""SQLite storage for the visual memory index."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PLUGIN_ID = "hermes-eye-memory"

try:  # Hermes host storage API
    from plugins.plugin_storage import plugin_data_dir, plugin_db
except Exception:  # pragma: no cover - tests and standalone CLI
    plugin_data_dir = None
    plugin_db = None

_FTS_READY: bool | None = None

MEDIA_COLUMNS = (
    "path",
    "source",
    "kind",
    "file_name",
    "ext",
    "size",
    "mtime",
    "width",
    "height",
    "taken_at",
    "gps_lat",
    "gps_lon",
    "camera",
    "quality",
    "ocr_text",
    "caption",
    "note",
    "tags",
    "phash",
    "embedding",
    "embedding_dim",
    "embedding_backend",
    "thumb_path",
    "indexed_at",
    "updated_at",
)

CORE_SCHEMA = """
CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL DEFAULT 'folder',
    kind TEXT NOT NULL DEFAULT 'photo',
    file_name TEXT,
    ext TEXT,
    size INTEGER,
    mtime REAL,
    width INTEGER,
    height INTEGER,
    taken_at TEXT,
    gps_lat REAL,
    gps_lon REAL,
    camera TEXT,
    quality REAL,
    ocr_text TEXT DEFAULT '',
    caption TEXT DEFAULT '',
    note TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    phash BLOB,
    embedding BLOB,
    embedding_dim INTEGER,
    embedding_backend TEXT,
    thumb_path TEXT,
    indexed_at TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_media_kind ON media(kind);
CREATE INDEX IF NOT EXISTS idx_media_taken_at ON media(taken_at);
CREATE INDEX IF NOT EXISTS idx_media_size ON media(size);

CREATE TABLE IF NOT EXISTS albums (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    query TEXT NOT NULL DEFAULT '',
    manifest_path TEXT,
    item_count INTEGER DEFAULT 0,
    created_at TEXT
);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS media_fts USING fts5(
    ocr_text,
    caption,
    note,
    tags,
    content=''
);
"""


def data_dir() -> Path:
    env = os.environ.get("HERMES_EYE_MEMORY_DATA")
    if env:
        path = Path(env)
    elif plugin_data_dir is not None:
        path = Path(plugin_data_dir(PLUGIN_ID))
    else:
        home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        path = home / "plugin-data" / PLUGIN_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


def thumbs_dir() -> Path:
    path = data_dir() / "thumbs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def frames_dir() -> Path:
    path = data_dir() / "frames"
    path.mkdir(parents=True, exist_ok=True)
    return path


def albums_dir() -> Path:
    path = data_dir() / "albums"
    path.mkdir(parents=True, exist_ok=True)
    return path


def models_dir() -> Path:
    path = data_dir() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def connect() -> sqlite3.Connection:
    if plugin_db is not None:
        conn = plugin_db(PLUGIN_ID)
    else:
        conn = sqlite3.connect(data_dir() / "data.db", timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.DatabaseError:
        pass
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    global _FTS_READY
    conn.executescript(CORE_SCHEMA)
    if _FTS_READY is None:
        try:
            conn.executescript(FTS_SCHEMA)
            _FTS_READY = True
        except sqlite3.OperationalError:
            _FTS_READY = False
    elif _FTS_READY:
        try:
            conn.executescript(FTS_SCHEMA)
        except sqlite3.OperationalError:
            _FTS_READY = False
    conn.commit()


def fts_ready() -> bool:
    return bool(_FTS_READY)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _tags_text(tags: Any) -> str:
    if isinstance(tags, (list, tuple)):
        return " ".join(str(t) for t in tags)
    if isinstance(tags, str):
        try:
            parsed = json.loads(tags)
            if isinstance(parsed, list):
                return " ".join(str(t) for t in parsed)
        except (ValueError, TypeError):
            pass
        return tags
    return ""


def _sync_fts(conn: sqlite3.Connection, media_id: int, ocr_text: str, caption: str, note: str, tags: Any) -> None:
    if not _FTS_READY:
        return
    try:
        conn.execute("DELETE FROM media_fts WHERE rowid = ?", (media_id,))
        conn.execute(
            "INSERT INTO media_fts(rowid, ocr_text, caption, note, tags) VALUES (?, ?, ?, ?, ?)",
            (media_id, ocr_text or "", caption or "", note or "", _tags_text(tags)),
        )
    except sqlite3.OperationalError:
        pass


def upsert_media(conn: sqlite3.Connection, **fields: Any) -> int:
    unknown = set(fields) - set(MEDIA_COLUMNS)
    if unknown:
        raise ValueError(f"unknown media columns: {sorted(unknown)}")

    fields["updated_at"] = fields.get("updated_at") or now_iso()
    if isinstance(fields.get("tags"), (list, tuple)):
        fields["tags"] = json.dumps(list(fields["tags"]))
    elif fields.get("tags") is None:
        fields["tags"] = "[]"

    row = conn.execute("SELECT * FROM media WHERE path = ?", (fields["path"],)).fetchone()
    if row:
        media_id = int(row["id"])
        assignments = ", ".join(f"{key} = ?" for key in fields)
        conn.execute(
            f"UPDATE media SET {assignments} WHERE id = ?",
            (*fields.values(), media_id),
        )
        fts_ocr = fields.get("ocr_text", row["ocr_text"])
        fts_caption = fields.get("caption", row["caption"])
        fts_note = fields.get("note", row["note"])
        fts_tags = fields.get("tags", row["tags"])
    else:
        fields.setdefault("indexed_at", now_iso())
        columns = ", ".join(fields)
        placeholders = ", ".join("?" for _ in fields)
        cur = conn.execute(
            f"INSERT INTO media ({columns}) VALUES ({placeholders})",
            tuple(fields.values()),
        )
        media_id = int(cur.lastrowid)
        fts_ocr = fields.get("ocr_text")
        fts_caption = fields.get("caption")
        fts_note = fields.get("note")
        fts_tags = fields.get("tags")

    _sync_fts(
        conn,
        media_id,
        str(fts_ocr or ""),
        str(fts_caption or ""),
        str(fts_note or ""),
        fts_tags or "[]",
    )
    conn.commit()
    return media_id


def get_media(conn: sqlite3.Connection, media_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()


def get_by_path(conn: sqlite3.Connection, path: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM media WHERE path = ?", (path,)).fetchone()


def delete_media(conn: sqlite3.Connection, media_id: int) -> bool:
    row = get_media(conn, media_id)
    if not row:
        return False
    conn.execute("DELETE FROM media WHERE id = ?", (media_id,))
    if _FTS_READY:
        try:
            conn.execute("DELETE FROM media_fts WHERE rowid = ?", (media_id,))
        except sqlite3.OperationalError:
            pass
    conn.commit()
    return True


def _date_filter(column: str, since: str | None, until: str | None) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if since:
        clauses.append(f"substr(COALESCE({column}, datetime(mtime, 'unixepoch')), 1, 10) >= ?")
        params.append(since[:10])
    if until:
        clauses.append(f"substr(COALESCE({column}, datetime(mtime, 'unixepoch')), 1, 10) <= ?")
        params.append(until[:10])
    return (" AND ".join(clauses), params)


def all_media(
    conn: sqlite3.Connection,
    *,
    kind: str | None = None,
    since: str | None = None,
    until: str | None = None,
    folder: str | None = None,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    clauses: list[str] = []
    params: list[Any] = []
    if kind and kind != "any":
        clauses.append("kind = ?")
        params.append(kind)
    date_sql, date_params = _date_filter("taken_at", since, until)
    if date_sql:
        clauses.append(date_sql)
        params.extend(date_params)
    if folder:
        clauses.append("path LIKE ?")
        params.append(str(Path(folder).expanduser().resolve()) + "%")
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM media{where} ORDER BY COALESCE(taken_at, datetime(mtime, 'unixepoch')) DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    return list(conn.execute(sql, params).fetchall())


def fts_search(conn: sqlite3.Connection, query: str, limit: int = 300) -> dict[int, float]:
    if not _FTS_READY or not query.strip():
        return {}
    tokens = re.findall(r"[A-Za-z0-9_]+", query)
    if not tokens:
        return {}
    match = " OR ".join(f'"{token}"' for token in tokens[:12])
    try:
        rows = conn.execute(
            "SELECT rowid, bm25(media_fts) AS rank FROM media_fts WHERE media_fts MATCH ? ORDER BY rank LIMIT ?",
            (match, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    result: dict[int, float] = {}
    for row in rows:
        result[int(row["rowid"])] = float(row["rank"])
    return result


def like_search(conn: sqlite3.Connection, query: str, limit: int = 300) -> list[int]:
    tokens = re.findall(r"[A-Za-z0-9_]+", query or "")[:8]
    if not tokens:
        return []
    clauses = []
    params: list[Any] = []
    for token in tokens:
        pattern = f"%{token}%"
        clauses.append(
            "(ocr_text LIKE ? OR caption LIKE ? OR note LIKE ? OR tags LIKE ? OR file_name LIKE ?)"
        )
        params.extend([pattern] * 5)
    sql = "SELECT id FROM media WHERE " + " OR ".join(clauses) + " LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [int(row["id"]) for row in rows]


def tags_list(row: sqlite3.Row) -> list[str]:
    raw = row["tags"] if "tags" in row.keys() else "[]"
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return [str(t) for t in parsed] if isinstance(parsed, list) else []
    except (ValueError, TypeError):
        return []


def stats(conn: sqlite3.Connection) -> dict[str, Any]:
    def scalar(sql: str, params: Iterable[Any] = ()) -> Any:
        row = conn.execute(sql, tuple(params)).fetchone()
        return row[0] if row else None

    total = int(scalar("SELECT COUNT(*) FROM media") or 0)
    photos = int(scalar("SELECT COUNT(*) FROM media WHERE kind = 'photo'") or 0)
    frames = int(scalar("SELECT COUNT(*) FROM media WHERE kind = 'frame'") or 0)
    with_ocr = int(scalar("SELECT COUNT(*) FROM media WHERE length(COALESCE(ocr_text, '')) > 0") or 0)
    with_embedding = int(scalar("SELECT COUNT(*) FROM media WHERE embedding IS NOT NULL") or 0)
    albums = int(scalar("SELECT COUNT(*) FROM albums") or 0)
    size = int(scalar("SELECT COALESCE(SUM(size), 0) FROM media") or 0)
    first = scalar("SELECT MIN(COALESCE(taken_at, datetime(mtime, 'unixepoch'))) FROM media")
    last = scalar("SELECT MAX(COALESCE(taken_at, datetime(mtime, 'unixepoch'))) FROM media")
    return {
        "total": total,
        "photos": photos,
        "frames": frames,
        "with_ocr": with_ocr,
        "with_embedding": with_embedding,
        "albums": albums,
        "bytes": size,
        "first": first,
        "last": last,
        "data_dir": str(data_dir()),
        "fts": fts_ready(),
    }


def record_album(conn: sqlite3.Connection, name: str, query: str, manifest_path: str, item_count: int) -> int:
    cur = conn.execute(
        "INSERT INTO albums(name, query, manifest_path, item_count, created_at) VALUES (?, ?, ?, ?, ?)",
        (name, query, manifest_path, item_count, now_iso()),
    )
    conn.commit()
    return int(cur.lastrowid)


def unix_now() -> float:
    return time.time()
