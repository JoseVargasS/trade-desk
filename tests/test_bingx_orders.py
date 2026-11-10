"""Payloads de BingX: firma y lo que se manda al abrir, cerrar y cancelar.

Sin red: se intercepta `_post` / `_delete` y se miran las rutas y los parámetros.
La API real se prueba a mano con `tools/probe_bingx.py`.
"""

import hashlib
import hmac
import time

import pytest

from tradedesk.bingx import (
    Bingx,
    BingxError,
    canonico,
    display_name,
    largo,
)
from tradedesk.bingx_comun import (
    decorate_orders,
    decorate_positions,
    es_condicional,
)

CONTRATO = {
    "symbol": "BTC-USDT",
    "contractSize": 0.0001,
    "priceScale": 1,
    "minQty": 0.0001,
    "minNotional": 2.0,
    "takerFeeRate": 0.0005,
}


def armado(precio=60000.0):
    """Cliente sin red: captura las llamadas y devuelve un id cualquiera."""
    cliente = Bingx("k", "s")
    enviados = []
    cliente._post = lambda ruta, params=None: (
        enviados.append(("POST", ruta, params)) or {"orderId": "1"}
    )
    cliente._delete = lambda ruta, params=None: enviados.append(("DEL", ruta, params)) or {"ok": 1}
    cliente.price = lambda simbolo: precio
    cliente.contract = lambda simbolo: dict(CONTRATO)
    cliente.open_orders = lambda simbolo=None: []
    cliente.positions = lambda: []
    return cliente, enviados


def payload_de(enviados, ruta):
    for _metodo, enviada, cuerpo in enviados:
        if enviada.endswith(ruta):
            return cuerpo
    raise AssertionError(f"no se llamo a {ruta}: {[e[1] for e in enviados]}")


def test_simbolos():
    assert canonico("BTC_USDT") == "BTC-USDT"
    assert canonico("BTCUSDT") == "BTC-USDT"
    assert display_name("BTC-USDT") == "BTCUSDT"


def test_condicionales_bingx_se_identifican_sin_marcar_limites_normales():
    cliente, _enviados = armado()
    ordenes = decorate_orders(
        cliente,
        [
            {
                "symbol": "BTC-USDT",
                "type": "STOP_MARKET",
                "side": "SELL",
                "positionSide": "LONG",
                "stopPrice": "69000",
                "quantity": "0.0001",
                "orderId": "stop",
            },
            {
                "symbol": "BTC-USDT",
                "type": "TAKE_PROFIT_MARKET",
                "side": "SELL",
                "positionSide": "LONG",
                "stopPrice": "84000",
                "quantity": "0.0001",
                "orderId": "take-profit",
            },
            {
                "symbol": "BTC-USDT",
                "type": "LIMIT",
                "side": "BUY",
                "positionSide": "LONG",
                "quantity": "0.0001",
                "orderId": "limit",
            },
        ],
    )

    assert es_condicional(ordenes[0])
    assert ordenes[0]["price"] == 69000
    assert ordenes[0]["stopLossPrice"] == 69000
    assert es_condicional(ordenes[1])
    assert ordenes[1]["takeProfitPrice"] == 84000
    assert not es_condicional(ordenes[2])


def test_largo_entiende_strings_y_bools():
    assert largo("LONG") is True
    assert largo("SHORT") is False
    assert largo(True) is True
    assert largo(False) is False


def test_firma_ordena_params_y_agrega_timestamp():
    cliente = Bingx("k", "secreto")
    firmado = cliente._firmar({"symbol": "BTC-USDT", "z": "1", "a": "2"})
    consulta = f"a=2&symbol=BTC-USDT&z=1&timestamp={firmado['timestamp']}"
    esperado = hmac.new(b"secreto", consulta.encode(), hashlib.sha256).hexdigest()
    assert firmado["signature"] == esperado
    assert firmado["timestamp"].isdigit()


