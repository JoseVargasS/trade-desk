"""Buscador de pares: filtro puro, USDT primero."""

import pytest

from tradedesk.search import filter_markets

MARKETS = {
    "BTC_USDT": {
        "symbol": "BTC_USDT",
        "baseCoin": "BTC",
        "quoteCoin": "USDT",
        "contractSize": 0.0001,
        "maxLeverage": 500,
    },
    "ETH_USDT": {
        "symbol": "ETH_USDT",
        "baseCoin": "ETH",
        "quoteCoin": "USDT",
        "contractSize": 0.01,
        "maxLeverage": 400,
    },
    "SOL_USDT": {
        "symbol": "SOL_USDT",
        "baseCoin": "SOL",
        "quoteCoin": "USDT",
        "contractSize": 0.1,
        "maxLeverage": 100,
    },
    "SOLV_USDT": {
        "symbol": "SOLV_USDT",
        "baseCoin": "SOLV",
        "quoteCoin": "USDT",
        "contractSize": 1,
        "maxLeverage": 50,
    },
    "BTC_USDC": {
        "symbol": "BTC_USDC",
        "baseCoin": "BTC",
        "quoteCoin": "USDC",
        "contractSize": 0.0001,
        "maxLeverage": 100,
    },
}


def test_vacio_muestra_favoritos_y_luego_usdt():
    vacio = filter_markets(MARKETS, "")
    assert vacio[0]["symbol"] == "BTC_USDT"
    assert vacio[1]["symbol"] == "ETH_USDT"
    assert all(c["symbol"].endswith("_USDT") for c in vacio[2:])


def test_prefijo_exacto_y_usdt_primero():
    btc = [c["symbol"] for c in filter_markets(MARKETS, "btc")]
    assert btc[0] == "BTC_USDT", f"prefijo exacto y USDT primero: {btc}"
    assert btc[1] == "BTC_USDC", f"USDC despues de USDT: {btc}"


def test_contiene_y_normalizacion():
    sol = [c["symbol"] for c in filter_markets(MARKETS, "sol")]
    assert set(sol) == {"SOL_USDT", "SOLV_USDT"}, sol
    assert filter_markets(MARKETS, "sol/usdt")[0]["symbol"] == "SOL_USDT"
    assert filter_markets(MARKETS, "  eth  ")[0]["symbol"] == "ETH_USDT"
    assert filter_markets(MARKETS, "zzzz") == []


@pytest.mark.parametrize("consulta", ["btc-usdt", "btc/usdt", "btc_usdt"])
def test_separadores_equivalentes(consulta):
    assert filter_markets(MARKETS, consulta)[0]["symbol"] == "BTC_USDT"
