"""Parseo puro de los formularios: tarjeta de par y editor de orden.

Sin widgets: así la validación se prueba sin abrir ventanas y la vista solo
pasa los textos tal cual los escribió el usuario.
"""


def _numero(texto):
    texto = "" if texto is None else str(texto).strip()
    return float(texto.replace(",", ""))


def form_tarjeta(symbol, palanca, tamano, tp, sl, margin_mode, size_mode, limite):
    """Valores ya parseados de una tarjeta, o None si algo no es número."""
    try:
        lev = int(_numero(palanca or 0))
        size = _numero(tamano)
    except ValueError:
        return None
    if lev < 1 or size <= 0:
        return None
    tp = (tp or "").strip()
    sl = (sl or "").strip()
    for valor in (tp, sl):
        if valor:
            try:
                _numero(valor)
            except ValueError:
                return None
    notional = size * lev if size_mode == "Margen" else size
    return {
        "symbol": symbol,
        "lev": lev,
        "size": size,
        "notional": notional,
        "tp": _numero(tp) if tp else None,
        "sl": _numero(sl) if sl else None,
        "open_type": 1 if margin_mode == "Aislado" else 2,
        "margin_mode": margin_mode,
        "size_mode": size_mode,
        "price": limite or None,
    }


def valores_orden(lev, margen, precio, tp, sl):
    """(lev, margen, precio, tp, sl) del editor de orden, o None si no sirve."""
    try:
        niveles = (
            _numero(lev),
            _numero(margen),
            _numero(precio),
            _numero(tp or 0),
            _numero(sl or 0),
        )
    except ValueError:
        return None
    if niveles[0] < 1 or niveles[1] <= 0 or niveles[2] <= 0 or niveles[3] < 0 or niveles[4] < 0:
        return None
    return int(niveles[0]), niveles[1], niveles[2], niveles[3], niveles[4]
