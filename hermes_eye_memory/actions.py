"""Library mutations: albums, receipt reports, notes, and deletion."""

from __future__ import annotations

import csv
import json
import logging
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import db, ocr, search

logger = logging.getLogger(__name__)


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", (value or "").strip()).strip("-._")
    return cleaned[:80] or "album"


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def make_album(
    *,
    name: str = "",
    query: str = "",
    limit: int = 200,
    copy_files: bool = False,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    own_conn = conn is None
    conn = conn or db.connect()
    if query:
        found = search.search(query, limit=limit, conn=conn)
        results = found["results"]
    else:
        results = [
            {
                "id": int(row["id"]),
                "path": row["path"],
                "taken_at": row["taken_at"],
                "tags": db.tags_list(row),
                "score": 1.0,
            }
            for row in db.all_media(conn, limit=limit)
        ]

    if not results:
        if own_conn:
            conn.close()
        return {"ok": False, "error": "no photos matched, album not created"}

    album_name = name.strip() or f"album-{_timestamp()}"
    slug = _slug(album_name)
    target = db.albums_dir() / slug
    if target.exists():
        slug = f"{slug}-{_timestamp()}"
        target = db.albums_dir() / slug
    target.mkdir(parents=True, exist_ok=True)

    copied = 0
    items = []
    for item in results:
        entry = {
            "id": item["id"],
            "path": item["path"],
            "taken_at": item.get("taken_at"),
            "tags": item.get("tags") or [],
            "score": item.get("score"),
        }
        if copy_files:
            source = Path(item["path"])
            if source.exists():
                destination = target / f"{item['id']:06d}-{source.name}"
                try:
                    shutil.copy2(source, destination)
                    entry["copy"] = str(destination)
                    copied += 1
                except OSError as exc:
                    entry["copy_error"] = str(exc)
        items.append(entry)

    manifest = {
        "name": album_name,
        "query": query,
        "created_at": db.now_iso(),
        "count": len(items),
        "copied": copied,
        "items": items,
    }
    manifest_path = target / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    album_id = db.record_album(conn, album_name, query, str(manifest_path), len(items))
    if own_conn:
        conn.close()

    return {
        "ok": True,
        "album_id": album_id,
        "name": album_name,
        "query": query,
        "count": len(items),
        "copied": copied,
        "folder": str(target),
        "manifest": str(manifest_path),
    }


def _receipt_rows(conn: sqlite3.Connection, since: str | None, until: str | None) -> list[sqlite3.Row]:
    rows = db.all_media(conn, since=since, until=until)
    selected = []
    for row in rows:
        tags = {tag.lower() for tag in db.tags_list(row)}
        text = row["ocr_text"] or ""
        if "receipt" in tags or ocr.looks_like_receipt(text):
            selected.append(row)
    return selected


def _write_pdf(path: Path, rows: list[dict[str, Any]], total: float) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(str(path), pagesize=letter, title="Receipt report")
    story = [Paragraph("Receipt report", styles["Title"]), Spacer(1, 8)]
    story.append(Paragraph(f"Generated {db.now_iso()} · {len(rows)} receipts · total {total:.2f}", styles["Normal"]))
    story.append(Spacer(1, 12))

    data = [["Date", "Merchant", "Amount", "File"]]
    for row in rows:
        data.append(
            [
                str(row.get("date") or row.get("taken_at") or "")[:10],
                str(row.get("merchant") or "")[:40],
                f"{row['amount']:.2f}" if row.get("amount") is not None else "",
                Path(row["path"]).name[:40],
            ]
        )
    table = Table(data, colWidths=[80, 190, 70, 160], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#222222")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#999999")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
            ]
        )
    )
    story.append(table)
    document.build(story)


