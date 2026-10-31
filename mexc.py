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
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

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
    5003: ("Precio de TP/SL invalido: MEXC exige que el TP este del lado de la ganancia "
           "y el SL del lado de la perdida, tomando como referencia el precio actual."),
    5004: ("La cantidad de la orden mas el TP/SL vigente supera lo cerrable. "
           "La orden anterior se cancela de forma asincrona: reintenta en un segundo."),
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
            f"precio actual ({fmt_plain(price)}): si ya esta alcanzado, MEXC lo rechaza.")

    if sl is not None and en_ganancia(sl):
        if tp is None:
            avisos.append(
                f"El SL {fmt_plain(sl)} estaba del lado de la ganancia: MEXC solo acepta "
                f"ese nivel como take profit, asi que se guardo como TP "
                f"(cierra en {fmt_plain(sl)}). La posicion queda SIN stop loss.")
            tp, sl = sl, None
        else:
            raise MexcError(
                f"El TP ({fmt_plain(tp)}) y el SL ({fmt_plain(sl)}) quedan los dos del "
                f"lado de la ganancia del precio actual ({fmt_plain(price)}). MEXC solo "
                f"admite un nivel ahi: deja el SL {lado_perdida} de {fmt_plain(price)}.")

    return tp, sl, avisos


def fmt_plain(value):
    """Precio para mensajes de error; los widgets usan theme.fmt_price."""
    return f"{float(value):,.2f}"


class MexcError(Exception):
    pass


