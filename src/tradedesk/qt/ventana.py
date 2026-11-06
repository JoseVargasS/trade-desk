"""Ventana principal: cabecera, deck arrastrable, pestañas y drenaje de la cola.

Las tres tablas viven en su módulo y se mezclan acá como mixins: la ventana es
una sola clase, pero el código queda partido por responsabilidad.

Toda la lógica de operar vive en `controller.Control`; aquí solo se pinta y se
leen los controles. Ningún pedido de red sale del hilo de la UI.
"""

import queue
import threading
import time

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import theme as t
from ..brokers import NOMBRES, TITULOS
from ..controller import Control
from ..layout import OPER_COLS, POS_COLS
from ..paths import ASSETS
from ..session import Session
from . import dialogs
from .cells import Bocadillo, Spinner, tabla
from .dialogs import QtPort
from .search import buscar
from .style import barra_oscura, logo, qss
from .style import boton as _boton
from .style import etiqueta as _etiqueta
from .tabla_historial import TablaHistorial
from .tabla_ordenes import TablaOrdenes
from .tabla_posiciones import TablaPosiciones
from .tarjeta import Tarjeta

BROKERS = NOMBRES


class VistaQt(TablaPosiciones, TablaOrdenes, TablaHistorial, QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Trade Desk")
        self.resize(1800, 1000)
        self._posiciones = []
        self._ordenes = []
        self._tarjetas = {}
        self._ultimo_error = ""
        self._error_hasta = 0.0
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
        self._mostrar_estado("DRY-RUN activo · no abre ni cierra posiciones")
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
        self._mostrar_estado("Key guardada. Listo para operar.")
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
        got = dialogs.ask_key(self, lambda k, s: clase(k, s).positions(), TITULOS[nombre])
        if not got:
            return
        creds.save(nombre, *got)
        self.session.poner_cliente(nombre, clase(*got))
        self._mostrar_estado(f"Claves de {nombre} guardadas.")

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
        self._mostrar_estado(f"IP {ip} copiada.{extra}")

    def _añadir_par(self):
        if not self.session.mercados:
            self._notificar("Catálogo", "Todavía se está cargando el catálogo de MEXC.")
            return
        symbol = buscar(self, self.session.mercados)
        if not symbol:
            return
        self.session.add_card(symbol)
        self._mostrar_estado(f"{symbol} añadido · elige el broker en la tarjeta.")

    def _cambio_dry(self, activo):
        self._dry = bool(activo)
        self.chk_dry.setText("DRY-RUN" if self._dry else "REAL")
        self.chk_dry.setStyleSheet(f"QCheckBox {{ color: {t.GOLD if self._dry else t.RED}; }}")
        self._mostrar_estado(
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
            if tarjeta not in self._cartas:
                return  # una caja que no esta en el deck no se arrastra
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
            self._mostrar_estado("Orden de las tarjetas guardado.")

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
        self._tabla_hist = tabla(OPER_COLS, 38)
        col_hist.addWidget(self._tabla_hist, 1)
        self._tabs.addTab(historial, "Historial")
        self._tabs.currentChanged.connect(self._cambio_pestana)
        return self._tabs

    def _cambio_pestana(self, indice):
        visible = self._tabs.tabText(indice) == "Historial"
        self.session.ver_historial = visible
        if visible:
            threading.Thread(target=self.session.cargar_historial, daemon=True).start()

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
                if mensaje[1] != self._ultimo_error or time.monotonic() >= self._error_hasta:
                    self._ultimo_error = mensaje[1]
                    self._mostrar_estado(mensaje[1], 8000, error=True)
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
                self._mostrar_estado(mensaje[1])
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

    def _mostrar_estado(self, texto, duracion=0, error=False):
        if error:
            self._error_hasta = time.monotonic() + duracion / 1000
        elif time.monotonic() < self._error_hasta:
            return
        self.statusBar().showMessage(texto, duracion)

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

    def _orden_terminada(self, *_):
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
        self._mostrar_estado(f"{len(self._posiciones)} posiciones abiertas")

    def showEvent(self, evento):
        super().showEvent(evento)
        # la barra de titulo solo se pinta oscura si DWM repinta el marco ahora
        barra_oscura(self)

    def _pintar_deck(self, tarjetas):
        """Crea solo las tarjetas nuevas y reusa las que siguen.

        Antes se borraban todas: al añadir un par se reconstruia el deck entero
        y se perdia lo escrito en el tamaño, TP y SL de las demas cajas.
        """
        # la sesion es la fuente de verdad de que tarjetas existen: un mensaje
        # atrasado puede traer una tarjeta que ya se borro y la resucitaria
        vivos = {t["id"] for t in self.session.tarjetas}
        tarjetas = [d for d in tarjetas if d["id"] in vivos]
        viejas = dict(self._tarjetas)
        clientes = dict(self.session.clientes())
        orden = []
        vistos = set()
        for datos in tarjetas:
            if datos["id"] in vistos:
                continue  # el mismo id dos veces: una sola tarjeta
            vistos.add(datos["id"])
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
            else:
                widget.tarjeta["contrato"] = datos["contrato"]
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
        self._mostrar_estado(f"{tarjeta.tarjeta['symbol']} ahora opera en {nombre.upper()}.")

    def _quitar_par(self, ident):
        self.session.remove_card(ident)
        widget = self._tarjetas.pop(ident, None)
        if widget is not None:
            # si la caja no se destruye aqui queda pegada en la ventana como
            # fantasma y al volver a agregar el par aparece una duplicada
            self._cartas = [c for c in self._cartas if c is not widget]
            widget.hide()
            widget.deleteLater()


def build_main_window():
    return VistaQt()
