"""Editor de una orden abierta: lado, apalancamiento, margen, precio y TP/SL."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLineEdit, QWidget

from .. import theme as t
from ..forms import valores_orden
from ..mexc import margen_inicial, num_texto
from .dialogos_base import Modal
from .style import Segmentado, boton, etiqueta, fnt


class EditorOrden(Modal):
    """Editor de una orden abierta: lado, apalancamiento, margen, precio y TP/SL.

    Guardar no modifica: MEXC no lo permite. El controlador cancela la orden y
    reenvía una nueva (por eso el aviso en amarillo).
    """

    def __init__(self, parent, orden, contrato, a_vol):
        super().__init__(parent, "Modificar orden", 420)
        self.orden = orden
        self.contrato = contrato or {}
        self.a_vol = a_vol
        self.resultado = None
        self.scale = int(orden.get("_priceScale") or 2)

        self.columna.addWidget(
            etiqueta(orden.get("_name") or orden.get("symbol", ""), 12, muted=True)
        )
        aviso = etiqueta(
            "Se cancela esta orden y se envía una nueva con estos datos.\n"
            "Si el precio se movió, la nueva puede quedar sin llenar.",
            11,
            color=t.GOLD,
        )
        aviso.setWordWrap(True)
        self.columna.addWidget(aviso)

        self.columna.addWidget(etiqueta("Dirección", 10, muted=True))
        self.lado = Segmentado(
            ("LONG", "SHORT"),
            "LONG" if int(orden.get("side") or 1) in (1, 4) else "SHORT",
        )
        self.columna.addWidget(self.lado)

        caja = QWidget()
        cuadricula = QGridLayout(caja)
        cuadricula.setContentsMargins(0, 6, 0, 0)
        cuadricula.setColumnStretch(1, 1)
        self.campos = {}
        filas = (
            ("lev", "Apalancamiento", str(int(orden.get("leverage") or 10)), "x"),
            ("margen", "Margen", f"{margen_inicial(orden):.2f}", "USDT"),
            (
                "precio",
                "Precio límite",
                t.fmt_price_exact(orden.get("price"), self.scale).replace(",", ""),
                "",
            ),
            ("tp", "TP", num_texto(orden.get("takeProfitPrice")), ""),
            ("sl", "SL", num_texto(orden.get("stopLossPrice")), ""),
        )
        for i, (clave, nombre, valor, sufijo) in enumerate(filas):
            linea = QLineEdit(valor)
            linea.setFont(fnt(13))
            linea.setFixedHeight(30)
            linea.setAlignment(Qt.AlignRight)
            linea.textChanged.connect(self._calc)
            self.campos[clave] = linea
            cuadricula.addWidget(etiqueta(nombre, 11, muted=True), i, 0)
            cuadricula.addWidget(linea, i, 1)
            if sufijo:
                cuadricula.addWidget(etiqueta(sufijo, 11, muted=True), i, 2)
        self.columna.addWidget(caja)

        self.lbl_calc = etiqueta("", 11, muted=True)
        self.columna.addWidget(self.lbl_calc)
        self.lbl_error = etiqueta("", 11, color=t.RED)
        self.lbl_error.setWordWrap(True)
        self.columna.addWidget(self.lbl_error)

        fila = QHBoxLayout()
        no = boton("Cancelar", 100, 34, t.INPUT, t.TEXT, t.R_CTRL, 12)
        no.clicked.connect(self.reject)
        fila.addWidget(no)
        fila.addStretch(1)
        si = boton("Guardar y reenviar", 160, 34, t.GREEN, t.ON_GREEN, t.R_CTRL, 12)
        si.clicked.connect(self._guardar)
        fila.addWidget(si)
        self.columna.addLayout(fila)
        self._calc()

    def leer(self):
        return {clave: linea.text().strip() for clave, linea in self.campos.items()}

    def _valores(self):
        """(lev, margen, precio, tp, sl) o None si algo no es número."""
        return valores_orden(
            self.campos["lev"].text(),
            self.campos["margen"].text(),
            self.campos["precio"].text(),
            self.campos["tp"].text(),
            self.campos["sl"].text(),
        )

    def _calc(self, *_):
        valores = self._valores()
        if not valores:
            self.lbl_calc.setText("—")
            return
        lev, margen, precio, _tp, _sl = valores
        nocional = margen * lev
        try:
            vol = self.a_vol(nocional, precio)
        except Exception:
            vol = 0
        self.lbl_calc.setText(
            f"≈ {t.fmt_qty(vol)} contratos · {t.fmt_usdt(nocional)} USDT nocional"
        )

    def _guardar(self):
        valores = self._valores()
        if not valores:
            self.lbl_error.setText("Revisa los números: apalancamiento, margen y precio > 0.")
            return
        lev, margen, precio, tp, sl = valores
        nocional = margen * lev
        try:
            vol = self.a_vol(nocional, precio)
        except Exception as exc:
            self.lbl_error.setText(str(exc)[:120])
            return
        if vol < 1:
            minimo = float(self.contrato.get("minVol") or 1) * float(
                self.contrato.get("contractSize") or 0
            )
            self.lbl_error.setText(
                f"Ese margen deja 0 contratos: sube el margen (mínimo ≈ "
                f"{t.fmt_usdt(minimo * precio)} USDT con {lev}x)."
            )
            return
        self.resultado = {
            "side": self.lado.elegida,
            "lev": lev,
            "margin": margen,
            "notional": nocional,
            "price": precio,
            "tp": tp or None,
            "sl": sl or None,
            "vol": vol,
            "scale": self.scale,
        }
        self.accept()

    def keyPressEvent(self, evento):
        if evento.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._guardar()
            return
        super().keyPressEvent(evento)


def editar_orden(parent, orden, contrato, a_vol):
    """Abre el editor y devuelve el formulario elegido, o None."""
    dialogo = EditorOrden(parent, orden, contrato, a_vol)
    dialogo.exec()
    return dialogo.resultado
