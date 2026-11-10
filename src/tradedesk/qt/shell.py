"""Ventana de prueba en Qt: cabecera, 8 tarjetas, pestañas y una tabla de 200 filas.

Es solo para medir el repintado: no habla con MEXC.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import theme as t
from ..layout import TARJETA_H, TARJETA_W
from .style import fnt, qss

COLUMNAS = (
    ("Par", 140),
    ("Lado", 90),
    ("Apertura", 110),
    ("Posición", 130),
    ("Entrada", 110),
    ("Mark price", 110),
    ("Liquidación", 110),
    ("Margin ratio", 110),
    ("Margen", 130),
    ("PnL", 130),
    ("Fee · %mrg / pos", 150),
    ("TP / SL", 190),
)

BOTONES = ("Mercado", "100%", "Cerrar LONG", "Reverse")


def _etiqueta(texto, size=13, bold=False, muted=False):
    etiqueta = QLabel(texto)
    etiqueta.setFont(fnt(size, bold))
    if muted:
        etiqueta.setProperty("muted", "true")
    return etiqueta


def _tarjeta(nombre, precio, pnl):
    caja = QFrame()
    caja.setObjectName("card")
    caja.setAttribute(Qt.WA_StyledBackground, True)
    caja.setFixedSize(TARJETA_W, TARJETA_H)
    columna = QVBoxLayout(caja)
    columna.setContentsMargins(12, 12, 12, 12)
    columna.setSpacing(6)
    columna.addWidget(_etiqueta(nombre, 15, True))
    precio_label = _etiqueta(f"{precio:,.2f}", 24, True)
    precio_label.setStyleSheet(f"color: {t.RED if pnl < 0 else t.GREEN};")
    columna.addWidget(precio_label)
    columna.addWidget(_etiqueta("10X LONG", 12, True))
    columna.addWidget(_etiqueta("Apalancamiento", 11))
    columna.addWidget(QLineEdit("10"))
    columna.addWidget(_etiqueta("Tamaño (USDT)", 11))
    columna.addWidget(QLineEdit("500"))
    columna.addWidget(_etiqueta("TP / SL", 11))
    fila = QHBoxLayout()
    fila.addWidget(QLineEdit("2500"))
    fila.addWidget(QLineEdit("1500"))
    columna.addLayout(fila)
    columna.addWidget(_etiqueta("5 contratos · 100.00 USDT", 11, muted=True))
    columna.addWidget(_etiqueta("fee 0.0800 · liq 1,800 / 2,200", 11, muted=True))
    columna.addStretch(1)
    acciones = QHBoxLayout()
    for texto in BOTONES:
        acciones.addWidget(QPushButton(texto))
    columna.addLayout(acciones)
    return caja


def _tabla(filas=200):
    tabla = QTableWidget(filas, len(COLUMNAS))
    tabla.setHorizontalHeaderLabels([nombre for nombre, _ancho in COLUMNAS])
    tabla.verticalHeader().setVisible(False)
    tabla.verticalHeader().setDefaultSectionSize(56)
    tabla.setAlternatingRowColors(True)
    tabla.setShowGrid(False)
    for indice, (_nombre, ancho) in enumerate(COLUMNAS):
        tabla.setColumnWidth(indice, ancho)
    for fila in range(filas):
        for columna, (nombre, _ancho) in enumerate(COLUMNAS):
            if nombre == "Par":
                texto = "GOLD(XAU)USDT"
            elif nombre == "Lado":
                texto = "10X LONG"
            elif nombre == "PnL":
                texto = f"{-12.3 - fila * 0.1:+,.4f} USDT"
            elif nombre == "Fee · %mrg / pos":
                texto = "1.4833 USDT"
            else:
                texto = f"{3900.75 + fila * 0.25:,.2f}"
            tabla.setItem(fila, columna, QTableWidgetItem(texto))
    return tabla


def build_window():
    ventana = QMainWindow()
    ventana.setWindowTitle("Trade Desk · prueba Qt")
    ventana.resize(1800, 1000)

    central = QWidget()
    central.setObjectName("central")
    raiz = QVBoxLayout(central)
    raiz.setContentsMargins(16, 16, 16, 8)
    raiz.setSpacing(8)

    cabecera = QFrame()
    cabecera.setObjectName("surface")
    cabecera.setAttribute(Qt.WA_StyledBackground, True)
    fila_cabecera = QHBoxLayout(cabecera)
    fila_cabecera.setContentsMargins(12, 8, 12, 8)
    fila_cabecera.addWidget(_etiqueta("TRADE DESK", 14, True))
    fila_cabecera.addStretch(1)
    fila_cabecera.addWidget(_etiqueta("DRY-RUN", 11, True))
    raiz.addWidget(cabecera)

    deck = QScrollArea()
    deck.setWidgetResizable(True)
    deck.setFrameShape(QFrame.NoFrame)
    deck.setFixedHeight(TARJETA_H + 34)
    contenido = QWidget()
    fila_tarjetas = QHBoxLayout(contenido)
    fila_tarjetas.setContentsMargins(0, 0, 0, 0)
    fila_tarjetas.setSpacing(10)
    for indice in range(8):
        fila_tarjetas.addWidget(_tarjeta(f"PAR {indice + 1}USDT", 3900.75 + indice, -12.3))
    fila_tarjetas.addStretch(1)
    deck.setWidget(contenido)
    raiz.addWidget(deck)

    pestanas = QTabWidget()
    pestanas.addTab(_tabla(200), "Posiciones")
    pestanas.addTab(QWidget(), "Órdenes")
    pestanas.addTab(QWidget(), "Historial")
    raiz.addWidget(pestanas, 1)

    ventana.setCentralWidget(central)
    ventana.statusBar().showMessage("conectado · 10 ms")
    ventana.setStyleSheet(qss())
    return ventana
