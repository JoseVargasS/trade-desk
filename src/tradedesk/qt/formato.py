"""Formato de las celdas que no son números puros: fecha y tamaño en USDT.

No vive en `theme.py` (un tema no formatea fechas) ni dentro de una tabla, porque
lo usan dos pestañas.
"""

from datetime import datetime

from .. import theme as t


def cuando(ms):
    """`createTime` (ms) -> `dd/mm hh:mm`; `—` si el dato no sirve."""
    try:
        return datetime.fromtimestamp(float(ms) / 1000).strftime("%d/%m %H:%M")
    except Exception:
        return "—"


def tamano_usdt(fila):
    """Tamaño de la operación en USDT (cantidad por el precio de entrada)."""
    cantidad = float(fila.get("qty") or fila.get("abierta") or fila.get("cerrada") or 0)
    precio = float(fila.get("entrada") or fila.get("salida") or 0)
    if not (cantidad and precio):
        return "—"
    return f"{t.fmt_usdt(cantidad * precio)} USDT"
