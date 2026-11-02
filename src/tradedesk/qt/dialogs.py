"""Ventanas de la vista Qt: confirmar, avisar, formularios, editor y TP/SL.

Sin marco, borde de 1 px, `Esc` cancela y `Enter` acepta. Nada de `QMessageBox`
(queda gris): el estilo sale de `qt/style.py`.
"""

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from .. import theme as t
from ..forms import valores_orden
from ..mexc import break_even_price, margen_inicial, num_texto, pnl_en_precio
from .style import Segmentado, boton, etiqueta, fnt, qss


class Modal(QDialog):
    """Ventana modal sin marco, centrada sobre el padre."""

    def __init__(self, parent, titulo, ancho=0):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self.setStyleSheet(
            qss() + f"QDialog {{ background: {t.CARD}; border: 1px solid {t.LINE}; }}"
        )
        self.columna = QVBoxLayout(self)
        self.columna.setContentsMargins(18, 14, 18, 16)
        self.columna.setSpacing(8)
        self.columna.addLayout(self._cabecera(titulo))
        if ancho:
            self.setFixedWidth(ancho)

    def _cabecera(self, texto):
        fila = QHBoxLayout()
        fila.addWidget(etiqueta(texto, 15, True))
        fila.addStretch(1)
        cerrar = boton("✕", 22, 22, fondo="transparent", borde=False, size=11)
        cerrar.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {t.MUTED}; border: 0px; }}"
            f"QPushButton:hover {{ color: {t.TEXT}; }}"
        )
        cerrar.clicked.connect(self.reject)
        fila.addWidget(cerrar)
        return fila

    def keyPressEvent(self, evento):
        if evento.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(evento)

    def showEvent(self, evento):
        super().showEvent(evento)
        self.adjustSize()
        padre = self.parentWidget()
        if padre is not None:
            centro = padre.window().frameGeometry().center()
            marco = self.frameGeometry()
            marco.moveCenter(centro)
            self.move(marco.topLeft())

    def _botones(self, aceptar="Guardar", color=None, letra=None, cancelar="Cancelar"):
        fila = QHBoxLayout()
        fila.addStretch(1)
        si = boton(aceptar, 130, 34, color or t.GREEN, letra or t.ON_GREEN, t.R_CTRL, 12)
        si.clicked.connect(self.accept)
        fila.addWidget(si)
        no = boton(cancelar, 110, 34, t.INPUT, t.TEXT, t.R_CTRL, 12)
        no.clicked.connect(self.reject)
        fila.addWidget(no)
        self.columna.addLayout(fila)
        return si, no


class _Dialogo(Modal):
    """Confirmacion o aviso: filas etiqueta/valor y una advertencia opcional."""

    def __init__(
        self,
        parent,
        titulo,
        filas=(),
        mensaje=None,
        aviso=None,
        ok="Confirmar",
        cancelar="Cancelar",
        danger=False,
    ):
        super().__init__(parent, titulo, 420)
        self.confirmado = False
        if mensaje:
            texto = etiqueta(mensaje, 12, muted=True)
            texto.setWordWrap(True)
            self.columna.addWidget(texto)
        if filas:
            caja = QWidget()
            cuadricula = QGridLayout(caja)
            cuadricula.setContentsMargins(0, 4, 0, 4)
            for i, (nombre, valor) in enumerate(filas):
                cuadricula.addWidget(etiqueta(nombre, 12, muted=True), i, 0, Qt.AlignLeft)
                cuadricula.addWidget(etiqueta(str(valor), 13), i, 1, Qt.AlignRight)
            self.columna.addWidget(caja)
        if aviso:
            linea = etiqueta(aviso, 12, True, color=t.RED if danger else t.GOLD)
            linea.setWordWrap(True)
            self.columna.addWidget(linea)
        si, _ = self._botones(
            ok,
            t.RED if danger else t.GREEN,
            t.ON_RED if danger else t.ON_GREEN,
            cancelar,
        )
        si.clicked.disconnect()
        si.clicked.connect(self._aceptar)

    def _aceptar(self):
        self.confirmado = True
        self.accept()

    def keyPressEvent(self, evento):
        if evento.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._aceptar()
            return
        super().keyPressEvent(evento)


def confirm(
    parent,
    titulo,
    filas=(),
    warn=None,
    ok_text="Confirmar",
    cancel_text="Cancelar",
    danger=False,
):
    """`dialog.confirm` de la app Tk: devuelve True si el usuario acepta."""
    dialogo = _Dialogo(
        parent,
        titulo,
        filas,
        aviso=warn,
        ok=ok_text,
        cancelar=cancel_text,
        danger=danger,
    )
    dialogo.exec()
    return dialogo.confirmado


