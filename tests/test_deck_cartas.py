"""El deck no debe dejar tarjetas fantasma ni duplicadas al borrar.

Reproduce el bug: al borrar una tarjeta su widget quedaba pegado en la
ventana y, al volver a agregar el mismo par, aparecian dos iguales.
"""

import queue

import pytest

from tradedesk.qt import ventana as ventana_mod


class FakeSession:
    """Session minima: el deck no necesita red para probarse."""

    def __init__(self):
        self.q = queue.Queue()
        self.precios = {}
        self.tarjetas = []
        self.hay = {"mexc": True, "bitunix": True, "bingx": True}
        self.mx = None
        self.bitunix = None
        self.bingx = None
        self.ver_historial = False
        self.saldos = {}
        self.fondos = {}
        self.mercados = {}

    def start(self):
        pass

    def stop(self):
        pass

    def clientes(self):
        return {"mexc": None, "bitunix": None, "bingx": None}

    def contract_for(self, _symbol):
        return {}

    def _pub(self, tarjeta):
        return {
            **tarjeta,
            "precio": 75000.0,
            "contrato": {},
            "nombre": tarjeta["symbol"].replace("_", ""),
        }

    def publicar(self):
        self.q.put(("cards", [self._pub(t) for t in self.tarjetas]))

    def add_card(self, symbol):
        ident = symbol
        numero = 2
        while any(t["id"] == ident for t in self.tarjetas):
            ident = f"{symbol}#{numero}"
            numero += 1
        self.tarjetas.append(
            {
                "id": ident,
                "symbol": symbol,
                "exchange": "bingx",
                "leverage": "10",
                "margin": "Aislado",
                "size_mode": "Margen",
            }
        )
        self.publicar()

    def remove_card(self, ident):
        self.tarjetas = [t for t in self.tarjetas if t["id"] != ident]
        self.publicar()

    def set_exchange(self, ident, exchange):
        for tarjeta in self.tarjetas:
            if tarjeta["id"] == ident:
                tarjeta["exchange"] = exchange

    def mover_tarjeta(self, ident, indice):
        actual = next((i for i, t in enumerate(self.tarjetas) if t["id"] == ident), None)
        if actual is None:
            return
        tarjeta = self.tarjetas.pop(actual)
        self.tarjetas.insert(max(0, min(indice, len(self.tarjetas))), tarjeta)


def _tarjeta(symbol, ident=None, exchange="bingx"):
    return {
        "id": ident or symbol,
        "symbol": symbol,
        "exchange": exchange,
        "leverage": "10",
        "margin": "Aislado",
        "size_mode": "Margen",
    }


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def vista(qapp, monkeypatch):
    monkeypatch.setattr(ventana_mod, "Session", FakeSession)
    # el aviso de claves no debe aparecer en el test
    monkeypatch.setattr(ventana_mod.VistaQt, "_pedir_key", lambda self: None)
    ventana = ventana_mod.VistaQt()
    yield ventana
    ventana.close()
    ventana.deleteLater()


def _visibles(vista):
    return [w for w in vista._lienzo.children() if hasattr(w, "tarjeta") and not w.isHidden()]


def _ids(vista):
    return [w.tarjeta["id"] for w in _visibles(vista)]


def test_borrar_una_tarjeta_no_deja_fantasmas(vista):
    sesion = vista.session
    sesion.tarjetas = [_tarjeta("BTC_USDT"), _tarjeta("ETH_USDT", exchange="bitunix")]
    sesion.publicar()
    vista._drenar()
    assert sorted(_ids(vista)) == ["BTC_USDT", "ETH_USDT"]

    vista._quitar_par("BTC_USDT")
    vista._drenar()

    assert _ids(vista) == ["ETH_USDT"]
    assert [t["id"] for t in sesion.tarjetas] == ["ETH_USDT"]


def test_re_agregar_el_mismo_par_no_deja_dos_tarjetas(vista):
    sesion = vista.session
    sesion.tarjetas = [_tarjeta("BTC_USDT"), _tarjeta("ETH_USDT", exchange="bitunix")]
    sesion.publicar()
    vista._drenar()

    vista._quitar_par("BTC_USDT")
    vista._drenar()
    sesion.add_card("BTC_USDT")
    vista._drenar()

    assert sorted(_ids(vista)) == ["BTC_USDT", "ETH_USDT"]
    assert len([i for i in _ids(vista) if i == "BTC_USDT"]) == 1


def test_un_snapshot_atrasado_no_resucita_una_tarjeta_borrada(vista):
    sesion = vista.session
    sesion.tarjetas = [_tarjeta("BTC_USDT"), _tarjeta("ETH_USDT", exchange="bitunix")]
    sesion.publicar()
    vista._drenar()
    vista._quitar_par("BTC_USDT")
    vista._drenar()

    # llega un mensaje armado antes del borrado
    sesion.q.put(
        (
            "cards",
            [
                sesion._pub(_tarjeta("BTC_USDT")),
                sesion._pub(_tarjeta("ETH_USDT", exchange="bitunix")),
            ],
        )
    )
    vista._drenar()

    assert _ids(vista) == ["ETH_USDT"]


def test_arrastrar_no_crea_tarjetas(vista):
    sesion = vista.session
    sesion.tarjetas = [_tarjeta("BTC_USDT"), _tarjeta("ETH_USDT", exchange="bitunix")]
    sesion.publicar()
    vista._drenar()

    btc = vista._tarjetas["BTC_USDT"]
    vista._arrastre_tarjeta(btc, "inicio", ventana_mod.QPoint(10, 10))
    vista._arrastre_tarjeta(btc, "mover", ventana_mod.QPoint(600, 10))
    vista._arrastre_tarjeta(btc, "fin")
    vista._drenar()

    assert sorted(_ids(vista)) == ["BTC_USDT", "ETH_USDT"]
    assert len(sesion.tarjetas) == 2
