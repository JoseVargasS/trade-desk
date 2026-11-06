"""MEXC Futures: firma, endpoints y conversion de tamano.

Solo lo necesario para operar a mercado: precio, posiciones, abrir, cerrar.
"""

import hashlib
import hmac
import json
import math
import time
import uuid

import httpx

BASE = "https://contract.mexc.com"

# el WAF de MEXC devuelve 403 con el User-Agent por defecto de las librerias Python
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# codigos de error que vale la pena traducir
ERRORES = {
    401: "Sesion no valida. Revisa la API key.",
    402: "API key expirada. Crea una nueva.",
    406: "Tu IP no esta autorizada en MEXC. Agrega la IP actual al whitelist de la key.",
    510: "Demasiadas peticiones. Espera un segundo.",
    511: "La key no tiene permiso para esta accion.",
    600: "Parametro invalido.",
    602: "Firma invalida. Revisa el secret.",
    1004: "Cantidad invalida.",
    2001: "Direccion de orden invalida.",
    2015: "Precision de precio o cantidad invalida para este contrato.",
    5002: "La orden TP/SL ya no existe: puede haberse ejecutado o estar cancelandose.",
    5003: (
        "Precio de TP/SL invalido: MEXC exige que el TP este del lado de la ganancia "
        "y el SL del lado de la perdida, tomando como referencia el precio actual."
    ),
    5004: (
        "La cantidad de la orden mas el TP/SL vigente supera lo cerrable. "
        "La orden anterior se cancela de forma asincrona: reintenta en un segundo."
    ),
}


def display_name(contract):
    """Nombre como lo muestra MEXC: XAU_USDT -> GOLD(XAU)USDT."""
    contract = contract or {}
    base = contract.get("baseCoinName") or contract.get("baseCoin") or ""
    quote = contract.get("quoteCoinName") or contract.get("quoteCoin") or ""
    if base and quote:
        return f"{base}{quote}"
    english = (contract.get("displayNameEn") or "").upper()
    for tail in (" PERPETUAL", "_PERPETUAL", "永续"):
        english = english.replace(tail, "")
    return english.replace("_", "") or contract.get("symbol", "")


def plan_tp_sl(long_, price, tp, sl):
    """Ordena el TP/SL segun la unica regla que aplica MEXC, medida contra el
    precio actual (no contra la entrada):

        LONG   -> TP debe quedar por encima, SL por debajo.
        SHORT  -> TP debe quedar por debajo, SL por encima.

    Un SL del lado de la ganancia se rechaza con 5003, pero ese mismo nivel si
    entra como take profit. Cuando el TP esta vacio se mueve ahi y se avisa;
    si el TP ya ocupa el lado de la ganancia no hay forma de representarlo.

    Devuelve (tp, sl, avisos) y lanza MexcError con el motivo en castellano.
    """
    price = float(price)
    tp = float(tp) if tp else None
    sl = float(sl) if sl else None
    lado_ganancia = "por encima" if long_ else "por debajo"
    lado_perdida = "por debajo" if long_ else "por encima"
    avisos = []

    def en_ganancia(valor):
        return valor > price if long_ else valor < price

    if tp is not None and not en_ganancia(tp):
        raise MexcError(
            f"El take profit ({fmt_plain(tp)}) tiene que estar {lado_ganancia} del "
            f"precio actual ({fmt_plain(price)}): si ya esta alcanzado, MEXC lo rechaza."
        )

    if sl is not None and en_ganancia(sl):
        if tp is None:
            avisos.append(
                f"El SL {fmt_plain(sl)} estaba del lado de la ganancia: MEXC solo acepta "
                f"ese nivel como take profit, asi que se guardo como TP "
                f"(cierra en {fmt_plain(sl)}). La posicion queda SIN stop loss."
            )
            tp, sl = sl, None
        else:
            raise MexcError(
                f"El TP ({fmt_plain(tp)}) y el SL ({fmt_plain(sl)}) quedan los dos del "
                f"lado de la ganancia del precio actual ({fmt_plain(price)}). MEXC solo "
                f"admite un nivel ahi: deja el SL {lado_perdida} de {fmt_plain(price)}."
            )

    return tp, sl, avisos


