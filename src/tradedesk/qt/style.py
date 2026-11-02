"""Estilos de la ventana Qt: los mismos tokens de `theme`, en QSS.

Nada de colores literales: si falta un token, se agrega en `theme.py`.
"""

from PySide6.QtGui import QFont

from .. import theme as t


def fnt(size, bold=False, num=True):
    """Fuente en pixeles (como CustomTkinter), no en puntos."""
    fuente = QFont(t.NUM if num else t.UI)
    fuente.setPixelSize(int(size))
    fuente.setWeight(QFont.DemiBold if bold else QFont.Normal)
    return fuente


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
