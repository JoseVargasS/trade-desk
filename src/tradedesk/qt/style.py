"""Estilos de la ventana Qt: los mismos tokens de `theme`, en QSS.

Nada de colores literales: si falta un token, se agrega en `theme.py`.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from .. import theme as t
from ..paths import ASSETS

_FAMILIA = None


def cargar_fuentes():
    """Registra los TTF en Qt y deja `theme.UI/NUM` apuntando a la familia real.

    `theme.load_fonts()` usa GDI (`AddFontResourceExW`), que era lo que veia Tk;
    Qt enumera con DirectWrite y no las encuentra, asi que sin esto la ventana
    caia en Tahoma. Se llama antes de crear widgets.
    """
    global _FAMILIA
    for ruta in sorted(ASSETS.joinpath("fonts").glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(ruta))
    _FAMILIA = "Geist" if "Geist" in QFontDatabase.families() else "Segoe UI"
    t.UI = _FAMILIA
    t.NUM = _FAMILIA
    return _FAMILIA


def familia():
    """Familia registrada (o la que pida `theme` si todavia no se cargo)."""
    return _FAMILIA or t.NUM


def fnt(size, bold=False, num=True):
    """Fuente en pixeles (como CustomTkinter), no en puntos.

    Geist va primero y cubre todo lo que muestra la app; Segoe UI y Arial son
    solo el respaldo si los TTF no se pudieron registrar (sin la lista, Qt caia
    en Tahoma). No hacen falta familias CJK: Qt resuelve los glifos que falten.
    """
    fuente = QFont(familia())
    fuente.setFamilies([familia(), "Segoe UI", "Arial"])
    fuente.setPixelSize(int(size))
    fuente.setWeight(QFont.DemiBold if bold else QFont.Normal)
    return fuente


def etiqueta(texto, size=13, bold=False, muted=False, color=None):
    lbl = QLabel(texto)
    lbl.setFont(fnt(size, bold))
    if muted:
        lbl.setProperty("muted", "true")
    if color:
        lbl.setStyleSheet(f"color: {color}; background: transparent;")
    return lbl


def boton(texto, ancho=None, alto=22, fondo=None, color=None, radio=None, size=11, borde=True):
    btn = QPushButton(texto)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setFont(fnt(size))
    fondo = fondo or t.INPUT
    color = color or t.TEXT
    radio = t.R_CHIP if radio is None else radio
    marco = f"1px solid {t.BORDER}" if borde else "0px"
    btn.setStyleSheet(
        f"QPushButton {{ background: {fondo}; color: {color}; border: {marco};"
        f" border-radius: {radio}px; }}"
        f"QPushButton:hover {{ border: 1px solid {t.MUTED}; }}"
        f"QPushButton:disabled {{ color: {t.MUTED}; border-color: {t.BORDER}; }}"
    )
    if ancho:
        btn.setFixedWidth(ancho)
    btn.setFixedHeight(alto)
    return btn


class Segmentado(QWidget):
    """Dos opciones excluyentes en una sola caja, como el CTkSegmentedButton."""

    def __init__(self, opciones, elegida, al_cambiar=None):
        super().__init__()
        self.al_cambiar = al_cambiar
        self.elegida = elegida
        self.setObjectName("seg")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget#seg {{ background: {t.INPUT}; border: 1px solid {t.BORDER};"
            f" border-radius: {t.R_CHIP}px; }}"
        )
        self.botones = {}
        fila = QHBoxLayout(self)
        fila.setContentsMargins(2, 2, 2, 2)
        fila.setSpacing(0)
        for texto in opciones:
            boton_ = QPushButton(texto)
            boton_.setCursor(Qt.PointingHandCursor)
            boton_.setFont(fnt(12))
            boton_.clicked.connect(lambda _=False, cual=texto: self._elegir(cual))
            fila.addWidget(boton_)
            self.botones[texto] = boton_
        self._pintar()

    def _elegir(self, texto):
        self.elegida = texto
        self._pintar()
        if self.al_cambiar:
            self.al_cambiar(texto)

    def _pintar(self):
        for texto, boton_ in self.botones.items():
            activo = texto == self.elegida
            boton_.setStyleSheet(
                f"QPushButton {{ background: {t.SURFACE if activo else 'transparent'};"
                f" color: {t.TEXT if activo else t.MUTED}; border: 0px;"
                f" border-radius: {t.R_CHIP - 2}px; }}"
            )


def qss():
    return f"""