def show(parent, titulo, mensaje, aviso=None, danger=False):
    """Aviso con un solo boton: Enter y Esc lo cierran."""
    dialogo = _Dialogo(
        parent, titulo, mensaje=mensaje, aviso=aviso, ok="Aceptar", cancelar="Cerrar", danger=danger
    )
    dialogo.exec()


class _Formulario(Modal):
    """N campos etiquetados; `valores()` devuelve un dict de texto."""

    def __init__(self, parent, titulo, campos, nota=None, ok="Guardar", extras=(), resumen=None):
        super().__init__(parent, titulo, 400)
        if nota:
            aviso = etiqueta(nota, 10, muted=True)
            aviso.setWordWrap(True)
            self.columna.addWidget(aviso)

        caja = QWidget()
        cuadricula = QGridLayout(caja)
        cuadricula.setContentsMargins(0, 4, 0, 0)
        cuadricula.setColumnStretch(1, 1)
        self.campos = {}
        for i, campo in enumerate(campos):
            clave, nombre, valor = campo[:3]
            tipo = campo[3] if len(campo) > 3 else "precio"
            linea = QLineEdit(str(valor or ""))
            linea.setFont(fnt(13))
            linea.setFixedHeight(32)
            linea.setAlignment(Qt.AlignRight if tipo == "precio" else Qt.AlignLeft)
            linea.returnPressed.connect(self._aceptar)
            self.campos[clave] = linea
            cuadricula.addWidget(etiqueta(nombre, 11, muted=True), i, 0)
            cuadricula.addWidget(linea, i, 1)
        self.columna.addWidget(caja)

        self.lbl_resumen = None
        if resumen:
            self.lbl_resumen = etiqueta(resumen(self.leer()), 10, muted=True)
            self.columna.addWidget(self.lbl_resumen)
            for linea in self.campos.values():
                linea.textChanged.connect(self._refrescar)

        fila = QHBoxLayout()
        for texto, comando, activo in extras:
            extra = boton(texto, 110, 34, t.INPUT, t.TEXT, t.R_CTRL, 11)
            extra.setEnabled(activo)
            extra.clicked.connect(lambda _=False, que=comando: que(self))
            fila.addWidget(extra)
        fila.addStretch(1)
        self.btn_ok = boton(ok, 130, 34, t.GREEN, t.ON_GREEN, t.R_CTRL, 12)
        self.btn_ok.clicked.connect(self._aceptar)
        fila.addWidget(self.btn_ok)
        no = boton("Cancelar", 110, 34, t.INPUT, t.TEXT, t.R_CTRL, 12)
        no.clicked.connect(self.reject)
        fila.addWidget(no)
        self.columna.addLayout(fila)
        self.resultado = None
        self._resumen = resumen

    def leer(self):
        return {clave: linea.text().strip() for clave, linea in self.campos.items()}

    def escribir(self, clave, texto):
        self.campos[clave].setText(texto)

    def _refrescar(self, *_):
        if self.lbl_resumen is not None:
            self.lbl_resumen.setText(self._resumen(self.leer()))

    def _aceptar(self):
        self.resultado = self.leer()
        self.accept()

    def keyPressEvent(self, evento):
        if evento.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._aceptar()
            return
        super().keyPressEvent(evento)


def form(parent, titulo, campos, nota=None, ok="Guardar"):
    """`dialog.form` de la app Tk: dict de textos, o None si se cancela."""
    dialogo = _Formulario(parent, titulo, campos, nota=nota, ok=ok)
    dialogo.exec()
    return dialogo.resultado


class _Puente(QObject):
    """Entrega el resultado de `verify` (que corre en un hilo) al hilo de la UI."""

    hecho = Signal(bool, str)


class _Claves(Modal):
    def __init__(self, parent, verify):
        super().__init__(parent, "Conectar MEXC", 440)
        self.resultado = None
        self.verify = verify

        self.e_key = QLineEdit()
        self.e_key.setPlaceholderText("API key")
        self.e_key.setFixedHeight(34)
        self.e_secret = QLineEdit()
        self.e_secret.setPlaceholderText("Secret")
        self.e_secret.setEchoMode(QLineEdit.Password)
        self.e_secret.setFixedHeight(34)
        self.columna.addWidget(self.e_key)
        self.columna.addWidget(self.e_secret)
        self.columna.addWidget(
            etiqueta("Se guardan en el Administrador de credenciales de Windows.", 11, muted=True)
        )
        self.lbl = etiqueta("", 11, color=t.GOLD)
        self.lbl.setWordWrap(True)
        self.columna.addWidget(self.lbl)
        self.btn = boton("Guardar y verificar", None, 36, t.GREEN, t.ON_GREEN, t.R_CTRL, 13)
        self.btn.clicked.connect(self._guardar)
        self.columna.addWidget(self.btn)
        self._puente = _Puente(self)
        self._puente.hecho.connect(self._verificado)
        self.e_key.setFocus()

    def _guardar(self):
        clave, secreto = self.e_key.text().strip(), self.e_secret.text().strip()
        if not clave or not secreto:
            self.lbl.setText("Faltan datos.")
            return
        self.btn.setEnabled(False)
        self.lbl.setText("Verificando…")

        def correr():
            # la red nunca va en el hilo de la UI
            try:
                self.verify(clave, secreto)
            except Exception as exc:
                self._puente.hecho.emit(False, str(exc))
                return
            self._puente.hecho.emit(True, "")

        threading.Thread(target=correr, daemon=True).start()

    def _verificado(self, bien, error):
        if not bien:
            self.btn.setEnabled(True)
            self.lbl.setText(f"No funciono: {error}")
            return
        self.resultado = (self.e_key.text().strip(), self.e_secret.text().strip())
        self.accept()


