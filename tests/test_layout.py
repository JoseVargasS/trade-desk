"""Medidas de las tablas: la fila de posiciones no crece (regla de AGENTS)."""

from tradedesk.layout import ACTION_W, ORDER_ACTION_W, ORDER_COLS, POS_COLS


def test_la_fila_de_posiciones_cabe_en_la_ventana():
    ancho = 30 + sum(columna[2] for columna in POS_COLS) + ACTION_W

    assert ancho <= 1650


def test_la_fila_de_ordenes_cabe_en_la_ventana():
    ancho = sum(columna[2] for columna in ORDER_COLS) + ORDER_ACTION_W

    assert ancho <= 1650
