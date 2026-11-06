import queue
import threading

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
    app._candado_tarjetas = threading.Lock()
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

    app._poll("mexc")

    assert app.precios == {"BTC_USDT": 100}
    assert app.q.get_nowait() == ("ticker", "BTC_USDT", 100, 1)


def test_poller_solo_mira_las_tarjetas_de_su_broker():
    app = _session()
    app.tarjetas = [
        {"symbol": "BTC_USDT", "id": "BTC_USDT", "exchange": "mexc"},
        {"symbol": "ETH_USDT", "id": "ETH_USDT", "exchange": "bitunix"},
    ]
    app.precios = {}

    class Cliente:
        def ticker(self, symbol):
            return {"lastPrice": 100, "riseFallRate": 0.01}

    app.cliente = lambda exchange: Cliente() if exchange == "mexc" else None

    app._poll("mexc")

    assert set(app.precios) == {"BTC_USDT"}
    assert app.q.get_nowait() == ("ticker", "BTC_USDT", 100, 1)


def test_un_broker_colgado_no_congela_los_precios_de_los_demas():
    """La prueba que motiva el hilo por broker: MEXC colgado, Bitunix al tanto."""
    parado = threading.Event()

    class Colgado:
        def ticker(self, _symbol):
            parado.wait(5.0)
            return {}

    class Vivo:
        def ticker(self, _symbol):
            return {"lastPrice": 55, "open": 50}

    app = object.__new__(Session)
    app.q = queue.Queue()
    app._parar = threading.Event()
    app._candado_tarjetas = threading.Lock()
    app.precios = {}
    app.tarjetas = [
        {"symbol": "BTC_USDT", "id": "BTC_USDT", "exchange": "mexc"},
        {"symbol": "BTC_USDT", "id": "BTC_USDT#2", "exchange": "bitunix"},
    ]
    app.cliente = lambda exchange: Colgado() if exchange == "mexc" else Vivo()

    hilos = [
        threading.Thread(target=app._poll, args=("mexc",), daemon=True),
        threading.Thread(target=app._poll, args=("bitunix",), daemon=True),
    ]
    for hilo in hilos:
        hilo.start()
    try:
        # el unico precio que llega es el de Bitunix, con MEXC todavia colgado
        assert app.q.get(timeout=5.0) == ("ticker", "BTC_USDT#2", 55, 10.0)
        assert set(app.precios) == {"BTC_USDT#2"}
    finally:
        parado.set()
        app._parar.set()
        for hilo in hilos:
            hilo.join(timeout=5.0)


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
        def __init__(self, target, daemon, args=()):
            objetivos.append((target.__name__, args, daemon))

        def start(self):
            pass

    monkeypatch.setattr(session_module.threading, "Thread", Thread)

    assert app.start() is app
    nombres = {nombre for nombre, _args, _daemon in objetivos}
    assert "_poll_cuenta" in nombres and "_poll_secundario" in nombres
    # un hilo de precios por broker, cada uno con su broker como argumento
    assert sorted(args[0] for _n, args, _d in objetivos if _n == "_poll") == [
        "bingx",
        "bitunix",
        "mexc",
    ]
    assert all(daemon for _nombre, _args, daemon in objetivos)
