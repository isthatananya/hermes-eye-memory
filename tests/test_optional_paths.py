"""Optional-path behavior when OCR, CLIP, or a camera is unavailable."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from hermes_eye_memory import camera, embeddings, indexer, ocr


def test_camera_reports_opencv_when_installed():
    pytest.importorskip("cv2")
    assert camera.available() is True
    assert camera.status()["opencv"] is True


def test_heic_indexing_when_pillow_heif_is_installed(tmp_path):
    heif = pytest.importorskip("pillow_heif")
    heif.register_heif_opener()
    path = tmp_path / "sample.heic"
    Image.new("RGB", (64, 64), "green").save(path, format="HEIF")

    result = indexer.index_file(path, run_ocr=False)
    assert result["status"] == "indexed"
    assert result["width"] == 64
    assert result["height"] == 64


def test_camera_tools_degrade_cleanly_without_opencv(monkeypatch):
    monkeypatch.setattr(camera, "_cv2", lambda: None)

    assert camera.available() is False
    assert camera.status()["opencv"] is False

    frame, error = camera.grab_frame()
    assert frame is None
    assert "opencv-python" in error

    for payload in (
        camera.capture(),
        camera.look(),
        camera.read(),
        camera.find(description="red mug"),
    ):
        assert payload["ok"] is False
        assert "opencv-python" in payload["error"]


def test_ocr_reports_unavailable_and_still_parses_text(monkeypatch):
    monkeypatch.setattr(ocr, "_engine_instance", lambda: None)

    result = ocr.ocr_image(Image.new("RGB", (32, 32), "white"))
    assert result == {"text": "", "lines": [], "score": 0.0, "available": False}

    text = "GREEN MARKET\n12 May 2024\nTotal 24.50\nPaid card"
    assert ocr.looks_like_receipt(text) is True
    fields = ocr.extract_receipt_fields(text)
    assert fields["amount"] == 24.5
    assert fields["merchant"] == "GREEN MARKET"


def test_clip_falls_back_when_model_backend_is_unavailable(monkeypatch):
    embedder = embeddings.Embedder("clip")
    embedder._failed = True
    monkeypatch.setattr(embedder, "_ensure_image", lambda: None)
    monkeypatch.setattr(embedder, "_ensure_text", lambda: None)

    vector = embedder.embed_image(Image.new("RGB", (32, 32), "red"))
    assert vector.shape == (832,)
    assert embedder.semantic is False
    assert embedder.embed_text("red mug") is None


def test_index_file_survives_ocr_failure(library, monkeypatch):
    def fail_ocr(_image):
        raise RuntimeError("OCR engine unavailable")

    monkeypatch.setattr(ocr, "ocr_image", fail_ocr)
    result = indexer.index_file(library / "red-square.jpg", run_ocr=True)
    assert result["status"] == "indexed"
    assert result["ocr"] is False
    assert result["ocr_text"] == ""


def test_camera_capture_includes_ocr_text_in_description(monkeypatch):
    frame = np.zeros((24, 32, 3), dtype=np.uint8)

    monkeypatch.setattr(camera, "grab_frame", lambda index=None: (frame, None))
    monkeypatch.setattr(camera, "_to_pil", lambda _frame: Image.new("RGB", (32, 24), "white"))
    monkeypatch.setattr(camera, "_write_frame", lambda _frame, path: path.write_bytes(b"frame") or True)
    monkeypatch.setattr(
        camera.indexer,
        "index_file",
        lambda *args, **kwargs: {
            "status": "indexed",
            "id": 7,
            "ocr_text": "hello from the camera",
        },
    )

    result = camera.capture(remember=True)
    assert result["ok"] is True
    assert "text: hello from the camera" in result["description"]
    assert "ocr_text" not in result