def test_abrir_mercado_long_pone_leverage_y_buy():
    cliente, enviados = armado()
    _, qty, px = cliente.open_market("BTC_USDT", "LONG", 100.0, 10, 1)
    assert (qty, px) == (0.0016, 60000.0)
    palanca = payload_de(enviados, "/trade/leverage")
    assert palanca["symbol"] == "BTC-USDT"
    assert palanca["leverage"] == 10
    assert palanca["side"] == "LONG"
    cuerpo = payload_de(enviados, "/trade/order")
    assert cuerpo["side"] == "BUY"
    assert cuerpo["positionSide"] == "LONG"
    assert cuerpo["type"] == "MARKET"
    assert cuerpo["quantity"] == "0.0016"


def test_abrir_short_string_manda_sell():
    """Regresión: "SHORT" llegaba como bool y todo entraba como BUY."""
    cliente, enviados = armado()
    cliente.open_market("BTC_USDT", "SHORT", 100.0, 5, 1)
    cuerpo = payload_de(enviados, "/trade/order")
    assert cuerpo["side"] == "SELL"
    assert cuerpo["positionSide"] == "SHORT"


def test_abrir_limite_con_tp_sl():
    cliente, enviados = armado()
    cliente.open_market("BTC-USDT", "LONG", 120.0, 5, 2, tp=79000.0, sl=70000.0, precio=76000.0)
    cuerpo = payload_de(enviados, "/trade/order")
    assert cuerpo["type"] == "LIMIT"
    assert cuerpo["price"] == "76000"
    assert cuerpo["quantity"] == "0.0015"
    assert "TAKE_PROFIT_MARKET" in cuerpo["takeProfit"]
    assert "79000.0" in cuerpo["takeProfit"]
    assert "STOP_MARKET" in cuerpo["stopLoss"]


def test_cerrar_posicion_entera_es_una_orden_al_contrario():
    """BingX v2 no tiene `closePosition`: se cierra con una orden."""
    cliente, enviados = armado()
    pos = {"symbol": "BTC-USDT", "positionId": "77", "holdVol": 0.0003, "positionType": 1}
    cliente.close_position(pos)
    cuerpo = payload_de(enviados, "/trade/order")
    assert cuerpo["side"] == "SELL"
    assert cuerpo["positionSide"] == "LONG"
    assert cuerpo["quantity"] == "0.0003"
    assert cuerpo["type"] == "MARKET"
    # en HEDGE mandar reduceOnly da 109400
    assert "reduceOnly" not in cuerpo


def test_cerrar_reintenta_con_reduce_only_si_la_api_lo_pide():
    """En one-way la API exige `reduceOnly`: se reintenta con el campo."""
    from tradedesk.bingx import BingxError

    cliente, enviados = armado()
    llamadas = []

    def falla_una(ruta, params=None):
        llamadas.append(dict(params or {}))
        if len(llamadas) == 1:
            raise BingxError("109400 In the ONE_WAY mode, the 'ReduceOnly' field is required")
        return {"orderId": "1"}

    cliente._post = falla_una
    pos = {"symbol": "BTC-USDT", "positionId": "77", "holdVol": 0.0003, "positionType": 1}
    cliente.close_position(pos)
    assert "reduceOnly" not in llamadas[0]
    assert llamadas[1]["reduceOnly"] == "true"


def test_cerrar_parcial_manda_orden():
    cliente, enviados = armado()
    pos = {"symbol": "BTC-USDT", "positionId": "77", "holdVol": 0.0003, "positionType": 1}
    cliente.close_position(pos, vol=0.0001)
    cuerpo = payload_de(enviados, "/trade/order")
    assert cuerpo["side"] == "SELL"
    assert cuerpo["positionSide"] == "LONG"
    assert cuerpo["quantity"] == "0.0001"
    assert cuerpo["type"] == "MARKET"


