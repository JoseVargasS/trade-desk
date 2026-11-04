"""Ventana Qt de la mesa: tarjetas, posiciones, órdenes e historial.

Toda la lógica de operar vive en `controller.Control`; aquí solo se pinta y se
leen los controles. Ningún pedido de red sale del hilo de la UI: eso lo hace
`Session` y llega por su cola.

Se abre con `python -m tradedesk` (o `python -m tradedesk.qt`).
"""

import queue
import threading
from datetime import datetime

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QPropertyAnimation, QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
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
from ..brokers import NOMBRES, TITULOS
from ..controller import Control
from ..layout import (
    ACTION_W,
    OPER_COLS,
    ORDER_ACTION_W,
    ORDER_COLS,
    ORDER_PENCILS,
    ORDER_ROW_H,
    PENCIL_COLS,
    POS_COLS,
    ROW_H,
    STATES,
)
from ..mexc import fee_desglose, resumen_pnl
from ..paths import ASSETS
from ..session import Session
from . import dialogs
from .cells import DETALLE, SUBRAYADO, Bocadillo, DelegadoCeldas, Spinner, icono_lapiz, lineas
from .dialogs import QtPort
from .search import buscar
from .style import barra_oscura, fnt, logo, qss
from .style import boton as _boton
from .style import etiqueta as _etiqueta
from .tarjeta import BarraCierre, Tarjeta

PRESETS = (1, 5, 10, 15, 20, 50)


BROKERS = NOMBRES


def _tamano_usdt(fila):
    """Tamano de la operacion en USDT (cantidad por el precio de entrada)."""
    cantidad = float(fila.get("qty") or fila.get("abierta") or fila.get("cerrada") or 0)
    precio = float(fila.get("entrada") or fila.get("salida") or 0)
    if not (cantidad and precio):
        return "—"
    return f"{t.fmt_usdt(cantidad * precio)} USDT"


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


class CeldaLapiz(QWidget):
    """Valor(es) + lapiz, actualizable en sitio (no se recrea en cada refresco)."""

    def __init__(self, partes, accion, fondo, vertical=False):
        super().__init__()
        self._accion = accion
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {fondo};")
        fila = QHBoxLayout(self)
        fila.setContentsMargins(6, 0, 6, 0)
        fila.setSpacing(4)
        fila.addStretch(1)
        caja = QWidget()
        self._caja = (QVBoxLayout if vertical else QHBoxLayout)(caja)
        self._caja.setContentsMargins(0, 0, 0, 0)
        self._caja.setSpacing(0)
        self._etiquetas = []
        fila.addWidget(caja)
        lapiz = QToolButton()
        lapiz.setIcon(QIcon(icono_lapiz(t.MUTED)))
        lapiz.setIconSize(QSize(16, 16))
        lapiz.setCursor(Qt.PointingHandCursor)
        lapiz.setStyleSheet("QToolButton { border: 0; background: transparent; }")
        lapiz.clicked.connect(lambda: self._accion())
        fila.addWidget(lapiz)
        self.set_partes(partes)

    def set_partes(self, partes):
        """Crea las etiquetas que falten: la celda puede pasar de 1 valor a 3."""
        while len(self._etiquetas) < len(partes):
            _texto, size, _negrita, _color = partes[len(self._etiquetas)]
            etiqueta = _etiqueta("", size)
            etiqueta.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._caja.addWidget(etiqueta)
            self._etiquetas.append(etiqueta)
        for indice, etiqueta in enumerate(self._etiquetas):
            if indice < len(partes):
                texto, size, negrita, color = partes[indice]
                etiqueta.setText(str(texto))
                etiqueta.setFont(fnt(size, negrita))
                etiqueta.setStyleSheet(f"color: {color}; background: transparent;")
                etiqueta.show()
            else:
                etiqueta.hide()

    def set_fondo(self, color):
        """Color de la fila: cambia cuando la posicion se mueve de lugar."""
        if self.styleSheet() != f"background: {color};":
            self.setStyleSheet(f"background: {color};")

    def set_accion(self, accion):
        """Se reasigna en cada refresco: la celda no puede quedarse con el dato viejo."""
        self._accion = accion