def fmt_plain(value):
    """Precio para mensajes de error; los widgets usan theme.fmt_price."""
    return f"{float(value):,.2f}"


def close_vol(hold_vol, pct):
    """Contratos a cerrar segun el % de la posicion.

    100% devuelve la posicion exacta (sin redondeo: un cierre total nunca falla
    por cantidad). Debajo, floor al contrato entero, que es el `volUnit` que
    tienen los 1.171 pares de MEXC.
    """
    hold = float(hold_vol or 0)
    pct = min(100.0, max(0.0, float(pct if pct is not None else 100)))
    if pct >= 100:
        return hold
    return float(math.floor(hold * pct / 100))


def fee_desglose(position):
    """Fee de la posicion como la muestra MEXC: comision cobrada + funding.

    `totalFee` es la comision ya cobrada al abrir, `holdFee` el funding (MEXC lo
    pinta en su propia linea) y `lowSaveTotalFee` lo ahorrado, que se muestra
    pero **no** suma. El total es la suma de los dos primeros.
    """
    comision = abs(float(position.get("totalFee") or 0))
    funding = abs(float(position.get("holdFee") or 0))
    return {
        "comision": comision,
        "funding": funding,
        "total": comision + funding,
        "ahorro": float(position.get("lowSaveTotalFee") or 0),
    }


def mark_price(position):
    """Precio de marca derivado del PnL: `open_positions` no lo manda."""
    qty = float(position.get("holdVol") or 0)
    size = float(position.get("_contractSize") or 0)
    if not (qty and size):
        return 0.0
    entry = float(position.get("holdAvgPrice") or 0)
    signo = 1 if int(position.get("positionType") or 1) == 1 else -1
    return entry + (float(position.get("unRealizedPnl") or 0) / (qty * size)) * signo


def precio_por_pnl(entrada, pct, apalancamiento, largo, escala=2):
    """Precio que deja ese % de PnL **sobre el margen** (TP/SL por porcentaje).

    PnL% = (salida - entrada) / entrada * apalancamiento * 100, así que
    precio = entrada * (1 ± pct / (100 * lev)). Un SL se escribe en negativo.
    """
    try:
        base = float(entrada or 0)
        porcentaje = float(str(pct if pct not in (None, "") else "0").replace(",", "").strip())
        palanca = max(1.0, float(apalancamiento or 1))
    except (TypeError, ValueError):
        return ""
    if not base or not porcentaje:
        return ""
    signo = 1 if largo else -1
    precio = base * (1 + signo * porcentaje / (100.0 * palanca))
    if precio <= 0:
        return ""
    return f"{precio:.{int(escala)}f}"


def pnl_en_precio(position, long_, precio):
    """Lo que se gana (o pierde) si la posicion se cerrara en `precio`, sin fees."""
    coins = float(position.get("holdVol") or 0) * float(position.get("_contractSize") or 0)
    entry = float(position.get("holdAvgPrice") or 0)
    return coins * (float(precio) - entry) * (1 if long_ else -1)


def neto_posicion(posicion, taker=None):
    """PnL bruto, costos y neto de una posicion abierta.

    `neto = pnl - comision pagada - funding cobrado - salida estimada`, con la
    salida estimada como el nocional por la tasa taker. Si no se pasa la tasa se
    usa la efectiva de la comision pagada, que es como la estima el globo de la
    fee. Sirve para los tres brokers: son los mismos campos ya decorados.
    """
    pnl = float(posicion.get("unRealizedPnl") or 0)
    detalle = fee_desglose(posicion)
    cantidad = float(posicion.get("holdVol") or 0)
    tamano = float(posicion.get("_contractSize") or 0)
    entrada = float(posicion.get("holdAvgPrice") or 0)
    nocional = cantidad * tamano * entrada
    comision = float(detalle.get("comision") or 0)
    funding = float(detalle.get("funding") or 0)
    tasa = taker if taker is not None else posicion.get("_takerRate")
    if tasa is None and nocional:
        tasa = comision / nocional
    salida = nocional * float(tasa or 0)
    costo = comision + funding + salida
    return {
        "bruto": pnl,
        "comision": comision,
        "funding": funding,
        "salida": salida,
        "costo": costo,
        "neto": pnl - costo,
    }


