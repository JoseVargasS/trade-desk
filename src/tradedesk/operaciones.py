"""Empareja órdenes en **operaciones**: una fila por posición, no por orden.

Las dos APIs devuelven una fila por orden, así que un cierre parcial aparece como
varias filas sueltas y el PnL y las fees quedan separados. Acá se juntan:

- MEXC trae `positionId` en el historial: todo lo de una posición se agrupa por
  ese id (apertura + uno o varios cierres).
- Bitunix **no** trae `positionId` en el historial, solo `reduceOnly`. Se empareja
  con una cola FIFO por (exchange, símbolo, lado): cada cierre consume las
  aperturas anteriores en orden.

Módulo puro (sin red ni widgets): así se prueba sin abrir ventanas.
"""

TOL = 1e-9


def _ms(orden):
    """Hora de la orden en milisegundos (MEXC `createTime`, Bitunix `ctime`)."""
    for clave in ("createTime", "ctime", "updateTime", "mtime"):
        valor = orden.get(clave)
        if not valor:
            continue
        try:
            return int(float(valor))
        except (TypeError, ValueError):
            continue
    return 0


def _numero(orden, *claves):
    for clave in claves:
        valor = orden.get(clave)
        if valor in (None, ""):
            continue
        try:
            return float(valor)
        except (TypeError, ValueError):
            continue
    return 0.0


def _precio(orden):
    return _numero(orden, "dealAvgPrice", "avgPrice", "price")


def _cantidad(orden):
    return _numero(orden, "dealVol", "qty", "vol")


def _fee(orden):
    return _numero(orden, "totalFee", "fee")


def _pnl(orden):
    return _numero(orden, "profit", "realizedPNL", "realisedPNL")


def _exchange(orden):
    return str(orden.get("_exchange") or "mexc")


def lado_y_cierre(orden):
    """(lado, es_cierre) con la convención de cada broker.

    En MEXC `side` 1/3 abren long/short y 2/4 cierran short/long. En Bitunix el
    `side` es el de la **orden** (1 = BUY, 3 = SELL) y lo que distingue abrir de
    cerrar es `reduceOnly`; con `reduceOnly` ausente se usa el PnL realizado.
    """
    side = int(_numero(orden, "side"))
    if _exchange(orden) == "bitunix":
        cierra = orden.get("reduceOnly")
        if cierra is None:
            cierra = _pnl(orden) != 0
        if bool(cierra):
            return ("SHORT" if side == 1 else "LONG"), True
        return ("LONG" if side == 1 else "SHORT"), False
    return {1: ("LONG", False), 2: ("SHORT", True), 3: ("SHORT", False), 4: ("LONG", True)}.get(
        side, ("?", False)
    )


def _media_ponderada(pares):
    """Precio medio de [(precio, cantidad)]; 0 si no hay cantidad."""
    total = sum(cantidad for _precio_, cantidad in pares)
    if total <= 0:
        return 0.0
    return sum(precio * cantidad for precio, cantidad in pares) / total


def _fila(base, lado, qty, entrada, salida, pnl, fee, apertura, cierre, abierta, cerrada, clave=""):
    if cerrada <= TOL:
        estado = "Abierta"
    elif cerrada >= qty - max(TOL, qty * 1e-9):
        estado = "Cerrada"
    else:
        estado = "Parcial"
    return {
        "symbol": base.get("symbol") or "",
        "_exchange": _exchange(base),
        "lado": lado,
        "qty": qty,
        "entrada": entrada,
        "salida": salida,
        "pnl": pnl,
        "fee": fee,
        "apertura": apertura,
        "cierre": cierre,
        "abierta": abierta,
        "cerrada": cerrada,
        "estado": estado,
        "_clave": clave,
        "_orden": apertura or cierre,
    }


