"""Tablas de posiciones e historial; la de órdenes abiertas está en orders.py.

Filas hechas con widgets (no Treeview) para poder colorear celda por celda.
Las filas se actualizan en sitio: solo se reconstruyen si cambia el conjunto.
"""

import math
import tkinter as tk
from datetime import datetime

import customtkinter as ctk

from . import theme as t
from .closebar import CloseBar
from .mexc import fee_desglose
from .tooltip import NumeroConDetalle

POS_COLS = (
    ("par", "Par", 132, "w"),
    ("lado", "Lado", 74, "w"),
    ("apertura", "Apertura", 84, "w"),
    ("pos", "Posición", 112, "e"),
    ("entrada", "Entrada", 94, "e"),
    ("mark", "Mark price", 94, "e"),
    ("liq", "Liquidación", 100, "e"),
    ("ratio", "Margin ratio", 98, "e"),
    ("margen", "Margen", 132, "e"),
    ("pnl", "PnL", 122, "e"),
    ("fee", "Fee · %mrg / pos", 140, "e"),
    ("tpsl", "TP / SL", 188, "e"),
)

# columnas con lapiz: la cabecera reserva el mismo hueco para que el texto
# quede sobre el borde derecho del valor, no sobre el del lapiz.
PENCIL_GUTTER = 24
PENCIL_COLS = {"margen", "tpsl"}

HIST_COLS = (
    ("fecha", "Fecha", 142, "w"),
    ("par", "Par", 126, "w"),
    ("tipo", "Tipo", 92, "w"),
    ("qty", "Qty", 90, "e"),
    ("precio", "Precio", 112, "e"),
    ("pnl", "PnL", 118, "e"),
    ("fee", "Fee", 94, "e"),
    ("estado", "Estado", 106, "w"),
)

SIDES = {1: "LONG", 2: "CLOSE S", 3: "SHORT", 4: "CLOSE L"}
STATES = {1: "Pendiente", 2: "Sin llenar", 3: "Ejecutada", 4: "Cancelada", 5: "Invalida"}

ROW_H = 56
ACTION_W = 200


def _pnl_color(value):
    if value > 0:
        return t.GREEN
    if value < 0:
        return t.RED
    return t.MUTED


def _fee_color(value):
    if value > 0:
        return t.RED
    if value < 0:
        return t.GREEN
    return t.MUTED


def fmt_when(ts):
    """Apertura / fecha de orden: ms de la API -> '30/10 04:31'."""
    try:
        return datetime.fromtimestamp(float(ts) / 1000).strftime("%d/%m %H:%M")
    except Exception:
        return "—"


class Pencil(tk.Canvas):
    """Lapiz dibujado a mano: trazo fino, sin glifo de fuente, sin color de relleno."""

    def __init__(self, master, command, bg, size=20, enabled=True):
        super().__init__(
            master,
            width=size,
            height=size,
            bg=bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2" if enabled else "arrow",
        )
        self.command = command
        self.size = size
        self.enabled = enabled
        self._paint(t.MUTED if enabled else t.BORDER)
        if enabled:
            self.bind("<Button-1>", lambda e: self.command())
            self.bind("<Enter>", lambda e: self._paint(t.TEXT))
            self.bind("<Leave>", lambda e: self._paint(t.MUTED))

    def _paint(self, color):
        self.delete("all")
        scale = self.size / 18.0
        angle = math.radians(135)
        cos, sin = math.cos(angle), math.sin(angle)
        ox, oy = 13 * scale, 4 * scale
        length, half, tip = 11, 1.8, 3

        def point(x, y):
            return (ox + (x * cos - y * sin) * scale, oy + (x * sin + y * cos) * scale)

        body = [
            point(0, -half),
            point(length, -half),
            point(length + tip, 0),
            point(length, half),
            point(0, half),
        ]
        self.create_polygon(
            body, outline=color, fill="", width=max(1, round(1.2 * scale)), joinstyle="round"
        )
        self.create_line(
            point(3, -half), point(3, half), fill=color, width=max(1, round(1.1 * scale))
        )


