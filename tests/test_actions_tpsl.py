"""TP/SL, break-even y verificación de órdenes. Sin Tk y sin red."""

import threading

import httpx

from tests.fakes import control, form_abrir
from tradedesk import controller
from tradedesk.mexc import MexcError


def test_timeout_en_tpsl_avisa_y_refresca_sin_reintentar(app, posicion):
    llamadas = []

    def timeout(*_args, **_kwargs):
        llamadas.append(True)
        raise httpx.ReadTimeout("timeout")

    app.mx.price = lambda _symbol: 3900.0
    app.mx.tpsl_list = timeout
    app._tpsl_worker(posicion, None, 3800.0)
    mensajes = [app.q.get_nowait() for _ in range(app.q.qsize())]

    assert len(llamadas) == 1
    assert app.session.refrescos == ["orders", "positions"]
    assert any(
        m[0] == "status" and "verifica posiciones y órdenes" in m[1].lower() for m in mensajes
    )
    assert app.mx.sent == []
    assert app.verificaciones[0][0] == "cambio de TP/SL"


def test_timeout_en_break_even_avisa_y_refresca_sin_reintentar(app, posicion):
    llamadas = []

    def timeout(*_args, **_kwargs):
        llamadas.append(True)
        raise httpx.ReadTimeout("timeout")

    app.mx.price = lambda _symbol: 3900.0
    app.mx.tpsl_list = timeout
    app._fila_be = lambda _pos: {"be": 3100.0}
    app._be_worker([posicion], {str(posicion["positionId"])})
    mensajes = [app.q.get_nowait() for _ in range(app.q.qsize())]

    assert len(llamadas) == 1
    assert app.session.refrescos == ["orders", "positions"]
    assert any(
        m[0] == "status" and "verifica posiciones y órdenes" in m[1].lower() for m in mensajes
    )
    assert app.verificaciones[0][0] == "TP/SL de GOLD(XAU)USDT"


def test_verificacion_confirma_apertura_por_el_cambio_de_posicion(app):
    app.session.ultimas_posiciones = []
    app.mx.open_market = lambda *_args: (_ for _ in ()).throw(httpx.ReadTimeout("timeout"))
    app.mx.positions = lambda: [{"symbol": "BTC_USDT", "positionType": 1, "holdVol": 2}]

    app._do_abrir("LONG", form_abrir(), False)

    accion, comprobar = app.verificaciones[0]
    assert accion == "apertura"
    assert comprobar()


def test_verificacion_confirma_orden_limite_abierta(app):
    app.mx.open_market = lambda *_args: (_ for _ in ()).throw(httpx.ReadTimeout("timeout"))
    app.mx.open_orders = lambda: [
        {"symbol": "BTC_USDT", "orderId": "new", "side": 1, "price": 100, "type": 1}
    ]

    app._do_abrir("LONG", dict(form_abrir(), price=100), False)

    accion, comprobar = app.verificaciones[0]
    assert accion == "apertura"
    assert comprobar()


def test_verificacion_confirma_cierre_si_la_posicion_ya_no_esta(app, posicion):
    app.mx.close_position = lambda *_args: (_ for _ in ()).throw(httpx.ReadTimeout("timeout"))
    app.mx.positions = lambda: []

    app._do_cerrar([posicion])

    accion, comprobar = app.verificaciones[0]
    assert accion == "cierre"
    assert comprobar()


def test_verificacion_confirma_cierre_limite_por_orden_nueva(app, posicion):
    app.mx.close_position = lambda *_args: (_ for _ in ()).throw(httpx.ReadTimeout("timeout"))
    app.mx.open_orders = lambda: [
        {"symbol": "XAU_USDT", "orderId": "new", "side": 4, "price": 105, "type": 1}
    ]

    app._do_cerrar([posicion], vol=5, price=105)

    accion, comprobar = app.verificaciones[0]
    assert accion == "cierre"
    assert comprobar()


def test_verificacion_confirma_reverse_solo_si_abre_el_lado_contrario(app, posicion):
    app.mx.reverse = lambda *_args: (_ for _ in ()).throw(httpx.ReadTimeout("timeout"))
    app.mx.positions = lambda: [{"symbol": "XAU_USDT", "positionType": 2, "holdVol": 22}]

    app.reverse(posicion)

    accion, comprobar = app.verificaciones[0]
    assert accion == "reverse"
    assert comprobar()


