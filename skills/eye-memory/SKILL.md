---
name: eye-memory
description: Use the local photo library and camera as a private visual memory. Index folders, search by meaning or text, build albums, cull duplicates, extract receipts, and recall what the camera saw.
version: 0.1.0
author: Ananya
license: MIT
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [Vision, Photos, Memory, Camera, Accessibility]
---

# Eye Memory

Use this skill when the user asks about their photos, screenshots, receipts, camera, or something they saw earlier. All work is local.

## First move

If the library has not been indexed, call `eye_index_status`. If it is empty and the user has a folder, call `eye_index` with that path. Re-indexing is safe: unchanged files are skipped.

```json
{"path": "C:/Users/me/Pictures", "limit": 500}
```

For a large folder, use `background=true`, then poll `eye_index_status`. Tell the user indexing is running instead of blocking the conversation.

## Search

`eye_search` is the default. Prefer natural language and add filters only when useful.

```json
{"query": "red mug on a wooden table", "limit": 10}
{"query": "tag:receipt year:2024", "limit": 20}
{"query": "beach sunset", "since": "2024-05-01", "until": "2024-06-30"}
{"query": "", "kind": "frame", "limit": 5}
```

Filters: `year:2024`, `month:2024-05`, `day:2024-05-12`, `tag:receipt`, `is:receipt`, `has:ocr`, `has:gps`, `kind:photo|frame`.

Use `mode: "text"` when the user means words in the image (receipts, screenshots, signs). Use `mode: "visual"` when the user describes appearance. Leave `auto` otherwise.

If results are weak, try one or two rephrasings. Do not claim a photo exists when the search returned nothing.

## Recall and camera

- `eye_recall` searches frames and photos the camera has already seen. Use it for "what did I see earlier" or "where did I put my keys".
- `eye_look` describes the current camera view. Use it for "what is on my desk right now".
- `eye_read` reads text or a receipt from the camera.
- `eye_find` compares the current camera view to the library. Use it for "do I own this" or "where did I see this".
- `eye_capture` captures a frame with an optional note and tags. It does not store the frame unless `remember=true`.

Camera tools are disabled by default. If they return a disabled error, tell the user to enable `camera_enabled` in the plugin settings. Do not retry in a loop. Camera tools may also fail if no camera is available; report the error plainly and offer the photo-library alternative.

## Albums, duplicates, best shots

- `eye_album` writes a manifest and can copy files. It never moves or deletes originals. Use a clear name.
- `eye_duplicates` groups near-duplicates. Suggest the best shot; do not delete unless the user asks.
- `eye_best` ranks by sharpness, exposure, and resolution. Use it before recommending which copy to keep.

```json
{"name": "beach-2024", "query": "beach", "limit": 30, "copy": true}
{"threshold": 6, "limit": 10}
{"query": "beach", "limit": 5}
```

## Receipts

`eye_receipts` finds receipt photos and extracts merchant, date, and total. It writes PDF, Markdown, or CSV under the plugin data directory. It does not accept an output path from the model. OCR must be enabled and the OCR engine installed.

```json
{"since": "2024-01-01", "format": "markdown"}
```

Receipt parsing is heuristic. Show the extracted values and mention that the user should verify totals. Do not present it as accounting data.

## Notes and tags

Use `eye_remember` to attach context the user gives you. Prefer `media_id` from a search result; `query` uses the first match.

```json
{"media_id": 42, "note": "Mum's birthday", "tags": ["family", "birthday"]}
```

## Deletion rules

- `eye_forget` only removes index rows. It never deletes original files.
- Query-based removal is capped by `max_forget_query`. Prefer `media_id` or `path` for a narrow removal.
- `all=true` requires `confirm=true`. Never set both unless the user explicitly asks to wipe the entire index.
- Never remove index entries based only on a weak search match. Confirm the path or media id first.

## Privacy rules

- Do not upload photos or OCR text anywhere.
- Do not read the index database directly; use the tools.
- Do not describe people's identities or infer sensitive attributes from photos.
- Camera frames are not stored unless `remember=true`. If the user does not want them kept, leave `remember` false or pass `remember=false` to `eye_look` or `eye_read`.

## Fallback behavior

If semantic search seems color-only, the plugin is in fallback mode (no CLIP model). Say that visual similarity is limited and lean on OCR text, tags, notes, filenames, and dates. Do not try to install models without asking.
