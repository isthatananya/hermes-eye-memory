"""Standalone CLI: ``python -m hermes_eye_memory.cli`` or ``hermes eye-memory``."""

from __future__ import annotations

import argparse
import json
from typing import Any

from . import tools


def _subparsers(parser: argparse.ArgumentParser):
    if hasattr(parser, "add_subparsers"):
        return parser.add_subparsers(dest="command")
    return parser


def setup_argparse(parser: argparse.ArgumentParser) -> None:
    sub = _subparsers(parser)

    index = sub.add_parser("index", help="Index a folder of photos")
    index.add_argument("path", nargs="?", default="", help="Folder to index (defaults to library_path)")
    index.add_argument("--force", action="store_true", help="Re-index unchanged files")
    index.add_argument("--no-ocr", action="store_true", help="Skip OCR")
    index.add_argument("--limit", type=int, default=None, help="Maximum files to index")

    search = sub.add_parser("search", help="Search photos and frames")
    search.add_argument("query", nargs="*", default=[])
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--kind", choices=["any", "photo", "frame"], default="any")
    search.add_argument("--since", default=None)
    search.add_argument("--until", default=None)
    search.add_argument("--folder", default=None)
    search.add_argument("--tags", default="")
    search.add_argument("--mode", choices=["auto", "text", "visual"], default="auto")

    sub.add_parser("stats", help="Show index statistics")
    sub.add_parser("status", help="Show index status and background job")

    timeline = sub.add_parser("timeline", help="Summarize by day, month, or year")
    timeline.add_argument("--since", default=None)
    timeline.add_argument("--until", default=None)
    timeline.add_argument("--bucket", choices=["day", "month", "year"], default="month")
    timeline.add_argument("--limit", type=int, default=24)

    duplicates = sub.add_parser("duplicates", help="Find near-duplicate photos")
    duplicates.add_argument("--threshold", type=int, default=6)
    duplicates.add_argument("--limit", type=int, default=20)
    duplicates.add_argument("--since", default=None)
    duplicates.add_argument("--until", default=None)

    best = sub.add_parser("best", help="Rank photos by quality")
    best.add_argument("query", nargs="*", default=[])
    best.add_argument("--limit", type=int, default=10)

    album = sub.add_parser("album", help="Create an album from a query")
    album.add_argument("query", nargs="*", default=[])
    album.add_argument("--name", default="")
    album.add_argument("--limit", type=int, default=200)
    album.add_argument("--copy", action="store_true", help="Copy image files into the album folder")

    receipts = sub.add_parser("receipts", help="Build a receipt report")
    receipts.add_argument("--since", default=None)
    receipts.add_argument("--until", default=None)
    receipts.add_argument("--format", choices=["pdf", "markdown", "csv"], default="pdf")
    receipts.add_argument("--out", default=None)

    capture = sub.add_parser("capture", help="Capture a webcam frame")
    capture.add_argument("--camera", type=int, default=None)
    capture.add_argument("--note", default="")
    capture.add_argument("--tags", default="")

    look = sub.add_parser("look", help="Look through the webcam")
    look.add_argument("--camera", type=int, default=None)
    look.add_argument("--no-ocr", action="store_true")
    look.add_argument("--no-remember", action="store_true")

    read = sub.add_parser("read", help="Read text or a receipt with the webcam")
    read.add_argument("--camera", type=int, default=None)
    read.add_argument("--no-remember", action="store_true")

    find = sub.add_parser("find", help="Find similar photos from the current camera view")
    find.add_argument("description", nargs="+")
    find.add_argument("--camera", type=int, default=None)
    find.add_argument("--limit", type=int, default=10)

    forget = sub.add_parser("forget", help="Remove items from the index")
    forget.add_argument("--id", type=int, default=None)
    forget.add_argument("--path", default=None)
    forget.add_argument("--query", default="")
    forget.add_argument("--delete-files", action="store_true")
    forget.add_argument("--all", action="store_true")
    forget.add_argument("--yes", action="store_true")

    remember = sub.add_parser("remember", help="Attach a note, caption, or tags")
    remember.add_argument("query", nargs="*", default=[])
    remember.add_argument("--id", type=int, default=None)
    remember.add_argument("--path", default=None)
    remember.add_argument("--note", default="")
    remember.add_argument("--caption", default="")
    remember.add_argument("--tags", default="")
    remember.add_argument("--all", action="store_true")

    recall = sub.add_parser("recall", help="Recall camera frames and photos")
    recall.add_argument("query", nargs="*", default=[])
    recall.add_argument("--limit", type=int, default=20)
    recall.add_argument("--kind", choices=["any", "photo", "frame"], default="any")
    recall.add_argument("--since", default=None)
    recall.add_argument("--until", default=None)

    sub.add_parser("warmup", help="Test the embedding backend")


def _call(name: str, params: dict[str, Any]) -> dict[str, Any]:
    payload = tools._HANDLERS[name](params)
    try:
        return json.loads(payload)
    except (TypeError, ValueError):
        return {"ok": False, "error": str(payload)}


