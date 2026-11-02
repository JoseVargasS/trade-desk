"""UI real: la fila no crece, la barra de cierre mide lo pactado y los popups abren.

Necesita abrir una ventana Tk: `pytest -m ui`. Si no hay display, se salta.
"""

import pytest

pytest.importorskip("customtkinter")


def _entry_con_var(widget, var):
    """El CTkEntry de la tarjeta que escribe en ese StringVar."""
    import customtkinter as ctk

    for hijo in widget.winfo_children():
        if isinstance(hijo, ctk.CTkEntry) and str(hijo.cget("textvariable")) == str(var):
            return hijo
        encontrado = _entry_con_var(hijo, var)
        if encontrado is not None:
            return encontrado
    return None


def _vivo(root, widget):
    return root.tk.eval(f"winfo exists {widget._w}") == "1"


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
def test_la_fee_suma_comision_y_funding_y_trae_detalle(ventana, posicion):
    """La celda muestra 0.9993 + 0.484 = 1.4833, con subrayado y detalle al pasar.

    Si vuelve a mostrar solo `totalFee` el numero queda congelado y por debajo
    del que da el terminal de MEXC.
    """
    fila = _tabla(ventana, [posicion]).rows[1]
    canvas = fila["labels"]["fee"]
    textos = [
        canvas.itemcget(item, "text") for item in canvas.find_all() if canvas.type(item) == "text"
    ]

    assert "1.4833 USDT" in textos
    assert canvas.itemcget(canvas.find_all()[1], "dash"), "el subrayado tiene que ser punteado"
    detalle = dict((nombre, valor) for nombre, valor, _color in canvas.detalle())
    assert detalle == {
        "Comisión (USDT)": "0.9993",
        "Funding (USDT)": "0.4840",
        "Fee total (USDT)": "1.4833",
        "Fees saved (USDT)": "1.7489",
    }
    assert fila["labels"]["fee_saved"].cget("text") == "ahorro 1.7489"


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
def test_la_tarjeta_no_se_corta_y_los_botones_van_en_una_fila(ventana):
    from tradedesk.cards import TradeCard

    tarjeta = TradeCard(
        ventana,
        "XAU_USDT",
        {"leverage": 10},
        on_remove=lambda c: None,
        on_symbol=lambda c: None,
        on_trade=lambda c, s: None,
        on_change=lambda c: None,
    )
    tarjeta.pack()
    tarjeta.set_price(3660.3, 1.2)
    tarjeta.set_preview("22 contratos · 80.53 USDT\nfee 0.1996 · liq 3,611.8 / 3,712.0")
    ventana.update()

    fin = max(w.winfo_y() + w.winfo_height() for w in tarjeta.winfo_children())
    assert fin <= tarjeta.winfo_height(), "la tarjeta corta contenido"
    assert tarjeta.btn_long.winfo_y() == tarjeta.btn_short.winfo_y(), "LONG y SHORT apilados"
    assert abs(tarjeta.btn_long.winfo_width() - tarjeta.btn_short.winfo_width()) <= 1


@pytest.mark.ui
def test_la_tarjeta_elige_mercado_o_limite(ventana):
    from tradedesk.cards import TradeCard

    tarjeta = TradeCard(
        ventana,
        "XAU_USDT",
        {"leverage": 10},
        on_remove=lambda c: None,
        on_symbol=lambda c: None,
        on_trade=lambda c, s: None,
        on_change=lambda c: None,
    )
    tarjeta.pack()
    tarjeta.set_price(2243.3, 0.7)
    tarjeta.set_scale(2)
    tarjeta.var_size.set("10")
    ventana.update()

    assert tarjeta.form()["price"] is None, "por defecto a mercado"
    assert tarjeta.btn_order.cget("text") == "Mercado"

    tarjeta.set_limit_price(2246.394)
    assert tarjeta.form()["price"] == 2246.394
    assert tarjeta.btn_order.cget("text") == "2,246.39", "se muestra como se envia"

    tarjeta.set_limit_price(None)
    assert tarjeta.form()["price"] is None
    assert tarjeta.btn_order.cget("text") == "Mercado"

    tarjeta.set_limit_price(2246.394)
    tarjeta.set_symbol("ETH_USDT")
    ventana.update()
    assert tarjeta.form()["price"] is None, "cambiar de par vuelve a mercado"
    assert tarjeta.btn_order.cget("text") == "Mercado"


