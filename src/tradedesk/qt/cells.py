"""Piezas de celda para las tablas Qt: celdas de varias lineas y el lapiz.

La tabla no crea un widget por celda (eso es lo que hacia lenta la version Tk):
cada celda guarda sus lineas como datos y el delegado las dibuja de una pasada.
"""

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from .. import theme as t

_FUENTES = {}


def fuente(size, bold=False):
    clave = (size, bold)
    if clave not in _FUENTES:
        letra = QFont(t.NUM)
        letra.setPixelSize(int(size))
        letra.setWeight(QFont.DemiBold if bold else QFont.Normal)
        _FUENTES[clave] = letra
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
        y = opcion.rect.top() + max(0, (opcion.rect.height() - sum(alturas)) // 2)
        derecha = bool((indice.data(Qt.TextAlignmentRole) or 0) & int(Qt.AlignRight))
        for (texto, size, negrita, color), alto in zip(partes, alturas, strict=True):
            letra = fuente(size, negrita)
            painter.setFont(letra)
            painter.setPen(QPen(QColor(color)))
            caja = QRect(opcion.rect.left() + 6, y, opcion.rect.width() - 12, alto)
            bandera = (Qt.AlignRight if derecha else Qt.AlignLeft) | Qt.AlignVCenter
            painter.drawText(caja, int(bandera), str(texto))
            y += alto
        painter.restore()


def icono_lapiz(color, tamano=14):
    """El lapiz de la fila, dibujado como en Tk (cuerpo, banda y punta)."""
    pixmap = QPixmap(tamano, tamano)
    pixmap.fill(Qt.transparent)
    pintor = QPainter(pixmap)
    pintor.setRenderHint(QPainter.Antialiasing, True)
    pintor.setPen(QPen(QColor(color), 1.4))
    pintor.drawLine(3, tamano - 4, tamano - 4, 3)
    pintor.drawLine(tamano - 4, 3, tamano - 2, 5)
    pintor.drawLine(3, tamano - 4, 1, tamano - 1)
    pintor.end()
    return pixmap