def test_verificacion_no_confirma_reverse_si_solo_se_cerro(app, posicion):
    app.mx.reverse = lambda *_args: (_ for _ in ()).throw(httpx.ReadTimeout("timeout"))
    app.mx.positions = lambda: []

    app.reverse(posicion)

    accion, comprobar = app.verificaciones[0]
    assert accion == "reverse"
    assert not comprobar()


def test_verificacion_confirma_tpsl_con_los_niveles_del_broker(app, posicion):
    llamadas = 0

    def stops():
        nonlocal llamadas
        llamadas += 1
        if llamadas == 1:
            raise httpx.ReadTimeout("timeout")
        return [{"positionId": 1, "stopLossPrice": 3800}]

    app.mx.price = lambda _symbol: 3900
    app.mx.tpsl_list = stops
    app._tpsl_worker(posicion, None, 3800)

    accion, comprobar = app.verificaciones[0]
    assert accion == "cambio de TP/SL"
    assert comprobar()


def test_verificacion_tpsl_bitunix_coteja_par_y_lado():
    class FakeBitunix:
        def positions(self):
            return [{"symbol": "BTCUSDT", "side": "BUY", "qty": 0.01}]

        def tpsl_list(self):
            return [
                {"symbol": "BTCUSDT", "tpPrice": 110},
                {"symbol": "BTCUSDT", "slPrice": 90},
            ]

    ctl = control(None)
    pos = {
        "symbol": "BTC_USDT",
        "positionId": "p1",
        "positionType": 1,
        "_priceScale": 1,
    }

    assert ctl._tpsl_coincide(FakeBitunix(), "bitunix", pos, 110, 90)


def test_verificacion_tpsl_bingx_ignora_condicional_del_lado_opuesto():
    class FakeBingx:
        def positions(self):
            return [{"symbol": "BTC-USDT", "positionSide": "LONG", "positionAmt": 0.01}]

        def open_orders(self, _symbol):
            return [
                {
                    "symbol": "BTC-USDT",
                    "positionSide": "SHORT",
                    "type": "STOP_MARKET",
                    "stopPrice": 90,
                },
                {
                    "symbol": "BTC-USDT",
                    "positionSide": "LONG",
                    "type": "TAKE_PROFIT_MARKET",
                    "stopPrice": 110,
                },
                {
                    "symbol": "BTC-USDT",
                    "positionSide": "LONG",
                    "type": "STOP_MARKET",
                    "stopPrice": 90,
                },
            ]

    ctl = control(None)
    pos = {
        "symbol": "BTC_USDT",
        "positionType": 1,
        "_priceScale": 1,
    }

    assert ctl._tpsl_coincide(FakeBingx(), "bingx", pos, 110, 90)


def test_verificador_publica_confirmacion_y_actualiza_las_tablas(app):
    app.VERIFICACION_ESPACIOS = (0,)

    controller.Control._iniciar_verificacion(app, "apertura", lambda: True)

    mensajes = [app.q.get_nowait() for _ in range(app.q.qsize())]
    assert any(m == ("status", "El broker confirmó la operación: apertura.") for m in mensajes)
    assert app.session.refrescos == ["positions", "orders"]


def test_verificador_no_presenta_como_confirmada_una_consulta_fallida(app):
    app.VERIFICACION_ESPACIOS = (0,)

    def fallo():
        raise httpx.ReadTimeout("timeout")

    controller.Control._iniciar_verificacion(app, "apertura", fallo)
    mensajes = [app.q.get_nowait() for _ in range(app.q.qsize())]

    assert any("no se pudo verificar" in m[1].lower() for m in mensajes if m[0] == "status")


def test_verificador_reintenta_lectura_tras_error_de_transporte(app):
    app.session._parar = threading.Event()
    app.VERIFICACION_INTERVALO = 0
    app.VERIFICACION_ESPACIOS = (0,)
    llamadas = 0

    def comprobar():
        nonlocal llamadas
        llamadas += 1
        if llamadas == 1:
            raise httpx.ReadTimeout("timeout")
        return True

    controller.Control._iniciar_verificacion(app, "reverse", comprobar)

    mensajes = [app.q.get_nowait() for _ in range(app.q.qsize())]
    assert llamadas == 2
    assert any("confirmó la operación" in m[1].lower() for m in mensajes if m[0] == "status")


def test_verificador_pide_revision_si_no_encuentra_cambios(app):
    app.VERIFICACION_ESPACIOS = (0,)

    controller.Control._iniciar_verificacion(app, "cierre", lambda: False)
    mensajes = [app.q.get_nowait() for _ in range(app.q.qsize())]

    assert any("no se encontró evidencia" in m[1].lower() for m in mensajes if m[0] == "status")
    assert not any("confirmó la operación" in m[1].lower() for m in mensajes if m[0] == "status")
    assert app.session.refrescos == ["positions", "orders"]


