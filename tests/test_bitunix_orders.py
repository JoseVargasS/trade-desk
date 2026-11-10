"""Payloads de Bitunix: lo que se manda de verdad al abrir, cerrar y cancelar.

Sin red: se intercepta `_post` y se miran las rutas y el cuerpo. La red se prueba
a mano con `tools/probe_bitunix.py`.
"""

import time

import pytest

from tradedesk.bitunix import Bitunix, BitunixError, canonico, con_guion

CONTRATO = {
    "symbol": "BTCUSDT",
    "contractSize": 1.0,
    "priceScale": 2,
    "qtyStep": 0.0001,
    "qtyPrecision": 4,
    "base": "BTC",
}


def armado(modo="HEDGE", precio=60000.0):
    """Cliente sin red: captura las llamadas y devuelve un id cualquiera."""
    cliente = Bitunix("k", "s")
    enviados = []
    cliente._post = lambda ruta, payload: enviados.append((ruta, payload)) or {"orderId": "1"}
    cliente._get = lambda ruta, params=None: {}
    cliente.price = lambda simbolo: precio
    cliente.contract = lambda simbolo: dict(CONTRATO)
    cliente.position_mode = lambda: modo
    cliente.open_orders = lambda: []
    return cliente, enviados


def payload_de(enviados, ruta):
    for enviada, cuerpo in enviados:
        if enviada.endswith(ruta):
            return cuerpo
    raise AssertionError(f"no se llamo a {ruta}: {[e[0] for e in enviados]}")


def test_fallo_al_consultar_modo_se_avisa_y_conserva_fallback_hedge():
    cliente = Bitunix("k", "s")
    cliente._get = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("sin conexión"))
    errores = []
    cliente.on_error = lambda recurso, exc: errores.append((recurso, exc))

    assert cliente.position_mode() == "HEDGE"
    assert errores and errores[0][0] == "modo de posición"


def test_simbolos():
    assert canonico("BTC_USDT") == "BTCUSDT"
    assert con_guion("BTCUSDT") == "BTC_USDT"


@pytest.mark.parametrize("codigo", (0, "0"))
def test_bitunix_acepta_solo_codigo_explicito_de_exito(codigo):
    class Respuesta:
        status_code = 200

        def json(self):
            return {"code": codigo, "data": {"ok": True}}

    assert Bitunix._leer(Respuesta()) == {"ok": True}


@pytest.mark.parametrize("codigo", (None, True, 1, ""))
def test_bitunix_rechaza_codigo_ausente_o_ambiguo(codigo):
    class Respuesta:
        status_code = 200

        def json(self):
            return {"code": codigo, "data": {"ok": True}}

    with pytest.raises(BitunixError):
        Bitunix._leer(Respuesta())


def test_bitunix_rechaza_respuesta_sin_objeto_o_http_no_exitoso():
    class Respuesta:
        status_code = 500

        def json(self):
            return {"code": 0, "data": {"ok": True}}

    with pytest.raises(BitunixError, match="HTTP 500"):
        Bitunix._leer(Respuesta())

    Respuesta.status_code = 200
    Respuesta.json = lambda self: []
    with pytest.raises(BitunixError, match="Respuesta invalida"):
        Bitunix._leer(Respuesta())


def test_abrir_mercado_long():
    cliente, enviados = armado()
    _, qty, px = cliente.open_market("BTC_USDT", True, 100.0, 10, 5)
    assert (qty, px) == (0.0016, 60000.0)
    cuerpo = payload_de(enviados, "/trade/place_order")
    assert cuerpo == {
        "symbol": "BTCUSDT",
        "qty": "0.0016",
        "side": "BUY",
        "orderType": "MARKET",
        "tradeSide": "OPEN",
    }