def resumen_pnl(posiciones):
    """Bruto y neto de todas las posiciones abiertas, juntos."""
    total = {"bruto": 0.0, "comision": 0.0, "funding": 0.0, "salida": 0.0, "costo": 0.0}
    cuantas = 0
    for posicion in posiciones or ():
        fila = neto_posicion(posicion)
        for clave in total:
            total[clave] += fila[clave]
        cuantas += 1
    total["neto"] = total["bruto"] - total["costo"]
    total["cuantas"] = cuantas
    return total


def break_even_price(position, long_):
    """SL que deja la operacion en cero (cubre entrada, salida y funding).

    MEXC no informa lo que cobrara al cerrar: la comision se calcula al cerrar
    con la tasa del contrato sobre el nocional de salida. Se usa la tasa
    efectiva que ya se cobro al abrir (asi entran los descuentos), aplicada al
    nocional del break-even: mismo tamaño y practicamente el mismo precio.

    Devuelve (precio, cubre): el SL redondeado hacia afuera del precio (ceil en
    long, floor en short, para que el tick nunca deje perdida) y lo que cubre en
    USDT, que es el PnL bruto en ese precio.
    """
    entry = float(position.get("holdAvgPrice") or 0)
    coins = float(position.get("holdVol") or 0) * float(position.get("_contractSize") or 0)
    if not (entry and coins):
        return None, 0.0
    fee = fee_desglose(position)
    coste = fee["comision"] + fee["funding"]
    tasa = fee["comision"] / (coins * entry)
    paso = 10 ** int(position.get("_priceScale") or 2)
    if long_:
        ideal = (entry + coste / coins) / (1 - tasa)
        be = math.ceil(ideal * paso) / paso
        return be, coins * (be - entry)
    ideal = (entry - coste / coins) / (1 + tasa)
    be = math.floor(ideal * paso) / paso
    return be, coins * (entry - be)


def es_editable(order):
    """Solo las órdenes que abren posición se pueden reenviar tal cual."""
    return int(order.get("side") or 0) in (1, 3)


def num_texto(valor):
    """Número para un campo de texto, sin ceros de relleno ni comas de miles."""
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        return ""
    if not numero:
        return ""
    return f"{numero:.8f}".rstrip("0").rstrip(".")


def margen_inicial(order):
    """Margen real de la orden (nocional / apalancamiento).

    `orderMargin` incluye la comisión, así que guardar sin tocar nada cambiaría
    el tamaño; se prefiere el margen limpio y solo se cae a `orderMargin` si
    falta algún dato.
    """
    vol = float(order.get("vol") or 0)
    size = float(order.get("_contractSize") or 0)
    price = float(order.get("price") or 0)
    lev = float(order.get("leverage") or 0)
    if vol and size and price and lev:
        return vol * size * price / lev
    return float(order.get("orderMargin") or 0)


def decorate_positions(mx, positions, on_error=None):
    """Agrega a cada posicion lo que `open_positions` no devuelve: contrato,
    nombre de MEXC y el TP/SL vigente (que vive en otro endpoint)."""
    for p in positions:
        try:
            contract = mx.contract(p["symbol"])
            p["_contractSize"] = contract["contractSize"]
            p["_volUnit"] = float(contract.get("volUnit") or 1)
            p["_priceScale"] = int(contract.get("priceScale") or 2)
            p["_name"] = display_name(contract)
        except Exception as exc:
            p["_contractSize"] = 0
            p["_volUnit"] = 1
            p["_priceScale"] = 2
            p["_name"] = p.get("symbol", "")
            if on_error:
                on_error("contrato", exc)
    stops = {}
    if positions:
        try:
            stops = {int(o.get("positionId") or 0): o for o in mx.tpsl_list()}
        except Exception as exc:
            stops = {}
            if on_error:
                on_error("TP/SL", exc)
    for p in positions:
        stop = stops.get(int(p.get("positionId") or 0))
        p["_tp"] = float(stop.get("takeProfitPrice") or 0) if stop else 0.0
        p["_sl"] = float(stop.get("stopLossPrice") or 0) if stop else 0.0
        p["_tpsl_id"] = stop.get("id") if stop else None
    return positions


