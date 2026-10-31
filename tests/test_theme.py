"""Formatos numericos: una sola fuente de verdad para lo que se pinta."""

from tradedesk import theme


def test_formatos_base():
    assert theme.fmt_pnl(12.40213) == "+12.4021"
    assert theme.fmt_pnl(-3.15) == "-3.1500"
    assert theme.fmt_fee(0.199533256) == "0.1995"
    assert theme.fmt_usdt(502.81124404) == "502.81"
    assert theme.fmt_usdt(502.81, sign=True) == "+502.81"
    assert theme.fmt_qty(127.0) == "127"
    assert theme.fmt_pct(-3.92) == "-3.92%"
    assert theme.fmt_share(0.2) == "0.20%"
    assert theme.fmt_share(0.002) == "<0.01%"
    assert theme.fmt_share(0) == "0.00%"


def test_fmt_price_tiene_reglas_por_magnitud():
    assert theme.fmt_price(78632.6) == "78,632.6"
    assert theme.fmt_price(2239.1) == "2,239.1"
    assert theme.fmt_price(999.5) == "999.50"
    assert theme.fmt_price(0.07745) == "0.07745"


def test_fmt_price_exact_respeta_la_escala_del_contrato():
    """El precio de una orden limite se muestra tal como se envia."""
    assert theme.fmt_price_exact(2246.394, 2) == "2,246.39"
    assert theme.fmt_price_exact(2246.394, 0) == "2,246"
    assert theme.fmt_price_exact(0.00012345, 6) == "0.000123"
    assert theme.fmt_price_exact(5, 8) == "5.00000000"
    assert theme.fmt_price_exact(None, 2) == "0.00"
