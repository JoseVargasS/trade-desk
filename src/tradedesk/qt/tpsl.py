"""Editor de TP/SL de una posición, con las dos líneas vivas del PnL."""

from .. import theme as t
from ..mexc import break_even_price, pnl_en_precio, precio_por_pnl
from .dialogos_base import _Formulario


def _lineas_pnl(pos, long_, tp, sl):
    """Lo que se gana o pierde si el TP/SL se ejecuta, en USDT y con color."""
    lineas = []
    for etiqueta_pnl, texto in (("TP", tp), ("SL", sl)):
        try:
            precio = float((texto or "").replace(",", "").strip())
        except ValueError:
            continue
        pnl = pnl_en_precio(pos, long_, precio)
        color = t.GREEN if pnl >= 0 else t.RED
        lineas.append(
            f"<span style='color:{color}'>{etiqueta_pnl} {t.fmt_price(precio)} → "
            f"<b>{t.fmt_pnl(pnl)} USDT</b></span>"
        )
    return "<br>".join(lineas) or "Escribe un precio para ver la ganancia o pérdida."


def editar_tpsl(parent, pos, long_, precio):
    """Lápiz de TP/SL: devuelve {'tp': texto, 'sl': texto} o None.

    Es el diálogo del lápiz de TP/SL: mismos campos, la línea viva con el PnL y
    el botón *Break-even* con `mexc.break_even_price`.
    """
    escala = int(pos.get("_priceScale") or 2)
    be, cubre = break_even_price(pos, long_)
    cabe = bool(precio and be and (precio > be if long_ else precio < be))
    texto_be = f"{be:.{escala}f}" if be else ""

    lado = ("SL debajo" if long_ else "SL arriba") if precio else "SL en contra"
    if be:
        nota = (
            f"Qty {t.fmt_qty(pos.get('holdVol'))} contratos · "
            f"precio actual {t.fmt_price(precio) if precio else '—'} ({lado})\n"
            f"Break-even {t.fmt_price_exact(be, escala)} → {t.fmt_pnl(cubre)} USDT "
            "(comision de entrada + salida + funding · neto 0)"
        )
        if not cabe:
            nota += (
                f"\nNecesita precio {'>' if long_ else '<'} "
                f"{t.fmt_price_exact(be, escala)} (ahora {t.fmt_price(precio)})"
            )
    else:
        nota = "Break-even no disponible: falta precio de entrada o tamaño"

    dialogo = _Formulario(
        parent,
        f"TP / SL · {pos.get('symbol')}",
        [
            ("tp", "Take profit", pos.get("_tp") or ""),
            ("tp_pct", "TP % del margen", ""),
            ("sl", "Stop loss", pos.get("_sl") or ""),
            ("sl_pct", "SL % del margen", ""),
        ],
        nota=nota + "\n\nEl % es sobre el margen (TP positivo, SL negativo):"
        " escribe el % y el precio se calcula.",
        extras=(("Break-even", lambda dlg: dlg.escribir("sl", texto_be), cabe),),
        resumen=lambda valores: _lineas_pnl(pos, long_, valores["tp"], valores["sl"]),
        traducir={
            "tp_pct": (
                "tp",
                lambda texto: precio_por_pnl(
                    pos.get("holdAvgPrice"), texto, pos.get("leverage"), long_, escala
                ),
            ),
            "sl_pct": (
                "sl",
                lambda texto: precio_por_pnl(
                    pos.get("holdAvgPrice"), texto, pos.get("leverage"), long_, escala
                ),
            ),
        },
    )
    dialogo.exec()
    return dialogo.resultado
