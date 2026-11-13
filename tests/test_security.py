"""Regression tests for the model-facing safety boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from hermes_eye_memory import actions, camera, config, db, indexer, schemas, tools


def _properties(name: str) -> dict:
    schema = next(item for item in schemas.SCHEMAS if item["name"] == name)
    return schema["parameters"]["properties"]


def test_receipt_schema_has_no_model_controlled_output_path():
    assert "out_path" not in _properties("eye_receipts")


def test_forget_schema_has_no_model_controlled_file_deletion():
    assert "delete_files" not in _properties("eye_forget")


@pytest.mark.parametrize(
    "bad_path",
    ["../escape.md", "sub/report.md", "sub\\report.md", "C:report.md", "..", "."],
)
def test_receipt_report_rejects_unsafe_paths(library, bad_path):
    indexer.index_folder(library, run_ocr=False)
    result = actions.receipt_report(fmt="markdown", out_path=bad_path)
    assert result["ok"] is False
    assert "bare file name" in result["error"]


def test_receipt_report_refuses_overwrite(library):
    indexer.index_folder(library, run_ocr=False)
    first = actions.receipt_report(fmt="markdown", out_path="report.md")
    assert first["ok"] is True
    second = actions.receipt_report(fmt="markdown", out_path="report.md")
    assert second["ok"] is False
    assert "overwrite" in second["error"]


def test_receipt_tool_ignores_out_path(library, tmp_path):
    indexer.index_folder(library, run_ocr=False)
    outside = tmp_path / "outside.md"
    payload = json.loads(
        tools._HANDLERS["eye_receipts"]({"format": "markdown", "out_path": str(outside)})
    )
    assert payload["ok"] is True
    assert Path(payload["path"]).parent == db.data_dir() / "receipts"
    assert not outside.exists()


def test_forget_tool_ignores_delete_files(library):
    indexer.index_folder(library, run_ocr=False)
    target = library / "red-square.jpg"
    payload = json.loads(
        tools._HANDLERS["eye_forget"]({"path": str(target), "delete_files": True})
    )
    assert payload["ok"] is True
    assert target.exists()
    conn = db.connect()
    assert db.get_by_path(conn, str(target.resolve())) is None
    conn.close()


def test_forget_query_is_capped(library):
    indexer.index_folder(library, run_ocr=False)
    result = actions.forget(query="jpg", max_query=1)
    assert result["ok"] is False
    assert "more than 1" in result["error"]
    conn = db.connect()
    assert db.stats(conn)["total"] == 3
    conn.close()


def test_camera_tools_are_disabled_by_default(monkeypatch):
    monkeypatch.setattr(config, "camera_enabled", lambda: False)
    for name in ("eye_capture", "eye_look", "eye_read", "eye_find"):
        params = {"description": "red mug"} if name == "eye_find" else {}
        payload = json.loads(tools._HANDLERS[name](params))
        assert payload["ok"] is False
        assert "disabled" in payload["error"]


def test_camera_tool_remember_defaults_to_false(monkeypatch):
    monkeypatch.setattr(config, "camera_enabled", lambda: True)
    seen = {}

    def fake_capture(**kwargs):
        seen.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(camera, "capture", fake_capture)
    payload = json.loads(tools._HANDLERS["eye_capture"]({}))
    assert payload["ok"] is True
    assert seen["remember"] is False


def test_camera_capture_defaults_to_not_remember(monkeypatch):
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    monkeypatch.setattr(camera, "grab_frame", lambda index=None: (frame, None))
    monkeypatch.setattr(camera, "_to_pil", lambda _frame: Image.new("RGB", (8, 8), "white"))
    monkeypatch.setattr(camera, "_write_frame", lambda _frame, path: path.write_bytes(b"x") or True)
    indexed = []
    monkeypatch.setattr(camera.indexer, "index_file", lambda *args, **kwargs: indexed.append(1) or {"status": "indexed"})

    result = camera.capture()
    assert result["ok"] is True
    assert result["indexed"] is False
    assert indexed == []
