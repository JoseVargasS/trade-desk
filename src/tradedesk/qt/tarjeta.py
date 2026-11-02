"""Tarjeta de par y barra de cierre de la fila (Qt)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLineEdit, QMenu, QVBoxLayout, QWidget

from .. import theme as t
from ..forms import form_tarjeta
from . import dialogs
from .style import Segmentado
from .style import boton as _boton
from .style import etiqueta as _etiqueta

PRESETS = (1, 5, 10, 15, 20, 50)


class BarraCierre(QWidget):
    """Los cuatro controles de la fila: Mercado · % · Cerrar · Reverse."""

    def __init__(self, position, pnl, largo, al_cerrar, al_reverse):
        super().__init__()
        self.position = position
        self.al_cerrar = al_cerrar
        self.al_reverse = al_reverse
        self.pct = 100
        self.precio = 0.0
        self.setFixedSize(190, 52)
        fila1 = QHBoxLayout()
        fila1.setSpacing(4)
        fila2 = QHBoxLayout()
        fila2.setSpacing(4)
        color = t.GREEN if pnl > 0 else (t.RED if pnl < 0 else t.INPUT)
        texto_color = t.BG if pnl else t.TEXT
        self.btn_tipo = _boton("Mercado ▾", 106, 22)
        self.btn_tipo.clicked.connect(self._menu_tipo)
        fila1.addWidget(self.btn_tipo)
        self.btn_pct = _boton("100% ▾", 78, 22)
        self.btn_pct.clicked.connect(self._pedir_pct)
        fila1.addWidget(self.btn_pct)
        cerrar = _boton(f"Cerrar {'LONG' if largo else 'SHORT'}", 102, 26, color, texto_color)
        cerrar.clicked.connect(self._cerrar)
        fila2.addWidget(cerrar)
        reverse = _boton("Reverse", 82, 26)
        reverse.clicked.connect(lambda: self.al_reverse(self.position))
        fila2.addWidget(reverse)
        columna = QVBoxLayout(self)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(4)
        columna.addLayout(fila1)
        columna.addLayout(fila2)

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
            self.btn_tipo.setText("Mercado ▾")
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
                self.btn_tipo.setText(f"{precio:,.2f} ▾")

    def _pedir_pct(self):
        res = dialogs.form(
            self.window(),
            "Cerrar una parte",
            [("pct", "Porcentaje", "100")],
            nota="Se redondea al contrato entero; 100% cierra todo.",
        )
        if res is None:
            return
        try:
            pct = float(res["pct"].replace(",", ""))
        except ValueError:
            return
        if 0 < pct <= 100:
            self.pct = pct
            self.btn_pct.setText(f"{pct:.0f}% ▾")

    def _cerrar(self):
        self.al_cerrar(self.position, {"pct": self.pct, "price": self.precio or None})


class Tarjeta(QFrame):
    """Una tarjeta de par: apalancamiento, tamaño, TP/SL y el resumen vivo."""

    def __init__(self, tarjeta, mx, on_trade=None, on_remove=None):
        super().__init__()
        self.tarjeta = tarjeta
        self.mx = mx
        self.on_trade = on_trade or (lambda _c, _s: None)
        self.on_remove = on_remove or (lambda _s: None)
        self.limite = 0.0
        self.setObjectName("card")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedSize(286, 436)

        columna = QVBoxLayout(self)
        columna.setContentsMargins(12, 12, 12, 12)
        columna.setSpacing(6)
        cabecera = QHBoxLayout()
        cabecera.addWidget(_etiqueta(tarjeta["nombre"], 15, True))
        cabecera.addStretch(1)
        quitar = _boton("✕", 22, 22, "transparent", t.MUTED, t.R_CHIP, 11, False)
        quitar.clicked.connect(lambda: self.on_remove(self.tarjeta["symbol"]))
        cabecera.addWidget(quitar)
        columna.addLayout(cabecera)
        self.lbl_precio = _etiqueta("—", 24, True)
        columna.addWidget(self.lbl_precio)
        columna.addWidget(_etiqueta(f"{tarjeta['leverage']}X · LONG", 12, True, color=t.GREEN))

        columna.addWidget(_etiqueta("Apalancamiento", 11, muted=True))
        fila_palanca = QHBoxLayout()
        fila_palanca.setSpacing(3)
        self.in_palanca = QLineEdit(tarjeta["leverage"])
        self.in_palanca.setFixedWidth(44)
        self.in_palanca.setAlignment(Qt.AlignRight)
        fila_palanca.addWidget(self.in_palanca)
        fila_palanca.addWidget(_etiqueta("x", 11, muted=True))
        for valor in PRESETS:
            preset = _boton(str(valor), 30, 20, size=10)
            preset.clicked.connect(lambda _=False, v=valor: self._poner_palanca(v))
            fila_palanca.addWidget(preset)
        columna.addLayout(fila_palanca)

        fila_modos = QHBoxLayout()
        fila_modos.setSpacing(4)
        self.seg_margen = Segmentado(("Aislado", "Cruzado"), tarjeta["margin"], self._cambio_margen)
        self.seg_modo = Segmentado(("Margen", "Nocional"), tarjeta["size_mode"], self._cambio_modo)
        fila_modos.addWidget(self.seg_margen)
        fila_modos.addWidget(self.seg_modo)
        columna.addLayout(fila_modos)

        columna.addWidget(_etiqueta("Tamaño (USDT)", 11, muted=True))
        fila_tamano = QHBoxLayout()
        fila_tamano.setSpacing(4)
        self.in_tamano = QLineEdit("")
        self.in_tamano.setAlignment(Qt.AlignRight)
        fila_tamano.addWidget(self.in_tamano, 1)
        self.chip_limite = _boton("Mercado ▾", 84, 26)
        self.chip_limite.clicked.connect(self._menu_limite)
        fila_tamano.addWidget(self.chip_limite)
        columna.addLayout(fila_tamano)

        columna.addWidget(_etiqueta("TP / SL", 11, muted=True))
        fila_stops = QHBoxLayout()
        fila_stops.setSpacing(4)
        self.in_tp = QLineEdit("")
        self.in_sl = QLineEdit("")
        for entrada in (self.in_tp, self.in_sl):
            entrada.setAlignment(Qt.AlignRight)
            fila_stops.addWidget(entrada)
        columna.addLayout(fila_stops)

        self.lbl_resumen = _etiqueta("—", 11, muted=True)
        self.lbl_resumen.setWordWrap(True)
        columna.addWidget(self.lbl_resumen)
        columna.addStretch(1)

        fila_botones = QHBoxLayout()
        fila_botones.setSpacing(8)
        self.btn_long = _boton("LONG", None, 38, t.GREEN, t.BG, t.R_CTRL, 14)
        self.btn_short = _boton("SHORT", None, 38, t.RED, t.BG, t.R_CTRL, 14)
        self.btn_long.clicked.connect(lambda: self.on_trade(self, "LONG"))
        self.btn_short.clicked.connect(lambda: self.on_trade(self, "SHORT"))
        fila_botones.addWidget(self.btn_long)
        fila_botones.addWidget(self.btn_short)
        columna.addLayout(fila_botones)

        for entrada in (self.in_palanca, self.in_tamano, self.in_tp, self.in_sl):
            entrada.textChanged.connect(self._actualizar)
        self._actualizar()

    def _cambio_margen(self, valor):
        self.tarjeta["margin"] = valor

    def _cambio_modo(self, valor):
        self.tarjeta["size_mode"] = valor
        self._actualizar()

    def _poner_palanca(self, valor):
        self.in_palanca.setText(str(valor))

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
        self.btn_long.setEnabled(not activo)
        self.btn_short.setEnabled(not activo)

    def set_precio(self, precio):
        """Precio nuevo del ticker: se actualiza sin pedir nada a la red."""
        self.tarjeta["precio"] = float(precio or 0)
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
            self.chip_limite.setText("Mercado ▾")
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
                    self.chip_limite.setText(f"{precio:,.2f} ▾")
        self.chip_limite.adjustSize()
        self._actualizar()

    def _actualizar(self):
        self.lbl_precio.setText(f"{float(self.tarjeta['precio'] or 0):,.2f}")
        if self.mx is None:
            return
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
            self.lbl_resumen.setText("—")
            return
        contrato = self.tarjeta["contrato"] or {}
        vol = self.mx.size_to_vol(self.tarjeta["symbol"], nocional, precio, contract=contrato)
        real = self.mx.vol_to_usdt(self.tarjeta["symbol"], vol, precio)
        fee = self.mx.est_fee(self.tarjeta["symbol"], real)
        liq_l = self.mx.est_liq(self.tarjeta["symbol"], precio, palanca, "LONG")
        liq_s = self.mx.est_liq(self.tarjeta["symbol"], precio, palanca, "SHORT")
        self.lbl_resumen.setText(
            f"{vol:.0f} contratos · {real:,.2f} USDT\n"
            f"fee {fee:.4f} · liq {liq_l:,.2f} / {liq_s:,.2f}"
        )
