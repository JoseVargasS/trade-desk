"""Cliente de Bitunix Futures (F1: solo lectura).

Diferencias con MEXC que este módulo enmascara para que la UI sea la misma:

- **Símbolo**: Bitunix usa `BTCUSDT`; MEXC `BTC_USDT`. En la app el símbolo es
  canónico (`BTCUSDT`) y cada módulo lo adapta al hablar con su servidor.
- **Tamaño**: Bitunix opera en **monedas** (`qty` 0.01 = 0.01 BTC), no en
  contratos. `qty` = nocional / precio, con el step de `minTradeVolume`.
- **Firma**: `SHA256(SHA256(nonce + timestamp + apiKey + queryParams + body) + secret)`
  con cabeceras `api-key`, `nonce`, `timestamp`, `sign`.
- Bitunix responde **HTTP 200 también en los errores**: el código de negocio va
  en el cuerpo (`code` 0 = éxito), así que `_leer` mira el cuerpo, no el status.
"""

import hashlib
import json
import time
import uuid

import httpx

BASE = "https://fapi.bitunix.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class BitunixError(Exception):
    """Error de negocio o de red devuelto por Bitunix."""


def canonico(simbolo):
    """`BTC_USDT` -> `BTCUSDT` (forma que se usa en toda la app)."""
    return (simbolo or "").replace("_", "").replace("-", "").upper()


def con_guion(simbolo):
    """`BTCUSDT` -> `BTC_USDT` (forma de MEXC)."""
    limpio = canonico(simbolo)
    if limpio.endswith("USDT"):
        return f"{limpio[:-4]}_USDT"
    return limpio


def largo(valor):
    """Interpreta el lado: la vista manda "LONG"/"SHORT", no un booleano.

    Antes se usaba `long_` como bool y "SHORT" (string no vacío) era verdadero:
    toda orden de Bitunix entraba como BUY.
    """
    if isinstance(valor, str):
        return valor.strip().upper() in ("LONG", "BUY", "TRUE", "1")
    return bool(valor)


def _filas(datos):
    """Bitunix devuelve listas o dicts con la lista adentro; esto lo normaliza."""
    if isinstance(datos, list):
        return datos
    if isinstance(datos, dict):
        for clave in ("list", "orderList", "rows", "tickers", "positions", "orders", "data"):
            if isinstance(datos.get(clave), list):
                return datos[clave]
        return [datos]
    return []


def _numero(fila, *claves, defecto=0.0):
    """Primer campo numérico que exista: Bitunix cambia nombres entre endpoints."""
    for clave in claves:
        valor = (fila or {}).get(clave)
        if valor in (None, ""):
            continue
        try:
            return float(valor)
        except (TypeError, ValueError):
            continue
    return defecto


def _texto(fila, *claves, defecto=""):
    for clave in claves:
        valor = (fila or {}).get(clave)
        if valor not in (None, ""):
            return str(valor)
    return defecto


def _display_name(simbolo):
    """Bitunix ya usa `BTCUSDT`; la interfaz muestra eso mismo."""
    return canonico(simbolo)


