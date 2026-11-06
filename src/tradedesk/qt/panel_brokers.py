"""Panel de brokers: logo, estado de las claves y botón para cargarlas."""

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from .. import theme as t
from .dialogos_base import Modal
from .style import boton, etiqueta, logo


class PanelBrokers(Modal):
    """Brokers disponibles: logo, estado de las claves y botón para cargarlas."""

    def __init__(self, parent, filas, al_claves):
        super().__init__(parent, "Brokers", 430)
        self.al_claves = al_claves
        aviso = etiqueta(
            "Las claves se guardan en el Windows Credential Manager, nunca en config.json.",
            10,
            muted=True,
        )
        aviso.setWordWrap(True)
        self.columna.addWidget(aviso)
        for nombre, titulo, conectado, saldo in filas:
            caja = QWidget()
            caja.setStyleSheet(f"QWidget {{ background: {t.INPUT}; border-radius: {t.R_CTRL}px; }}")
            fila = QHBoxLayout(caja)
            fila.setContentsMargins(10, 8, 10, 8)
            fila.setSpacing(10)
            marca = QLabel()
            marca.setPixmap(logo(nombre, 22))
            marca.setStyleSheet("background: transparent;")
            fila.addWidget(marca)
            fila.addWidget(etiqueta(titulo, 13, True))
            fila.addStretch(1)
            estado = "Conectado" if conectado else "Sin claves"
            if conectado:
                estado += f" · {t.fmt_usdt(saldo)} USDT"
            fila.addWidget(etiqueta(estado, 11, color=t.GREEN if conectado else t.MUTED))
            accion = boton(
                "Cambiar" if conectado else "Agregar", 92, 28, t.SURFACE, t.TEXT, t.R_CHIP, 11
            )
            accion.clicked.connect(lambda _=False, n=nombre: self._claves(n))
            fila.addWidget(accion)
            self.columna.addWidget(caja)
        cerrar = boton("Cerrar", 110, 32, t.INPUT, t.TEXT, t.R_CTRL, 12)
        cerrar.clicked.connect(self.accept)
        pie = QHBoxLayout()
        pie.addStretch(1)
        pie.addWidget(cerrar)
        self.columna.addLayout(pie)

    def _claves(self, nombre):
        self.accept()
        self.al_claves(nombre)


def brokers(parent, filas, al_claves):
    """Abre el panel de brokers; `filas` = [(logo, titulo, conectado), ...]."""
    panel = PanelBrokers(parent, filas, al_claves)
    panel.exec()