QWidget {{
    color: {t.TEXT};
}}
QMainWindow, QWidget#central {{
    background: {t.BG};
}}
QFrame#surface {{
    background: {t.SURFACE};
    border-radius: 0px;
}}
QFrame#card {{
    background: {t.CARD};
    border: 1px solid {t.BORDER};
    border-radius: {t.R_CARD}px;
}}
QLabel[muted="true"] {{
    color: {t.MUTED};
}}
QLineEdit {{
    background: {t.INPUT};
    border: 1px solid {t.BORDER};
    border-radius: {t.R_CTRL}px;
    padding: 4px 6px;
}}
QScrollArea {{
    background: {t.BG};
    border: 0px;
}}
QScrollArea > QWidget > QWidget {{
    background: {t.BG};
}}
QTabWidget {{
    background: {t.BG};
}}
QTabWidget::pane {{
    background: {t.CARD};
    border: 0px;
}}
QHeaderView {{
    background: {t.SURFACE};
}}
QTableCornerButton::section {{
    background: {t.SURFACE};
    border: 0px;
}}
QTabBar::tab {{
    background: {t.INPUT};
    color: {t.MUTED};
    padding: 6px 14px;
    margin-right: 4px;
    border-radius: {t.R_CHIP}px;
}}
QTabBar::tab:selected {{
    background: {t.SURFACE};
    color: {t.TEXT};
}}
QHeaderView::section {{
    background: {t.SURFACE};
    color: {t.MUTED};
    border: 0px;
    padding: 6px;
}}
QTableView {{
    background: {t.CARD};
    alternate-background-color: {t.ROW_ALT};
    border: 0px;
    gridline-color: {t.BORDER};
    selection-background-color: {t.SURFACE};
}}
QStatusBar {{
    background: {t.BG};
    color: {t.MUTED};
}}
QToolTip {{
    background: {t.CARD};
    color: {t.TEXT};
    border: 1px solid {t.BORDER};
    padding: 6px 8px;
}}
"""


def logo(nombre, alto=22, completo=False):
    """Pixmap del logo del broker a la altura pedida.

    `completo=True` usa el wordmark (`<nombre>_full.svg`, marca + nombre) y si no
    la marca sola; los colores ya vienen normalizados porque Qt no lee variables
    CSS en los SVG.
    """
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtSvg import QSvgRenderer

    sufijo = "_full" if completo else ""
    ruta = ASSETS / f"{nombre}{sufijo}.svg"
    if not ruta.exists():
        return QPixmap()
    render = QSvgRenderer(str(ruta))
    if not render.isValid():
        return QPixmap()
    base = render.defaultSize()
    escala = alto / max(1, base.height())
    imagen = QPixmap(max(1, round(base.width() * escala)), alto)
    imagen.fill(Qt.transparent)
    pintor = QPainter(imagen)
    render.render(pintor)
    pintor.end()
    return imagen


def barra_oscura(ventana):
    """Barra de titulo en el tema oscuro (Windows 10 y 11).

    Hay que llamarla con el HWND ya creado **y** forzar el marco: DWM no repinta
    la barra hasta que algo la invalida, y por eso se veia blanca hasta minimizar
    y volver a abrir.
    """
    try:
        import ctypes

        hwnd = int(ventana.winId())
        dwm = ctypes.windll.dwmapi
        activo = ctypes.c_int(1)
        for atributo in (20, 19):  # 20: Win10 1903+ / Win11, 19: builds anteriores
            if dwm.DwmSetWindowAttribute(hwnd, atributo, ctypes.byref(activo), 4) == 0:
                break
        fondo = ctypes.c_int(0x0A0A0A)  # COLORREF (BGR) = #0A0A0A
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(fondo), 4)  # caption color
        letras = ctypes.c_int(0xEDEAE8)  # #E8EAED en BGR
        dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(letras), 4)  # text color
        # invalida el marco para que Windows lo repinte ya (SWP_FRAMECHANGED)
        banderas = 0x0020 | 0x0002 | 0x0001 | 0x0004 | 0x0010
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, banderas)
    except Exception:
        pass
