"""Piezas de celda para las tablas Qt: celdas de varias lineas, lapiz y tooltip.

La tabla no crea un widget por celda (eso es lo que hacia lenta la version Tk):
cada celda guarda sus lineas como datos y el delegado las dibuja de una pasada.
La celda marcada con `SUBRAYADO` lleva linea punteada bajo el importe y muestra
su `ToolTipRole` al pasar el puntero (el detalle de la fee).
"""

from PySide6.QtCore import QPoint, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QToolTip, QWidget

from .. import theme as t
from .style import fnt

SUBRAYADO = Qt.UserRole + 1
DETALLE = Qt.UserRole + 2  # filas (nombre, valor, color) del globo de la fee
_FUENTES = {}


class Spinner(QWidget):
    """Ruedita de carga: un arco girando, sin gifs ni dependencias."""

    def __init__(self, lado=14, color=None, parent=None):
        super().__init__(parent)
        self.lado = lado
        self._angulo = 0
        self._color = color or t.GOLD
        self.setFixedSize(lado, lado)
        self._timer = QTimer(self)
        self._timer.setInterval(70)
        self._timer.timeout.connect(self._girar)
        self.hide()

    def _girar(self):
        self._angulo = (self._angulo + 30) % 360
        self.update()

    def empezar(self):
        self.show()
        if not self._timer.isActive():
            self._timer.start()

    def parar(self):
        self._timer.stop()
        self.hide()

    def paintEvent(self, evento):
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.Antialiasing)
        pluma = QPen(self._color, 2)
        pluma.setCapStyle(Qt.RoundCap)
        pintor.setPen(pluma)
        margen = 2
        lado = self.lado - margen * 2
        pintor.drawArc(margen, margen, lado, lado, self._angulo * 16, 270 * 16)
        pintor.end()


def fuente(size, bold=False):
    """Misma fuente que los widgets (Geist + respaldo), cacheada por tamaño."""
    clave = (size, bold)
    if clave not in _FUENTES:
        _FUENTES[clave] = fnt(size, bold)
    return _FUENTES[clave]


def lineas(*partes):
    """Empaqueta las lineas de una celda: `(texto, size, bold, color)`."""
    return tuple(partes)


