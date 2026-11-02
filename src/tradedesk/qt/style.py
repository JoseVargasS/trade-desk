"""Estilos de la ventana Qt: los mismos tokens de `theme`, en QSS.

Nada de colores literales: si falta un token, se agrega en `theme.py`.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from .. import theme as t


def fnt(size, bold=False, num=True):
    """Fuente en pixeles (como CustomTkinter), no en puntos."""
    fuente = QFont(t.NUM if num else t.UI)
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
    """Dos opciones excluyentes, como el CTkSegmentedButton de la app."""

    def __init__(self, opciones, elegida, al_cambiar=None):
        super().__init__()
        self.al_cambiar = al_cambiar
        self.elegida = elegida
        self.botones = {}
        fila = QHBoxLayout(self)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(2)
        for texto in opciones:
            boton_ = boton(texto, None, 24, size=10)
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
                f"QPushButton {{ background: {t.SURFACE if activo else t.INPUT};"
                f" color: {t.TEXT if activo else t.MUTED}; border: 1px solid {t.BORDER};"
                f" border-radius: {t.R_CHIP}px; }}"
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
"""