def _fila_de_grupo(ordenes, clave):
    """Una posición de MEXC: aperturas y cierres comparten `positionId`."""
    ordenadas = sorted(ordenes, key=_ms)
    aperturas = [orden for orden in ordenadas if not lado_y_cierre(orden)[1]]
    cierres = [orden for orden in ordenadas if lado_y_cierre(orden)[1]]
    primera = (aperturas or cierres or ordenadas)[0]
    lado = lado_y_cierre(primera)[0]
    qty = sum(_cantidad(orden) for orden in aperturas) or sum(_cantidad(orden) for orden in cierres)
    abierta = sum(_cantidad(orden) for orden in aperturas)
    cerrada = sum(_cantidad(orden) for orden in cierres)
    apertura = _ms(aperturas[0]) if aperturas else _ms(cierres[0])
    cierre = _ms(cierres[-1]) if cierres else 0
    return _fila(
        primera,
        lado,
        qty,
        _media_ponderada([(_precio(orden), _cantidad(orden)) for orden in aperturas]),
        _media_ponderada([(_precio(orden), _cantidad(orden)) for orden in cierres]),
        sum(_pnl(orden) for orden in cierres),
        sum(_fee(orden) for orden in ordenadas),
        apertura,
        cierre,
        abierta,
        cerrada,
        clave,
    )


def _fila_de_lote(lote):
    cerrada = lote["cerrada"]
    salida = lote["salida"] / cerrada if cerrada > TOL else 0.0
    return _fila(
        lote,
        lote["lado"],
        lote["qty"],
        lote["entrada"],
        salida,
        lote["pnl"],
        lote["fee"],
        lote["apertura"],
        lote["cierre"],
        lote["qty"],
        cerrada,
        lote["clave"],
    )


def _filas_por_cola(ordenes):
    """Bitunix: empareja por (exchange, símbolo, lado) con una cola FIFO."""
    lotes = {}
    filas = []
    for orden in sorted(ordenes, key=_ms):
        lado, cierra = lado_y_cierre(orden)
        clave = (_exchange(orden), orden.get("symbol") or "", lado)
        cantidad = _cantidad(orden)
        if not cierra:
            lotes.setdefault(clave, []).append(
                {
                    "symbol": orden.get("symbol") or "",
                    "_exchange": _exchange(orden),
                    "lado": lado,
                    "clave": f"fifo|{_exchange(orden)}|{orden.get('symbol') or ''}|{lado}"
                    f"|{_ms(orden)}|{cantidad:g}",
                    "qty": cantidad,
                    "entrada": _precio(orden),
                    "apertura": _ms(orden),
                    "cierre": 0,
                    "salida": 0.0,
                    "cerrada": 0.0,
                    "pnl": 0.0,
                    "fee": _fee(orden),
                }
            )
            continue
        restante = cantidad
        pnl = _pnl(orden)
        fee = _fee(orden)
        for lote in lotes.get(clave, []):
            if restante <= TOL:
                break
            hueco = lote["qty"] - lote["cerrada"]
            if hueco <= TOL:
                continue
            toma = min(hueco, restante)
            parte = toma / cantidad if cantidad > TOL else 1.0
            lote["cerrada"] += toma
            lote["salida"] += toma * _precio(orden)
            lote["pnl"] += pnl * parte
            lote["fee"] += fee * parte
            lote["cierre"] = max(lote["cierre"], _ms(orden))
            restante -= toma
        if restante > TOL:
            # cierre de una posición abierta antes de la ventana del historial
            filas.append(
                _fila(
                    orden,
                    lado,
                    restante,
                    0.0,
                    _precio(orden),
                    pnl,
                    fee,
                    _ms(orden),
                    _ms(orden),
                    restante,
                    restante,
                    f"cierre|{_exchange(orden)}|{orden.get('symbol') or ''}|{_ms(orden)}"
                    f"|{lado}|{restante:g}",
                )
            )
    for grupo in lotes.values():
        for lote in grupo:
            filas.append(_fila_de_lote(lote))
    return filas


def operaciones(ordenes):
    """Agrupa las órdenes del historial en operaciones, de la más nueva a la más vieja."""
    grupos = {}
    sueltas = []
    for orden in ordenes or ():
        ident = orden.get("positionId")
        if ident:
            grupos.setdefault((_exchange(orden), str(ident)), []).append(orden)
        else:
            sueltas.append(orden)
    filas = [_fila_de_grupo(grupo, f"pos|{clave[0]}|{clave[1]}") for clave, grupo in grupos.items()]
    filas.extend(_filas_por_cola(sueltas))
    filas.sort(key=lambda fila: fila["_orden"], reverse=True)
    return filas
