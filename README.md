# Hermes Eye Memory

Local visual memory for Hermes. Point it at a photo library, then search by meaning, build albums, cull duplicates, pull totals out of receipt photos, and ask what the webcam just saw.

Everything runs on your machine. No cloud vision API, no upload, no account.

## Why

Most photo tools are either a cloud black box or a folder of filenames. Hermes Eye Memory gives an agent a private visual memory it can query with tools:

- "Find the photo of the red mug on the wooden table."
- "Which receipts did I photograph in May 2024?"
- "Make an album of the beach, best shots only."
- "What is on my desk right now?" (camera)
- "Where did I see this?" (camera to library)

## Install

As a Hermes plugin from a local checkout:

```bash
hermes plugins install /absolute/path/to/hermes-eye-memory
```

From the catalog, once listed:

```bash
hermes plugins install hermes-eye-memory
```

Standalone CLI without Hermes:

```bash
python -m pip install -e .
python -m hermes_eye_memory.cli index ~/Pictures
python -m hermes_eye_memory.cli search "red mug"
```

Python 3.11+ is required. Core install needs Pillow, NumPy, and reportlab. Optional extras:

```bash
python -m pip install -e ".[semantic]"   # fastembed / CLIP semantic search
python -m pip install -e ".[ocr]"        # rapidocr-onnxruntime local OCR
python -m pip install -e ".[camera]"     # opencv-python webcam support
python -m pip install -e ".[heic]"       # pillow-heif iPhone photos
```

Without the optional extras the plugin still runs in fallback mode: color/composition search, filenames, notes, tags, EXIF, duplicates, albums, and timeline. Optional extras need wheels for your Python version; if a model or camera package is unavailable, the related tool returns a clear error and the rest keeps working.

## Quick start

```bash
# 1. Index a folder. Re-running skips unchanged files.
python -m hermes_eye_memory.cli index ~/Pictures --limit 2000

# 2. Search with natural language and filters.
python -m hermes_eye_memory.cli search "dog on the beach" --limit 10
python -m hermes_eye_memory.cli search "tag:receipt year:2024"

# 3. Inspect the library.
python -m hermes_eye_memory.cli stats
python -m hermes_eye_memory.cli timeline --bucket month

# 4. Find near-duplicates and keep the best shot.
python -m hermes_eye_memory.cli duplicates --threshold 6
python -m hermes_eye_memory.cli best "beach" --limit 5

# 5. Build a non-destructive album.
python -m hermes_eye_memory.cli album "garden" --name garden-2024 --copy

# 6. Receipt report.
python -m hermes_eye_memory.cli receipts --since 2024-01-01 --format markdown
```

The same operations are exposed as 16 Hermes tools.

## Tools

| Tool | What it does |
| --- | --- |
| `eye_index` | Index a folder; EXIF, hashes, embeddings, thumbnails, optional OCR. Supports background jobs. |
| `eye_index_status` | Index health, coverage, data directory, background job state. |
| `eye_search` | Hybrid text, OCR, tag, date, folder, and visual search. |
| `eye_album` | Create a named album manifest; optionally copy files. |
| `eye_duplicates` | Group near-duplicates and bursts; suggest the best shot. |
| `eye_best` | Rank candidates by sharpness, exposure, and resolution. |
| `eye_receipts` | Extract merchant, date, and total; write PDF, Markdown, or CSV. |
| `eye_timeline` | Counts by day, month, or year with examples. |
| `eye_stats` | Totals, bytes, date range, OCR and embedding coverage. |
| `eye_forget` | Remove from the index; optional file deletion with confirmation. |
| `eye_capture` | Capture a webcam frame into memory. |
| `eye_look` | Describe the current camera view: size, colors, OCR text. |
| `eye_read` | Read text or a receipt with the camera. |
| `eye_find` | Capture the camera view and find similar library photos. |
| `eye_remember` | Attach a note, caption, or tags to a photo or search result. |
| `eye_recall` | Recall earlier camera frames and photos by text, tag, or time. |

Search filters include `year:2024`, `month:2024-05`, `day:2024-05-12`, `tag:receipt`, `is:receipt`, `has:ocr`, `has:gps`, and `kind:photo|frame`. Quoted phrases are kept together.

