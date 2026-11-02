"""Órdenes abiertas: las límite que MEXC todavía no llenó.

La tabla imita el panel de órdenes de MEXC: par con el % llenado debajo, fecha,
dirección, apalancamiento, monto, precio, llenado, margen usado, TP/SL en dos
líneas, fee, estado y la acción. Los lápices de Monto, Precio y TP/SL —igual que
en MEXC— abren el editor; en la columna de acciones están `Modificar` y
`Cancelar`.

MEXC **no deja modificar** una orden: guardar el editor cancela la actual y
reenvía una nueva. Eso lo hace el App en un hilo (`actions._replace_order`);
aquí no se habla con la API.
"""

import tkinter as tk
from datetime import datetime

import customtkinter as ctk

from . import theme as t
from .dialog import Modal
from .mexc import es_editable, margen_inicial, num_texto
from .table import STATES, Header, Pencil, sync_header_pad

ORDER_COLS = (
    ("par", "Par", 180, "w"),
    ("fecha", "Fecha", 148, "w"),
    ("dir", "Dirección", 108, "w"),
    ("apal", "Apal.", 84, "w"),
    ("monto", "Monto", 130, "e"),
    ("precio", "Precio", 130, "e"),
    ("llenado", "Llenado", 96, "e"),
    ("margen", "Margen usado", 124, "e"),
    ("stops", "TP / SL", 190, "e"),
    ("fee", "Fee (USDT)", 92, "e"),
    ("estado", "Estado", 96, "w"),
)

PENCIL_COLS = {"monto", "precio", "stops"}
ACTION_W = 190
ROW_H = 54

# como MEXC: dice si compra o vende y de qué lado queda la posición
DIRS = {
    1: ("Compra LONG", True),
    2: ("Cierra SHORT", True),
    3: ("Venta SHORT", False),
    4: ("Cierra LONG", False),
}


def fmt_fecha(ts):
    """Fecha de la orden con segundos, como el panel de MEXC."""
    try:
        return datetime.fromtimestamp(float(ts) / 1000).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "—"


def direccion(order):
    """(texto, color) de la dirección: 1 y 2 compran, 3 y 4 venden."""
    texto, compra = DIRS.get(int(order.get("side") or 0), ("?", True))
    return texto, t.GREEN if compra else t.RED


