"""Optional OCR through RapidOCR, plus receipt field extraction."""

from __future__ import annotations

import logging
import re
import threading
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

MAX_SIDE = 2400
_LOCK = threading.Lock()
_ENGINE: Any = None
_ENGINE_FAILED = False

RECEIPT_WORDS = re.compile(
    r"\b(receipt|invoice|subtotal|total|amount|tax|gst|vat|paid|change|cash|card|"
    r"order|bill|merchant|store|date|qty|item)\b",
    re.IGNORECASE,
)
AMOUNT_RE = re.compile(
    r"(?:grand\s+total|total|amount|subtotal|paid)[^\d]{0,24}"
    r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
    re.IGNORECASE,
)
DATE_RE = re.compile(
    r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}[./-]\d{1,2}[./-]\d{1,2}|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{2,4})\b",
    re.IGNORECASE,
)


def _engine_instance() -> Any:
    global _ENGINE, _ENGINE_FAILED
    if _ENGINE_FAILED:
        return None
    with _LOCK:
        if _ENGINE is not None:
            return _ENGINE
        try:
            from rapidocr_onnxruntime import RapidOCR

            _ENGINE = RapidOCR()
        except Exception as exc:
            logger.warning("OCR engine unavailable: %s", exc)
            _ENGINE_FAILED = True
            return None
        return _ENGINE


def ocr_image(img: Image.Image) -> dict[str, Any]:
    """Return OCR text and line scores. Empty result when OCR is unavailable."""
    engine = _engine_instance()
    if engine is None:
        return {"text": "", "lines": [], "score": 0.0, "available": False}

    image = img.convert("RGB")
    if max(image.size) > MAX_SIDE:
        image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    array = np.asarray(image)
    bgr = array[:, :, ::-1].copy()

    try:
        output = engine(bgr)
    except Exception as exc:
        logger.warning("OCR failed: %s", exc)
        return {"text": "", "lines": [], "score": 0.0, "available": True}

    lines: list[str] = []
    scores: list[float] = []

    # RapidOCR 1.3 returns (result, elapse); newer builds return an object.
    result = output
    if isinstance(output, tuple) and len(output) >= 1:
        result = output[0]

    if result is None:
        return {"text": "", "lines": [], "score": 0.0, "available": True}

    if hasattr(result, "txts"):
        texts = list(getattr(result, "txts") or [])
        values = list(getattr(result, "scores") or [])
        for index, text in enumerate(texts):
            text = str(text).strip()
            if text:
                lines.append(text)
                try:
                    scores.append(float(values[index]))
                except (IndexError, TypeError, ValueError):
                    pass
    else:
        for item in result:
            try:
                text = str(item[1]).strip()
                score = float(item[2])
            except (IndexError, TypeError, ValueError):
                continue
            if text:
                lines.append(text)
                scores.append(score)

    text = "\n".join(lines)
    mean_score = float(sum(scores) / len(scores)) if scores else 0.0
    return {"text": text, "lines": lines, "score": mean_score, "available": True}


def looks_like_receipt(text: str) -> bool:
    if not text:
        return False
    hits = len(set(match.group(0).lower() for match in RECEIPT_WORDS.finditer(text)))
    return hits >= 2 or bool(AMOUNT_RE.search(text))


def extract_receipt_fields(text: str) -> dict[str, Any]:
    amount = None
    match = AMOUNT_RE.search(text or "")
    if match:
        try:
            amount = float(match.group(1).replace(",", ""))
        except ValueError:
            amount = None

    date = None
    date_match = DATE_RE.search(text or "")
    if date_match:
        date = date_match.group(1)

    merchant = None
    for line in (text or "").splitlines():
        line = line.strip()
        if len(line) >= 3 and not re.fullmatch(r"[\d\W]+", line):
            merchant = line[:80]
            break

    return {"amount": amount, "date": date, "merchant": merchant}
