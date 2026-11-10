"""Mixin: enviar todas las tarjetas de un tirón, con una sola confirmación.

Vive aparte de `ventana.py` porque ese archivo ya está en el tope de líneas; el
mixin usa el estado de la ventana, igual que las tablas y el calendario.
"""

from ..controller_lote import resumen_lote
from . import dialogs


class LoteDeck:
    def _cartas_lote(self):
        return [c for c in self._cartas if c.lado_lote()]

    def _actualizar_boton_lote(self):
        total = len(self._cartas_lote()) if self._lienzo is not None else 0
        self.btn_lote.setText(f"ENVIAR TODAS ({total})")
        self.btn_lote.setEnabled(total > 0 and not self._lote_en_curso)

    def _enviar_todas(self):
        if self._lote_en_curso:
            return
        cartas = self._cartas_lote()
        if not cartas:
            self._notificar("Lote", "Elige LONG o SHORT en al menos una tarjeta.")
            return
        items = []
        elegidas = []
        invalidas = []
        omitidas = []
        for tarjeta in cartas:
            form = tarjeta.form()
            if not form:
                invalidas.append(tarjeta.tarjeta["symbol"])
                continue
            exchange = tarjeta.broker()
            if not exchange or self.session.cliente(exchange) is None:
                omitidas.append(f"{tarjeta.tarjeta['symbol']} (sin cliente)")
                continue
            if self._estado_mercado(exchange, tarjeta.tarjeta["symbol"]) is False:
                omitidas.append(f"{tarjeta.tarjeta['symbol']} (no disponible)")
                continue
            elegidas.append(tarjeta)
            items.append({"side": tarjeta.lado_lote(), "form": form, "exchange": exchange})
        if invalidas:
            dialogs.show(
                self,
                "Datos invalidos",
                "Revisa " + ", ".join(invalidas) + ": apalancamiento y tamaño deben "
                "ser numeros positivos, y TP/SL vacios o numericos.",
            )
            return
        if not items:
            self._notificar("Lote", "Ninguna tarjeta quedo disponible para enviar.")
            return
        self._lote_cartas = elegidas

        def enviar():
            self._lote_en_curso = True
            for carta in self._lote_cartas:
                carta.set_busy(True)
            self._actualizar_boton_lote()

        self.control.abrir_lote(items, al_enviar=enviar, omitidos=omitidas)

    def _lote_terminado(self, datos):
        """Un solo aviso para todo el lote; nunca un modal por orden."""
        self._lote_en_curso = False
        resultados = datos.get("resultados") or []
        for indice, carta in enumerate(self._lote_cartas):
            carta.set_busy(False)
            estado = resultados[indice][2] if indice < len(resultados) else ""
            if estado in ("ok", "desconocida"):
                carta.limpiar_lado_lote()
        self._lote_cartas = []
        self._actualizar_boton_lote()
        titulo, mensaje, problema = resumen_lote(resultados, datos.get("dry", False))
        dialogs.show(self, titulo, mensaje, danger=problema)
