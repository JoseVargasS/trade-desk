"""Estado y pollers sin UI: la base que comparten la app de Tk y la vista Qt.

Solo **lee** de MEXC (tickers, posiciones y órdenes) y publica mensajes en una cola:
`("cards", ...)`, `("ticker", symbol, precio)`, `("positions", ...)`, `("orders", ...)`,
`("error", texto)`. No envía órdenes, no abre diálogos y no toca widgets: eso queda en
cada UI. Los previews de las tarjetas se calculan en la UI con las funciones puras de
`mexc` (`size_to_vol`, `vol_to_usdt`, `est_fee`, `est_liq`).

La app de Tkinter todavía tiene su propio poller en `app.py`; este módulo es el que usa
la vista Qt y el que queda cuando se retire la vista Tk (F6).
"""

import json
import queue
import threading
import time

from . import creds, paths
from .mexc import Mexc, decorate_orders, decorate_positions, display_name

TICKER_SEG = 0.70  # una peticion cada 0.7 s en total (~1.4 req/s, el limite medido)
POSICIONES_SEG = 3.0


class Session:
    def __init__(self, mx=None):
        self.mx = mx or Mexc(*creds.load("mexc"))
        self.q = queue.Queue()
        self.tarjetas = self._tarjetas()
        self.precios = {}
        self.mercados = {}
        self.ultimas_posiciones = []
        self.ultimas_ordenes = []
        self._parar = threading.Event()
        self._hilos = []

    # ------------------------------------------------------------- consultas
    def contract_for(self, symbol):
        """Contrato del par: catálogo o cache. Sin red."""
        return self.mercados.get(symbol) or self.mx.cached_contract(symbol) or {}

    def log(self, msg):
        from datetime import datetime

        try:
            with open(str(paths.DATA_DIR / "trades.log"), "a", encoding="utf-8") as f:
                f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")
        except Exception:
            pass

    def refresh_positions(self):
        try:
            self.q.put(("positions", decorate_positions(self.mx, self.mx.positions())))
        except Exception as exc:
            self.q.put(("status", f"posiciones: {exc}"))

    def refresh_orders(self):
        try:
            self.q.put(("orders", decorate_orders(self.mx, self.mx.open_orders())))
        except Exception as exc:
            self.q.put(("status", f"ordenes: {exc}"))

    # ------------------------------------------------------------------ config
    @staticmethod
    def _leer_config():
        try:
            return json.loads((paths.DATA_DIR / "config.json").read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _tarjetas(self):
        tarjetas = []
        for tarjeta in self._leer_config().get("cards") or []:
            if tarjeta.get("symbol"):
                tarjetas.append(
                    {
                        "symbol": tarjeta["symbol"],
                        "leverage": str(tarjeta.get("leverage") or "10"),
                        "margin": str(tarjeta.get("margin") or "Aislado"),
                        "size_mode": str(tarjeta.get("size_mode") or "Margen"),
                    }
                )
        return tarjetas

    # ------------------------------------------------------------------- ciclo
    def start(self):
        for objetivo in (self._cargar_tarjetas, self._cargar_catalogo, self._poll):
            hilo = threading.Thread(target=objetivo, daemon=True)
            hilo.start()
            self._hilos.append(hilo)
        return self

    def stop(self):
        self._parar.set()

    # ------------------------------------------------------------------ hilos
    def _cargar_tarjetas(self):
        """Contrato y primer precio de cada tarjeta: esto si pide red, va en su hilo."""
        lista = []
        for tarjeta in self.tarjetas:
            contrato = {}
            try:
                contrato = self.mx.contract(tarjeta["symbol"]) or {}
            except Exception as exc:
                self.q.put(("error", f"contrato {tarjeta['symbol']}: {exc}"))
            precio = 0.0
            try:
                precio = float(self.mx.price(tarjeta["symbol"]) or 0)
            except Exception as exc:
                self.q.put(("error", f"precio {tarjeta['symbol']}: {exc}"))
            if precio:
                self.precios[tarjeta["symbol"]] = precio
            lista.append(
                {
                    **tarjeta,
                    "precio": precio,
                    "contrato": contrato,
                    "nombre": display_name(contrato)
                    if contrato
                    else tarjeta["symbol"].replace("_", ""),
                }
            )
        self.q.put(("cards", lista))

    def _cargar_catalogo(self):
        """Catálogo completo (1.171 pares) para el buscador y `contract_for`."""
        try:
            self.mercados = self.mx.markets()
            self.q.put(("markets", self.mercados))
        except Exception as exc:
            self.q.put(("error", f"catalogo: {exc}"))

    def _poll(self):
        indice = 0
        proximo = 0.0
        while not self._parar.is_set():
            if self.tarjetas:
                symbol = self.tarjetas[indice % len(self.tarjetas)]["symbol"]
                indice += 1
                try:
                    precio = float(self.mx.price(symbol) or 0)
                    if precio:
                        self.precios[symbol] = precio
                        self.q.put(("ticker", symbol, precio))
                except Exception as exc:
                    self.q.put(("error", f"ticker {symbol}: {exc}"))
            ahora = time.monotonic()
            if ahora >= proximo:
                proximo = ahora + POSICIONES_SEG
                try:
                    posiciones = decorate_positions(self.mx, self.mx.positions())
                    self.ultimas_posiciones = posiciones
                    self.q.put(("positions", posiciones))
                except Exception as exc:
                    self.q.put(("error", f"posiciones: {exc}"))
                try:
                    ordenes = decorate_orders(self.mx, self.mx.open_orders())
                    self.ultimas_ordenes = ordenes
                    self.q.put(("orders", ordenes))
                except Exception as exc:
                    self.q.put(("error", f"órdenes: {exc}"))
            time.sleep(TICKER_SEG)
