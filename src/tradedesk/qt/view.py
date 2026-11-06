"""Fachada de la ventana Qt: la clase vive en `qt/ventana.py`.

Se deja este módulo para no tocar los imports de `qt/__main__.py` ni de
`tools/smoke_live.py`.
"""

from .ventana import VistaQt, build_main_window

__all__ = ["VistaQt", "build_main_window"]