def test_abrir_short_como_string_manda_sell():
    """Regresión: la vista manda "SHORT" y el booleano lo tomaba como long."""
    cliente, enviados = armado()
    cliente.open_market("BTC_USDT", "SHORT", 100.0, 10, 5)
    cuerpo = payload_de(enviados, "/trade/place_order")
    assert cuerpo["side"] == "SELL"


def test_abrir_limite_short_con_tp_sl():
    cliente, enviados = armado()
    cliente.open_market("BTCUSDT", False, 120.0, 5, 1, tp=59000.0, sl=61500.0, precio=61000.0)
    cuerpo = payload_de(enviados, "/trade/place_order")
    assert cuerpo["side"] == "SELL"
    assert cuerpo["orderType"] == "LIMIT"
    assert cuerpo["price"] == "61000.00"
    assert cuerpo["effect"] == "GTC"
    assert cuerpo["tpPrice"] == "59000.00" and cuerpo["tpOrderType"] == "MARKET"
    assert cuerpo["slPrice"] == "61500.00" and cuerpo["slStopType"] == "LAST_PRICE"


def test_abrir_sin_cantidad_no_manda_orden():
    """Si el floor deja 0 monedas, no se manda nada y se avisa."""
    cliente, enviados = armado()
    cliente.change_leverage = lambda *a, **k: None
    error = ""
    try:
        cliente.open_market("BTCUSDT", True, 0.5, 10, 5)  # 5 USDT / 60000 -> 0 monedas
    except Exception as exc:
        error = str(exc)
    assert "cantidad" in error.lower()
    assert [ruta for ruta, _ in enviados if ruta.endswith("place_order")] == []


def test_cierre_total_usa_flash_close():
    cliente, enviados = armado()
    pos = {"symbol": "BTCUSDT", "positionId": 77, "positionType": 1, "holdVol": 0.002}
    cliente.close_position(pos)
    cuerpo = payload_de(enviados, "/flash_close_position")
    assert cuerpo == {"positionId": "77"}


def test_cierre_parcial_es_reduce_only():
    cliente, enviados = armado()
    pos = {"symbol": "BTCUSDT", "positionId": 77, "positionType": 1, "holdVol": 0.002}
    cliente.close_position(pos, vol=0.0005)
    cuerpo = payload_de(enviados, "/trade/place_order")
    assert cuerpo["reduceOnly"] is True
    assert cuerpo["tradeSide"] == "CLOSE"
    assert cuerpo["positionId"] == "77"
    assert cuerpo["qty"] == "0.0005"
    assert cuerpo["orderType"] == "MARKET"


def test_cierre_limite_lleva_precio():
    cliente, enviados = armado()
    pos = {"symbol": "BTCUSDT", "positionId": 77, "positionType": 2, "holdVol": 0.002}
    cliente.close_position(pos, vol=0.001, price=61000.0)
    cuerpo = payload_de(enviados, "/trade/place_order")
    assert cuerpo["orderType"] == "LIMIT"
    assert cuerpo["price"] == "61000.00"
    assert cuerpo["side"] == "SELL"  # short segun la doc de Bitunix
    assert cuerpo["effect"] == "GTC"


def test_cerrar_todo_cierra_cada_posicion_por_su_id():
    """El endpoint masivo responde OK sin detalle: se cierra por `positionId`."""
    cliente, enviados = armado()
    cliente.positions = lambda: [
        {"symbol": "BTCUSDT", "positionId": 77},
        {"symbol": "ETHUSDT", "positionId": 88},
    ]
    cliente.close_all()
    flashes = [cuerpo for ruta, cuerpo in enviados if ruta.endswith("/flash_close_position")]
    assert flashes == [{"positionId": "77"}, {"positionId": "88"}]
    assert not any(ruta.endswith("/close_all_position") for ruta, _ in enviados)


def test_cancelar_resuelve_el_simbolo():
    cliente, enviados = armado()
    cliente.open_orders = lambda: [{"orderId": "555", "symbol": "ETHUSDT"}]
    cliente.cancel(["555"])
    cuerpo = payload_de(enviados, "/trade/cancel_orders")
    assert cuerpo == {"symbol": "ETHUSDT", "orderList": [{"orderId": "555"}]}


