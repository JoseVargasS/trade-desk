"""Tabla de órdenes abiertas (panel estilo MEXC).

Es un mixin de `VistaQt` (`qt/ventana.py`).
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QTableWidgetItem, QWidget

from .. import theme as t
from ..bingx import es_condicional
from ..layout import ORDER_ACTION_W, ORDER_COLS, ORDER_PENCILS, ORDER_ROW_H, STATES
from .cells import CeldaLapiz, lineas, tabla
from .formato import cuando
from .style import boton as _boton


class TablaOrdenes:
    """Mixin: pintado de la pestaña Órdenes."""

    def _tabla_ordenes(self):
        columnas = [*ORDER_COLS, ("acciones", "", ORDER_ACTION_W, "w")]
        return tabla(columnas, ORDER_ROW_H)

    # ------------------------------------------------------------------ refresco

    def _pintar_ordenes(self, ordenes):
        tabla = self._tabla_ord
        tabla.setRowCount(len(ordenes))
        for fila, orden in enumerate(ordenes):
            condicional_bingx = es_condicional(orden)
            escala = int(orden.get("_priceScale") or 2)
            lado = int(orden.get("side") or 0)
            largo = lado in (1, 4)
            monto = (
                float(orden.get("vol") or 0)
                * float(orden.get("_contractSize") or 0)
                * float(orden.get("price") or 0)
            )
            tp = float(orden.get("takeProfitPrice") or 0)
            sl = float(orden.get("stopLossPrice") or 0)
            valores = {
                "par": lineas(
                    (orden.get("_name") or orden.get("symbol", ""), 13, True, t.TEXT),
                    ("Perpetual", 10, False, t.MUTED),
                ),
                "fecha": lineas((cuando(orden.get("createTime")), 13, False, t.MUTED)),
                "dir": lineas(
                    (
                        "Compra LONG" if largo else "Venta SHORT",
                        13,
                        False,
                        t.GREEN if largo else t.RED,
                    )
                ),
                "apal": lineas(
                    (f"{int(orden.get('leverage') or 0)}X", 13, True, t.GREEN if largo else t.RED)
                ),
                "monto": lineas((f"{t.fmt_usdt(monto)} USDT", 13, False, t.TEXT)),
                "precio": lineas(
                    (t.fmt_price_exact(float(orden.get("price") or 0), escala), 13, True, t.TEXT)
                ),
                "llenado": lineas(
                    (
                        f"{t.fmt_qty(orden.get('dealVol'))}/{t.fmt_qty(orden.get('vol'))}",
                        13,
                        False,
                        t.MUTED,
                    )
                ),
                "margen": lineas(
                    (f"{t.fmt_usdt(orden.get('orderMargin'))} USDT", 13, True, t.TEXT)
                ),
                "stops": lineas(
                    (
                        f"TP: Last≥{t.fmt_price_exact(tp, escala)}" if tp else "TP: —",
                        13,
                        False,
                        t.GREEN if tp else t.MUTED,
                    ),
                    (
                        f"SL: Last≤{t.fmt_price_exact(sl, escala)}" if sl else "SL: —",
                        13,
                        False,
                        t.RED if sl else t.MUTED,
                    ),
                ),
                "fee": lineas((t.fmt_fee(orden.get("totalFee") or 0), 13, False, t.MUTED)),
                "estado": lineas(
                    (STATES.get(int(orden.get("state") or 0), "Pendiente"), 13, False, t.TEXT)
                ),
            }
            for columna, (clave, _rotulo, _ancho, anclaje) in enumerate(ORDER_COLS):
                item = QTableWidgetItem()
                item.setData(Qt.UserRole, valores.get(clave, lineas(("—", 13, False, t.MUTED))))
                item.setTextAlignment(Qt.AlignRight if anclaje == "e" else Qt.AlignLeft)
                tabla.setItem(fila, columna, item)
                if clave in ORDER_PENCILS and not condicional_bingx:
                    tabla.setCellWidget(
                        fila,
                        columna,
                        CeldaLapiz(
                            valores.get(clave, lineas(("—", 13, False, t.MUTED))),
                            lambda o=orden: self.control.modificar(o),
                            t.ROW_ALT if fila % 2 else t.CARD,
                            vertical=clave == "stops",
                        ),
                    )

            acciones = QWidget()
            fila_acciones = QHBoxLayout(acciones)
            fila_acciones.setContentsMargins(4, 0, 8, 0)
            fila_acciones.setSpacing(6)
            cancelar = _boton("Cancelar", 84, 26, t.INPUT, t.RED)
            cancelar.clicked.connect(lambda _=False, o=orden: self.control.cancelar(o))
            if not condicional_bingx:
                modificar = _boton("Modificar", 84, 26)
                modificar.clicked.connect(lambda _=False, o=orden: self.control.modificar(o))
                fila_acciones.addWidget(modificar)
            fila_acciones.addWidget(cancelar)
            tabla.setCellWidget(fila, len(ORDER_COLS), acciones)
        self._lbl_ordenes.setText(
            f"{len(ordenes)} pendientes" if ordenes else "Sin órdenes pendientes"
        )

    # ----------------------------------------------------------------- historial
