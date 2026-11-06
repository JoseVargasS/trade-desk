"""Parseo de los formularios: tarjeta y editor de orden. Sin ventanas."""

from tradedesk.forms import (
    form_tarjeta,
    limites_orden,
    orden_alcanza_minimo,
    valores_orden,
)


def test_la_tarjeta_arma_el_formulario():
    form = form_tarjeta("BTC_USDT", "10", "5", "", "", "Aislado", "Margen", 0.0)

    assert form["symbol"] == "BTC_USDT"
    assert form["lev"] == 10
    assert form["size"] == 5.0
    assert form["notional"] == 50.0
    assert form["open_type"] == 1
    assert form["price"] is None


def test_la_tarjeta_usa_el_nocional_en_modo_nocional():
    form = form_tarjeta("BTC_USDT", "10", "120", "", "", "Aislado", "Nocional", 0.0)

    assert form["notional"] == 120.0


def test_la_tarjeta_rechaza_texto_o_tamano_vacio():
    assert form_tarjeta("BTC_USDT", "10", "", "", "", "Aislado", "Margen", 0.0) is None
    assert form_tarjeta("BTC_USDT", "10", "5", "abc", "", "Aislado", "Margen", 0.0) is None
    assert form_tarjeta("BTC_USDT", "0", "5", "", "", "Aislado", "Margen", 0.0) is None


def test_la_tarjeta_pasa_el_precio_limite():
    form = form_tarjeta("BTC_USDT", "10", "5", "110,000", "90,000", "Cruzado", "Margen", 99.5)

    assert form["price"] == 99.5
    assert form["open_type"] == 2
    assert form["tp"] == 110000.0
    assert form["sl"] == 90000.0


def test_el_editor_de_orden_parsea_y_valida():
    assert valores_orden("10", "500", "104,200.0", "", "") == (10, 500.0, 104200.0, 0.0, 0.0)
    assert valores_orden("10", "0.0001", "104200", "", "") is not None
    assert valores_orden("0", "500", "104200", "", "") is None
    assert valores_orden("10", "0", "104200", "", "") is None
    assert valores_orden("10", "500", "", "", "") is None
    assert valores_orden("10", "500", "104200", "-1", "") is None


def test_limites_del_editor_respetan_unidades_y_pasos_por_broker():
    assert limites_orden("mexc", {"minVol": 2, "volUnit": 1}) == ("contratos", 2, 1, 0)
    assert limites_orden("bitunix", {"base": "BTC", "qtyStep": 0.0001}) == (
        "BTC",
        0.0001,
        0.0001,
        0,
    )
    assert limites_orden("bingx", {"base": "BTC", "minQty": 0.0001, "minNotional": 2}) == (
        "BTC",
        0.0001,
        0.0001,
        2,
    )


def test_editor_rechaza_tamano_bajo_minimo_o_fuera_del_paso():
    mexc = {"minVol": 2, "volUnit": 1, "contractSize": 0.001}
    bitunix = {"qtyStep": 0.0001, "contractSize": 1}
    bingx = {"minQty": 0.0001, "minNotional": 2, "contractSize": 1}

    assert orden_alcanza_minimo(2, 1000, "mexc", mexc)
    assert not orden_alcanza_minimo(1, 1000, "mexc", mexc)
    assert orden_alcanza_minimo(0.0002, 60000, "bitunix", bitunix)
    assert not orden_alcanza_minimo(0.00015, 60000, "bitunix", bitunix)
    assert orden_alcanza_minimo(0.0001, 60000, "bingx", bingx)
    assert not orden_alcanza_minimo(0.0001, 10000, "bingx", bingx)
