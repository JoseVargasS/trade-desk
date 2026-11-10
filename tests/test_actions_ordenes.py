"""Cancelación y edición de órdenes. Sin Tk y sin red."""


def test_cancelar_publica_confirmacion_visible(app):
    app.cancelar(
        {
            "orderId": "123",
            "symbol": "XAU_USDT",
            "side": 1,
            "orderType": 1,
            "price": 4000,
            "vol": 2,
            "_exchange": "mexc",
        }
    )

    assert app.q.get_nowait() == ("status", "1 orden(es) cancelada(s) en mexc.")
    assert app.mx.sent[-1][0].endswith("/order/cancel")


def test_fallo_al_cancelar_publica_error_visible(app):
    def rechazar(_ids):
        raise RuntimeError("API no disponible")

    app.mx.cancel = rechazar
    app.cancelar(
        {
            "orderId": "123",
            "symbol": "XAU_USDT",
            "side": 1,
            "orderType": 1,
            "price": 4000,
            "vol": 2,
            "_exchange": "mexc",
        }
    )

    assert app.q.get_nowait() == ("error", "Error al cancelar en mexc: API no disponible")


def test_orden_condicional_bingx_no_se_puede_editar(app):
    app.modificar(
        {
            "_exchange": "bingx",
            "type": "STOP_MARKET",
            "side": 1,
        }
    )

    assert app.port.mensajes == ["Las condicionales TP/SL de BingX se gestionan desde Posiciones."]
