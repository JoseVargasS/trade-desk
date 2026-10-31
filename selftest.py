"""Self-check de la logica pura: busqueda, formatos, fee y liquidacion.

No abre ventana ni toca la API privada. Corre con: python selftest.py
"""
import io
import re

import theme as t
from mexc import Mexc, MexcError, close_vol, display_name, plan_tp_sl
from search import filter_markets

# un worker corre en un hilo: si toca un widget, Tk se bloquea varios segundos
WIDGET_CALL = re.compile(r"\b(card|self\.(?:lbl_|btn_|table|tree))\w*\.(configure|set_\w+|insert|delete|config)\(")


def check_workers_do_not_touch_widgets():
    for name in ("app.py", "actions.py"):
        current = None
        for number, line in enumerate(io.open(name, encoding="utf-8"), 1):
            found = re.search(r"def (_\w*worker)\(", line)
            if found:
                current = found.group(1)
            elif current and re.match(r"\s+def ", line):
                current = None
            if current and WIDGET_CALL.search(line):
                raise AssertionError(
                    f"{name}:{number} {current} toca widgets desde un hilo: {line.strip()}")


def check_close_orders():
    """Cierre total, parcial y limite: el payload que saldria hacia MEXC."""
    mx = Mexc()
    mx.price = lambda symbol: 100.0
    mx.contract = lambda symbol: {"priceScale": 2}
    sent = {}
    mx._post = lambda path, payload: sent.update(path=path, **payload)

    pos = {"symbol": "XAU_USDT", "positionType": 2, "openType": 1, "holdVol": 22}
    mx.close_position(pos)
    assert sent["type"] == 5 and sent["vol"] == 22 and sent["price"] == 100.0, sent
    assert sent["side"] == 2 and sent["openType"] == 1, sent          # short -> side 2

    mx.close_position(pos, 7, 2246.394)
    assert sent["type"] == 1 and sent["vol"] == 7, sent               # limite
    assert sent["price"] == 2246.39, sent                             # precioScale = 2

    mx.close_position(dict(pos, positionType=1, openType=2), 5)
    assert sent["side"] == 4 and sent["type"] == 5 and sent["openType"] == 2, sent

    for bad in (0, 23, -1):
        try:
            mx.close_position(pos, bad)
        except MexcError:
            pass
        else:
            raise AssertionError(f"deberia rechazar vol={bad}")


