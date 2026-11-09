"""Pestaña Calendario: un mes en cuadrícula con el resultado de cada día.

Es un mixin de `VistaQt` (`qt/ventana.py`). Toda la agregación vive en
`tradedesk/calendario.py`: acá solo se pinta.

El calendario no pide nada a la red: usa las mismas filas del historial que
pinta la pestaña Historial (el archivo local fusionado con el broker).
"""

from calendar import monthrange
from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import calendario as cal
from .. import paths
from .. import theme as t
from ..brokers import TITULOS
from ..layout import CAL_ALTO_CABECERA, CAL_ALTO_DIA, CAL_ANCHO_DIA, CAL_COLS, CAL_PANEL_W
from ..pnl import neto_operacion
from .calendario_widgets import CurvaMes, DelegadoMes
from .cells import CeldaPar, Spinner, lineas, tabla
from .formato import cuando
from .style import boton as _boton
from .style import etiqueta as _etiqueta
from .style import logo, menu_estilo


class PestanaCalendario:
    """Mixin: la pestaña Calendario (mes, métricas del período y detalle del día)."""

    # ------------------------------------------------------------------ armado
    def _armar_calendario(self):
        """Arma la pestaña completa y devuelve el widget."""
        hoy = date.today()
        self._cal_filas = []
        self._cal_anio = hoy.year
        self._cal_mes = hoy.month
        self._cal_broker = ""
        self._cal_par = ""
        self._cal_dia = None
        self._cal_ocultar = False

        contenido = QWidget()
        raiz = QVBoxLayout(contenido)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(8)
        raiz.addLayout(self._cal_barra())
        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(12)
        cuerpo.addWidget(self._cal_cuadricula(), 0)
        cuerpo.addWidget(self._cal_panel(), 0)
        # el detalle ocupa el espacio libre de la derecha: sin bajar la vista
        cuerpo.addWidget(self._cal_detalle(), 1)
        raiz.addLayout(cuerpo)
        raiz.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(contenido)
        self._cal_scroll = scroll
        return scroll

    def _cal_barra(self):
        fila = QHBoxLayout()
        fila.setSpacing(5)

        anterior = _boton("‹", 28, 26)
        anterior.clicked.connect(lambda: self._cal_mover_mes(-1))
        fila.addWidget(anterior)
        self._lbl_mes = _etiqueta("", 13, True)
        self._lbl_mes.setMinimumWidth(110)
        self._lbl_mes.setAlignment(Qt.AlignCenter)
        fila.addWidget(self._lbl_mes)
        siguiente = _boton("›", 28, 26)
        siguiente.clicked.connect(lambda: self._cal_mover_mes(1))
        fila.addWidget(siguiente)

        self._btn_anio_ant = _boton("‹", 24, 26)
        self._btn_anio_ant.clicked.connect(lambda: self._cal_mover_anio(-1))
        fila.addWidget(self._btn_anio_ant)
        self._lbl_anio = _etiqueta("", 13, True)
        self._lbl_anio.setAlignment(Qt.AlignCenter)
        self._lbl_anio.setMinimumWidth(40)
        fila.addWidget(self._lbl_anio)
        self._btn_anio_sig = _boton("›", 24, 26)
        self._btn_anio_sig.clicked.connect(lambda: self._cal_mover_anio(1))
        fila.addWidget(self._btn_anio_sig)

        hoy = _boton("Hoy", 58, 26)
        hoy.clicked.connect(self._cal_hoy)
        fila.addWidget(hoy)
        fila.addSpacing(10)

        self._btn_broker = _boton("Broker: Todos", 130, 26)
        self._btn_broker.clicked.connect(self._cal_menu_broker)
        fila.addWidget(self._btn_broker)
        self._btn_par = _boton("Par: Todos", 130, 26)
        self._btn_par.clicked.connect(self._cal_menu_par)
        fila.addWidget(self._btn_par)

        fila.addStretch(1)
        self._btn_montos = _boton("Ocultar montos", 120, 26)
        self._btn_montos.clicked.connect(self._cal_alternar_montos)
        fila.addWidget(self._btn_montos)
        self._btn_csv = _boton("Exportar CSV", 110, 26)
        self._btn_csv.clicked.connect(self._cal_exportar)
        fila.addWidget(self._btn_csv)
        self._btn_mas_cal = _boton("Cargar más historial", 165, 26)
        self._btn_mas_cal.clicked.connect(lambda: self._pedir_mas_historial(self._btn_mas_cal))
        fila.addWidget(self._btn_mas_cal)
        self._spin_cal = Spinner(14)
        fila.addWidget(self._spin_cal, 0, Qt.AlignVCenter)
        self._lbl_cargando_cal = _etiqueta("Cargando…", 10, muted=True)
        self._lbl_cargando_cal.hide()
        fila.addWidget(self._lbl_cargando_cal)
        return fila

    def _cal_cuadricula(self):
        """El mes como tabla: una superficie, separadores de pelo, sin cajas."""
        rejilla = QTableWidget(0, 7)
        rejilla.setHorizontalHeaderLabels(list(cal.DIAS))
        for columna in range(7):
            rejilla.horizontalHeaderItem(columna).setTextAlignment(Qt.AlignCenter)
        rejilla.verticalHeader().setVisible(False)
        rejilla.verticalHeader().setDefaultSectionSize(CAL_ALTO_DIA)
        rejilla.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        rejilla.horizontalHeader().setDefaultSectionSize(CAL_ANCHO_DIA)
        rejilla.horizontalHeader().setFixedHeight(CAL_ALTO_CABECERA)
        rejilla.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        rejilla.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        rejilla.setFixedWidth(7 * CAL_ANCHO_DIA + 2 * rejilla.frameWidth() + 2)
        rejilla.setShowGrid(True)
        rejilla.setAlternatingRowColors(False)
        rejilla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        rejilla.setSelectionMode(QAbstractItemView.NoSelection)
        rejilla.setFocusPolicy(Qt.NoFocus)
        rejilla.setWordWrap(False)
        rejilla.setItemDelegate(DelegadoMes(rejilla))
        rejilla.setStyleSheet(
            f"QTableView {{ background: {t.SURFACE}; gridline-color: {t.LINE};"
            f" border: 1px solid {t.LINE}; }}"
            f"QHeaderView::section {{ background: {t.SURFACE}; color: {t.MUTED};"
            f" border: 0px; border-bottom: 1px solid {t.LINE}; padding: 4px; }}"
        )
        rejilla.cellClicked.connect(self._cal_click)
        self._cal_grilla = rejilla
        return rejilla

    def _cal_panel(self):
        panel = QWidget()
        panel.setFixedWidth(CAL_PANEL_W)
        columna = QVBoxLayout(panel)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(6)
        columna.addWidget(self._cal_tarjeta_neto())
        columna.addWidget(self._cal_tarjeta_resumen())
        columna.addStretch(1)
        return panel

    @staticmethod
    def _cal_tarjeta(titulo):
        """Una tarjeta del panel: etiqueta arriba, una columna debajo."""
        caja = QFrame()
        caja.setObjectName("cal_tarjeta")
        caja.setStyleSheet(
            f"QFrame#cal_tarjeta {{ background: {t.CARD}; border: 1px solid {t.LINE};"
            f" border-radius: {t.R_CTRL}px; }}"
        )
        columna = QVBoxLayout(caja)
        columna.setContentsMargins(10, 8, 10, 8)
        columna.setSpacing(1)
        columna.addWidget(_etiqueta(titulo, 10, muted=True))
        return caja, columna

    def _cal_tarjeta_neto(self):
        caja, columna = self._cal_tarjeta("Neto del mes")
        self._cal_lbl_neto = _etiqueta("—", 18, True)
        self._cal_lbl_neto_sub = _etiqueta("", 10, muted=True)
        self._curva = CurvaMes()
        columna.addWidget(self._cal_lbl_neto)
        columna.addWidget(self._cal_lbl_neto_sub)
        columna.addWidget(self._curva)
        return caja

    def _cal_tarjeta_resumen(self):
        """Métricas, brokers y semanas en una tarjeta: el área de pestañas es
        de ~400 px con la ventana de 1000 px y tres tarjetas no entraban."""
        caja, columna = self._cal_tarjeta("Resumen del mes")
        self._cal_valores = {}
        for clave, nombre in (
            ("mejor", "Mejor día"),
            ("peor", "Peor día"),
            ("profit", "Profit factor"),
            ("drawdown", "Drawdown máx."),
            ("rachas", "Rachas"),
            ("fees", "Fees totales"),
        ):
            fila = QHBoxLayout()
            fila.setSpacing(8)
            fila.addWidget(_etiqueta(nombre, 10, muted=True))
            fila.addStretch(1)
            valor = _etiqueta("—", 12, True)
            fila.addWidget(valor)
            self._cal_valores[clave] = valor
            columna.addLayout(fila)

        separador = QFrame()
        separador.setFixedHeight(1)
        separador.setStyleSheet(f"background: {t.LINE};")
        columna.addWidget(separador)

        contenedor = QWidget()
        self._lista_brokers = QVBoxLayout(contenedor)
        self._lista_brokers.setContentsMargins(0, 4, 0, 0)
        self._lista_brokers.setSpacing(3)
        columna.addWidget(contenedor)

        self._lbl_semanas = _etiqueta("", 10, muted=True)
        self._lbl_semanas.setWordWrap(True)
        columna.addWidget(self._lbl_semanas)

        self._lbl_nota = _etiqueta("Neto = PnL − comisión. No incluye el funding.", 10, muted=True)
        columna.addWidget(self._lbl_nota)
        columna.addStretch(1)
        return caja

    def _cal_detalle(self):
        caja = QWidget()
        columna = QVBoxLayout(caja)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(4)
        self._lbl_detalle = _etiqueta("", 11, muted=True)
        columna.addWidget(self._lbl_detalle)
        self._tabla_cal = tabla(CAL_COLS, 32)
        columna.addWidget(self._tabla_cal, 1)
        return caja

    @staticmethod
    def _vaciar(layout):
        while layout.count():
            hijo = layout.takeAt(0)
            widget = hijo.widget()
            if widget is not None:
                widget.deleteLater()

    # ------------------------------------------------------------------ pintado
    def _pintar_calendario(self, filas):
        """Llega el historial (archivo + broker): se guarda y se repinta."""
        self._cal_filas = list(filas or [])
        if not hasattr(self, "_cal_grilla"):
            return
        self._cal_pintar()

    def _cal_filtradas(self):
        return cal.filtrar(self._cal_filas, self._cal_broker or None, self._cal_par or None)

    def _cal_monto(self, texto):
        return "••••" if self._cal_ocultar else texto

    def _cal_pintar(self):
        """Repinta el mes, las métricas y el detalle."""
        filtradas = self._cal_filtradas()
        dias = cal.por_dia(filtradas)
        self._cal_pintar_grilla(dias)
        self._cal_pintar_panel(filtradas, dias)
        self._cal_pintar_detalle(filtradas)

    def _cal_pintar_grilla(self, dias):
        rejilla = self._cal_grilla
        celdas = cal.dias_del_mes(self._cal_anio, self._cal_mes)
        filas = len(celdas) // 7
        if rejilla.rowCount() != filas:
            rejilla.setRowCount(filas)
            # altura fija: sin esto el QScrollArea estira la tabla y las filas
            # crecen hasta llenar el panel de al lado
            rejilla.setFixedHeight(CAL_ALTO_CABECERA + filas * CAL_ALTO_DIA + 4)
        hoy = date.today()
        for indice, fecha in enumerate(celdas):
            fila, columna = divmod(indice, 7)
            item = rejilla.item(fila, columna)
            if item is None:
                item = QTableWidgetItem()
                rejilla.setItem(fila, columna, item)
            dentro = fecha.year == self._cal_anio and fecha.month == self._cal_mes
            info = dias.get(fecha) if dentro else None
            operaciones = info["n"] if info else 0
            neto = info["neto"] if info else 0.0
            item.setData(
                Qt.UserRole,
                {
                    "dia": fecha.day if dentro else None,
                    "neto": neto,
                    "operaciones": operaciones,
                    "hoy": dentro and fecha == hoy,
                    "seleccionado": dentro and fecha == self._cal_dia,
                    "oculto": self._cal_ocultar,
                },
            )
            item.setToolTip(self._cal_tooltip(fecha, dentro, operaciones, neto))

    def _cal_tooltip(self, fecha, dentro, operaciones, neto):
        """El resumen del día sale de la celda: queda en el tooltip."""
        if not dentro:
            return ""
        dia = f"{fecha.day:02d} {cal.MESES[fecha.month - 1][:3]}"
        if not operaciones:
            return f"{dia} · sin operaciones"
        cuenta = f"{operaciones} operaciones" if operaciones != 1 else "1 operación"
        if self._cal_ocultar:
            return f"{dia} · {cuenta}"
        return f"{dia} · {cuenta} · {t.fmt_pnl(neto)}"

    def _cal_pintar_panel(self, filtradas, dias):
        mes_filas = cal.en_mes(filtradas, self._cal_anio, self._cal_mes)
        metricas = cal.metricas(mes_filas)
        total = cal.resumen(dias, self._cal_anio, self._cal_mes)
        self._lbl_mes.setText(cal.MESES[self._cal_mes - 1].capitalize())
        self._lbl_anio.setText(str(self._cal_anio))

        neto = total["neto"]
        self._cal_lbl_neto.setText(self._cal_monto(t.fmt_pnl(neto)))
        self._cal_lbl_neto.setStyleSheet(
            f"color: {t.GREEN if neto >= 0 else t.RED}; background: transparent;"
        )
        operaciones = metricas["operaciones"]
        self._cal_lbl_neto_sub.setText(
            f"{operaciones} operacion{'es' if operaciones != 1 else ''} · "
            f"{t.fmt_share(metricas['win_rate'] * 100)} win rate"
        )

        valores = self._cal_valores
        valores["mejor"].setText(self._cal_monto(self._cal_dia_texto(metricas["mejor_dia"])))
        valores["mejor"].setStyleSheet(f"color: {t.GREEN}; background: transparent;")
        valores["peor"].setText(self._cal_monto(self._cal_dia_texto(metricas["peor_dia"])))
        valores["peor"].setStyleSheet(f"color: {t.RED}; background: transparent;")
        factor = metricas["profit_factor"]
        if factor is None:
            valores["profit"].setText("—")
        elif factor == float("inf"):
            valores["profit"].setText("∞")
        else:
            valores["profit"].setText(t.fmt_price(factor))
        ganadoras = metricas["racha_ganadora"]
        perdedoras = metricas["racha_perdedora"]
        valores["rachas"].setText(
            f"{ganadoras} ganadora{'s' if ganadoras != 1 else ''} / "
            f"{perdedoras} perdedora{'s' if perdedoras != 1 else ''}"
        )
        valores["drawdown"].setText(self._cal_monto(t.fmt_pnl(metricas["drawdown"])))
        valores["drawdown"].setStyleSheet(f"color: {t.RED}; background: transparent;")
        valores["fees"].setText(self._cal_monto(t.fmt_fee(metricas["fee"])))

        self._vaciar(self._lista_brokers)
        if metricas["por_broker"]:
            for broker, info in sorted(metricas["por_broker"].items()):
                fila = QHBoxLayout()
                fila.setSpacing(6)
                marca = QLabel()
                marca.setPixmap(logo(broker, 11, completo=True))
                fila.addWidget(marca)
                fila.addWidget(_etiqueta(str(info["n"]), 10, muted=True))
                fila.addStretch(1)
                color = t.GREEN if info["neto"] >= 0 else t.RED
                fila.addWidget(
                    _etiqueta(self._cal_monto(t.fmt_pnl(info["neto"])), 12, True, color=color)
                )
                self._lista_brokers.addLayout(fila)
        else:
            self._lista_brokers.addWidget(_etiqueta("—", 12, muted=True))

        semanas = [s for s in cal.semanas(dias, self._cal_anio, self._cal_mes) if s["n"]]
        if not semanas:
            self._lbl_semanas.setText("")
        else:
            partes = []
            for semana in semanas:
                texto = "••••" if self._cal_ocultar else t.fmt_pnl(semana["neto"])
                color = t.GREEN if semana["neto"] >= 0 else t.RED
                partes.append(f'<span style="color:{color}">{semana["etiqueta"]} {texto}</span>')
            self._lbl_semanas.setText("  ·  ".join(partes))
            self._lbl_semanas.setTextFormat(Qt.RichText)

        dias_mes = monthrange(self._cal_anio, self._cal_mes)[1]
        if self._cal_ocultar:
            self._curva.set_curva([], dias_mes, t.MUTED)
            return
        curva = cal.curva(mes_filas, self._cal_anio, self._cal_mes)
        final = curva[-1][1] if curva else 0.0
        self._curva.set_curva(
            [(fecha.day, valor) for fecha, valor in curva],
            dias_mes,
            t.GREEN if final >= 0 else t.RED,
        )

    @staticmethod
    def _cal_dia_texto(mejor):
        """`06 nov · +94.6993` (o `—` si no hay días)."""
        if not mejor:
            return "—"
        dia, neto = mejor
        return f"{dia.day:02d} {cal.MESES[dia.month - 1][:3]} · {t.fmt_pnl(neto)}"

    def _cal_pintar_detalle(self, filtradas):
        rejilla = self._tabla_cal
        rejilla.setRowCount(0)
        if self._cal_dia is None:
            # sin día elegido el mes se ve entero: la tabla aparece al elegir
            rejilla.hide()
            if cal.en_mes(filtradas, self._cal_anio, self._cal_mes):
                self._lbl_detalle.setText("Elige un día del mes para ver sus operaciones")
            else:
                self._lbl_detalle.setText(
                    "Sin operaciones en este mes. «Cargar más historial» trae días antiguos."
                )
            return
        filas = [fila for dia, fila in cal.cerradas(filtradas) if dia == self._cal_dia]
        self._lbl_detalle.setText(
            f"{self._cal_dia.day:02d} {cal.MESES[self._cal_dia.month - 1]} {self._cal_dia.year} · "
            f"{len(filas)} operaciones"
        )
        for indice, fila in enumerate(filas):
            rejilla.insertRow(indice)
            pnl = float(fila.get("pnl") or 0)
            fee = float(fila.get("fee") or 0)
            neto = neto_operacion(pnl, fee)
            lado = fila.get("lado") or "—"
            valores = {
                "lado": lineas((lado, 12, True, t.GREEN if lado == "LONG" else t.RED)),
                "entrada": lineas(
                    (
                        self._cal_monto(t.fmt_price(fila.get("entrada")))
                        if fila.get("entrada")
                        else "—",
                        12,
                        False,
                        t.TEXT,
                    )
                ),
                "salida": lineas(
                    (
                        self._cal_monto(t.fmt_price(fila.get("salida")))
                        if fila.get("salida")
                        else "—",
                        12,
                        False,
                        t.TEXT,
                    )
                ),
                "pnl": lineas(
                    (self._cal_monto(t.fmt_pnl(pnl)), 12, False, t.GREEN if pnl >= 0 else t.RED)
                ),
                "fee": lineas(
                    (self._cal_monto(t.fmt_fee(fee)), 12, False, t.RED if fee > 0 else t.MUTED)
                ),
                "neto": lineas(
                    (self._cal_monto(t.fmt_pnl(neto)), 12, True, t.GREEN if neto >= 0 else t.RED)
                ),
                "hora": lineas((cuando(fila.get("cierre")), 12, False, t.MUTED)),
            }
            for columna, (clave, _rotulo, _ancho, anclaje) in enumerate(CAL_COLS):
                if clave == "par":
                    rejilla.setCellWidget(
                        indice,
                        columna,
                        CeldaPar(
                            fila.get("symbol", ""),
                            fila.get("_exchange") or "",
                            t.CARD,
                            compacta=True,
                        ),
                    )
                    continue
                item = QTableWidgetItem()
                item.setData(Qt.UserRole, valores[clave])
                item.setTextAlignment(Qt.AlignRight if anclaje == "e" else Qt.AlignLeft)
                rejilla.setItem(indice, columna, item)
        rejilla.show()

    # ------------------------------------------------------------- navegación
    def _cal_mover_mes(self, delta):
        mes = self._cal_mes + delta
        anio = self._cal_anio
        while mes < 1:
            mes += 12
            anio -= 1
        while mes > 12:
            mes -= 12
            anio += 1
        self._cal_mes = mes
        self._cal_anio = anio
        self._cal_dia = None
        self._cal_pintar()
        self._cal_scroll.verticalScrollBar().setValue(0)

    def _cal_mover_anio(self, delta):
        self._cal_anio += delta
        self._cal_dia = None
        self._cal_pintar()
        self._cal_scroll.verticalScrollBar().setValue(0)

    def _cal_hoy(self):
        hoy = date.today()
        self._cal_anio = hoy.year
        self._cal_mes = hoy.month
        self._cal_dia = hoy
        self._cal_pintar()

    def _cal_click(self, fila, columna):
        indice = fila * 7 + columna
        celdas = cal.dias_del_mes(self._cal_anio, self._cal_mes)
        if indice >= len(celdas):
            return
        fecha = celdas[indice]
        if fecha.year != self._cal_anio or fecha.month != self._cal_mes:
            return
        self._cal_dia = fecha
        self._cal_pintar()

    # ----------------------------------------------------------------- filtros
    def _cal_menu_broker(self):
        menu = QMenu(self)
        menu.setStyleSheet(menu_estilo())
        todos = menu.addAction("Todos")
        todos.setCheckable(True)
        todos.setChecked(not self._cal_broker)
        acciones = {todos: ""}
        for nombre in cal.brokers(self._cal_filas):
            accion = menu.addAction(QIcon(logo(nombre, 14)), TITULOS.get(nombre, nombre))
            accion.setCheckable(True)
            accion.setChecked(nombre == self._cal_broker)
            acciones[accion] = nombre
        elegido = menu.exec(self._btn_broker.mapToGlobal(self._btn_broker.rect().bottomLeft()))
        if elegido is None or elegido not in acciones:
            return
        self._cal_broker = acciones[elegido]
        self._btn_broker.setText(
            f"Broker: {TITULOS.get(self._cal_broker, self._cal_broker)}"
            if self._cal_broker
            else "Broker: Todos"
        )
        self._cal_pintar()

    def _cal_menu_par(self):
        menu = QMenu(self)
        menu.setStyleSheet(menu_estilo())
        todos = menu.addAction("Todos")
        todos.setCheckable(True)
        todos.setChecked(not self._cal_par)
        acciones = {todos: ""}
        for symbol in cal.pares(self._cal_filas):
            accion = menu.addAction(symbol)
            accion.setCheckable(True)
            accion.setChecked(symbol == self._cal_par)
            acciones[accion] = symbol
        elegido = menu.exec(self._btn_par.mapToGlobal(self._btn_par.rect().bottomLeft()))
        if elegido is None or elegido not in acciones:
            return
        self._cal_par = acciones[elegido]
        self._btn_par.setText(f"Par: {self._cal_par}" if self._cal_par else "Par: Todos")
        self._cal_pintar()

    # ---------------------------------------------------------------- acciones
    def _cal_alternar_montos(self):
        self._cal_ocultar = not self._cal_ocultar
        self._btn_montos.setText("Mostrar montos" if self._cal_ocultar else "Ocultar montos")
        self._cal_pintar()

    def _cal_exportar(self):
        filas = cal.en_mes(self._cal_filtradas(), self._cal_anio, self._cal_mes)
        if not filas:
            self._mostrar_estado("No hay operaciones en este mes para exportar.")
            return
        nombre = f"calendario_{self._cal_anio}-{self._cal_mes:02d}.csv"
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Exportar CSV", str(paths.DATA_DIR / nombre), "CSV (*.csv)"
        )
        if not ruta:
            return
        try:
            Path(ruta).write_text(cal.a_csv(filas), encoding="utf-8")
        except OSError as exc:
            self._mostrar_estado(f"No se pudo guardar el CSV: {exc}", 8000, error=True)
            return
        self._mostrar_estado(f"CSV guardado en {ruta}")

    def _cal_estado_historial(self, cargando, hay_mas):
        """El botón de «Cargar más historial» sigue al del Historial."""
        self._btn_mas_cal.setEnabled(not cargando and hay_mas)
        if cargando:
            texto = "Cargando…"
        else:
            texto = "Cargar más historial" if hay_mas else "Sin más historial"
        self._btn_mas_cal.setText(texto)
        if cargando:
            self._spin_cal.empezar()
            self._lbl_cargando_cal.show()
        else:
            self._spin_cal.parar()
            self._lbl_cargando_cal.hide()
