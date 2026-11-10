"""Create a small, safe photo library for demos and screenshots.

Usage:
    python scripts/make_demo_library.py --out demo_library

The images are synthetic. No personal photos are read or written.
"""

from __future__ import annotations

import argparse
import os
import shutil
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def font(size: int):
    for name in ("arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def gradient(size, top, bottom):
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    width, height = size
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3))
        draw.line([(0, y), (width, y)], fill=color)
    return image


def beach(path: Path) -> None:
    image = gradient((960, 640), (255, 190, 120), (40, 90, 160))
    draw = ImageDraw.Draw(image)
    draw.ellipse((650, 90, 810, 250), fill=(255, 236, 160))
    draw.rectangle((0, 400, 960, 640), fill=(22, 74, 122))
    for y in range(410, 640, 18):
        draw.line((0, y, 960, y), fill=(30, 92, 145), width=3)
    draw.polygon([(0, 640), (300, 390), (620, 640)], fill=(226, 198, 150))
    image.save(path, quality=92)


def mug(path: Path) -> None:
    image = gradient((800, 600), (238, 231, 220), (200, 190, 178))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 430, 800, 600), fill=(166, 132, 96))
    draw.ellipse((250, 250, 550, 500), fill=(190, 32, 38), outline=(120, 20, 24), width=6)
    draw.ellipse((470, 300, 620, 430), outline=(190, 32, 38), width=26)
    draw.ellipse((300, 280, 500, 360), fill=(92, 18, 22))
    image.save(path, quality=92)


def cat(path: Path) -> None:
    image = gradient((900, 620), (236, 240, 244), (198, 208, 218))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 470, 900, 620), fill=(96, 110, 126))
    draw.ellipse((300, 360, 640, 560), fill=(70, 72, 78))
    draw.ellipse((380, 230, 560, 410), fill=(70, 72, 78))
    draw.polygon([(390, 250), (420, 160), (460, 245)], fill=(70, 72, 78))
    draw.polygon([(480, 245), (520, 160), (550, 250)], fill=(70, 72, 78))
    draw.ellipse((420, 290, 448, 318), fill=(238, 220, 120))
    draw.ellipse((492, 290, 520, 318), fill=(238, 220, 120))
    draw.ellipse((466, 330, 486, 350), fill=(220, 140, 150))
    image.save(path, quality=92)


def garden(path: Path) -> None:
    image = gradient((900, 620), (186, 224, 246), (100, 160, 92))
    draw = ImageDraw.Draw(image)
    for x in range(0, 900, 40):
        draw.line((x, 360, x + 30, 620), fill=(52, 118, 60), width=10)
    for x, y, color in [
        (140, 430, (230, 90, 120)),
        (260, 500, (240, 190, 70)),
        (420, 390, (250, 250, 250)),
        (600, 470, (150, 90, 210)),
        (760, 420, (240, 120, 70)),
    ]:
        for angle in range(0, 360, 60):
            draw.ellipse((x - 28, y - 28, x + 28, y + 28), fill=color)
        draw.ellipse((x - 10, y - 10, x + 10, y + 10), fill=(250, 220, 90))
    image.save(path, quality=92)


def receipt(path: Path, store: str, date: str, lines: list[tuple[str, str]], total: str) -> None:
    image = Image.new("RGB", (720, 980), (250, 248, 242))
    draw = ImageDraw.Draw(image)
    title_font = font(42)
    body = font(28)
    mono = font(26)
    draw.text((48, 46), store, fill=(28, 28, 28), font=title_font)
    draw.text((48, 110), date, fill=(70, 70, 70), font=body)
    draw.line((48, 160, 672, 160), fill=(150, 150, 150), width=2)
    y = 196
    for label, amount in lines:
        draw.text((48, y), label, fill=(40, 40, 40), font=mono)
        draw.text((560, y), amount, fill=(40, 40, 40), font=mono)
        y += 52
    draw.line((48, y + 10, 672, y + 10), fill=(150, 150, 150), width=2)
    draw.text((48, y + 34), "TOTAL", fill=(20, 20, 20), font=title_font)
    draw.text((520, y + 34), total, fill=(20, 20, 20), font=title_font)
    draw.text((48, y + 120), "Paid by card", fill=(80, 80, 80), font=body)
    draw.text((48, y + 170), "Thank you", fill=(80, 80, 80), font=body)
    image.save(path)


def notes(path: Path) -> None:
    image = Image.new("RGB", (900, 620), (252, 251, 246))
    draw = ImageDraw.Draw(image)
    draw.text((60, 56), "Project Atlas", fill=(28, 42, 66), font=font(54))
    draw.text((60, 140), "Launch checklist", fill=(40, 60, 80), font=font(34))
    for index, line in enumerate(
        [
            "1. Ship the visual memory demo",
            "2. Record the 90 second walkthrough",
            "3. Post the video and tag the team",
            "4. Submit the catalog entry",
        ]
    ):
        draw.text((80, 220 + index * 70), line, fill=(60, 64, 70), font=font(28))
    draw.line((60, 190, 840, 190), fill=(180, 190, 200), width=2)
    image.save(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="demo_library")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    root = Path(args.out).expanduser().resolve()
    if args.clean and root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    beach(root / "beach-sunset.jpg")
    shutil.copyfile(root / "beach-sunset.jpg", root / "beach-sunset-copy.jpg")
    mug(root / "red-mug.jpg")
    cat(root / "cat-on-sofa.jpg")
    garden(root / "garden-flowers.jpg")
    notes(root / "project-atlas-notes.png")
    receipt(
        root / "green-market-receipt.png",
        "GREEN MARKET",
        "12 May 2024",
        [("Apples", "4.00"), ("Sourdough", "3.25"), ("Coffee", "8.75"), ("Olive oil", "8.50")],
        "24.50",
    )
    receipt(
        root / "blue-cafe-receipt.png",
        "BLUE CAFE",
        "03 Jun 2024",
        [("Latte", "4.25"), ("Croissant", "3.50"), ("Tip", "1.00")],
        "8.75",
    )

    dates = {
        "beach-sunset.jpg": "2024-05-12",
        "beach-sunset-copy.jpg": "2024-05-12",
        "red-mug.jpg": "2024-06-03",
        "cat-on-sofa.jpg": "2024-06-18",
        "garden-flowers.jpg": "2024-07-04",
        "project-atlas-notes.png": "2024-07-21",
        "green-market-receipt.png": "2024-05-12",
        "blue-cafe-receipt.png": "2024-06-03",
    }
    for name, day in dates.items():
        stamp = datetime.fromisoformat(day + "T12:00:00").timestamp()
        os.utime(root / name, (stamp, stamp))

    print(f"demo library ready: {root}")
    print(f"{len(list(root.glob('*')))} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
