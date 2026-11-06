"""Barra de cierre de la fila: chip de tipo, slider del % y los dos botones.

Es la parte de `tarjeta.py` que vive dentro de la tabla de posiciones.
"""

import math

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .. import theme as t
from ..forms import volumen_cerrar
from . import dialogs
from .style import boton as _boton
from .style import etiqueta as _etiqueta
from .style import fnt


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
