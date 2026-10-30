"""Design system de trade-desk: color, tipografia, radio y formatos.

Unica fuente de tokens. Ningun otro archivo define colores ni fuentes.
Las reglas de uso estan en AGENTS.md y docs/DESIGN.md.
"""
import ctypes
import os
import tkinter.font as tkfont

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
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
_FALLBACK = {"Geist": "Segoe UI"}

_loaded = False
UI = "Geist"
NUM = "Geist"   # numeros: Geist proporcional, ~19% mas angosto que Geist Mono


def load_fonts():
    """Registra los TTF en este proceso. No los instala en Windows."""
    global _loaded, UI, NUM
    if _loaded:
        return
    if os.name == "nt" and os.path.isdir(FONT_DIR):
        for name in sorted(os.listdir(FONT_DIR)):
            if name.lower().endswith(".ttf"):
                ctypes.windll.gdi32.AddFontResourceExW(
                    os.path.join(FONT_DIR, name), 0x10, 0)
    _loaded = True


def resolve_fonts(root):
    """Debe llamarse despues de crear el Tk root."""
    global UI, NUM
    load_fonts()
    available = set(tkfont.families(root))
    UI = "Geist" if "Geist" in available else _FALLBACK["Geist"]
    NUM = UI
    return UI, NUM


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


def fmt_pnl(value):
    return f"{float(value or 0):+,.4f}"


def fmt_usdt(value, sign=False):
    v = float(value or 0)
    return f"{v:+,.2f}" if sign else f"{v:,.2f}"


def fmt_fee(value):
    return f"{float(value or 0):.4f}"


def fmt_qty(value):
    v = float(value or 0)
    if v == int(v):
        return f"{int(v):,}"
    return f"{v:,.4f}".rstrip("0").rstrip(".")


def fmt_pct(value):
    return f"{float(value or 0):+.2f}%"
