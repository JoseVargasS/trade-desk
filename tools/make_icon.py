"""Genera icon.ico / icon.png en src/tradedesk/assets.

Solo hace falta al cambiar el icono: python tools/make_icon.py
Requiere Pillow (dependencia de desarrollo, no de ejecucion).
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tradedesk.paths import ASSETS  # noqa: E402

SIZE = 1024
BG = "#1A1D23"
RING = "#2A2E35"
GREEN = "#1ECB81"
RED = "#F6465D"


def build():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=224, fill=BG, outline=RING, width=10)

    def candle(cx, top, bottom, wick_top, wick_bottom, color):
        d.line([(cx, wick_top), (cx, wick_bottom)], fill=color, width=26)
        d.rounded_rectangle((cx - 78, top, cx + 78, bottom), radius=26, fill=color)

    candle(352, 430, 720, 330, 800, GREEN)
    candle(672, 300, 560, 210, 660, RED)
    return img


def main():
    big = build()
    big.save(
        ASSETS / "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    big.resize((256, 256), Image.LANCZOS).save(ASSETS / "icon.png")
    print("icon.ico e icon.png generados en", ASSETS)


if __name__ == "__main__":
    main()
