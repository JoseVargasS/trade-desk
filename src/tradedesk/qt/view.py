"""Vista Qt de la mesa, **solo lectura**, con el mismo diseño que la app de Tkinter.

Porta F2 (tarjetas) y F3 (tablas de posiciones y ordenes): mismos anchos, colores,
altos de fila y textos que la version Tk. **No envia ordenes**: las acciones de
operar avisan que se conectan en F5 y la logica de ordenes no se toca.

Se abre con `python -m tradedesk.qt`.
"""

import queue
from datetime import datetime

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import theme as t
from ..mexc import fee_desglose
from ..orders import ACTION_W as ORDER_ACTION_W
from ..orders import ORDER_COLS
from ..orders import PENCIL_COLS as ORDER_PENCILS
from ..orders import ROW_H as ORDER_H
from ..session import Session
from ..table import ACTION_W, PENCIL_COLS, POS_COLS, ROW_H, STATES
from .cells import DelegadoCeldas, icono_lapiz, lineas
from .style import fnt, qss

PRESETS = (1, 5, 10, 15, 20, 50)


def _cuando(ms):
    try:
        return datetime.fromtimestamp(float(ms) / 1000).strftime("%d/%m %H:%M")
    except Exception:
        return "—"


def _etiqueta(texto, size=13, bold=False, muted=False, color=None):
    etiqueta = QLabel(texto)
    etiqueta.setFont(fnt(size, bold))
    if muted:
        etiqueta.setProperty("muted", "true")
    if color:
        etiqueta.setStyleSheet(f"color: {color}; background: transparent;")
    return etiqueta


def _boton(texto, ancho=None, alto=22, fondo=None, color=None, radio=None, size=11, borde=True):
    boton = QPushButton(texto)
    boton.setCursor(Qt.PointingHandCursor)
    boton.setFont(fnt(size))
    fondo = fondo or t.INPUT
    color = color or t.TEXT
    radio = t.R_CHIP if radio is None else radio
    marco = f"1px solid {t.BORDER}" if borde else "0px"
    boton.setStyleSheet(
        f"QPushButton {{ background: {fondo}; color: {color}; border: {marco};"
        f" border-radius: {radio}px; }}"
        f"QPushButton:hover {{ border: 1px solid {t.MUTED}; }}"
    )
    if ancho:
        boton.setFixedWidth(ancho)
    boton.setFixedHeight(alto)
    return boton


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


class BarraCierre(QWidget):
    """Los cuatro controles de la fila: Mercado · % · Cerrar · Reverse."""

    def __init__(self, position, pnl, largo, avisar):
        super().__init__()
        self.setFixedSize(190, 52)
        fila1 = QHBoxLayout()
        fila1.setSpacing(4)
        fila2 = QHBoxLayout()
        fila2.setSpacing(4)
        color = t.GREEN if pnl > 0 else (t.RED if pnl < 0 else t.INPUT)
        texto_color = t.BG if pnl else t.TEXT
        cerrar = f"Cerrar {'LONG' if largo else 'SHORT'}"
        controles = (
            ("Mercado", 106, 22, None, None, fila1),
            ("100%", 78, 22, None, None, fila1),
            (cerrar, 102, 26, color, texto_color, fila2),
            ("Reverse", 82, 26, None, None, fila2),
        )
        for texto, ancho, alto, fondo, letra, fila in controles:
            boton = _boton(texto, ancho, alto, fondo, letra)
            boton.clicked.connect(lambda _=False, que=texto: avisar(que))
            fila.addWidget(boton)
        columna = QVBoxLayout(self)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(4)
        columna.addLayout(fila1)
        columna.addLayout(fila2)


class Segmentado(QWidget):
    """Dos opciones excluyentes, como el CTkSegmentedButton de la app."""

    def __init__(self, opciones, elegida, al_cambiar):
        super().__init__()
        self.al_cambiar = al_cambiar
        self.elegida = elegida
        self.botones = {}
        fila = QHBoxLayout(self)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(2)
        for texto in opciones:
            boton = _boton(texto, None, 24, size=10)
            boton.clicked.connect(lambda _=False, cual=texto: self._elegir(cual))
            fila.addWidget(boton)
            self.botones[texto] = boton
        self._pintar()

    def _elegir(self, texto):
        self.elegida = texto
        self._pintar()
        self.al_cambiar(texto)

    def _pintar(self):
        for texto, boton in self.botones.items():
            activo = texto == self.elegida
            boton.setStyleSheet(
                f"QPushButton {{ background: {t.SURFACE if activo else t.INPUT};"
                f" color: {t.TEXT if activo else t.MUTED}; border: 1px solid {t.BORDER};"
                f" border-radius: {t.R_CHIP}px; }}"
            )


