"""Payloads de orden: abrir a mercado y cerrar (total, parcial, limite).

Sin red: el cliente falso guarda lo que se iba a enviar. Esto es la red de
seguridad de la ruta critica: si un cambio mueve `side`, `type` o `vol`, aqui
se cae antes de tocar la cuenta.
"""

import pytest

from tradedesk.mexc import MexcError


def test_abrir_long_a_mercado(mx):
    data, vol, px = mx.open_market("XAU_USDT", "LONG", 100, 10)

    path, payload = mx.sent[-1]
    assert path == "/api/v1/private/order/create"
    assert data == {"orderId": "test"}
    assert (vol, px) == (1000.0, 100.0), "100 USDT a 100 con size 0.001 = 1000 contratos"
    assert payload["side"] == 1, "1 = abre long"
    assert payload["type"] == 5, "5 = mercado"
    assert payload["leverage"] == 10
    assert payload["openType"] == 1
    assert payload["price"] == 100.0
    assert len(payload["externalOid"]) == 24, "idempotencia"
    assert "takeProfitPrice" not in payload and "stopLossPrice" not in payload


def test_abrir_short_con_tp_sl(mx):
    mx.open_market("XAU_USDT", "SHORT", 100, 5, open_type=2, tp=90, sl=110)

    payload = mx.sent[-1][1]
    assert payload["side"] == 3, "3 = abre short"
    assert payload["openType"] == 2, "2 = cruzado"
    assert payload["takeProfitPrice"] == 90.0
    assert payload["stopLossPrice"] == 110.0
    assert payload["priceProtect"] == 0
    assert payload["profitTrend"] == 1 and payload["lossTrend"] == 1


def test_cerrar_todo_a_mercado(mx, posicion):
    mx.close_position(posicion)

    payload = mx.sent[-1][1]
    assert payload["type"] == 5
    assert payload["side"] == 4, "4 = cierra long"
    assert payload["vol"] == 22.0
    assert payload["price"] == 100.0


def test_cerrar_short_y_parcial(mx, posicion):
    mx.close_position(dict(posicion, positionType=2), vol=7)

    payload = mx.sent[-1][1]
    assert payload["side"] == 2, "2 = cierra short"
    assert payload["vol"] == 7.0
    assert payload["type"] == 5


def test_cerrar_limite_redondea_al_price_scale(mx, posicion):
    mx.close_position(posicion, vol=10, price=2246.394)

    payload = mx.sent[-1][1]
    assert payload["type"] == 1, "1 = limite"
    assert payload["price"] == 2246.39, "priceScale 2 del contrato"
    assert payload["vol"] == 10.0


@pytest.mark.parametrize("vol", [0, -1, 23])
def test_cerrar_rechaza_cantidades_imposibles(mx, posicion, vol):
    with pytest.raises(MexcError):
        mx.close_position(posicion, vol=vol)
    assert mx.sent == [], "no debe llegar nada a la API"


def test_cerrar_sin_precio_no_pide_contrato_al_limite(mx, posicion):
    """A mercado no hace falta priceScale: no se gasta un request de contrato."""
    mx.close_position(posicion)
    assert len(mx.sent) == 1
