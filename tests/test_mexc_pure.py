"""Logica pura de MEXC: nombres, TP/SL, contratos a cerrar y decoracion."""

import pytest

from tests.fakes import FakeMexc
from tradedesk.mexc import (
    MexcError,
    break_even_price,
    close_vol,
    decorate_positions,
    display_name,
    fee_desglose,
    mark_price,
    neto_posicion,
    plan_tp_sl,
    pnl_en_precio,
    precio_por_pnl,
    resumen_pnl,
)


def test_display_name_como_mexc():
    assert display_name({"baseCoinName": "GOLD(XAU)", "quoteCoinName": "USDT"}) == "GOLD(XAU)USDT"
    assert display_name({"symbol": "BTC_USDT", "displayNameEn": "BTC_USDT PERPETUAL"}) == "BTCUSDT"
    assert display_name({}) == ""


def test_tp_sl_long_y_short():
    # LONG: TP arriba, SL abajo. Se mide contra el precio actual, no la entrada.
    assert plan_tp_sl(True, 100, 110, 90) == (110.0, 90.0, [])
    assert plan_tp_sl(False, 100, 90, 110) == (90.0, 110.0, [])


def test_sl_del_lado_de_la_ganancia_se_guarda_como_tp():
    tp, sl, avisos = plan_tp_sl(True, 100, None, 105)
    assert (tp, sl) == (105.0, None)
    assert avisos, "tiene que avisar que la posicion queda sin SL"

    tp, sl, avisos = plan_tp_sl(False, 100, None, 95)
    assert (tp, sl) == (95.0, None)
    assert avisos


@pytest.mark.parametrize(
    "args",
    [
        (True, 100, 110, 105),  # TP y SL del lado de la ganancia
        (True, 100, 95, 90),  # TP del lado de la perdida
        (True, 100, 100, None),  # TP en el precio actual
        (False, 100, 110, None),  # SHORT con TP arriba
        (False, 100, 95, 98),  # SL del lado de la ganancia con TP puesto
    ],
)
def test_tp_sl_imposibles_se_rechazan(args):
    with pytest.raises(MexcError):
        plan_tp_sl(*args)


def test_close_vol_total_es_exacto_y_parcial_baja_al_contrato():
    assert close_vol(127, 100) == 127, "100% no redondea"
    assert close_vol(127, None) == 127, "sin tocar nada = 100%"
    assert close_vol(127, 50) == 63
    assert close_vol(127, 33) == 41
    assert close_vol(127, 150) == 127, "no se puede cerrar de mas"
    assert close_vol(3, 10) == 0, "menos de un contrato lo rechaza la accion"
    assert close_vol(22, -5) == 0


def test_decorate_positions_agrega_contrato_y_tp_sl():
    mx = FakeMexc(price_scale=3)
    mx.stops = [{"positionId": 1, "takeProfitPrice": "4100", "stopLossPrice": 3800, "id": 77}]
    pos = decorate_positions(mx, [{"positionId": 1, "symbol": "XAU_USDT"}])[0]

    assert pos["_contractSize"] == 0.001
    assert pos["_volUnit"] == 1
    assert pos["_priceScale"] == 3
    assert pos["_name"] == "GOLD(XAU)USDT"
    assert (pos["_tp"], pos["_sl"], pos["_tpsl_id"]) == (4100.0, 3800.0, 77)


def test_decorate_positions_aguanta_un_contrato_que_falla():
    class SinContrato(FakeMexc):
        def contract(self, symbol):
            raise MexcError("sin red")

    errores = []
    pos = decorate_positions(
        SinContrato(),
        [{"positionId": 2, "symbol": "BTC_USDT"}],
        on_error=lambda recurso, exc: errores.append((recurso, exc)),
    )[0]
    assert pos["_contractSize"] == 0
    assert pos["_volUnit"] == 1
    assert pos["_priceScale"] == 2
    assert pos["_name"] == "BTC_USDT"
    assert pos["_tp"] == 0.0 and pos["_sl"] == 0.0 and pos["_tpsl_id"] is None
    assert errores and errores[0][0] == "contrato"


def test_la_fee_es_comision_mas_funding():
    """MEXC suma `totalFee` (comision) + `holdFee` (funding); el ahorro no suma."""
    detalle = fee_desglose({"totalFee": 0.9993, "holdFee": -0.484, "lowSaveTotalFee": 1.7489})
    assert detalle["comision"] == pytest.approx(0.9993)
    assert detalle["funding"] == pytest.approx(0.484)
    assert detalle["total"] == pytest.approx(1.4833)
    assert detalle["ahorro"] == pytest.approx(1.7489), "el ahorro se muestra, no suma"


def test_la_fee_aguanta_una_posicion_recien_abierta():
    detalle = fee_desglose({"totalFee": 0.2})
    assert (detalle["comision"], detalle["funding"], detalle["total"]) == (0.2, 0.0, 0.2)
    assert detalle["ahorro"] == 0.0


def _pos(**extra):
    """Posicion base para las cuentas de break-even: 100 USDT de nocional."""
    base = {
        "positionType": 1,
        "holdVol": 10,
        "holdAvgPrice": 100.0,
        "_contractSize": 1.0,
        "_priceScale": 2,
        "totalFee": 0.2,
        "holdFee": -0.1,
    }
    base.update(extra)
    return base


