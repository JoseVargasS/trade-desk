"""Puente de la app Tk con `controller.Control`.

La lógica vive en `controller.py` (compartida con la vista Qt); aquí solo queda
el `UiPort` que la envuelve con `dialog.*` y el estado de la ventana Tk.
"""

from . import dialog
from . import theme as t
from .controller import Control
from .mexc import break_even_price, pnl_en_precio
from .orders import edit_order


def _resumen_tpsl(pos, long_, campos):
    """Lo que se gana o pierde si el TP/SL se ejecuta, en USDT."""
    lineas = []
    for clave, etiqueta in (("tp", "TP"), ("sl", "SL")):
        texto = campos[clave].get().replace(",", "").strip()
        if not texto:
            continue
        try:
            precio = float(texto)
        except ValueError:
            continue
        lineas.append(
            f"{etiqueta} {t.fmt_price(precio)} → "
            f"{t.fmt_pnl(pnl_en_precio(pos, long_, precio))} USDT"
        )
    return "\n".join(lineas) or "Escribe un precio para ver la ganancia o perdida."


class TkPort:
    """`UiPort` de la app Tk: mismos diálogos de siempre."""

    def __init__(self, app):
        self.app = app

    def confirm(self, titulo, rows=(), warn=None, danger=False, ok="Confirmar", cancel="Cancelar"):
        return dialog.confirm(
            self.app.root,
            titulo,
            rows=rows,
            warn=warn,
            danger=danger,
            ok_text=ok,
            cancel_text=cancel,
        )

    def show(self, titulo, mensaje, aviso=None, danger=False):
        dialog.show(self.app.root, titulo, mensaje, aviso=aviso, danger=danger)

    def form(self, titulo, campos, nota=None, ok="Guardar"):
        return dialog.form(self.app.root, titulo, campos, ok_text=ok, note=nota)

    def status(self, texto):
        self.app._status(texto)

    def tpsl(self, pos, precio):
        long_ = int(pos.get("positionType") or 1) == 1
        scale = int(pos.get("_priceScale") or 2)
        lado = ("SL debajo" if long_ else "SL arriba") if precio else "SL en contra"

        be, cubre = break_even_price(pos, long_)
        cabe = bool(precio and be and (precio > be if long_ else precio < be))
        texto_be = f"{be:.{scale}f}" if be else ""
        if be:
            linea_be = (
                f"Break-even {t.fmt_price_exact(be, scale)} → {t.fmt_pnl(cubre)} USDT "
                "(comision de entrada + salida + funding · neto 0)"
            )
            if not cabe:
                linea_be += (
                    f"\nNecesita precio {'>' if long_ else '<'} "
                    f"{t.fmt_price_exact(be, scale)} (ahora {t.fmt_price(precio)})"
                )
        else:
            linea_be = "Break-even no disponible: falta precio de entrada o tamaño"

        return dialog.form(
            self.app.root,
            f"TP / SL · {pos.get('symbol')}",
            [
                ("tp", "Take profit", pos.get("_tp") or ""),
                ("sl", "Stop loss", pos.get("_sl") or ""),
            ],
            ok_text="Guardar",
            note=f"Qty {t.fmt_qty(pos.get('holdVol'))} contratos · "
            f"precio actual {t.fmt_price(precio) if precio else '—'} ({lado})\n{linea_be}",
            extras=[("Break-even", lambda campos: campos["sl"].set(texto_be), cabe)],
            resumen=lambda campos: _resumen_tpsl(pos, long_, campos),
        )

    def editar_orden(self, order, contract, to_vol):
        return edit_order(self.app.root, order, contract, to_vol)


class TkSession:
    """Lo que `Control` necesita de la ventana Tk: cliente, cola y refrescos."""

    def __init__(self, app):
        self.app = app

    @property
    def mx(self):
        return self.app.mx

    @property
    def q(self):
        return self.app.q

    @property
    def precios(self):
        return self.app._prices

    def contract_for(self, symbol):
        return self.app._contract_for(symbol)

    def log(self, msg):
        self.app._log(msg)

    def refresh_positions(self):
        self.app._refresh_positions()

    def refresh_orders(self):
        self.app._refresh_orders()


class ActionsMixin:
    """Los callbacks que ya usaba la UI de Tk, delegados al `Control`."""

    def _control(self):
        control = getattr(self, "_ctl", None)
        if control is None:
            control = Control(TkSession(self), TkPort(self), dry=lambda: bool(self.var_dry.get()))
            self._ctl = control
        return control

    # ------------------------------------------------------------------ cierres
    def _close_position(self, pos, info=None):
        self._control().cerrar(pos, info)

    def _close_selected(self):
        self._control().cerrar_seleccionadas(self.table.selected())

    def _reverse_position(self, pos):
        self._control().reverse(pos)

    def _close_all(self):
        self._control().cerrar_todo(self.table.checked_count())

    # --------------------------------------------------------------- tp/sl
    def _edit_tpsl(self, pos):
        self._control().tpsl(pos)

    def _tpsl_worker(self, pos, tp, sl, es_be=False):
        self._control()._tpsl_worker(pos, tp, sl, es_be)

    # -------------------------------------------------------- ordenes abiertas
    def _cancel_order(self, order):
        self._control().cancelar(order)

    def _cancel_all_orders(self):
        self._control().cancelar_todo(self.orders.all())

    def _modify_order(self, order):
        self._control().modificar(order)

    # ---------------------------------------------------------------- margen
    def _add_margin(self, pos):
        self._control().margen(pos)
