"""Dobles de prueba: cliente MEXC sin red y datos de ejemplo."""

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