def main():
    check_workers_do_not_touch_widgets()
    print("workers sin widgets ok")

    # ---------------------------------------------------------- formatos
    assert t.fmt_pnl(12.40213) == "+12.4021", t.fmt_pnl(12.40213)
    assert t.fmt_pnl(-3.15) == "-3.1500", t.fmt_pnl(-3.15)
    assert t.fmt_fee(0.199533256) == "0.1995", t.fmt_fee(0.199533256)
    assert t.fmt_usdt(502.81124404) == "502.81"
    assert t.fmt_qty(127.0) == "127"
    assert t.fmt_pct(-3.92) == "-3.92%"
    assert t.fmt_share(0.2) == "0.20%"
    assert t.fmt_share(0.002) == "<0.01%"
    assert t.fmt_share(0) == "0.00%"
    assert t.fmt_price(78632.6) == "78,632.6"
    assert t.fmt_price(0.07745) == "0.07745"
    print("formatos ok")

    # ------------------------------------------------- nombre del par y TP/SL
    assert display_name({"baseCoinName": "GOLD(XAU)", "quoteCoinName": "USDT"}) \
        == "GOLD(XAU)USDT"
    assert display_name({"symbol": "BTC_USDT",
                         "displayNameEn": "BTC_USDT PERPETUAL"}) == "BTCUSDT"
    assert display_name({}) == ""

    # LONG: TP arriba, SL abajo. Contra el precio actual, no contra la entrada.
    assert plan_tp_sl(True, 100, 110, 90) == (110.0, 90.0, [])
    # un SL del lado de la ganancia no existe para MEXC: es un TP
    tp, sl, avisos = plan_tp_sl(True, 100, None, 105)
    assert (tp, sl) == (105.0, None) and avisos, (tp, sl, avisos)
    # con el TP ya ocupado no se puede representar
    for args in ((True, 100, 110, 105), (True, 100, 95, 90), (True, 100, 100, None),
                 (False, 100, 110, None), (False, 100, 95, 98)):
        try:
            plan_tp_sl(*args)
        except MexcError:
            pass
        else:
            raise AssertionError(f"deberia rechazar {args}")
    # SHORT: espejo exacto
    assert plan_tp_sl(False, 100, 90, 110) == (90.0, 110.0, [])
    tp, sl, avisos = plan_tp_sl(False, 100, None, 95)
    assert (tp, sl) == (95.0, None) and avisos
    print("nombre de par y tp/sl ok")

    # ---------------------------------------------------------- busqueda
    markets = {
        "BTC_USDT": {"symbol": "BTC_USDT", "baseCoin": "BTC", "quoteCoin": "USDT",
                     "contractSize": 0.0001, "maxLeverage": 500},
        "ETH_USDT": {"symbol": "ETH_USDT", "baseCoin": "ETH", "quoteCoin": "USDT",
                     "contractSize": 0.01, "maxLeverage": 400},
        "SOL_USDT": {"symbol": "SOL_USDT", "baseCoin": "SOL", "quoteCoin": "USDT",
                     "contractSize": 0.1, "maxLeverage": 100},
        "SOLV_USDT": {"symbol": "SOLV_USDT", "baseCoin": "SOLV", "quoteCoin": "USDT",
                      "contractSize": 1, "maxLeverage": 50},
        "BTC_USDC": {"symbol": "BTC_USDC", "baseCoin": "BTC", "quoteCoin": "USDC",
                     "contractSize": 0.0001, "maxLeverage": 100},
    }

    vacio = filter_markets(markets, "")
    assert vacio[0]["symbol"] == "BTC_USDT", "los favoritos van primero"
    assert vacio[1]["symbol"] == "ETH_USDT"

    sol = [c["symbol"] for c in filter_markets(markets, "sol")]
    assert sol[0] in ("SOL_USDT", "SOLV_USDT"), sol
    assert set(sol) == {"SOL_USDT", "SOLV_USDT"}, sol

    btc = [c["symbol"] for c in filter_markets(markets, "btc")]
    assert btc[0] == "BTC_USDT", f"prefijo exacto y USDT primero: {btc}"
    assert btc[1] == "BTC_USDC", f"USDC despues de USDT: {btc}"

    assert filter_markets(markets, "sol/usdt")[0]["symbol"] == "SOL_USDT"
    assert filter_markets(markets, "  eth  ")[0]["symbol"] == "ETH_USDT"
    assert filter_markets(markets, "zzzz") == []
    print("busqueda ok")

    # ---------------------------------------------------------- fee y liq
    mx = Mexc()
    px = mx.price("BTC_USDT")
    vol = mx.size_to_vol("BTC_USDT", 1000, px)
    real = mx.vol_to_usdt("BTC_USDT", vol, px)
    assert 0 < real <= 1000, real
    assert vol == int(vol), "el step de BTC es entero"

    fee = mx.est_fee("BTC_USDT", real)
    rate = float(mx.contract("BTC_USDT")["takerFeeRate"])
    assert abs(fee - real * rate) < 1e-9, (fee, real * rate)
    assert fee < 1, f"la fee de 1000 USDT no puede ser {fee}"

    long_liq = mx.est_liq("BTC_USDT", px, 10, "LONG")
    short_liq = mx.est_liq("BTC_USDT", px, 10, "SHORT")
    assert 0 < long_liq < px < short_liq, (long_liq, px, short_liq)
    assert abs((px - long_liq) / px - 0.099) < 0.01, "long liq ~ -10%"
    print(f"fee ok ({fee:.4f}) · liq ok ({long_liq:,.1f} / {short_liq:,.1f})")

    # ------------------------------------------------- cierre total / parcial
    assert close_vol(127, 100) == 127, "100% cierra la posicion exacta"
    assert close_vol(127, None) == 127, "sin tocar nada = 100%"
    assert close_vol(127, 50) == 63
    assert close_vol(127, 33) == 41
    assert close_vol(3, 10) == 0, "menos de un contrato: lo rechaza la accion"
    assert close_vol(127, 150) == 127, "no se puede cerrar de mas"
    check_close_orders()
    print("cierre total / parcial / limite ok")

    print("SELFTEST OK")


if __name__ == "__main__":
    main()