## Configuration

`plugin.yaml` exposes these settings:

| Key | Default | Meaning |
| --- | --- | --- |
| `library_path` | `""` | Default folder for `eye_index` and CLI commands. |
| `ocr_enabled` | `true` | Read text in photos. Slower, enables receipt search. |
| `embedding_backend` | `clip` | `clip` for semantic search, `fallback` for a no-download color/edge vector. |
| `camera_index` | `0` | Default desktop camera. |
| `max_results` | `20` | Default result count. |

Environment overrides:

| Variable | Purpose |
| --- | --- |
| `HERMES_EYE_MEMORY_DATA` | Data directory for the SQLite index and thumbnails. |
| `HERMES_EYE_MEMORY_LIBRARY` | Default library folder. |
| `HERMES_EYE_MEMORY_OCR_ENABLED` | `true` / `false`. |
| `HERMES_EYE_MEMORY_EMBEDDING_BACKEND` | `clip` / `fallback`. |
| `HERMES_EYE_MEMORY_CAMERA_INDEX` | Default camera index. |
| `HERMES_EYE_MEMORY_MAX_RESULTS` | Default result count. |

The plugin uses Hermes's `plugin_db` and `plugin_data_dir` when available. Otherwise it stores data under `HERMES_HOME/plugin-data/hermes-eye-memory`.

## Fallback mode

CLIP is the best experience, but it downloads a model on first use. For an offline machine or a quick demo:

```bash
HERMES_EYE_MEMORY_EMBEDDING_BACKEND=fallback python -m hermes_eye_memory.cli index ~/Pictures
```

Fallback embeddings combine color histograms, a grayscale thumbnail, and a perceptual hash. Search still works for color, composition, OCR text, filenames, notes, and tags. It is not a replacement for CLIP semantics.

## Privacy and safety

See [docs/PRIVACY.md](docs/PRIVACY.md) for the full data inventory and threat model.

- Photos never leave the machine. There is no network code in the plugin.
- OCR is local. The optional OCR engine runs on CPU.
- The index stores paths, EXIF, hashes, OCR text, captions, tags, and small thumbnails. Original files are not modified.
- `eye_forget` only removes index rows by default. Deleting originals requires `delete_files=true`, and `all=true` requires `confirm=true`.
- Albums are manifests plus optional copies. They never move or delete originals.
- Camera access is explicit: only `eye_capture`, `eye_look`, `eye_read`, and `eye_find` open a camera.
- Background indexing is bounded to one job at a time.

## Demo

Generate a synthetic library and run the whole flow:

```bash
python scripts/make_demo_library.py --out demo_library --clean
python -m hermes_eye_memory.cli index demo_library
python -m hermes_eye_memory.cli search "red mug"
python -m hermes_eye_memory.cli duplicates
python -m hermes_eye_memory.cli receipts --format markdown
```

See [docs/DEMO.md](docs/DEMO.md) for a scripted walkthrough and screenshot suggestions.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the index schema, search scoring, and failure behavior.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

Install the optional extras before testing OCR, CLIP, camera, or HEIC paths.

On Windows, if pytest cannot create its temp directory, point it at a writable folder:

```powershell
$env:TEMP = "C:\Users\you\AppData\Local\Temp"
python -m pytest
```

Tests use `HERMES_EYE_MEMORY_EMBEDDING_BACKEND=fallback` and disable OCR, so they do not download models or need a camera.

## Validate before publishing

With Hermes installed:

```bash
hermes plugins doctor . --ci
hermes plugins validate . --install-deps
```

`doctor` loads `plugin.yaml`, calls `register(ctx)`, and compares declared tools with registered tools. `validate` runs the catalog checks. See [catalog/README.md](catalog/README.md) for the submission steps.

## Limitations

- CLIP and OCR models are optional dependencies; without them the plugin degrades to fallback search and filename/notes/tags.
- HEIC needs `pillow-heif` (install the `heic` extra).
- Video indexing is not included. Camera frames are stills.
- Receipt parsing is heuristic. It extracts a best-effort merchant, date, and total, not accounting-grade data.
- Face recognition and people labeling are deliberately not included.

## License

MIT. See [LICENSE](LICENSE).
