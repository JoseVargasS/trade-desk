import builtins
import queue
import threading

import pytest

from tradedesk import session as session_module
from tradedesk import session_cuenta as cuenta_module
from tradedesk.mexc import Mexc, MexcError
from tradedesk.session import Session


class Response:
    status_code = 200

    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class Http:
    def __init__(self, responses):
        self.responses = iter(responses)

    def get(self, *_args, **_kwargs):
        return next(self.responses)


class ReadClient:
    def __init__(self, positions=None, orders=None, fail=None):
        self.rows = {
            "positions": positions or [],
            "orders": orders or [],
        }
        self.fail = fail

    def _read(self, name):
        if self.fail == name:
            raise RuntimeError(f"{name} unavailable")
        return list(self.rows[name])

    def positions(self):
        return self._read("positions")

    def open_orders(self):
        return self._read("orders")

    def tpsl_list(self):
        return []

    def comisiones(self):
        return {}


def _session(mx, bitunix, bingx):
    app = object.__new__(Session)
    app.mx = mx
    app.bitunix = bitunix
    app.bingx = bingx
    app.hay = {"mexc": True, "bitunix": True, "bingx": True}
    app.q = queue.Queue()
    app._log_error_reported = False
    app.log = lambda _msg: None
    return app


def test_posiciones_de_un_broker_fallido_no_ocultan_los_otros(monkeypatch):
    monkeypatch.setattr(cuenta_module, "decorate_positions", lambda _c, rows, **_kw: rows)
    monkeypatch.setattr(cuenta_module, "decorate_positions_bitunix", lambda _c, rows, _s: rows)
    monkeypatch.setattr(cuenta_module, "decorate_positions_bingx", lambda _c, rows, _o, _f: rows)
    mx = ReadClient(fail="positions")
    bitunix = ReadClient(positions=[{"symbol": "ETHUSDT"}])
    bingx = ReadClient(positions=[{"symbol": "BTC-USDT"}])
    app = _session(mx, bitunix, bingx)

    filas = app.posiciones_todas()

    assert [fila["symbol"] for fila in filas] == ["ETHUSDT", "BTC-USDT"]
    assert app.q.get_nowait() == ("error", "posiciones mexc: positions unavailable")


def test_fallo_de_comisiones_bingx_se_avisa_sin_ocultar_posiciones(monkeypatch):
    monkeypatch.setattr(cuenta_module, "decorate_positions", lambda _c, rows, **_kw: rows)
    monkeypatch.setattr(cuenta_module, "decorate_positions_bitunix", lambda _c, rows, _s: rows)
    monkeypatch.setattr(cuenta_module, "decorate_positions_bingx", lambda _c, rows, _o, _f: rows)
    bingx = ReadClient(positions=[{"symbol": "BTC-USDT"}])

    def falla():
        raise RuntimeError("historial no disponible")

    bingx.comisiones = falla
    app = _session(ReadClient(), ReadClient(), bingx)

    filas = app.posiciones_todas()
    mensajes = list(app.q.queue)

    assert [fila["symbol"] for fila in filas] == ["BTC-USDT"]
    assert any("comisiones de posiciones bingx" in msg[1] for msg in mensajes)


def test_ordenes_de_un_broker_fallido_no_ocultan_los_otros(monkeypatch):
    monkeypatch.setattr(cuenta_module, "decorate_orders", lambda _c, rows: rows)
    monkeypatch.setattr(cuenta_module, "decorate_orders_bitunix", lambda _c, rows: rows)
    monkeypatch.setattr(cuenta_module, "decorate_orders_bingx", lambda _c, rows: rows)
    mx = ReadClient(orders=[{"orderId": "1"}], fail="orders")
    bitunix = ReadClient(orders=[{"orderId": "2"}])
    bingx = ReadClient(orders=[{"orderId": "3"}])
    app = _session(mx, bitunix, bingx)

    filas = app.ordenes_todas()

    assert [fila["orderId"] for fila in filas] == ["2", "3"]
    assert app.q.get_nowait() == ("error", "ordenes mexc: orders unavailable")


def test_contrato_mexc_fallido_no_se_cachea_y_se_puede_recuperar():
    cliente = Mexc("key", "secret")
    cliente.http = Http(
        [
            Response({"success": True, "data": None}),
            Response({"success": True, "data": {"symbol": "BTC_USDT"}}),
        ]
    )

    with pytest.raises(MexcError, match="no devolvio el contrato"):
        cliente.contract("BTC_USDT")
    assert cliente.cached_contract("BTC_USDT") is None
    assert cliente.contract("BTC_USDT") == {"symbol": "BTC_USDT"}


def test_catalogo_mexc_fallido_no_se_cachea_y_se_puede_recuperar():
    cliente = Mexc("key", "secret")
    cliente.http = Http(
        [
            Response({"success": False, "code": 510}),
            Response(
                {
                    "success": True,
                    "data": [{"symbol": "BTC_USDT", "state": 0, "apiAllowed": True}],
                }
            ),
        ]
    )

    with pytest.raises(MexcError):
        cliente.markets()
    assert cliente._markets is None
    assert cliente.markets() == {"BTC_USDT": {"symbol": "BTC_USDT", "state": 0, "apiAllowed": True}}


def test_respuesta_mexc_no_json_no_se_cachea():
    cliente = Mexc("key", "secret")

    class InvalidResponse:
        status_code = 200

        def json(self):
            raise ValueError("not json")

    cliente.http = Http([InvalidResponse()])
    with pytest.raises(MexcError, match="respuesta no JSON"):
        cliente.contract("BTC_USDT")
    assert cliente.cached_contract("BTC_USDT") is None


def test_fallo_al_escribir_log_se_avisa_sin_repetirlo(monkeypatch, tmp_path):
    app = object.__new__(Session)
    app.q = queue.Queue()
    app._log_lock = threading.Lock()
    app._log_error_reported = False
    monkeypatch.setattr(session_module.paths, "DATA_DIR", tmp_path)

    def no_escribir(*_args, **_kwargs):
        raise OSError("disco no disponible")

    monkeypatch.setattr(builtins, "open", no_escribir)
    app.log("evento")
    app.log("otro evento")

    assert app.q.get_nowait() == (
        "error",
        "No se pudo escribir trades.log: disco no disponible",
    )
    assert app.q.empty()