def test_apalancamiento():
    cliente, enviados = armado()
    cliente.change_leverage("BTCUSDT", 12)
    cuerpo = payload_de(enviados, "/account/change_leverage")
    assert cuerpo == {"symbol": "BTCUSDT", "leverage": 12, "marginCoin": "USDT"}


def test_qty_hace_floor_al_step():
    cliente, _ = armado()
    assert cliente.size_to_qty("BTCUSDT", 100.0, 60000.0) == 0.0016
    assert cliente.size_to_qty("BTCUSDT", 1000.0, 60000.0) == 0.0166
    assert cliente.size_to_qty("BTCUSDT", 0.0, 60000.0) == 0.0


def test_cierre_tolera_posicion_cruda():
    """La posición cruda trae `qty`, no `holdVol`: si vol viene en 0 se usa qty."""
    cliente, enviados = armado()
    cruda = {"symbol": "BTCUSDT", "positionId": 9, "positionType": 2, "qty": "0.0002"}
    cliente.close_position(cruda, vol=0)
    cuerpo = payload_de(enviados, "/trade/place_order")
    assert cuerpo["qty"] == "0.0002"
    assert cuerpo["side"] == "SELL"


def test_reverse_cierra_reduce_only_y_abre_la_contraria():
    """El cierre del reverse NO usa flash_close: bloquea la apertura inmediata."""
    cliente, enviados = armado()
    cerrado = []
    cliente.close_position = lambda pos, vol=None, price=None: cerrado.append(vol)
    cliente._esperar_sin_posicion = lambda simbolo, timeout=4.0: True
    pos = {"symbol": "BTCUSDT", "positionId": 9, "positionType": 2, "holdVol": 0.0002}
    cliente.reverse(pos)
    assert cerrado == [0.0002]  # cierra por cantidad (reduceOnly), no flash
    cuerpo = payload_de(enviados, "/trade/place_order")
    assert cuerpo["side"] == "BUY"  # era short: la contraria es long
    assert cuerpo["tradeSide"] == "OPEN"
    assert cuerpo["qty"] == "0.0002"


def test_firma_get_sin_separadores():
    """Los query params se firman como `limit5skip0`, sin `=` ni `&`."""
    import hashlib

    cliente = Bitunix("clave", "secreto")
    visto = {}

    class Falso:
        def get(self, url, params=None, headers=None):
            visto.update(url=url, params=params, headers=headers)
            return type(
                "R", (), {"status_code": 200, "json": lambda self: {"code": 0, "data": []}}
            )()

    cliente._cliente = Falso()
    cliente._get("/x", {"skip": 0, "limit": 5})
    cabeceras = visto["headers"]
    digest = hashlib.sha256(
        f"{cabeceras['nonce']}{cabeceras['timestamp']}clavelimit5skip0".encode()
    ).hexdigest()
    assert cabeceras["sign"] == hashlib.sha256((digest + "secreto").encode()).hexdigest()


def test_tpsl_a_nivel_de_posicion():
    cliente, enviados = armado()
    cliente.tpsl_place(77, 0.0002, tp=70000.0, sl=90000.0, simbolo="BTCUSDT")
    cuerpo = payload_de(enviados, "/tpsl/position/place_order")
    assert cuerpo == {
        "symbol": "BTCUSDT",
        "positionId": "77",
        "tpPrice": "70000.00",
        "tpStopType": "LAST_PRICE",
        "slPrice": "90000.00",
        "slStopType": "LAST_PRICE",
    }


def test_tpsl_cancel_pide_el_simbolo():
    cliente, enviados = armado()
    cliente.tpsl_cancel("123", simbolo="BTCUSDT")
    assert payload_de(enviados, "/tpsl/cancel_order") == {
        "symbol": "BTCUSDT",
        "orderId": "123",
    }