def _print_results(payload: dict[str, Any], limit: int = 20) -> None:
    if not payload.get("ok"):
        print("error:", payload.get("error", "unknown error"))
        return
    results = payload.get("results", [])
    print(f"{payload.get('count', len(results))} result(s) · {payload.get('mode', '')}")
    for item in results[:limit]:
        date = (item.get("taken_at") or "")[:10]
        snippet = (item.get("ocr") or "").replace("\n", " ")[:70]
        print(f"  #{item['id']:<5} {date:<10} {item['score']:<6} {item['path']}")
        if snippet:
            print(f"          {snippet}")


def handle(args, *_extra) -> int:
    command = getattr(args, "command", None)
    if not command:
        print("usage: hermes-eye-memory <index|search|stats|timeline|duplicates|best|album|receipts|capture|look|read|find|forget|remember|recall>")
        return 2

    if command == "index":
        payload = _call(
            "eye_index",
            {
                "path": args.path,
                "force": args.force,
                "ocr": not args.no_ocr,
                "limit": args.limit,
            },
        )
        if payload.get("ok"):
            print(f"indexed {payload.get('files', 0)} file(s) in {payload.get('seconds', 0)}s")
            print("counts:", payload.get("counts", {}))
            stats = payload.get("stats", {})
            print(f"library total: {stats.get('total', 0)} · OCR {stats.get('with_ocr', 0)} · embedded {stats.get('with_embedding', 0)}")
            for error in payload.get("errors", [])[:10]:
                print("  error:", error.get("path"), error.get("error"))
        else:
            print("error:", payload.get("error"))
        return 0 if payload.get("ok") else 1

    if command in {"search", "recall"}:
        payload = _call(
            "eye_search" if command == "search" else "eye_recall",
            {
                "query": " ".join(args.query),
                "limit": args.limit,
                "kind": args.kind,
                "since": args.since,
                "until": args.until,
                "folder": getattr(args, "folder", None),
                "tags": getattr(args, "tags", ""),
                "mode": getattr(args, "mode", "auto"),
            },
        )
        _print_results(payload, args.limit)
        return 0 if payload.get("ok") else 1

    if command in {"stats", "status"}:
        payload = _call("eye_index_status", {})
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok") else 1

    if command == "timeline":
        payload = _call(
            "eye_timeline",
            {"since": args.since, "until": args.until, "bucket": args.bucket, "limit": args.limit},
        )
        for bucket in payload.get("buckets", []):
            print(f"{bucket['bucket']}  {bucket['count']:>5}  {bucket['examples'][0]['path'] if bucket['examples'] else ''}")
        return 0 if payload.get("ok") else 1

    if command == "duplicates":
        payload = _call(
            "eye_duplicates",
            {"threshold": args.threshold, "limit": args.limit, "since": args.since, "until": args.until},
        )
        print(f"{payload.get('count', 0)} group(s) · scanned {payload.get('scanned', 0)}")
        for group in payload.get("groups", []):
            best = group["best"]
            print(f"  {group['size']} copies · best #{best['id']} {best['path']}")
            for item in group["items"]:
                print(f"      #{item['id']} {item['path']}")
        return 0 if payload.get("ok") else 1

    if command == "best":
        payload = _call("eye_best", {"query": " ".join(args.query), "limit": args.limit})
        _print_results(payload, args.limit)
        return 0 if payload.get("ok") else 1

    if command == "album":
        payload = _call(
            "eye_album",
            {"query": " ".join(args.query), "name": args.name, "limit": args.limit, "copy": args.copy},
        )
        if payload.get("ok"):
            print(f"album '{payload['name']}' · {payload['count']} item(s) · {payload['folder']}")
        else:
            print("error:", payload.get("error"))
        return 0 if payload.get("ok") else 1

    if command == "receipts":
        payload = _call(
            "eye_receipts",
            {"since": args.since, "until": args.until, "format": args.format, "out_path": args.out},
        )
        if payload.get("ok"):
            print(f"{payload['count']} receipt(s) · total {payload['total']} · {payload['path']}")
        else:
            print("error:", payload.get("error"))
        return 0 if payload.get("ok") else 1

    if command in {"capture", "look", "read", "find"}:
        name = f"eye_{command}"
        params: dict[str, Any] = {"camera_index": getattr(args, "camera", None)}
        if command == "capture":
            params.update({"note": args.note, "tags": args.tags})
        elif command == "look":
            params.update({"ocr": not args.no_ocr, "remember": not args.no_remember})
        elif command == "read":
            params.update({"remember": not args.no_remember})
        elif command == "find":
            params.update({"description": " ".join(args.description), "limit": args.limit})
        payload = _call(name, params)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok") else 1

    if command == "forget":
        payload = _call(
            "eye_forget",
            {
                "media_id": args.id,
                "path": args.path,
                "query": args.query,
                "delete_files": args.delete_files,
                "all": args.all,
                "confirm": args.yes,
            },
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok") else 1

    if command == "remember":
        payload = _call(
            "eye_remember",
            {
                "media_id": args.id,
                "path": args.path,
                "query": " ".join(args.query),
                "note": args.note,
                "caption": args.caption,
                "tags": args.tags,
                "all": args.all,
            },
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok") else 1

    if command == "warmup":
        from .embeddings import warmup

        print(json.dumps(warmup(), ensure_ascii=False, indent=2))
        return 0

    print("unknown command:", command)
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(prog="hermes-eye-memory")
    setup_argparse(parser)
    return handle(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