def test_editar_el_tpsl_cancela_todos_los_stop_de_la_posicion(app, posicion):
    """Se cancela por positionId, no por el `_tpsl_id` cacheado: si no, MEXC
    acumula stops duplicados cada vez que se edita."""
    app.mx._fake_price = 3900.0
    app.mx.stops = [
        {"id": 5, "positionId": 1},
        {"id": 6, "positionId": 1},
        {"id": 7, "positionId": 2},  # otra posicion: no se toca
    ]

    app._tpsl_worker(dict(posicion, _tpsl_id=None), None, 3800.0)
    rutas = [ruta for ruta, _ in app.mx.sent]
    cancelados = [p[0]["stopPlanOrderId"] for ruta, p in app.mx.sent if ruta.endswith("/cancel")]

    assert sorted(cancelados) == [5, 6]
    assert rutas[-1].endswith("/stoporder/place")
    assert app.mx.sent[-1][1]["stopLossPrice"] == 3800.0


def test_el_break_even_no_se_guarda_como_tp_si_el_precio_se_movio(app, posicion):
    """Si el precio volvio a la entrada, el SL del break-even queda del lado de
    la ganancia y `plan_tp_sl` lo convertiria en TP: mejor rechazar."""
    app.mx._fake_price = 3000.0

    app._tpsl_worker(posicion, None, 3100.0, True)
    avisos = []
    while not app.q.empty():
        kind, payload = app.q.get()
        if kind == "notice":
            avisos.append(payload[1])

    assert app.mx.sent == []
    assert avisos and "break-even" in avisos[0].lower()


def test_bingx_coloca_el_tpsl_sin_tpsl_list(app, posicion):
    """BingX no tiene `tpsl_list`: el worker no debe pedirlo o no coloca nada.

    Era el bug real: el worker llamaba `mx.tpsl_list()` siempre y en BingX tiraba
    AttributeError antes de mandar el TP/SL (el break-even no se colocaba).
    """
    llamadas = []

    class FakeBingx:
        def price(self, symbol):
            return 3900.0

        def tpsl_place(self, position_id, vol, tp, sl, simbolo=None):
            llamadas.append((position_id, vol, tp, sl, simbolo))
            return []

    bingx = FakeBingx()
    app.session.cliente = lambda nombre: bingx if nombre == "bingx" else None

    app._tpsl_worker(dict(posicion, _exchange="bingx"), None, 3800.0)

    assert not hasattr(bingx, "tpsl_list"), "el fake imita a BingX"
    assert llamadas, "BingX tiene que recibir el TP/SL"
    assert llamadas[0][0] == posicion["positionId"]
    assert llamadas[0][3] == 3800.0


def test_bingx_borra_el_tpsl_cuando_los_campos_estan_vacios(app, posicion):
    """Sacar el TP y el SL tiene que borrar las condicionales.

    En BingX las cancela `tpsl_place`, asi que con los dos campos vacios hay que
    llamarlo igual: antes no se llamaba y el SL quedaba pegado en el broker.
    """
    llamadas = []

    class FakeBingx:
        def price(self, symbol):
            return 3900.0

        def tpsl_place(self, position_id, vol, tp, sl, simbolo=None):
            llamadas.append((position_id, tp, sl))
            return []

    bingx = FakeBingx()
    app.session.cliente = lambda nombre: bingx if nombre == "bingx" else None

    app._tpsl_worker(dict(posicion, _exchange="bingx"), None, None)

    assert llamadas == [(posicion["positionId"], None, None)]


def test_be_todas_pone_el_sl_de_las_elegidas_sin_cerrar(app, posicion):
    """El BE masivo mueve el SL, no cierra: la orden de cierre no se manda."""
    # el break-even de esta posicion queda en ~4104,65: el precio tiene que estar arriba
    app.mx._fake_price = 4200.0
    app.session.precios["XAU_USDT"] = 4200.0
    pos = dict(posicion, markPrice=4200.0)
    app.port.elegidas_be = [str(pos["positionId"])]

    app.be_todas([pos])

    rutas = [ruta for ruta, _ in app.mx.sent]
    assert any(ruta.endswith("/stoporder/place") for ruta in rutas)
    assert not any(ruta.endswith("/order/create") for ruta in rutas), "no debe cerrar"
    stop = app.mx.sent[-1][1]
    assert stop["stopLossPrice"] > posicion["holdAvgPrice"]


