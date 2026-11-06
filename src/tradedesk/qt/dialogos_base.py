"""Diálogos base: ventana sin marco, confirmación, aviso, formulario y claves.

Todo lo demás (`tpsl`, `editor_orden`, `be`, `panel_brokers`) se arma con estas
piezas. Nada de `QMessageBox`: el estilo sale de `qt/style.py`.
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
from .style import boton, etiqueta, fnt, qss


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

    def __init__(
        self,
        parent,
        titulo,
        campos,
        nota=None,
        ok="Guardar",
        extras=(),
        resumen=None,
        traducir=None,
    ):
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
            # el resumen puede traer color por linea (TP verde / SL rojo)
            self.lbl_resumen.setTextFormat(Qt.RichText)
            self.columna.addWidget(self.lbl_resumen)
            for linea in self.campos.values():
                linea.textChanged.connect(self._refrescar)

        # campos que escriben en otro campo: el "%" de PnL calcula el precio
        for origen, (destino, calcular) in (traducir or {}).items():
            if origen in self.campos and destino in self.campos:
                self.campos[origen].textChanged.connect(
                    lambda texto, d=destino, f=calcular: self._traducir(texto, d, f)
                )

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

    def _traducir(self, texto, destino, calcular):
        try:
            valor = calcular(texto)
        except (TypeError, ValueError):
            return
        if not valor:
            return
        campo = self.campos[destino]
        campo.blockSignals(True)
        campo.setText(valor)
        campo.blockSignals(False)
        self._refrescar()

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


def form(parent, titulo, campos, nota=None, ok="Guardar", traducir=None):
    """`dialog.form` de la app Tk: dict de textos, o None si se cancela."""
    dialogo = _Formulario(parent, titulo, campos, nota=nota, ok=ok, traducir=traducir)
    dialogo.exec()
    return dialogo.resultado


class _Puente(QObject):
    """Entrega el resultado de `verify` (que corre en un hilo) al hilo de la UI."""

    hecho = Signal(bool, str)


class _Claves(Modal):
    def __init__(self, parent, verify, broker="MEXC"):
        super().__init__(parent, f"Conectar {broker}", 440)
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


def ask_key(parent, verify, broker="MEXC"):
    """Devuelve (key, secret) ya verificados, o None."""
    dialogo = _Claves(parent, verify, broker)
    dialogo.exec()
    return dialogo.resultado