def test_cerrar_short_parcial_compra():
    cliente, enviados = armado()
    pos = {"symbol": "BTC-USDT", "positionId": "78", "holdVol": 0.0004, "positionType": 2}
    cliente.close_position(pos, vol=0.0002, price=75000)
    cuerpo = payload_de(enviados, "/trade/order")
    assert cuerpo["side"] == "BUY"
    assert cuerpo["positionSide"] == "SHORT"
    assert cuerpo["type"] == "LIMIT"
    assert cuerpo["price"] == "75000"


def test_cancelar_por_id_busca_el_simbolo():
    cliente, enviados = armado()
    cliente.open_orders = lambda simbolo=None: [
        {"orderId": "55", "symbol": "ETH-USDT"},
        {"orderId": "66", "symbol": "BTC-USDT"},
    ]
    cliente.cancel(["66"])
    cuerpo = payload_de(enviados, "/trade/order")
    assert cuerpo == {"symbol": "BTC-USDT", "orderId": "66"}


def test_cantidad_con_floor_y_sin_ceros_de_mas():
    cliente, _ = armado(precio=77000.0)
    assert cliente.size_to_qty("BTC-USDT", 100.0, 77000.0) == 0.0012
    assert cliente._texto_qty("BTC-USDT", 0.0012) == "0.0012"
    assert cliente._texto_qty("BTC-USDT", 3.0) == "3"


def test_la_posicion_toma_el_tp_sl_de_las_condicionales():
    """BingX no manda TP/SL en la posición: vienen como órdenes condicionales."""
    cliente, _ = armado()
    posicion = {
        "symbol": "BTC-USDT",
        "positionId": "9",
        "positionAmt": "0.0002",
        "positionSide": "LONG",
        "avgPrice": "76000",
        "unrealizedProfit": "-0.01",
        "leverage": 1,
        "margin": "15.2",
        "riskRate": "0.01",
    }
    condicionales = [
        {
            "symbol": "BTC-USDT",
            "type": "TAKE_PROFIT_MARKET",
            "positionSide": "LONG",
            "stopPrice": "84000",
        },
        {"symbol": "BTC-USDT", "type": "STOP_MARKET", "positionSide": "LONG", "stopPrice": "69000"},
    ]
    fila = decorate_positions(cliente, [posicion], condicionales)[0]
    assert fila["_tp"] == 84000
    assert fila["_sl"] == 69000
    assert fila["holdVol"] == 0.0002
    assert fila["_lado"] == "LONG"


def test_tpsl_place_manda_dos_condicionales_con_cantidad():
    cliente, enviados = armado()
    cliente.positions = lambda: [
        {"positionId": "9", "symbol": "BTC-USDT", "positionAmt": "0.0002", "positionSide": "LONG"}
    ]
    cliente.tpsl_place("9", tp=84000, sl=69000, simbolo="BTC_USDT")
    stops = [
        cuerpo
        for _metodo, _ruta, cuerpo in enviados
        if cuerpo.get("type") in ("TAKE_PROFIT_MARKET", "STOP_MARKET")
    ]
    assert len(stops) == 2
    assert {cuerpo["type"] for cuerpo in stops} == {"TAKE_PROFIT_MARKET", "STOP_MARKET"}
    assert all(cuerpo["quantity"] == "0.0002" for cuerpo in stops)
    # `closePosition` = la app de BingX lo muestra como "Posicion completa";
    # sin el, queda como "parcial al 100 %" (que es lo que hacia antes)
    assert all(cuerpo["closePosition"] == "true" for cuerpo in stops)
    assert all("reduceOnly" not in cuerpo for cuerpo in stops)


def test_tpsl_place_aborta_si_no_puede_limpiar_condicionales_viejas():
    cliente, enviados = armado()
    cliente.positions = lambda: [
        {"positionId": "9", "symbol": "BTC-USDT", "positionAmt": "0.0002", "positionSide": "LONG"}
    ]
    cliente.open_orders = lambda: [
        {
            "symbol": "BTC-USDT",
            "type": "STOP_MARKET",
            "positionSide": "LONG",
            "orderId": "old-stop",
        }
    ]

    def cancelar(_ordenes):
        raise BingxError("cancel rechazada")

    cliente.cancel = cancelar
    with pytest.raises(BingxError, match="no se pudo cancelar.*cancel rechazada"):
        cliente.tpsl_place("9", tp=84000, simbolo="BTC_USDT")

    assert not any(ruta.endswith("/trade/order") for _metodo, ruta, _body in enviados)


