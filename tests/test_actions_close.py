"""Glue del cierre: porcentaje -> contratos -> orden. Sin Tk y sin red."""

import queue
import types

import pytest

from tradedesk import actions


class InlineThread:
    """Hilo que corre en el acto: el test no espera a nadie."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self.target, self.args, self.kwargs = target, args or (), kwargs or {}

    def start(self):
        self.target(*self.args, **self.kwargs)


class FakeApp(actions.ActionsMixin):
    def __init__(self, mx, dry=False):
        self.var_dry = types.SimpleNamespace(get=lambda: dry)
        self.mx = mx
        self.q = queue.Queue()
        self.root = None
        self.status = []

    def _status(self, msg):
        self.status.append(msg)

    def _log(self, msg):
        pass

    def _refresh_positions(self):
        pass


@pytest.fixture
def app(mx, monkeypatch):
    monkeypatch.setattr(actions, "threading", types.SimpleNamespace(Thread=InlineThread))
    monkeypatch.setattr(actions.dialog, "confirm", lambda *a, **k: True)
    avisos = []
    monkeypatch.setattr(actions.dialog, "show", lambda parent, title, msg, **k: avisos.append(msg))
    fake = FakeApp(mx)
    fake.avisos = avisos
    return fake


def test_sin_tocar_nada_cierra_todo_a_mercado(app, posicion):
    app._close_position(posicion)

    payload = app.mx.sent[-1][1]
    assert payload["vol"] == 22.0
    assert payload["type"] == 5


def test_porcentaje_cierra_una_parte(app, posicion):
    app._close_position(posicion, {"pct": 50})

    assert app.mx.sent[-1][1]["vol"] == 11.0


def test_precio_lo_manda_como_limite(app, posicion):
    app._close_position(posicion, {"pct": 100, "price": 2246.394})

    payload = app.mx.sent[-1][1]
    assert payload["type"] == 1
    assert payload["price"] == 2246.39


def test_porcentaje_que_deja_cero_contratos_no_envia_nada(app, posicion):
    app._close_position(dict(posicion, holdVol=3), {"pct": 10})

    assert app.mx.sent == []
    assert "0 contratos" in app.avisos[-1]


def test_dry_run_bloquea(app, posicion):
    app.var_dry = types.SimpleNamespace(get=lambda: True)
    app._close_position(posicion)

    assert app.mx.sent == []
    assert app.status and "DRY-RUN" in app.status[-1]


def test_cancelar_la_confirmacion_no_envia(app, posicion, monkeypatch):
    monkeypatch.setattr(actions.dialog, "confirm", lambda *a, **k: False)
    app._close_position(posicion)

    assert app.mx.sent == []


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