def receipt_report(
    *,
    since: str | None = None,
    until: str | None = None,
    fmt: str = "pdf",
    out_path: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    own_conn = conn is None
    conn = conn or db.connect()
    rows = _receipt_rows(conn, since, until)

    records: list[dict[str, Any]] = []
    total = 0.0
    for row in rows:
        fields = ocr.extract_receipt_fields(row["ocr_text"] or "")
        amount = fields.get("amount")
        if amount:
            total += float(amount)
        records.append(
            {
                "id": int(row["id"]),
                "path": row["path"],
                "taken_at": row["taken_at"],
                "date": fields.get("date"),
                "merchant": fields.get("merchant"),
                "amount": amount,
                "text": (row["ocr_text"] or "")[:1000],
            }
        )

    fmt = (fmt or "pdf").lower()
    if fmt not in {"pdf", "md", "markdown", "csv"}:
        fmt = "pdf"
    extension = {"pdf": "pdf", "md": "md", "markdown": "md", "csv": "csv"}[fmt]
    target = Path(out_path).expanduser() if out_path else db.data_dir() / "receipts" / f"receipts-{_timestamp()}.{extension}"
    target.parent.mkdir(parents=True, exist_ok=True)

    used = extension
    if extension == "pdf":
        try:
            _write_pdf(target, records, total)
        except Exception as exc:
            logger.warning("PDF report failed, writing markdown instead: %s", exc)
            target = target.with_suffix(".md")
            used = "md"
            extension = "md"

    if extension == "md":
        lines = [
            "# Receipt report",
            "",
            f"Generated {db.now_iso()} · {len(records)} receipts · total {total:.2f}",
            "",
            "| Date | Merchant | Amount | File |",
            "| --- | --- | --- | --- |",
        ]
        for record in records:
            lines.append(
                f"| {record.get('date') or record.get('taken_at') or ''} | "
                f"{(record.get('merchant') or '').replace('|', '/')} | "
                f"{record['amount'] if record.get('amount') is not None else ''} | "
                f"{Path(record['path']).name} |"
            )
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif extension == "csv":
        with target.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["id", "date", "merchant", "amount", "path", "text"])
            for record in records:
                writer.writerow(
                    [
                        record["id"],
                        record.get("date") or record.get("taken_at"),
                        record.get("merchant"),
                        record.get("amount"),
                        record["path"],
                        record["text"].replace("\n", " "),
                    ]
                )

    if own_conn:
        conn.close()

    return {
        "ok": True,
        "count": len(records),
        "total": round(total, 2),
        "format": used,
        "path": str(target),
        "receipts": [
            {
                "id": record["id"],
                "date": record.get("date") or record.get("taken_at"),
                "merchant": record.get("merchant"),
                "amount": record.get("amount"),
                "path": record["path"],
            }
            for record in records[:50]
        ],
    }


def forget(
    *,
    media_id: int | None = None,
    path: str | None = None,
    query: str = "",
    delete_files: bool = False,
    all_items: bool = False,
    confirm: bool = False,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    own_conn = conn is None
    conn = conn or db.connect()

    targets: list[sqlite3.Row] = []
    if media_id:
        row = db.get_media(conn, int(media_id))
        if row:
            targets.append(row)
    elif path:
        row = db.get_by_path(conn, str(Path(path).expanduser().resolve()))
        if row:
            targets.append(row)
    elif query:
        found = search.search(query, limit=500, conn=conn)
        targets = [row for row in (db.get_media(conn, item["id"]) for item in found["results"]) if row]
    elif all_items:
        if not confirm:
            if own_conn:
                conn.close()
            return {"ok": False, "error": "refusing to delete everything without confirm=true"}
        targets = db.all_media(conn)

    if not targets:
        if own_conn:
            conn.close()
        return {"ok": False, "error": "no matching media found"}

    deleted = 0
    files_removed = 0
    for row in targets:
        if delete_files:
            try:
                Path(row["path"]).unlink(missing_ok=True)
                files_removed += 1
            except OSError:
                pass
        thumb = row["thumb_path"]
        if thumb:
            try:
                Path(thumb).unlink(missing_ok=True)
            except OSError:
                pass
        if db.delete_media(conn, int(row["id"])):
            deleted += 1

    if own_conn:
        conn.close()
    return {"ok": True, "deleted": deleted, "files_removed": files_removed}


def remember(
    *,
    note: str = "",
    caption: str = "",
    tags: Iterable[str] | None = None,
    media_id: int | None = None,
    path: str | None = None,
    query: str = "",
    apply_all: bool = False,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    own_conn = conn is None
    conn = conn or db.connect()

    targets: list[sqlite3.Row] = []
    if media_id:
        row = db.get_media(conn, int(media_id))
        if row:
            targets.append(row)
    elif path:
        row = db.get_by_path(conn, str(Path(path).expanduser().resolve()))
        if row:
            targets.append(row)
    elif query:
        found = search.search(query, limit=20, conn=conn)
        ids = [item["id"] for item in found["results"]]
        if not apply_all:
            ids = ids[:1]
        targets = [row for row in (db.get_media(conn, item_id) for item_id in ids) if row]

    if not targets:
        if own_conn:
            conn.close()
        return {"ok": False, "error": "no matching media found"}

    if not note and not caption and not tags:
        if own_conn:
            conn.close()
        return {"ok": False, "error": "provide note, caption, or tags"}

    updated = []
    for row in targets:
        merged_tags = db.tags_list(row)
        for tag in tags or []:
            tag = str(tag).strip()
            if tag and tag not in merged_tags:
                merged_tags.append(tag)
        old_note = (row["note"] or "").strip()
        new_note = note.strip()
        if new_note:
            new_note = f"{old_note}\n{new_note}" if old_note else new_note
        else:
            new_note = old_note
        db.upsert_media(
            conn,
            path=row["path"],
            note=new_note,
            caption=caption.strip() or (row["caption"] or ""),
            tags=merged_tags,
        )
        updated.append(int(row["id"]))

    if own_conn:
        conn.close()
    return {"ok": True, "updated": updated, "count": len(updated)}