def decorate_positions(bitunix, posiciones, stops=()):
    """Adapta la posición de Bitunix a la forma que pinta la interfaz.

    Campos confirmados con una posición real (27-jul): `qty`, `avgOpenPrice`,
    `side` (BUY = long), `margin`, `marginRate`, `unrealizedPNL`, `liqPrice`,
    `fee` y `funding`. Los stops vienen **partidos** (un registro con `tpPrice`
    y otro con `slPrice`), así que se juntan por símbolo.
    """
    vigentes = {}
    for stop in stops or ():
        simbolo = canonico(stop.get("symbol"))
        actual = vigentes.setdefault(simbolo, {"tp": 0.0, "sl": 0.0, "id": None})
        actual["tp"] = _numero(stop, "tpPrice", "takeProfitPrice") or actual["tp"]
        actual["sl"] = _numero(stop, "slPrice", "stopLossPrice") or actual["sl"]
        actual["id"] = actual["id"] or stop.get("id")
    salida = []
    for pos in posiciones:
        simbolo = canonico(pos.get("symbol"))
        largo = _texto(pos, "side").upper() == "BUY"
        contrato = bitunix.contract(simbolo)
        stop = vigentes.get(simbolo) or {}
        salida.append(
            {
                **pos,
                "symbol": simbolo,
                "positionId": pos.get("positionId") or pos.get("id") or simbolo,
                "positionType": 1 if largo else 2,
                "holdVol": _numero(pos, "qty", "vol", "positionAmt"),
                "holdAvgPrice": _numero(pos, "avgOpenPrice", "entryPrice", "avgPrice"),
                "unRealizedPnl": _numero(pos, "unrealizedPNL", "unrealizedPnl", "unrealisedPnl"),
                "liquidatePrice": _numero(pos, "liqPrice", "liquidatePrice"),
                "leverage": int(_numero(pos, "leverage")) or 1,
                "im": _numero(pos, "margin", "im", "marginAmount"),
                "marginRatio": _numero(pos, "marginRate", "marginRatio"),
                "createTime": _numero(pos, "ctime", "createTime"),
                "totalFee": abs(_numero(pos, "fee", "totalFee")),
                "holdFee": abs(_numero(pos, "funding")),
                "lowSaveTotalFee": 0.0,
                "_contractSize": float(contrato.get("contractSize") or 1.0),
                "_priceScale": int(contrato.get("priceScale") or 4),
                "_volUnit": 1.0,
                "_qtyStep": float(contrato.get("qtyStep") or 0.0001),
                "_name": _display_name(simbolo),
                "_tp": float(stop.get("tp") or 0.0),
                "_sl": float(stop.get("sl") or 0.0),
                "_tpsl_id": stop.get("id"),
                "_exchange": "bitunix",
            }
        )
    return salida


def decorate_orders(bitunix, ordenes):
    """Órdenes abiertas de Bitunix con la forma que espera la tabla."""
    salida = []
    for orden in ordenes:
        simbolo = canonico(orden.get("symbol"))
        contrato = bitunix.contract(simbolo)
        largo = _texto(orden, "side").upper() in ("BUY", "LONG")
        salida.append(
            {
                **orden,
                "symbol": simbolo,
                "orderId": _texto(orden, "orderId", "id"),
                "side": 1 if largo else 3,
                "vol": _numero(orden, "qty", "vol"),
                "dealVol": _numero(orden, "tradeQty", "filledQty", "dealVol"),
                "price": _numero(orden, "price"),
                "leverage": int(_numero(orden, "leverage")) or 1,
                "orderMargin": _numero(orden, "margin", "orderMargin"),
                "state": 2,
                "createTime": _numero(orden, "ctime", "createTime"),
                "takeProfitPrice": _numero(orden, "takeProfitPrice", "tpPrice"),
                "stopLossPrice": _numero(orden, "stopLossPrice", "slPrice"),
                "totalFee": _numero(orden, "fee", "paidFee"),
                "_contractSize": 1.0,
                "_priceScale": int(contrato.get("priceScale") or 4),
                "_name": _display_name(simbolo),
                "_exchange": "bitunix",
            }
        )
    return salida


