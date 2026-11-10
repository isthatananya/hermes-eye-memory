"""Hybrid lexical and visual search."""

from __future__ import annotations

import calendar
import re
import sqlite3
from typing import Any, Iterable

import numpy as np

from . import config, db, ocr
from .embeddings import Embedder, get_embedder

_POPCOUNT = np.array([bin(value).count("1") for value in range(256)], dtype=np.uint8)

_TOKEN_RE = re.compile(r"(?:[^\s\"]|\"[^\"]*\")+")
_FILTER_RE = re.compile(r"^(\w+):(.*)$")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def parse_query(query: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {
        "text": "",
        "since": None,
        "until": None,
        "kind": None,
        "folder": None,
        "tags": [],
        "has": [],
        "is": [],
    }
    words: list[str] = []
    for token in _TOKEN_RE.findall(query or ""):
        match = _FILTER_RE.match(token)
        if not match:
            words.append(_unquote(token))
            continue
        key, value = match.group(1).lower(), _unquote(match.group(2))
        if key in {"after", "since"}:
            parsed["since"] = value
        elif key in {"before", "until"}:
            parsed["until"] = value
        elif key == "year":
            if value.isdigit():
                parsed["since"] = f"{value}-01-01"
                parsed["until"] = f"{value}-12-31"
        elif key == "month":
            parsed["since"] = f"{value}-01"
            parts = value.split("-")
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                year, month = int(parts[0]), int(parts[1])
                last_day = calendar.monthrange(year, month)[1]
                parsed["until"] = f"{year:04d}-{month:02d}-{last_day:02d}"
        elif key == "tag":
            parsed["tags"].append(value.lower())
        elif key == "kind":
            parsed["kind"] = value.lower()
        elif key in {"in", "folder"}:
            parsed["folder"] = value
        elif key == "has":
            parsed["has"].append(value.lower())
        elif key == "is":
            parsed["is"].append(value.lower())
        else:
            words.append(token)
    parsed["text"] = " ".join(words).strip()
    return parsed


def _row_tags(row: sqlite3.Row) -> set[str]:
    return {tag.lower() for tag in db.tags_list(row)}


def _passes_filters(row: sqlite3.Row, parsed: dict[str, Any]) -> bool:
    row_tags = _row_tags(row)
    for tag in parsed["tags"]:
        if tag not in row_tags:
            return False
    for flag in parsed["has"]:
        if flag == "ocr" and not (row["ocr_text"] or "").strip():
            return False
        if flag == "gps" and (row["gps_lat"] is None or row["gps_lon"] is None):
            return False
        if flag == "note" and not (row["note"] or "").strip():
            return False
    for flag in parsed["is"]:
        if flag == "receipt":
            if "receipt" not in row_tags and not ocr.looks_like_receipt(row["ocr_text"] or ""):
                return False
        elif flag == "frame" and row["kind"] != "frame":
            return False
        elif flag == "photo" and row["kind"] != "photo":
            return False
    return True


def _cosine(row: sqlite3.Row, vector: np.ndarray | None) -> float:
    if vector is None:
        return 0.0
    raw = row["embedding"]
    if raw is None:
        return 0.0
    try:
        other = np.frombuffer(raw, dtype=np.float32)
    except (TypeError, ValueError):
        return 0.0
    if other.shape != vector.shape:
        return 0.0
    return float(np.dot(other, vector))


def _result(row: sqlite3.Row, score: float, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    ocr_text = row["ocr_text"] or ""
    item = {
        "id": int(row["id"]),
        "path": row["path"],
        "kind": row["kind"],
        "taken_at": row["taken_at"],
        "width": row["width"],
        "height": row["height"],
        "tags": db.tags_list(row),
        "score": round(float(score), 4),
        "ocr": ocr_text[:240] if ocr_text else "",
        "thumb": row["thumb_path"],
    }
    if extra:
        item.update(extra)
    return item


def search(
    query: str,
    *,
    limit: int | None = None,
    kind: str | None = None,
    since: str | None = None,
    until: str | None = None,
    folder: str | None = None,
    tags: Iterable[str] | None = None,
    mode: str = "auto",
    embedder: Embedder | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    limit = int(limit or config.max_results())
    parsed = parse_query(query or "")
    if kind:
        parsed["kind"] = kind
    if since:
        parsed["since"] = since
    if until:
        parsed["until"] = until
    if folder:
        parsed["folder"] = folder
    if tags:
        parsed["tags"].extend(str(tag).lower() for tag in tags)

    own_conn = conn is None
    conn = conn or db.connect()
    embedder = embedder or get_embedder()

    rows = db.all_media(
        conn,
        kind=parsed["kind"],
        since=parsed["since"],
        until=parsed["until"],
        folder=parsed["folder"],
    )
    rows = [row for row in rows if _passes_filters(row, parsed)]

    text = parsed["text"]
    text_vector = embedder.embed_text(text) if text and mode != "text" else None
    semantic = bool(text_vector is not None and embedder.semantic)

    fts = db.fts_search(conn, text) if text and mode != "visual" else {}
    likes = set(db.like_search(conn, text)) if text and mode != "visual" else set()

    if mode == "text":
        text_vector = None

    ranked: list[tuple[float, sqlite3.Row]] = []
    if not text:
        for row in rows:
            ranked.append((1.0, row))
    else:
        for row in rows:
            media_id = int(row["id"])
            lex = 0.0
            if media_id in fts:
                lex = 1.0
            elif media_id in likes:
                lex = 0.6
            elif text.lower() in (row["path"] or "").lower():
                lex = 0.3
            visual = max(0.0, _cosine(row, text_vector)) if text_vector is not None else 0.0
            if semantic:
                score = 0.62 * visual + 0.38 * lex
            else:
                score = 0.72 * lex + 0.28 * visual
            if score > 0.001:
                ranked.append((score, row))

    ranked.sort(key=lambda item: (item[0], item[1]["taken_at"] or ""), reverse=True)
    results = [_result(row, score) for score, row in ranked[:limit]]

    if own_conn:
        conn.close()

    return {
        "ok": True,
        "query": query,
        "parsed": parsed,
        "mode": "visual" if semantic else "lexical+fallback",
        "semantic": semantic,
        "candidates": len(rows),
        "count": len(results),
        "results": results,
    }


def visual_matches(
    vector: np.ndarray,
    rows: Iterable[sqlite3.Row],
    *,
    limit: int = 10,
) -> list[tuple[float, sqlite3.Row]]:
    scored: list[tuple[float, sqlite3.Row]] = []
    for row in rows:
        score = max(0.0, _cosine(row, vector))
        if score > 0.0:
            scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[:limit]


def find_similar(vector: np.ndarray, *, limit: int = 10, conn=None, kind: str | None = None) -> dict[str, Any]:
    own_conn = conn is None
    conn = conn or db.connect()
    rows = db.all_media(conn, kind=kind)
    matches = visual_matches(vector, rows, limit=limit)
    results = [_result(row, score) for score, row in matches]
    if own_conn:
        conn.close()
    return {"ok": True, "count": len(results), "results": results}


def _union_find_groups(hashes: np.ndarray, threshold: int) -> list[list[int]]:
    count = hashes.shape[0]
    parent = list(range(count))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(a: int, b: int) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    for start in range(0, count, 256):
        end = min(count, start + 256)
        block = hashes[start:end]
        for offset in range(end - start):
            index = start + offset
            others = hashes[index + 1 :]
            if others.size == 0:
                continue
            distances = _POPCOUNT[block[offset] ^ others].sum(axis=1)
            for hit in np.nonzero(distances <= threshold)[0]:
                union(index, index + 1 + int(hit))
    groups: dict[int, list[int]] = {}
    for index in range(count):
        groups.setdefault(find(index), []).append(index)
    return [members for members in groups.values() if len(members) > 1]


def duplicate_groups(
    *,
    threshold: int = 6,
    limit: int = 20,
    conn=None,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    own_conn = conn is None
    conn = conn or db.connect()
    rows = [
        row
        for row in db.all_media(conn, since=since, until=until)
        if row["phash"] is not None
    ][:20000]
    if len(rows) < 2:
        if own_conn:
            conn.close()
        return {"ok": True, "groups": [], "count": 0, "scanned": len(rows)}

    hashes = np.stack([np.frombuffer(row["phash"], dtype=np.uint8) for row in rows])
    groups = _union_find_groups(hashes, max(0, min(32, int(threshold))))

    payload = []
    for members in groups:
        items = [rows[index] for index in members]
        best = max(items, key=lambda row: (float(row["quality"] or 0), int(row["size"] or 0)))
        payload.append(
            {
                "size": len(items),
                "best": _result(best, 1.0),
                "items": [_result(row, 1.0) for row in items],
                "bytes": sum(int(row["size"] or 0) for row in items),
            }
        )
    payload.sort(key=lambda group: (group["size"], group["bytes"]), reverse=True)
    if own_conn:
        conn.close()
    return {
        "ok": True,
        "threshold": threshold,
        "scanned": len(rows),
        "count": len(payload[:limit]),
        "groups": payload[:limit],
    }


def best_shots(
    *,
    query: str = "",
    media_ids: Iterable[int] | None = None,
    limit: int = 10,
    conn=None,
) -> dict[str, Any]:
    own_conn = conn is None
    conn = conn or db.connect()
    if media_ids:
        rows = [row for row in (db.get_media(conn, int(i)) for i in media_ids) if row]
    elif query:
        found = search(query, limit=200, conn=conn)
        ids = [item["id"] for item in found["results"]]
        rows = [row for row in (db.get_media(conn, int(i)) for i in ids) if row]
    else:
        rows = db.all_media(conn)
    rows.sort(key=lambda row: (float(row["quality"] or 0), int(row["size"] or 0)), reverse=True)
    results = [_result(row, float(row["quality"] or 0)) for row in rows[:limit]]
    if own_conn:
        conn.close()
    return {"ok": True, "count": len(results), "results": results}


def timeline(
    *,
    since: str | None = None,
    until: str | None = None,
    bucket: str = "month",
    limit: int = 24,
    conn=None,
) -> dict[str, Any]:
    own_conn = conn is None
    conn = conn or db.connect()
    if bucket not in {"day", "month", "year"}:
        bucket = "month"
    width = {"day": 10, "month": 7, "year": 4}[bucket]
    clauses = ["1 = 1"]
    params: list[Any] = []
    if since:
        clauses.append("substr(COALESCE(taken_at, datetime(mtime, 'unixepoch')), 1, 10) >= ?")
        params.append(since[:10])
    if until:
        clauses.append("substr(COALESCE(taken_at, datetime(mtime, 'unixepoch')), 1, 10) <= ?")
        params.append(until[:10])
    sql = (
        "SELECT substr(COALESCE(taken_at, datetime(mtime, 'unixepoch')), 1, ?) AS bucket, "
        "COUNT(*) AS count FROM media WHERE " + " AND ".join(clauses) + " "
        "GROUP BY bucket ORDER BY bucket DESC LIMIT ?"
    )
    rows = conn.execute(sql, (width, *params, int(limit))).fetchall()
    buckets = []
    for row in rows:
        label = row["bucket"]
        examples = conn.execute(
            "SELECT * FROM media WHERE substr(COALESCE(taken_at, datetime(mtime, 'unixepoch')), 1, ?) = ? "
            "ORDER BY quality DESC LIMIT 3",
            (width, label),
        ).fetchall()
        buckets.append(
            {
                "bucket": label,
                "count": int(row["count"]),
                "examples": [_result(item, 1.0) for item in examples],
            }
        )
    if own_conn:
        conn.close()
    return {"ok": True, "bucket": bucket, "buckets": buckets}