class Tarjeta(QFrame):
    """Una tarjeta de par: apalancamiento, tamaño, TP/SL y el resumen vivo."""

    def __init__(self, tarjeta, mx):
        super().__init__()
        self.tarjeta = tarjeta
        self.mx = mx
        self.limite = 0.0
        self.setObjectName("card")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedSize(286, 436)

        columna = QVBoxLayout(self)
        columna.setContentsMargins(12, 12, 12, 12)
        columna.setSpacing(6)
        columna.addWidget(_etiqueta(tarjeta["nombre"], 15, True))
        self.lbl_precio = _etiqueta("—", 24, True)
        columna.addWidget(self.lbl_precio)
        columna.addWidget(_etiqueta(f"{tarjeta['leverage']}X · LONG", 12, True, color=t.GREEN))

        columna.addWidget(_etiqueta("Apalancamiento", 11, muted=True))
        fila_palanca = QHBoxLayout()
        fila_palanca.setSpacing(3)
        self.in_palanca = QLineEdit(tarjeta["leverage"])
        self.in_palanca.setFixedWidth(44)
        self.in_palanca.setAlignment(Qt.AlignRight)
        fila_palanca.addWidget(self.in_palanca)
        fila_palanca.addWidget(_etiqueta("x", 11, muted=True))
        for valor in PRESETS:
            preset = _boton(str(valor), 30, 20, size=10)
            preset.clicked.connect(lambda _=False, v=valor: self._poner_palanca(v))
            fila_palanca.addWidget(preset)
        columna.addLayout(fila_palanca)

        fila_modos = QHBoxLayout()
        fila_modos.setSpacing(4)
        self.seg_margen = Segmentado(("Aislado", "Cruzado"), tarjeta["margin"], self._cambio_margen)
        self.seg_modo = Segmentado(("Margen", "Nocional"), tarjeta["size_mode"], self._cambio_modo)
        fila_modos.addWidget(self.seg_margen)
        fila_modos.addWidget(self.seg_modo)
        columna.addLayout(fila_modos)

        columna.addWidget(_etiqueta("Tamaño (USDT)", 11, muted=True))
        fila_tamano = QHBoxLayout()
        fila_tamano.setSpacing(4)
        self.in_tamano = QLineEdit("")
        self.in_tamano.setAlignment(Qt.AlignRight)
        fila_tamano.addWidget(self.in_tamano, 1)
        self.chip_limite = _boton("Mercado ▾", 84, 26)
        self.chip_limite.clicked.connect(self._menu_limite)
        fila_tamano.addWidget(self.chip_limite)
        columna.addLayout(fila_tamano)

        columna.addWidget(_etiqueta("TP / SL", 11, muted=True))
        fila_stops = QHBoxLayout()
        fila_stops.setSpacing(4)
        self.in_tp = QLineEdit("")
        self.in_sl = QLineEdit("")
        for entrada in (self.in_tp, self.in_sl):
            entrada.setAlignment(Qt.AlignRight)
            fila_stops.addWidget(entrada)
        columna.addLayout(fila_stops)

        self.lbl_resumen = _etiqueta("—", 11, muted=True)
        self.lbl_resumen.setWordWrap(True)
        columna.addWidget(self.lbl_resumen)
        columna.addStretch(1)

        fila_botones = QHBoxLayout()
        fila_botones.setSpacing(8)
        self.btn_long = _boton("LONG", None, 38, t.GREEN, t.BG, t.R_CTRL, 14)
        self.btn_short = _boton("SHORT", None, 38, t.RED, t.BG, t.R_CTRL, 14)
        self.btn_long.setEnabled(False)
        self.btn_short.setEnabled(False)
        fila_botones.addWidget(self.btn_long)
        fila_botones.addWidget(self.btn_short)
        columna.addLayout(fila_botones)

        for entrada in (self.in_palanca, self.in_tamano, self.in_tp, self.in_sl):
            entrada.textChanged.connect(self._actualizar)
        self._actualizar()

    def _cambio_margen(self, valor):
        self.tarjeta["margin"] = valor

    def _cambio_modo(self, valor):
        self.tarjeta["size_mode"] = valor
        self._actualizar()

    def _poner_palanca(self, valor):
        self.in_palanca.setText(str(valor))

    def set_precio(self, precio):
        """Precio nuevo del ticker: se actualiza sin pedir nada a la red."""
        self.tarjeta["precio"] = float(precio or 0)
        self._actualizar()

    def _menu_limite(self):
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: {t.CARD}; color: {t.TEXT}; border: 1px solid {t.BORDER}; }}"
            f"QMenu::item:selected {{ background: {t.SURFACE}; }}"
        )
        mercado = menu.addAction("Mercado")
        limite = menu.addAction("Límite…")
        elegido = menu.exec(self.chip_limite.mapToGlobal(self.chip_limite.rect().bottomLeft()))
        if elegido is mercado:
            self.limite = 0.0
            self.chip_limite.setText("Mercado ▾")
        elif elegido is limite:
            precio, aceptado = QInputDialog.getDouble(
                self, "Precio límite", "Precio:", float(self.tarjeta["precio"] or 0), 0, 1e12, 6
            )
            if aceptado and precio > 0:
                self.limite = float(precio)
                self.chip_limite.setText(f"{self.limite:,.2f} ▾")
        self.chip_limite.adjustSize()
        self._actualizar()

    def _actualizar(self):
        self.lbl_precio.setText(f"{float(self.tarjeta['precio'] or 0):,.2f}")
        if self.mx is None:
            return
        try:
            palanca = max(1, int(float(self.in_palanca.text() or 0)))
        except ValueError:
            palanca = 1
        try:
            tamano = float(self.in_tamano.text().replace(",", "") or 0)
        except ValueError:
            tamano = 0.0
        precio = self.limite or float(self.tarjeta["precio"] or 0)
        nocional = tamano * palanca if self.tarjeta["size_mode"] == "Margen" else tamano
        if not (nocional and precio):
            self.lbl_resumen.setText("—")
            return
        contrato = self.tarjeta["contrato"] or {}
        vol = self.mx.size_to_vol(self.tarjeta["symbol"], nocional, precio, contract=contrato)
        real = self.mx.vol_to_usdt(self.tarjeta["symbol"], vol, precio)
        fee = self.mx.est_fee(self.tarjeta["symbol"], real)
        liq_l = self.mx.est_liq(self.tarjeta["symbol"], precio, palanca, "LONG")
        liq_s = self.mx.est_liq(self.tarjeta["symbol"], precio, palanca, "SHORT")
        self.lbl_resumen.setText(
            f"{vol:.0f} contratos · {real:,.2f} USDT\n"
            f"fee {fee:.4f} · liq {liq_l:,.2f} / {liq_s:,.2f}"
        )