class OpenOrdersTable(ctk.CTkFrame):
    """Órdenes que MEXC tiene en el libro, con edición y cancelación por fila.

    No habla con la API: entrega la orden elegida a `on_modify` / `on_cancel` /
    `on_cancel_all`. Se actualiza en sitio (el poller manda la lista cada 3 s)
    para no reconstruir filas debajo del mouse.
    """

    def __init__(self, parent, on_modify=None, on_cancel=None, on_cancel_all=None):
        super().__init__(parent, fg_color="transparent")
        self.on_modify = on_modify or (lambda o: None)
        self.on_cancel = on_cancel or (lambda o: None)
        self.on_cancel_all = on_cancel_all or (lambda: None)
        self.rows = {}

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", pady=(0, 4))
        self.lbl = ctk.CTkLabel(
            top, text="Sin órdenes pendientes", font=(t.UI, 13), text_color=t.MUTED, anchor="w"
        )
        self.lbl.pack(side="left", padx=4)
        self.btn_all = ctk.CTkButton(
            top,
            text="Cancelar todo",
            width=140,
            height=28,
            corner_radius=t.R_CTRL,
            fg_color=t.DANGER_SOFT,
            hover_color=t.DANGER_SOFT_HOVER,
            border_width=1,
            border_color=t.BORDER,
            text_color=t.RED,
            font=(t.UI, 12, "bold"),
            command=self.on_cancel_all,
        )
        self.btn_all.pack(side="right")

        self.header = Header(
            self,
            ORDER_COLS,
            extra_right=ACTION_W,
            extra_label="Acción",
            pencil_cols=PENCIL_COLS,
        )
        self.header.pack(fill="x")

        self.body = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=t.INPUT,
            scrollbar_button_hover_color=t.BORDER,
        )
        self.body.pack(fill="both", expand=True, pady=(4, 0))
        self.body.grid_columnconfigure(0, weight=1)

        self.empty = ctk.CTkLabel(
            self.body,
            text="Sin órdenes pendientes.\n"
            "Una orden límite que no se llenó se queda aquí hasta que la cancele"
            " el mercado o tú.",
            font=(t.UI, 13),
            text_color=t.MUTED,
            justify="left",
        )
        self.empty.grid(row=0, column=0, pady=30)

        self.bind("<Configure>", lambda e: self.after(30, self._sync_header_pad), add="+")
        self.after(150, self._sync_header_pad)

    def _sync_header_pad(self):
        sync_header_pad(self)

    # ------------------------------------------------------------------ datos
    def all(self):
        """Órdenes vivas, en el orden en que las pintó la última respuesta."""
        return [row["data"] for row in self.rows.values()]

    def render(self, orders):
        orders = list(orders or [])
        ids = [o.get("orderId") for o in orders]
        if ids != list(self.rows):
            self._rebuild(orders)
        else:
            for o in orders:
                self._fill(self.rows[o["orderId"]], o)
        self._sync_top(len(orders))

    def _sync_top(self, count):
        if count:
            self.lbl.configure(
                text="1 orden pendiente" if count == 1 else f"{count} órdenes pendientes",
                text_color=t.TEXT,
            )
            self.btn_all.configure(state="normal")
        else:
            self.lbl.configure(text="Sin órdenes pendientes", text_color=t.MUTED)
            self.btn_all.configure(state="disabled")

    # ------------------------------------------------------------- construccion
    def _rebuild(self, orders):
        for row in self.rows.values():
            row["frame"].destroy()
        self.rows = {}
        self.empty.grid_forget()
        if not orders:
            self.empty.grid(row=0, column=0, pady=30)
            return
        for index, o in enumerate(orders):
            self._add_row(o, index)

    def _add_row(self, o, index):
        bg = t.CARD if index % 2 == 0 else t.ROW_ALT
        editable = es_editable(o)
        # fila y celdas en tk: los CTkLabel son Canvas aparte y multiplicaban el
        # costo de repintado de la ventana (ver tools/medir_repintado.py)
        frame = tk.Frame(self.body, bg=bg, height=t.px(ROW_H))
        frame.grid(row=index, column=0, sticky="ew")
        frame.grid_propagate(False)
        frame.grid_rowconfigure(0, weight=1)

        cells = {}
        col = 0
        for key, _label, width, anchor in ORDER_COLS:
            frame.grid_columnconfigure(col, minsize=width + 8, weight=0)
            if key == "par":
                cells.update(self._celda_par(frame, col, bg))
            elif key == "stops":
                cells.update(self._celda_stops(frame, col, bg, o, editable))
            elif key in PENCIL_COLS:
                # lápiz al final de la celda, como en la tabla de posiciones
                cell = tk.Frame(frame, bg=bg)
                cell.grid(row=0, column=col, sticky="ew", padx=(6, 2))
                cell.grid_columnconfigure(0, weight=1)
                valor = tk.Label(
                    cell, text="", bg=bg, fg=t.TEXT, font=t.num_font(13, bold=True), anchor="e"
                )
                valor.grid(row=0, column=0, sticky="e")
                Pencil(
                    cell,
                    lambda order=o: self.on_modify(order),
                    bg=bg,
                    enabled=editable,
                ).grid(row=0, column=1, sticky="e", padx=(4, 0))
                cells[key] = valor
            else:
                lbl = tk.Label(
                    frame,
                    text="",
                    bg=bg,
                    fg=t.TEXT,
                    font=t.num_font(13, bold=key == "apal"),
                    anchor=anchor,
                )
                lbl.grid(row=0, column=col, sticky="ew", padx=(6, 2))
                cells[key] = lbl
            col += 1

        frame.grid_columnconfigure(col, minsize=0, weight=1)
        col += 1
        frame.grid_columnconfigure(col, minsize=ACTION_W, weight=0)
        acciones = tk.Frame(frame, bg=bg)
        acciones.grid(row=0, column=col, padx=(4, 8), sticky="e")
        ctk.CTkButton(
            acciones,
            text="Modificar",
            width=84,
            height=26,
            corner_radius=t.R_CHIP,
            fg_color=t.INPUT,
            hover_color=t.BORDER,
            border_width=1,
            border_color=t.BORDER,
            text_color=t.TEXT if editable else t.BORDER,
            font=(t.UI, 11),
            state="normal" if editable else "disabled",
            command=lambda order=o: self.on_modify(order),
        ).pack(side="left")
        ctk.CTkButton(
            acciones,
            text="Cancelar",
            width=84,
            height=26,
            corner_radius=t.R_CHIP,
            fg_color=t.INPUT,
            hover_color=t.DANGER_SOFT_HOVER,
            border_width=1,
            border_color=t.BORDER,
            text_color=t.RED,
            font=(t.UI, 11),
            command=lambda order=o: self.on_cancel(order),
        ).pack(side="left", padx=(6, 0))

        row = {"frame": frame, "labels": cells, "data": o}
        self.rows[o.get("orderId")] = row
        self._fill(row, o)

    def _celda_par(self, frame, col, bg):
        """Par en bold + `Perpetual` en gris; debajo, el % llenado (como MEXC)."""
        cell = tk.Frame(frame, bg=bg)
        cell.grid(row=0, column=col, sticky="ew", padx=(6, 2))
        cell.grid_columnconfigure(0, weight=1)
        linea = tk.Frame(cell, bg=bg)
        linea.grid(row=0, column=0, sticky="w")
        par = tk.Label(linea, text="", bg=bg, fg=t.TEXT, font=t.num_font(13, bold=True), anchor="w")
        par.pack(side="left")
        tk.Label(linea, text="Perpetual", bg=bg, fg=t.MUTED, font=t.ui_font(10), anchor="w").pack(
            side="left", padx=(4, 0)
        )
        lleno = tk.Label(cell, text="", bg=bg, fg=t.MUTED, font=t.num_font(11), anchor="w")
        lleno.grid(row=1, column=0, sticky="w")
        return {"par": par, "lleno_pct": lleno}

    def _celda_stops(self, frame, col, bg, orden, editable):
        """TP y SL en dos líneas, igual que en la tabla de órdenes de MEXC."""
        cell = tk.Frame(frame, bg=bg)
        cell.grid(row=0, column=col, sticky="ew", padx=(6, 2))
        cell.grid_columnconfigure(0, weight=1)
        tp = tk.Label(cell, text="", bg=bg, fg=t.GREEN, font=t.num_font(13, bold=True), anchor="e")
        tp.grid(row=0, column=0, sticky="e")
        sl = tk.Label(cell, text="", bg=bg, fg=t.RED, font=t.num_font(13, bold=True), anchor="e")
        sl.grid(row=1, column=0, sticky="e")
        Pencil(cell, lambda order=orden: self.on_modify(order), bg=bg, enabled=editable).grid(
            row=0, column=1, rowspan=2, sticky="e", padx=(4, 0)
        )
        return {"tp": tp, "sl": sl}

    def _fill(self, row, o):
        vol = float(o.get("vol") or 0)
        lleno = float(o.get("dealVol") or 0)
        price = float(o.get("price") or 0)
        size = float(o.get("_contractSize") or 0)
        scale = int(o.get("_priceScale") or 2)
        notional = vol * size * price
        pct = (lleno / vol * 100) if vol else 0.0

        labels = row["labels"]
        direccion_txt, direccion_color = direccion(o)
        labels["par"].configure(text=o.get("_name") or o.get("symbol", ""))
        labels["lleno_pct"].configure(text=f"{pct:.2f}%")
        labels["fecha"].configure(text=fmt_fecha(o.get("createTime")), fg=t.MUTED)
        labels["dir"].configure(text=direccion_txt, fg=direccion_color)
        labels["apal"].configure(
            text=f"{int(o.get('leverage') or 0)}X",
            fg=t.GREEN if direccion_color == t.GREEN else t.RED,
        )
        labels["monto"].configure(text=f"{t.fmt_usdt(notional)} USDT" if notional else "—")
        labels["precio"].configure(text=t.fmt_price_exact(price, scale))
        labels["llenado"].configure(
            text=f"{t.fmt_qty(lleno)}/{t.fmt_qty(vol)}",
            fg=t.GOLD if lleno else t.MUTED,
        )
        labels["margen"].configure(text=f"{t.fmt_usdt(o.get('orderMargin'))} USDT")
        labels["fee"].configure(text=t.fmt_fee(o.get("totalFee") or o.get("fee")), fg=t.MUTED)
        estado = int(o.get("state") or 0)
        labels["estado"].configure(
            text=STATES.get(estado, str(estado)),
            fg=t.TEXT if estado in (1, 2) else t.MUTED,
        )

        tp = float(o.get("takeProfitPrice") or 0)
        sl = float(o.get("stopLossPrice") or 0)
        labels["tp"].configure(
            text=f"TP {t.fmt_price_exact(tp, scale)}" if tp else "—",
            fg=t.GREEN if tp else t.MUTED,
        )
        labels["sl"].configure(
            text=f"SL {t.fmt_price_exact(sl, scale)}" if sl else "",
            fg=t.RED,
        )

        row["data"] = o


