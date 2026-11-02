"""Vista Qt de la mesa: `python -m tradedesk.qt`."""

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .. import theme
from ..paths import ASSETS
from .view import VistaQt


def main():
    theme.load_fonts()
    app = QApplication(sys.argv)
    app.setApplicationName("Trade Desk")
    icono = ASSETS / "icon.ico"
    if icono.exists():
        app.setWindowIcon(QIcon(str(icono)))
    ventana = VistaQt()
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
