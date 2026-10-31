"""Design system de trade-desk: color, tipografia, radio y formatos.

Unica fuente de tokens. Ningun otro archivo define colores ni fuentes.
Las reglas de uso estan en AGENTS.md y docs/DESIGN.md.
"""

import ctypes
import os
import tkinter.font as tkfont

from .paths import ASSETS

# --------------------------------------------------------------------- color
BG = "#0A0A0A"
SURFACE = "#121212"
CARD = "#1A1D23"
INPUT = "#1E2026"
LINE = "#2A2E35"
BORDER = "#3A3F47"
TEXT = "#E8EAED"
MUTED = "#9AA0A8"

GREEN = "#1ECB81"
RED = "#F6465D"
GOLD = "#FFD60A"
BLUE = "#2196F3"

# botones llenos: hover un paso mas oscuro y texto legible encima
GREEN_HOVER = "#18B374"
RED_HOVER = "#E03A50"
ON_GREEN = "#04140D"
ON_RED = "#150508"

# acciones destructivas suaves: fondo vino, texto rojo (CERRAR TODO, cancelar)
DANGER_SOFT = "#3A1A1E"
DANGER_SOFT_HOVER = "#4A2226"

GREEN_TINT = "#0F1A15"
RED_TINT = "#1C1214"

SELECT = "#243044"
ACCENT_SOFT = "#26405F"
SELECT_SOFT = "#1B2534"
ROW_ALT = "#16191F"

# ------------------------------------------------------------------ geometria
R_CARD = 12
R_CTRL = 8
R_CHIP = 6
PAD = 8

# ------------------------------------------------------------------ tipografia
FONT_DIR = str(ASSETS / "fonts")
_FALLBACK = {"Geist": "Segoe UI"}

_loaded = False
UI = "Geist"
NUM = "Geist"  # numeros: Geist proporcional, ~19% mas angosto que Geist Mono
SCALE = 1.0  # escala de CustomTkinter (DPI); la fija resolve_fonts


def load_fonts():
    """Registra los TTF en este proceso. No los instala en Windows."""
    global _loaded, UI, NUM
    if _loaded:
        return
    if os.name == "nt" and os.path.isdir(FONT_DIR):
        for name in sorted(os.listdir(FONT_DIR)):
            if name.lower().endswith(".ttf"):
                ctypes.windll.gdi32.AddFontResourceExW(os.path.join(FONT_DIR, name), 0x10, 0)
    _loaded = True


def resolve_fonts(root):
    """Debe llamarse despues de crear el Tk root."""
    global UI, NUM, SCALE
    load_fonts()
    available = set(tkfont.families(root))
    UI = "Geist" if "Geist" in available else _FALLBACK["Geist"]
    NUM = UI
    try:
        SCALE = float(root._get_widget_scaling())
    except Exception:
        SCALE = 1.0
    return UI, NUM


def _px(size):
    """Tamano en pixeles, como CustomTkinter (size negativo = pixeles)."""
    return -max(1, round(abs(size) * SCALE))


def px(length):
    """Largo en pixeles con la escala de CustomTkinter (anchos, altos)."""
    return max(1, round(abs(length) * SCALE))


def ui_font(size, bold=False):
    """Fuente para widgets tk nativos (Label/Frame del sistema), en pixeles."""
    return (UI, _px(size), "bold" if bold else "normal")


def num_font(size, bold=False):
    """Igual que ui_font, para numeros."""
    return (NUM, _px(size), "bold" if bold else "normal")


# ------------------------------------------------------------------- formatos
def fmt_price(value):
    v = float(value or 0)
    a = abs(v)
    if a >= 1000:
        return f"{v:,.1f}"
    if a >= 1:
        return f"{v:,.2f}"
    if a >= 0.01:
        return f"{v:.5f}"
    if a >= 0.0001:
        return f"{v:.6f}"
    return f"{v:.8f}"


def fmt_price_exact(value, scale=2):
    """Precio con los decimales del contrato (priceScale): 2,246.39.

    fmt_price recorta a 1 decimal desde 1000 y eso no sirve para una orden
    limite: lo que se ve tiene que ser lo que se envia.
    """
    return f"{float(value or 0):,.{max(0, int(scale or 0))}f}"


def fmt_pnl(value):
    return f"{float(value or 0):+,.4f}"


def fmt_usdt(value, sign=False):
    v = float(value or 0)
    return f"{v:+,.2f}" if sign else f"{v:,.2f}"


def fmt_fee(value):
    return f"{float(value or 0):.4f}"


def fmt_share(value):
    """Parte de un total, sin signo y a 2 decimales: 0.20%."""
    v = abs(float(value or 0))
    if 0 < v < 0.01:
        return "<0.01%"
    return f"{v:.2f}%"


def fmt_qty(value):
    v = float(value or 0)
    if v == int(v):
        return f"{int(v):,}"
    return f"{v:,.4f}".rstrip("0").rstrip(".")


def fmt_pct(value):
    return f"{float(value or 0):+.2f}%"
