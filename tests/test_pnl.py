"""Neto de una operación del historial: PnL realizado menos la fee cobrada."""

import pytest

from tradedesk.pnl import neto_operacion


def test_descuenta_la_fee():
    assert neto_operacion(10.0, 1.5) == pytest.approx(8.5)


def test_sin_fee_el_neto_es_el_pnl():
    assert neto_operacion(3.25, 0) == pytest.approx(3.25)


def test_un_rebate_suma():
    """Fee negativa = rebate: el neto queda por encima del PnL."""
    assert neto_operacion(2.0, -0.5) == pytest.approx(2.5)


def test_perdida_con_fee():
    assert neto_operacion(-4.0, 0.25) == pytest.approx(-4.25)


def test_valores_vacios_no_revientan():
    assert neto_operacion(None, None) == 0.0
    assert neto_operacion("2.5", "0.5") == pytest.approx(2.0)


def test_conserva_los_decimales_del_pnl():
    """La resta no redondea: el formato a 4 decimales lo hace la vista."""
    assert neto_operacion(0.123456, 0.000001) == pytest.approx(0.123455)
