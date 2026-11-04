"""El saldo de la cabecera es el de la cuenta CON el PnL abierto (en vivo).

Se mueve con las posiciones abiertas a propósito: es el patrimonio que el
usuario ve en la app de cada broker.
"""

from tradedesk.bingx import Bingx
from tradedesk.bitunix import Bitunix
from tradedesk.mexc import Mexc


def test_bingx_saldo_es_el_equity_con_el_pnl_abierto():
    cliente = Bingx("k", "s")
    # `balance()` ya devuelve la lista desenvuelta
    cliente.balance = lambda: [
        {
            "asset": "USDT",
            "balance": "313.2413",
            "equity": "321.5406",  # balance + 8.30 de PnL abierto
            "availableMargin": "14.7890",
            "usedMargin": "298.4523",
        }
    ]
    assert round(cliente.saldo(), 4) == 321.5406
    assert round(cliente.available(), 4) == 14.789


def test_bitunix_saldo_incluye_el_pnl_no_realizado():
    cliente = Bitunix("k", "s")
    cliente.assets = lambda: [
        {
            "marginCoin": "USDT",
            "available": "8.5",
            "margin": "300.5",
            "frozen": "0",
            "crossUnrealizedPNL": "2.0",
            "isolationUnrealizedPNL": "0.5",
        },
        {"marginCoin": "BTC", "available": "0", "margin": "0"},
    ]
    # disponible + margen: el `available` ya trae el PnL abierto
    assert round(cliente.saldo(), 4) == 309.0
    assert round(cliente.available(), 4) == 8.5


def test_mexc_saldo_es_el_equity():
    cliente = Mexc("k", "s")
    cliente.assets = lambda: [
        {
            "currency": "USDT",
            "cashBalance": 4915.27,
            "equity": 4930.0,  # incluye 14.73 de PnL abierto
            "availableBalance": 2.0,
        },
    ]
    assert round(cliente.saldo(), 4) == 4930.0
    assert round(cliente.available(), 4) == 2.0