class Header(tk.Frame):
    """Cabecera de tabla con widgets tk: pintan ~3x mas rapido que los CTk.

    Cada CTkLabel es un Canvas propio y Windows lo repinta por separado; con
    ~150 etiquetas eso convertia la restauracion de la ventana en un parpadeo.
    """

    def __init__(
        self,
        parent,
        cols,
        checkbox_var=None,
        checkbox_command=None,
        extra_right=0,
        extra_label=None,
        pencil_cols=(),
    ):
        super().__init__(parent, bg=t.SURFACE, height=t.px(36))
        self.grid_propagate(False)
        self.checkbox = None
        col = 0
        if checkbox_var is not None:
            self.grid_columnconfigure(0, minsize=30, weight=0)
            self.checkbox = ctk.CTkCheckBox(
                self,
                text="",
                width=22,
                checkbox_width=16,
                checkbox_height=16,
                variable=checkbox_var,
                command=checkbox_command,
                fg_color=t.GREEN,
                hover_color=t.GREEN,
                border_color=t.BORDER,
            )
            self.checkbox.grid(row=0, column=0, padx=(6, 0), pady=8)
            col = 1
        for i, (key, label, width, anchor) in enumerate(cols):
            gutter = PENCIL_GUTTER if key in pencil_cols else 0
            self.grid_columnconfigure(col + i, minsize=width + 8, weight=0)
            tk.Label(
                self,
                text=label,
                bg=t.SURFACE,
                fg=t.MUTED,
                font=t.ui_font(11, bold=True),
                anchor=anchor,
            ).grid(row=0, column=col + i, sticky="ew", padx=(6, 2 + gutter), pady=6)
        if extra_right:
            self.grid_columnconfigure(col + len(cols), minsize=0, weight=1)
            self.grid_columnconfigure(col + len(cols) + 1, minsize=extra_right, weight=0)
            if extra_label:
                tk.Label(
                    self,
                    text=extra_label,
                    bg=t.SURFACE,
                    fg=t.MUTED,
                    font=t.ui_font(11, bold=True),
                    anchor="e",
                ).grid(
                    row=0,
                    column=col + len(cols) + 1,
                    sticky="ew",
                    padx=(6, 10),
                    pady=6,
                )


def sync_header_pad(tabla):
    """Iguala origen y ancho de la cabecera al area donde viven las filas.

    El cuerpo tiene barra de scroll y la cabecera no: sin esto la cabecera se
    corre ~16 px respecto de los datos.
    """
    try:
        total = tabla.winfo_width()
        canvas = tabla.body._parent_canvas
        left = canvas.winfo_rootx() - tabla.winfo_rootx()
        width = canvas.winfo_width()
    except Exception:
        return
    if total < 200 or width < 200:
        return
    pad = (max(0, left), max(0, total - left - width))
    if pad == getattr(tabla, "_pad", None):
        return
    tabla._pad = pad
    try:
        tabla.header.pack_configure(padx=pad)
    except Exception:
        pass


