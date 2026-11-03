"""Cierre parcial: contratos enteros en MEXC y step del par en Bitunix."""

from tradedesk.forms import volumen_cerrar


def test_mexc_cierra_contratos_enteros():
    assert volumen_cerrar(22, 50, 1) == 11
    assert volumen_cerrar(22, 100, 1) == 22
    assert volumen_cerrar(3, 10, 1) == 0  # no llega a un contrato


def test_bitunix_cierra_por_step():
    assert volumen_cerrar(0.0003, 50, 0.0001) == 0.0001
    assert volumen_cerrar(0.0003, 34, 0.0001) == 0.0001
    assert volumen_cerrar(0.0003, 100, 0.0001) == 0.0003
    assert volumen_cerrar(0.0003, 10, 0.0001) == 0.0


def test_cien_por_ciento_es_exacto():
    # un cierre total no puede fallar por redondeo
    assert volumen_cerrar(7.3, 100, 1) == 7.3
    assert volumen_cerrar(0.123456, 100, 0.0001) == 0.123456


def test_sin_posicion_no_cierra_nada():
    assert volumen_cerrar(0, 50, 1) == 0.0
    assert volumen_cerrar(10, 0, 1) == 0.0
