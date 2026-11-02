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