class VistaQt(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Trade Desk · vista Qt (solo lectura)")
        self.resize(1800, 1000)
        self._posiciones = []
        self._tarjetas = {}

        central = QWidget()
        central.setObjectName("central")
        raiz = QVBoxLayout(central)
        raiz.setContentsMargins(16, 16, 16, 8)
        raiz.setSpacing(8)
        raiz.addWidget(self._cabecera())
        self._aviso = _etiqueta("", 12, muted=True)
        self._aviso.hide()
        raiz.addWidget(self._aviso)
        raiz.addWidget(self._armar_deck())
        raiz.addWidget(self._armar_pestanas(), 1)

        self.setCentralWidget(central)
        self.statusBar().showMessage("vista previa · solo lectura · las acciones se conectan en F5")
        self.setStyleSheet(qss())

        self._latido = QTimer(self)
        self._latido.timeout.connect(self._drenar)
        self._latido.start(120)
        self.session = Session().start()

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
        fila.addWidget(_etiqueta("Qt · vista previa", 11, muted=True))
        fila.addStretch(1)
        fila.addWidget(_etiqueta("DRY-RUN", 11, True, color=t.GOLD))
        return cabecera

    def _armar_deck(self):
        deck = QScrollArea()
        deck.setWidgetResizable(True)
        deck.setFrameShape(QFrame.NoFrame)
        deck.setFixedHeight(470)
        self._fila_tarjetas = QHBoxLayout()
        self._fila_tarjetas.setContentsMargins(0, 0, 0, 0)
        self._fila_tarjetas.setSpacing(10)
        self._fila_tarjetas.addStretch(1)
        contenido = QWidget()
        contenido.setLayout(self._fila_tarjetas)
        deck.setWidget(contenido)
        return deck

    def _armar_pestanas(self):
        self._tabs = QTabWidget()

        posiciones = QWidget()
        col_pos = QVBoxLayout(posiciones)
        col_pos.setContentsMargins(0, 0, 0, 0)
        col_pos.setSpacing(6)
        self._lbl_abiertas = _etiqueta("0 abiertas", 11, muted=True)
        col_pos.addWidget(self._lbl_abiertas)
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
        self._btn_cancelar_todo.clicked.connect(lambda: self._avisar("Cancelar todo"))
        barra.addWidget(self._btn_cancelar_todo)
        col_ord.addLayout(barra)
        self._tabla_ord = self._tabla_ordenes()
        col_ord.addWidget(self._tabla_ord, 1)

        self._tabs.addTab(posiciones, "Posiciones")
        self._tabs.addTab(ordenes, "Órdenes")
        self._tabs.addTab(_etiqueta("Historial: se porta en F3b", 12, muted=True), "Historial")
        return self._tabs

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
        return _tabla(columnas, ORDER_H)

    # ------------------------------------------------------------------ refresco
    def _drenar(self):
        for _ in range(40):
            try:
                mensaje = self.session.q.get_nowait()
            except queue.Empty:
                return
            tipo = mensaje[0]
            if tipo == "error":
                self._aviso.setText(mensaje[1])
                self._aviso.show()
            elif tipo == "cards":
                self._pintar_deck(mensaje[1])
            elif tipo == "ticker":
                self._actualizar_precio(mensaje[1], mensaje[2])
            elif tipo == "positions":
                self._posiciones = mensaje[1]
                self._pintar_posiciones(self._posiciones)
            elif tipo == "orders":
                self._pintar_ordenes(mensaje[1])

    def _avisar(self, que):
        self.statusBar().showMessage(f"{que}: se conecta en F5 (esta vista no envía órdenes)")

    def _actualizar_precio(self, symbol, precio):
        tarjeta = self._tarjetas.get(symbol)
        if tarjeta is not None:
            tarjeta.set_precio(precio)
        self.statusBar().showMessage(
            f"{len(self._posiciones)} posiciones · solo lectura · las acciones se conectan en F5"
        )

    def _pintar_deck(self, tarjetas):
        self._aviso.hide()
        while self._fila_tarjetas.count() > 1:
            elemento = self._fila_tarjetas.takeAt(0)
            if elemento.widget():
                elemento.widget().deleteLater()
        self._tarjetas = {}
        for tarjeta in tarjetas:
            widget = Tarjeta(tarjeta, self.session.mx)
            self._tarjetas[tarjeta["symbol"]] = widget
            self._fila_tarjetas.insertWidget(self._fila_tarjetas.count() - 1, widget)

    # --------------------------------------------------------------- posiciones
    def _pintar_posiciones(self, posiciones):
        tabla = self._tabla_pos
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
            seleccion.setCheckState(Qt.Unchecked)
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
                    tabla.setCellWidget(
                        fila,
                        columna,
                        self._celda_lapiz(clave, valores[clave], position, fondo_fila),
                    )
                else:
                    item.setData(Qt.UserRole, valores[clave])
                tabla.setItem(fila, columna, item)

            acciones = len(POS_COLS) + 2
            tabla.setCellWidget(fila, acciones, BarraCierre(position, pnl, largo, self._avisar))
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

    def _celda_lapiz(self, clave, partes, position, fondo=None):
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
        lapiz.clicked.connect(lambda: self._avisar(f"editar {clave}"))
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
                            clave, valores.get(clave, lineas(("—", 13, False, t.MUTED))), orden
                        ),
                    )

            acciones = QWidget()
            fila_acciones = QHBoxLayout(acciones)
            fila_acciones.setContentsMargins(4, 0, 8, 0)
            fila_acciones.setSpacing(6)
            modificar = _boton("Modificar", 84, 26)
            cancelar = _boton("Cancelar", 84, 26, t.INPUT, t.RED)
            modificar.clicked.connect(lambda: self._avisar("Modificar"))
            cancelar.clicked.connect(lambda: self._avisar("Cancelar"))
            fila_acciones.addWidget(modificar)
            fila_acciones.addWidget(cancelar)
            tabla.setCellWidget(fila, len(ORDER_COLS), acciones)
        self._lbl_ordenes.setText(
            f"{len(ordenes)} pendientes" if ordenes else "Sin órdenes pendientes"
        )


def build_main_window():
    return VistaQt()