class PositionsTable(ctk.CTkFrame):
    def __init__(
        self, parent, on_close, on_selection=None, on_tpsl=None, on_margin=None, on_reverse=None
    ):
        super().__init__(parent, fg_color="transparent")
        self.on_close = on_close
        self.on_selection = on_selection
        self.on_tpsl = on_tpsl or (lambda p: None)
        self.on_margin = on_margin or (lambda p: None)
        self.on_reverse = on_reverse or (lambda p: None)
        self.rows = {}
        self._all = ctk.BooleanVar(value=False)

        self.header = Header(
            self,
            POS_COLS,
            checkbox_var=self._all,
            checkbox_command=self._toggle_all,
            extra_right=ACTION_W,
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
            self.body, text="Sin posiciones abiertas", font=(t.UI, 13), text_color=t.MUTED
        )
        self.empty.grid(row=0, column=0, pady=30)

        # el cuerpo tiene barra de scroll y la cabecera no: se iguala el ancho
        self.bind("<Configure>", lambda e: self.after(30, self._sync_header_pad), add="+")
        self.after(150, self._sync_header_pad)

    def _sync_header_pad(self):
        sync_header_pad(self)

    # ------------------------------------------------------------- construccion
    def _rebuild(self, positions):
        for row in self.rows.values():
            row["frame"].destroy()
        self.rows = {}
        self.empty.grid_forget()

        if not positions:
            self.empty.grid(row=0, column=0, pady=30)
            return

        for index, p in enumerate(positions):
            self._add_row(p, index)

    def _add_row(self, p, index):
        bg = t.CARD if index % 2 == 0 else t.ROW_ALT
        # fila y celdas en tk: los CTkLabel/CTkFrame son Canvas aparte y el
        # repintado de la ventana completa se disparaba a ~180 ms
        frame = tk.Frame(self.body, bg=bg, height=t.px(ROW_H))
        frame.grid(row=index, column=0, sticky="ew")
        frame.grid_propagate(False)
        # fila entera de alto: asi todo queda centrado y nada toca el borde
        frame.grid_rowconfigure(0, weight=1)

        var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            frame,
            text="",
            width=22,
            checkbox_width=16,
            checkbox_height=16,
            variable=var,
            command=self._sync_all,
            fg_color=t.GREEN,
            hover_color=t.GREEN,
            border_color=t.BORDER,
        ).grid(row=0, column=0, padx=(6, 0), pady=12)
        frame.grid_columnconfigure(0, minsize=30, weight=0)

        cells = {}
        col = 1
        for key, _label, width, anchor in POS_COLS:
            frame.grid_columnconfigure(col, minsize=width + 8, weight=0)

            if key == "margen":
                cell = tk.Frame(frame, bg=bg)
                cell.grid(row=0, column=col, sticky="ew", padx=(6, 2))
                cell.grid_columnconfigure(0, weight=1)
                value = tk.Label(
                    cell, text="", bg=bg, fg=t.TEXT, font=t.num_font(13, bold=True), anchor="e"
                )
                value.grid(row=0, column=0, sticky="e")
                Pencil(
                    cell,
                    lambda pos=p: self.on_margin(pos),
                    bg=bg,
                    enabled=int(p.get("openType") or 1) == 1,
                ).grid(row=0, column=1, padx=(4, 0), sticky="e")
                cells["mar_val"] = value

            elif key == "tpsl":
                # todo alineado a la derecha: con TP, SL o ambos el borde derecho
                # del dato coincide con el de la cabecera
                cell = tk.Frame(frame, bg=bg)
                cell.grid(row=0, column=col, sticky="ew", padx=(6, 2))
                cell.grid_columnconfigure(0, weight=1)
                box = tk.Frame(cell, bg=bg)
                box.grid(row=0, column=0, sticky="e")
                Pencil(cell, lambda pos=p: self.on_tpsl(pos), bg=bg).grid(
                    row=0, column=1, sticky="e", padx=(4, 0)
                )
                tp = tk.Label(
                    box, text="", bg=bg, fg=t.GREEN, font=t.num_font(13, bold=True), anchor="e"
                )
                sep = tk.Label(
                    box, text="", bg=bg, fg=t.MUTED, font=t.num_font(13), anchor="e", padx=3
                )
                sl = tk.Label(
                    box, text="", bg=bg, fg=t.RED, font=t.num_font(13, bold=True), anchor="e"
                )
                sl.pack(side="right")
                sep.pack(side="right")
                tp.pack(side="right")
                cells["tp"], cells["sep"], cells["sl"] = tp, sep, sl

            elif key == "pnl":
                # como en MEXC: importe con su moneda y el ROE debajo
                cell = tk.Frame(frame, bg=bg)
                cell.grid(row=0, column=col, sticky="ew", padx=(6, 2))
                cell.grid_columnconfigure(0, weight=1)
                value = tk.Label(
                    cell, text="", bg=bg, fg=t.TEXT, font=t.num_font(13, bold=True), anchor="e"
                )
                value.grid(row=0, column=0, sticky="e")
                pct = tk.Label(cell, text="", bg=bg, fg=t.MUTED, font=t.num_font(11), anchor="e")
                pct.grid(row=1, column=0, sticky="e")
                cells["pnl"], cells["pnl_pct"] = value, pct

            elif key == "fee":
                # Fee = comision + funding (lo que suma MEXC), con subrayado punteado y
                # detalle al pasar el puntero. Tres lineas en alto fijo: la fuente deja
                # mas interlineado del que ocupa la fila y si no se recorta, la tercera
                # linea se sale de los 56 px. El importe lleva 24 px para que quepa la
                # linea punteada debajo del texto.
                alto = (t.px(24), t.px(15), t.px(13))
                cell = tk.Frame(frame, bg=bg, height=sum(alto))
                cell.grid(row=0, column=col, sticky="ew", padx=(6, 2))
                cell.grid_propagate(False)
                value = NumeroConDetalle(cell, bg=bg, titulo="Fee de la posición", alto=alto[0])
                share = tk.Label(cell, text="", bg=bg, fg=t.MUTED, font=t.num_font(11), anchor="e")
                saved = tk.Label(
                    cell, text="", bg=bg, fg=t.GREEN, font=t.num_font(11), anchor="e", padx=0, bd=0
                )
                y = 0
                for lbl, alto_linea in ((value, alto[0]), (share, alto[1]), (saved, alto[2])):
                    lbl.place(x=0, y=y, relwidth=1.0, height=alto_linea)
                    y += alto_linea
                cells["fee"] = value
                cells["fee_share"] = share
                cells["fee_saved"] = saved

            else:
                bold = key in ("mark", "pos", "par", "lado")
                lbl = tk.Label(
                    frame,
                    text="",
                    bg=bg,
                    fg=t.TEXT,
                    font=t.num_font(13, bold=bold),
                    anchor=anchor,
                )
                lbl.grid(row=0, column=col, sticky="ew", padx=(6, 2))
                cells[key] = lbl
            col += 1

        frame.grid_columnconfigure(col, minsize=0, weight=1)
        col += 1
        frame.grid_columnconfigure(col, minsize=ACTION_W, weight=0)
        acts = CloseBar(
            frame,
            on_close=lambda info, pos=p: self.on_close(pos, info),
            on_reverse=lambda pos=p: self.on_reverse(pos),
        )
        acts.grid(row=0, column=col, padx=(4, 6), sticky="e")

        self.rows[p.get("positionId")] = {
            "frame": frame,
            "labels": cells,
            "var": var,
            "data": p,
            "bar": acts,
        }
        self._fill(self.rows[p.get("positionId")], p)

    def _fill(self, row, p):
        long_ = int(p.get("positionType") or 1) == 1
        qty = float(p.get("holdVol") or 0)
        entry = float(p.get("holdAvgPrice") or 0)
        pnl = float(p.get("unRealizedPnl") or 0)
        liq = float(p.get("liquidatePrice") or 0)
        ratio = float(p.get("marginRatio") or 0) * 100

        size = float(p.get("_contractSize") or 0)
        mark = None
        if qty and size:
            mark = entry + (pnl / (qty * size)) * (1 if long_ else -1)

        notional = (qty * size * mark) if (mark and size) else 0.0
        # lo que MEXC llama "Fee": comision cobrada + funding (el ahorro no suma)
        fee = fee_desglose(p)

        labels = row["labels"]
        labels["par"].configure(text=p.get("_name") or p.get("symbol", ""))
        labels["lado"].configure(
            text=f"{p.get('leverage', '')}X {'LONG' if long_ else 'SHORT'}",
            fg=t.GREEN if long_ else t.RED,
        )

        labels["pos"].configure(text=f"{t.fmt_usdt(notional)} USDT" if notional else "—")
        # precios con los decimales del contrato (minimo 2): fmt_price recorta a 1
        # decimal desde 1000 y en el mark/liq se perdia el centavo
        escala = max(2, int(p.get("_priceScale") or 2))
        labels["entrada"].configure(text=t.fmt_price_exact(entry, escala))
        labels["mark"].configure(text=t.fmt_price_exact(mark, escala) if mark else "—", fg=t.MUTED)
        if mark:
            winning = mark > entry if long_ else mark < entry
            labels["mark"].configure(fg=t.GREEN if winning else t.RED)
        labels["liq"].configure(text=t.fmt_price_exact(liq, escala) if liq > 0 else "—", fg=t.GOLD)
        labels["ratio"].configure(
            text=f"{ratio:.2f}%" if ratio else "—", fg=t.GOLD if ratio >= 20 else t.TEXT
        )

        labels["apertura"].configure(text=fmt_when(p.get("createTime")), fg=t.MUTED)
        labels["mar_val"].configure(text=f"{t.fmt_usdt(p.get('im'))} USDT")
        margin = float(p.get("im") or 0)
        roe = (pnl / margin * 100) if margin else 0.0
        labels["pnl"].configure(text=f"{t.fmt_pnl(pnl)} USDT", fg=_pnl_color(pnl))
        labels["pnl_pct"].configure(text=f"{roe:+.2f}%", fg=_pnl_color(pnl))

        # fee = comision + funding; el desglose completo va en el tooltip
        total_fee = fee["total"]
        labels["fee"].set(
            f"{t.fmt_fee(total_fee)} USDT",
            _fee_color(total_fee),
            [
                ("Comisión (USDT)", t.fmt_fee(fee["comision"]), t.TEXT),
                ("Funding (USDT)", t.fmt_fee(fee["funding"]), t.RED),
                ("Fee total (USDT)", t.fmt_fee(total_fee), _fee_color(total_fee)),
                ("Fees saved (USDT)", t.fmt_fee(fee["ahorro"]), t.GREEN),
            ],
        )
        labels["fee_share"].configure(
            text=f"{t.fmt_share(total_fee / margin * 100 if margin else 0)} / "
            f"{t.fmt_share(total_fee / notional * 100 if notional else 0)}"
        )
        labels["fee_saved"].configure(
            text=f"ahorro {t.fmt_fee(fee['ahorro'])}" if fee["ahorro"] > 0 else ""
        )

        tp = float(p.get("_tp") or 0)
        sl = float(p.get("_sl") or 0)
        if tp and sl:
            labels["tp"].configure(text=t.fmt_price(tp), fg=t.GREEN)
            labels["sep"].configure(text="/")
            labels["sl"].configure(text=t.fmt_price(sl), fg=t.RED)
        elif tp:
            labels["tp"].configure(text=f"TP {t.fmt_price(tp)}", fg=t.GREEN)
            labels["sep"].configure(text="")
            labels["sl"].configure(text="")
        elif sl:
            labels["tp"].configure(text="")
            labels["sep"].configure(text="")
            labels["sl"].configure(text=f"SL {t.fmt_price(sl)}", fg=t.RED)
        else:
            labels["tp"].configure(text="—", fg=t.MUTED)
            labels["sep"].configure(text="")
            labels["sl"].configure(text="")

        row["data"] = p
        row["bar"].set_context(p, pnl, mark or 0.0, notional)

    # -------------------------------------------------------------- refresco
    def render(self, positions):
        ids = [p.get("positionId") for p in positions]
        if set(ids) != set(self.rows):
            self._rebuild(positions)
        else:
            for p in positions:
                row = self.rows.get(p.get("positionId"))
                if row:
                    self._fill(row, p)
        if self.on_selection:
            self.on_selection()

    def selected(self):
        return [row["data"] for row in self.rows.values() if row["var"].get()]

    def checked_count(self):
        return len(self.selected())

    def _toggle_all(self):
        value = bool(self._all.get())
        for row in self.rows.values():
            row["var"].set(value)

    def _sync_all(self):
        flags = [row["var"].get() for row in self.rows.values()]
        self._all.set(bool(flags) and all(flags))


