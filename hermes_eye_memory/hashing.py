"""Perceptual hashing and cheap visual features."""

from __future__ import annotations

import colorsys

import numpy as np
from PIL import Image


def dhash(img: Image.Image, hash_size: int = 8) -> bytes:
    """Difference hash: robust to scaling and small color shifts."""
    gray = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
    pixels = np.asarray(gray, dtype=np.int16)
    diff = pixels[:, 1:] > pixels[:, :-1]
    return np.packbits(diff.reshape(-1)).tobytes()


def hamming(a: bytes | None, b: bytes | None) -> int:
    if not a or not b:
        return 64
    value = int.from_bytes(a, "big") ^ int.from_bytes(b, "big")
    return int(value.bit_count())


def _l2(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-12:
        return vector
    return vector / norm


def fallback_vector(img: Image.Image) -> np.ndarray:
    """Deterministic visual vector used when CLIP is unavailable.

    It combines an HSV color histogram, a coarse grayscale thumbnail, and the
    difference hash. It cannot understand text semantics, but it keeps visual
    similarity search and duplicate grouping working offline.
    """
    hsv = np.asarray(img.convert("HSV").resize((64, 64), Image.Resampling.BILINEAR))
    hist, _ = np.histogramdd(
        hsv.reshape(-1, 3),
        bins=(8, 8, 8),
        range=((0, 256), (0, 256), (0, 256)),
    )
    hist = _l2(hist.reshape(-1))

    gray = np.asarray(img.convert("L").resize((16, 16), Image.Resampling.BILINEAR), dtype=np.float32)
    gray = _l2((gray.reshape(-1) / 255.0) - 0.5)

    bits = np.unpackbits(np.frombuffer(dhash(img), dtype=np.uint8)).astype(np.float32)
    bits = (bits * 2.0) - 1.0

    return _l2(np.concatenate([hist, gray, bits]))


def sharpness(img: Image.Image) -> float:
    gray = np.asarray(img.convert("L").resize((256, 256), Image.Resampling.BILINEAR), dtype=np.float32)
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    lap = np.abs(
        4.0 * gray[1:-1, 1:-1]
        - gray[:-2, 1:-1]
        - gray[2:, 1:-1]
        - gray[1:-1, :-2]
        - gray[1:-1, 2:]
    )
    return float(lap.var())


def exposure_penalty(img: Image.Image) -> float:
    gray = np.asarray(img.convert("L").resize((256, 256), Image.Resampling.BILINEAR), dtype=np.float32)
    if gray.size == 0:
        return 1.0
    clipped = np.count_nonzero((gray < 5) | (gray > 250))
    return float(clipped) / float(gray.size)


def dominant_colors(img: Image.Image, count: int = 3) -> list[str]:
    small = img.convert("RGB").resize((64, 64), Image.Resampling.BILINEAR)
    pixels = np.asarray(small, dtype=np.uint16) // 16
    keys = (pixels[:, :, 0] << 8) | (pixels[:, :, 1] << 4) | pixels[:, :, 2]
    values, counts = np.unique(keys.reshape(-1), return_counts=True)
    order = np.argsort(counts)[::-1][:count]
    colors: list[str] = []
    for index in order:
        key = int(values[index])
        r = ((key >> 8) & 0xF) * 17
        g = ((key >> 4) & 0xF) * 17
        b = (key & 0xF) * 17
        colors.append(f"#{r:02x}{g:02x}{b:02x}")
    return colors


def color_name(value: str) -> str:
    value = value.lstrip("#")
    try:
        r, g, b = (int(value[index : index + 2], 16) / 255.0 for index in (0, 2, 4))
    except (ValueError, IndexError):
        return "color"
    hue, saturation, brightness = colorsys.rgb_to_hsv(r, g, b)
    if brightness < 0.14:
        return "black"
    if saturation < 0.12:
        return "white" if brightness > 0.85 else "gray"
    if brightness < 0.35:
        return "dark"
    degrees = hue * 360.0
    if degrees < 15 or degrees >= 345:
        return "red"
    if degrees < 40:
        return "orange"
    if degrees < 70:
        return "yellow"
    if degrees < 160:
        return "green"
    if degrees < 195:
        return "cyan"
    if degrees < 250:
        return "blue"
    if degrees < 290:
        return "purple"
    if degrees < 330:
        return "pink"
    return "red"


def color_caption(img: Image.Image, count: int = 3) -> str:
    names: list[str] = []
    for value in dominant_colors(img, count):
        name = color_name(value)
        if name not in names:
            names.append(name)
    return " ".join(names)
