"""Tarjeta de par y barra de cierre de la fila (Qt), con la geometría de la Tk.

Las medidas salen del `cards.py` / `closebar.py` que tenía la versión Tkinter:
la tarjeta es 286×436, los segmentados van uno debajo del otro a todo el ancho,
el tamaño lleva el `USDT` dentro de la caja y el `%` de cierre abre un panel con
slider (estilo MEXC) que se aplica al soltar.
"""

import math

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFontMetrics, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import theme as t
from ..brokers import NOMBRES, TITULOS
from ..forms import form_tarjeta, volumen_cerrar
from . import dialogs
from .style import Segmentado, fnt, logo
from .style import boton as _boton
from .style import etiqueta as _etiqueta

PRESETS = (1, 5, 10, 15, 20, 50)
PISTAS = "escribe el tamaño en USDT"


def _mark(position):
    """Precio de marca derivado del PnL (open_positions no lo manda)."""
    cantidad = float(position.get("holdVol") or 0)
    tamano = float(position.get("_contractSize") or 0)
    if not (cantidad and tamano):
        return 0.0
    signo = 1 if int(position.get("positionType") or 1) == 1 else -1
    return (
        float(position.get("holdAvgPrice") or 0)
        + (float(position.get("unRealizedPnl") or 0) / (cantidad * tamano)) * signo
    )


def _estilo_boton(fondo, color):
    return (
        f"QPushButton {{ background: {fondo}; color: {color}; border: 1px solid {t.BORDER};"
        f" border-radius: {t.R_CHIP}px; }}"
        f"QPushButton:hover {{ border: 1px solid {t.MUTED}; }}"
    )