def test_mark_price_sale_del_pnl():
    # +1 USDT sobre 10 contratos de 1 moneda = 0.10 por moneda
    assert mark_price(_pos(unRealizedPnl=1.0)) == pytest.approx(100.1)
    corto = _pos(positionType=2, unRealizedPnl=1.0)
    assert mark_price(corto) == pytest.approx(99.9), "en SHORT la ganancia va al reves"


def test_pnl_en_precio_long_y_short():
    assert pnl_en_precio(_pos(), True, 103) == pytest.approx(30.0)
    assert pnl_en_precio(_pos(), False, 103) == pytest.approx(-30.0)


def test_break_even_cubre_comision_entrada_salida_y_funding():
    """Con 0.2 de comision y 0.1 de funding, el SL tiene que dejar el neto en cero."""
    be, cubre = break_even_price(_pos(), True)
    assert be > 100, "el SL de un LONG se pone arriba de la entrada"
    assert be == pytest.approx(100.06), "redondea hacia arriba al tick"
    assert cubre == pytest.approx(10 * (be - 100), rel=1e-9)
    # neto = PnL - (comision + funding + comision de salida): nunca negativo y
    # como mucho un tick de mas (lo que agrega el redondeo)
    salida = 0.2 / (10 * 100) * (10 * be)
    neto = cubre - (0.2 + 0.1 + salida)
    assert 0 <= neto < 0.01 * 10


def test_break_even_short_va_debajo_y_redondea_hacia_afuera():
    be, cubre = break_even_price(_pos(positionType=2), False)
    assert be < 100
    assert be == pytest.approx(99.95), "floor: el tick nunca deja perdida"
    salida = 0.2 / (10 * 100) * (10 * be)
    assert 0 <= cubre - (0.2 + 0.1 + salida) < 0.01 * 10


def test_break_even_sin_tamano_no_inventa_un_precio():
    assert break_even_price(_pos(holdVol=0), True) == (None, 0.0)
    assert break_even_price(_pos(holdAvgPrice=0), True) == (None, 0.0)


def test_precio_por_pnl_es_sobre_el_margen():
    """El % del TP/SL se mide sobre el margen: 15% a 10x = 1,5% de precio."""
    assert precio_por_pnl(100.0, "15", 10, True, 2) == "101.50"
    assert precio_por_pnl(100.0, "-15", 10, True, 2) == "98.50"
    assert precio_por_pnl(100.0, "15", 10, False, 2) == "98.50"
    assert precio_por_pnl(100.0, "-8", 10, False, 2) == "100.80"
    assert precio_por_pnl(100.0, "7,5", 5, True, 2) == "115.00"


def test_precio_por_pnl_sin_datos_no_inventa():
    assert precio_por_pnl(100.0, "", 10, True) == ""
    assert precio_por_pnl(100.0, "abc", 10, True) == ""
    assert precio_por_pnl(0, "15", 10, True) == ""
    # -200% a 10x sería un precio negativo: no se inventa nada
    assert precio_por_pnl(100.0, "-2000", 10, True) == ""


def test_neto_descuenta_comision_funding_y_salida():
    """Neto = bruto − comisión pagada − funding − salida estimada."""
    pos = {
        "unRealizedPnl": 10.0,
        "totalFee": 1.0,
        "holdFee": 0.5,
        "holdVol": 1.0,
        "_contractSize": 1.0,
        "holdAvgPrice": 1000.0,
        "_takerRate": 0.001,
    }
    fila = neto_posicion(pos)
    assert round(fila["comision"], 4) == 1.0
    assert round(fila["funding"], 4) == 0.5
    assert round(fila["salida"], 4) == 1.0  # 1000 de nocional por la tasa
    assert round(fila["neto"], 4) == 7.5


def test_neto_sin_taker_usa_la_tasa_efectiva_de_la_comision():
    pos = {
        "unRealizedPnl": 10.0,
        "totalFee": 2.0,
        "holdVol": 1.0,
        "_contractSize": 1.0,
        "holdAvgPrice": 1000.0,
    }
    fila = neto_posicion(pos)
    # tasa efectiva 2/1000 = 0.002 -> salida 2.0
    assert round(fila["salida"], 4) == 2.0
    assert round(fila["neto"], 4) == 6.0


def test_resumen_pnl_suma_todas_las_posiciones():
    una = {
        "unRealizedPnl": 10.0,
        "totalFee": 1.0,
        "holdVol": 1.0,
        "holdAvgPrice": 1000.0,
        "_contractSize": 1.0,
        "_takerRate": 0.001,
    }
    otra = {
        "unRealizedPnl": -4.0,
        "totalFee": 1.0,
        "holdVol": 1.0,
        "holdAvgPrice": 1000.0,
        "_contractSize": 1.0,
        "_takerRate": 0.001,
    }
    total = resumen_pnl([una, otra])
    assert total["cuantas"] == 2
    assert round(total["bruto"], 4) == 6.0
    # por posición: comisión 1 + salida 1 (sin funding) = 2
    assert round(total["costo"], 4) == 4.0
    assert round(total["neto"], 4) == 2.0


def test_resumen_pnl_vacio_no_rompe():
    total = resumen_pnl([])
    assert total["cuantas"] == 0
    assert total["neto"] == 0.0
