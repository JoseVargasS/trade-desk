"""UI real: la fila no crece, la barra de cierre mide lo pactado y los popups abren.

Necesita abrir una ventana Tk: `pytest -m ui`. Si no hay display, se salta.
"""

import pytest

pytest.importorskip("customtkinter")


@pytest.fixture
def ventana():
    import tkinter

    import customtkinter as ctk

    from tradedesk import theme

    try:
        root = ctk.CTk()
    except tkinter.TclError:
        pytest.skip("sin display para Tk")
    root.geometry("1760x900")
    theme.resolve_fonts(root)
    root.update()
    try:
        yield root
    finally:
        root.destroy()


def _tabla(root, posiciones):
    from tradedesk import table

    tabla = table.PositionsTable(
        root,
        on_close=lambda p, i: None,
        on_tpsl=lambda p: None,
        on_margin=lambda p: None,
        on_reverse=lambda p: None,
    )
    tabla.pack(fill="both", expand=True, padx=16, pady=8)
    tabla.render(posiciones)
    root.update()
    return tabla


@pytest.mark.ui
def test_la_fila_no_se_corta_en_la_ventana_minima(ventana, posicion):
    tabla = _tabla(ventana, [posicion])
    fila = tabla.rows[1]["frame"]
    barra = tabla.rows[1]["bar"]
    ultimo = max(fila.winfo_children(), key=lambda w: w.winfo_x())

    assert barra.winfo_width() == 190, "los 200 px de acciones dan 190 utiles"
    assert ultimo.winfo_x() + ultimo.winfo_width() <= fila.winfo_width(), (
        "la ultima columna se sale de la fila"
    )
    assert barra.winfo_height() <= tabla.winfo_height(), "la barra cabe en el alto"


@pytest.mark.ui
def test_la_barra_mide_dos_lineas_y_cuatro_controles(ventana, posicion):
    barra = _tabla(ventana, [posicion]).rows[1]["bar"]
    linea1, linea2 = barra.winfo_children()
    precio, pct = linea1.winfo_children()
    cerrar, reverse = linea2.winfo_children()

    assert (precio.winfo_width(), pct.winfo_width()) == (106, 78)
    assert (cerrar.winfo_width(), reverse.winfo_width()) == (102, 82)
    assert cerrar.cget("text") == "Cerrar LONG"
    assert precio.cget("text") == "Mercado"
    assert pct.cget("text") == "100%"


@pytest.mark.ui
def test_el_boton_sigue_al_pnl_y_a_lado(ventana, posicion):
    from tradedesk import theme

    tabla = _tabla(
        ventana,
        [
            dict(posicion, positionId=1, unRealizedPnl=-1.0),
            dict(posicion, positionId=2, positionType=2, unRealizedPnl=5.0),
        ],
    )

    perdedora = tabla.rows[1]["bar"].close_btn
    ganadora = tabla.rows[2]["bar"].close_btn
    assert perdedora.cget("text") == "Cerrar LONG"
    assert perdedora.cget("fg_color") == theme.RED
    assert ganadora.cget("text") == "Cerrar SHORT"
    assert ganadora.cget("fg_color") == theme.GREEN


@pytest.mark.ui
def test_cantidad_y_precio_se_normalizan(ventana, posicion):
    barra = _tabla(ventana, [posicion]).rows[1]["bar"]

    barra.set_pct(37)
    assert barra.pct == 37 and barra.pct_btn.cget("text") == "37%"
    barra.set_pct(150)
    assert barra.pct == 100, "no se puede cerrar mas que la posicion"
    barra.set_context(dict(posicion, holdVol=3), 0.0, 100.0, 300.0)
    assert barra.min_pct() == 34, "el minimo que deja un contrato"
    barra.set_pct(5)
    assert barra.pct == 34

    barra.set_price(2246.394)
    assert barra.limit_price == 2246.394
    assert barra.price_btn.cget("text") == "2,246.39", "se muestra como se envia"
    barra.set_price(None)
    assert barra.price_btn.cget("text") == "Mercado"


@pytest.mark.ui
def test_los_popups_abren_y_escriben_en_la_fila(ventana, posicion):
    from tradedesk import closebar

    barra = _tabla(ventana, [posicion]).rows[1]["bar"]

    popup = closebar._PercentPopup(barra)
    ventana.update()
    assert "Cerrable:" in popup.lines.cget("text")
    assert "contratos" in popup.lines.cget("text")
    popup.var.set("60")
    popup._typed()
    assert barra.pct == 60
    popup.destroy()

    precio = closebar._PricePopup(barra)
    ventana.update()
    assert precio.seg.get() == "Mercado"
    precio.seg.set("Límite")
    precio._mode("Límite")
    precio.var.set("2,246.39")  # como lo muestra la fila: comas de miles
    precio._apply()
    assert barra.limit_price == 2246.39
    assert barra.price_btn.cget("text") == "2,246.39"
