import queue

from tradedesk import session as session_module
from tradedesk.session import Session


class StopAfterWait:
    def __init__(self):
        self.stopped = False
        self.delays = []

    def is_set(self):
        return self.stopped

    def wait(self, delay):
        self.delays.append(delay)
        self.stopped = True
        return True


def _session():
    app = object.__new__(Session)
    app._parar = StopAfterWait()
    app.q = queue.Queue()
    return app


def test_poller_de_ticker_no_consulta_posiciones_ni_ordenes():
    app = _session()
    app.tarjetas = [{"symbol": "BTC_USDT", "id": "BTC_USDT", "exchange": "mexc"}]
    app.precios = {}

    class Cliente:
        def ticker(self, _symbol):
            return {"lastPrice": 100, "riseFallRate": 0.01}

    app.cliente = lambda _exchange: Cliente()
    app.posiciones_todas = lambda: (_ for _ in ()).throw(AssertionError("cuenta en ticker"))
    app.ordenes_todas = app.posiciones_todas

    app._poll()

    assert app.precios == {"BTC_USDT": 100}
    assert app.q.get_nowait() == ("ticker", "BTC_USDT", 100, 1)


def test_poller_de_cuenta_actualiza_posiciones_y_ordenes_en_ciclo_aparte():
    app = _session()
    app.ultimas_posiciones = []
    app.posiciones_todas = lambda: [{"symbol": "BTC_USDT"}]
    app.ordenes_todas = lambda: [{"orderId": "123"}]

    app._poll_cuenta()

    assert app.ultimas_posiciones == [{"symbol": "BTC_USDT"}]
    assert app.q.get_nowait() == ("positions", [{"symbol": "BTC_USDT"}])
    assert app.q.get_nowait() == ("orders", [{"orderId": "123"}])


def test_fallo_de_cuenta_aplica_backoff_sin_retrasar_ticker():
    app = _session()
    app.posiciones_todas = lambda: (_ for _ in ()).throw(RuntimeError("sin conexión"))
    app.ordenes_todas = lambda: [{"orderId": "123"}]

    app._poll_cuenta()

    assert app.q.get_nowait() == ("error", "posiciones: sin conexión")
    assert app.q.get_nowait() == ("orders", [{"orderId": "123"}])
    assert 4.9 <= app._parar.delays[0] <= 5.0


def test_poller_secundario_mantiene_cadencias_fuera_del_ticker(monkeypatch):
    app = _session()
    app.ver_historial = True
    llamadas = []
    monkeypatch.setattr(session_module.time, "monotonic", lambda: 1000.0)
    monkeypatch.setattr(session_module, "SALDOS_SEG", 0)
    monkeypatch.setattr(session_module, "FONDOS_SEG", 0)
    monkeypatch.setattr(session_module, "IP_SEG", 0)
    app.cargar_historial = lambda: llamadas.append("historial")
    app.refresh_saldos = lambda: llamadas.append("saldos")
    app.refresh_fondos = lambda: llamadas.append("funding")
    app._cargar_ip = lambda: llamadas.append("ip")

    app._poll_secundario()

    assert llamadas == ["historial", "saldos", "funding", "ip"]


def test_start_crea_workers_independientes(monkeypatch):
    app = _session()
    app._hilos = []
    objetivos = []

    class Thread:
        def __init__(self, target, daemon):
            objetivos.append((target.__name__, daemon))

        def start(self):
            pass

    monkeypatch.setattr(session_module.threading, "Thread", Thread)

    assert app.start() is app
    assert {nombre for nombre, _daemon in objetivos} >= {
        "_poll",
        "_poll_cuenta",
        "_poll_secundario",
    }
    assert all(daemon for _nombre, daemon in objetivos)
