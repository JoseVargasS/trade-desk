import queue
import types

import httpx

from tradedesk.controller import Control
from tradedesk.controller_lote import resumen_lote


class InlineThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}

    def start(self):
        self.target(*self.args, **self.kwargs)


class FakeClient:
    def __init__(self):
        self.sent = []
        self.failures = {}

    def price(self, _symbol):
        return 100

    def size_to_vol(self, _symbol, notional, _price):
        return notional

    def open_market(self, symbol, side, notional, *_args):
        self.sent.append((symbol, side, notional))
        fallo = self.failures.get(symbol)
        if fallo:
            raise fallo
        return {"orderId": f"id-{symbol}"}, notional, 100


class FakeSession:
    def __init__(self, cliente):
        self.mx = cliente
        self.q = queue.Queue()
        self.precios = {}
        self.ultimas_posiciones = []
        self.ultimas_ordenes = []
        self.logs = []
        self.refrescos = []

    def cliente(self, exchange):
        return self.mx if exchange == "mexc" else None

    def contract_for(self, _symbol):
        return {"priceScale": 2}

    def log(self, mensaje):
        self.logs.append(mensaje)

    def refresh_positions(self):
        self.refrescos.append("positions")

    def refresh_orders(self):
        self.refrescos.append("orders")


class FakePort:
    def __init__(self, confirmar=True):
        self.confirmar = confirmar
        self.confirmaciones = []
        self.avisos = []

    def confirm(self, *args, **kwargs):
        self.confirmaciones.append((args, kwargs))
        return self.confirmar


def _form(symbol):
    return {
        "symbol": symbol,
        "size": 5,
        "notional": 50,
        "lev": 10,
        "margin_mode": "Aislado",
        "size_mode": "Margen",
        "open_type": 1,
        "tp": None,
        "sl": None,
        "price": None,
    }


def _items(*symbols):
    return [{"side": "LONG", "form": _form(symbol), "exchange": "mexc"} for symbol in symbols]


def _control(monkeypatch, confirmar=True, dry=False):
    from tradedesk import controller as controller_mod
    from tradedesk import controller_lote as lote_mod

    monkeypatch.setattr(controller_mod, "threading", types.SimpleNamespace(Thread=InlineThread))
    monkeypatch.setattr(lote_mod, "threading", types.SimpleNamespace(Thread=InlineThread))
    cliente = FakeClient()
    session = FakeSession(cliente)
    port = FakePort(confirmar)
    control = Control(session, port, dry=lambda: dry)
    control.verificaciones = []
    control._iniciar_verificacion = lambda accion, comprobar: control.verificaciones.append(
        (accion, comprobar)
    )
    return control, cliente, port


def _mensajes(control, tipo):
    mensajes = []
    while not control.q.empty():
        mensaje = control.q.get_nowait()
        if mensaje[0] == tipo:
            mensajes.append(mensaje)
    return mensajes


def test_abrir_lote_confirma_una_vez_y_cancelado_no_envia(monkeypatch):
    control, cliente, port = _control(monkeypatch, confirmar=False)

    resultado = control.abrir_lote(_items("BTC_USDT", "ETH_USDT"))

    assert resultado is False
    assert len(port.confirmaciones) == 1
    assert cliente.sent == []
    assert _mensajes(control, "lote") == []


def test_abrir_lote_envia_en_orden_y_publica_un_solo_resultado(monkeypatch):
    control, cliente, port = _control(monkeypatch)

    control.abrir_lote(_items("BTC_USDT", "ETH_USDT", "SOL_USDT"))

    assert len(port.confirmaciones) == 1
    assert cliente.sent == [
        ("BTC_USDT", "LONG", 50),
        ("ETH_USDT", "LONG", 50),
        ("SOL_USDT", "LONG", 50),
    ]
    lotes = _mensajes(control, "lote")
    assert len(lotes) == 1
    assert [fila[2] for fila in lotes[0][1]["resultados"]] == ["ok"] * 3
    assert _mensajes(control, "notice") == []


def test_rechazo_de_una_orden_no_frena_el_resto(monkeypatch):
    control, cliente, _port = _control(monkeypatch)
    cliente.failures["ETH_USDT"] = ValueError("rechazo simulado")

    control.abrir_lote(_items("BTC_USDT", "ETH_USDT", "SOL_USDT"))
    datos = _mensajes(control, "lote")[0][1]

    assert [orden[0] for orden in cliente.sent] == ["BTC_USDT", "ETH_USDT", "SOL_USDT"]
    assert [fila[2] for fila in datos["resultados"]] == ["ok", "rechazada", "ok"]
    assert resumen_lote(datos["resultados"], False)[2] is True


def test_timeout_se_marca_desconocido_y_programa_verificacion(monkeypatch):
    control, cliente, _port = _control(monkeypatch)
    cliente.failures["BTC_USDT"] = httpx.ReadTimeout("timeout")

    control.abrir_lote(_items("BTC_USDT"))
    datos = _mensajes(control, "lote")[0][1]

    assert datos["resultados"][0][2] == "desconocida"
    assert control.verificaciones[0][0] == "apertura"
    assert control.session.refrescos == ["positions", "orders"]


def test_dry_run_no_envia_y_el_resumen_indica_que_no_se_envio(monkeypatch):
    control, cliente, _port = _control(monkeypatch, dry=True)

    control.abrir_lote(_items("BTC_USDT", "ETH_USDT"))
    datos = _mensajes(control, "lote")[0][1]
    titulo, mensaje, problema = resumen_lote(datos["resultados"], datos["dry"])

    assert cliente.sent == []
    assert datos["dry"] is True
    assert titulo == "DRY-RUN: no se envio nada"
    assert "2 ordenes" in mensaje
    assert problema is False


def test_abrir_individual_sigue_publicando_notice(monkeypatch):
    control, _cliente, _port = _control(monkeypatch, dry=True)

    control._do_abrir("LONG", _form("BTC_USDT"), True)

    assert len(_mensajes(control, "notice")) == 1


def test_resumen_lote_muestra_estado_y_problemas_por_orden():
    resultados = [
        ("BTC_USDT", "LONG", "ok", "enviado"),
        ("ETH_USDT", "SHORT", "rechazada", "saldo insuficiente"),
        ("ADA_USDT", "LONG", "broker", "broker desconectado"),
        ("SOL_USDT", "SHORT", "desconocida", "timeout"),
    ]

    titulo, mensaje, problema = resumen_lote(resultados, False)

    assert titulo == "Lote con problemas"
    assert "✓ BTC_USDT LONG: enviada" in mensaje
    assert "✗ ETH_USDT SHORT: saldo insuficiente" in mensaje
    assert "✗ ADA_USDT LONG: broker desconectado" in mensaje
    assert (
        "? SOL_USDT SHORT: estado desconocido, revisa Posiciones y Órdenes antes de reintentar"
        in mensaje
    )
    assert problema is True


def test_excepcion_inesperada_tambien_publica_resultado_de_lote(monkeypatch):
    control, _cliente, _port = _control(monkeypatch)

    def falla(*_args, **_kwargs):
        raise RuntimeError("error inesperado")

    control._do_abrir = falla
    control.abrir_lote(_items("BTC_USDT"))

    lotes = _mensajes(control, "lote")
    assert len(lotes) == 1
    assert lotes[0][1]["resultados"][0][2:] == ("rechazada", "error inesperado")
