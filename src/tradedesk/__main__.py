"""Arranque de la app: `python -m tradedesk` abre la vista Qt."""

import ctypes
import os


def main():
    if os.name == "nt":
        try:
            # debe ir antes de crear la ventana o la barra de tareas usa el icono de Python
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("tradedesk.mexc.v1")
        except Exception:
            pass
    from .qt.__main__ import main as qt_main

    return qt_main()


if __name__ == "__main__":
    raise SystemExit(main())
