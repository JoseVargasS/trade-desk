import queue
import threading
import time

from tradedesk import session as session_module
from tradedesk.session import Session


class StopAfterWait:
    def __init__(self, after=1):
        self.stopped = False
        self.delays = []
        self.after = after

    def is_set(self):
        return self.stopped

    def wait(self, delay):
        self.delays.append(delay)
        self.stopped = len(self.delays) >= self.after
        return True


def _session():
    app = object.__new__(Session)
    app._parar = StopAfterWait()
    app.q = queue.Queue()
    app._candado_tarjetas = threading.Lock()
    app.precios_par = {}
    return app


def test_el_precio_guardado_sirve_solo_si_es_fresco():
    """Un precio viejo no puede decidir el lado del TP/SL: mejor no usarlo."""
    app = _session()
    app.precios_par = {("mexc", "BTCUSDT"): (100.0, time.monotonic())}

    assert app.precio_de("mexc", "BTC_USDT") == 100.0

    app.precios_par[("mexc", "BTCUSDT")] = (100.0, time.monotonic() - 10)
    assert app.precio_de("mexc", "BTC_USDT") is None


def test_poller_de_ticker_no_consulta_posiciones_ni_ordenes():
    app = _session()
    app.tarjetas = [{"symbol": "BTC_USDT", "id": "BTC_USDT", "exchange": "mexc"}]
    app.precios = {}

    class Cliente:
        def ticker(self, _symbol):
            return {"lastPrice": 100, "riseFallRate": 0.01}

    app.mx = Cliente()
    app.posiciones_todas = lambda: (_ for _ in ()).throw(AssertionError("cuenta en ticker"))
    app.ordenes_todas = app.posiciones_todas

    app._poll("mexc")

    assert app.precios == {"BTC_USDT": 100}
    # el precio tambien queda por par y broker: lo usan las órdenes y el TP/SL
    assert app.precios_par[("mexc", "BTCUSDT")][0] == 100
    assert app.q.get_nowait() == ("ticker", "BTC_USDT", "mexc", 100, 1)


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

    app.mx = Cliente()
    app.bitunix = Cliente()

    app._poll("mexc")

    assert set(app.precios) == {"BTC_USDT"}
    assert app.q.get_nowait() == ("ticker", "BTC_USDT", "mexc", 100, 1)


def test_poller_rota_entre_todas_las_tarjetas_del_mismo_broker():
    app = _session()
    app._parar = StopAfterWait(after=2)
    app.tarjetas = [
        {"symbol": "BTC_USDT", "id": "BTC_USDT", "exchange": "bitunix"},
        {"symbol": "XAU_USDT", "id": "XAU_USDT", "exchange": "bitunix"},
    ]
    app.precios = {}

    class Cliente:
        def ticker(self, symbol):
            return {"lastPrice": 100 if symbol == "BTC_USDT" else 4000, "open": 100}

    app.bitunix = Cliente()

    app._poll("bitunix")

    eventos = [app.q.get_nowait(), app.q.get_nowait()]
    assert [evento[1] for evento in eventos] == ["BTC_USDT", "XAU_USDT"]
    assert app.precios == {"BTC_USDT": 100, "XAU_USDT": 4000}


def test_ticker_publico_de_bitunix_no_requiere_clave_api():
    app = _session()
    app.tarjetas = [{"symbol": "XAU_USDT", "id": "XAU_USDT", "exchange": "bitunix"}]
    app.precios = {}

    class Cliente:
        def ticker(self, symbol):
            assert symbol == "XAU_USDT"
            return {"lastPrice": "4072.8", "open": "4081.0"}

    app.bitunix = Cliente()
    app.hay = {"bitunix": False}
    app.cliente = lambda _exchange: None

    app._poll("bitunix")

    assert app.precios == {"XAU_USDT": 4072.8}
    evento = app.q.get_nowait()
    assert evento[:4] == ("ticker", "XAU_USDT", "bitunix", 4072.8)
    assert abs(evento[4] + 0.20093) < 1e-4


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
    app.precios_par = {}
    app.tarjetas = [
        {"symbol": "BTC_USDT", "id": "BTC_USDT", "exchange": "mexc"},
        {"symbol": "BTC_USDT", "id": "BTC_USDT#2", "exchange": "bitunix"},
    ]
    app.mx = Colgado()
    app.bitunix = Vivo()

    hilos = [
        threading.Thread(target=app._poll, args=("mexc",), daemon=True),
        threading.Thread(target=app._poll, args=("bitunix",), daemon=True),
    ]
    for hilo in hilos:
        hilo.start()
    try:
        # el unico precio que llega es el de Bitunix, con MEXC todavia colgado
        assert app.q.get(timeout=5.0) == ("ticker", "BTC_USDT#2", "bitunix", 55, 10.0)
        assert set(app.precios) == {"BTC_USDT#2"}
    finally:
        parado.set()
        app._parar.set()
        for hilo in hilos:
            hilo.join(timeout=5.0)