def _pisan_tk(widget):
    """Atributos que tapan un metodo de tkinter (el bug real: `_root`, `anchor`, `size`)."""
    choques = []
    for nombre, valor in widget.__dict__.items():
        clase = getattr(type(widget), nombre, None)
        if callable(clase) and not callable(valor):
            choques.append(nombre)
    return sorted(choques)


@pytest.mark.ui
def test_los_widgets_no_pisan_nombres_de_tk(ventana, posicion):
    """Pisar `_root` rompe `%W -> nametowidget -> _root()` y el error se lleva el
    mainloop: la app se cierra al abrir el panel. `anchor` y `size` son lo mismo."""
    from tradedesk import closebar
    from tradedesk.cards import TradeCard

    tarjeta = TradeCard(
        ventana,
        "XAU_USDT",
        {"leverage": 10},
        on_remove=lambda c: None,
        on_symbol=lambda c: None,
        on_trade=lambda c, s: None,
        on_change=lambda c: None,
    )
    tarjeta.pack()
    ventana.update()
    barra = _tabla(ventana, [posicion]).rows[1]["bar"]
    panel = closebar.PricePopup(
        tarjeta.btn_order, tarjeta._mark, tarjeta._scale, None, tarjeta.set_limit_price
    )
    ventana.update()

    for widget in (tarjeta, tarjeta.btn_order, barra, panel):
        choques = _pisan_tk(widget)
        assert not choques, f"{type(widget).__name__} pisa {choques} de tkinter"
    panel.destroy()


@pytest.mark.ui
def test_el_panel_no_se_come_el_clic_ni_el_foco(ventana):
    """El grab del panel cerraba al clic pero se lo tragaba: el input quedaba sordo."""
    import time

    from tradedesk import closebar
    from tradedesk.cards import TradeCard

    tarjeta = TradeCard(
        ventana,
        "XAU_USDT",
        {"leverage": 10},
        on_remove=lambda c: None,
        on_symbol=lambda c: None,
        on_trade=lambda c, s: None,
        on_change=lambda c: None,
    )
    tarjeta.pack()
    tarjeta.set_price(2243.3, 0.7)
    ventana.update()

    tamano = _entry_con_var(tarjeta, tarjeta.var_size)
    assert tamano is not None

    panel = closebar.PricePopup(
        tarjeta.btn_order, tarjeta._mark, tarjeta._scale, None, tarjeta.set_limit_price
    )
    ventana.update()
    time.sleep(0.05)  # el watcher de clics se arma a los 30 ms
    ventana.update()

    assert ventana.grab_current() is None, "un grab se traga el primer clic de afuera"

    tamano._entry.event_generate("<Button-1>", x=5, y=5)
    ventana.update()
    assert not _vivo(ventana, panel), "el panel se cierra con el primer clic afuera"

    tamano._entry.event_generate("<KeyPress>", keysym="7")
    ventana.update()
    assert tarjeta.var_size.get() == "7", "el clic y el teclado tienen que llegar al input"


@pytest.mark.ui
def test_el_panel_devuelve_el_teclado_a_la_ventana(ventana):
    """El sintoma real: tras elegir Mercado o Limite no se podia escribir en la
    tarjeta. El panel se lleva el teclado con `focus_force`; si al morir no lo
    devuelve, Tk se queda sin ventana con foco y los clics posteriores no le dan
    el foco a ningun input (hasta abrir y cerrar el buscador, que si lo hace).
    """
    from tradedesk import closebar
    from tradedesk.cards import TradeCard

    tarjeta = TradeCard(
        ventana,
        "XAU_USDT",
        {"leverage": 10},
        on_remove=lambda c: None,
        on_symbol=lambda c: None,
        on_trade=lambda c, s: None,
        on_change=lambda c: None,
    )
    tarjeta.pack()
    tarjeta.set_price(2243.3, 0.7)
    ventana.update()
    tamano = _entry_con_var(tarjeta, tarjeta.var_size)
    assert tamano is not None
    tamano._entry.focus_set()
    ventana.update()

    panel = closebar.PricePopup(
        tarjeta.btn_order, tarjeta._mark, tarjeta._scale, None, tarjeta.set_limit_price
    )
    ventana.update()
    panel.seg.set("Límite")
    panel._mode("Límite")
    ventana.update()
    panel.var.set("2,245")
    panel._apply()
    ventana.update()

    assert str(ventana.tk.call("focus")) != "", "el panel dejo la ventana sin foco"
    tamano._entry.event_generate("<Button-1>", x=5, y=5)
    ventana.update()
    assert ventana.focus_get() is not None, "el clic en el input no le da el foco"
    assert str(ventana.focus_get()) == str(tamano._entry)
    assert tarjeta.btn_order.cget("text") == "2,245.00"


