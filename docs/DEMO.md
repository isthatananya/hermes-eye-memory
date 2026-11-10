# Demo

A repeatable demo that needs no personal photos, no model download, and no camera.

## Setup

```bash
python scripts/make_demo_library.py --out demo_library --clean
export HERMES_EYE_MEMORY_DATA="$PWD/.demo-data"
export HERMES_EYE_MEMORY_EMBEDDING_BACKEND=fallback
export HERMES_EYE_MEMORY_OCR_ENABLED=false
python -m hermes_eye_memory.cli index demo_library
```

PowerShell:

```powershell
python scripts/make_demo_library.py --out demo_library --clean
$env:HERMES_EYE_MEMORY_DATA = "$PWD\.demo-data"
$env:HERMES_EYE_MEMORY_EMBEDDING_BACKEND = "fallback"
$env:HERMES_EYE_MEMORY_OCR_ENABLED = "false"
python -m hermes_eye_memory.cli index demo_library
```

## Script

```bash
# 1. Library overview
python -m hermes_eye_memory.cli stats
python -m hermes_eye_memory.cli timeline --bucket month

# 2. Search
python -m hermes_eye_memory.cli search "red mug"
python -m hermes_eye_memory.cli search "receipt"
python -m hermes_eye_memory.cli search "tag:receipt"

# 3. Duplicates and best shot
python -m hermes_eye_memory.cli duplicates --threshold 4
python -m hermes_eye_memory.cli best --limit 3

# 4. Album
python -m hermes_eye_memory.cli album "receipt" --name receipts --copy

# 5. Receipt report
python -m hermes_eye_memory.cli receipts --format markdown
```

With OCR enabled and `rapidocr-onnxruntime` installed, the two receipt images produce merchant/date/total rows. Without OCR, filename tags still find them and the report lists them with zero totals.

## Screenshot ideas

- Terminal: `stats` followed by `search "red mug"` showing the top result.
- Finder/Explorer: `demo_library` next to `.demo-data/thumbs`.
- Receipt Markdown report open in an editor.
- Hermes chat: "What did I photograph in May 2024?" then `eye_timeline`.
- Optional: camera `eye_look` on a desk with a mug.

Use synthetic demo images only. Do not put personal photos in screenshots.
