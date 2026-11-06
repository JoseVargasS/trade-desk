"""Cliente de BingX (futuros USDT-M). Sin dependencias de la UI.

Firma y endpoints verificados contra la API real el 3-nov-2026 con el probe
`tools/probe_bingx.py`:

- Base `https://open-api.bingx.com`, **solo v2** (v1 responde `100400`).
- Firma: params ordenados + `timestamp` (ms) -> `HMAC-SHA256` en hex, que viaja
  como **parámetro** `signature`; la key va en la cabecera `X-BX-APIKEY`.
- Respuesta **HTTP 200 también con error**: el código de negocio va en `code`
  (`0` = bien) y el mensaje en `msg`.
- Símbolo con guion (`BTC-USDT`) y `quantity` en **monedas** (BTC step 0.0001),
  igual que Bitunix.
"""

import hashlib
import hmac
import json
import time

import httpx

BASE = "https://open-api.bingx.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class BingxError(Exception):
    """Error de negocio de BingX (viene con HTTP 200)."""


# ------------------------------------------------------------------ simbolos
def canonico(simbolo):
    """`BTC_USDT` / `BTCUSDT` -> `BTC-USDT`, que es lo que espera BingX."""
    texto = str(simbolo or "").upper().replace("-", "").replace("_", "")
    if texto.endswith("USDT"):
        return f"{texto[:-4]}-USDT"
    if texto.endswith("USDC"):
        return f"{texto[:-4]}-USDC"
    return texto


def display_name(simbolo):
    """`BTC-USDT` -> `BTCUSDT`, como se muestra en las tablas."""
    return canonico(simbolo).replace("-", "").replace("_", "")


# ------------------------------------------------------------------- utileria
def largo(valor):
    """Interpreta el lado: la vista manda "LONG"/"SHORT", no un booleano."""
    if isinstance(valor, str):
        return valor.strip().upper() in ("LONG", "BUY", "TRUE", "1")
    return bool(valor)


def _filas(datos):
    if datos is None:
        return []
    if isinstance(datos, list):
        return datos
    if isinstance(datos, dict):
        for clave in ("orders", "positions", "list", "rows", "data"):
            if isinstance(datos.get(clave), list):
                return datos[clave]
        return [datos]
    return []


def _numero(fila, *claves, defecto=0.0):
    for clave in claves:
        valor = fila.get(clave)
        if valor in (None, ""):
            continue
        try:
            return float(valor)
        except (TypeError, ValueError):
            continue
    return defecto


def _texto(fila, *claves, defecto=""):
    for clave in claves:
        valor = fila.get(clave)
        if valor not in (None, ""):
            return str(valor)
    return defecto


# ---------------------------------------------------------------- decoradores
def _apalancamiento(valor):
    """BingX manda el apalancamiento como `"10X"`; la app lo pinta con `int()`."""
    texto = str(valor if valor is not None else "").strip().upper().rstrip("X")
    try:
        return int(float(texto.replace(",", "")))
    except (TypeError, ValueError):
        return 0


def _lado(posicion):
    """(positionType, lado) con la convencion de la app: 1 long, 2 short."""
    side = _texto(posicion, "positionSide").upper()
    if side == "SHORT":
        return 2, "SHORT"
    if side == "LONG":
        return 1, "LONG"
    return (1, "LONG") if _numero(posicion, "positionAmt") >= 0 else (2, "SHORT")


def _tp_sl_de(posicion, condicionales):
    """TP/SL de una posicion: BingX no los pone en `positions`, vienen como
    ordenes condicionales del par (`TAKE_PROFIT_MARKET` / `STOP_MARKET`)."""
    tp = _numero(posicion.get("takeProfit") or {}, "price", "stopPrice")
    sl = _numero(posicion.get("stopLoss") or {}, "price", "stopPrice")
    if tp and sl:
        return tp, sl
    symbol = canonico(posicion.get("symbol"))
    lado = _texto(posicion, "positionSide").upper()
    for orden in condicionales or ():
        if canonico(orden.get("symbol")) != symbol:
            continue
        if lado and _texto(orden, "positionSide").upper() not in (lado, ""):
            continue
        tipo = _texto(orden, "type").upper()
        precio = _numero(orden, "stopPrice")
        if not precio:
            continue
        if "TAKE_PROFIT" in tipo and not tp:
            tp = precio
        elif "STOP" in tipo and not sl:
            sl = precio
    return tp, sl