def test_be_todas_marca_las_que_no_llegan_y_no_hace_nada(app, posicion):
    """Si el precio no llegó al break-even, la fila sale apagada y no se toca."""
    app.mx._fake_price = 3900.0
    app.session.precios["XAU_USDT"] = 3900.0  # por debajo del break-even
    pos = dict(posicion, markPrice=3900.0)
    app.port.elegidas_be = []

    app.be_todas([pos])

    fila = app.port.filas_be[0]
    assert fila["puede"] is False
    assert "break-even" in fila["motivo"]
    assert app.mx.sent == []


def test_be_todas_cancelado_no_manda_nada(app, posicion):
    app.mx._fake_price = 4200.0
    app.session.precios["XAU_USDT"] = 4200.0
    app.port.elegidas_be = None

    app.be_todas([dict(posicion, markPrice=4200.0)])

    assert app.mx.sent == []


def test_el_tpsl_reintenta_si_el_broker_sigue_contando_el_stop_cancelado(
    app, posicion, monkeypatch
):
    """MEXC cancela el stop viejo de forma asíncrona: al colocar avisa 5004.

    Antes se sondeaba la lista de stops; ahora se reintenta el envío, que es
    un viaje menos.
    """
    intentos = []

    class Cliente:
        def price(self, _symbol):
            return 3900.0

        def tpsl_list(self):
            return []

        def tpsl_place(self, position_id, vol, tp, sl, simbolo=None):
            intentos.append(sl)
            if len(intentos) < 3:
                raise MexcError("todavia cuenta el stop viejo", code=5004)
            return []

    monkeypatch.setattr("tradedesk.controller_tpsl.time.sleep", lambda _s: None)
    app.session.cliente = lambda _nombre: Cliente()

    app._tpsl_worker(dict(posicion, _exchange="mexc"), None, 3800.0)

    assert len(intentos) == 3
    mensajes = [app.q.get_nowait() for _ in range(app.q.qsize())]
    assert any(m[0] == "closed" and "TP/SL actualizado" in m[1] for m in mensajes)


def test_el_tpsl_no_reintenta_un_error_que_no_es_5004(app, posicion):
    intentos = []

    class Cliente:
        def price(self, _symbol):
            return 3900.0

        def tpsl_list(self):
            return []

        def tpsl_place(self, position_id, vol, tp, sl, simbolo=None):
            intentos.append(sl)
            raise MexcError("Precio de TP/SL invalido")

    app.session.cliente = lambda _nombre: Cliente()

    app._tpsl_worker(dict(posicion, _exchange="mexc"), None, 3800.0)

    assert len(intentos) == 1
    mensajes = [app.q.get_nowait() for _ in range(app.q.qsize())]
    assert any(m[0] == "notice" for m in mensajes)


def test_el_be_masivo_va_en_paralelo_entre_brokers(app, posicion, monkeypatch):
    """Cada broker tiene su propio límite: los dos pueden entrar a la vez."""
    barrera = threading.Barrier(2, timeout=5)

    class Cliente:
        def price(self, _symbol):
            return 4200.0

        def tpsl_list(self):
            return []

        def tpsl_place(self, position_id, vol, tp, sl, simbolo=None):
            barrera.wait()
            return []

    clientes = {"mexc": Cliente(), "bitunix": Cliente()}
    app.session.cliente = lambda nombre: clientes.get(nombre)
    monkeypatch.setattr("tradedesk.controller_tpsl.time.sleep", lambda _s: None)

    app._be_worker(
        [
            dict(posicion, _exchange="mexc"),
            dict(posicion, positionId=2, _exchange="bitunix"),
        ],
        {"1", "2"},
    )

    mensajes = [app.q.get_nowait() for _ in range(app.q.qsize())]
    assert any(m[0] == "closed" and "BE aplicado en 2 de 2" in m[1] for m in mensajes)
    assert not any(m[0] == "notice" for m in mensajes), "la barrera debe cruzarse"


def test_el_verificador_espacia_las_reconsultas(app, monkeypatch):
    """La primera reconsulta va rápido: el broker suele reflejar el cambio ya."""
    esperas = []
    monkeypatch.setattr("tradedesk.controller_verificacion.time.sleep", lambda s: esperas.append(s))

    controller.Control._iniciar_verificacion(app, "cierre", lambda: False)

    assert esperas == [0.4, 1.0, 2.0, 3.0]
