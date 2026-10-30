"""Self-check de la logica pura: busqueda, formatos, fee y liquidacion.

No abre ventana ni toca la API privada. Corre con: python selftest.py
"""
import io
import re

import theme as t
from mexc import Mexc
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
    assert t.fmt_price(78632.6) == "78,632.6"
    assert t.fmt_price(0.07745) == "0.07745"
    print("formatos ok")

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

    print("SELFTEST OK")


if __name__ == "__main__":
    main()
