"""Ventana Qt de la mesa: tarjetas, posiciones, órdenes e historial.

Toda la lógica de operar vive en `controller.Control`; aquí solo se pinta y se
leen los controles. Ningún pedido de red sale del hilo de la UI: eso lo hace
`Session` y llega por su cola.

Se abre con `python -m tradedesk` (o `python -m tradedesk.qt`).
"""

import queue
import threading
from datetime import datetime

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QMainWindow,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import theme as t
from ..controller import Control
from ..layout import (
    ACTION_W,
    HIST_COLS,
    ORDER_ACTION_W,
    ORDER_COLS,
    ORDER_PENCILS,
    ORDER_ROW_H,
    PENCIL_COLS,
    POS_COLS,
    ROW_H,
    SIDES,
    STATES,
)
from ..mexc import fee_desglose
from ..session import Session
from . import dialogs
from .cells import DelegadoCeldas, icono_lapiz, lineas
from .dialogs import QtPort
from .search import buscar
from .style import boton as _boton
from .style import etiqueta as _etiqueta
from .style import qss
from .tarjeta import BarraCierre, Tarjeta

PRESETS = (1, 5, 10, 15, 20, 50)


def _cuando(ms):
    try:
        return datetime.fromtimestamp(float(ms) / 1000).strftime("%d/%m %H:%M")
    except Exception:
        return "—"


def _tabla(columnas, alto_fila):
    tabla = QTableWidget(0, len(columnas))
    tabla.setHorizontalHeaderLabels([columna[1] for columna in columnas])
    tabla.verticalHeader().setVisible(False)
    tabla.verticalHeader().setDefaultSectionSize(alto_fila)
    tabla.setShowGrid(False)
    tabla.setAlternatingRowColors(False)
    tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
    tabla.setSelectionMode(QAbstractItemView.NoSelection)
    tabla.setFocusPolicy(Qt.NoFocus)
    tabla.setWordWrap(False)
    tabla.setItemDelegate(DelegadoCeldas(tabla))
    for indice, columna in enumerate(columnas):
        tabla.setColumnWidth(indice, columna[2])
        encabezado = tabla.horizontalHeaderItem(indice)
        if encabezado is not None:
            alineacion = Qt.AlignRight if columna[3] == "e" else Qt.AlignLeft
            encabezado.setTextAlignment(alineacion | Qt.AlignVCenter)
    return tabla


