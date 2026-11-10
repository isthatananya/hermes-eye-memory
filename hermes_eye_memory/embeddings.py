"""Image and text embeddings with a no-model fallback.

CLIP runs through fastembed (ONNX Runtime, no torch). If the model cannot be
loaded or downloaded, the plugin degrades to a deterministic visual vector so
indexing and duplicate grouping still work.
"""

from __future__ import annotations

import logging
import tempfile
import threading
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from . import config, db
from .hashing import fallback_vector

logger = logging.getLogger(__name__)

IMAGE_MODEL = "Qdrant/clip-ViT-B-32-vision"
TEXT_MODEL = "Qdrant/clip-ViT-B-32-text"

_LOCK = threading.Lock()
_EMBEDDER: "Embedder | None" = None
_EMBEDDER_BACKEND: str | None = None


def normalize(vector: Any) -> np.ndarray:
    array = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(array))
    if norm <= 1e-12:
        return array
    return array / norm


class Embedder:
    def __init__(self, backend: str = "clip") -> None:
        self.backend = backend if backend in {"clip", "fallback"} else "clip"
        self._image_model: Any = None
        self._text_model: Any = None
        self._failed = False
        self._lock = threading.Lock()

    def _ensure_image(self) -> Any:
        if self.backend != "clip" or self._failed:
            return None
        with self._lock:
            if self._image_model is not None:
                return self._image_model
            try:
                from fastembed import ImageEmbedding

                cache = str(db.models_dir())
                try:
                    self._image_model = ImageEmbedding(model_name=IMAGE_MODEL, cache_dir=cache)
                except TypeError:
                    self._image_model = ImageEmbedding(model_name=IMAGE_MODEL)
                return self._image_model
            except Exception as exc:
                logger.warning("CLIP image model unavailable, using fallback: %s", exc)
                self._failed = True
                return None

    def _ensure_text(self) -> Any:
        if self.backend != "clip" or self._failed:
            return None
        with self._lock:
            if self._text_model is not None:
                return self._text_model
            try:
                from fastembed import TextEmbedding

                cache = str(db.models_dir())
                try:
                    self._text_model = TextEmbedding(model_name=TEXT_MODEL, cache_dir=cache)
                except TypeError:
                    self._text_model = TextEmbedding(model_name=TEXT_MODEL)
                return self._text_model
            except Exception as exc:
                logger.warning("CLIP text model unavailable: %s", exc)
                self._failed = True
                return None

    def embed_image(self, img: Image.Image) -> np.ndarray:
        model = self._ensure_image()
        if model is None:
            return fallback_vector(img)
        try:
            try:
                vectors = list(model.embed([img]))
            except Exception:
                handle = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                handle.close()
                path = Path(handle.name)
                try:
                    img.convert("RGB").save(path, format="JPEG", quality=90)
                    vectors = list(model.embed([str(path)]))
                finally:
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        pass
            if not vectors:
                raise ValueError("empty embedding")
            return normalize(vectors[0])
        except Exception as exc:
            logger.warning("image embedding failed, using fallback: %s", exc)
            self._failed = True
            return fallback_vector(img)

    def embed_text(self, text: str) -> np.ndarray | None:
        if not text.strip():
            return None
        model = self._ensure_text()
        if model is None:
            return None
        try:
            vectors = list(model.embed([text]))
            if not vectors:
                return None
            return normalize(vectors[0])
        except Exception as exc:
            logger.warning("text embedding failed: %s", exc)
            self._failed = True
            return None

    @property
    def semantic(self) -> bool:
        return self.backend == "clip" and not self._failed


def get_embedder(backend: str | None = None) -> Embedder:
    global _EMBEDDER, _EMBEDDER_BACKEND
    chosen = backend or config.embedding_backend()
    with _LOCK:
        if _EMBEDDER is None or _EMBEDDER_BACKEND != chosen:
            _EMBEDDER = Embedder(chosen)
            _EMBEDDER_BACKEND = chosen
        return _EMBEDDER


def warmup(backend: str | None = None) -> dict[str, Any]:
    embedder = get_embedder(backend)
    image = Image.new("RGB", (64, 64), (120, 90, 200))
    image_vector = embedder.embed_image(image)
    text_vector = embedder.embed_text("a test image")
    return {
        "backend": embedder.backend,
        "semantic": embedder.semantic,
        "image_dim": int(image_vector.shape[0]),
        "text_dim": int(text_vector.shape[0]) if text_vector is not None else 0,
    }
