"""Buscador de pares de la vista Qt: escribe, Enter toma el primero, Esc cierra."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit, QListWidget, QListWidgetItem

from .. import theme as t
from ..pairs import contract_line, filter_markets
from .dialogs import Modal
from .style import fnt


class BuscarPar(Modal):
    """Devuelve el `symbol` elegido en `.resultado`, o None."""

    def __init__(self, parent, mercados, titulo="Buscar par"):
        super().__init__(parent, titulo, 440)
        self.setFixedHeight(430)
        self.mercados = mercados or {}
        self.resultado = None
        self._items = []

        self.entrada = QLineEdit()
        self.entrada.setPlaceholderText("BTC, sol, eth…")
        self.entrada.setFixedHeight(34)
        self.entrada.setFont(fnt(14))
        self.entrada.textChanged.connect(self._filtrar)
        self.entrada.returnPressed.connect(self._primero)
        self.columna.addWidget(self.entrada)

        self.lista = QListWidget()
        self.lista.setFont(fnt(12))
        self.lista.setStyleSheet(
            f"QListWidget {{ background: {t.INPUT}; border: 0px; }}"
            f"QListWidget::item {{ padding: 5px 6px; }}"
            f"QListWidget::item:selected {{ background: {t.SELECT}; color: {t.TEXT}; }}"
        )
        self.lista.itemClicked.connect(self._clic)
        self.columna.addWidget(self.lista, 1)

        self._filtrar("")
        self.entrada.setFocus()

    def keyPressEvent(self, evento):
        if evento.key() == Qt.Key_Down:
            self._mover(1)
            return
        if evento.key() == Qt.Key_Up:
            self._mover(-1)
            return
        super().keyPressEvent(evento)

    def _filtrar(self, texto):
        self._items = filter_markets(self.mercados, texto, limit=200)
        self.lista.clear()
        if not self.mercados:
            self.lista.addItem(QListWidgetItem("  cargando catalogo…"))
            return
        if not self._items:
            self.lista.addItem(QListWidgetItem("  sin resultados"))
            return
        for contrato in self._items:
            self.lista.addItem(QListWidgetItem(contract_line(contrato)))
        self.lista.setCurrentRow(0)

    def _mover(self, salto):
        if not self._items:
            return
        actual = max(0, min(self.lista.currentRow() + salto, len(self._items) - 1))
        self.lista.setCurrentRow(actual)

    def _primero(self):
        if self._items:
            self._elegir(0)

    def _clic(self, _item):
        self._elegir(self.lista.currentRow())

    def _elegir(self, indice):
        if not (0 <= indice < len(self._items)):
            return
        self.resultado = self._items[indice]["symbol"]
        self.accept()


def buscar(parent, mercados, titulo="Buscar par"):
    dialogo = BuscarPar(parent, mercados, titulo)
    dialogo.exec()
    return dialogo.resultado