class CeldaPar(QWidget):
    """Par y broker: el nombre arriba y el wordmark del broker debajo."""

    def __init__(self, nombre, exchange, fondo, compacta=False):
        super().__init__()
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {fondo};")
        self._compacta = bool(compacta)
        alto = 2 if compacta else 8
        columna = QVBoxLayout(self)
        columna.setContentsMargins(6, alto, 6, 2 if compacta else 6)
        columna.setSpacing(0 if compacta else 1)
        self.lbl_nombre = _etiqueta(nombre, 12 if compacta else 13, True)
        columna.addWidget(self.lbl_nombre)
        self.lbl_marca = QLabel()
        self.lbl_marca.setStyleSheet("background: transparent;")
        columna.addWidget(self.lbl_marca)
        columna.addStretch(1)
        self.set_datos(nombre, exchange)

    def set_fondo(self, color):
        if self.styleSheet() != f"background: {color};":
            self.setStyleSheet(f"background: {color};")

    def set_datos(self, nombre, exchange):
        self.lbl_nombre.setText(str(nombre))
        alto = 10 if self._compacta else 12
        imagen = logo(exchange, alto, completo=True) if exchange else QPixmap()
        if imagen.isNull():
            self.lbl_marca.hide()
            return
        self.lbl_marca.setPixmap(imagen)
        self.lbl_marca.show()