def test_tpsl_cancel_expone_el_fallo_de_cancelacion():
    cliente, _enviados = armado()
    cliente.open_orders = lambda: [
        {
            "symbol": "BTC-USDT",
            "type": "STOP_MARKET",
            "positionSide": "LONG",
            "orderId": "old-stop",
        }
    ]

    def cancelar(_ordenes):
        raise BingxError("cancel rechazada")

    cliente.cancel = cancelar
    with pytest.raises(BingxError, match="cancel rechazada"):
        cliente.tpsl_cancel(None, simbolo="BTC_USDT")


def test_reverse_reabre_el_mismo_tamano():
    """El nocional del reopen lleva 1 % de margen: si no, el floor da 0."""
    cliente, enviados = armado(precio=76550.4)
    vistas = {"n": 0}

    def posiciones():
        vistas["n"] += 1
        if vistas["n"] > 1:
            return []
        return [
            {
                "positionId": "9",
                "symbol": "BTC-USDT",
                "positionAmt": "0.0001",
                "positionSide": "SHORT",
                "avgPrice": "76550.4",
            }
        ]

    cliente.positions = posiciones
    pos = {
        "symbol": "BTC-USDT",
        "positionType": 2,
        "holdVol": 0.0001,
        "holdAvgPrice": 76550.4,
        "leverage": 1,
        "positionId": "9",
        "_exchange": "bingx",
    }
    cliente.reverse(pos)
    ordenes = [
        (cuerpo, ruta) for _metodo, ruta, cuerpo in enviados if ruta.endswith("/trade/order")
    ]
    assert ordenes, "el reverse tiene que mandar órdenes"
    cierra, reabre = ordenes[0][0], ordenes[-1][0]
    assert cierra["side"] == "BUY" and cierra["positionSide"] == "SHORT"
    assert reabre["side"] == "BUY" and reabre["positionSide"] == "LONG"
    assert reabre["quantity"] == "0.0001"


def test_comisiones_del_historial_por_position_id():
    """La fee no viene en /positions: se suma `commission` por `positionID`."""
    cliente, _ = armado()
    cliente._get = lambda ruta, params=None: {
        "orders": [
            {"status": "FILLED", "positionID": "9", "commission": "-0.0038"},
            {"status": "FILLED", "positionID": "9", "commission": "-0.0010"},
            {"status": "CANCELED", "positionID": "9", "commission": "-0.5000"},
            {"status": "FILLED", "positionID": "", "commission": "-0.9000"},
        ]
    }
    totales = cliente.comisiones()
    assert set(totales) == {"9"}
    assert round(totales["9"], 6) == 0.0048


def test_error_al_cargar_comisiones_no_se_convierte_en_fee_cero():
    cliente, _ = armado()

    def falla(*_args, **_kwargs):
        raise RuntimeError("historial no disponible")

    cliente._get = falla
    with pytest.raises(RuntimeError, match="historial no disponible"):
        cliente.comisiones()


def test_la_posicion_toma_la_fee_del_historial():
    cliente, _ = armado()
    posicion = {
        "positionId": "9",
        "symbol": "BTC-USDT",
        "positionAmt": "0.0001",
        "positionSide": "SHORT",
        "avgPrice": "76494.4",
        "unrealizedProfit": "0",
        "leverage": 1,
        "margin": "7.65",
    }
    fila = decorate_positions(cliente, [posicion], [], {"9": 0.003824})[0]
    assert round(fila["totalFee"], 6) == 0.003824


