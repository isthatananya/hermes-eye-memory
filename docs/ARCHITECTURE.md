# Architecture

Hermes Eye Memory is a local index plus a thin tool layer. The index is SQLite. Images are read only when indexing, searching visually, or generating thumbnails.

## Pipeline

```text
folder / camera frame
        |
        v
  indexer.index_file
        |
        +--> EXIF (taken_at, GPS, camera)
        +--> PIL decode, resize, RGB
        +--> quality (sharpness and exposure)
        +--> dhash (near-duplicate grouping)
        +--> thumbnail (data_dir/thumbs)
        +--> caption (dominant color words)
        +--> OCR (optional, local)
        +--> embedding (CLIP or fallback vector)
        |
        v
  SQLite media table + FTS5 (optional)
        |
        v
  search / albums / duplicates / receipts / timeline
```

## Modules

| Module | Responsibility |
| --- | --- |
| `config.py` | Merge plugin config, environment, and defaults; resolve data dir. |
| `db.py` | Schema, migrations, upsert, FTS sync, stats, albums. |
| `hashing.py` | dHash, Hamming distance, fallback vector, color caption, quality. |
| `exif.py` | EXIF date/GPS/camera extraction with graceful fallbacks. |
| `embeddings.py` | Lazy CLIP embedder, normalized vectors, fallback. |
| `ocr.py` | Lazy RapidOCR, receipt field extraction. |
| `indexer.py` | Folder walk, change detection, thumbnails, per-file indexing. |
| `search.py` | Query parsing, hybrid scoring, duplicates, best shots, timeline. |
| `actions.py` | Albums, receipt reports, forget, remember. |
| `camera.py` | OpenCV capture, look/read/find, frame storage. |
| `schemas.py` | Tool schemas exposed to Hermes. |
| `tools.py` | Handlers, background job, context wiring. |
| `cli.py` | Standalone and `hermes eye-memory` CLI. |

## Storage

Default location:

```text
$HERMES_HOME/plugin-data/hermes-eye-memory/
  data.db
  thumbs/
    <sha1>.jpg
```

When the Hermes host provides `plugin_db` and `plugin_data_dir`, those are used instead. `HERMES_EYE_MEMORY_DATA` overrides both.

### Tables

- `media`: one row per indexed file or camera frame.
- `media_fts`: FTS5 mirror of `ocr_text`, `caption`, `note`, and `tags` when FTS5 is available.
- `albums`: album name, query, manifest path, item count, and creation timestamp.

`upsert_media` merges partial updates so a re-index does not erase a user note, caption, or tags. FTS rows are updated in the same transaction.

## Search scoring

`search.search` parses filters out of the query first. The remaining text is tokenized.

- Lexical score: FTS5 match, or LIKE fallback. Exact phrase and token overlap boost the score.
- Visual score: cosine similarity between the query embedding and stored image embeddings. With fallback mode there is no text encoder, so this term is zero and lexical/visual-neighbor scores carry the result.
- Final score in `auto` mode: `0.62 * visual + 0.38 * lexical` when a CLIP text encoder is available, otherwise `0.72 * lexical + 0.28 * visual`. `text` and `visual` modes use only their term.

Date, tag, folder, kind, `has:ocr`, and `has:gps` filters are applied before scoring. Results include a short reason string.

## Background indexing

`eye_index` with `background=true` starts one worker thread. Progress lives in a process-local job dict and is returned by `eye_index_status`. A second job is refused while one is running. The worker uses its own SQLite connection.

## Failure behavior

- Missing optional model or OCR engine: log once, continue with fallback.
- Unreadable image: record an error count, do not abort the folder.
- Missing file during search: the indexed row is still returned; use `eye_forget` or re-index to clean it up.
- Camera unavailable: return a clear error, do not crash the agent.
- FTS5 unavailable: use LIKE search; the rest of the schema is unchanged.