def ask_key(parent, verify):
    """Devuelve (key, secret) ya verificados, o None."""
    dialogo = _Claves(parent, verify)
    dialogo.exec()
    return dialogo.resultado


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


class QtPort:
    """`UiPort` de la vista Qt: los diálogos de este módulo."""

    def __init__(self, ventana):
        self.ventana = ventana

    def confirm(
        self,
        titulo,
        rows=(),
        warn=None,
        danger=False,
        ok="Confirmar",
        cancel="Cancelar",
    ):
        return confirm(
            self.ventana,
            titulo,
            rows,
            warn=warn,
            danger=danger,
            ok_text=ok,
            cancel_text=cancel,
        )

    def show(self, titulo, mensaje, aviso=None, danger=False):
        show(self.ventana, titulo, mensaje, aviso=aviso, danger=danger)

    def form(self, titulo, campos, nota=None, ok="Guardar"):
        return form(self.ventana, titulo, campos, nota=nota, ok=ok)

    def status(self, texto):
        self.ventana.statusBar().showMessage(texto)

    def tpsl(self, pos, precio):
        return editar_tpsl(self.ventana, pos, int(pos.get("positionType") or 1) == 1, precio)

    def editar_orden(self, orden, contrato, a_vol):
        return editar_orden(self.ventana, orden, contrato, a_vol)


def _lineas_pnl(pos, long_, tp, sl):
    """Lo que se gana o pierde si el TP/SL se ejecuta, en USDT."""
    lineas = []
    for etiqueta_pnl, texto in (("TP", tp), ("SL", sl)):
        try:
            precio = float((texto or "").replace(",", "").strip())
        except ValueError:
            continue
        lineas.append(
            f"{etiqueta_pnl} {t.fmt_price(precio)} → "
            f"{t.fmt_pnl(pnl_en_precio(pos, long_, precio))} USDT"
        )
    return "\n".join(lineas) or "Escribe un precio para ver la ganancia o perdida."


def editar_tpsl(parent, pos, long_, precio):
    """Lápiz de TP/SL: devuelve {'tp': texto, 'sl': texto} o None.

    Es el diálogo del lápiz de TP/SL: mismos campos, la línea viva con el PnL y
    el botón *Break-even* con `mexc.break_even_price`.
    """
    escala = int(pos.get("_priceScale") or 2)
    be, cubre = break_even_price(pos, long_)
    cabe = bool(precio and be and (precio > be if long_ else precio < be))
    texto_be = f"{be:.{escala}f}" if be else ""

    lado = ("SL debajo" if long_ else "SL arriba") if precio else "SL en contra"
    if be:
        nota = (
            f"Qty {t.fmt_qty(pos.get('holdVol'))} contratos · "
            f"precio actual {t.fmt_price(precio) if precio else '—'} ({lado})\n"
            f"Break-even {t.fmt_price_exact(be, escala)} → {t.fmt_pnl(cubre)} USDT "
            "(comision de entrada + salida + funding · neto 0)"
        )
        if not cabe:
            nota += (
                f"\nNecesita precio {'>' if long_ else '<'} "
                f"{t.fmt_price_exact(be, escala)} (ahora {t.fmt_price(precio)})"
            )
    else:
        nota = "Break-even no disponible: falta precio de entrada o tamaño"

    dialogo = _Formulario(
        parent,
        f"TP / SL · {pos.get('symbol')}",
        [
            ("tp", "Take profit", pos.get("_tp") or ""),
            ("sl", "Stop loss", pos.get("_sl") or ""),
        ],
        nota=nota,
        extras=(("Break-even", lambda dlg: dlg.escribir("sl", texto_be), cabe),),
        resumen=lambda valores: _lineas_pnl(pos, long_, valores["tp"], valores["sl"]),
    )
    dialogo.exec()
    return dialogo.resultado