class HistoryTable(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self.rows = {}

        self.header = Header(self, HIST_COLS)
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
            self.body, text="Sin operaciones registradas", font=(t.UI, 13), text_color=t.MUTED
        )
        self.empty.grid(row=0, column=0, pady=30)

    def render(self, orders):
        if orders:
            self.empty.grid_forget()
        else:
            self.empty.grid(row=0, column=0, pady=30)

        for row in self.rows.values():
            row.destroy()
        self.rows = {}

        for index, o in enumerate(orders):
            self._add_row(o, index)

    def _add_row(self, o, index):
        bg = t.CARD if index % 2 == 0 else t.ROW_ALT
        frame = tk.Frame(self.body, bg=bg, height=t.px(38))
        frame.grid(row=index, column=0, sticky="ew")
        frame.grid_propagate(False)

        pnl = float(o.get("profit") or 0)
        fee = float(o.get("totalFee") or 0)
        state = int(o.get("state") or 0)
        values = {
            "fecha": (fmt_when(o.get("createTime")), t.MUTED),
            "par": (o.get("symbol", ""), t.TEXT),
            "tipo": (SIDES.get(int(o.get("side") or 0), "?"), t.MUTED),
            "qty": (t.fmt_qty(o.get("vol")), t.TEXT),
            "precio": (t.fmt_price(o.get("dealAvgPrice") or o.get("price")), t.TEXT),
            "pnl": (t.fmt_pnl(pnl), _pnl_color(pnl)),
            "fee": (t.fmt_fee(fee), _fee_color(fee)),
            "estado": (STATES.get(state, str(state)), t.GREEN if state == 3 else t.MUTED),
        }

        for col, (key, _, width, anchor) in enumerate(HIST_COLS):
            frame.grid_columnconfigure(col, minsize=width + 8, weight=0)
            text, color = values[key]
            tk.Label(frame, text=text, bg=bg, fg=color, font=t.num_font(13), anchor=anchor).grid(
                row=0, column=col, sticky="ew", padx=(6, 2), pady=5
            )

        self.rows[o.get("orderId")] = frame
