"""Avisos: se muestran uno por vez y fuera de `_drain` (un modal no encola la UI)."""

from tradedesk import app as app_mod


class FakeRoot:
    """`after_idle` corre en el acto: el test no abre ventanas."""

    def after_idle(self, fn):
        fn()


def _app(monkeypatch, vistos):
    app = app_mod.App.__new__(app_mod.App)  # sin __init__: no toca red ni Tk
    app.root = FakeRoot()
    app._avisos = []
    app._aviso_abierto = False
    monkeypatch.setattr(
        app_mod.dialog, "show", lambda parent, title, text, **k: vistos.append(title)
    )
    return app


def test_los_avisos_salen_en_orden_uno_por_vez(monkeypatch):
    vistos = []
    app = _app(monkeypatch, vistos)

    app._notice("Orden enviada", "ok")
    app._notice("Orden rechazada", "5004", danger=True)

    assert vistos == ["Orden enviada", "Orden rechazada"]
    assert app._avisos == []
    assert app._aviso_abierto is False


def test_con_un_modal_abierto_los_avisos_se_encolan(monkeypatch):
    vistos = []
    app = _app(monkeypatch, vistos)
    app._aviso_abierto = True  # ya hay un dialogo en pantalla

    app._notice("nuevo", "y")

    assert vistos == [], "no abre un segundo modal encima"
    assert [a[0] for a in app._avisos] == ["nuevo"]