def decorate_orders(mx, orders):
    """Nombre, size y precision de cada orden abierta. Nunca pide red.

    `open_orders` ya trae precio, cantidad y TP/SL; solo falta el contrato para
    pasar contratos a USDT y para mostrar el precio con los decimales exactos
    con los que se envio (priceScale).
    """
    for o in orders:
        contract = mx.known_contract(o.get("symbol"))
        o["_contractSize"] = float(contract.get("contractSize") or 0)
        o["_priceScale"] = int(contract.get("priceScale") or 2)
        o["_name"] = display_name(contract) if contract else o.get("symbol", "")
    return orders


class MexcError(Exception):
    pass


class Mexc:
    def __init__(self, api_key="", secret=""):
        self.api_key = api_key
        self.secret = secret
        # cliente persistente: reusa la conexion TLS (~20ms por orden en vez de ~45ms)
        # local_address IPv4: la key esta atada a la IPv4 del usuario y sin esto
        # la conexion puede salir por IPv6 (BingX responde 100419)
        self.http = httpx.Client(
            base_url=BASE,
            timeout=8.0,
            headers={"User-Agent": UA, "Content-Type": "application/json"},
            transport=httpx.HTTPTransport(local_address="0.0.0.0"),
        )
        self._contracts = {}
        self._markets = None

    # ------------------------------------------------------------------ firma
    def _sign(self, ts, payload_str):
        msg = (self.api_key + ts + payload_str).encode()
        return hmac.new(self.secret.encode(), msg, hashlib.sha256).hexdigest()

    @staticmethod
    def _unwrap(resp):
        try:
            data = resp.json()
        except ValueError:
            if resp.status_code in (403, 418, 429):
                raise MexcError(
                    f"HTTP {resp.status_code}: peticion bloqueada (WAF o limite). "
                    "Reintenta en unos segundos."
                ) from None
            raise MexcError(f"HTTP {resp.status_code}: respuesta no JSON") from None
        if not isinstance(data, dict):
            raise MexcError("Respuesta invalida de MEXC.")
        if data.get("success") is not True:
            code = data.get("code")
            msg = ERRORES.get(code) or data.get("message") or f"code={code}"
            raise MexcError(msg)
        return data.get("data")

    def _post(self, path, payload):
        ts = str(int(time.time() * 1000))
        body = json.dumps(payload, separators=(",", ":"))
        headers = {
            "ApiKey": self.api_key,
            "Request-Time": ts,
            "Signature": self._sign(ts, body),
            "Content-Type": "application/json",
        }
        return self._unwrap(self.http.post(path, content=body.encode(), headers=headers))

    def _get(self, path, params=None):
        ts = str(int(time.time() * 1000))
        items = sorted((k, v) for k, v in (params or {}).items() if v is not None)
        qs = "&".join(f"{k}={v}" for k, v in items)
        headers = {
            "ApiKey": self.api_key,
            "Request-Time": ts,
            "Signature": self._sign(ts, qs),
        }
        return self._unwrap(self.http.get(path + (f"?{qs}" if qs else ""), headers=headers))

    # --------------------------------------------------------------- publico
    def ticker(self, symbol):
        return self._unwrap(self.http.get("/api/v1/contract/ticker", params={"symbol": symbol}))

    def price(self, symbol):
        return float(self.ticker(symbol)["lastPrice"])

    def contract(self, symbol):
        if symbol not in self._contracts:
            data = self._unwrap(self.http.get("/api/v1/contract/detail", params={"symbol": symbol}))
            if not isinstance(data, dict) or not data:
                raise MexcError(f"MEXC no devolvio el contrato de {symbol}.")
            self._contracts[symbol] = data
        return self._contracts[symbol]

    def cached_contract(self, symbol):
        """Contrato ya pedido (sin red). Sirve para pintar el nombre del par."""
        return self._contracts.get(symbol)

    def known_contract(self, symbol):
        """Contrato del catalogo o del detalle ya cacheado. Nunca pide red."""
        return (self._markets or {}).get(symbol) or self._contracts.get(symbol) or {}

    def markets(self, force=False):
        """Todos los contratos operables por API, indexados por simbolo.

        No alimenta self._contracts: el catalogo trae tasas y precisiones que
        pueden diferir del endpoint individual, que es el que manda.
        """
        if self._markets is None or force:
            data = self._unwrap(self.http.get("/api/v1/contract/detail"))
            if (
                not isinstance(data, list)
                or not data
                or not all(isinstance(contract, dict) for contract in data)
            ):
                raise MexcError("MEXC devolvio un catalogo de contratos invalido.")
            self._markets = {
                c["symbol"]: c for c in data if c.get("state") == 0 and c.get("apiAllowed")
            }
        return self._markets

    def est_fee(self, symbol, notional_usdt):
        c = self.contract(symbol)
        return float(notional_usdt) * float(c.get("takerFeeRate") or 0)

    def est_liq(self, symbol, entry, leverage, side):
        """Liquidacion aproximada en margen aislado. Ignora los tiers de riesgo."""
        c = self.contract(symbol)
        mmr = float(c.get("maintenanceMarginRate") or 0)
        lev = max(int(leverage), 1)
        if side == "LONG":
            return float(entry) * (1 - 1 / lev + mmr)
        return float(entry) * (1 + 1 / lev - mmr)

    def size_to_vol(self, symbol, notional_usdt, price, contract=None):
        """USDT nocionales -> contratos, respetando el step del contrato.

        `contract` permite pasar el contrato ya cacheado: la UI lo usa para
        previsualizar sin pedir nada a la red.
        """
        c = contract or self.contract(symbol)
        size = float(c["contractSize"])
        step = float(c.get("volUnit") or 1)
        min_vol = float(c.get("minVol") or step)
        max_vol = float(c.get("maxVol") or 0)

        raw = notional_usdt / (price * size)
        vol = math.floor(raw / step) * step
        vol = round(vol, int(c.get("volScale") or 0))

        if vol < min_vol:
            minimo = min_vol * size * price
            raise MexcError(
                f"Tamano muy chico: {vol} contratos. Minimo {min_vol} = {minimo:.2f} USDT"
            )
        if max_vol and vol > max_vol:
            raise MexcError(f"Tamano muy grande: {vol} > maximo {max_vol}")
        return vol

    def vol_to_usdt(self, symbol, vol, price):
        return float(vol) * float(self.contract(symbol)["contractSize"]) * price

    # --------------------------------------------------------------- privado
    def positions(self):
        return self._get("/api/v1/private/position/open_positions") or []

    def open_orders(self):
        return (
            self._get("/api/v1/private/order/list/open_orders", {"page_num": 1, "page_size": 20})
            or []
        )

    def history(self, size=50, pagina=1):
        """Órdenes históricas (las más nuevas primero), paginadas de 1 en adelante."""
        return (
            self._get(
                "/api/v1/private/order/list/history_orders",
                {"page_num": pagina, "page_size": size},
            )
            or []
        )

    def assets(self):
        return self._get("/api/v1/private/account/assets") or []

    def available(self, currency="USDT"):
        """Saldo disponible de esa moneda en futuros (lo que se puede usar)."""
        for fila in self.assets():
            if str(fila.get("currency") or "").upper() == currency:
                return float(fila.get("availableBalance") or 0)
        return 0.0

    def saldo(self, currency="USDT"):
        """Saldo de la cuenta en futuros (`equity` = balance + PnL no realizado)."""
        for fila in self.assets():
            if str(fila.get("currency") or "").upper() == currency:
                return float(fila.get("equity") or fila.get("cashBalance") or 0)
        return 0.0

    def funding(self, symbol):
        """Tasa y hora del próximo funding del par (MEXC la da en fracción)."""
        filas = self._get("/api/v1/contract/funding_rate", {"symbol": symbol}) or []
        if isinstance(filas, dict):
            filas = [filas]
        for fila in filas:
            if fila.get("symbol") == symbol:
                return {
                    "tasa": float(fila.get("fundingRate") or 0),
                    "proxima": float(fila.get("nextSettleTime") or 0) / 1000,
                    "ciclo": int(fila.get("collectCycle") or 8),
                }
        return {}

    def open_market(
        self, symbol, side, notional_usdt, leverage, open_type=1, tp=None, sl=None, price=None
    ):
        """side: 'LONG' o 'SHORT'. notional_usdt = margen * apalancamiento.

        `price` vacio = a mercado (type 5) con el ultimo precio. Con precio =
        orden limite (type 1) a ese nivel; el tamano se convierte con ese precio,
        no con el de mercado.
        """
        if price:
            scale = int(self.contract(symbol).get("priceScale") or 0)
            px = round(float(price), scale)
            order_type = 1
        else:
            px = self.price(symbol)
            order_type = 5
        vol = self.size_to_vol(symbol, notional_usdt, px)
        payload = {
            "symbol": symbol,
            "price": px,
            "vol": vol,
            "side": 1 if side == "LONG" else 3,  # 1 abre long / 3 abre short
            "type": order_type,
            "openType": int(open_type),  # 1 aislado / 2 cruzado
            "leverage": int(leverage),
            "externalOid": uuid.uuid4().hex[:24],  # idempotencia: un reintento no duplica
        }
        if tp or sl:
            payload["priceProtect"] = 0
            payload["profitTrend"] = 1
            payload["lossTrend"] = 1
            if tp:
                payload["takeProfitPrice"] = float(tp)
            if sl:
                payload["stopLossPrice"] = float(sl)
        return self._post("/api/v1/private/order/create", payload), vol, px

    def close_position(self, pos, vol=None, price=None):
        """Cierra toda la posicion o una parte (`vol` en contratos).

        `price` vacio = a mercado (type 5). Con precio = orden limite (type 1)
        a ese nivel, redondeado a los decimales que admite el contrato.
        """
        hold = float(pos["holdVol"])
        vol = hold if vol is None else float(vol)
        if not 0 < vol <= hold:
            raise MexcError(f"Cantidad a cerrar invalida: {vol:g} de {hold:g} contratos.")
        if price:
            scale = int(self.contract(pos["symbol"]).get("priceScale") or 0)
            px = round(float(price), scale)
            order_type = 1
        else:
            px = self.price(pos["symbol"])
            order_type = 5
        # 4 cierra long / 2 cierra short
        side = 4 if int(pos["positionType"]) == 1 else 2
        payload = {
            "symbol": pos["symbol"],
            "price": px,
            "vol": vol,
            "side": side,
            "type": order_type,
            "openType": int(pos["openType"]),
            "externalOid": uuid.uuid4().hex[:24],
        }
        return self._post("/api/v1/private/order/create", payload)

    def close_all(self):
        return self._post("/api/v1/private/position/close_all", {})

    def reverse(self, pos):
        return self._post(
            "/api/v1/private/position/reverse",
            {
                "symbol": pos["symbol"],
                "positionId": int(pos["positionId"]),
                "vol": float(pos["holdVol"]),
            },
        )

    def tpsl_list(self):
        """TP/SL no finalizados, para cruzar por positionId."""
        return (
            self._get(
                "/api/v1/private/stoporder/list/orders",
                {"is_finished": 0, "page_num": 1, "page_size": 100},
            )
            or []
        )

    def tpsl_place(self, position_id, vol, tp=None, sl=None, simbolo=None):
        payload = {
            "positionId": int(position_id),
            "vol": float(vol),
            "lossTrend": 1,
            "profitTrend": 1,
            "priceProtect": 0,
        }
        if tp:
            payload["takeProfitPrice"] = float(tp)
            payload["takeProfitType"] = 0  # 0 = TP a mercado
        if sl:
            payload["stopLossPrice"] = float(sl)
            payload["stopLossType"] = 0  # 0 = SL a mercado
        return self._post("/api/v1/private/stoporder/place", payload)

    def tpsl_cancel(self, stop_id, simbolo=None):
        # el endpoint espera un array de objetos, no un objeto
        return self._post("/api/v1/private/stoporder/cancel", [{"stopPlanOrderId": int(stop_id)}])

    def change_margin(self, position_id, amount, kind="ADD", simbolo=None, side=None):
        return self._post(
            "/api/v1/private/position/change_margin",
            {
                "positionId": int(position_id),
                "amount": float(amount),
                "type": kind,
            },
        )

    def cancel(self, order_ids):
        """Cancela ordenes abiertas.

        El body es un **array de ids sueltos**, no `{"orderIds": [...]}`: con el
        objeto MEXC responde 600 Parameter error. Los ids van como texto para no
        perder precision en el JSON (orderId tiene 18 digitos).
        """
        ids = [str(i) for i in order_ids if i]
        if not ids:
            return []
        return self._post("/api/v1/private/order/cancel", ids)