class SliderPct(QSlider):
    """Slider del % lineal de 1 a 100, con el aspecto de MEXC.

    El clic y el arrastre se mapean a mano sobre la misma geometria que se pinta:
    el estilo de Qt calcula la posicion con la caja del handle, que no coincide
    con la pista dibujada, y con eso el primer clic caia en otro valor.
    """

    MARGEN = 10
    ALTO = 54

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.setFixedHeight(self.ALTO)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimum(1)
        self.setMaximum(100)
        self._minimo_valido = 1

    def set_minimo_valido(self, pct):
        """Hasta ese % no se cierra ni un contrato: se pinta apagado."""
        self._minimo_valido = max(1, int(pct))
        self.update()

    # --------------------------------------------------------------- geometria
    def _x(self, valor):
        ancho = max(1, self.width() - 2 * self.MARGEN)
        rango = max(1, self.maximum() - self.minimum())
        x = self.MARGEN + round(ancho * (valor - self.minimum()) / rango)
        return min(self.width() - self.MARGEN, max(self.MARGEN, x))

    def _valor(self, x):
        ancho = max(1, self.width() - 2 * self.MARGEN)
        parte = min(1.0, max(0.0, (x - self.MARGEN) / ancho))
        return round(self.minimum() + parte * (self.maximum() - self.minimum()))

    # ------------------------------------------------------------------- raton
    def mousePressEvent(self, evento):
        if evento.button() == Qt.LeftButton:
            self.setValue(self._valor(int(evento.position().x())))
            evento.accept()
            return
        super().mousePressEvent(evento)

    def mouseMoveEvent(self, evento):
        if evento.buttons() & Qt.LeftButton:
            self.setValue(self._valor(int(evento.position().x())))
            evento.accept()
            return
        super().mouseMoveEvent(evento)

    # ---------------------------------------------------------------- pintura
    def paintEvent(self, _evento):
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.Antialiasing, True)
        y = 30
        x = self._x(self.value())
        inicio = self.MARGEN
        fin = self.width() - self.MARGEN

        pintor.setPen(Qt.NoPen)
        pintor.setBrush(QColor(t.INPUT))
        pintor.drawRoundedRect(QRect(inicio, y - 2, max(1, fin - inicio), 4), 2, 2)
        tramo_apagado = self._x(self._minimo_valido) - inicio
        if tramo_apagado > 0:
            pintor.setBrush(QColor(t.BORDER))
            pintor.drawRoundedRect(QRect(inicio, y - 2, tramo_apagado, 4), 2, 2)
        pintor.setBrush(QColor(t.GREEN))
        pintor.drawRoundedRect(QRect(inicio, y - 2, max(0, x - inicio), 4), 2, 2)

        letra_marca = fnt(9)
        pintor.setFont(letra_marca)
        for paso in (0, 25, 50, 75, 100):
            px = self._x(paso)
            if abs(px - x) > 7:
                pintor.setPen(Qt.NoPen)
                pintor.setBrush(QColor(t.MUTED if paso >= self._minimo_valido else t.BORDER))
                pintor.drawEllipse(QPoint(px, y), 2, 2)
            pintor.setPen(QPen(QColor(t.MUTED if paso <= self.value() else t.BORDER)))
            pintor.drawText(QRect(px - 20, y + 8, 40, 14), Qt.AlignCenter, str(paso))

        pintor.setPen(Qt.NoPen)
        pintor.setBrush(QColor(t.TEXT))
        pintor.drawEllipse(QPoint(x, y), 6, 6)

        texto = f"{self.value()}%"
        letra = fnt(11, True)
        ancho_texto = QFontMetrics(letra).horizontalAdvance(texto) + 14
        caja = QRect(x - ancho_texto // 2, 0, ancho_texto, 20)
        caja.moveLeft(max(0, min(caja.left(), self.width() - ancho_texto)))
        pintor.setBrush(QColor(t.INPUT))
        pintor.setPen(QPen(QColor(t.BORDER), 1))
        pintor.drawRoundedRect(caja, 5, 5)
        pintor.setPen(QPen(QColor(t.TEXT)))
        pintor.setFont(letra)
        pintor.drawText(caja, Qt.AlignCenter, texto)
        pintor.end()


class PanelPct(QDialog):
    """Panel del `%` de cierre: slider, valor escrito y resumen de lo que cierra."""

    def __init__(self, barra):
        super().__init__(barra, Qt.Popup)
        self.barra = barra
        self.setFixedWidth(250)
        self.setStyleSheet(
            f"QDialog {{ background: {t.CARD}; border: 1px solid {t.BORDER}; }}"
            f"QLabel {{ color: {t.MUTED}; background: transparent; }}"
            f"QLineEdit {{ background: {t.INPUT}; color: {t.TEXT}; border: 1px solid {t.BORDER};"
            f" border-radius: {t.R_CHIP}px; padding: 3px 6px; }}"
        )
        columna = QVBoxLayout(self)
        columna.setContentsMargins(12, 8, 12, 10)
        columna.setSpacing(2)

        self.lbl_resumen = _etiqueta("", 10)
        self.lbl_resumen.setWordWrap(True)
        columna.addWidget(self.lbl_resumen)

        self.slider = SliderPct()
        self.slider.set_minimo_valido(barra.min_pct())
        self.slider.setValue(int(barra.pct))
        self.slider.valueChanged.connect(self._deslizar)
        columna.addWidget(self.slider)

        fila = QHBoxLayout()
        fila.setSpacing(4)
        self.in_pct = QLineEdit(f"{barra.pct:.0f}")
        self.in_pct.setAlignment(Qt.AlignRight)
        self.in_pct.setFixedWidth(56)
        self.in_pct.textChanged.connect(self._escrito)
        fila.addWidget(self.in_pct)
        fila.addWidget(_etiqueta("%", 12))
        fila.addStretch(1)
        listo = _boton("Listo", 70, 24, t.GREEN, t.BG)
        listo.clicked.connect(self.accept)
        fila.addWidget(listo)
        columna.addLayout(fila)
        self.adjustSize()
        self._deslizar(int(barra.pct))

    def leaveEvent(self, evento):
        """Se cierra al salir el mouse: si queda abierto, es un popup y el
        primer clic en Cerrar lo cierra a el en vez de abrir el dialogo."""
        if QApplication.mouseButtons() == Qt.NoButton:
            self.close()
        super().leaveEvent(evento)

    def _deslizar(self, valor):
        self.barra.set_pct(valor)
        # si el % quedo por debajo del minimo que cierra 1 contrato, la bolita
        # vuelve al minimo: se ve que no se puede bajar mas
        if self.slider.value() != int(self.barra.pct):
            self.slider.blockSignals(True)
            self.slider.setValue(int(self.barra.pct))
            self.slider.blockSignals(False)
        self.in_pct.blockSignals(True)
        self.in_pct.setText(f"{self.barra.pct:.0f}")
        self.in_pct.blockSignals(False)
        self._resumen()
        self.slider.update()

    def _escrito(self, texto):
        try:
            self.barra.set_pct(float(texto.replace(",", "")))
        except ValueError:
            return
        self.slider.blockSignals(True)
        self.slider.setValue(int(self.barra.pct))
        self.slider.blockSignals(False)
        self.slider.update()
        self._resumen()

    def _resumen(self):
        pct = self.barra.pct
        unidades = volumen_cerrar(self.barra.hold, pct, self.barra.paso)
        monto = self.barra.notional * pct / 100
        if self.barra.unidad == "contratos":
            unidad = "contrato" if unidades == 1 else "contratos"
        else:
            unidad = self.barra.unidad
        texto = f"Cierras: {t.fmt_fee(monto)} USDT ≈ {t.fmt_qty(unidades)} {unidad}"
        minimo = self.barra.min_pct()
        if self.barra.hold > self.barra.paso and pct <= minimo:
            texto += f" · mínimo {minimo:.0f}% para 1 {unidad}"
        self.lbl_resumen.setText(texto)


class BarraCierre(QWidget):
    """Los cuatro controles de la fila: Mercado · % · Cerrar · Reverse."""

    def __init__(self, position, pnl, largo, al_cerrar, al_reverse):
        super().__init__()
        self.al_cerrar = al_cerrar
        self.al_reverse = al_reverse
        self.pct = 100.0
        self.precio = 0.0
        self.position = position
        self.hold = 0.0
        self.notional = 0.0
        self.paso = 1.0
        self.unidad = "contratos"
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedSize(190, 52)
        fila1 = QHBoxLayout()
        fila1.setSpacing(4)
        fila2 = QHBoxLayout()
        fila2.setSpacing(4)
        self.btn_tipo = _boton("Mercado", 106, 22)
        self.btn_tipo.clicked.connect(self._menu_tipo)
        fila1.addWidget(self.btn_tipo)
        self.btn_pct = _boton("100%", 78, 22)
        self.btn_pct.clicked.connect(self._abrir_pct)
        fila1.addWidget(self.btn_pct)
        self.btn_cerrar = _boton("Cerrar", 102, 26)
        self.btn_cerrar.clicked.connect(self._cerrar)
        fila2.addWidget(self.btn_cerrar)
        reverse = _boton("Reverse", 82, 26)
        reverse.clicked.connect(lambda: self.al_reverse(self.position))
        fila2.addWidget(reverse)
        columna = QVBoxLayout(self)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(4)
        columna.addLayout(fila1)
        columna.addLayout(fila2)
        self.actualizar(position, pnl, largo)

    # ------------------------------------------------------------------ estado
    def set_fondo(self, color):
        """Color de la fila de la tabla (cambia cuando la posicion se mueve)."""
        if self.styleSheet() != f"background: {color};":
            self.setStyleSheet(f"background: {color};")

    def actualizar(self, position, pnl, largo):
        """Refresca datos y color sin recrear la barra: el `%` elegido se mantiene."""
        self.position = position
        self.hold = float(position.get("holdVol") or 0)
        self.notional = self.hold * float(position.get("_contractSize") or 0) * _mark(position)
        # MEXC opera en contratos enteros; Bitunix en monedas con su propio step
        self.paso = float(position.get("_qtyStep") or 1.0)
        self.unidad = "contratos" if (position.get("_exchange") or "mexc") == "mexc" else "monedas"
        color = t.GREEN if pnl > 0 else (t.RED if pnl < 0 else t.INPUT)
        self.btn_cerrar.setText(f"Cerrar {'LONG' if largo else 'SHORT'}")
        self.btn_cerrar.setStyleSheet(_estilo_boton(color, t.BG if pnl else t.TEXT))
        # una posicion de una sola unidad no se puede partir: el chip avisa
        # en vez de dejar mover el slider y que vuelva solo (parecia roto)
        partir = self.min_pct() < 100.0
        self.btn_pct.setEnabled(partir)
        self.btn_pct.setToolTip(
            ""
            if partir
            else (
                f"La posicion esta en el minimo del par ({t.fmt_qty(self.paso)}): "
                "no se puede cerrar por partes, solo el 100%."
            )
        )

    def min_pct(self):
        """% mínimo que todavía cierra una unidad (un contrato o un step del par)."""
        if self.hold <= 0:
            return 100.0
        return min(100.0, max(1.0, math.ceil(100.0 * self.paso / self.hold)))

    def set_pct(self, valor):
        self.pct = min(100.0, max(self.min_pct(), float(valor)))
        self.btn_pct.setText(f"{self.pct:.0f}%")

    def _abrir_pct(self):
        # sin `exec()`: el panel es modal y se comia el clic en Cerrar (se
        # elegia 30% y al pulsar Cerrar no pasaba nada). Con `show()` el resto
        # de la ventana sigue viva y el panel se cierra solo al salir.
        abierto = getattr(self, "_panel", None)
        if abierto is not None and abierto.isVisible():
            abierto.close()
            return
        panel = PanelPct(self)
        self._panel = panel
        punto = self.btn_pct.mapToGlobal(QPoint(0, 0))
        ancho, alto = panel.width(), panel.height()
        pantalla = self.screen().availableGeometry()
        # centrado sobre el boton: pegado a la derecha de la fila el panel se
        # iba contra el borde de la pantalla
        x = punto.x() + self.btn_pct.width() // 2 - ancho // 2
        x = min(max(pantalla.left() + 4, x), pantalla.right() - ancho - 4)
        y = punto.y() - alto - 6
        if y < pantalla.top() + 4:
            y = punto.y() + self.btn_pct.height() + 6
        panel.move(x, y)
        panel.show()

    def _menu_tipo(self):
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: {t.CARD}; color: {t.TEXT}; border: 1px solid {t.BORDER}; }}"
            f"QMenu::item:selected {{ background: {t.SURFACE}; }}"
        )
        mercado = menu.addAction("Mercado")
        limite = menu.addAction("Límite…")
        elegido = menu.exec(self.btn_tipo.mapToGlobal(self.btn_tipo.rect().bottomLeft()))
        if elegido is mercado:
            self.precio = 0.0
            self.btn_tipo.setText("Mercado")
        elif elegido is limite:
            res = dialogs.form(
                self.window(),
                "Cerrar a límite",
                [("precio", "Precio", "")],
                nota="Una orden límite puede quedar sin llenar.",
            )
            if res is None:
                return
            try:
                precio = float(res["precio"].replace(",", ""))
            except ValueError:
                return
            if precio > 0:
                self.precio = precio
                self.btn_tipo.setText(f"{precio:,.2f}")

    def _cerrar(self):
        self.al_cerrar(self.position, {"pct": self.pct, "price": self.precio or None})


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
        menu.setStyleSheet(
            f"QMenu {{ background: {t.CARD}; color: {t.TEXT}; border: 1px solid {t.BORDER}; }}"
            f"QMenu::item {{ padding: 6px 18px 6px 8px; }}"
            f"QMenu::item:selected {{ background: {t.SURFACE}; }}"
        )
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
        cliente = self.clientes.get(nombre)
        if cliente is not None:
            try:
                self.tarjeta["contrato"] = cliente.contract(self.tarjeta["symbol"]) or {}
            except Exception:
                pass
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
        if exchange == "bitunix":
            qty = cliente.size_to_qty(self.tarjeta["symbol"], nocional, precio)
            real = cliente.qty_to_usdt(self.tarjeta["symbol"], qty, precio)
            unidad = contrato.get("base") or "monedas"
            self.lbl_resumen.setText(f"{t.fmt_qty(qty)} {unidad} · {t.fmt_usdt(real)} USDT")
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