class OrderEditor(Modal):
    """Editor de una orden abierta: lado, apalancamiento, margen, precio y TP/SL.

    Guardar no modifica: MEXC no lo permite. El App cancela esta orden y reenvía
    una nueva con los datos elegidos (por eso el aviso en amarillo).
    """

    def __init__(self, parent, order, contract, to_vol):
        super().__init__(parent)
        self.order = order
        self.contract = contract or {}
        self.to_vol = to_vol
        self.result = None
        self.scale = int(order.get("_priceScale") or 2)

        self.title("Modificar orden")
        self.overrideredirect(True)
        self.configure(fg_color=t.LINE)
        self.transient(parent)
        self.grab_set()

        wrap = ctk.CTkFrame(self, fg_color=t.CARD, corner_radius=t.R_CARD)
        wrap.pack(fill="both", expand=True, padx=1, pady=1)
        wrap.grid_columnconfigure(0, weight=0, minsize=150)
        wrap.grid_columnconfigure(1, weight=1, minsize=214)

        head = ctk.CTkFrame(wrap, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(14, 0))
        ctk.CTkLabel(head, text="Modificar orden", font=(t.UI, 15, "bold"), text_color=t.TEXT).pack(
            side="left"
        )
        ctk.CTkButton(
            head,
            text="✕",
            width=22,
            height=22,
            corner_radius=t.R_CHIP,
            fg_color="transparent",
            hover_color=t.BORDER,
            text_color=t.MUTED,
            font=(t.UI, 12),
            command=self.destroy,
        ).pack(side="right")
        ctk.CTkLabel(
            head,
            text=order.get("_name") or order.get("symbol", ""),
            font=(t.NUM, 12),
            text_color=t.MUTED,
        ).pack(side="right", padx=(0, 10))

        ctk.CTkLabel(
            wrap,
            text="Se cancela esta orden y se envía una nueva con estos datos.\n"
            "Si el precio se movió, la nueva puede quedar sin llenar.",
            font=(t.UI, 11),
            text_color=t.GOLD,
            anchor="w",
            justify="left",
            wraplength=396,
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=18, pady=(6, 0))

        row = 2
        ctk.CTkLabel(wrap, text="Dirección", font=(t.UI, 10), text_color=t.MUTED, anchor="w").grid(
            row=row, column=0, columnspan=2, sticky="w", padx=18, pady=(12, 2)
        )
        self.var_lado = ctk.StringVar(
            value="LONG" if int(order.get("side") or 1) in (1, 4) else "SHORT"
        )
        ctk.CTkSegmentedButton(
            wrap,
            values=["LONG", "SHORT"],
            variable=self.var_lado,
            height=28,
            corner_radius=t.R_CTRL,
            font=(t.UI, 12, "bold"),
            fg_color=t.BORDER,
            border_width=1,
            selected_color=t.ACCENT_SOFT,
            selected_hover_color=t.ACCENT_SOFT,
            unselected_color=t.INPUT,
            unselected_hover_color=t.BORDER,
            text_color=t.TEXT,
            text_color_disabled=t.MUTED,
        ).grid(row=row + 1, column=0, columnspan=2, sticky="ew", padx=18)

        self.var_lev = ctk.StringVar(value=str(int(order.get("leverage") or 10)))
        self.var_margen = ctk.StringVar(value=f"{margen_inicial(order):.2f}")
        self.var_precio = ctk.StringVar(
            value=t.fmt_price_exact(order.get("price"), self.scale).replace(",", "")
        )
        self.var_tp = ctk.StringVar(value=num_texto(order.get("takeProfitPrice")))
        self.var_sl = ctk.StringVar(value=num_texto(order.get("stopLossPrice")))

        row += 2
        self._campo(wrap, row, "Apalancamiento", self.var_lev, "x")
        self._campo(wrap, row + 1, "Margen", self.var_margen, "USDT")
        self._campo(wrap, row + 2, "Precio límite", self.var_precio, "")
        self._campo(wrap, row + 3, "TP", self.var_tp, "")
        self._campo(wrap, row + 4, "SL", self.var_sl, "")

        self.lbl_calc = ctk.CTkLabel(
            wrap, text="", font=(t.NUM, 11), text_color=t.MUTED, anchor="w"
        )
        self.lbl_calc.grid(row=row + 5, column=0, columnspan=2, sticky="w", padx=18, pady=(10, 0))

        self.lbl_error = ctk.CTkLabel(
            wrap, text="", font=(t.UI, 11), text_color=t.RED, anchor="w", wraplength=396
        )
        self.lbl_error.grid(row=row + 6, column=0, columnspan=2, sticky="w", padx=18, pady=(6, 0))

        botones = ctk.CTkFrame(wrap, fg_color="transparent")
        botones.grid(row=row + 7, column=0, columnspan=2, sticky="ew", padx=18, pady=(12, 16))
        ctk.CTkButton(
            botones,
            text="Cancelar",
            width=100,
            height=34,
            corner_radius=t.R_CTRL,
            fg_color=t.INPUT,
            hover_color=t.BORDER,
            text_color=t.TEXT,
            font=(t.UI, 12),
            command=self.destroy,
        ).pack(side="left")
        ctk.CTkButton(
            botones,
            text="Guardar y reenviar",
            height=34,
            corner_radius=t.R_CTRL,
            fg_color=t.GREEN,
            hover_color=t.GREEN_HOVER,
            text_color=t.ON_GREEN,
            font=(t.UI, 12, "bold"),
            command=self._guardar,
        ).pack(side="right")

        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Return>", lambda e: self._guardar())
        for var in (self.var_lev, self.var_margen, self.var_precio):
            var.trace_add("write", lambda *_: self._calc())
        self.update_idletasks()
        self._calc()
        self._centrar(parent)

    def _campo(self, wrap, row, etiqueta, var, sufijo):
        ctk.CTkLabel(wrap, text=etiqueta, font=(t.UI, 11), text_color=t.MUTED, anchor="w").grid(
            row=row, column=0, sticky="w", padx=(18, 6), pady=3
        )
        caja = ctk.CTkFrame(wrap, fg_color="transparent")
        caja.grid(row=row, column=1, sticky="ew", padx=(0, 18), pady=3)
        caja.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(
            caja,
            textvariable=var,
            width=196,
            height=30,
            corner_radius=t.R_CTRL,
            fg_color=t.INPUT,
            border_color=t.BORDER,
            border_width=1,
            text_color=t.TEXT,
            font=(t.NUM, 13),
            justify="right",
        ).grid(row=0, column=0, sticky="ew")
        if sufijo:
            ctk.CTkLabel(
                caja, text=sufijo, font=(t.NUM, 11), text_color=t.MUTED, width=34, anchor="w"
            ).grid(row=0, column=1, padx=(6, 0))

    def _centrar(self, parent):
        try:
            x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 3
        except Exception:
            x, y = 200, 150
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _valores(self):
        """(lev, margen, precio, tp, sl) o None si algo no es número."""
        try:
            lev = int(float(self.var_lev.get().replace(",", "")))
            margen = float(self.var_margen.get().replace(",", ""))
            precio = float(self.var_precio.get().replace(",", ""))
            tp = float(self.var_tp.get().replace(",", "")) if self.var_tp.get().strip() else 0.0
            sl = float(self.var_sl.get().replace(",", "")) if self.var_sl.get().strip() else 0.0
        except ValueError:
            return None
        if lev < 1 or margen <= 0 or precio <= 0 or tp < 0 or sl < 0:
            return None
        return lev, margen, precio, tp, sl

    def _calc(self):
        valores = self._valores()
        if not valores:
            self.lbl_calc.configure(text="—")
            return
        lev, margen, precio, _tp, _sl = valores
        notional = margen * lev
        try:
            vol = self.to_vol(notional, precio)
        except Exception:
            vol = 0
        self.lbl_calc.configure(
            text=f"≈ {t.fmt_qty(vol)} contratos · {t.fmt_usdt(notional)} USDT nocional"
        )

    def _guardar(self):
        valores = self._valores()
        if not valores:
            self.lbl_error.configure(
                text="Revisa los números: apalancamiento, margen y precio > 0."
            )
            return
        lev, margen, precio, tp, sl = valores
        notional = margen * lev
        try:
            vol = self.to_vol(notional, precio)
        except Exception as e:
            self.lbl_error.configure(text=str(e)[:120])
            return
        if vol < 1:
            minimo = float(self.contract.get("minVol") or 1) * float(
                self.contract.get("contractSize") or 0
            )
            self.lbl_error.configure(
                text=f"Ese margen deja 0 contratos: sube el margen (mínimo ≈ "
                f"{t.fmt_usdt(minimo * precio)} USDT con {lev}x)."
            )
            return
        self.result = {
            "side": self.var_lado.get(),
            "lev": lev,
            "margin": margen,
            "notional": notional,
            "price": precio,
            "tp": tp or None,
            "sl": sl or None,
            "vol": vol,
            "scale": self.scale,
        }
        self.destroy()


def edit_order(parent, order, contract, to_vol):
    """Abre el editor y devuelve el formulario elegido, o None."""
    editor = OrderEditor(parent, order, contract, to_vol)
    parent.wait_window(editor)
    return editor.result