@pytest.mark.ui
def test_los_dialogos_tambien_devuelven_el_teclado(ventana):
    """Mismo caso que el panel de precio: el dialogo se lleva el teclado con
    `focus_force` y, si no lo devuelve, el input de atras no recibe teclas."""
    import time

    import customtkinter as ctk

    from tradedesk import dialog

    var = ctk.StringVar()
    campo = ctk.CTkEntry(ventana, textvariable=var)
    campo.pack(pady=20)
    ventana.update()
    campo._entry.focus_set()
    ventana.update()

    aviso = dialog._Dialog(ventana, "Aviso", message="texto")
    fin = time.time() + 0.2  # el dialogo pide el foco a los 50 ms
    while time.time() < fin:
        ventana.update()
    aviso.destroy()
    ventana.update()

    assert str(ventana.tk.call("focus")) != "", "el dialogo dejo la ventana sin foco"
    campo._entry.event_generate("<Button-1>", x=5, y=5)
    ventana.update()
    assert str(ventana.focus_get()) == str(campo._entry)


@pytest.mark.ui
def test_la_tabla_de_ordenes_pinta_y_gestiona(ventana):
    """La orden pendiente se ve como en MEXC (par con % llenado, dirección,
    apalancamiento, monto, precio, TP/SL en dos líneas) y se puede editar o
    cancelar desde su fila."""
    import customtkinter as ctk

    from tradedesk import theme
    from tradedesk.orders import OpenOrdersTable

    acciones = []
    tabla = OpenOrdersTable(
        ventana,
        on_modify=acciones.append,
        on_cancel=lambda o: acciones.append(("cancelar", o["orderId"])),
        on_cancel_all=lambda: acciones.append("todas"),
    )
    tabla.pack(fill="both", expand=True)
    ventana.update()

    tabla.render([])
    ventana.update()
    assert tabla.rows == {}
    assert tabla.lbl.cget("text") == "Sin órdenes pendientes"
    assert tabla.btn_all.cget("state") == "disabled"

    orden = {
        "orderId": "871374754337090048",
        "symbol": "ETH_USDT",
        "price": 2000,
        "vol": 5,
        "dealVol": 0,
        "side": 1,
        "orderType": 1,
        "state": 2,
        "createTime": 1793422330674,
        "takeProfitPrice": 2500,
        "stopLossPrice": 1500,
        "orderMargin": 10.16,
        "leverage": 10,
        "totalFee": 0,
        "_contractSize": 0.01,
        "_priceScale": 2,
        "_name": "ETHUSDT",
    }
    tabla.render([orden])
    ventana.update()

    assert list(tabla.rows) == ["871374754337090048"]
    assert tabla.all() == [orden]
    fila = tabla.rows["871374754337090048"]
    etiquetas = fila["labels"]
    assert etiquetas["par"].cget("text") == "ETHUSDT"
    assert etiquetas["lleno_pct"].cget("text") == "0.00%"
    assert etiquetas["dir"].cget("text") == "Compra LONG"
    assert etiquetas["dir"].cget("fg") == theme.GREEN
    assert etiquetas["apal"].cget("text") == "10X"
    assert etiquetas["monto"].cget("text") == "100.00 USDT"
    assert etiquetas["precio"].cget("text") == "2,000.00"
    assert etiquetas["llenado"].cget("text") == "0/5"
    assert etiquetas["margen"].cget("text") == "10.16 USDT"
    assert etiquetas["tp"].cget("text") == "TP 2,500.00"
    assert etiquetas["sl"].cget("text") == "SL 1,500.00"
    assert etiquetas["estado"].cget("text") == "Sin llenar"
    assert etiquetas["fecha"].cget("text").startswith("20")
    assert tabla.lbl.cget("text") == "1 orden pendiente"
    assert tabla.btn_all.cget("state") == "normal"

    botones = {
        b.cget("text"): b
        for b in fila["frame"].winfo_children()[-1].winfo_children()
        if isinstance(b, ctk.CTkButton)
    }
    assert set(botones) == {"Modificar", "Cancelar"}
    botones["Modificar"].invoke()
    assert acciones == [orden], "la fila entrega la orden al editor"
    botones["Cancelar"].invoke()
    assert acciones[-1] == ("cancelar", orden["orderId"])

    tabla.btn_all.invoke()
    assert acciones[-1] == "todas"

    # sin ordenes vuelve el estado vacio
    tabla.render([])
    ventana.update()
    assert tabla.rows == {}
    assert tabla.btn_all.cget("state") == "disabled"