def test_el_tamano_de_contrato_es_1_porque_la_cantidad_va_en_monedas():
    """BingX publica `size` 0,0001 en el catalogo, pero `quantity` va en monedas.

    Tomar ese `size` como tamaño de contrato multiplicaba el nocional y el mark
    price por 10.000: la posición salía en negativo con un mark price absurdo.
    """
    cliente = Bingx("k", "s")
    cliente.contracts = lambda: [
        {
            "symbol": "BTC-USDT",
            "size": "0.0001",
            "pricePrecision": 1,
            "tradeMinQuantity": "0.0001",
        }
    ]
    contrato = cliente.contract("BTC_USDT")
    assert contrato["contractSize"] == 1.0
    assert contrato["priceScale"] == 1

    cliente.positions = lambda: [
        {
            "positionId": "1",
            "symbol": "BTC-USDT",
            "positionAmt": "0.0388",
            "positionSide": "SHORT",
            "avgPrice": "76920.7",
            "leverage": 10,
            "unrealizedProfit": "7.4826",
        }
    ]
    fila = decorate_positions(cliente, cliente.positions(), [])[0]
    assert fila["_contractSize"] == 1.0
    assert round(fila["holdVol"], 4) == 0.0388
    # nocional = monedas × precio (sin factores de 10.000)
    assert round(fila["holdVol"] * fila["_contractSize"] * fila["holdAvgPrice"], 2) == 2984.52


def test_el_apalancamiento_de_una_orden_llega_como_numero():
    """BingX manda `leverage: "10X"` y la tabla lo pinta con `int()`."""
    from tradedesk.bingx import decorate_orders

    cliente, _ = armado()
    ordenes = [
        {
            "orderId": "5",
            "symbol": "BTC-USDT",
            "side": "BUY",
            "positionSide": "LONG",
            "type": "LIMIT",
            "price": "60000",
            "quantity": "0.001",
            "executedQty": "0",
            "status": "NEW",
            "leverage": "10X",
            "time": 1793752692570,
        }
    ]
    fila = decorate_orders(cliente, ordenes)[0]
    assert fila["leverage"] == 10
    assert isinstance(fila["leverage"], int)


def test_el_apalancamiento_no_se_reenvia_si_ya_esta_puesto():
    """El apalancamiento es un viaje por par y lado: si no cambió, no se repite."""
    cliente, enviados = armado()

    cliente.open_market("BTC_USDT", "LONG", 100.0, 10, 1)
    cliente.open_market("BTC_USDT", "LONG", 100.0, 10, 1)

    cambios = [cuerpo for _metodo, ruta, cuerpo in enviados if ruta.endswith("/trade/leverage")]
    assert len(cambios) == 1


def test_el_apalancamiento_se_reenvia_si_cambia():
    cliente, enviados = armado()

    cliente.open_market("BTC_USDT", "LONG", 100.0, 10, 1)
    cliente.open_market("BTC_USDT", "LONG", 100.0, 20, 1)

    cambios = [cuerpo for _metodo, ruta, cuerpo in enviados if ruta.endswith("/trade/leverage")]
    assert [c["leverage"] for c in cambios] == [10, 20]


def test_el_apalancamiento_se_reenvia_tras_la_edad_maxima():
    """Si el usuario lo cambió en el exchange, la app tiene que mandar el suyo."""
    cliente, enviados = armado()
    cliente.open_market("BTC_USDT", "LONG", 100.0, 10, 1)
    cliente._apalancamiento[("BTC-USDT", "LONG")] = (10, time.monotonic() - 61)

    cliente.open_market("BTC_USDT", "LONG", 100.0, 10, 1)

    cambios = [cuerpo for _metodo, ruta, cuerpo in enviados if ruta.endswith("/trade/leverage")]
    assert len(cambios) == 2


def test_el_precio_de_referencia_ahorra_el_ticker():
    cliente, _enviados = armado()
    cliente.price = lambda _simbolo: (_ for _ in ()).throw(AssertionError("ticker extra"))

    _, _qty, px = cliente.open_market("BTC_USDT", "LONG", 100.0, 10, 1, precio_ref=60000.0)

    assert px == 60000.0
