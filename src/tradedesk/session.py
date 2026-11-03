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

import httpx

from . import creds, paths
from .archivo import Archivo
from .bitunix import Bitunix, con_guion
from .bitunix import decorate_orders as decorate_orders_bitunix
from .bitunix import decorate_positions as decorate_positions_bitunix
from .mexc import Mexc, decorate_orders, decorate_positions, display_name
from .operaciones import operaciones

TICKER_SEG = 0.70  # una peticion cada 0.7 s en total (~1.4 req/s, el limite medido)
POSICIONES_SEG = 3.0
HISTORIAL_SEG = 15.0
SALDOS_SEG = 15.0
HISTORIAL_PAGINA = 50
FONDOS_SEG = 60.0


class Session:
    def __init__(self, mx=None, bitunix=None):
        self.mx = mx or Mexc(*creds.load("mexc"))
        # segundo broker: por ahora solo lectura (F1); se rutea por tarjeta en F3
        self.bitunix = bitunix or Bitunix(*creds.load("bitunix"))
        # qué brokers tienen claves: se lee una vez, no en cada vuelta del poller
        self.hay = {
            "mexc": bool(getattr(self.mx, "api_key", "")),
            "bitunix": bool(self.bitunix.key),
        }
        self.q = queue.Queue()
        self.tarjetas = self._tarjetas()
        self.precios = {}
        self.mercados = {}
        self.ultimas_posiciones = []
        self.ultimas_ordenes = []
        self.saldos = {"mexc": 0.0, "bitunix": 0.0}
        self.fondos = {}
        self._hist_ordenes = {}
        self._hist_pagina = 0
        self.historial_hay_mas = {"mexc": True, "bitunix": True}
        # archivo local: el broker borra su historial, esto queda
        self.archivo = Archivo(paths.DATA_DIR / "operaciones.json")
        self.ver_historial = False
        self._parar = threading.Event()
        self._hilos = []
        # el historial guardado se pinta al instante, sin esperar a la red
        if self.archivo.filas:
            self.q.put(("history", self.archivo.todas()))

    # --------------------------------------------------------------- tarjetas
    def cliente(self, exchange):
        """Cliente del broker pedido, o None si todavía no tiene claves."""
        if exchange == "bitunix":
            return self.bitunix if self.hay.get("bitunix") else None
        if exchange == "mexc":
            return self.mx if self.hay.get("mexc") else None
        return None

    def set_exchange(self, tarjeta_id, exchange):
        """Fija el broker de una tarjeta y lo guarda.

        No republica las tarjetas: eso reconstruiría los widgets y borraría lo
        que el usuario escribió (tamaño, TP/SL). El precio lo trae el poller.
        """
        for tarjeta in self.tarjetas:
            if tarjeta["id"] == tarjeta_id:
                tarjeta["exchange"] = exchange
        self._guardar_config()

    def add_card(self, symbol):
        # se permite el mismo par en los dos brokers: cada tarjeta lleva un id
        ident = symbol
        numero = 2
        while any(t["id"] == ident for t in self.tarjetas):
            ident = f"{symbol}#{numero}"
            numero += 1
        self.tarjetas.append(
            {
                "id": ident,
                "symbol": symbol,
                "exchange": "",
                "leverage": "10",
                "margin": "Aislado",
                "size_mode": "Margen",
            }
        )
        self._guardar_config()
        threading.Thread(target=self._publicar, daemon=True).start()
        return True

    def remove_card(self, tarjeta_id):
        self.tarjetas = [t for t in self.tarjetas if t["id"] != tarjeta_id]
        self.precios.pop(tarjeta_id, None)
        self._guardar_config()
        threading.Thread(target=self._publicar, daemon=True).start()

    def mover_tarjeta(self, tarjeta_id, indice):
        """Reordena las tarjetas (arrastrar y soltar) y lo guarda."""
        actual = next((i for i, t in enumerate(self.tarjetas) if t["id"] == tarjeta_id), None)
        if actual is None:
            return
        tarjeta = self.tarjetas.pop(actual)
        indice = max(0, min(int(indice), len(self.tarjetas)))
        self.tarjetas.insert(indice, tarjeta)
        self._guardar_config()

    def _guardar_config(self):
        try:
            (paths.DATA_DIR / "config.json").write_text(
                json.dumps({"cards": self.tarjetas}, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def _publicar(self):
        """Contrato y precio de cada tarjeta, con el broker que eligió."""
        lista = []
        for tarjeta in self.tarjetas:
            exchange = tarjeta.get("exchange") or ""
            cliente = self.cliente(exchange)
            contrato = {}
            precio = float(self.precios.get(tarjeta["id"]) or 0)
            if cliente is not None:
                try:
                    if exchange == "bitunix":
                        contrato = cliente.contract(tarjeta["symbol"]) or {}
                    else:
                        contrato = self.contract_for(tarjeta["symbol"]) or cliente.contract(
                            tarjeta["symbol"]
                        )
                except Exception as exc:
                    self.q.put(("error", f"contrato {tarjeta['symbol']}: {exc}"))
                if not precio:
                    try:
                        precio = float(cliente.price(tarjeta["symbol"]) or 0)
                    except Exception as exc:
                        self.q.put(("error", f"precio {tarjeta['symbol']}: {exc}"))
                if precio:
                    self.precios[tarjeta["id"]] = precio
            if contrato and exchange == "mexc":
                nombre = display_name(contrato)
            else:
                nombre = tarjeta["symbol"].replace("_", "")
            lista.append(
                {
                    **tarjeta,
                    "precio": precio,
                    "contrato": contrato,
                    "nombre": nombre,
                }
            )
        self.q.put(("cards", lista))

    def cargar_historial(self, mas=False):
        """Historial de los dos brokers, agrupado en operaciones (una fila por posición).

        La página 1 se refresca sola cada 15 s y se **fusiona** con lo ya traído; con
        `mas=True` (botón `Ver más`) se pide la página siguiente de cada broker. Las
        órdenes se guardan por `(broker, orderId)`, así un refresco no borra lo viejo
        ni duplica filas.
        """
        self._hist_pagina = self._hist_pagina + 1 if mas else 1
        pagina = self._hist_pagina
        for nombre, traer in (
            (
                "mexc",
                lambda: decorate_orders(self.mx, self.mx.history(HISTORIAL_PAGINA, pagina)),
            ),
            (
                "bitunix",
                lambda: self.bitunix.history(HISTORIAL_PAGINA, (pagina - 1) * HISTORIAL_PAGINA),
            ),
        ):
            cliente = self.cliente(nombre)
            if cliente is None:
                continue
            try:
                filas = traer()
            except Exception as exc:
                self.q.put(("error", f"historial {nombre}: {exc}"))
                continue
            for orden in filas:
                orden["_exchange"] = nombre
                clave = (nombre, str(orden.get("orderId") or ""))
                if clave in self._hist_ordenes:
                    continue
                self._hist_ordenes[clave] = orden
            if len(filas) < HISTORIAL_PAGINA:
                self.historial_hay_mas[nombre] = False
        self.q.put(
            ("history", self.archivo.fusionar(operaciones(list(self._hist_ordenes.values()))))
        )
        self.q.put(("history_mas", any(self.historial_hay_mas.values())))

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
            self.q.put(("positions", self.posiciones_todas()))
        except Exception as exc:
            self.q.put(("status", f"posiciones: {exc}"))

    def posiciones_todas(self):
        """Posiciones de todos los brokers conectados, ya adaptadas a la interfaz."""
        filas = []
        if self.cliente("mexc"):
            for pos in decorate_positions(self.mx, self.mx.positions()):
                pos["_exchange"] = "mexc"
                filas.append(pos)
        if self.cliente("bitunix"):
            try:
                stops = self.bitunix.tpsl_list()
            except Exception:
                stops = []
            filas.extend(decorate_positions_bitunix(self.bitunix, self.bitunix.positions(), stops))
        return filas

    def refresh_orders(self):
        try:
            self.q.put(("orders", self.ordenes_todas()))
        except Exception as exc:
            self.q.put(("status", f"ordenes: {exc}"))

    def ordenes_todas(self):
        filas = []
        if self.cliente("mexc"):
            for orden in decorate_orders(self.mx, self.mx.open_orders()):
                orden["_exchange"] = "mexc"
                filas.append(orden)
        if self.cliente("bitunix"):
            filas.extend(decorate_orders_bitunix(self.bitunix, self.bitunix.open_orders()))
        return filas

    def refresh_saldos(self):
        """USDT disponible en cada broker conectado (lo que se puede usar)."""
        saldos = dict(self.saldos)
        for nombre, cliente in (
            ("mexc", self.cliente("mexc")),
            ("bitunix", self.cliente("bitunix")),
        ):
            if cliente is None:
                continue
            try:
                saldos[nombre] = float(cliente.available())
            except Exception as exc:
                self.q.put(("error", f"saldo {nombre}: {exc}"))
        self.saldos = saldos
        self.q.put(("balances", dict(saldos)))

    def refresh_fondos(self):
        """Tasa y hora del próximo funding de los pares en pantalla (cambia lento)."""
        pares = {(t.get("exchange") or "", t["symbol"]) for t in self.tarjetas if t.get("exchange")}
        for pos in self.ultimas_posiciones:
            pares.add((pos.get("_exchange") or "", pos.get("symbol") or ""))
        for exchange, symbol in pares:
            cliente = self.cliente(exchange)
            if cliente is None or not symbol:
                continue
            try:
                datos = cliente.funding(symbol)
            except Exception as exc:
                self.q.put(("error", f"funding {symbol}: {exc}"))
                continue
            if datos:
                self.fondos[(exchange, symbol)] = datos
        if self.fondos:
            self.q.put(("funding", dict(self.fondos)))

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
                        # las tarjetas viejas no tenían broker: eran de MEXC
                        "exchange": str(tarjeta.get("exchange", "mexc")),
                        "id": str(tarjeta.get("id") or tarjeta["symbol"]),
                    }
                )
        return tarjetas

    # ------------------------------------------------------------------- ciclo
    def start(self):
        for objetivo in (
            self._cargar_tarjetas,
            self._cargar_catalogo,
            self._cargar_ip,
            self._poll,
        ):
            hilo = threading.Thread(target=objetivo, daemon=True)
            hilo.start()
            self._hilos.append(hilo)
        return self

    def stop(self):
        self._parar.set()

    # ------------------------------------------------------------------ hilos
    def _cargar_tarjetas(self):
        """Contrato y primer precio de cada tarjeta: esto si pide red, va en su hilo."""
        self._publicar()
        self.refresh_saldos()

    def _cargar_ip(self):
        try:
            ip = httpx.get("https://api.ipify.org", timeout=5).text.strip()
        except Exception:
            ip = "desconocida"
        self.q.put(("ip", ip))

    def _cargar_catalogo(self):
        """Catálogo completo del buscador: MEXC y, si hay claves, Bitunix."""
        try:
            self.mercados = self.mx.markets()
            self.q.put(("markets", self.mercados))
        except Exception as exc:
            self.q.put(("error", f"catalogo: {exc}"))
        cliente = self.cliente("bitunix")
        if cliente is None:
            return
        try:
            extra = 0
            for par in cliente.trading_pairs():
                simbolo = con_guion(par.get("symbol"))
                if not simbolo or simbolo in self.mercados:
                    continue
                self.mercados[simbolo] = {
                    "symbol": simbolo,
                    "baseCoin": par.get("base"),
                    "quoteCoin": par.get("quote"),
                    "_priceScale": int(par.get("quotePrecision") or 4),
                    "_solo": "bitunix",
                }
                extra += 1
            if extra:
                self.q.put(("markets", self.mercados))
                self.q.put(("status", f"Catálogo: {extra} pares extra de Bitunix"))
        except Exception as exc:
            self.q.put(("error", f"catalogo bitunix: {exc}"))

    def _poll(self):
        indice = 0
        proximo = 0.0
        proximo_hist = 0.0
        proximo_saldos = SALDOS_SEG
        proximo_fondos = FONDOS_SEG
        espera = TICKER_SEG
        while not self._parar.is_set():
            fallo = False
            if self.tarjetas:
                tarjeta = self.tarjetas[indice % len(self.tarjetas)]
                indice += 1
                symbol = tarjeta["symbol"]
                ident = tarjeta["id"]
                exchange = tarjeta.get("exchange") or ""
                cliente = self.cliente(exchange)
                if cliente is not None:
                    try:
                        datos = cliente.ticker(symbol) or {}
                        precio = float(datos.get("lastPrice") or 0)
                        if exchange == "bitunix":
                            apertura = float(datos.get("open") or 0)
                            cambio = (precio - apertura) / apertura * 100 if apertura else 0.0
                        else:
                            cambio = float(datos.get("riseFallRate") or 0) * 100
                        if precio:
                            self.precios[ident] = precio
                            self.q.put(("ticker", ident, precio, cambio))
                    except Exception as exc:
                        fallo = True
                        self.q.put(("error", f"precio {symbol}: {exc}"))
            ahora = time.monotonic()
            if ahora >= proximo:
                proximo = ahora + POSICIONES_SEG
                try:
                    posiciones = self.posiciones_todas()
                    self.ultimas_posiciones = posiciones
                    self.q.put(("positions", posiciones))
                except Exception as exc:
                    fallo = True
                    self.q.put(("error", f"posiciones: {exc}"))
                try:
                    ordenes = self.ordenes_todas()
                    self.ultimas_ordenes = ordenes
                    self.q.put(("orders", ordenes))
                except Exception as exc:
                    fallo = True
                    self.q.put(("error", f"órdenes: {exc}"))
            if self.ver_historial and ahora >= proximo_hist:
                proximo_hist = ahora + HISTORIAL_SEG
                self.cargar_historial()
            if ahora >= proximo_saldos:
                proximo_saldos = ahora + SALDOS_SEG
                self.refresh_saldos()
            if ahora >= proximo_fondos:
                proximo_fondos = ahora + FONDOS_SEG
                self.refresh_fondos()
            # si algo falla (tipico: 510 Demasiadas peticiones) se afloja el ritmo
            espera = min(5.0, espera * 2) if fallo else TICKER_SEG
            time.sleep(espera)