@pytest.mark.ui
def test_las_ordenes_de_cierre_solo_se_cancelan(ventana):
    """Reenviar una orden de cierre como si abriera sería un error de lado: el
    boton y el lapiz quedan deshabilitados."""
    import customtkinter as ctk

    from tradedesk.orders import OpenOrdersTable

    tabla = OpenOrdersTable(ventana)
    tabla.pack(fill="both", expand=True)
    ventana.update()

    cierre = {
        "orderId": "9",
        "symbol": "ETH_USDT",
        "price": 3000,
        "vol": 2,
        "dealVol": 0,
        "side": 4,  # cierra long
        "orderType": 1,
        "state": 2,
        "createTime": 1793422330674,
        "orderMargin": 10.0,
        "leverage": 10,
        "_contractSize": 0.01,
        "_priceScale": 2,
        "_name": "ETHUSDT",
    }
    tabla.render([cierre])
    ventana.update()

    fila = tabla.rows["9"]
    assert fila["labels"]["dir"].cget("text") == "Cierra LONG"
    botones = {
        b.cget("text"): b
        for b in fila["frame"].winfo_children()[-1].winfo_children()
        if isinstance(b, ctk.CTkButton)
    }
    assert str(botones["Modificar"].cget("state")) == "disabled"
    assert str(botones["Cancelar"].cget("state")) == "normal"


@pytest.mark.ui
def test_el_editor_de_orden_calcula_el_tamano(ventana):
    """El editor muestra contratos/nocional en vivo y devuelve el formulario.
    MEXC no deja modificar: guardar significa cancelar y reenviar."""
    from tradedesk.orders import OrderEditor

    contract = {"contractSize": 0.01, "volUnit": 1, "minVol": 1, "priceScale": 2}
    orden = {
        "orderId": "1",
        "symbol": "ETH_USDT",
        "price": 2000,
        "vol": 5,
        "side": 1,
        "leverage": 10,
        "orderMargin": 10.0,
        "takeProfitPrice": 2500,
        "stopLossPrice": 1500,
        "_priceScale": 2,
        "_name": "ETHUSDT",
    }

    def to_vol(notional, price):
        return int(notional / (price * 0.01))

    editor = OrderEditor(ventana, orden, contract, to_vol)
    ventana.update()
    assert "contratos" in editor.lbl_calc.cget("text")

    editor.var_margen.set("20")
    ventana.update()
    assert "10 contratos" in editor.lbl_calc.cget("text"), "20 USDT x 10 = 2,000 de nocional"
    assert "200.00 USDT nocional" in editor.lbl_calc.cget("text")

    editor._guardar()
    assert editor.result["margin"] == 20
    assert editor.result["notional"] == 200
    assert editor.result["vol"] == 10
    assert editor.result["side"] == "LONG"
    assert editor.result["price"] == 2000
    assert editor.result["tp"] == 2500 and editor.result["sl"] == 1500


@pytest.mark.ui
def test_el_editor_rechaza_un_margen_que_deja_cero_contratos(ventana):
    from tradedesk.orders import OrderEditor

    contract = {"contractSize": 0.01, "volUnit": 1, "minVol": 1, "priceScale": 2}
    orden = {
        "orderId": "1",
        "symbol": "ETH_USDT",
        "price": 2000,
        "vol": 5,
        "side": 1,
        "leverage": 10,
        "orderMargin": 10.0,
        "_priceScale": 2,
        "_name": "ETHUSDT",
    }
    editor = OrderEditor(ventana, orden, contract, lambda n, p: int(n / (p * 0.01)))
    ventana.update()
    editor.var_margen.set("0.5")  # 5 USDT de nocional = 0 contratos
    editor._guardar()
    assert editor.result is None
    assert "0 contratos" in editor.lbl_error.cget("text")
    editor.destroy()


