from __future__ import annotations

import pytest
from PIL import Image, ImageDraw


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_EYE_MEMORY_DATA", str(tmp_path / "plugin-data"))
    monkeypatch.setenv("HERMES_EYE_MEMORY_EMBEDDING_BACKEND", "fallback")
    monkeypatch.setenv("HERMES_EYE_MEMORY_OCR_ENABLED", "false")

    import hermes_eye_memory.embeddings as embeddings

    embeddings._EMBEDDER = None
    embeddings._EMBEDDER_BACKEND = None
    yield


def make_image(path, background, shapes=(), size=(320, 240)):
    image = Image.new("RGB", size, background)
    draw = ImageDraw.Draw(image)
    for shape in shapes:
        kind = shape[0]
        if kind == "rect":
            draw.rectangle(shape[1], fill=shape[2], outline=shape[3] if len(shape) > 3 else None, width=3)
        elif kind == "ellipse":
            draw.ellipse(shape[1], fill=shape[2], outline=shape[3] if len(shape) > 3 else None, width=3)
        elif kind == "text":
            draw.text(shape[1], shape[2], fill=shape[3] if len(shape) > 3 else "black")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "library"
    make_image(
        root / "red-square.jpg",
        (245, 240, 235),
        [("rect", (60, 50, 260, 200), (200, 30, 30))],
    )
    make_image(
        root / "blue-circle.png",
        (240, 245, 250),
        [("ellipse", (70, 40, 250, 210), (30, 70, 190))],
    )
    make_image(
        root / "green-field.jpg",
        (210, 235, 200),
        [("rect", (0, 150, 320, 240), (40, 140, 50))],
    )
    return root
