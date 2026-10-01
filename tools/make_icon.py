"""Génère gazefocus.ico : l'œil de l'icône de notification, en toutes tailles.

    python tools/make_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024  # dessiné en grand puis réduit, pour des bords lisses
GREEN = (80, 220, 120)


def eye() -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    s = SIZE / 64
    draw.ellipse((2 * s, 14 * s, 62 * s, 50 * s), fill=(245, 245, 245), outline=(40, 40, 40),
                 width=int(2.5 * s))
    draw.ellipse((20 * s, 20 * s, 44 * s, 44 * s), fill=GREEN)
    draw.ellipse((27 * s, 27 * s, 37 * s, 37 * s), fill=(20, 20, 20))
    return image


if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent / "gazefocus.ico"
    eye().save(target, sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])
    print(target)
