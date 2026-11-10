"""Glue del cierre: porcentaje -> contratos -> orden. Sin Tk y sin red."""

import types

import httpx
import pytest

from tests.fakes import InlineThread, control, form_abrir
from tradedesk import controller
from tradedesk.mexc import MexcError


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
    ctl = control(mx, dry=True)

    ctl.cerrar(posicion)

    assert ctl.mx.sent == []
    assert ctl.port.mensajes and "DRY-RUN" in ctl.port.mensajes[-1]


def test_cancelar_la_confirmacion_no_envia(mx, posicion, monkeypatch):
    monkeypatch.setattr(controller, "threading", types.SimpleNamespace(Thread=InlineThread))
    ctl = control(mx)
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


def test_timeout_al_abrir_avisa_estado_desconocido_y_refresca(app):
    refrescos = []

    def timeout(*_args, **_kwargs):
        raise httpx.ReadTimeout("write timed out")

    app.mx.open_market = timeout
    app.session.refresh_positions = lambda *_a: refrescos.append("positions")
    app.session.refresh_orders = lambda *_a: refrescos.append("orders")

    app._do_abrir("LONG", form_abrir(), False)

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

    app._do_abrir("LONG", form_abrir(), False)

    assert app.q.get_nowait() == ("order", (False, "Saldo insuficiente"))
    assert app.q.get_nowait() == ("closed", "Saldo insuficiente")
    assert app.q.get_nowait()[1][0] == "Orden rechazada"


def test_broker_desconocido_no_enruta_a_mexc(app):
    enviados = []
    app.mx.open_market = lambda *_args, **_kwargs: enviados.append(True)

    app._do_abrir("LONG", form_abrir(), False, exchange="desconocido")

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

    app._do_abrir("LONG", form_abrir(), True, exchange=exchange)

    assert app.q.get_nowait() == (
        "order",
        (True, "DRY-RUN LONG 0.25 BTC @ 100.00 (no enviado)"),
    )
