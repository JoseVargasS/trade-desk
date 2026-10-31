"""Logica pura de MEXC: nombres, TP/SL, contratos a cerrar y decoracion."""

import pytest

from tests.fakes import FakeMexc
from tradedesk.mexc import (
    MexcError,
    close_vol,
    decorate_positions,
    display_name,
    fee_desglose,
    plan_tp_sl,
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

    pos = decorate_positions(SinContrato(), [{"positionId": 2, "symbol": "BTC_USDT"}])[0]
    assert pos["_contractSize"] == 0
    assert pos["_volUnit"] == 1
    assert pos["_priceScale"] == 2
    assert pos["_name"] == "BTC_USDT"
    assert pos["_tp"] == 0.0 and pos["_sl"] == 0.0 and pos["_tpsl_id"] is None


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
