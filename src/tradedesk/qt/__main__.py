"""Vista Qt de la mesa: `python -m tradedesk.qt`."""

import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .. import theme
from ..paths import ASSETS
from .style import barra_oscura, cargar_fuentes, fnt, qss
from .view import VistaQt


def main():
    theme.load_fonts()
    app = QApplication(sys.argv)
    cargar_fuentes()
    app.setFont(fnt(13))
    app.setApplicationName("Trade Desk")
    # a nivel de aplicacion: el tooltip es una ventana aparte y no hereda el
    # estilo de la ventana principal (salia con el fondo claro del sistema)
    app.setStyleSheet(qss())
    icono = ASSETS / "icon.ico"
    if icono.exists():
        app.setWindowIcon(QIcon(str(icono)))
    ventana = VistaQt()
    ventana.show()
    # la barra de titulo a veces no se pinta oscura hasta que el marco se
    # invalida; se reintenta con el bucle ya andando
    barra_oscura(ventana)
    QTimer.singleShot(0, lambda: barra_oscura(ventana))
    QTimer.singleShot(150, lambda: barra_oscura(ventana))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
