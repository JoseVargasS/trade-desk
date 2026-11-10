"""Dobles de prueba: cliente MEXC sin red, mesa sin widgets y datos de ejemplo."""

import queue

from tradedesk import controller
from tradedesk.mexc import Mexc


class FakeMexc(Mexc):
    """Cliente sin red: `_post` guarda el payload, `_get` devuelve lo que se le pida."""

    def __init__(self, price=100.0, price_scale=2, stops=None):
        super().__init__("key", "secret")
        self.sent = []
        self.stops = stops or []
        self._fake_price = price
        self._fake_scale = price_scale

    def price(self, symbol):
        return self._fake_price

    def contract(self, symbol):
        return {
            "contractSize": 0.001,
            "volUnit": 1,
            "priceScale": self._fake_scale,
            "minVol": 1,
            "maxVol": 1_000_000,
            "baseCoinName": "GOLD(XAU)",
            "quoteCoinName": "USDT",
        }

    def known_contract(self, symbol):
        """Sin cache ni catalogo reales: el doble siempre conoce el contrato."""
        return self.contract(symbol)

    def tpsl_list(self):
        return self.stops

    def _post(self, path, payload):
        # hay endpoints con dict y otros con array (order/cancel): se copia igual
        copia = dict(payload) if isinstance(payload, dict) else list(payload)
        self.sent.append((path, copia))
        if path.endswith("/stoporder/cancel"):
            fuera = copia[0]["stopPlanOrderId"]
            self.stops = [s for s in self.stops if s.get("id") != fuera]
        return {"orderId": "test"}

    def _get(self, path, params=None):
        return []


def posicion(**extra):
    """Posicion LONG de 22 contratos, como la deja `decorate_positions`."""
    base = {
        "positionId": 1,
        "symbol": "XAU_USDT",
        "positionType": 1,
        "openType": 1,
        "holdVol": 22,
        "holdAvgPrice": 3990.5,
        "unRealizedPnl": -7.2633,
        "totalFee": 0.9993,
        "holdFee": -0.484,
        "liquidatePrice": 3611.8,
        "marginRatio": 0.005,
        "leverage": 10,
        "createTime": 1761800000000,
        "im": 500.69,
        "lowSaveTotalFee": 1.7489,
        "_contractSize": 0.001,
        "_volUnit": 1,
        "_priceScale": 2,
        "_name": "GOLD(XAU)USDT",
        "_takerRate": 0.0002,
        "_tp": 0.0,
        "_sl": 0.0,
        "_tpsl_id": None,
    }
    base.update(extra)
    return base


class InlineThread:
    """Hilo que corre en el acto: el test no espera a nadie."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self.target, self.args, self.kwargs = target, args or (), kwargs or {}

    def start(self):
        self.target(*self.args, **self.kwargs)


class FakeSession:
    """Sesión sin red: solo la cola, los precios y los refrescos."""

    def __init__(self, mx):
        self.mx = mx
        self.q = queue.Queue()
        self.precios = {}
        self.avisos = []
        self.refrescos = []

    def log(self, msg):
        pass

    def refresh_positions(self, broker=None):
        self.refrescos.append("positions")

    def refresh_orders(self, broker=None):
        self.refrescos.append("orders")

    def contract_for(self, symbol):
        return {}


class FakePort:
    """La ventana de la mesa, sin widgets: solo responde lo que se le pregunta."""

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


def control(mx, dry=False):
    """Control con la mesa falsa: sin red y sin ventana."""
    return controller.Control(FakeSession(mx), FakePort(), dry=lambda: dry)


def form_abrir():
    """Orden de mercado mínima, como la arma la tarjeta."""
    return {
        "symbol": "BTC_USDT",
        "notional": 100,
        "lev": 1,
        "open_type": 1,
        "tp": None,
        "sl": None,
        "price": None,
    }
