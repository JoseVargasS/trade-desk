"""Filtro puro del buscador de pares: lo comparten la ventana Tk y la de Qt.

Sin widgets y sin red: solo el catalogo que ya se pidio y el texto del usuario.
"""

from . import theme as t
from .mexc import display_name

FAVORITOS = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT"]


def _is_usdt(contract):
    return (contract.get("quoteCoin") or "USDT").upper() == "USDT"


def contract_line(c):
    # mismo nombre que muestra MEXC, no el simbolo crudo de la API
    return (
        f"{display_name(c)}    {c.get('maxLeverage', '')}x    "
        f"1 = {t.fmt_qty(c.get('contractSize'))} {c.get('baseCoin', '')}"
    )


def filter_markets(markets, text, limit=60):
    """USDT primero, luego prefijo exacto, luego 'contiene'."""
    query = (text or "").strip().upper().replace("-", "_").replace("/", "_")
    items = list(markets.values())

    if not query:
        top = [markets[s] for s in FAVORITOS if s in markets]
        seen = {c["symbol"] for c in top}
        rest = [c for c in items if c["symbol"] not in seen and _is_usdt(c)]
        return top + rest[:limit]

    starts, contains = [], []
    for c in items:
        symbol = c["symbol"]
        base = (c.get("baseCoin") or "").upper()
        if symbol.startswith(query) or base == query:
            starts.append(c)
        elif query in symbol or query in display_name(c).upper():
            # se busca tambien por el nombre de MEXC: "gold" encuentra GOLD(XAU)USDT
            contains.append(c)

    # orden estable: los pares USDT primero dentro de cada grupo
    starts.sort(key=lambda c: 0 if _is_usdt(c) else 1)
    contains.sort(key=lambda c: 0 if _is_usdt(c) else 1)
    return (starts + contains)[:limit]
