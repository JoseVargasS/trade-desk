"""Tabla del historial: una fila por operación, con su neto.

Es un mixin de `VistaQt` (`qt/ventana.py`).
"""

import threading

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem

from .. import theme as t
from ..layout import OPER_COLS
from ..pnl import neto_operacion
from .cells import CeldaPar, lineas
from .formato import cuando, tamano_usdt


class TablaHistorial:
    """Mixin: pintado de la pestaña Historial."""

    def _pedir_mas_historial(self):
        """Trae la página siguiente de cada broker (lo ya visto no se pierde)."""
        self._btn_mas.setEnabled(False)
        self._btn_mas.setText("Cargando…")
        threading.Thread(target=self.session.cargar_historial, args=(True,), daemon=True).start()

    def _pintar_historial(self, filas):
        """Una fila por operación: apertura y cierre con su PnL y sus fees."""
        tabla = self._tabla_hist
        barra = tabla.verticalScrollBar()
        # el refresco de 15 s no puede devolver la vista al principio
        previo = barra.value()
        self._lbl_hist.setText(
            f"{len(filas)} operaciones" if filas else "Sin operaciones en el historial"
        )
        tabla.setRowCount(len(filas))
        for indice, fila in enumerate(filas):
            pnl = float(fila.get("pnl") or 0)
            fee = float(fila.get("fee") or 0)
            neto = neto_operacion(pnl, fee)
            estado = fila.get("estado") or ""
            cierre = fila.get("cierre") or 0
            lado = fila.get("lado") or "—"
            valores = {
                "apertura": lineas((cuando(fila.get("apertura")), 12, False, t.MUTED)),
                "cierre": lineas((cuando(cierre) if cierre else "—", 12, False, t.MUTED)),
                "lado": lineas((lado, 12, True, t.GREEN if lado == "LONG" else t.RED)),
                "qty": lineas((tamano_usdt(fila), 12, False, t.TEXT)),
                "entrada": lineas(
                    (
                        t.fmt_price(fila.get("entrada")) if fila.get("entrada") else "—",
                        12,
                        False,
                        t.TEXT if fila.get("entrada") else t.MUTED,
                    )
                ),
                "salida": lineas(
                    (
                        t.fmt_price(fila.get("salida")) if fila.get("salida") else "—",
                        12,
                        False,
                        t.TEXT if fila.get("salida") else t.MUTED,
                    )
                ),
                "pnl": lineas((t.fmt_pnl(pnl), 12, False, t.GREEN if pnl >= 0 else t.RED)),
                "fee": lineas((t.fmt_fee(fee), 12, False, t.RED if fee > 0 else t.MUTED)),
                "neto": lineas((t.fmt_pnl(neto), 12, True, t.GREEN if neto >= 0 else t.RED)),
                "estado": lineas(
                    (
                        estado,
                        12,
                        False,
                        t.GREEN
                        if estado == "Cerrada"
                        else (t.GOLD if estado == "Parcial" else t.MUTED),
                    )
                ),
            }
            for columna, (clave, _rotulo, _ancho, anclaje) in enumerate(OPER_COLS):
                if clave == "par":
                    # par + wordmark del broker, igual que en posiciones
                    tabla.setCellWidget(
                        indice,
                        columna,
                        CeldaPar(
                            fila.get("symbol", ""),
                            fila.get("_exchange") or "",
                            t.ROW_ALT if indice % 2 else t.CARD,
                            compacta=True,
                        ),
                    )
                    continue
                item = QTableWidgetItem()
                item.setData(Qt.UserRole, valores[clave])
                item.setTextAlignment(Qt.AlignRight if anclaje == "e" else Qt.AlignLeft)
                tabla.setItem(indice, columna, item)
        barra.setValue(min(previo, barra.maximum()))
