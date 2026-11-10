"""Símbolo, utilería y filas de BingX en la forma que las pinta la mesa.

Vive aparte de `bingx.py` porque ese módulo ya está en el tope de líneas: aquí
van los helpers compartidos y los adaptadores de posiciones, órdenes y
condicionales. No importa al cliente: solo recibe el `bingx` como argumento.
"""


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
        largo_ = side == "BUY"
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
                "_largo": largo_,
            }
        )
    return salida


def es_condicional(orden):
    """TP/SL condicional de BingX: visible y cancelable, no editable."""
    tipo = _texto(orden or {}, "type").upper()
    return (orden or {}).get("_exchange") == "bingx" and ("STOP" in tipo or "TAKE_PROFIT" in tipo)