@pytest.mark.ui
def test_el_panel_se_cierra_con_escape_y_con_su_fondo(ventana, posicion):
    """Tk no entrega `event_generate` a las ventanas overrideredirect, asi que
    se comprueba el cableado (bindings) y los handlers."""
    from types import SimpleNamespace

    from tradedesk import closebar

    barra = _tabla(ventana, [posicion]).rows[1]["bar"]

    panel = closebar._PercentPopup(barra)
    ventana.update()
    assert "<Key-Escape>" in panel.bind(), "el panel tiene que cerrarse con Escape"
    assert "<Button-1>" in panel.bind()

    panel._click_out(SimpleNamespace(widget=panel.wrap))
    ventana.update()
    assert not _vivo(ventana, panel)

    panel = closebar._PercentPopup(barra)
    ventana.update()
    panel.destroy()
    ventana.update()
    assert not _vivo(ventana, panel), "cerrar dos veces no debe romper"


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

    precio = closebar.PricePopup(
        barra.price_btn, barra.mark, barra.scale, barra.limit_price, barra.set_price
    )
    ventana.update()
    assert precio.seg.get() == "Mercado"
    precio.seg.set("Límite")
    precio._mode("Límite")
    precio.var.set("2,246.39")  # como lo muestra la fila: comas de miles
    precio._apply()
    assert barra.limit_price == 2246.39
    assert barra.price_btn.cget("text") == "2,246.39"


def _widgets(widget):
    for hijo in widget.winfo_children():
        yield hijo
        yield from _widgets(hijo)


@pytest.mark.ui
def test_el_lapiz_usa_el_dato_vigente_y_no_la_foto_vieja(ventana, posicion):
    """`render()` refresca la fila; el lápiz no puede quedarse con el dict viejo.

    Con el dict viejo `_tpsl_id` era None y cada edición creaba otro SL en MEXC.
    """
    from tradedesk import table

    visto = []
    tabla = table.PositionsTable(
        ventana,
        on_close=lambda p, i: None,
        on_tpsl=visto.append,
        on_margin=lambda p: None,
        on_reverse=lambda p: None,
    )
    tabla.pack(fill="both", expand=True)
    tabla.render([posicion])
    ventana.update()
    tabla.render([dict(posicion, _tpsl_id=99, _sl=3800.0)])
    ventana.update()

    lapices = [w for w in _widgets(tabla.rows[1]["frame"]) if isinstance(w, table.Pencil)]
    lapices[-1].command()  # el ultimo es el de TP/SL

    assert visto and visto[-1]["_tpsl_id"] == 99
    assert visto[-1]["_sl"] == 3800.0


@pytest.mark.ui
def test_el_formulario_pinta_el_resumen_y_bloquea_el_extra(ventana):
    import customtkinter as ctk

    from tradedesk import dialog

    campos = [("sl", "Stop loss", "")]
    resumen = lambda e: f"SL {e['sl'].get()} → 0 USDT"  # noqa: E731

    bloqueado = dialog._FormDialog(
        ventana,
        "TP / SL",
        campos,
        extras=[("Break-even", lambda e: e["sl"].set("123.45"), False)],
        resumen=resumen,
    )
    ventana.update()
    assert bloqueado.lbl_resumen.cget("text") == "SL  → 0 USDT"
    bloqueado.entries["sl"].set("100")
    assert bloqueado.lbl_resumen.cget("text") == "SL 100 → 0 USDT", "se actualiza al escribir"
    boton = next(
        w
        for w in _widgets(bloqueado)
        if isinstance(w, ctk.CTkButton) and w.cget("text") == "Break-even"
    )
    assert str(boton.cget("state")) == "disabled"
    bloqueado.destroy()

    activo = dialog._FormDialog(
        ventana,
        "TP / SL",
        campos,
        extras=[("Break-even", lambda e: e["sl"].set("123.45"), True)],
        resumen=resumen,
    )
    ventana.update()
    boton = next(
        w
        for w in _widgets(activo)
        if isinstance(w, ctk.CTkButton) and w.cget("text") == "Break-even"
    )
    boton._command()
    assert activo.entries["sl"].get() == "123.45", "el extra escribe en el input"
    activo.destroy()
