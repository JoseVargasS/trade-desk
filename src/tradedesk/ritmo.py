"""Cerrar varias posiciones en paralelo sin pasarse del límite de cada broker."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor


class Ritmo:
    """Deja arrancar como máximo `por_segundo` peticiones por segundo.

    Serializa solo el arranque de cada envío, no la espera de la respuesta: los
    cierres siguen solapados, pero el broker nunca ve más de los que aguanta.
    """

    def __init__(self, por_segundo):
        self.hueco = 1.0 / float(por_segundo)
        self._candado = threading.Lock()
        self._ultimo = 0.0

    def esperar(self):
        with self._candado:
            falta = self._ultimo + self.hueco - time.monotonic()
            if falta > 0:
                time.sleep(falta)
            self._ultimo = time.monotonic()


def en_paralelo(funcion, items, maximo):
    """Aplica `funcion` a cada item con hasta `maximo` a la vez."""
    with ThreadPoolExecutor(max_workers=max(1, maximo)) as pool:
        return list(pool.map(funcion, items))


# Ordenes por segundo que soporta cada broker (ver docs/API_BROKERS.md):
# MEXC order/create 4 cada 2 s, Bitunix flash_close 5/s, sin datos de BingX.
RITMO_ORDEN = {"mexc": 2, "bitunix": 4, "bingx": 2}
