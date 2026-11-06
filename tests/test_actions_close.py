"""Glue del cierre: porcentaje -> contratos -> orden. Sin Tk y sin red."""

import queue
import types

import pytest

from tradedesk import controller


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

    def log(self, msg):
        pass

    def refresh_positions(self):
        pass

    def refresh_orders(self):
        pass

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
    monkeypatch.setattr(controller, "threading", types.SimpleNamespace(Thread=InlineThread))
    ctl = _control(mx)
    ctl.port.avisos = []
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
