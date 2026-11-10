"""Small, defensive EXIF reader."""

from __future__ import annotations

from typing import Any

from PIL import Image


def _to_float(value: Any) -> float | None:
    try:
        if isinstance(value, tuple) and len(value) == 2:
            return float(value[0]) / float(value[1])
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _normalize_datetime(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if len(text) >= 19 and text[4] == ":" and text[7] == ":":
        return f"{text[0:4]}-{text[5:7]}-{text[8:10]}T{text[11:19]}"
    return text or None


def read_exif(img: Image.Image) -> dict[str, Any]:
    result: dict[str, Any] = {}
    try:
        exif = img.getexif()
    except Exception:
        return result
    if not exif:
        return result

    try:
        taken = exif.get(36867) or exif.get(306)
        normalized = _normalize_datetime(taken)
        if normalized:
            result["taken_at"] = normalized
    except Exception:
        pass

    try:
        make = str(exif.get(271) or "").strip()
        model = str(exif.get(272) or "").strip()
        camera = " ".join(part for part in (make, model) if part)
        if camera:
            result["camera"] = camera
    except Exception:
        pass

    try:
        gps = exif.get_ifd(34853)
    except Exception:
        gps = None
    if gps:
        try:
            lat = _to_float(gps.get(2))
            lon = _to_float(gps.get(4))
            if lat is not None and lon is not None:
                lat_ref = str(gps.get(1) or "N").upper()
                lon_ref = str(gps.get(3) or "E").upper()
                if lat_ref.startswith("S"):
                    lat = -lat
                if lon_ref.startswith("W"):
                    lon = -lon
                result["gps_lat"] = round(lat, 7)
                result["gps_lon"] = round(lon, 7)
        except Exception:
            pass

    return result
