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

    def _pedir_mas_historial(self, boton=None):
        """Trae la página siguiente de cada broker (lo ya visto no se pierde).

        El botón es opcional: el Calendario reutiliza la misma paginación con
        su propio botón.
        """
        boton = boton or self._btn_mas
        boton.setEnabled(False)
        boton.setText("Cargando…")
        threading.Thread(target=self.session.cargar_historial, args=(True,), daemon=True).start()

    def _pintar_historial(self, filas):
        """Una fila por operación: apertura y cierre con su PnL y sus fees."""
        tabla = self._tabla_hist
        barra = tabla.verticalScrollBar()
        previo = barra.value()
        self._lbl_hist.setText(
            f"{len(filas)} operaciones" if filas else "Sin operaciones en el historial"
        )
        identificadores = []
        repeticiones = {}
        for fila in filas:
            clave = str(fila.get("_clave") or "")
            if not clave:
                clave = "|".join(
                    str(fila.get(campo) or "")
                    for campo in ("symbol", "_exchange", "lado", "apertura", "cierre", "qty")
                )
            base = (str(fila.get("_exchange") or ""), clave)
            numero = repeticiones.get(base, 0)
            repeticiones[base] = numero + 1
            identificadores.append((base, numero))

        anteriores = getattr(self, "_historial_ids", [])
        cache = getattr(self, "_historial_cache", {})
        if len(anteriores) != tabla.rowCount():
            anteriores = []
            cache = {}
            tabla.setRowCount(0)
        if identificadores == anteriores and all(
            cache.get(ident) == fila for ident, fila in zip(identificadores, filas, strict=True)
        ):
            barra.setValue(min(previo, barra.maximum()))
            return

        actuales = list(anteriores)
        tabla.setUpdatesEnabled(False)
        try:
            for indice, (ident, fila) in enumerate(zip(identificadores, filas, strict=True)):
                if indice < len(actuales) and actuales[indice] == ident:
                    if cache.get(ident) != fila:
                        self._pintar_fila_historial(tabla, indice, fila)
                    continue
                origen = next(
                    (i for i in range(indice + 1, len(actuales)) if actuales[i] == ident),
                    None,
                )
                if origen is not None:
                    tabla.removeRow(origen)
                    actuales.pop(origen)
                tabla.insertRow(indice)
                actuales.insert(indice, ident)
                self._pintar_fila_historial(tabla, indice, fila)
            while len(actuales) > len(identificadores):
                tabla.removeRow(len(actuales) - 1)
                actuales.pop()
        finally:
            tabla.setUpdatesEnabled(True)

        self._historial_ids = identificadores
        self._historial_cache = {
            ident: fila.copy() for ident, fila in zip(identificadores, filas, strict=True)
        }
        barra.setValue(min(previo, barra.maximum()))

    @staticmethod
    def _pintar_fila_historial(tabla, indice, fila):
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
