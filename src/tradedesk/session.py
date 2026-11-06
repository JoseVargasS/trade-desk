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
import os
import queue
import threading
import time

import httpx

from . import creds, paths
from .archivo import Archivo
from .bingx import Bingx
from .bingx import canonico as canonico_bingx
from .bingx import decorate_orders as decorate_orders_bingx
from .bingx import decorate_positions as decorate_positions_bingx
from .bitunix import Bitunix, con_guion
from .bitunix import decorate_orders as decorate_orders_bitunix
from .bitunix import decorate_positions as decorate_positions_bitunix
from .mexc import Mexc, decorate_orders, decorate_positions, display_name
from .operaciones import operaciones

TICKER_SEG = 0.70  # una peticion cada 0.7 s en total (~1.4 req/s, el limite medido)
POSICIONES_SEG = 3.0
HISTORIAL_SEG = 15.0
SALDOS_SEG = 15.0
IP_SEG = 900.0
HISTORIAL_PAGINA = 50
FONDOS_SEG = 60.0


class Session:
    def __init__(self, mx=None, bitunix=None, bingx=None):
        self.mx = mx or Mexc(*creds.load("mexc"))
        # segundo broker: por ahora solo lectura (F1); se rutea por tarjeta en F3
        self.bitunix = bitunix or Bitunix(*creds.load("bitunix"))
        self.bingx = bingx or Bingx(*creds.load("bingx"))
        # qué brokers tienen claves: se lee una vez, no en cada vuelta del poller
        self.hay = {
            "mexc": bool(getattr(self.mx, "api_key", "")),
            "bitunix": bool(self.bitunix.key),
            "bingx": bool(self.bingx.key),
        }
        self.q = queue.Queue()
        self._log_error_reported = False
        self.tarjetas = self._tarjetas()
        self.precios = {}
        self.mercados = {}
        self.ultimas_posiciones = []
        self.ultimas_ordenes = []
        self.saldos = {"mexc": 0.0, "bitunix": 0.0, "bingx": 0.0}
        self.fondos = {}
        self._hist_ordenes = {}
        self._hist_pagina = 0
        self._hist_candado = threading.Lock()
        self.historial_hay_mas = {"mexc": True, "bitunix": True, "bingx": True}
        # archivo local: el broker borra su historial, esto queda
        self.archivo = Archivo(paths.DATA_DIR / "operaciones.json")
        self.ver_historial = False
        self._parar = threading.Event()
        self._hilos = []
        # el historial guardado se pinta al instante, sin esperar a la red
        if self.archivo.filas:
            self.q.put(("history", self.archivo.todas()))
        if getattr(self.archivo, "aviso", None):
            self.q.put(("notice", self.archivo.aviso))

    # --------------------------------------------------------------- tarjetas
    def cliente(self, exchange):
        """Cliente del broker pedido, o None si todavía no tiene claves."""
        if exchange == "bitunix":
            return self.bitunix if self.hay.get("bitunix") else None
        if exchange == "mexc":
            return self.mx if self.hay.get("mexc") else None
        if exchange == "bingx":
            return self.bingx if self.hay.get("bingx") else None
        return None

    def clientes(self):
        """Los tres clientes, con o sin claves (la tarjeta decide si sirve)."""
        return {"mexc": self.mx, "bitunix": self.bitunix, "bingx": self.bingx}

    def poner_cliente(self, exchange, cliente):
        """Reemplaza el cliente cuando se cargan claves nuevas desde la UI."""
        setattr(self, "mx" if exchange == "mexc" else exchange, cliente)
        self.hay[exchange] = True

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
        ruta = paths.DATA_DIR / "config.json"
        temporal = ruta.with_name(ruta.name + ".tmp")
        try:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            temporal.write_text(json.dumps({"cards": self.tarjetas}, indent=2), encoding="utf-8")
            os.replace(temporal, ruta)
        except Exception as exc:
            self.log(f"ERR config: {exc}")
            self.q.put(("status", f"No se pudo guardar config.json: {exc}"))
            try:
                temporal.unlink(missing_ok=True)
            except OSError:
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
                    if exchange in ("bitunix", "bingx"):
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
        """Historial de los brokers, agrupado en operaciones (una fila por posición).

        La página 1 se refresca sola cada 15 s y se **fusiona** con lo ya traído; con
        `mas=True` (botón `Ver más`) se pide la siguiente página de cada broker. Las
        órdenes se guardan por `(broker, orderId)`, así un refresco no borra lo viejo ni
        duplica filas.

        El refresco automático **no** toca `_hist_pagina`: antes lo reiniciaba a 1 y el
        botón volvía a pedir la misma página (parecía que "no traía nada"). El candado
        evita que dos cargas se pisen si el refresco cae mientras se pide más.
        """
        if not self._hist_candado.acquire(blocking=False):
            self.q.put(("history_cargando", False))
            return
        self.q.put(("history_cargando", True))
        try:
            if mas:
                self._hist_pagina += 1
            else:
                self._hist_pagina = max(1, self._hist_pagina)
            # el refresco automatico pide siempre la 1 (los cierres nuevos);
            # `Ver mas` avanza el puntero y pide esa pagina
            pagina = self._hist_pagina if mas else 1
            for nombre, traer in (
                (
                    "mexc",
                    lambda: decorate_orders(self.mx, self.mx.history(HISTORIAL_PAGINA, pagina)),
                ),
                (
                    "bitunix",
                    lambda: self.bitunix.history(HISTORIAL_PAGINA, (pagina - 1) * HISTORIAL_PAGINA),
                ),
                (
                    "bingx",
                    lambda: self.bingx.history(HISTORIAL_PAGINA, (pagina - 1) * HISTORIAL_PAGINA),
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
        finally:
            self.q.put(("history_cargando", False))
            self._hist_candado.release()

    # ------------------------------------------------------------- consultas
    def contract_for(self, symbol):
        """Contrato del par: catálogo o cache. Sin red."""
        return self.mercados.get(symbol) or self.mx.cached_contract(symbol) or {}

    def log(self, msg):
        from datetime import datetime

        ruta = paths.DATA_DIR / "trades.log"
        try:
            self._rotar_log(ruta)
            with open(str(ruta), "a", encoding="utf-8") as f:
                f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")
            self._log_error_reported = False
        except Exception as exc:
            if not self._log_error_reported:
                self._log_error_reported = True
                self.q.put(("error", f"No se pudo escribir trades.log: {exc}"))

    @staticmethod
    def _rotar_log(ruta, limite=1_000_000, copias=3):
        try:
            if not ruta.exists() or ruta.stat().st_size < limite:
                return
            for indice in range(copias, 0, -1):
                origen = ruta if indice == 1 else ruta.with_name(f"{ruta.name}.{indice - 1}")
                destino = ruta.with_name(f"{ruta.name}.{indice}")
                if origen.exists():
                    try:
                        os.replace(origen, destino)
                    except OSError:
                        pass
        except OSError:
            pass

    def refresh_positions(self):
        try:
            self.q.put(("positions", self.posiciones_todas()))
        except Exception as exc:
            self.q.put(("status", f"posiciones: {exc}"))

    def posiciones_todas(self):
        """Posiciones de todos los brokers conectados, ya adaptadas a la interfaz."""
        filas = []
        cliente = self.cliente("mexc")
        if cliente:
            try:
                posiciones = decorate_positions(cliente, cliente.positions())
            except Exception as exc:
                self._error_consulta("posiciones", "mexc", exc)
            else:
                for pos in posiciones:
                    pos["_exchange"] = "mexc"
                    filas.append(pos)
        cliente = self.cliente("bitunix")
        if cliente:
            try:
                stops = cliente.tpsl_list()
            except Exception as exc:
                self._error_consulta("TP/SL de posiciones", "bitunix", exc)
                stops = []
            try:
                filas.extend(decorate_positions_bitunix(cliente, cliente.positions(), stops))
            except Exception as exc:
                self._error_consulta("posiciones", "bitunix", exc)
        cliente = self.cliente("bingx")
        if cliente:
            try:
                condicionales = cliente.open_orders()
            except Exception as exc:
                self._error_consulta("TP/SL de posiciones", "bingx", exc)
                condicionales = []
            try:
                posiciones = cliente.positions()
                comisiones = cliente.comisiones() if posiciones else {}
                filas.extend(
                    decorate_positions_bingx(cliente, posiciones, condicionales, comisiones)
                )
            except Exception as exc:
                self._error_consulta("posiciones", "bingx", exc)
        return filas

    def _error_consulta(self, recurso, broker, exc):
        texto = f"{recurso} {broker}: {exc}"
        self.log(f"ERR {recurso} {broker}: {type(exc).__name__}")
        self.q.put(("error", texto))

    def refresh_orders(self):
        try:
            self.q.put(("orders", self.ordenes_todas()))
        except Exception as exc:
            self.q.put(("status", f"ordenes: {exc}"))

    def ordenes_todas(self):
        filas = []
        for broker, cliente, decorar in (
            ("mexc", self.cliente("mexc"), decorate_orders),
            ("bitunix", self.cliente("bitunix"), decorate_orders_bitunix),
            ("bingx", self.cliente("bingx"), decorate_orders_bingx),
        ):
            if cliente is None:
                continue
            try:
                ordenes = cliente.open_orders()
                filas_broker = decorar(cliente, ordenes)
                if broker == "mexc":
                    for orden in filas_broker:
                        orden["_exchange"] = broker
                filas.extend(filas_broker)
            except Exception as exc:
                self._error_consulta("ordenes", broker, exc)
        return filas

    def refresh_saldos(self):
        """Saldo total de cada broker conectado (libre + margen en uso).

        Antes se mostraba solo lo disponible: con una posicion abierta el
        numero chico (14,79 de 313,24) parecia un saldo roto.
        """
        saldos = dict(self.saldos)
        for nombre, cliente in (
            ("mexc", self.cliente("mexc")),
            ("bitunix", self.cliente("bitunix")),
            ("bingx", self.cliente("bingx")),
        ):
            if cliente is None:
                continue
            try:
                leer = getattr(cliente, "saldo", None) or cliente.available
                saldos[nombre] = float(leer())
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
        """IPv4 e IPv6 publicas.

        La key se ata a la IP, y el exchange ve la que usa la conexion: si el
        cliente sale por IPv6 (BingX responde `100419`), whitelistear la IPv4 no
        sirve. Se muestran las dos y los clientes fuerzan IPv4.
        """
        datos = {"v4": "", "v6": ""}
        try:
            with httpx.Client(
                timeout=5, transport=httpx.HTTPTransport(local_address="0.0.0.0")
            ) as cliente:
                datos["v4"] = cliente.get("https://api.ipify.org").text.strip()
        except Exception:
            datos["v4"] = ""
        try:
            with httpx.Client(timeout=5) as cliente:
                datos["v6"] = cliente.get("https://api6.ipify.org").text.strip()
        except Exception:
            datos["v6"] = ""
        self.q.put(("ip", datos))

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
        cliente = self.cliente("bingx")
        if cliente is None:
            return
        try:
            extra = 0
            for par in cliente.contracts():
                symbol = str(par.get("symbol") or "")
                if not symbol.upper().endswith("-USDT"):
                    continue
                simbolo = canonico_bingx(symbol).replace("-", "_")
                if not simbolo or simbolo in self.mercados:
                    continue
                self.mercados[simbolo] = {
                    "symbol": simbolo,
                    "baseCoin": canonico_bingx(symbol).split("-")[0],
                    "quoteCoin": "USDT",
                    "_priceScale": int(par.get("pricePrecision") or 2),
                    "_solo": "bingx",
                }
                extra += 1
            if extra:
                self.q.put(("markets", self.mercados))
                self.q.put(("status", f"Catálogo: {extra} pares extra de BingX"))
        except Exception as exc:
            self.q.put(("error", f"catalogo bingx: {exc}"))

    def _poll(self):
        indice = 0
        proximo = 0.0
        proximo_hist = 0.0
        proximo_saldos = SALDOS_SEG
        proximo_fondos = FONDOS_SEG
        proximo_ip = IP_SEG
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
                        if exchange in ("bitunix", "bingx"):
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
            if ahora >= proximo_ip:
                # la IP cambia (o el ISP la rota): se revalida cada 15 min
                proximo_ip = ahora + IP_SEG
                self._cargar_ip()
            # si algo falla (tipico: 510 Demasiadas peticiones) se afloja el ritmo
            espera = min(5.0, espera * 2) if fallo else TICKER_SEG
            time.sleep(espera)
