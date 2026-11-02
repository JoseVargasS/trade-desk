"""Abre la vista Qt de solo lectura: `python -m tradedesk.qt`.

Es una ventana de comprobacion mientras se hace el port: pinta las tarjetas, las
posiciones y las ordenes reales, pero **no envia ninguna orden**.
"""

import sys

from PySide6.QtWidgets import QApplication

from .. import theme
from .view import VistaQt


def main():
    theme.load_fonts()
    app = QApplication(sys.argv)
    ventana = VistaQt()
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