class VistaQt(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Trade Desk")
        self.resize(1800, 1000)
        self._posiciones = []
        self._ordenes = []
        self._tarjetas = {}
        self._ultimo_error = ""
        self._fondos = {}
        self._saldos = {}
        self._ip = {}
        self._hay_mas_hist = True
        self._caja_saldos = None
        self._firma_pos = ()
        self._arrastrada = None
        self._desfase = QPoint()
        self._destino = None
        self._cartas = []
        self._anims = {}
        self._lienzo = None
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
        self.session.hay["mexc"] = True
        self.statusBar().showMessage("Key guardada. Listo para operar.")
        threading.Thread(target=self.session.refresh_positions, daemon=True).start()

    def closeEvent(self, evento):
        self.session.stop()
        super().closeEvent(evento)

    # ------------------------------------------------------------------ brokers
    def _celda_saldo(self, nombre):
        """Wordmark del broker + número + USDT, para la cabecera."""
        caja = QWidget()
        caja.setStyleSheet("background: transparent;")
        fila = QHBoxLayout(caja)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(6)
        marca = QLabel()
        marca.setPixmap(logo(nombre, 13, completo=True))
        marca.setStyleSheet("background: transparent;")
        fila.addWidget(marca, 0, Qt.AlignVCenter)
        numero = _etiqueta("—", 13, True)
        numero.setToolTip("Saldo en vivo: balance + PnL no realizado de las posiciones")
        fila.addWidget(numero, 0, Qt.AlignVCenter)
        fila.addWidget(_etiqueta("USDT", 13, True), 0, Qt.AlignVCenter)
        self._caja_saldos.addWidget(caja)
        self._saldos[nombre] = numero
        if len(self._saldos) > 1:
            self._caja_saldos.addWidget(_etiqueta("·", 12, False, muted=True))
        return numero

    def _pintar_saldos(self, saldos):
        """USDT disponible de cada broker, con su wordmark, en la cabecera."""
        conectados = [nombre for nombre in BROKERS if self.session.cliente(nombre) is not None]
        if not conectados:
            self._lbl_saldo.setText("— USDT")
            return
        self._lbl_saldo.setVisible(False)
        for nombre in conectados:
            numero = self._saldos.get(nombre) or self._celda_saldo(nombre)
            numero.setText(t.fmt_usdt(saldos.get(nombre) or 0))

    def _abrir_brokers(self):
        from .. import creds

        saldos = self.session.saldos
        filas = [
            (nombre, TITULOS[nombre], bool(creds.load(nombre)[0]), saldos.get(nombre) or 0)
            for nombre in BROKERS
        ]
        dialogs.brokers(self, filas, self._cargar_claves)

    def _cargar_claves(self, nombre):
        from .. import creds
        from ..bingx import Bingx
        from ..bitunix import Bitunix
        from ..mexc import Mexc

        clase = {"mexc": Mexc, "bitunix": Bitunix, "bingx": Bingx}[nombre]
        got = dialogs.ask_key(self, lambda k, s: clase(k, s).positions())
        if not got:
            return
        creds.save(nombre, *got)
        self.session.poner_cliente(nombre, clase(*got))
        self.statusBar().showMessage(f"Claves de {nombre} guardadas.")

        def refrescar():
            self.session.refresh_saldos()
            self.session.refresh_positions()

        threading.Thread(target=refrescar, daemon=True).start()
        self._abrir_brokers()

    # ------------------------------------------------------------- construccion
    def _cabecera(self):
        cabecera = QFrame()
        cabecera.setObjectName("surface")
        cabecera.setAttribute(Qt.WA_StyledBackground, True)
        fila = QHBoxLayout(cabecera)
        fila.setContentsMargins(12, 8, 12, 8)
        icono = QLabel()
        pixmap = QPixmap(str(ASSETS / "icon.png"))
        if not pixmap.isNull():
            icono.setPixmap(pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        icono.setStyleSheet("background: transparent;")
        fila.addWidget(icono)
        fila.addSpacing(8)
        fila.addWidget(_etiqueta("TRADE DESK", 14, True))
        fila.addStretch(1)
        brokers_btn = _boton("Brokers", 78, 22, size=10)
        brokers_btn.clicked.connect(self._abrir_brokers)
        fila.addWidget(brokers_btn)
        fila.addSpacing(10)
        # respaldo cuando no hay ningun broker conectado
        self._lbl_saldo = _etiqueta("— USDT", 11, muted=True)
        fila.addWidget(self._lbl_saldo)
        self._caja_saldos = QHBoxLayout()
        self._caja_saldos.setSpacing(8)
        fila.addLayout(self._caja_saldos)
        fila.addSpacing(10)
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
        v6 = (getattr(self, "_ip", {}) or {}).get("v6")
        extra = f" · IPv6 {v6} en el tooltip" if v6 else ""
        self.statusBar().showMessage(f"IP {ip} copiada.{extra}")

    def _añadir_par(self):
        if not self.session.mercados:
            self._notificar("Catálogo", "Todavía se está cargando el catálogo de MEXC.")
            return
        symbol = buscar(self, self.session.mercados)
        if not symbol:
            return
        self.session.add_card(symbol)
        self.statusBar().showMessage(f"{symbol} añadido · elegí el broker en la tarjeta.")

    def _cambio_dry(self, activo):
        self._dry = bool(activo)
        self.chk_dry.setText("DRY-RUN" if self._dry else "REAL")
        self.chk_dry.setStyleSheet(f"QCheckBox {{ color: {t.GOLD if self._dry else t.RED}; }}")
        self.statusBar().showMessage(
            "DRY-RUN activo · no abre ni cierra posiciones"
            if self._dry
            else "REAL · las órdenes se envían"
        )

    # --------------------------------------------------------- fila de tarjetas
    TARJETA_W = 286
    TARJETA_GAP = 10
    ANIM_MS = 150

    def _armar_deck(self):
        deck = QScrollArea()
        deck.setWidgetResizable(True)
        deck.setFrameShape(QFrame.NoFrame)
        deck.setFixedHeight(470)
        contenido = QWidget()
        fila = QHBoxLayout(contenido)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(10)
        # las tarjetas se colocan a mano: así el arrastre anima cada una por separado
        self._lienzo = QWidget()
        self._lienzo.setFixedHeight(436)
        fila.addWidget(self._lienzo, 0, Qt.AlignTop)
        fila.addStretch(1)
        agregar = _boton("+ Añadir par", 120, 34)
        agregar.clicked.connect(self._añadir_par)
        fila.addWidget(agregar, 0, Qt.AlignTop)
        deck.setWidget(contenido)
        return deck

    def _paso(self):
        return self.TARJETA_W + self.TARJETA_GAP

    def _ubicar(self, animar=True, saltar=None):
        """Coloca cada tarjeta en su slot (animando si se pide)."""
        paso = self._paso()
        for indice, carta in enumerate(self._cartas):
            if carta is saltar:
                continue
            destino = QPoint(indice * paso, 0)
            if animar:
                self._animar_carta(carta, destino)
            else:
                self._detener(carta)
                carta.move(destino)
        self._lienzo.setMinimumWidth(max(1, len(self._cartas) * paso - self.TARJETA_GAP))

    def _animar_carta(self, carta, destino):
        self._detener(carta)
        anim = QPropertyAnimation(carta, b"pos", self)
        anim.setDuration(self.ANIM_MS)
        anim.setStartValue(carta.pos())
        anim.setEndValue(destino)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._anims[carta] = anim

    def _detener(self, carta):
        anim = self._anims.pop(carta, None)
        if anim is not None:
            anim.stop()

    def _indice_destino(self, tarjeta):
        """Slot donde caería: cuántas tarjetas quedan a la izquierda de su centro."""
        centro = tarjeta.x() + tarjeta.width() // 2
        paso = self._paso()
        indice = 0
        for carta in self._cartas:
            if carta is tarjeta:
                continue
            if centro > indice * paso + self.TARJETA_W // 2:
                indice += 1
            else:
                break
        return indice

    def _arrastre_tarjeta(self, tarjeta, accion, punto=None):
        """Arrastre en vivo sin hueco.

        La tarjeta agarrada sigue al cursor (queda por encima) y las demás se
        animan a su slot nuevo, como si la primera las empujara.
        """
        if accion == "inicio":
            self._arrastrada = tarjeta
            self._desfase = punto  # punto donde se agarró, en coords de la tarjeta
            self._destino = self._cartas.index(tarjeta) if tarjeta in self._cartas else 0
            tarjeta.raise_()
        elif accion == "mover" and self._arrastrada is not None:
            local = self._lienzo.mapFromGlobal(punto)
            tarjeta.move(local - self._desfase)
            destino = self._indice_destino(tarjeta)
            if destino != self._destino:
                self._destino = destino
                otras = [c for c in self._cartas if c is not tarjeta]
                otras.insert(min(destino, len(otras)), tarjeta)
                self._cartas = otras
                self._ubicar(animar=True, saltar=tarjeta)
        elif accion == "fin" and self._arrastrada is not None:
            self._animar_carta(tarjeta, QPoint(self._destino * self._paso(), 0))
            self.session.mover_tarjeta(tarjeta.tarjeta["id"], self._destino)
            self._arrastrada = None
            self._destino = None
            self.statusBar().showMessage("Orden de las tarjetas guardado.")

    def _armar_pestanas(self):
        self._tabs = QTabWidget()

        posiciones = QWidget()
        col_pos = QVBoxLayout(posiciones)
        col_pos.setContentsMargins(0, 0, 0, 0)
        col_pos.setSpacing(6)
        barra_pos = QHBoxLayout()
        self._lbl_abiertas = _etiqueta("0 abiertas", 11, muted=True)
        barra_pos.addWidget(self._lbl_abiertas)
        # bruto y neto de TODAS las posiciones abiertas (las filas no cambian)
        self._lbl_bruto = _etiqueta("", 11, True, t.MUTED)
        barra_pos.addWidget(self._lbl_bruto)
        barra_pos.addWidget(_etiqueta("·", 11, False, t.MUTED))
        self._lbl_neto = _etiqueta("", 11, True, t.MUTED)
        barra_pos.addWidget(self._lbl_neto)
        barra_pos.addStretch(1)
        self._btn_be = _boton("Poner a BE", 110, 26)
        self._btn_be.clicked.connect(lambda: self.control.be_todas(self._posiciones))
        barra_pos.addWidget(self._btn_be)
        self._btn_sel = _boton("Cerrar seleccionadas", 170, 26)
        self._btn_sel.clicked.connect(self._cerrar_seleccionadas)
        barra_pos.addWidget(self._btn_sel)
        todo = _boton("CERRAR TODO", 120, 26, t.DANGER_SOFT, t.RED)
        todo.clicked.connect(lambda: self.control.cerrar_todo(len(self._seleccionadas())))
        barra_pos.addWidget(todo)
        col_pos.addLayout(barra_pos)
        self._tabla_pos = self._tabla_posiciones()
        self._col_fee = 1 + next(i for i, col in enumerate(POS_COLS) if col[0] == "fee")
        self._tabla_pos.viewport().setMouseTracking(True)
        self._tabla_pos.entered.connect(self._hover_posiciones)
        self._tabla_pos.viewport().installEventFilter(self)
        self._bocadillo = Bocadillo(self)
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
        col_hist.setSpacing(6)
        barra_hist = QHBoxLayout()
        barra_hist.setSpacing(8)
        self._lbl_hist = _etiqueta("Historial", 11, muted=True)
        barra_hist.addWidget(self._lbl_hist)
        self._spin_hist = Spinner(14)
        barra_hist.addWidget(self._spin_hist, 0, Qt.AlignVCenter)
        self._lbl_cargando = _etiqueta("Cargando…", 10, muted=True)
        self._lbl_cargando.hide()
        barra_hist.addWidget(self._lbl_cargando)
        barra_hist.addStretch(1)
        self._btn_mas = _boton("Ver más", 110, 26)
        self._btn_mas.clicked.connect(self._pedir_mas_historial)
        barra_hist.addWidget(self._btn_mas)
        col_hist.addLayout(barra_hist)
        self._tabla_hist = _tabla(OPER_COLS, 38)
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
                # los errores del poller (tipico: 510 Demasiadas peticiones) van a la
                # barra de estado: un modal por cada reintento tapa la app entera
                if mensaje[1] != self._ultimo_error:
                    self._ultimo_error = mensaje[1]
                    self.statusBar().showMessage(mensaje[1], 8000)
            elif tipo == "cards":
                self._pintar_deck(mensaje[1])
            elif tipo == "ticker":
                self._actualizar_precio(*mensaje[1:])
            elif tipo == "balances":
                self._pintar_saldos(mensaje[1])
            elif tipo == "funding":
                # tasa y hora del próximo funding: cambia lento, se guarda y se usa
                # en el globo de la fee del siguiente refresco (3 s)
                self._fondos = mensaje[1]
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
            elif tipo == "history_mas":
                self._hay_mas_hist = bool(mensaje[1])
                self._btn_mas.setEnabled(self._hay_mas_hist and not self._hist_cargando)
                self._btn_mas.setText("Ver más" if self._hay_mas_hist else "Sin más")
            elif tipo == "history_cargando":
                cargando = bool(mensaje[1])
                self._hist_cargando = cargando
                if cargando:
                    self._spin_hist.empezar()
                else:
                    self._spin_hist.parar()
                self._lbl_cargando.setVisible(cargando)
                self._btn_mas.setEnabled(not cargando and self._hay_mas_hist)
                self._btn_mas.setText(
                    "Cargando…" if cargando else ("Ver más" if self._hay_mas_hist else "Sin más")
                )
            elif tipo == "ip":
                datos = mensaje[1] if isinstance(mensaje[1], dict) else {"v4": mensaje[1]}
                self._ip = datos
                self._lbl_ip.setText(f"IP {datos.get('v4') or '—'}")
                self._lbl_ip.setToolTip(
                    f"IPv4 {datos.get('v4') or '—'}\nIPv6 {datos.get('v6') or '—'}\n"
                    "La key se ata a la que ve el exchange: los clientes usan la IPv4."
                )
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

        self.control.abrir(side, form, al_enviar=enviar, exchange=tarjeta.broker())

    def _actualizar_precio(self, ident, precio, cambio=0.0):
        tarjeta = self._tarjetas.get(ident)
        if tarjeta is not None:
            tarjeta.set_precio(precio, cambio)
        self.statusBar().showMessage(f"{len(self._posiciones)} posiciones abiertas")

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

    def showEvent(self, evento):
        super().showEvent(evento)
        # la barra de titulo solo se pinta oscura si DWM repinta el marco ahora
        barra_oscura(self)

    def _pintar_deck(self, tarjetas):
        """Crea solo las tarjetas nuevas y reusa las que siguen.

        Antes se borraban todas: al añadir un par se reconstruia el deck entero
        y se perdia lo escrito en el tamaño, TP y SL de las demas cajas.
        """
        viejas = dict(self._tarjetas)
        clientes = dict(self.session.clientes())
        orden = []
        for datos in tarjetas:
            widget = viejas.pop(datos["id"], None)
            if widget is None:
                widget = Tarjeta(
                    datos,
                    clientes,
                    on_trade=self._trade,
                    on_remove=self._quitar_par,
                    on_broker=self._cambio_broker,
                    on_arrastre=self._arrastre_tarjeta,
                )
                widget.setParent(self._lienzo)
                widget.show()
            orden.append(widget)
        for sobrante in viejas.values():
            sobrante.hide()
            sobrante.deleteLater()
        self._tarjetas = {
            datos["id"]: widget for datos, widget in zip(tarjetas, orden, strict=True)
        }
        self._cartas = orden
        self._anims = {}
        self._arrastrada = None
        self._destino = None
        self._ubicar(animar=False)

    def _cambio_broker(self, tarjeta, nombre):
        ident = tarjeta.tarjeta["id"]
        self.session.set_exchange(ident, nombre)
        self.statusBar().showMessage(
            f"{tarjeta.tarjeta['symbol']} ahora opera en {nombre.upper()}."
        )

    def _quitar_par(self, ident):
        self.session.remove_card(ident)
        self._tarjetas.pop(ident, None)

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
                if clave in ORDER_PENCILS:
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
            neto = pnl - fee
            estado = fila.get("estado") or ""
            cierre = fila.get("cierre") or 0
            lado = fila.get("lado") or "—"
            valores = {
                "apertura": lineas((_cuando(fila.get("apertura")), 12, False, t.MUTED)),
                "cierre": lineas((_cuando(cierre) if cierre else "—", 12, False, t.MUTED)),
                "lado": lineas((lado, 12, True, t.GREEN if lado == "LONG" else t.RED)),
                "qty": lineas((_tamano_usdt(fila), 12, False, t.TEXT)),
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


def build_main_window():
    return VistaQt()
