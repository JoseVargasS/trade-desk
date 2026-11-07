"""Widgets visuales independientes de la pestaña Calendario."""

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen, QPolygon
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QToolTip, QWidget

from .. import theme as t
from .cells import fuente


class DelegadoMes(QStyledItemDelegate):
    """Pinta una celda del mes: el número del día y su PnL.

    A propósito no rellena la celda entera: los separadores de la tabla tienen
    que verse. Solo pinta el círculo de «hoy» y el tinte del día elegido.
    """

    def paint(self, pintor: QPainter, opcion, indice):
        datos = indice.data(Qt.UserRole)
        if not datos or datos.get("dia") is None:
            super().paint(pintor, opcion, indice)
            return
        caja = opcion.rect
        hoy = bool(datos.get("hoy"))
        operaciones = int(datos.get("operaciones") or 0)
        neto = float(datos.get("neto") or 0)
        pintor.save()
        pintor.setRenderHint(QPainter.TextAntialiasing, True)
        if datos.get("seleccionado"):
            pintor.fillRect(caja.adjusted(1, 1, -1, -1), QColor(t.INPUT))
        elif opcion.state & QStyle.State_MouseOver:
            pintor.fillRect(caja.adjusted(1, 1, -1, -1), QColor(t.SURFACE))

        letra_dia = fuente(14, True)
        alto_dia = QFontMetrics(letra_dia).height()
        if hoy:
            centro = QPoint(caja.center().x(), caja.top() + 5 + alto_dia // 2)
            pintor.setPen(Qt.NoPen)
            pintor.setBrush(QColor(t.ACCENT_SOFT))
            pintor.drawEllipse(centro, 11, 11)

        y = caja.top() + 5
        pintor.setFont(letra_dia)
        color_dia = t.TEXT if (operaciones or hoy) else t.MUTED
        pintor.setPen(QPen(QColor(color_dia)))
        pintor.drawText(
            QRect(caja.left(), y, caja.width(), alto_dia), int(Qt.AlignCenter), str(datos["dia"])
        )
        if operaciones:
            letra_pnl = fuente(13, True)
            alto_pnl = QFontMetrics(letra_pnl).height()
            oculto = bool(datos.get("oculto"))
            if not oculto and neto > 0:
                color = t.GREEN
            elif not oculto and neto < 0:
                color = t.RED
            else:
                color = t.MUTED
            caja_pnl = QRect(caja.left(), y + alto_dia + 2, caja.width(), alto_pnl)
            pintor.setFont(letra_pnl)
            pintor.setPen(QPen(QColor(color)))
            pintor.drawText(caja_pnl, int(Qt.AlignCenter), "••••" if oculto else t.fmt_pnl(neto))
        pintor.restore()

    def helpEvent(self, evento, vista, opcion, indice):
        texto = indice.data(Qt.ToolTipRole)
        if texto:
            # igual que el delegado de las tablas: sin el retardo de ~700 ms
            if not QToolTip.isVisible():
                QToolTip.showText(evento.globalPos(), texto, vista)
            return True
        return super().helpEvent(evento, vista, opcion, indice)


class CurvaMes(QWidget):
    """La curva acumulada del mes: una polilínea con el área debajo."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(28)
        self._puntos = []
        self._dias = 30
        self._color = t.MUTED

    def set_curva(self, puntos, dias_mes, color):
        """`puntos` son `[(día del mes, acumulado)]`."""
        self._puntos = [(int(dia), float(valor)) for dia, valor in puntos]
        self._dias = max(2, int(dias_mes))
        self._color = color
        self.update()

    def paintEvent(self, evento):
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.Antialiasing, True)
        caja = self.rect().adjusted(1, 4, -1, -4)
        if len(self._puntos) < 2:
            return
        valores = [valor for _dia, valor in self._puntos]
        minimo = min(min(valores), 0.0)
        maximo = max(max(valores), 0.0)
        if maximo - minimo < 1e-9:
            maximo = minimo + 1.0

        def lugar(dia, valor):
            x = caja.left() + (dia - 1) / (self._dias - 1) * caja.width()
            y = caja.bottom() - (valor - minimo) / (maximo - minimo) * caja.height()
            return QPoint(int(round(x)), int(round(y)))

        camino = [lugar(dia, valor) for dia, valor in self._puntos]
        cruza = minimo < 0 < maximo
        if cruza:
            cero = lugar(1, 0.0).y()
            pintor.setPen(QPen(QColor(t.LINE), 1))
            pintor.drawLine(caja.left(), cero, caja.right(), cero)
        base = lugar(1, 0.0).y() if cruza else caja.bottom()
        relleno = QPolygon(camino + [QPoint(camino[-1].x(), base), QPoint(camino[0].x(), base)])
        pintor.setPen(Qt.NoPen)
        pintor.setBrush(QColor(t.mezclar(self._color, t.CARD, 0.16)))
        pintor.drawPolygon(relleno)
        pintor.setPen(QPen(QColor(self._color), 2))
        pintor.drawPolyline(camino)
        pintor.setBrush(QColor(self._color))
        pintor.drawEllipse(camino[-1], 3, 3)
        pintor.end()