def decorate_positions(bingx, posiciones, condicionales=(), comisiones=None):
    """Posiciones de BingX con la forma que pintan las tablas."""
    salida = []
    for posicion in posiciones or ():
        symbol = canonico(posicion.get("symbol"))
        contrato = bingx.contract(symbol)
        tipo, lado = _lado(posicion)
        cantidad = abs(_numero(posicion, "positionAmt", "positionAmount"))
        if cantidad <= 0:
            continue
        entrada = _numero(posicion, "avgPrice", "openPrice")
        tp, sl = _tp_sl_de(posicion, condicionales)
        salida.append(
            {
                **posicion,
                "symbol": display_name(symbol),
                "positionId": _texto(posicion, "positionId"),
                "positionType": tipo,
                "holdVol": cantidad,
                "holdAvgPrice": entrada,
                "unRealizedPnl": _numero(posicion, "unrealizedProfit", "unrealizedPnl"),
                "liquidatePrice": _numero(posicion, "liquidationPrice", "liqPrice"),
                "leverage": _apalancamiento(posicion.get("leverage")) or 1,
                "marginRatio": _numero(posicion, "riskRate", "marginRate"),
                "im": _numero(posicion, "margin", "isolatedMargin"),
                "totalFee": float((comisiones or {}).get(str(posicion.get("positionId")), 0.0)),
                "holdFee": 0.0,
                "lowSaveTotalFee": 0.0,
                "createTime": int(_numero(posicion, "updateTime", "createTime")),
                "_tp": tp,
                "_sl": sl,
                "_exchange": "bingx",
                "_contractSize": float(contrato.get("contractSize") or 1.0),
                "_priceScale": int(contrato.get("priceScale") or 2),
                "_qtyStep": float(contrato.get("minQty") or 0.0001),
                "_name": display_name(symbol),
                "_lado": lado,
            }
        )
    return salida


def decorate_orders(bingx, ordenes):
    """Órdenes de BingX con la forma que pinta la app (side 1/3 = abrir)."""
    salida = []
    for orden in ordenes or ():
        symbol = canonico(orden.get("symbol"))
        contrato = bingx.contract(symbol)
        tipo_orden = _texto(orden, "type").upper()
        precio_stop = _numero(orden, "stopPrice")
        side = _texto(orden, "side").upper()
        lado = _texto(orden, "positionSide").upper()
        largo = side == "BUY"
        abriendo = bool(orden.get("reduceOnly") is False or not orden.get("reduceOnly"))
        tipos = {("SHORT", True): 3, ("SHORT", False): 2, ("LONG", True): 1, ("LONG", False): 4}
        tipo = tipos[(lado if lado in ("SHORT", "LONG") else "LONG", abriendo)]
        cantidad = _numero(orden, "quantity", "origQty")
        llenado = _numero(orden, "executedQty", "cumQty")
        tp = _numero(orden, "takeProfitPrice", "tpPrice")
        sl = _numero(orden, "stopLossPrice", "slPrice")
        if "TAKE_PROFIT" in tipo_orden:
            tp = tp or precio_stop
        elif "STOP" in tipo_orden:
            sl = sl or precio_stop
        precio = _numero(orden, "price")
        if not precio and ("STOP" in tipo_orden or "TAKE_PROFIT" in tipo_orden):
            precio = precio_stop
        salida.append(
            {
                **orden,
                "symbol": display_name(symbol),
                "orderId": _texto(orden, "orderId"),
                "side": tipo,
                "vol": cantidad,
                "dealVol": llenado,
                "dealAvgPrice": _numero(orden, "avgPrice", "price"),
                "price": precio,
                "takeProfitPrice": tp,
                "stopLossPrice": sl,
                "profit": _numero(orden, "profit"),
                "totalFee": abs(_numero(orden, "commission", "fee")),
                "leverage": _apalancamiento(orden.get("leverage")),
                "state": 3 if _texto(orden, "status").upper() in ("FILLED",) else 1,
                "createTime": int(_numero(orden, "time", "createTime", "updateTime")),
                "_exchange": "bingx",
                "_contractSize": float(contrato.get("contractSize") or 1.0),
                "_priceScale": int(contrato.get("priceScale") or 2),
                "_name": display_name(symbol),
                "_largo": largo,
            }
        )
    return salida


