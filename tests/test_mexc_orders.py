"""Payloads de orden: abrir a mercado y cerrar (total, parcial, limite).

Sin red: el cliente falso guarda lo que se iba a enviar. Esto es la red de
seguridad de la ruta critica: si un cambio mueve `side`, `type` o `vol`, aqui
se cae antes de tocar la cuenta.
"""

import pytest

from tradedesk.mexc import MexcError, decorate_orders


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


def test_abrir_con_precio_es_orden_limite(mx):
    mx.open_market("XAU_USDT", "LONG", 100, 10, price=110.004)

    payload = mx.sent[-1][1]
    assert payload["type"] == 1, "1 = limite"
    assert payload["price"] == 110.0, "precio redondeado al priceScale del contrato"
    assert payload["vol"] == 909.0, "el tamaño se convierte con el precio limite"


def test_abrir_a_mercado_ignora_un_precio_vacio(mx):
    mx.open_market("XAU_USDT", "LONG", 100, 10, price=None)

    payload = mx.sent[-1][1]
    assert payload["type"] == 5
    assert payload["price"] == 100.0, "precio de mercado"


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


# --------------------------------------------------------------- ordenes abiertas
def test_cancelar_manda_un_array_de_ids(mx):
    """El endpoint espera [id, id]; con {"orderIds": []} responde 600."""
    mx.cancel(["871374754337090048", 42])

    path, payload = mx.sent[-1]
    assert path == "/api/v1/private/order/cancel"
    assert payload == ["871374754337090048", "42"], "ids como texto, body en array"


def test_cancelar_sin_ids_no_llama_a_la_api(mx):
    assert mx.cancel([]) == []
    assert mx.sent == [], "sin ids no hay request"


def test_las_ordenes_abiertas_traen_contrato_y_nombre(mx):
    """El precio limite se pinta con el priceScale del contrato y el par con el
    nombre de MEXC, sin pedir nada a la red."""
    orden = decorate_orders(mx, [{"orderId": "1", "symbol": "XAU_USDT"}])[0]

    assert orden["_contractSize"] == 0.001
    assert orden["_priceScale"] == 2
    assert orden["_name"] == "GOLD(XAU)USDT"


def test_sin_contrato_conocido_la_orden_no_revienta():
    class SinCatalogo:
        def known_contract(self, symbol):
            return {}

    orden = decorate_orders(SinCatalogo(), [{"orderId": "1", "symbol": "ABC_USDT"}])[0]

    assert orden["_contractSize"] == 0.0
    assert orden["_priceScale"] == 2
    assert orden["_name"] == "ABC_USDT", "cae al simbolo crudo"


# --------------------------------------------- editar = cancelar y reenviar
def _app_de_prueba(mx):
    """App sin ventana: solo lo que usa el worker de reenvio."""
    import queue

    from tradedesk.app import App

    app = App.__new__(App)
    app.mx = mx
    app.q = queue.Queue()
    app._log = lambda msg: None
    app._refresh_orders = lambda: None
    return app


def test_modificar_cancela_y_reenvia_la_orden(mx):
    app = _app_de_prueba(mx)
    orden = {"orderId": "871374754337090048", "symbol": "XAU_USDT", "openType": 1}
    form = {
        "side": "SHORT",
        "lev": 20,
        "margin": 10.0,
        "notional": 200.0,
        "price": 110.0,
        "tp": None,
        "sl": None,
        "vol": 1818,
    }

    app._replace_order_worker(orden, form)

    assert [p for p, _ in mx.sent] == [
        "/api/v1/private/order/cancel",
        "/api/v1/private/order/create",
    ], "primero cancela y despues reenvia"
    assert mx.sent[0][1] == ["871374754337090048"]
    crear = mx.sent[1][1]
    assert crear["side"] == 3, "SHORT abre con 3"
    assert crear["type"] == 1, "sigue siendo orden limite"
    assert crear["leverage"] == 20
    assert crear["openType"] == 1, "conserva aislado/cruzado"
    assert crear["price"] == 110.0
    assert app.q.get_nowait() == ("closed", "Orden reenviada · XAU_USDT")


def test_si_el_reenvio_falla_avisa_que_la_vieja_ya_se_cancelo(mx):
    class FallaAlCrear(type(mx)):
        def _post(self, path, payload):
            if path.endswith("/order/create"):
                raise MexcError("margen insuficiente")
            return super()._post(path, payload)

    app = _app_de_prueba(FallaAlCrear())
    orden = {"orderId": "1", "symbol": "XAU_USDT", "openType": 1}
    form = {
        "side": "LONG",
        "lev": 10,
        "margin": 10.0,
        "notional": 100.0,
        "price": 100.0,
        "tp": None,
        "sl": None,
        "vol": 1000,
    }

    app._replace_order_worker(orden, form)

    eventos = {}
    while not app.q.empty():
        kind, payload = app.q.get_nowait()
        eventos.setdefault(kind, []).append(payload)
    assert "margen insuficiente" in eventos["closed"][0]
    _titulo, texto, danger = eventos["notice"][0]
    assert "ya se canceló" in texto and danger is True
