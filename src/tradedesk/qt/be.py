"""Ventana de "Poner a BE": una fila por posición y "Todos"."""

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import theme as t
from .dialogos_base import Modal
from .style import boton, etiqueta, logo


class _ListaBe(Modal):
    """Selección de posiciones para poner a BE (las que no se pueden, apagadas)."""

    def __init__(self, parent, filas):
        super().__init__(parent, "Poner a BE", 620)
        self.filas = filas
        self.resultado = None
        self.cajas = {}
        self.setStyleSheet(
            f"QDialog {{ background: {t.CARD}; border: 1px solid {t.BORDER}; }}"
            f"QCheckBox {{ color: {t.TEXT}; background: transparent; }}"
            f"QCheckBox:disabled {{ color: {t.MUTED}; }}"
            f"QLabel {{ background: transparent; }}"
        )
        aviso = etiqueta(
            "Elige las posiciones que quieres mover al break-even. "
            "Las que todavía no llegan aparecen apagadas.",
            10,
            muted=True,
        )
        aviso.setWordWrap(True)
        self.columna.addWidget(aviso)

        self.todos = QCheckBox("Todos")
        self.todos.clicked.connect(self._marcar_todos)
        self.lbl_cuenta = etiqueta("", 10, muted=True)
        cabecera = QHBoxLayout()
        cabecera.addWidget(self.todos)
        cabecera.addStretch(1)
        cabecera.addWidget(self.lbl_cuenta)
        self.columna.addLayout(cabecera)

        for fila in filas:
            caja = QWidget()
            caja.setStyleSheet(
                f"QWidget {{ background: {t.INPUT if fila['puede'] else t.SURFACE};"
                f" border-radius: {t.R_CTRL}px; }}"
            )
            columna = QVBoxLayout(caja)
            columna.setContentsMargins(10, 6, 10, 6)
            columna.setSpacing(1)
            linea = QHBoxLayout()
            linea.setSpacing(8)
            caja_sel = QCheckBox()
            caja_sel.setEnabled(fila["puede"])
            caja_sel.clicked.connect(self._actualizar)
            self.cajas[fila["id"]] = caja_sel
            linea.addWidget(caja_sel)
            marca = QLabel()
            marca.setPixmap(logo(fila["broker"], 14))
            marca.setStyleSheet("background: transparent;")
            linea.addWidget(marca)
            color = t.TEXT if fila["puede"] else t.MUTED
            linea.addWidget(etiqueta(fila["nombre"], 12, True, color))
            lado = "LONG" if fila["lado"] == "LONG" else "SHORT"
            linea.addWidget(etiqueta(lado, 11, True, t.GREEN if lado == "LONG" else t.RED))
            linea.addStretch(1)
            linea.addWidget(etiqueta(t.fmt_pnl(fila["pnl"]) + " USDT", 11, True, color))
            columna.addLayout(linea)
            detalle = (
                f"entrada {t.fmt_price_exact(fila['entrada'], fila['escala'])} · "
                f"precio {t.fmt_price_exact(fila['precio'], fila['escala'])} · "
                f"BE {t.fmt_price_exact(fila['be'], fila['escala'])}"
            )
            if not fila["puede"]:
                detalle += f" · {fila['motivo']}"
            suelto = etiqueta(detalle, 10, muted=True)
            suelto.setContentsMargins(28, 0, 0, 0)
            columna.addWidget(suelto)
            self.columna.addWidget(caja)

        pie = QHBoxLayout()
        pie.addStretch(1)
        self.btn_ok = boton("Poner a BE", 140, 32, t.GREEN, t.ON_GREEN, t.R_CTRL, 12)
        self.btn_ok.clicked.connect(self._aceptar_lista)
        pie.addWidget(self.btn_ok)
        no = boton("Cancelar", 110, 32, t.INPUT, t.TEXT, t.R_CTRL, 12)
        no.clicked.connect(self.reject)
        pie.addWidget(no)
        self.columna.addLayout(pie)
        self._actualizar()

    def _marcar_todos(self):
        marcar = self.todos.isChecked()
        for fila in self.filas:
            if fila["puede"]:
                self.cajas[fila["id"]].setChecked(marcar)
        self._actualizar()

    def _elegidas(self):
        return [
            fila["id"]
            for fila in self.filas
            if fila["puede"] and self.cajas[fila["id"]].isChecked()
        ]

    def _actualizar(self):
        elegidas = self._elegidas()
        posibles = sum(1 for fila in self.filas if fila["puede"])
        self.lbl_cuenta.setText(f"{len(elegidas)} de {posibles} seleccionadas")
        self.btn_ok.setText(f"Poner a BE ({len(elegidas)})" if elegidas else "Poner a BE")
        self.btn_ok.setEnabled(bool(elegidas))
        self.todos.blockSignals(True)
        self.todos.setChecked(bool(posibles) and len(elegidas) == posibles)
        self.todos.blockSignals(False)

    def _aceptar_lista(self):
        self.resultado = self._elegidas()
        self.accept()


def be_lista(parent, filas):
    """Ventana del BE: una fila por posicion y "Todos". Devuelve los ids."""
    dialogo = _ListaBe(parent, filas)
    dialogo.exec()
    return dialogo.resultado
