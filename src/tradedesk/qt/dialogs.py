"""Fachada de los diálogos: quedan acá los nombres que usan la vista y el port.

Cada diálogo vive en su módulo (`dialogos_base`, `tpsl`, `editor_orden`, `be`,
`panel_brokers`, `port`); este archivo solo reexporta.
"""

from .be import _ListaBe, be_lista
from .dialogos_base import (
    Modal,
    _Claves,
    _Dialogo,
    _Formulario,
    _Puente,
    ask_key,
    confirm,
    form,
    show,
)
from .editor_orden import EditorOrden, editar_orden
from .panel_brokers import PanelBrokers, brokers
from .port import QtPort
from .tpsl import _lineas_pnl, editar_tpsl

__all__ = [
    "EditorOrden",
    "Modal",
    "PanelBrokers",
    "QtPort",
    "_Claves",
    "_Dialogo",
    "_Formulario",
    "_ListaBe",
    "_Puente",
    "_lineas_pnl",
    "ask_key",
    "be_lista",
    "brokers",
    "confirm",
    "editar_orden",
    "editar_tpsl",
    "form",
    "show",
]