class Mexc:
    def __init__(self, api_key="", secret=""):
        self.api_key = api_key
        self.secret = secret
        # cliente persistente: reusa la conexion TLS (~20ms por orden en vez de ~45ms)
        self.http = httpx.Client(
            base_url=BASE,
            timeout=8.0,
            headers={"User-Agent": UA, "Content-Type": "application/json"},
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
                raise MexcError(f"HTTP {resp.status_code}: peticion bloqueada (WAF o limite). Reintenta en unos segundos.") from None
            raise MexcError(f"HTTP {resp.status_code}: respuesta no JSON") from None
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
            data = self.http.get("/api/v1/contract/detail", params={"symbol": symbol}).json()["data"]
            self._contracts[symbol] = data
        return self._contracts[symbol]

    def cached_contract(self, symbol):
        """Contrato ya pedido (sin red). Sirve para pintar el nombre del par."""
        return self._contracts.get(symbol)

    def markets(self, force=False):
        """Todos los contratos operables por API, indexados por simbolo.

        No alimenta self._contracts: el catalogo trae tasas y precisiones que
        pueden diferir del endpoint individual, que es el que manda.
        """
        if self._markets is None or force:
            data = self.http.get("/api/v1/contract/detail").json()["data"]
            self._markets = {
                c["symbol"]: c for c in data
                if c.get("state") == 0 and c.get("apiAllowed")
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

    def size_to_vol(self, symbol, notional_usdt, price):
        """USDT nocionales -> contratos, respetando el step del contrato."""
        c = self.contract(symbol)
        size = float(c["contractSize"])
        step = float(c.get("volUnit") or 1)
        min_vol = float(c.get("minVol") or step)
        max_vol = float(c.get("maxVol") or 0)

        raw = notional_usdt / (price * size)
        vol = math.floor(raw / step) * step
        vol = round(vol, int(c.get("volScale") or 0))

        if vol < min_vol:
            minimo = min_vol * size * price
            raise MexcError(f"Tamano muy chico: {vol} contratos. Minimo {min_vol} = {minimo:.2f} USDT")
        if max_vol and vol > max_vol:
            raise MexcError(f"Tamano muy grande: {vol} > maximo {max_vol}")
        return vol

    def vol_to_usdt(self, symbol, vol, price):
        return float(vol) * float(self.contract(symbol)["contractSize"]) * price

    # --------------------------------------------------------------- privado
    def positions(self):
        return self._get("/api/v1/private/position/open_positions") or []

    def open_orders(self):
        return self._get("/api/v1/private/order/list/open_orders",
                         {"page_num": 1, "page_size": 20}) or []

    def history(self, size=50):
        return self._get("/api/v1/private/order/list/history_orders",
                         {"page_num": 1, "page_size": size}) or []

    def assets(self):
        return self._get("/api/v1/private/account/assets") or []

    def open_market(self, symbol, side, notional_usdt, leverage, open_type=1, tp=None, sl=None):
        """side: 'LONG' o 'SHORT'. notional_usdt = margen * apalancamiento."""
        px = self.price(symbol)
        vol = self.size_to_vol(symbol, notional_usdt, px)
        payload = {
            "symbol": symbol,
            "price": px,
            "vol": vol,
            "side": 1 if side == "LONG" else 3,   # 1 abre long / 3 abre short
            "type": 5,                             # 5 = mercado
            "openType": int(open_type),            # 1 aislado / 2 cruzado
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

    def close_position(self, pos):
        px = self.price(pos["symbol"])
        # 4 cierra long / 2 cierra short
        side = 4 if int(pos["positionType"]) == 1 else 2
        payload = {
            "symbol": pos["symbol"],
            "price": px,
            "vol": float(pos["holdVol"]),
            "side": side,
            "type": 5,
            "openType": int(pos["openType"]),
            "externalOid": uuid.uuid4().hex[:24],
        }
        return self._post("/api/v1/private/order/create", payload)

    def close_all(self):
        return self._post("/api/v1/private/position/close_all", {})

    def reverse(self, pos):
        return self._post("/api/v1/private/position/reverse", {
            "symbol": pos["symbol"],
            "positionId": int(pos["positionId"]),
            "vol": float(pos["holdVol"]),
        })

    def tpsl_list(self):
        """TP/SL no finalizados, para cruzar por positionId."""
        return self._get("/api/v1/private/stoporder/list/orders",
                         {"is_finished": 0, "page_num": 1, "page_size": 100}) or []

    def tpsl_place(self, position_id, vol, tp=None, sl=None):
        payload = {
            "positionId": int(position_id),
            "vol": float(vol),
            "lossTrend": 1,
            "profitTrend": 1,
            "priceProtect": 0,
        }
        if tp:
            payload["takeProfitPrice"] = float(tp)
            payload["takeProfitType"] = 0   # 0 = TP a mercado
        if sl:
            payload["stopLossPrice"] = float(sl)
            payload["stopLossType"] = 0     # 0 = SL a mercado
        return self._post("/api/v1/private/stoporder/place", payload)

    def tpsl_cancel(self, stop_id):
        # el endpoint espera un array de objetos, no un objeto
        return self._post("/api/v1/private/stoporder/cancel",
                          [{"stopPlanOrderId": int(stop_id)}])

    def change_margin(self, position_id, amount, kind="ADD"):
        return self._post("/api/v1/private/position/change_margin", {
            "positionId": int(position_id),
            "amount": float(amount),
            "type": kind,
        })

    def cancel(self, order_ids):
        return self._post("/api/v1/private/order/cancel", {"orderIds": [int(i) for i in order_ids]})


# ------------------------------------------------------------------ self-check
if __name__ == "__main__":
    m = Mexc()
    px = m.price("BTC_USDT")
    c = m.contract("BTC_USDT")
    print(f"BTC_USDT precio={px} contractSize={c['contractSize']} volUnit={c['volUnit']} minVol={c['minVol']}")

    # 1000 USDT nocionales deben dar el vol esperado, nunca mas
    vol = m.size_to_vol("BTC_USDT", 1000, px)
    real = m.vol_to_usdt("BTC_USDT", vol, px)
    assert 0 < real <= 1000, f"nocional {real} excede 1000"
    assert real > 1000 - m.vol_to_usdt("BTC_USDT", float(c["volUnit"]), px), "redondeo demasiado conservador"
    print(f"1000 USDT -> {vol} contratos = {real:.2f} USDT reales")

    # un tamano imposible debe fallar, no devolver 0 silencioso
    try:
        m.size_to_vol("BTC_USDT", 0.01, px)
        raise SystemExit("FALLO: tamano minimo no fue rechazado")
    except MexcError as e:
        print(f"rechazo correcto: {e}")

    print("OK")
