"""Piezas de celda para las tablas Qt: celdas de varias lineas, lapiz y tooltip.

La tabla no crea un widget por celda (eso es lo que hacia lenta la version Tk):
cada celda guarda sus lineas como datos y el delegado las dibuja de una pasada.
La celda marcada con `SUBRAYADO` lleva linea punteada bajo el importe y muestra
su `ToolTipRole` al pasar el puntero (el detalle de la fee).
"""

from PySide6.QtCore import QPoint, QPointF, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QStyle,
    QStyledItemDelegate,
    QTableWidget,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from .. import theme as t
from .style import etiqueta, fnt, logo

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


def tabla(columnas, alto_fila):
    """Tabla con el delegado, los anchos y la alineación de cada columna."""
    rejilla = QTableWidget(0, len(columnas))
    rejilla.setHorizontalHeaderLabels([columna[1] for columna in columnas])
    rejilla.verticalHeader().setVisible(False)
    rejilla.verticalHeader().setDefaultSectionSize(alto_fila)
    rejilla.setShowGrid(False)
    rejilla.setAlternatingRowColors(False)
    rejilla.setEditTriggers(QAbstractItemView.NoEditTriggers)
    rejilla.setSelectionMode(QAbstractItemView.NoSelection)
    rejilla.setFocusPolicy(Qt.NoFocus)
    rejilla.setWordWrap(False)
    rejilla.setItemDelegate(DelegadoCeldas(rejilla))
    for indice, columna in enumerate(columnas):
        rejilla.setColumnWidth(indice, columna[2])
        encabezado = rejilla.horizontalHeaderItem(indice)
        if encabezado is not None:
            alineacion = Qt.AlignRight if columna[3] == "e" else Qt.AlignLeft
            encabezado.setTextAlignment(alineacion | Qt.AlignVCenter)
    return rejilla


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
            lbl = etiqueta("", size)
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._caja.addWidget(lbl)
            self._etiquetas.append(lbl)
        for indice, lbl in enumerate(self._etiquetas):
            if indice < len(partes):
                texto, size, negrita, color = partes[indice]
                lbl.setText(str(texto))
                lbl.setFont(fnt(size, negrita))
                lbl.setStyleSheet(f"color: {color}; background: transparent;")
                lbl.show()
            else:
                lbl.hide()

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
        self.lbl_nombre = etiqueta(nombre, 12 if compacta else 13, True)
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