def es_condicional(orden):
    """TP/SL condicional de BingX: visible y cancelable, no editable."""
    tipo = _texto(orden or {}, "type").upper()
    return (orden or {}).get("_exchange") == "bingx" and ("STOP" in tipo or "TAKE_PROFIT" in tipo)


# --------------------------------------------------------------------- cliente
class Bingx:
    def __init__(self, key="", secret="", timeout=15.0):
        self.key = key
        self.secret = secret
        self.timeout = timeout
        self._contratos = {}
        self._cliente = None

    # ------------------------------------------------------------- transporte
    def cliente(self):
        if self._cliente is None:
            # IPv4 forzada: las keys estan atadas a la IPv4 del usuario
            self._cliente = httpx.Client(
                timeout=self.timeout,
                # sin Content-Type: los POST van con params en la query y un
                # cuerpo vacio; con "application/json" BingX responde 109400
                headers={"User-Agent": UA},
                transport=httpx.HTTPTransport(local_address="0.0.0.0"),
            )
        return self._cliente

    def _firmar(self, params):
        """Params ordenados + timestamp -> HMAC-SHA256 hex, como `signature`."""
        limpio = {clave: valor for clave, valor in (params or {}).items() if valor is not None}
        orden = sorted((str(clave), str(valor)) for clave, valor in limpio.items())
        orden.append(("timestamp", str(int(time.time() * 1000))))
        consulta = "&".join(f"{clave}={valor}" for clave, valor in orden)
        firma = hmac.new(self.secret.encode(), consulta.encode(), hashlib.sha256).hexdigest()
        firmado = dict(orden)
        firmado["signature"] = firma
        return firmado

    def _leer(self, respuesta):
        try:
            datos = respuesta.json()
        except ValueError as exc:
            raise BingxError(f"respuesta ilegible ({respuesta.status_code})") from exc
        codigo = datos.get("code")
        if str(codigo) != "0":
            raise BingxError(f"{codigo} {datos.get('msg') or ''}".strip())
        return datos.get("data")

    def _get(self, ruta, params=None, firmado=True):
        enviar = self._firmar(params) if firmado else (params or {})
        cabeceras = {"X-BX-APIKEY": self.key} if firmado else {}
        return self._leer(self.cliente().get(BASE + ruta, params=enviar, headers=cabeceras))

    def _post(self, ruta, params=None):
        enviar = self._firmar(params)
        return self._leer(
            self.cliente().post(BASE + ruta, params=enviar, headers={"X-BX-APIKEY": self.key})
        )

    def _delete(self, ruta, params=None):
        enviar = self._firmar(params)
        return self._leer(
            self.cliente().delete(BASE + ruta, params=enviar, headers={"X-BX-APIKEY": self.key})
        )

    # ---------------------------------------------------------------- mercado
    def ticker(self, simbolo):
        symbol = canonico(simbolo)
        return self._get("/openApi/swap/v2/quote/ticker", {"symbol": symbol}, firmado=False) or {}

    def price(self, simbolo):
        return _numero(self.ticker(simbolo), "lastPrice", "price")

    def cambio(self, simbolo):
        dato = self.ticker(simbolo)
        ultimo = _numero(dato, "lastPrice")
        previo = _numero(dato, "openPrice") or ultimo
        if not ultimo or not previo:
            return 0.0
        return (ultimo - previo) / previo * 100

    def contracts(self):
        datos = self._get("/openApi/swap/v2/quote/contracts", firmado=False) or []
        return _filas(datos)

    def contract(self, simbolo):
        symbol = canonico(simbolo)
        if not self._contratos:
            for fila in self.contracts():
                clave = canonico(fila.get("symbol"))
                self._contratos[clave] = fila
        crudo = self._contratos.get(symbol) or {}
        return {
            **crudo,
            # `quantity` va en **monedas** (0,0388 = 0,0388 BTC), asi que el
            # tamano de contrato es 1. El `size` de BingX es el valor de un
            # contrato en monedas; usarlo aca multiplicaba el nocional y el
            # mark price por 10.000 (posicion en negativo y mark price absurdo).
            "contractSize": 1.0,
            "priceScale": int(_numero(crudo, "pricePrecision", defecto=2) or 2),
            "volUnit": 1,
            "minQty": _numero(crudo, "tradeMinQuantity", "tradeMinLimit", defecto=0.0001),
            "minNotional": _numero(crudo, "tradeMinUSDT", defecto=2.0),
            "takerFeeRate": _numero(crudo, "takerFeeRate", defecto=0.0005),
            "makerFeeRate": _numero(crudo, "makerFeeRate", defecto=0.0002),
        }

    # ---------------------------------------------------------------- cuenta
    def balance(self):
        """/user/balance devuelve `{"balance": {...}}`, no una lista."""
        datos = self._get("/openApi/swap/v2/user/balance") or {}
        if isinstance(datos, dict) and isinstance(datos.get("balance"), dict):
            return [datos["balance"]]
        return _filas(datos)

    def saldo(self, moneda="USDT"):
        """Saldo en vivo de la cuenta: `equity` = balance + PnL no realizado."""
        for fila in self.balance():
            if str(fila.get("asset") or fila.get("currency") or "").upper() == moneda:
                return _numero(fila, "equity", "balance")
        return 0.0

    def available(self, moneda="USDT"):
        for fila in self.balance():
            if str(fila.get("asset") or "").upper() == moneda:
                return _numero(fila, "availableMargin", "balance", "equity")
        return 0.0

    def comisiones(self, limite=100):
        """Comision ya pagada por posicion, sacada del historial.

        BingX no manda la fee en `/user/positions`, pero `allOrders` trae
        `commission` (negativo) y `positionID` en mayusculas, asi que se suma por
        posicion. Se cachea 2 s: el poller pide posiciones cada 3 s y el historial
        tarda unos segundos en indexar la orden de apertura.
        """
        ahora = time.time()
        cache = getattr(self, "_com_cache", None)
        if cache and ahora - cache[0] < 2:
            return cache[1]
        total = {}
        try:
            filas = _filas(self._get("/openApi/swap/v2/trade/allOrders", {"limit": int(limite)}))
        except Exception:
            filas = []
        for orden in filas:
            if _texto(orden, "status").upper() != "FILLED":
                continue
            ident = _texto(orden, "positionID", "positionId")
            comision = abs(_numero(orden, "commission", "fee"))
            if not ident or not comision:
                continue
            total[ident] = total.get(ident, 0.0) + comision
        self._com_cache = (ahora, total)
        return total

    def positions(self):
        return _filas(self._get("/openApi/swap/v2/user/positions") or [])

    def open_orders(self, simbolo=None):
        params = {"symbol": canonico(simbolo)} if simbolo else {}
        return _filas(self._get("/openApi/swap/v2/trade/openOrders", params) or [])

    def history(self, limite=50, salto=0):
        """Historial paginado a mano: BingX no tiene `page`, se pide de más y se corta."""
        datos = self._get(
            "/openApi/swap/v2/trade/allOrders", {"limit": int(limite) + int(salto or 0)}
        )
        filas = _filas(datos)
        if salto:
            filas = filas[int(salto) :]
        return decorate_orders(self, filas)

    # ---------------------------------------------------------------- tamaños
    def _texto_qty(self, simbolo, qty):
        contrato = self.contract(simbolo)
        decimales = 0
        paso = float(contrato.get("minQty") or 0.0001)
        while paso < 1 and decimales < 8:
            paso *= 10
            decimales += 1
        return f"{qty:.{decimales}f}".rstrip("0").rstrip(".") or "0"

    def size_to_qty(self, simbolo, nocional, precio):
        """USDT -> monedas, con floor al step del par (nunca se pasa de lo pedido)."""
        contrato = self.contract(simbolo)
        paso = float(contrato.get("minQty") or 0.0001) or 0.0001
        if not precio:
            return 0.0
        bruto = float(nocional) / float(precio)
        pasos = int(bruto / paso)
        return round(pasos * paso, 8)

    def qty_to_usdt(self, simbolo, qty, precio):
        return float(qty) * float(precio)

    def size_to_vol(self, simbolo, nocional_usdt, price, contract=None):
        return self.size_to_qty(simbolo, nocional_usdt, price)

    def vol_to_usdt(self, simbolo, vol, price):
        return self.qty_to_usdt(simbolo, vol, price)

    # ------------------------------------------------------------------ ordenes
    def change_leverage(self, simbolo, leverage, lado="LONG"):
        symbol = canonico(simbolo)
        return self._post(
            "/openApi/swap/v2/trade/leverage",
            {"symbol": symbol, "side": str(lado).upper(), "leverage": int(leverage)},
        )

    def _tp_sl(self, tp, sl, lado):
        """TP/SL como JSON en la orden, alineado con el lado de la posición."""
        partes = {}
        if tp:
            partes["takeProfit"] = _json_tp_sl("TAKE_PROFIT_MARKET", tp)
        if sl:
            partes["stopLoss"] = _json_tp_sl("STOP_MARKET", sl)
        return partes

    def open_market(self, simbolo, long_, nocional, leverage, tipo, tp=None, sl=None, precio=None):
        """Abre a mercado o limite. `tipo` es 1 (mercado) o 2 (limite), como MEXC."""
        symbol = canonico(simbolo)
        es_largo = largo(long_)
        lado = "LONG" if es_largo else "SHORT"
        precio_ref = float(precio or 0) or self.price(symbol)
        qty = self.size_to_qty(symbol, nocional, precio_ref)
        if qty <= 0:
            raise BingxError(
                f"{display_name(symbol)}: el tamaño no llega al minimo "
                f"({self.contract(symbol).get('minQty')} monedas)"
            )
        self.change_leverage(symbol, leverage, lado)
        params = {
            "symbol": symbol,
            "side": "BUY" if es_largo else "SELL",
            "positionSide": lado,
            "type": "LIMIT" if int(tipo or 1) == 2 else "MARKET",
            "quantity": self._texto_qty(symbol, qty),
        }
        if int(tipo or 1) == 2:
            params["price"] = _texto_precio(precio)
        params.update(self._tp_sl(tp, sl, lado))
        datos = self._post("/openApi/swap/v2/trade/order", params) or {}
        return datos, qty, precio_ref

    def close_position(self, pos, vol=None, price=None):
        """Cierra con una orden al lado contrario, sin `reduceOnly` en HEDGE.

        BingX v2 **no tiene** `closePosition` (responde `100400 this api is not
        exist`). En **HEDGE** el lado de la posición (`positionSide`) ya identifica
        qué se cierra y mandar `reduceOnly` da `109400 In the Hedge mode, the
        'ReduceOnly' field can not be filled`. En one-way hace falta al revés, así
        que se reintenta con `reduceOnly` sólo si la API lo pide.
        """
        symbol = canonico(pos.get("symbol"))
        cantidad = float(pos.get("holdVol") or 0)
        qty = float(vol or cantidad)
        lado = "LONG" if int(pos.get("positionType") or 1) == 1 else "SHORT"
        params = {
            "symbol": symbol,
            "side": "SELL" if lado == "LONG" else "BUY",
            "positionSide": lado,
            "type": "LIMIT" if price else "MARKET",
            "quantity": self._texto_qty(symbol, qty),
        }
        if price:
            params["price"] = _texto_precio(price)
        try:
            return self._post("/openApi/swap/v2/trade/order", params)
        except BingxError as exc:
            if "educe" not in str(exc):
                raise
            return self._post("/openApi/swap/v2/trade/order", {**params, "reduceOnly": "true"})

    def close_all(self, simbolo=None):
        salida = []
        for posicion in decorate_positions(self, self.positions()):
            if simbolo and canonico(simbolo) != canonico(posicion.get("symbol")):
                continue
            salida.append(self.close_position(posicion))
        return salida

    def reverse(self, pos):
        """Cierra a mercado y abre la contraria con el mismo tamaño."""
        symbol = canonico(pos.get("symbol"))
        lado = int(pos.get("positionType") or 1)
        cantidad = float(pos.get("holdVol") or 0)
        # 1 % de margen: con el nocional justo, un tick de mas deja el floor en 0
        # y el reverse abre nada despues de haber cerrado
        entrada = float(pos.get("holdAvgPrice") or 0) or self.price(symbol)
        importe = self.qty_to_usdt(symbol, cantidad, entrada) * 1.01
        self.close_position(pos)
        self._esperar_sin_posicion(symbol)
        return self.open_market(symbol, lado != 1, importe, int(pos.get("leverage") or 1), 1)

    def _esperar_sin_posicion(self, simbolo, timeout=4.0):
        limite = time.time() + timeout
        while time.time() < limite:
            if not any(
                canonico(fila.get("symbol")) == canonico(simbolo)
                for fila in self.positions()
                if abs(_numero(fila, "positionAmt")) > 0
            ):
                return True
            time.sleep(0.25)
        return False

    def cancel(self, order_ids):
        """Cancela por id. BingX exige el símbolo, así que se busca en las vivas."""
        salida = []
        vivas = None
        for orden in order_ids if isinstance(order_ids, (list, tuple)) else [order_ids]:
            if isinstance(orden, dict):
                params = {
                    "symbol": canonico(orden.get("symbol")),
                    "orderId": _texto(orden, "orderId", "id"),
                }
            else:
                if vivas is None:
                    vivas = self.open_orders()
                symbol = ""
                for fila in vivas:
                    if _texto(fila, "orderId", "id") == str(orden):
                        symbol = canonico(fila.get("symbol"))
                        break
                if not symbol:
                    raise BingxError(f"BingX: no encontre la orden {orden} para cancelar")
                params = {"symbol": symbol, "orderId": str(orden)}
            salida.append(self._delete("/openApi/swap/v2/trade/order", params))
        return salida

    def cancel_all(self, simbolo=None):
        """BingX cancela por simbolo; se recorre cada par con ordenes vivas."""
        pares = (
            {canonico(simbolo)}
            if simbolo
            else {canonico(orden.get("symbol")) for orden in self.open_orders()}
        )
        salida = []
        for par in pares:
            if par:
                salida.append(self._delete("/openApi/swap/v2/trade/order", {"symbol": par}))
        return salida

    def change_margin(self, position_id, amount, kind="ADD", simbolo=None, side=None):
        symbol = canonico(simbolo)
        params = {
            "symbol": symbol,
            "amount": abs(float(amount)),
            "type": 1 if str(kind).upper().startswith("ADD") else 2,
            "positionSide": (side or "LONG").upper(),
        }
        return self._post("/openApi/swap/v2/trade/positionMargin", params)

    def _condicionales(self, simbolo, lado=""):
        """Ordenes TP/SL vivas de ese par (y lado)."""
        symbol = canonico(simbolo)
        salida = []
        for orden in self.open_orders():
            if canonico(orden.get("symbol")) != symbol:
                continue
            tipo = _texto(orden, "type").upper()
            if "TAKE_PROFIT" not in tipo and "STOP" not in tipo:
                continue
            if lado and _texto(orden, "positionSide").upper() not in (lado, ""):
                continue
            salida.append(orden)
        return salida

    def tpsl_place(self, position_id, vol=None, tp=None, sl=None, simbolo=None):
        """TP/SL de una posición abierta: dos condicionales con `quantity`.

        `closePosition` no sirve (pide `quantity` o `stopPrice`): se manda la
        cantidad de la posición. Primero se cancelan las condicionales viejas.
        """
        symbol = canonico(simbolo)
        posicion = None
        for fila in self.positions():
            if _texto(fila, "positionId") == str(position_id):
                posicion = fila
                break
        if posicion is None:
            raise BingxError("BingX: no encontre la posicion para el TP/SL")
        lado = "LONG" if _texto(posicion, "positionSide").upper() != "SHORT" else "SHORT"
        cantidad = abs(_numero(posicion, "positionAmt")) or float(vol or 0)
        for vieja in self._condicionales(symbol, lado):
            try:
                self.cancel([vieja])
            except Exception as exc:
                raise BingxError(
                    f"BingX: no se pudo cancelar una condicional TP/SL anterior: {exc}"
                ) from exc
        salida = []
        for tipo, precio in (("TAKE_PROFIT_MARKET", tp), ("STOP_MARKET", sl)):
            if not precio:
                continue
            salida.append(
                self._post(
                    "/openApi/swap/v2/trade/order",
                    {
                        "symbol": symbol,
                        "side": "SELL" if lado == "LONG" else "BUY",
                        "positionSide": lado,
                        "type": tipo,
                        "stopPrice": _texto_precio(precio),
                        # `closePosition` cierra la posicion ENTERA al dispararse
                        # (en la app de BingX sale como "Posicion completa").
                        # La doc exige igual `quantity` y `stopPrice`, y prohibe
                        # combinarlo con `reduceOnly`.
                        "quantity": self._texto_qty(symbol, cantidad),
                        "closePosition": "true",
                        "workingType": "MARK_PRICE",
                    },
                )
            )
        return salida

    def tpsl_cancel(self, stop_id, simbolo=None, posicion=None):
        """Cancela las condicionales vivas de ese par."""
        salida = []
        for orden in self._condicionales(simbolo):
            salida.append(self.cancel([orden]))
        return salida

    def modify_order(self, orden, form):
        """BingX no edita una orden viva: se cancela y se reenvía."""
        self.cancel(orden)
        return self.open_market(
            orden.get("symbol"),
            form.get("lado") or (int(orden.get("side") or 1) in (1, 4)),
            float(form.get("nocional") or 0),
            int(form.get("lev") or 1),
            2,
            form.get("tp"),
            form.get("sl"),
            form.get("precio"),
        )

    def funding(self, simbolo):
        """BingX no da la tasa en un endpoint público simple: queda vacío."""
        return {}


def _texto_precio(precio):
    """Precio sin ceros de mas ni notacion cientifica."""
    if precio in (None, ""):
        return "0"
    numero = float(precio)
    if numero == int(numero):
        return str(int(numero))
    return f"{numero:.10f}".rstrip("0").rstrip(".")


def _json_tp_sl(tipo, precio):
    """TP/SL de BingX: JSON compacto dentro del parámetro de la orden."""
    return json.dumps(
        {"type": tipo, "stopPrice": float(precio), "workingType": "MARK_PRICE"},
        separators=(",", ":"),
    )