class VistaQt(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Trade Desk")
        self.resize(1800, 1000)
        self._posiciones = []
        self._ordenes = []
        self._tarjetas = {}
        self._tarjeta_enviando = None
        self._avisos = []
        self._mostrando = False
        self._dry = True

        self.session = Session()
        self.control = Control(self.session, QtPort(self), dry=lambda: self._dry)

        central = QWidget()
        central.setObjectName("central")
        raiz = QVBoxLayout(central)
        raiz.setContentsMargins(16, 16, 16, 8)
        raiz.setSpacing(8)
        raiz.addWidget(self._cabecera())
        raiz.addWidget(self._armar_deck())
        raiz.addWidget(self._armar_pestanas(), 1)

        self.setCentralWidget(central)
        self.statusBar().showMessage("DRY-RUN activo · no abre ni cierra posiciones")
        self.setStyleSheet(qss())

        self._latido = QTimer(self)
        self._latido.timeout.connect(self._drenar)
        self._latido.start(120)
        self.session.start()
        QTimer.singleShot(600, self._pedir_key)

    def _pedir_key(self):
        from .. import creds
        from ..mexc import Mexc

        if creds.load("mexc")[0]:
            return
        got = dialogs.ask_key(self, lambda k, s: Mexc(k, s).positions())
        if not got:
            return
        creds.save("mexc", *got)
        self.session.mx = Mexc(*got)
        self.statusBar().showMessage("Key guardada. Listo para operar.")
        threading.Thread(target=self.session.refresh_positions, daemon=True).start()

    def closeEvent(self, evento):
        self.session.stop()
        super().closeEvent(evento)

    # ------------------------------------------------------------- construccion
    def _cabecera(self):
        cabecera = QFrame()
        cabecera.setObjectName("surface")
        cabecera.setAttribute(Qt.WA_StyledBackground, True)
        fila = QHBoxLayout(cabecera)
        fila.setContentsMargins(12, 8, 12, 8)
        fila.addWidget(_etiqueta("TRADE DESK", 14, True))
        fila.addSpacing(16)
        fila.addWidget(_etiqueta("Qt", 11, muted=True))
        fila.addStretch(1)
        self._lbl_ip = _etiqueta("IP —", 11, muted=True)
        fila.addWidget(self._lbl_ip)
        copiar = _boton("Copiar IP", 74, 22, size=10)
        copiar.clicked.connect(self._copiar_ip)
        fila.addWidget(copiar)
        self.chk_dry = QCheckBox("DRY-RUN")
        self.chk_dry.setChecked(True)
        self.chk_dry.setCursor(Qt.PointingHandCursor)
        self.chk_dry.setStyleSheet(f"QCheckBox {{ color: {t.GOLD}; }}")
        self.chk_dry.toggled.connect(self._cambio_dry)
        fila.addWidget(self.chk_dry)
        return cabecera

    def _copiar_ip(self):
        ip = self._lbl_ip.text().replace("IP", "").strip()
        QApplication.clipboard().setText(ip)
        self.statusBar().showMessage(f"IP {ip} copiada.")

    def _añadir_par(self):
        if not self.session.mercados:
            self._notificar("Catálogo", "Todavía se está cargando el catálogo de MEXC.")
            return
        symbol = buscar(self, self.session.mercados)
        if symbol and not self.session.add_card(symbol):
            self.statusBar().showMessage(f"{symbol} ya esta en pantalla.")

    def _cambio_dry(self, activo):
        self._dry = bool(activo)
        self.chk_dry.setText("DRY-RUN" if self._dry else "REAL")
        self.chk_dry.setStyleSheet(f"QCheckBox {{ color: {t.GOLD if self._dry else t.RED}; }}")
        self.statusBar().showMessage(
            "DRY-RUN activo · no abre ni cierra posiciones"
            if self._dry
            else "REAL · las órdenes se envían"
        )

    def _armar_deck(self):
        deck = QScrollArea()
        deck.setWidgetResizable(True)
        deck.setFrameShape(QFrame.NoFrame)
        deck.setFixedHeight(470)
        contenido = QWidget()
        fila = QHBoxLayout(contenido)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(10)
        self._fila_tarjetas = QHBoxLayout()
        self._fila_tarjetas.setContentsMargins(0, 0, 0, 0)
        self._fila_tarjetas.setSpacing(10)
        self._fila_tarjetas.addStretch(1)
        fila.addLayout(self._fila_tarjetas, 1)
        agregar = _boton("+ Añadir par", 120, 34)
        agregar.clicked.connect(self._añadir_par)
        fila.addWidget(agregar, 0, Qt.AlignTop)
        deck.setWidget(contenido)
        return deck

    def _armar_pestanas(self):
        self._tabs = QTabWidget()

        posiciones = QWidget()
        col_pos = QVBoxLayout(posiciones)
        col_pos.setContentsMargins(0, 0, 0, 0)
        col_pos.setSpacing(6)
        barra_pos = QHBoxLayout()
        self._lbl_abiertas = _etiqueta("0 abiertas", 11, muted=True)
        barra_pos.addWidget(self._lbl_abiertas)
        barra_pos.addStretch(1)
        self._btn_sel = _boton("Cerrar seleccionadas", 170, 26)
        self._btn_sel.clicked.connect(self._cerrar_seleccionadas)
        barra_pos.addWidget(self._btn_sel)
        todo = _boton("CERRAR TODO", 120, 26, t.DANGER_SOFT, t.RED)
        todo.clicked.connect(lambda: self.control.cerrar_todo(len(self._seleccionadas())))
        barra_pos.addWidget(todo)
        col_pos.addLayout(barra_pos)
        self._tabla_pos = self._tabla_posiciones()
        col_pos.addWidget(self._tabla_pos, 1)

        ordenes = QWidget()
        col_ord = QVBoxLayout(ordenes)
        col_ord.setContentsMargins(0, 0, 0, 0)
        col_ord.setSpacing(6)
        barra = QHBoxLayout()
        self._lbl_ordenes = _etiqueta("Sin órdenes pendientes", 12, muted=True)
        barra.addWidget(self._lbl_ordenes)
        barra.addStretch(1)
        self._btn_cancelar_todo = _boton("Cancelar todo", 120, 26, t.DANGER_SOFT, t.RED)
        self._btn_cancelar_todo.clicked.connect(lambda: self.control.cancelar_todo(self._ordenes))
        barra.addWidget(self._btn_cancelar_todo)
        col_ord.addLayout(barra)
        self._tabla_ord = self._tabla_ordenes()
        col_ord.addWidget(self._tabla_ord, 1)

        self._tabs.addTab(posiciones, "Posiciones")
        self._tabs.addTab(ordenes, "Órdenes")
        historial = QWidget()
        col_hist = QVBoxLayout(historial)
        col_hist.setContentsMargins(0, 0, 0, 0)
        self._tabla_hist = _tabla(HIST_COLS, 38)
        col_hist.addWidget(self._tabla_hist, 1)
        self._tabs.addTab(historial, "Historial")
        self._tabs.currentChanged.connect(self._cambio_pestana)
        return self._tabs

    def _cambio_pestana(self, indice):
        visible = self._tabs.tabText(indice) == "Historial"
        self.session.ver_historial = visible
        if visible:
            threading.Thread(target=self.session.cargar_historial, daemon=True).start()

    def _tabla_posiciones(self):
        columnas = [
            ("sel", "", 30, "w"),
            *POS_COLS,
            ("hueco", "", 0, "w"),
            ("acciones", "", ACTION_W, "w"),
        ]
        tabla = _tabla(columnas, ROW_H)
        for indice, columna in enumerate(columnas):
            if columna[0] == "hueco":
                tabla.horizontalHeader().setSectionResizeMode(indice, QHeaderView.Stretch)
            elif columna[0] == "acciones":
                tabla.horizontalHeader().setSectionResizeMode(indice, QHeaderView.Fixed)
        return tabla

    def _tabla_ordenes(self):
        columnas = [*ORDER_COLS, ("acciones", "", ORDER_ACTION_W, "w")]
        return _tabla(columnas, ORDER_ROW_H)

    # ------------------------------------------------------------------ refresco
    def _drenar(self):
        for _ in range(40):
            try:
                mensaje = self.session.q.get_nowait()
            except queue.Empty:
                break
            tipo = mensaje[0]
            if tipo == "error":
                self._notificar("Error", mensaje[1], danger=True)
            elif tipo == "cards":
                self._pintar_deck(mensaje[1])
            elif tipo == "ticker":
                self._actualizar_precio(mensaje[1], mensaje[2])
            elif tipo == "positions":
                self._posiciones = mensaje[1]
                self._pintar_posiciones(self._posiciones)
            elif tipo == "orders":
                self._ordenes = mensaje[1]
                self._pintar_ordenes(self._ordenes)
            elif tipo in ("status", "closed"):
                self.statusBar().showMessage(mensaje[1])
            elif tipo == "notice":
                self._notificar(*mensaje[1])
            elif tipo == "order":
                self._orden_terminada(*mensaje[1])
            elif tipo == "history":
                self._pintar_historial(mensaje[1])
            elif tipo == "ip":
                self._lbl_ip.setText(f"IP {mensaje[1]}")
        # un modal dentro de _drenar congela el refresco: se abre al volver al bucle
        QTimer.singleShot(0, self._siguiente_aviso)

    def _notificar(self, titulo, mensaje, aviso=None, danger=False):
        self._avisos.append((titulo, mensaje, aviso, danger))
        QTimer.singleShot(0, self._siguiente_aviso)

    def _siguiente_aviso(self):
        if self._mostrando or not self._avisos:
            return
        self._mostrando = True
        titulo, mensaje, aviso, danger = self._avisos.pop(0)
        try:
            dialogs.show(self, titulo, mensaje, aviso=aviso, danger=danger)
        finally:
            self._mostrando = False
        QTimer.singleShot(0, self._siguiente_aviso)

    def _orden_terminada(self, ok, msg):
        if self._tarjeta_enviando is not None:
            self._tarjeta_enviando.set_busy(False)
        self._tarjeta_enviando = None

    def _trade(self, tarjeta, side):
        form = tarjeta.form()
        if not form:
            dialogs.show(
                self,
                "Datos invalidos",
                "Revisa el apalancamiento y el tamaño: deben ser numeros "
                "positivos, y TP/SL vacios o numericos.",
            )
            return

        def enviar():
            self._tarjeta_enviando = tarjeta
            tarjeta.set_busy(True)

        self.control.abrir(side, form, al_enviar=enviar)

    def _actualizar_precio(self, symbol, precio):
        tarjeta = self._tarjetas.get(symbol)
        if tarjeta is not None:
            tarjeta.set_precio(precio)
        self.statusBar().showMessage(f"{len(self._posiciones)} posiciones abiertas")

    def _pintar_deck(self, tarjetas):
        while self._fila_tarjetas.count() > 1:
            elemento = self._fila_tarjetas.takeAt(0)
            if elemento.widget():
                elemento.widget().deleteLater()
        self._tarjetas = {}
        for tarjeta in tarjetas:
            widget = Tarjeta(
                tarjeta,
                self.session.mx,
                on_trade=self._trade,
                on_remove=self._quitar_par,
            )
            self._tarjetas[tarjeta["symbol"]] = widget
            self._fila_tarjetas.insertWidget(self._fila_tarjetas.count() - 1, widget)

    def _quitar_par(self, symbol):
        self.session.remove_card(symbol)
        self._tarjetas.pop(symbol, None)

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
    def _pintar_posiciones(self, posiciones):
        tabla = self._tabla_pos
        marcadas = {p.get("positionId") for p in self._seleccionadas()}
        tabla.setRowCount(len(posiciones))
        for fila, position in enumerate(posiciones):
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

            seleccion = QTableWidgetItem()
            seleccion.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            seleccion.setCheckState(
                Qt.Checked if position.get("positionId") in marcadas else Qt.Unchecked
            )
            tabla.setItem(fila, 0, seleccion)

            valores = {
                "par": lineas(
                    (position.get("_name") or position.get("symbol", ""), 13, True, t.TEXT)
                ),
                "lado": lineas(
                    (
                        f"{position.get('leverage', '')}X {'LONG' if largo else 'SHORT'}",
                        13,
                        True,
                        t.GREEN if largo else t.RED,
                    )
                ),
                "apertura": lineas((_cuando(position.get("createTime")), 13, False, t.MUTED)),
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
            fondo_fila = t.ROW_ALT if fila % 2 else t.CARD
            for columna, (clave, _rotulo, _ancho, anclaje) in enumerate(POS_COLS, start=1):
                item = QTableWidgetItem()
                item.setTextAlignment(Qt.AlignRight if anclaje == "e" else Qt.AlignLeft)
                if clave in PENCIL_COLS:
                    # la celda lleva widget (valor + lapiz): el delegado no pinta nada
                    accion = (
                        (lambda p=position: self.control.tpsl(p))
                        if clave == "tpsl"
                        else (lambda p=position: self.control.margen(p))
                    )
                    tabla.setCellWidget(
                        fila,
                        columna,
                        self._celda_lapiz(clave, valores[clave], accion, fondo_fila),
                    )
                else:
                    item.setData(Qt.UserRole, valores[clave])
                tabla.setItem(fila, columna, item)

            acciones = len(POS_COLS) + 2
            tabla.setCellWidget(
                fila,
                acciones,
                BarraCierre(position, pnl, largo, self.control.cerrar, self.control.reverse),
            )
        self._lbl_abiertas.setText(f"{len(posiciones)} abiertas")

    def _texto_stops(self, position, escala):
        tp = float(position.get("_tp") or 0)
        sl = float(position.get("_sl") or 0)
        if tp and sl:
            return (
                (t.fmt_price_exact(tp, escala), 13, True, t.GREEN),
                (t.fmt_price_exact(sl, escala), 13, True, t.RED),
            )
        if tp:
            return ((f"TP {t.fmt_price_exact(tp, escala)}", 13, True, t.GREEN),)
        if sl:
            return ((f"SL {t.fmt_price_exact(sl, escala)}", 13, True, t.RED),)
        return (("—", 13, False, t.MUTED),)

    def _celda_lapiz(self, clave, partes, accion, fondo=None):
        caja = QWidget()
        if fondo:
            caja.setStyleSheet(f"background: {fondo};")
        fila = QHBoxLayout(caja)
        fila.setContentsMargins(6, 0, 6, 0)
        fila.setSpacing(4)
        for texto, size, negrita, color in partes:
            etiqueta = _etiqueta(str(texto), size, negrita, color=color)
            etiqueta.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            fila.addWidget(etiqueta, 1)
        lapiz = QToolButton()
        lapiz.setIcon(QIcon(icono_lapiz(t.MUTED)))
        lapiz.setIconSize(QSize(14, 14))
        lapiz.setCursor(Qt.PointingHandCursor)
        lapiz.setStyleSheet("QToolButton { border: 0; background: transparent; }")
        lapiz.clicked.connect(lambda _=False: accion())
        fila.addWidget(lapiz, 0)
        return caja

    # ------------------------------------------------------------------ ordenes
    def _pintar_ordenes(self, ordenes):
        tabla = self._tabla_ord
        tabla.setRowCount(len(ordenes))
        for fila, orden in enumerate(ordenes):
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
                "fecha": lineas((_cuando(orden.get("createTime")), 13, False, t.MUTED)),
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
                        f"TP {t.fmt_price_exact(tp, escala)}" if tp else "—",
                        13,
                        False,
                        t.GREEN if tp else t.MUTED,
                    ),
                    (f"SL {t.fmt_price_exact(sl, escala)}" if sl else "", 13, False, t.RED),
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
                if clave in ORDER_PENCILS:
                    tabla.setCellWidget(
                        fila,
                        columna,
                        self._celda_lapiz(
                            clave,
                            valores.get(clave, lineas(("—", 13, False, t.MUTED))),
                            lambda o=orden: self.control.modificar(o),
                        ),
                    )

            acciones = QWidget()
            fila_acciones = QHBoxLayout(acciones)
            fila_acciones.setContentsMargins(4, 0, 8, 0)
            fila_acciones.setSpacing(6)
            modificar = _boton("Modificar", 84, 26)
            cancelar = _boton("Cancelar", 84, 26, t.INPUT, t.RED)
            modificar.clicked.connect(lambda _=False, o=orden: self.control.modificar(o))
            cancelar.clicked.connect(lambda _=False, o=orden: self.control.cancelar(o))
            fila_acciones.addWidget(modificar)
            fila_acciones.addWidget(cancelar)
            tabla.setCellWidget(fila, len(ORDER_COLS), acciones)
        self._lbl_ordenes.setText(
            f"{len(ordenes)} pendientes" if ordenes else "Sin órdenes pendientes"
        )

    # ----------------------------------------------------------------- historial
    def _pintar_historial(self, ordenes):
        tabla = self._tabla_hist
        tabla.setRowCount(len(ordenes))
        for fila, orden in enumerate(ordenes):
            pnl = float(orden.get("profit") or 0)
            fee = float(orden.get("totalFee") or 0)
            estado = int(orden.get("state") or 0)
            valores = {
                "fecha": lineas((_cuando(orden.get("createTime")), 12, False, t.MUTED)),
                "par": lineas((orden.get("symbol", ""), 12, False, t.TEXT)),
                "tipo": lineas((SIDES.get(int(orden.get("side") or 0), "?"), 12, False, t.MUTED)),
                "qty": lineas((t.fmt_qty(orden.get("vol")), 12, False, t.TEXT)),
                "precio": lineas(
                    (
                        t.fmt_price(orden.get("dealAvgPrice") or orden.get("price")),
                        12,
                        False,
                        t.TEXT,
                    )
                ),
                "pnl": lineas((t.fmt_pnl(pnl), 12, False, t.GREEN if pnl >= 0 else t.RED)),
                "fee": lineas((t.fmt_fee(fee), 12, False, t.RED if fee > 0 else t.MUTED)),
                "estado": lineas(
                    (
                        STATES.get(estado, str(estado)),
                        12,
                        False,
                        t.GREEN if estado == 3 else t.MUTED,
                    )
                ),
            }
            for columna, (clave, _rotulo, _ancho, anclaje) in enumerate(HIST_COLS):
                item = QTableWidgetItem()
                item.setData(Qt.UserRole, valores[clave])
                item.setTextAlignment(Qt.AlignRight if anclaje == "e" else Qt.AlignLeft)
                tabla.setItem(fila, columna, item)


def build_main_window():
    return VistaQt()