def test_catalogo_publica_disponibilidad_de_futuros_sin_claves():
    app = _session()
    app.mercados = {}

    class MexcCatalogo:
        def markets(self):
            return {"XAU_USDT": {}, "BTC_USDT": {}}

    class BitunixCatalogo:
        def trading_pairs(self):
            return [
                {"symbol": "XAUUSDT", "symbolStatus": "OPEN", "isApiSupported": True},
                {"symbol": "CLOSEDUSDT", "symbolStatus": "CLOSED", "isApiSupported": True},
                {"symbol": "NOAPIUSDT", "symbolStatus": "OPEN", "isApiSupported": False},
            ]

    class BingxCatalogo:
        def contracts(self):
            return [
                {"symbol": "XAUT-USDT", "status": 1, "apiStateOpen": "true"},
                {"symbol": "PAXG-USDT", "status": 1, "apiStateOpen": "true"},
                {"symbol": "XAU-USDT", "status": 25, "apiStateOpen": "true"},
            ]

    app.mx = MexcCatalogo()
    app.bitunix = BitunixCatalogo()
    app.bingx = BingxCatalogo()

    app._cargar_catalogo()

    disponibilidad = {}
    while not app.q.empty():
        mensaje = app.q.get_nowait()
        if mensaje[0] == "market_availability":
            disponibilidad[mensaje[1]] = mensaje[2]
    assert disponibilidad == {
        "mexc": {"XAUUSDT", "BTCUSDT"},
        "bitunix": {"XAUUSDT"},
        "bingx": {"XAUTUSDT", "PAXGUSDT"},
    }


def test_cambio_de_broker_descarta_un_ticker_que_quedo_en_vuelo():
    app = _session()
    app.tarjetas = [{"symbol": "XAU_USDT", "id": "XAU_USDT", "exchange": "mexc"}]
    app.precios = {"XAU_USDT": 4072.8}

    class Cliente:
        def ticker(self, _symbol):
            app.tarjetas[0]["exchange"] = "bingx"
            return {"lastPrice": 4072.8, "riseFallRate": 0.01}

    app.mx = Cliente()

    app._poll("mexc")

    assert app.precios == {"XAU_USDT": 4072.8}
    assert app.q.empty()


def test_cambiar_broker_invalida_el_precio_cacheado():
    app = _session()
    app.tarjetas = [{"symbol": "XAU_USDT", "id": "XAU_USDT", "exchange": "mexc"}]
    app.precios = {"XAU_USDT": 4072.8}
    app._guardar_config = lambda: None

    app.set_exchange("XAU_USDT", "bitunix")

    assert app.tarjetas[0]["exchange"] == "bitunix"
    assert "XAU_USDT" not in app.precios


def test_poller_de_cuenta_actualiza_posiciones_y_ordenes_en_ciclo_aparte():
    app = _session()
    app.ultimas_posiciones = []
    app.posiciones_todas = lambda: [{"symbol": "BTC_USDT"}]
    app.ordenes_todas = lambda: [{"orderId": "123"}]

    app._poll_cuenta()

    assert app.ultimas_posiciones == [{"symbol": "BTC_USDT"}]
    assert app.q.get_nowait() == ("positions", [{"symbol": "BTC_USDT"}])
    assert app.q.get_nowait() == ("orders", [{"orderId": "123"}])


def test_cargar_historial_actualiza_una_orden_ya_vista(monkeypatch):
    existente = {
        "_exchange": "mexc",
        "orderId": "1",
        "positionId": "7",
        "symbol": "BTC_USDT",
        "side": 1,
        "dealVol": 1,
        "dealAvgPrice": 100,
        "totalFee": 0.1,
        "createTime": 1000,
    }
    reciente = {**existente, "totalFee": 0.2}

    class Cliente:
        def history(self, _limite, _pagina):
            return [reciente]

    class Archivo:
        def fusionar(self, filas):
            self.filas = filas
            return filas

    app = _session()
    app.mx = Cliente()
    app.bitunix = object()
    app.bingx = object()
    app.cliente = lambda exchange: app.mx if exchange == "mexc" else None
    app._hist_candado = threading.Lock()
    app._hist_pagina = 0
    app._hist_ordenes = {("mexc", "1"): existente}
    app.historial_hay_mas = {"mexc": True, "bitunix": False, "bingx": False}
    app.archivo = Archivo()
    app._publicar_estado_archivo = lambda: None
    monkeypatch.setattr(session_module, "decorate_orders", lambda _mx, filas: filas)

    app.cargar_historial()

    assert app._hist_ordenes[("mexc", "1")]["totalFee"] == 0.2
    assert app.archivo.filas[0]["fee"] == 0.2


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
