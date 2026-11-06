"""Tabla de posiciones: filas, resumen de bruto/neto y globo de la fee.

Es un mixin de `VistaQt` (`qt/ventana.py`): no guarda estado propio, usa el de la
ventana (`_posiciones`, `_tabla_pos`, `_bocadillo`, `control`).
"""

from datetime import datetime

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtWidgets import QHeaderView, QTableWidgetItem

from .. import theme as t
from ..layout import ACTION_W, PENCIL_COLS, POS_COLS, ROW_H
from ..mexc import fee_desglose, resumen_pnl
from .cells import DETALLE, SUBRAYADO, CeldaLapiz, CeldaPar, lineas, tabla
from .formato import cuando
from .tarjeta import BarraCierre


class TablaPosiciones:
    """Mixin: pintado de la pestaña Posiciones."""

    def _tabla_posiciones(self):
        columnas = [
            ("sel", "", 30, "w"),
            *POS_COLS,
            ("hueco", "", 0, "w"),
            ("acciones", "", ACTION_W, "w"),
        ]
        rejilla = tabla(columnas, ROW_H)
        for indice, columna in enumerate(columnas):
            if columna[0] == "hueco":
                rejilla.horizontalHeader().setSectionResizeMode(indice, QHeaderView.Stretch)
            elif columna[0] == "acciones":
                rejilla.horizontalHeader().setSectionResizeMode(indice, QHeaderView.Fixed)
        return rejilla

    def _seleccionadas(self):
        elegidas = []
        for fila in range(self._tabla_pos.rowCount()):
            item = self._tabla_pos.item(fila, 0)
            if item is None or item.checkState() != Qt.Checked:
                continue
            if fila < len(self._posiciones):
                elegidas.append(self._posiciones[fila])
        return elegidas

    def _cerrar_seleccionadas(self):
        self.control.cerrar_seleccionadas(self._seleccionadas())

    # --------------------------------------------------------------- posiciones

    def _valores_fila(self, position):
        """Datos de cada celda de una posicion: los pinta el delegado o el widget."""
        largo = int(position.get("positionType") or 1) == 1
        cantidad = float(position.get("holdVol") or 0)
        entrada = float(position.get("holdAvgPrice") or 0)
        pnl = float(position.get("unRealizedPnl") or 0)
        tamano = float(position.get("_contractSize") or 0)
        escala = max(2, int(position.get("_priceScale") or 2))
        marca = entrada + (pnl / (cantidad * tamano)) * (1 if largo else -1) if cantidad else 0
        nocional = cantidad * tamano * marca
        detalle = fee_desglose(position)
        proporcion = float(position.get("im") or 0)
        ratio = float(position.get("marginRatio") or 0) * 100
        valores = {
            "par": lineas((position.get("_name") or position.get("symbol", ""), 13, True, t.TEXT)),
            "lado": lineas(
                (
                    f"{position.get('leverage', '')}X {'LONG' if largo else 'SHORT'}",
                    13,
                    True,
                    t.GREEN if largo else t.RED,
                )
            ),
            "apertura": lineas((cuando(position.get("createTime")), 13, False, t.MUTED)),
            "pos": lineas((f"{t.fmt_usdt(nocional)} USDT", 13, True, t.TEXT)),
            "entrada": lineas((t.fmt_price_exact(entrada, escala), 13, False, t.TEXT)),
            "mark": lineas(
                (
                    t.fmt_price_exact(marca, escala),
                    13,
                    False,
                    t.GREEN if (marca > entrada) == largo else t.RED,
                )
            ),
            "liq": lineas(
                (
                    t.fmt_price_exact(float(position.get("liquidatePrice") or 0), escala),
                    13,
                    False,
                    t.GOLD,
                )
            ),
            "ratio": lineas(
                (
                    f"{ratio:.2f}%" if ratio else "—",
                    13,
                    False,
                    t.GOLD if ratio >= 20 else t.TEXT,
                )
            ),
            "margen": lineas((f"{t.fmt_usdt(proporcion)} USDT", 13, True, t.TEXT)),
            "pnl": lineas(
                (f"{t.fmt_pnl(pnl)} USDT", 13, True, t.GREEN if pnl >= 0 else t.RED),
                (
                    f"{pnl / proporcion * 100 if proporcion else 0:+.2f}%",
                    11,
                    False,
                    t.GREEN if pnl >= 0 else t.RED,
                ),
            ),
            "fee": lineas(
                (
                    f"{t.fmt_fee(detalle['total'])} USDT",
                    13,
                    True,
                    t.RED if detalle["total"] else t.MUTED,
                ),
                (
                    f"{t.fmt_share(detalle['total'] / proporcion * 100 if proporcion else 0)}"
                    f" / {t.fmt_share(detalle['total'] / nocional * 100 if nocional else 0)}",
                    11,
                    False,
                    t.MUTED,
                ),
                (
                    f"ahorro {t.fmt_fee(detalle['ahorro'])}" if detalle["ahorro"] > 0 else "",
                    11,
                    False,
                    t.GREEN,
                ),
            ),
            "tpsl": lineas(*self._texto_stops(position, escala)),
        }
        return valores, pnl, largo, detalle, nocional

    @staticmethod
    def _detalle_fee(detalle, nocional=0.0, funding=None, largo=True):
        """Filas del globo de la fee: lo pagado, el próximo funding y el cierre.

        El total es lo **ya cobrado** (comisión + funding), que solo cambia cuando el
        broker lo cobra (funding cada 8 h o al cerrar una parte). El funding próximo
        se muestra con su hora y el importe estimado para que el número no parezca
        congelado.
        """
        filas = [
            ("Comisión pagada (USDT)", t.fmt_fee(detalle["comision"]), t.TEXT),
        ]
        if detalle["funding"] > 0:
            filas.append(("Funding cobrado (USDT)", t.fmt_fee(detalle["funding"]), t.RED))
        filas.append(
            (
                "Fee pagada (USDT)",
                t.fmt_fee(detalle["total"]),
                t.RED if detalle["total"] else t.MUTED,
            )
        )
        if detalle["ahorro"] > 0:
            filas.append(("Fees saved (USDT)", t.fmt_fee(detalle["ahorro"]), t.GREEN))
        if funding and funding.get("proxima") and nocional:
            tasa = float(funding.get("tasa") or 0)
            hora = datetime.fromtimestamp(funding["proxima"]).strftime("%H:%M")
            monto = abs(tasa * nocional)
            paga = (tasa >= 0) == bool(largo)
            filas.append(
                (
                    f"Funding {hora} ({tasa * 100:.4f}%)",
                    f"{'paga' if paga else 'cobra'} {t.fmt_fee(monto)}",
                    t.GOLD,
                )
            )
        if nocional and detalle["comision"]:
            tasa = detalle["comision"] / nocional * 100
            filas.append(
                (f"Al cerrar (taker {tasa:.3f}%)", t.fmt_fee(detalle["comision"]), t.MUTED)
            )
        return tuple(filas)

    def _pintar_posiciones(self, posiciones):
        """Actualiza en sitio; solo recrea filas si cambia el conjunto de posiciones.

        Recrear cada 3 s destruia la barra de cierre y el `%` elegido volvia a
        100, ademas de cerrar el panel del slider que colgaba de ella.
        """
        tabla = self._tabla_pos
        ids = tuple(p.get("positionId") for p in posiciones)
        rehacer = ids != self._firma_pos or tabla.rowCount() != len(posiciones)
        self._firma_pos = ids
        if rehacer:
            tabla.setRowCount(len(posiciones))
        marcadas = {p.get("positionId") for p in self._seleccionadas()}
        for fila, position in enumerate(posiciones):
            valores, pnl, largo, detalle, nocional = self._valores_fila(position)
            fondo = self._fondos.get(
                ((position.get("_exchange") or ""), position.get("symbol") or "")
            )
            tooltip = self._detalle_fee(detalle, nocional, fondo, largo)
            marcada = position.get("positionId") in marcadas
            fondo_fila = t.ROW_ALT if fila % 2 else t.CARD
            if rehacer:
                seleccion = QTableWidgetItem()
                seleccion.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                seleccion.setCheckState(Qt.Checked if marcada else Qt.Unchecked)
                tabla.setItem(fila, 0, seleccion)
            elif tabla.item(fila, 0) is not None:
                tabla.item(fila, 0).setCheckState(Qt.Checked if marcada else Qt.Unchecked)

            for columna, (clave, _rotulo, _ancho, anclaje) in enumerate(POS_COLS, start=1):
                if clave == "par":
                    # par + wordmark del broker (dos lineas, como en MEXC)
                    nombre = position.get("_name") or position.get("symbol", "")
                    exchange = position.get("_exchange") or ""
                    if rehacer:
                        tabla.setCellWidget(fila, columna, CeldaPar(nombre, exchange, fondo_fila))
                    else:
                        tabla.cellWidget(fila, columna).set_datos(nombre, exchange)
                    tabla.cellWidget(fila, columna).set_fondo(fondo_fila)
                elif clave in PENCIL_COLS:
                    if rehacer:
                        tabla.setCellWidget(
                            fila, columna, CeldaLapiz(valores[clave], lambda: None, fondo_fila)
                        )
                    else:
                        tabla.cellWidget(fila, columna).set_partes(valores[clave])
                    # el lapiz tiene que abrir SIEMPRE el dato de esta fila, no el
                    # que habia cuando se creo el widget (por eso reabria el TP viejo)
                    celda = tabla.cellWidget(fila, columna)
                    celda.set_fondo(fondo_fila)
                    celda.set_partes(valores[clave])
                    celda.set_accion(
                        (lambda f=fila: self._editar_tpsl(f))
                        if clave == "tpsl"
                        else (lambda f=fila: self._editar_margen(f))
                    )
                elif rehacer:
                    item = QTableWidgetItem()
                    item.setTextAlignment(Qt.AlignRight if anclaje == "e" else Qt.AlignLeft)
                    item.setData(Qt.UserRole, valores[clave])
                    if clave == "fee":
                        item.setData(SUBRAYADO, True)
                        item.setData(DETALLE, tooltip)
                    tabla.setItem(fila, columna, item)
                else:
                    item = tabla.item(fila, columna)
                    item.setData(Qt.UserRole, valores[clave])
                    if clave == "fee":
                        item.setData(DETALLE, tooltip)

            acciones = len(POS_COLS) + 2
            if rehacer:
                tabla.setCellWidget(
                    fila,
                    acciones,
                    BarraCierre(position, pnl, largo, self.control.cerrar, self.control.reverse),
                )
            else:
                tabla.cellWidget(fila, acciones).actualizar(position, pnl, largo)
            tabla.cellWidget(fila, acciones).set_fondo(fondo_fila)
        self._lbl_abiertas.setText(f"{len(posiciones)} abiertas")
        self._pintar_resumen(posiciones)

    def _pintar_resumen(self, posiciones):
        """Bruto y neto de todas las posiciones, en la barra de la tabla."""
        resumen = resumen_pnl(posiciones)
        bruto = resumen["bruto"]
        neto = resumen["neto"]
        self._lbl_bruto.setText(f"Bruto {t.fmt_pnl(bruto)} USDT")
        self._lbl_neto.setText(f"Neto {t.fmt_pnl(neto)} USDT")
        self._lbl_bruto.setStyleSheet(f"color: {t.GREEN if bruto >= 0 else t.RED};")
        self._lbl_neto.setStyleSheet(f"color: {t.GREEN if neto >= 0 else t.RED};")
        detalle = (
            f"Comisión pagada −{t.fmt_fee(resumen['comision'])}\n"
            f"Funding cobrado −{t.fmt_fee(resumen['funding'])}\n"
            f"Salida estimada (taker) −{t.fmt_fee(resumen['salida'])}\n"
            f"Neto {t.fmt_pnl(neto)} USDT"
        )
        self._lbl_bruto.setToolTip(detalle)
        self._lbl_neto.setToolTip(detalle)

    def _texto_stops(self, position, escala):
        """TP y SL en una linea: `81,000.00 / 71,000.00`, y `--` donde no hay nivel."""
        tp = float(position.get("_tp") or 0)
        sl = float(position.get("_sl") or 0)
        texto_tp = t.fmt_price_exact(tp, escala) if tp else "--"
        texto_sl = t.fmt_price_exact(sl, escala) if sl else "--"
        return (
            (texto_tp, 13, True, t.GREEN if tp else t.MUTED),
            ("/", 13, False, t.MUTED),
            (texto_sl, 13, True, t.RED if sl else t.MUTED),
        )

    # ------------------------------------------------------------------ ordenes

    def _posicion(self, fila):
        """La posicion viva de esa fila (la que llego en el ultimo refresco)."""
        if 0 <= fila < len(self._posiciones):
            return self._posiciones[fila]
        return None

    def _editar_tpsl(self, fila):
        pos = self._posicion(fila)
        if pos:
            self.control.tpsl(pos)

    def _editar_margen(self, fila):
        pos = self._posicion(fila)
        if pos:
            self.control.margen(pos)

    # ------------------------------------------------------------------ tooltip

    def _hover_posiciones(self, indice):
        """Globo de la fee al entrar en la celda, arriba y apuntando a la celda."""
        if indice.column() != self._col_fee:
            self._bocadillo.hide()
            return
        item = self._tabla_pos.item(indice.row(), indice.column())
        filas = item.data(DETALLE) if item else None
        if not filas:
            self._bocadillo.hide()
            return
        caja = self._tabla_pos.visualRect(indice)
        vista = self._tabla_pos.viewport()
        arriba = vista.mapToGlobal(caja.topLeft())
        ancla = QPoint(arriba.x() + caja.width() // 2, arriba.y())
        self._bocadillo.mostrar(ancla, "Fee de la posición", filas)

    def eventFilter(self, objeto, evento):
        if evento.type() == QEvent.Leave and objeto is self._tabla_pos.viewport():
            self._bocadillo.hide()
        return super().eventFilter(objeto, evento)
