"""Glue del cierre: porcentaje -> contratos -> orden. Sin Tk y sin red."""

import queue
import threading
import types

import httpx
import pytest

from tradedesk import controller
from tradedesk.mexc import MexcError


class InlineThread:
    """Hilo que corre en el acto: el test no espera a nadie."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self.target, self.args, self.kwargs = target, args or (), kwargs or {}

    def start(self):
        self.target(*self.args, **self.kwargs)


class FakeSession:
    def __init__(self, mx):
        self.mx = mx
        self.q = queue.Queue()
        self.precios = {}
        self.avisos = []
        self.refrescos = []

    def log(self, msg):
        pass

    def refresh_positions(self):
        self.refrescos.append("positions")

    def refresh_orders(self):
        self.refrescos.append("orders")

    def contract_for(self, symbol):
        return {}


class FakePort:
    def __init__(self, confirmar=True):
        self.confirmar = confirmar
        self.avisos = []
        self.mensajes = []

    def confirm(self, *a, **k):
        return self.confirmar

    def show(self, titulo, mensaje, **k):
        self.avisos.append(mensaje)

    def form(self, *a, **k):
        return None

    def tpsl(self, pos, precio):
        return None

    def editar_orden(self, orden, contrato, a_vol):
        return None

    def be_lista(self, filas):
        """Lo que devuelve la ventana de BE: los ids elegidos o None."""
        self.filas_be = filas
        return self.elegidas_be

    def status(self, texto):
        self.mensajes.append(texto)


def _control(mx, dry=False):
    return controller.Control(FakeSession(mx), FakePort(), dry=lambda: dry)


@pytest.fixture
def app(mx, monkeypatch):
    fake_threading = types.SimpleNamespace(Thread=InlineThread)
    monkeypatch.setattr(controller, "threading", fake_threading)
    monkeypatch.setattr("tradedesk.controller_verificacion.threading", fake_threading)
    monkeypatch.setattr("tradedesk.controller_tpsl.threading", fake_threading)
    monkeypatch.setattr("tradedesk.controller_ordenes.threading", fake_threading)
    ctl = _control(mx)
    ctl.port.avisos = []
    ctl.verificaciones = []
    ctl._iniciar_verificacion = lambda accion, comprobar: ctl.verificaciones.append(
        (accion, comprobar)
    )
    return ctl


def test_sin_tocar_nada_cierra_todo_a_mercado(app, posicion):
    app.cerrar(posicion)

    payload = app.mx.sent[-1][1]
    assert payload["vol"] == 22.0
    assert payload["type"] == 5


def test_porcentaje_cierra_una_parte(app, posicion):
    app.cerrar(posicion, {"pct": 50})

    assert app.mx.sent[-1][1]["vol"] == 11.0


def test_precio_lo_manda_como_limite(app, posicion):
    app.cerrar(posicion, {"pct": 100, "price": 2246.394})

    payload = app.mx.sent[-1][1]
    assert payload["type"] == 1
    assert payload["price"] == 2246.39


def test_porcentaje_que_deja_cero_contratos_no_envia_nada(app, posicion):
    app.cerrar(dict(posicion, holdVol=3), {"pct": 10})

    assert app.mx.sent == []
    assert "0 contratos" in app.port.avisos[-1]


def test_dry_run_bloquea(mx, posicion, monkeypatch):
    monkeypatch.setattr(controller, "threading", types.SimpleNamespace(Thread=InlineThread))
    ctl = _control(mx, dry=True)

    ctl.cerrar(posicion)

    assert ctl.mx.sent == []
    assert ctl.port.mensajes and "DRY-RUN" in ctl.port.mensajes[-1]


def test_cancelar_la_confirmacion_no_envia(mx, posicion, monkeypatch):
    monkeypatch.setattr(controller, "threading", types.SimpleNamespace(Thread=InlineThread))
    ctl = _control(mx)
    ctl.port.confirmar = False

    ctl.cerrar(posicion)

    assert ctl.mx.sent == []


def test_timeout_al_abrir_avisa_resultado_desconocido_y_refresca(app):
    llamadas = []

    def timeout(*_args):
        llamadas.append(True)
        raise httpx.ReadTimeout("timeout")

    app.mx.open_market = timeout
    app._do_abrir(
        "LONG",
        {
            "symbol": "XAU_USDT",
            "notional": 100,
            "lev": 1,
            "open_type": 1,
            "tp": None,
            "sl": None,
            "price": None,
        },
        False,
    )
    mensajes = [app.q.get_nowait() for _ in range(app.q.qsize())]

    assert len(llamadas) == 1
    assert app.session.refrescos == ["positions", "orders"]
    assert any("resultado es desconocido" in str(m).lower() for m in mensajes)
    assert app.verificaciones[0][0] == "apertura"


def test_timeout_al_cerrar_avisa_y_refresca_sin_reintentar(app, posicion):
    llamadas = []

    def timeout(*_args):
        llamadas.append(True)
        raise httpx.ReadTimeout("timeout")

    app.mx.close_position = timeout
    app._do_cerrar([posicion])
    mensajes = [app.q.get_nowait() for _ in range(app.q.qsize())]

    assert len(llamadas) == 1
    assert app.session.refrescos == ["positions", "orders"]
    assert any(m[0] == "status" and "resultado es desconocido" in m[1].lower() for m in mensajes)
    assert app.verificaciones[0][0] == "cierre"


def test_timeout_en_reverse_avisa_y_refresca_sin_reintentar(app, posicion):
    llamadas = []

    def timeout(*_args):
        llamadas.append(True)
        raise httpx.ReadTimeout("timeout")

    app.mx.reverse = timeout
    app.reverse(posicion)
    mensajes = [app.q.get_nowait() for _ in range(app.q.qsize())]

    assert len(llamadas) == 1
    assert app.session.refrescos == ["orders", "positions"]
    assert any(m[0] == "status" and "resultado es desconocido" in m[1].lower() for m in mensajes)
    assert app.verificaciones[0][0] == "reverse"


def test_cerrar_todo_avisa_la_posicion_que_siguio_abierta(app):
    """Cerrar sin error no basta: si la posición sigue, se nombra el símbolo."""
    app.CIERRE_ESPERA = 0.0
    app.mx.close_all = lambda: {"code": 0, "data": ""}
    app.mx.positions = lambda: [{"symbol": "ETH_USDT", "positionId": 9}]
    app._brokers = lambda: [("mexc", app.mx)]
    app.session.ultimas_posiciones = [{"symbol": "ETH_USDT", "_exchange": "mexc"}]
    app.cerrar_todo(1)
    mensajes = [app.q.get_nowait() for _ in range(app.q.qsize())]
    cerrado = next(m[1] for m in mensajes if m[0] == "closed")

    assert "ETH_USDT" in cerrado
    assert "Todas las posiciones cerradas" not in cerrado


def test_cerrar_todo_no_se_detiene_si_un_broker_falla(app):
    """Se cierran los tres a la vez: el que falla no deja al resto parado."""
    app.CIERRE_ESPERA = 0.0
    cerrados = []

    def falla():
        cerrados.append("mexc")
        raise RuntimeError("boom")

    otro = types.SimpleNamespace(
        close_all=lambda: cerrados.append("bitunix"),
        positions=lambda: [],
    )
    app.mx.close_all = falla
    app.mx.positions = lambda: []
    app._brokers = lambda: [("mexc", app.mx), ("bitunix", otro)]
    app.cerrar_todo(1)
    mensajes = [app.q.get_nowait() for _ in range(app.q.qsize())]

    assert sorted(cerrados) == ["bitunix", "mexc"]
    assert "boom" in next(m[1] for m in mensajes if m[0] == "closed")


def test_timeout_al_cerrar_todo_avisa_y_refresca_sin_reintentar(app):
    llamadas = []

    def timeout():
        llamadas.append(True)
        raise httpx.ReadTimeout("timeout")

    app.mx.close_all = timeout
    app.mx.positions = lambda: []
    app._brokers = lambda: [("mexc", app.mx)]
    app.cerrar_todo(1)
    mensajes = [app.q.get_nowait() for _ in range(app.q.qsize())]

    assert len(llamadas) == 1
    assert app.session.refrescos == ["positions", "orders"]
    assert any(m[0] == "closed" and "resultado es desconocido" in m[1].lower() for m in mensajes)
    assert app.verificaciones[0][0] == "cierre total en mexc"
    assert app.verificaciones[0][1]()


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

    app._do_abrir("LONG", _form_abrir(), False)

    accion, comprobar = app.verificaciones[0]
    assert accion == "apertura"
    assert comprobar()


def test_verificacion_confirma_orden_limite_abierta(app):
    app.mx.open_market = lambda *_args: (_ for _ in ()).throw(httpx.ReadTimeout("timeout"))
    app.mx.open_orders = lambda: [
        {"symbol": "BTC_USDT", "orderId": "new", "side": 1, "price": 100, "type": 1}
    ]

    app._do_abrir("LONG", dict(_form_abrir(), price=100), False)

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

    ctl = _control(None)
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

    ctl = _control(None)
    pos = {
        "symbol": "BTC_USDT",
        "positionType": 1,
        "_priceScale": 1,
    }

    assert ctl._tpsl_coincide(FakeBingx(), "bingx", pos, 110, 90)


def test_verificador_publica_confirmacion_y_actualiza_las_tablas(app):
    app.VERIFICACION_INTERVALO = 0

    controller.Control._iniciar_verificacion(app, "apertura", lambda: True)

    mensajes = [app.q.get_nowait() for _ in range(app.q.qsize())]
    assert any(m == ("status", "El broker confirmó la operación: apertura.") for m in mensajes)
    assert app.session.refrescos == ["positions", "orders"]


def test_verificador_no_presenta_como_confirmada_una_consulta_fallida(app):
    app.VERIFICACION_INTERVALO = 0

    def fallo():
        raise httpx.ReadTimeout("timeout")

    controller.Control._iniciar_verificacion(app, "apertura", fallo)
    mensajes = [app.q.get_nowait() for _ in range(app.q.qsize())]

    assert any("no se pudo verificar" in m[1].lower() for m in mensajes if m[0] == "status")


def test_verificador_reintenta_lectura_tras_error_de_transporte(app):
    app.session._parar = threading.Event()
    app.VERIFICACION_INTERVALO = 0
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
    app.VERIFICACION_INTERVALO = 0

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


def test_cancelar_publica_confirmacion_visible(app):
    app.cancelar(
        {
            "orderId": "123",
            "symbol": "XAU_USDT",
            "side": 1,
            "orderType": 1,
            "price": 4000,
            "vol": 2,
            "_exchange": "mexc",
        }
    )

    assert app.q.get_nowait() == ("status", "1 orden(es) cancelada(s) en mexc.")
    assert app.mx.sent[-1][0].endswith("/order/cancel")


def test_fallo_al_cancelar_publica_error_visible(app):
    def rechazar(_ids):
        raise RuntimeError("API no disponible")

    app.mx.cancel = rechazar
    app.cancelar(
        {
            "orderId": "123",
            "symbol": "XAU_USDT",
            "side": 1,
            "orderType": 1,
            "price": 4000,
            "vol": 2,
            "_exchange": "mexc",
        }
    )

    assert app.q.get_nowait() == ("error", "Error al cancelar en mexc: API no disponible")


def test_orden_condicional_bingx_no_se_puede_editar(app):
    app.modificar(
        {
            "_exchange": "bingx",
            "type": "STOP_MARKET",
            "side": 1,
        }
    )

    assert app.port.mensajes == ["Las condicionales TP/SL de BingX se gestionan desde Posiciones."]


def _form_abrir():
    return {
        "symbol": "BTC_USDT",
        "notional": 100,
        "lev": 1,
        "open_type": 1,
        "tp": None,
        "sl": None,
        "price": None,
    }


def test_timeout_al_abrir_avisa_estado_desconocido_y_refresca(app):
    refrescos = []

    def timeout(*_args, **_kwargs):
        raise httpx.ReadTimeout("write timed out")

    app.mx.open_market = timeout
    app.session.refresh_positions = lambda: refrescos.append("positions")
    app.session.refresh_orders = lambda: refrescos.append("orders")

    app._do_abrir("LONG", _form_abrir(), False)

    assert refrescos == ["positions", "orders"]
    assert app.q.get_nowait() == (
        "order",
        (
            False,
            "No pudimos confirmar si la solicitud llegó al broker. El resultado es "
            "desconocido. Revisa Posiciones y Órdenes antes de volver a intentarlo. "
            "No se volverá a enviar automáticamente.",
        ),
    )
    assert app.q.get_nowait()[0] == "closed"
    assert app.q.get_nowait()[1][0] == "Estado de la orden desconocido"


def test_rechazo_de_negocio_al_abrir_sigue_siendo_rechazo(app):
    app.mx.open_market = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        MexcError("Saldo insuficiente")
    )

    app._do_abrir("LONG", _form_abrir(), False)

    assert app.q.get_nowait() == ("order", (False, "Saldo insuficiente"))
    assert app.q.get_nowait() == ("closed", "Saldo insuficiente")
    assert app.q.get_nowait()[1][0] == "Orden rechazada"


def test_broker_desconocido_no_enruta_a_mexc(app):
    enviados = []
    app.mx.open_market = lambda *_args, **_kwargs: enviados.append(True)

    app._do_abrir("LONG", _form_abrir(), False, exchange="desconocido")

    assert enviados == []
    assert app.q.get_nowait() == (
        "order",
        (False, "Broker desconocido: desconocido."),
    )
    assert app.q.get_nowait() == ("closed", "Broker desconocido: desconocido.")
    assert app.q.get_nowait()[1][0] == "Broker no disponible"


@pytest.mark.parametrize("exchange", ("bitunix", "bingx"))
def test_dry_run_usa_cantidad_y_unidad_del_broker(app, exchange):
    class Cliente:
        def price(self, _symbol):
            return 100

        def size_to_qty(self, _symbol, _notional, _price):
            return 0.25

    app.session.cliente = lambda _nombre: Cliente()

    app._do_abrir("LONG", _form_abrir(), True, exchange=exchange)

    assert app.q.get_nowait() == (
        "order",
        (True, "DRY-RUN LONG 0.25 BTC @ 100.00 (no enviado)"),
    )
