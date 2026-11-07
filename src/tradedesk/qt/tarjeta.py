"""Tarjeta de par: apalancamiento, margen, tamaño, TP/SL y el resumen vivo.

La barra de cierre de la fila vive en `qt/cierre.py`; acá se reexporta para que
los imports de la vista no cambien.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QToolButton,
    QVBoxLayout,
)

from .. import theme as t
from ..brokers import NOMBRES, TITULOS
from ..forms import form_tarjeta
from . import dialogs
from .cierre import BarraCierre
from .style import Segmentado, fnt, logo, menu_estilo
from .style import boton as _boton
from .style import etiqueta as _etiqueta

PRESETS = (1, 5, 10, 15, 20, 50)
PISTAS = "escribe el tamaño en USDT"

__all__ = ["BarraCierre", "Tarjeta"]


class Tarjeta(QFrame):
    """Una tarjeta de par: apalancamiento, tamaño, TP/SL y el resumen vivo."""

    def __init__(
        self, tarjeta, clientes, on_trade=None, on_remove=None, on_broker=None, on_arrastre=None
    ):
        super().__init__()
        self.tarjeta = tarjeta
        self.clientes = clientes or {}
        self.on_trade = on_trade or (lambda _c, _s: None)
        self.on_remove = on_remove or (lambda _s: None)
        self.on_broker = on_broker or (lambda _c, _n: None)
        self.on_arrastre = on_arrastre or (lambda _c, _a, _p=None: None)
        self.limite = 0.0
        self._presets = {}
        self._ocupado = False
        self._arrastre = None
        self._cursor = None
        self._moviendo = False
        self.setObjectName("card")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedSize(286, 436)

        columna = QVBoxLayout(self)
        columna.setContentsMargins(12, 12, 12, 12)
        columna.setSpacing(6)

        cabecera = QHBoxLayout()
        cabecera.setSpacing(6)
        cabecera.addWidget(_etiqueta(tarjeta["nombre"], 13, True))
        self.btn_broker = QToolButton()
        self.btn_broker.setFixedSize(86, 22)
        self.btn_broker.setCursor(Qt.PointingHandCursor)
        self.btn_broker.setToolTip("Elegir broker")
        self.btn_broker.setStyleSheet(
            f"QToolButton {{ border: 1px solid {t.BORDER}; border-radius: {t.R_CHIP}px;"
            f" background: {t.INPUT}; color: {t.MUTED}; }}"
            f"QToolButton:hover {{ border: 1px solid {t.MUTED}; }}"
        )
        self.btn_broker.clicked.connect(self._menu_broker)
        cabecera.addWidget(self.btn_broker)
        cabecera.addStretch(1)
        quitar = _boton("✕", 24, 24, "transparent", t.MUTED, t.R_CHIP, 13, False)
        quitar.clicked.connect(lambda: self.on_remove(self.tarjeta["id"]))
        cabecera.addWidget(quitar)
        columna.addLayout(cabecera)
        self._pintar_broker()

        fila_precio = QHBoxLayout()
        self.lbl_precio = _etiqueta("—", 19, True)
        fila_precio.addWidget(self.lbl_precio)
        fila_precio.addStretch(1)
        self.lbl_cambio = _etiqueta("", 12, color=t.GREEN)
        fila_precio.addWidget(self.lbl_cambio)
        columna.addLayout(fila_precio)

        fila_palanca = QHBoxLayout()
        fila_palanca.setSpacing(6)
        fila_palanca.addWidget(_etiqueta("Apalancamiento", 12, muted=True))
        fila_palanca.addStretch(1)
        self.in_palanca = QLineEdit(tarjeta["leverage"])
        self.in_palanca.setFixedSize(46, 24)
        self.in_palanca.setAlignment(Qt.AlignRight)
        fila_palanca.addWidget(self.in_palanca)
        fila_palanca.addWidget(_etiqueta("x", 12, muted=True))
        columna.addLayout(fila_palanca)

        fila_presets = QHBoxLayout()
        fila_presets.setSpacing(3)
        for valor in PRESETS:
            preset = _boton(str(valor), 32, 24, size=11)
            preset.clicked.connect(lambda _=False, v=valor: self._poner_palanca(v))
            fila_presets.addWidget(preset)
            self._presets[valor] = preset
        fila_presets.addStretch(1)
        columna.addLayout(fila_presets)

        self.seg_margen = Segmentado(("Aislado", "Cruzado"), tarjeta["margin"], self._cambio_margen)
        self.seg_margen.setFixedHeight(26)
        columna.addWidget(self.seg_margen)
        self.seg_modo = Segmentado(("Margen", "Nocional"), tarjeta["size_mode"], self._cambio_modo)
        self.seg_modo.setFixedHeight(26)
        columna.addWidget(self.seg_modo)

        fila_rotulo = QHBoxLayout()
        fila_rotulo.addWidget(_etiqueta("Tamaño (USDT)", 10, muted=True))
        fila_rotulo.addStretch(1)
        self.chip_limite = _boton("Mercado", 84, 20, size=10)
        self.chip_limite.clicked.connect(self._menu_limite)
        fila_rotulo.addWidget(self.chip_limite)
        columna.addLayout(fila_rotulo)

        caja_tamano = QFrame()
        caja_tamano.setFixedHeight(36)
        caja_tamano.setStyleSheet(
            f"QFrame {{ background: {t.INPUT}; border: 1px solid {t.BORDER};"
            f" border-radius: {t.R_CTRL}px; }}"
            f"QLineEdit {{ background: transparent; border: 0px; color: {t.TEXT};"
            f" padding: 0px 6px; }}"
            f"QLabel {{ background: transparent; color: {t.MUTED}; }}"
        )
        fila_tamano = QHBoxLayout(caja_tamano)
        fila_tamano.setContentsMargins(2, 0, 8, 0)
        fila_tamano.setSpacing(2)
        self.in_tamano = QLineEdit("")
        self.in_tamano.setFont(fnt(16, True))
        self.in_tamano.setAlignment(Qt.AlignRight)
        fila_tamano.addWidget(self.in_tamano, 1)
        fila_tamano.addWidget(_etiqueta("USDT", 10, muted=True))
        columna.addWidget(caja_tamano)

        fila_stops = QHBoxLayout()
        fila_stops.setSpacing(4)
        for rotulo in ("TP", "SL"):
            fila_stops.addWidget(_etiqueta(rotulo, 10, muted=True), 1)
        columna.addLayout(fila_stops)
        fila_entradas = QHBoxLayout()
        fila_entradas.setSpacing(4)
        self.in_tp = QLineEdit("")
        self.in_sl = QLineEdit("")
        for entrada in (self.in_tp, self.in_sl):
            entrada.setFixedHeight(34)
            entrada.setFont(fnt(12))
            entrada.setAlignment(Qt.AlignRight)
            fila_entradas.addWidget(entrada, 1)
        columna.addLayout(fila_entradas)

        self.lbl_resumen = _etiqueta(PISTAS, 12, muted=True)
        self.lbl_resumen.setWordWrap(True)
        self.lbl_resumen.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        columna.addWidget(self.lbl_resumen)
        columna.addStretch(1)

        fila_botones = QHBoxLayout()
        fila_botones.setSpacing(8)
        self.btn_long = _boton("LONG", None, 34, t.GREEN, t.BG, t.R_CTRL, 14)
        self.btn_short = _boton("SHORT", None, 34, t.RED, t.BG, t.R_CTRL, 14)
        self.btn_long.clicked.connect(lambda: self.on_trade(self, "LONG"))
        self.btn_short.clicked.connect(lambda: self.on_trade(self, "SHORT"))
        fila_botones.addWidget(self.btn_long)
        fila_botones.addWidget(self.btn_short)
        columna.addLayout(fila_botones)

        for entrada in (self.in_palanca, self.in_tamano, self.in_tp, self.in_sl):
            entrada.textChanged.connect(self._actualizar)
        self._actualizar()

    # ------------------------------------------------------------------ estado
    def _cambio_margen(self, valor):
        self.tarjeta["margin"] = valor

    def _cambio_modo(self, valor):
        self.tarjeta["size_mode"] = valor
        self._actualizar()

    def _poner_palanca(self, valor):
        self.in_palanca.setText(str(valor))

    def _marcar_presets(self):
        """El preset que coincide con el apalancamiento se ve seleccionado."""
        try:
            activo = int(float(self.in_palanca.text() or 0))
        except ValueError:
            activo = 0
        for valor, boton in self._presets.items():
            elegido = valor == activo
            boton.setStyleSheet(
                f"QPushButton {{ background: {t.SURFACE if elegido else t.INPUT};"
                f" color: {t.TEXT if elegido else t.MUTED};"
                f" border: 1px solid {t.GREEN if elegido else t.BORDER};"
                f" border-radius: {t.R_CHIP}px; }}"
                f"QPushButton:hover {{ border: 1px solid {t.MUTED}; }}"
            )

    def form(self):
        """Valores ya parseados, o None si algo no es número."""
        return form_tarjeta(
            self.tarjeta["symbol"],
            self.in_palanca.text(),
            self.in_tamano.text(),
            self.in_tp.text(),
            self.in_sl.text(),
            self.tarjeta["margin"],
            self.tarjeta["size_mode"],
            self.limite,
        )

    def set_busy(self, activo):
        self._ocupado = bool(activo)
        self.btn_long.setEnabled(not activo)
        self.btn_short.setEnabled(not activo)

    # ------------------------------------------------------------------ broker
    def broker(self):
        return self.tarjeta.get("exchange") or ""

    # --------------------------------------------------------------- arrastre
    def mousePressEvent(self, evento):
        """Arranca el arrastre solo desde la cabecera (no sobre los inputs)."""
        if evento.button() == Qt.LeftButton and evento.position().y() < 46:
            self._arrastre = evento.position().toPoint()
            self._cursor = evento.globalPosition().toPoint()
        super().mousePressEvent(evento)

    def mouseMoveEvent(self, evento):
        if self._arrastre is None or not (evento.buttons() & Qt.LeftButton):
            return super().mouseMoveEvent(evento)
        global_ = evento.globalPosition().toPoint()
        if not self._moviendo:
            if (global_ - self._cursor).manhattanLength() < QApplication.startDragDistance():
                return
            self._moviendo = True
            self.on_arrastre(self, "inicio", self._arrastre)
        self.on_arrastre(self, "mover", global_)

    def mouseReleaseEvent(self, evento):
        if self._moviendo:
            self._moviendo = False
            self.on_arrastre(self, "fin")
        self._arrastre = None
        super().mouseReleaseEvent(evento)

    def _pintar_broker(self):
        nombre = self.broker()
        if nombre:
            imagen = logo(nombre, 15, completo=True)
            self.btn_broker.setIcon(QIcon(imagen))
            self.btn_broker.setIconSize(imagen.size())
            self.btn_broker.setText("")
        else:
            self.btn_broker.setIcon(QIcon())
            self.btn_broker.setText("Broker")

    def _menu_broker(self):
        """Selector del broker: los logos en el desplegable, como en MEXC."""
        menu = QMenu(self)
        menu.setStyleSheet(menu_estilo())
        actual = self.broker()
        acciones = {}
        for nombre in NOMBRES:
            titulo = TITULOS[nombre]
            accion = menu.addAction(QIcon(logo(nombre, 14)), titulo)
            accion.setCheckable(True)
            accion.setChecked(nombre == actual)
            acciones[accion] = nombre
        elegido = menu.exec(self.btn_broker.mapToGlobal(self.btn_broker.rect().bottomLeft()))
        if elegido not in acciones:
            return
        nombre = acciones[elegido]
        if nombre == actual:
            return
        self.tarjeta["exchange"] = nombre
        self._pintar_broker()
        self.on_broker(self, nombre)
        self._actualizar()

    def set_precio(self, precio, cambio=0.0):
        """Precio y variación del ticker: se actualiza sin pedir nada a la red."""
        self.tarjeta["precio"] = float(precio or 0)
        self.lbl_precio.setText(t.fmt_price(self.tarjeta["precio"]))
        self.lbl_cambio.setText(t.fmt_pct(cambio))
        self.lbl_cambio.setStyleSheet(
            f"color: {t.GREEN if cambio >= 0 else t.RED}; background: transparent;"
        )
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
            self.chip_limite.setText("Mercado")
        elif elegido is limite:
            res = dialogs.form(
                self,
                "Precio límite",
                [("precio", "Precio", f"{float(self.tarjeta['precio'] or 0):.6f}".rstrip("0"))],
                nota="La orden sale a límite: puede quedar sin llenar.",
            )
            if res and res["precio"]:
                try:
                    precio = float(res["precio"].replace(",", ""))
                except ValueError:
                    precio = 0.0
                if precio > 0:
                    self.limite = precio
                    self.chip_limite.setText(f"{precio:,.2f}")
        self._actualizar()

    def _actualizar(self):
        exchange = self.broker()
        cliente = self.clientes.get(exchange) if exchange else None
        self._marcar_presets()
        if cliente is None:
            self.lbl_precio.setText("—")
            self.lbl_cambio.setText("")
            self.lbl_resumen.setText(
                "Elige un broker para operar" if not exchange else f"Falta la key de {exchange}"
            )
            self.btn_long.setEnabled(False)
            self.btn_short.setEnabled(False)
            return
        self.lbl_precio.setText(t.fmt_price(self.tarjeta["precio"]))
        self.btn_long.setEnabled(not self._ocupado)
        self.btn_short.setEnabled(not self._ocupado)
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
            self.lbl_resumen.setText(PISTAS)
            return
        contrato = self.tarjeta["contrato"] or {}
        try:
            if exchange in ("bitunix", "bingx"):
                qty = cliente.size_to_qty(self.tarjeta["symbol"], nocional, precio)
                real = cliente.qty_to_usdt(self.tarjeta["symbol"], qty, precio)
                unidad = contrato.get("base") or self.tarjeta["symbol"].split("_")[0]
                resumen = f"{t.fmt_qty(qty)} {unidad} · {t.fmt_usdt(real)} USDT"
                if exchange == "bingx":
                    fee = real * float(contrato.get("takerFeeRate") or 0)
                    resumen += f"\nfee estimada {t.fmt_fee(fee)}"
                self.lbl_resumen.setText(resumen)
                return
            vol = cliente.size_to_vol(self.tarjeta["symbol"], nocional, precio, contract=contrato)
            real = cliente.vol_to_usdt(self.tarjeta["symbol"], vol, precio)
            fee = cliente.est_fee(self.tarjeta["symbol"], real)
            liq_l = cliente.est_liq(self.tarjeta["symbol"], precio, palanca, "LONG")
            liq_s = cliente.est_liq(self.tarjeta["symbol"], precio, palanca, "SHORT")
            self.lbl_resumen.setText(
                f"{vol:.0f} contratos · {real:,.2f} USDT\n"
                f"fee {fee:.4f} · liq {liq_l:,.2f} / {liq_s:,.2f}"
            )
        except Exception as exc:
            self.lbl_resumen.setText(f"No se pudo calcular el resumen ({type(exc).__name__}).")
