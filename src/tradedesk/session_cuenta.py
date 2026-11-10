"""Consultas de cuenta: posiciones y órdenes.

Vive aparte de `session.py` porque ese archivo ya está en el tope de líneas. Los
brokers se consultan **en paralelo**: cada uno tiene su propio límite y uno lento
no debe atrasar la tabla de los demás. Con `brokers` se refresca solo esos y las
filas de los demás se conservan (no cambiaron).
"""

from .bingx_comun import decorate_orders as decorate_orders_bingx
from .bingx_comun import decorate_positions as decorate_positions_bingx
from .bitunix import decorate_orders as decorate_orders_bitunix
from .bitunix import decorate_positions as decorate_positions_bitunix
from .mexc import decorate_orders, decorate_positions
from .ritmo import en_paralelo

BROKERS = ("mexc", "bitunix", "bingx")


def _pedidos(brokers):
    """Lista de brokers a consultar: None = todos, str = uno, lista = varios."""
    if brokers is None:
        return list(BROKERS)
    if isinstance(brokers, str):
        brokers = [brokers]
    return [nombre for nombre in brokers if nombre in BROKERS]


class CuentaMixin:
    # --------------------------------------------------------------- posiciones
    def refresh_positions(self, brokers=None):
        """Refresca posiciones. Con `brokers` solo esos; las de los demás se conservan."""
        try:
            nombres = _pedidos(brokers)
            if not nombres:
                filas = self.posiciones_todas()
            else:
                planos = en_paralelo(self._posiciones_de, nombres, len(nombres))
                otras = [
                    fila
                    for fila in self.ultimas_posiciones
                    if (fila.get("_exchange") or "mexc") not in nombres
                ]
                filas = otras + [fila for grupo in planos for fila in grupo]
            self.ultimas_posiciones = filas
            self.q.put(("positions", filas))
        except Exception as exc:
            self.q.put(("status", f"posiciones: {exc}"))

    def posiciones_todas(self, broker=None):
        """Posiciones de un broker (o de todos), ya adaptadas a la interfaz."""
        nombres = [broker] if broker in BROKERS else list(BROKERS)
        if len(nombres) == 1:
            return self._posiciones_de(nombres[0])
        planos = en_paralelo(self._posiciones_de, nombres, 3)
        return [fila for grupo in planos for fila in grupo]

    def _posiciones_de(self, broker):
        cliente = self.cliente(broker)
        if cliente is None:
            return []
        if broker == "mexc":
            try:
                posiciones = decorate_positions(
                    cliente,
                    cliente.positions(),
                    on_error=lambda recurso, exc: self._error_consulta(
                        f"{recurso} de posiciones", "mexc", exc
                    ),
                )
            except Exception as exc:
                self._error_consulta("posiciones", "mexc", exc)
                return []
            for pos in posiciones:
                pos["_exchange"] = "mexc"
            return posiciones
        if broker == "bitunix":
            try:
                stops = cliente.tpsl_list()
            except Exception as exc:
                self._error_consulta("TP/SL de posiciones", "bitunix", exc)
                stops = []
            try:
                return decorate_positions_bitunix(cliente, cliente.positions(), stops)
            except Exception as exc:
                self._error_consulta("posiciones", "bitunix", exc)
                return []
        try:
            condicionales = cliente.open_orders()
        except Exception as exc:
            self._error_consulta("TP/SL de posiciones", "bingx", exc)
            condicionales = []
        try:
            posiciones = cliente.positions()
            try:
                comisiones = cliente.comisiones() if posiciones else {}
            except Exception as exc:
                self._error_consulta("comisiones de posiciones", "bingx", exc)
                comisiones = {}
            return decorate_positions_bingx(cliente, posiciones, condicionales, comisiones)
        except Exception as exc:
            self._error_consulta("posiciones", "bingx", exc)
            return []

    # ------------------------------------------------------------------ órdenes
    def refresh_orders(self, brokers=None):
        """Refresca órdenes. Con `brokers` solo esos; las de los demás se conservan."""
        try:
            nombres = _pedidos(brokers)
            if not nombres:
                filas = self.ordenes_todas()
            else:
                planos = en_paralelo(self._ordenes_de, nombres, len(nombres))
                otras = [
                    fila
                    for fila in self.ultimas_ordenes
                    if (fila.get("_exchange") or "mexc") not in nombres
                ]
                filas = otras + [fila for grupo in planos for fila in grupo]
            self.ultimas_ordenes = filas
            self.q.put(("orders", filas))
        except Exception as exc:
            self.q.put(("status", f"ordenes: {exc}"))

    def ordenes_todas(self, broker=None):
        """Órdenes de un broker (o de todos), ya adaptadas a la interfaz."""
        nombres = [broker] if broker in BROKERS else list(BROKERS)
        if len(nombres) == 1:
            return self._ordenes_de(nombres[0])
        planos = en_paralelo(self._ordenes_de, nombres, 3)
        return [fila for grupo in planos for fila in grupo]

    def _ordenes_de(self, broker):
        cliente = self.cliente(broker)
        if cliente is None:
            return []
        decorar = {
            "mexc": decorate_orders,
            "bitunix": decorate_orders_bitunix,
            "bingx": decorate_orders_bingx,
        }[broker]
        try:
            filas_broker = decorar(cliente, cliente.open_orders())
        except Exception as exc:
            self._error_consulta("ordenes", broker, exc)
            return []
        if broker == "mexc":
            for orden in filas_broker:
                orden["_exchange"] = broker
        return filas_broker