def test_modificar_orden_nativa():
    cliente, enviados = armado()
    orden = {"orderId": "1", "symbol": "BTCUSDT"}
    form = {"vol": 0.0002, "price": 61000.0, "tp": 59000.0, "sl": 62000.0}
    cliente.modify_order(orden, form)
    cuerpo = payload_de(enviados, "/trade/modify_order")
    assert cuerpo["orderId"] == "1"
    assert cuerpo["symbol"] == "BTCUSDT"
    assert cuerpo["qty"] == "0.0002"
    assert cuerpo["price"] == "61000.00"
    assert cuerpo["tpPrice"] == "59000.00"


def test_historial_usa_avgprice_y_estado():
    cliente, _ = armado()
    cruda = {
        "orderId": "5",
        "symbol": "BTCUSDT",
        "qty": "0.0002",
        "tradeQty": "0.0002",
        "price": "MARKET",
        "avgPrice": "76946.1",
        "realizedPNL": "-0.00002",
        "fee": "0.0077",
        "status": "FILLED",
        "ctime": "1793672692760",
        "side": "BUY",
    }
    cliente._get = lambda ruta, params=None: {"orderList": [cruda]}
    fila = cliente.history(5)[0]
    assert fila["dealAvgPrice"] == 76946.1
    assert fila["price"] == 0.0  # "MARKET" no es un numero
    assert fila["state"] == 3
    assert fila["side"] == 1
    assert fila["totalFee"] == 0.0077


def test_cambio_de_margen():
    cliente, enviados = armado()
    cliente.change_margin(77, 1.0, "ADD", simbolo="BTCUSDT", side=True)
    cuerpo = payload_de(enviados, "/adjust_position_margin")
    assert cuerpo == {
        "marginCoin": "USDT",
        "amount": "1",
        "positionId": "77",
        "symbol": "BTCUSDT",
        "side": "LONG",
    }


def test_el_apalancamiento_no_se_reenvia_si_ya_esta_puesto():
    """El apalancamiento es un viaje por par: si no cambió, no se repite."""
    cliente, enviados = armado()

    cliente.open_market("BTC_USDT", True, 100.0, 10, 5)
    cliente.open_market("BTC_USDT", True, 100.0, 10, 5)

    cambios = [cuerpo for ruta, cuerpo in enviados if ruta.endswith("/change_leverage")]
    assert len(cambios) == 1


def test_el_apalancamiento_se_reenvia_si_cambia():
    cliente, enviados = armado()

    cliente.open_market("BTC_USDT", True, 100.0, 10, 5)
    cliente.open_market("BTC_USDT", True, 100.0, 20, 5)

    cambios = [cuerpo for ruta, cuerpo in enviados if ruta.endswith("/change_leverage")]
    assert [c["leverage"] for c in cambios] == [10, 20]


def test_el_apalancamiento_se_reenvia_tras_la_edad_maxima():
    """Si el usuario lo cambió en el exchange, la app tiene que mandar el suyo."""
    cliente, enviados = armado()
    cliente.open_market("BTC_USDT", True, 100.0, 10, 5)
    cliente._apalancamiento["BTCUSDT"] = (10, time.monotonic() - 61)

    cliente.open_market("BTC_USDT", True, 100.0, 10, 5)

    cambios = [cuerpo for ruta, cuerpo in enviados if ruta.endswith("/change_leverage")]
    assert len(cambios) == 2


def test_el_precio_de_referencia_ahorra_el_ticker():
    cliente, _enviados = armado()
    cliente.price = lambda _simbolo: (_ for _ in ()).throw(AssertionError("ticker extra"))

    _, _qty, px = cliente.open_market("BTC_USDT", True, 100.0, 10, 5, precio_ref=60000.0)

    assert px == 60000.0