class Bitunix:
    def __init__(self, key="", secret="", timeout=15.0):
        self.key = (key or "").strip()
        self.secret = (secret or "").strip()
        self.timeout = timeout
        self._cliente = None
        self._contratos = {}
        self._precios = {}
        self._modo = ""

    # -------------------------------------------------------------- transporte
    @property
    def cliente(self):
        if self._cliente is None:
            # IPv4 forzada: las keys estan atadas a la IPv4 del usuario
            self._cliente = httpx.Client(
                timeout=self.timeout,
                headers={"User-Agent": UA, "Content-Type": "application/json"},
                transport=httpx.HTTPTransport(local_address="0.0.0.0"),
            )
        return self._cliente

    def _firma(self, params, cuerpo):
        nonce = uuid.uuid4().hex
        estamp = str(int(time.time() * 1000))
        digest = hashlib.sha256(f"{nonce}{estamp}{self.key}{params}{cuerpo}".encode()).hexdigest()
        return {
            "api-key": self.key,
            "nonce": nonce,
            "timestamp": estamp,
            "sign": hashlib.sha256((digest + self.secret).encode()).hexdigest(),
        }

    def _get(self, ruta, params=None):
        params = {k: v for k, v in (params or {}).items() if v is not None}
        # Bitunix firma los query params SIN separadores: `id=1&uid=200` se firma
        # como "id1uid200" (asi lo documenta el ejemplo oficial). Con `&`/`=`
        # devuelve 10007 Signature Error.
        orden = "".join(f"{k}{params[k]}" for k in sorted(params))
        cabeceras = self._firma(orden, "") if self.key else {}
        respuesta = self.cliente.get(BASE + ruta, params=params, headers=cabeceras)
        return self._leer(respuesta)

    def _post(self, ruta, payload):
        cuerpo = json.dumps(payload, separators=(",", ":"))
        cabeceras = self._firma("", cuerpo)
        respuesta = self.cliente.post(BASE + ruta, content=cuerpo, headers=cabeceras)
        return self._leer(respuesta)

    @staticmethod
    def _leer(respuesta):
        try:
            datos = respuesta.json()
        except ValueError:
            raise BitunixError(f"HTTP {respuesta.status_code}") from None
        if not isinstance(datos, dict):
            raise BitunixError(f"Respuesta invalida de Bitunix (HTTP {respuesta.status_code}).")
        if not 200 <= respuesta.status_code < 300:
            raise BitunixError(f"HTTP {respuesta.status_code}")
        codigo = datos.get("code")
        exito = (type(codigo) is int and codigo == 0) or codigo == "0"
        if not exito:
            raise BitunixError(
                f"{codigo}: {datos.get('msg') or datos.get('message') or ''}".strip()
            )
        return datos.get("data")

    # ----------------------------------------------------------------- mercado
    def tickers(self, simbolos=()):
        params = {"symbols": ",".join(canonico(s) for s in simbolos)} if simbolos else {}
        return _filas(self._get("/api/v1/futures/market/tickers", params))

    def ticker(self, simbolo):
        """Fila del ticker: `lastPrice`, `markPrice`, `open`, `high`, `low`."""
        buscado = canonico(simbolo)
        for fila in self.tickers([buscado]):
            if canonico(fila.get("symbol")) == buscado:
                return fila
        return {}

    def price(self, simbolo):
        precio = float(self.ticker(simbolo).get("lastPrice") or 0)
        if precio:
            self._precios[canonico(simbolo)] = precio
        return precio

    def cambio(self, simbolo):
        """Variación 24 h en %, con `open` como referencia (como `riseFallRate`)."""
        fila = self.ticker(simbolo)
        ultimo = float(fila.get("lastPrice") or 0)
        apertura = float(fila.get("open") or 0)
        return (ultimo - apertura) / apertura * 100 if apertura else 0.0

    def trading_pairs(self):
        return _filas(self._get("/api/v1/futures/market/trading_pairs", {}))

    def contract(self, simbolo):
        """Especificaciones del par, con la forma que espera la interfaz.

        `contractSize` es 1: en Bitunix `qty` ya está en monedas, así que el
        nocional es `qty × precio` y `priceScale` sale de `quotePrecision`.
        """
        buscado = canonico(simbolo)
        if buscado in self._contratos:
            return self._contratos[buscado]
        contrato = {}
        for fila in _filas(self._get("/api/v1/futures/market/trading_pairs", {"symbols": buscado})):
            if canonico(fila.get("symbol")) == buscado:
                contrato = {
                    "symbol": buscado,
                    "contractSize": 1.0,
                    "priceScale": int(fila.get("quotePrecision") or 4),
                    "qtyStep": float(fila.get("minTradeVolume") or 0.0001),
                    "qtyPrecision": int(fila.get("basePrecision") or 4),
                    "maxLeverage": int(fila.get("maxLeverage") or 1),
                    "minLeverage": int(fila.get("minLeverage") or 1),
                    "defaultLeverage": int(fila.get("defaultLeverage") or 10),
                    "estado": fila.get("symbolStatus"),
                    "base": fila.get("base"),
                    "quote": fila.get("quote"),
                }
                break
        self._contratos[buscado] = contrato
        return contrato

    # ------------------------------------------------------------------ cuenta
    def assets(self):
        """Saldo de futuros (`available`, `margin`, `unrealizedPNL`...)."""
        return self._get("/api/v1/futures/account", {}) or {}

    def available(self, margin_coin="USDT"):
        """USDT disponible en la cuenta de futuros."""
        for fila in _filas(self.assets()):
            if str(fila.get("marginCoin") or "").upper() == margin_coin:
                return _numero(fila, "available")
        return 0.0

    def saldo(self, margin_coin="USDT"):
        """Saldo en vivo: disponible + margen + congelado.

        El `available` de Bitunix ya incluye el PnL no realizado, así que esta
        suma es el equity de la cuenta y se mueve con las posiciones abiertas.
        """
        for fila in _filas(self.assets()):
            if str(fila.get("marginCoin") or "").upper() == margin_coin:
                return (
                    _numero(fila, "available") + _numero(fila, "margin") + _numero(fila, "frozen")
                )
        return 0.0

    def funding(self, simbolo):
        """Tasa y hora del próximo funding.

        Ojo con la unidad: Bitunix manda `fundingRate` en **porcentaje**
        (`"0.01"` = 0,01 %), MEXC en fracción; acá se normaliza a fracción.
        """
        symbol = canonico(simbolo)
        datos = self._get("/api/v1/futures/market/funding_rate", {"symbol": symbol}) or {}
        if not datos:
            return {}
        proxima = _numero(datos, "nextFundingTime")
        return {
            "tasa": _numero(datos, "fundingRate") / 100,
            "proxima": proxima / 1000 if proxima else 0.0,
            "ciclo": int(_numero(datos, "fundingInterval") or 8),
        }

    def positions(self):
        """Posiciones abiertas (campos crudos de Bitunix)."""
        return _filas(self._get("/api/v1/futures/position/get_pending_positions", {}))

    def open_orders(self):
        return _filas(self._get("/api/v1/futures/trade/get_pending_orders", {}))

    def tpsl_list(self):
        return _filas(self._get("/api/v1/futures/tpsl/get_pending_orders", {}))

    # ------------------------------------------------------------- conversiones
    def size_to_qty(self, simbolo, nocional, precio):
        """USDT -> monedas, con floor al step del par (nunca se pasa de lo pedido)."""
        if not (nocional and precio):
            return 0.0
        contrato = self.contract(simbolo)
        bruto = float(nocional) / float(precio)
        step = float(contrato.get("qtyStep") or 0.0001) or 0.0001
        pasos = int(bruto / step)
        decimales = max(0, int(contrato.get("qtyPrecision") or 4))
        return round(pasos * step, decimales)

    def qty_to_usdt(self, simbolo, qty, precio):
        return float(qty or 0) * float(precio or 0)

    # ------------------------------------------------------------------ cuenta
    def position_mode(self):
        """`HEDGE` o `ONE_WAY`: define si la orden lleva `tradeSide`."""
        if self._modo:
            return self._modo
        try:
            datos = self._get("/api/v1/futures/account/position_mode", {}) or {}
            self._modo = str(datos.get("positionMode") or "HEDGE").upper()
        except Exception:
            self._modo = "HEDGE"
        return self._modo

    def change_leverage(self, simbolo, leverage):
        return self._post(
            "/api/v1/futures/account/change_leverage",
            {
                "symbol": canonico(simbolo),
                "leverage": int(leverage),
                "marginCoin": "USDT",
            },
        )

    # compatibilidad con la interfaz (misma superficie que Mexc)
    def size_to_vol(self, simbolo, nocional_usdt, price, contract=None):
        return self.size_to_qty(simbolo, nocional_usdt, price)

    def vol_to_usdt(self, simbolo, vol, price):
        return self.qty_to_usdt(simbolo, vol, price)

    # ----------------------------------------------------------------- órdenes
    def _texto_qty(self, qty):
        return f"{float(qty):.8f}".rstrip("0").rstrip(".")

    def _texto_precio(self, simbolo, precio):
        escala = int(self.contract(simbolo).get("priceScale") or 4)
        return f"{float(precio):.{escala}f}"

    def open_market(self, simbolo, long_, nocional, leverage, tipo, tp=None, sl=None, precio=None):
        """Abre a mercado o límite. Misma firma y salida que `Mexc.open_market`."""
        symbol = canonico(simbolo)
        px = float(precio or 0) or self.price(symbol)
        if not px:
            raise BitunixError("Sin precio para calcular la cantidad")
        self.change_leverage(symbol, leverage)
        qty = self.size_to_qty(symbol, nocional, px)
        if qty <= 0:
            raise BitunixError("La cantidad quedó en 0: subí el tamaño")
        payload = {
            "symbol": symbol,
            "qty": self._texto_qty(qty),
            "side": "BUY" if largo(long_) else "SELL",
            "orderType": "LIMIT" if precio else "MARKET",
        }
        if self.position_mode() == "HEDGE":
            payload["tradeSide"] = "OPEN"
        if precio:
            payload["price"] = self._texto_precio(symbol, precio)
            payload["effect"] = "GTC"
        if tp:
            payload["tpPrice"] = self._texto_precio(symbol, tp)
            payload["tpStopType"] = "LAST_PRICE"
            payload["tpOrderType"] = "MARKET"
        if sl:
            payload["slPrice"] = self._texto_precio(symbol, sl)
            payload["slStopType"] = "LAST_PRICE"
            payload["slOrderType"] = "MARKET"
        data = self._post("/api/v1/futures/trade/place_order", payload)
        return data or {}, qty, px

    def close_position(self, pos, vol=None, price=None):
        """Cierra una posición.

        Sin `vol` ni precio va por `flash_close_position` (mercado, total), que
        no tiene la ambigüedad del `side` que pide `place_order` en modo hedge.
        """
        symbol = canonico(pos.get("symbol"))
        position_id = str(pos.get("positionId"))
        if vol is None and not price:
            return self._post(
                "/api/v1/futures/trade/flash_close_position", {"positionId": position_id}
            )
        qty = float(vol or pos.get("holdVol") or pos.get("qty") or 0)
        payload = {
            "symbol": symbol,
            "qty": self._texto_qty(qty),
            "side": "BUY" if int(pos.get("positionType") or 1) == 1 else "SELL",
            "orderType": "LIMIT" if price else "MARKET",
            "reduceOnly": True,
            "positionId": position_id,
        }
        if self.position_mode() == "HEDGE":
            payload["tradeSide"] = "CLOSE"
        if price:
            payload["price"] = self._texto_precio(symbol, price)
            payload["effect"] = "GTC"
        return self._post("/api/v1/futures/trade/place_order", payload)

    def close_all(self, simbolo=None):
        cuerpo = {"symbol": canonico(simbolo)} if simbolo else {}
        return self._post("/api/v1/futures/trade/close_all_position", cuerpo)

    def _esperar_sin_posicion(self, simbolo, timeout=4.0):
        """Espera a que la posición desaparezca: el cierre es asincrono."""
        buscado = canonico(simbolo)
        fin = time.time() + timeout
        while time.time() < fin:
            if not any(canonico(x.get("symbol")) == buscado for x in self.positions()):
                return True
            time.sleep(0.3)
        return False

    def reverse(self, pos):
        """No hay reverse nativo: cierra a mercado y abre la contraria.

        Se cierra con `place_order` reduceOnly y **no** con `flash_close_position`:
        después del flash close, Bitunix rechaza una apertura inmediata del mismo
        par con `30016` (lo probamos con 0.0001 y 0.0002, y esperando 10 s).
        """
        symbol = canonico(pos.get("symbol"))
        largo = int(pos.get("positionType") or 1) == 1
        qty = float(pos.get("holdVol") or pos.get("qty") or 0)
        self.close_position(pos, vol=qty)
        self._esperar_sin_posicion(symbol)
        payload = {
            "symbol": symbol,
            "qty": self._texto_qty(qty),
            "side": "SELL" if largo else "BUY",
            "orderType": "MARKET",
        }
        if self.position_mode() == "HEDGE":
            payload["tradeSide"] = "OPEN"
        try:
            return self._post("/api/v1/futures/trade/place_order", payload)
        except BitunixError as exc:
            raise BitunixError(
                f"Se cerró la posición pero no se pudo abrir la contraria: {exc}"
            ) from exc

    def cancel(self, order_ids):
        """Cancela por id: Bitunix pide el símbolo, así que se agrupa."""
        ids = [str(i) for i in order_ids if i]
        if not ids:
            return None
        pendientes = {
            _texto(o, "orderId", "id"): canonico(o.get("symbol")) for o in self.open_orders()
        }
        por_simbolo = {}
        for order_id in ids:
            simbolo = pendientes.get(order_id)
            if simbolo:
                por_simbolo.setdefault(simbolo, []).append({"orderId": order_id})
        salida = []
        for simbolo, lista in por_simbolo.items():
            salida.append(
                self._post(
                    "/api/v1/futures/trade/cancel_orders",
                    {"symbol": simbolo, "orderList": lista},
                )
            )
        return salida

    def cancel_all(self, simbolo=None):
        return self._post(
            "/api/v1/futures/trade/cancel_all_orders",
            {"symbol": canonico(simbolo)} if simbolo else {},
        )

    def change_margin(self, position_id, amount, kind="ADD", simbolo=None, side=None):
        delta = abs(float(amount)) * (1 if str(kind).upper() == "ADD" else -1)
        payload = {
            "marginCoin": "USDT",
            "amount": f"{delta:.8f}".rstrip("0").rstrip("."),
            "positionId": str(position_id),
        }
        if simbolo:
            payload["symbol"] = canonico(simbolo)
        if side:
            payload["side"] = "LONG" if side else "SHORT"
        return self._post("/api/v1/futures/account/adjust_position_margin", payload)

    # ------------------------------------------------------------------ tp/sl
    def _simbolo_de(self, position_id=None, stop_id=None):
        """Símbolo de una posición o de un stop (las firmas de la UI no lo traen)."""
        for stop in self.tpsl_list():
            if stop_id is not None and str(stop.get("id")) == str(stop_id):
                return canonico(stop.get("symbol"))
            if position_id is not None and str(stop.get("positionId")) == str(position_id):
                return canonico(stop.get("symbol"))
        for pos in self.positions():
            if position_id is not None and str(pos.get("positionId")) == str(position_id):
                return canonico(pos.get("symbol"))
        raise BitunixError("No encontré el símbolo de esa posición")

    def tpsl_place(self, position_id, vol=None, tp=None, sl=None, simbolo=None):
        """TP/SL a nivel de posición: al dispararse cierra toda la posición.

        Es el endpoint `tpsl/position/place_order` (uno por posición, sin `qty`).
        """
        symbol = canonico(simbolo) if simbolo else self._simbolo_de(position_id)
        payload = {"symbol": symbol, "positionId": str(position_id)}
        if tp:
            payload["tpPrice"] = self._texto_precio(symbol, tp)
            payload["tpStopType"] = "LAST_PRICE"
        if sl:
            payload["slPrice"] = self._texto_precio(symbol, sl)
            payload["slStopType"] = "LAST_PRICE"
        if "tpPrice" not in payload and "slPrice" not in payload:
            raise BitunixError("Hay que indicar un TP o un SL")
        return self._post("/api/v1/futures/tpsl/position/place_order", payload)

    def tpsl_cancel(self, stop_id, simbolo=None):
        symbol = canonico(simbolo) if simbolo else self._simbolo_de(stop_id=stop_id)
        return self._post(
            "/api/v1/futures/tpsl/cancel_order", {"symbol": symbol, "orderId": str(stop_id)}
        )

    # ------------------------------------------------------------- modificar
    def modify_order(self, orden, form):
        """Cambia cantidad, precio y TP/SL de una orden viva (nativo, sin cancelar)."""
        symbol = canonico(orden.get("symbol"))
        payload = {
            "orderId": str(orden.get("orderId")),
            "symbol": symbol,
            "qty": self._texto_qty(form["vol"]),
            "price": self._texto_precio(symbol, form["price"]),
        }
        if form.get("tp"):
            payload["tpPrice"] = self._texto_precio(symbol, form["tp"])
            payload["tpStopType"] = "LAST_PRICE"
            payload["tpOrderType"] = "MARKET"
        if form.get("sl"):
            payload["slPrice"] = self._texto_precio(symbol, form["sl"])
            payload["slStopType"] = "LAST_PRICE"
            payload["slOrderType"] = "MARKET"
        return self._post("/api/v1/futures/trade/modify_order", payload)

    # --------------------------------------------------------------- historial
    def history(self, limite=50, salto=0):
        """Órdenes históricas con la forma que pinta la pestaña Historial."""
        filas = _filas(
            self._get("/api/v1/futures/trade/get_history_orders", {"limit": limite, "skip": salto})
        )
        salida = []
        for orden in filas:
            symbol = canonico(orden.get("symbol"))
            contrato = self.contract(symbol)
            largo = _texto(orden, "side").upper() in ("BUY", "LONG")
            estado = _texto(orden, "status").upper()
            hecho = estado == "FILLED"
            salida.append(
                {
                    **orden,
                    "symbol": _display_name(symbol),
                    "orderId": _texto(orden, "orderId", "id"),
                    "side": 1 if largo else 3,
                    "vol": _numero(orden, "qty"),
                    "dealVol": _numero(orden, "tradeQty"),
                    "price": _numero(orden, "price"),
                    "dealAvgPrice": _numero(orden, "avgPrice", "price"),
                    "profit": _numero(orden, "realizedPNL"),
                    "totalFee": abs(_numero(orden, "fee")),
                    "state": 3 if hecho else 4,
                    "createTime": _numero(orden, "ctime"),
                    "_priceScale": int(contrato.get("priceScale") or 4),
                    "_exchange": "bitunix",
                }
            )
        return salida
