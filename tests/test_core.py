from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from hermes_eye_memory import actions, db, hashing, indexer, search, tools
from hermes_eye_memory.embeddings import get_embedder


def test_dhash_and_fallback_vector(library):
    first = Image.open(library / "red-square.jpg")
    second = Image.open(library / "red-square.jpg")
    third = Image.open(library / "blue-circle.png")

    assert hashing.dhash(first) == hashing.dhash(second)
    assert hashing.hamming(hashing.dhash(first), hashing.dhash(second)) == 0
    assert hashing.hamming(hashing.dhash(first), hashing.dhash(third)) > 0

    vector = get_embedder("fallback").embed_image(first)
    assert vector.shape == (832,)
    assert abs(float(np.linalg.norm(vector)) - 1.0) < 1e-5


def test_index_search_and_skip(library):
    result = indexer.index_folder(library, run_ocr=False)
    assert result["ok"] is True
    assert result["counts"]["indexed"] == 3
    assert result["backend"] == "fallback"

    conn = db.connect()
    assert db.stats(conn)["total"] == 3
    row = db.get_by_path(conn, str((library / "red-square.jpg").resolve()))
    assert row is not None
    assert row["width"] == 320
    assert row["embedding_dim"] == 832
    conn.close()

    again = indexer.index_folder(library, run_ocr=False)
    assert again["counts"]["skipped"] == 3
    assert again["counts"]["indexed"] == 0


def test_notes_tags_and_query_filters(library):
    indexer.index_folder(library, run_ocr=False)
    conn = db.connect()
    row = db.get_by_path(conn, str((library / "red-square.jpg").resolve()))
    media_id = int(row["id"])

    remembered = actions.remember(media_id=media_id, note="red square on a table", tags=["red", "studio"])
    assert remembered["ok"] is True

    by_text = search.search("red square", mode="text")
    assert by_text["count"] == 1
    assert by_text["results"][0]["id"] == media_id

    by_tag = search.search("tag:red")
    assert by_tag["count"] == 1
    assert by_tag["results"][0]["tags"] == ["red", "studio"]

    parsed = search.parse_query("year:2024 month:2024-05 tag:red has:note is:receipt")
    assert parsed["since"] == "2024-05-01"
    assert parsed["until"] == "2024-05-31"
    assert parsed["tags"] == ["red"]
    assert parsed["has"] == ["note"]
    assert parsed["is"] == ["receipt"]
    conn.close()


def test_invalid_month_filter_is_ignored():
    parsed = search.parse_query("month:2024-13")
    assert parsed["since"] is None
    assert parsed["until"] is None


def test_duplicate_groups(library, tmp_path):
    shutil.copyfile(library / "red-square.jpg", library / "red-square-copy.jpg")
    indexer.index_folder(library, run_ocr=False)

    result = search.duplicate_groups(threshold=4)
    assert result["count"] == 1
    group = result["groups"][0]
    assert group["size"] == 2
    assert group["best"]["id"] in {item["id"] for item in group["items"]}


def test_album_and_forget(library):
    indexer.index_folder(library, run_ocr=False)
    conn = db.connect()
    row = db.get_by_path(conn, str((library / "red-square.jpg").resolve()))
    actions.remember(media_id=int(row["id"]), note="album target", tags=["album-test"])
    conn.close()

    album = actions.make_album(name="Red things", query="tag:album-test", copy_files=True)
    assert album["ok"] is True
    assert album["count"] == 1
    assert album["copied"] == 1
    assert Path(album["manifest"]).exists()
    assert Path(album["folder"], "manifest.json").exists()

    target = library / "red-square.jpg"
    removed = actions.forget(path=str(target), delete_files=True)
    assert removed["deleted"] == 1
    assert not target.exists()


def test_receipt_report(library):
    indexer.index_folder(library, run_ocr=False)
    conn = db.connect()
    row = db.get_by_path(conn, str((library / "red-square.jpg").resolve()))
    text = "GREEN MARKET\n12 May 2024\nApples 4.00\nTotal 24.50\nPaid card"
    db.upsert_media(conn, path=row["path"], ocr_text=text, tags=["receipt"])
    conn.close()

    report = actions.receipt_report(fmt="markdown")
    assert report["ok"] is True
    assert report["count"] == 1
    assert report["total"] == 24.5
    content = Path(report["path"]).read_text(encoding="utf-8")
    assert "GREEN MARKET" in content
    assert "24.5" in content


def test_timeline(library):
    indexer.index_folder(library, run_ocr=False)
    result = search.timeline(bucket="month")
    assert result["ok"] is True
    assert sum(bucket["count"] for bucket in result["buckets"]) == 3


def test_tool_handlers(library):
    payload = json.loads(tools._HANDLERS["eye_index"]({"path": str(library), "ocr": False}))
    assert payload["ok"] is True
    assert payload["counts"]["indexed"] == 3

    stats = json.loads(tools._HANDLERS["eye_stats"]({}))
    assert stats["ok"] is True
    assert stats["stats"]["total"] == 3

    guard = json.loads(tools._HANDLERS["eye_forget"]({"all": True}))
    assert guard["ok"] is False
    assert "confirm" in guard["error"]


def test_register_wires_every_tool():
    class FakeContext:
        def __init__(self):
            self.tools = []
            self.cli = []
            self.skills = []

        def register_tool(self, **kwargs):
            self.tools.append(kwargs)

        def register_cli_command(self, **kwargs):
            self.cli.append(kwargs)

        def register_skill(self, *args, **kwargs):
            self.skills.append((args, kwargs))

        def get_config(self, key, default=None):
            return default

    from hermes_eye_memory import register

    ctx = FakeContext()
    register(ctx)
    assert len(ctx.tools) == 16
    assert {tool["name"] for tool in ctx.tools} == {schema["name"] for schema in __import__("hermes_eye_memory.schemas", fromlist=["SCHEMAS"]).SCHEMAS}
    assert len(ctx.cli) == 1
    assert ctx.cli[0]["name"] == "eye-memory"
    assert len(ctx.skills) == 1
    assert ctx.skills[0][0][0] == "eye-memory"
