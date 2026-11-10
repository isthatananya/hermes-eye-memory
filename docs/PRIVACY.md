# Privacy

Hermes Eye Memory is local-first by design. This document describes exactly what is stored and what leaves the machine.

## What leaves the machine

Nothing. The plugin contains no HTTP client, telemetry, analytics, crash reporting, or update checker. It does not call a cloud vision, OCR, or embedding API.

The only network activity is dependency installation and, on first use of CLIP, `fastembed` downloading its model. That download is performed by the library, not by plugin code. Set `HERMES_EYE_MEMORY_EMBEDDING_BACKEND=fallback` to avoid it.

## What is stored locally

In the data directory:

- File paths, file names, extensions, sizes, and mtimes.
- Image dimensions, EXIF capture time, GPS coordinates if present, and camera make/model.
- Perceptual hash, fallback/CLIP embedding vector, and quality scores.
- OCR text extracted from the image.
- Dominant-color caption and any user notes or tags.
- A small JPEG thumbnail (max 512 px long edge).
- Album manifests and receipt reports you explicitly create.

Original photos are never copied into the data directory and are never modified.

## What is not stored

- No face embeddings or identity labels.
- No cloud identifiers, accounts, or API keys.
- No usage events or query logs beyond the local index itself.

## Deletion

`eye_forget` removes index rows and thumbnails. It deletes originals only when `delete_files=true`. Deleting the whole index requires `all=true` and `confirm=true`.

To remove everything, stop Hermes and delete the data directory shown by `eye_stats` or `eye_index_status`.

## Camera

Camera access happens only when a camera tool is invoked. Frames are written to the data directory as normal indexed media and can be removed with `eye_forget`. No camera stream is recorded continuously and nothing is sent anywhere.

## Threat model

The plugin assumes the local machine and the Hermes data directory are trusted. It does not encrypt the index at rest. If your disk is not encrypted, the index (including OCR text and GPS) is readable by anyone with file access. Use full-disk encryption for sensitive libraries.