class DelegadoCeldas(QStyledItemDelegate):
    """Dibuja 1-3 lineas por celda, alineadas y con color, sin widgets."""

    def paint(self, painter: QPainter, opcion, indice):
        partes = indice.data(Qt.UserRole)
        if not partes:
            super().paint(painter, opcion, indice)
            return
        painter.save()
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        fondo = t.ROW_ALT if indice.row() % 2 else t.CARD
        if opcion.state & QStyle.State_Selected:
            fondo = t.SURFACE
        painter.fillRect(opcion.rect, QColor(fondo))

        alturas = [QFontMetrics(fuente(parte[1], parte[2])).height() for parte in partes]
        arriba = opcion.rect.top() + max(0, (opcion.rect.height() - sum(alturas)) // 2)
        y = arriba
        derecha = bool((indice.data(Qt.TextAlignmentRole) or 0) & int(Qt.AlignRight))
        for (texto, size, negrita, color), alto in zip(partes, alturas, strict=True):
            letra = fuente(size, negrita)
            painter.setFont(letra)
            painter.setPen(QPen(QColor(color)))
            caja = QRect(opcion.rect.left() + 6, y, opcion.rect.width() - 12, alto)
            bandera = (Qt.AlignRight if derecha else Qt.AlignLeft) | Qt.AlignVCenter
            painter.drawText(caja, int(bandera), str(texto))
            y += alto

        if indice.data(SUBRAYADO) is not None and partes:
            texto0, size0, negrita0, _color0 = partes[0]
            ancho = QFontMetrics(fuente(size0, negrita0)).horizontalAdvance(str(texto0))
            borde = opcion.rect.right() - 6
            linea_y = arriba + alturas[0] - 2
            pluma = QPen(QColor(t.MUTED), 1)
            pluma.setStyle(Qt.DotLine)
            painter.setPen(pluma)
            painter.drawLine(borde - ancho, linea_y, borde, linea_y)
        painter.restore()

    def helpEvent(self, evento, vista, opcion, indice):
        texto = indice.data(Qt.ToolTipRole)
        if texto:
            # la vista ya lo muestra al entrar en la celda; aca solo se evita que
            # Qt lo repita 700 ms despues (el retardo del tooltip del sistema)
            if not QToolTip.isVisible():
                QToolTip.showText(evento.globalPos(), texto, vista)
            return True
        return super().helpEvent(evento, vista, opcion, indice)


def icono_lapiz(color, tamano=16):
    """Lapiz de la fila: cuerpo, punta y banda, dibujado como en MEXC."""
    pixmap = QPixmap(tamano, tamano)
    pixmap.fill(Qt.transparent)
    pintor = QPainter(pixmap)
    pintor.setRenderHint(QPainter.Antialiasing, True)
    pintor.translate(tamano / 2, tamano / 2)
    pintor.rotate(-45)
    largo = tamano * 0.80
    ancho = tamano * 0.34
    punta = largo * 0.30
    pluma = QPen(QColor(color), max(1.0, tamano / 14))
    pluma.setJoinStyle(Qt.RoundJoin)
    pintor.setPen(pluma)
    cuerpo = QPolygonF(
        [
            QPointF(-largo / 2, 0),
            QPointF(-largo / 2 + punta, -ancho / 2),
            QPointF(largo / 2, -ancho / 2),
            QPointF(largo / 2, ancho / 2),
            QPointF(-largo / 2 + punta, ancho / 2),
        ]
    )
    pintor.drawPolygon(cuerpo)
    banda = largo / 2 - ancho * 0.55
    pintor.drawLine(QPointF(banda, -ancho / 2), QPointF(banda, ancho / 2))
    pintor.end()
    return pixmap


class Bocadillo(QWidget):
    """Globo con punta para el detalle de la fee: sale arriba y apunta a la celda.

    Es una ventana sin marco: `QToolTip` no deja dibujar la punta ni elegir el
    lado, asi que el globo se pinta a mano (caja redondeada + triangulo abajo).
    """

    PUNTA = 9
    ANCHO = 220

    def __init__(self, parent=None):
        super().__init__(parent, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._titulo = ""
        self._filas = []
        self.setFixedWidth(self.ANCHO)

    def mostrar(self, ancla: QPoint, titulo, filas):
        """`ancla` es el punto global del borde superior de la celda, centrado."""
        self._titulo = titulo
        self._filas = list(filas)
        alto = 26 + 18 * len(self._filas) + 8 + self.PUNTA
        self.setFixedHeight(alto)
        x = ancla.x() - self.width() // 2
        y = ancla.y() - alto - 4
        pantalla = self.screen().availableGeometry() if self.screen() else None
        if pantalla is not None:
            x = min(max(pantalla.left() + 4, x), pantalla.right() - self.width() - 4)
            y = max(pantalla.top() + 4, y)
        self.move(x, y)
        self.show()
        self.raise_()

    def paintEvent(self, _evento):
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.Antialiasing, True)
        caja = QRect(0, 0, self.width(), self.height() - self.PUNTA)
        centro = self.width() // 2
        pintor.setPen(QPen(QColor(t.BORDER), 1))
        pintor.setBrush(QColor(t.CARD))
        cola = QPolygonF(
            [
                QPointF(centro - 7, caja.bottom() - 1),
                QPointF(centro, caja.bottom() + self.PUNTA),
                QPointF(centro + 7, caja.bottom() - 1),
            ]
        )
        pintor.drawPolygon(cola)
        pintor.drawRoundedRect(caja, 8, 8)

        pintor.setFont(fnt(11, True))
        pintor.setPen(QColor(t.MUTED))
        pintor.drawText(QRect(10, 7, caja.width() - 20, 16), Qt.AlignLeft, self._titulo)
        y = 26
        for nombre, valor, color in self._filas:
            pintor.setFont(fnt(11))
            pintor.setPen(QColor(t.MUTED))
            pintor.drawText(QRect(10, y, 140, 16), Qt.AlignLeft, nombre)
            pintor.setFont(fnt(11, True))
            pintor.setPen(QColor(color))
            pintor.drawText(QRect(0, y, caja.width() - 10, 16), Qt.AlignRight, valor)
            y += 18
        pintor.end()
