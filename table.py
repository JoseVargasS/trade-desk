"""Tablas de posiciones e historial.

Filas hechas con widgets (no Treeview) para poder colorear celda por celda.
Las filas se actualizan en sitio: solo se reconstruyen si cambia el conjunto.
"""
import math
import tkinter as tk
from datetime import datetime

import customtkinter as ctk

import theme as t

POS_COLS = (
    ("par", "Par", 124, "w"),
    ("lado", "Lado", 95, "w"),
    ("pos", "Posición", 102, "e"),
    ("entrada", "Entrada", 97, "e"),
    ("mark", "Mark", 97, "e"),
    ("liq", "Liquidación", 104, "e"),
    ("ratio", "Margen %", 86, "e"),
    ("margen", "Margen", 152, "e"),
    ("pnl", "PnL", 106, "e"),
    ("fee", "Fee", 82, "e"),
    ("tpsl", "TP / SL", 190, "e"),
)

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

ROW_H = 46
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


class Pencil(tk.Canvas):
    """Lapiz dibujado a mano: trazo fino, sin glifo de fuente, sin color de relleno."""

    def __init__(self, master, command, bg, size=20, enabled=True):
        super().__init__(master, width=size, height=size, bg=bg,
                         highlightthickness=0, bd=0,
                         cursor="hand2" if enabled else "arrow")
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
            return (ox + (x * cos - y * sin) * scale,
                    oy + (x * sin + y * cos) * scale)

        body = [point(0, -half), point(length, -half), point(length + tip, 0),
                point(length, half), point(0, half)]
        self.create_polygon(body, outline=color, fill="",
                            width=max(1, round(1.2 * scale)), joinstyle="round")
        self.create_line(point(3, -half), point(3, half), fill=color,
                         width=max(1, round(1.1 * scale)))


class _Header(ctk.CTkFrame):
    def __init__(self, parent, cols, checkbox_var=None, checkbox_command=None,
                 extra_right=0):
        super().__init__(parent, fg_color=t.SURFACE, corner_radius=0, height=36)
        self.grid_propagate(False)
        self.checkbox = None
        col = 0
        if checkbox_var is not None:
            self.grid_columnconfigure(0, minsize=30, weight=0)
            self.checkbox = ctk.CTkCheckBox(
                self, text="", width=22, checkbox_width=16, checkbox_height=16,
                variable=checkbox_var, command=checkbox_command,
                fg_color=t.GREEN, hover_color=t.GREEN, border_color=t.BORDER)
            self.checkbox.grid(row=0, column=0, padx=(6, 0), pady=8)
            col = 1
        for i, (_, label, width, anchor) in enumerate(cols):
            self.grid_columnconfigure(col + i, minsize=width + 8, weight=0)
            ctk.CTkLabel(self, text=label, font=(t.UI, 11, "bold"), text_color=t.MUTED,
                         anchor=anchor, width=width).grid(
                row=0, column=col + i, sticky="ew", padx=(6, 2), pady=5)
        if extra_right:
            self.grid_columnconfigure(col + len(cols), minsize=0, weight=1)
            self.grid_columnconfigure(col + len(cols) + 1, minsize=extra_right, weight=0)


class PositionsTable(ctk.CTkFrame):
    def __init__(self, parent, on_close, on_selection=None, on_tpsl=None,
                 on_margin=None, on_reverse=None):
        super().__init__(parent, fg_color="transparent")
        self.on_close = on_close
        self.on_selection = on_selection
        self.on_tpsl = on_tpsl or (lambda p: None)
        self.on_margin = on_margin or (lambda p: None)
        self.on_reverse = on_reverse or (lambda p: None)
        self.rows = {}
        self._all = ctk.BooleanVar(value=False)

        self.header = _Header(self, POS_COLS, checkbox_var=self._all,
                              checkbox_command=self._toggle_all, extra_right=ACTION_W)
        self.header.pack(fill="x")

        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                           scrollbar_button_color=t.INPUT,
                                           scrollbar_button_hover_color=t.BORDER)
        self.body.pack(fill="both", expand=True, pady=(4, 0))
        self.body.grid_columnconfigure(0, weight=1)

        self.empty = ctk.CTkLabel(self.body, text="Sin posiciones abiertas",
                                  font=(t.UI, 13), text_color=t.MUTED)
        self.empty.grid(row=0, column=0, pady=30)

        # el cuerpo tiene barra de scroll y la cabecera no: se iguala el ancho
        self.bind("<Configure>", lambda e: self.after(30, self._sync_header_pad), add="+")
        self.after(150, self._sync_header_pad)

    def _sync_header_pad(self):
        """Iguala origen y ancho de la cabecera al area donde viven las filas."""
        try:
            total = self.winfo_width()
            canvas = self.body._parent_canvas
            left = canvas.winfo_rootx() - self.winfo_rootx()
            width = canvas.winfo_width()
        except Exception:
            return
        if total < 200 or width < 200:
            return
        pad = (max(0, left), max(0, total - left - width))
        if pad == getattr(self, "_pad", None):
            return
        self._pad = pad
        try:
            self.header.pack_configure(padx=pad)
        except Exception:
            pass

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
        frame = ctk.CTkFrame(self.body, fg_color=bg, corner_radius=0, height=ROW_H)
        frame.grid(row=index, column=0, sticky="ew")
        frame.grid_propagate(False)

        var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(frame, text="", width=22, checkbox_width=16, checkbox_height=16,
                        variable=var, command=self._sync_all,
                        fg_color=t.GREEN, hover_color=t.GREEN,
                        border_color=t.BORDER).grid(row=0, column=0, padx=(6, 0), pady=12)
        frame.grid_columnconfigure(0, minsize=30, weight=0)

        cells = {}
        col = 1
        for key, _label, width, anchor in POS_COLS:
            frame.grid_columnconfigure(col, minsize=width + 8, weight=0)

            if key == "margen":
                cell = ctk.CTkFrame(frame, fg_color="transparent")
                cell.grid(row=0, column=col, sticky="ew", padx=(6, 2))
                cell.grid_columnconfigure(0, weight=1)
                value = ctk.CTkLabel(cell, text="", font=(t.NUM, 13, "bold"),
                                     text_color=t.TEXT, anchor="e")
                value.grid(row=0, column=0, sticky="e")
                Pencil(cell, lambda pos=p: self.on_margin(pos), bg=bg,
                       enabled=int(p.get("openType") or 1) == 1).grid(row=0, column=1, padx=(6, 0))
                cells["mar_val"] = value

            elif key == "tpsl":
                cell = ctk.CTkFrame(frame, fg_color="transparent")
                cell.grid(row=0, column=col, sticky="ew", padx=(6, 2))
                tp = ctk.CTkLabel(cell, text="", font=(t.NUM, 13, "bold"),
                                  text_color=t.GREEN, anchor="e")
                sep = ctk.CTkLabel(cell, text="", font=(t.NUM, 13),
                                   text_color=t.MUTED, anchor="center", width=18)
                sl = ctk.CTkLabel(cell, text="", font=(t.NUM, 13, "bold"),
                                  text_color=t.RED, anchor="w")
                tp.pack(side="left", expand=True, fill="x")
                sep.pack(side="left")
                sl.pack(side="left", expand=True, fill="x")
                Pencil(cell, lambda pos=p: self.on_tpsl(pos), bg=bg).pack(
                    side="right", padx=(6, 0))
                cells["tp"], cells["sep"], cells["sl"] = tp, sep, sl

            elif key == "pnl":
                cell = ctk.CTkFrame(frame, fg_color="transparent")
                cell.grid(row=0, column=col, sticky="ew", padx=(6, 2))
                cell.grid_columnconfigure(0, weight=1)
                value = ctk.CTkLabel(cell, text="", font=(t.NUM, 13, "bold"),
                                     text_color=t.TEXT, anchor="e")
                value.grid(row=0, column=0, sticky="e")
                pct = ctk.CTkLabel(cell, text="", font=(t.NUM, 11),
                                   text_color=t.MUTED, anchor="e")
                pct.grid(row=1, column=0, sticky="e")
                cells["pnl"], cells["pnl_pct"] = value, pct

            else:
                bold = "bold" if key in ("mark", "pos", "par", "lado") else None
                font = (t.NUM, 13, bold) if bold else (t.NUM, 13)
                lbl = ctk.CTkLabel(frame, text="", font=font, text_color=t.TEXT,
                                   anchor=anchor, width=width)
                lbl.grid(row=0, column=col, sticky="ew", padx=(6, 2))
                cells[key] = lbl
            col += 1

        frame.grid_columnconfigure(col, minsize=0, weight=1)
        col += 1
        frame.grid_columnconfigure(col, minsize=ACTION_W, weight=0)
        acts = ctk.CTkFrame(frame, fg_color="transparent")
        acts.grid(row=0, column=col, padx=(4, 6), sticky="e")
        ctk.CTkButton(acts, text="Cerrar", width=84, height=28, corner_radius=t.R_CHIP,
                      fg_color=t.GREEN, hover_color="#18B374", text_color="#04140D",
                      font=(t.UI, 13, "bold"),
                      command=lambda pos=p: self.on_close(pos)).pack(side="left")
        ctk.CTkButton(acts, text="Reverse", width=92, height=28, corner_radius=t.R_CHIP,
                      fg_color=t.INPUT, hover_color=t.BORDER, border_width=1,
                      border_color=t.BORDER, text_color=t.TEXT,
                      font=(t.UI, 12),
                      command=lambda pos=p: self.on_reverse(pos)).pack(side="left", padx=(6, 0))

        self.rows[p.get("positionId")] = {
            "frame": frame, "labels": cells, "var": var, "data": p,
        }
        self._fill(self.rows[p.get("positionId")], p)

    def _fill(self, row, p):
        long_ = int(p.get("positionType") or 1) == 1
        qty = float(p.get("holdVol") or 0)
        entry = float(p.get("holdAvgPrice") or 0)
        pnl = float(p.get("unRealizedPnl") or 0)
        fee = float(p.get("totalFee") or 0)
        liq = float(p.get("liquidatePrice") or 0)
        ratio = float(p.get("marginRatio") or 0) * 100

        size = float(p.get("_contractSize") or 0)
        mark = None
        if qty and size:
            mark = entry + (pnl / (qty * size)) * (1 if long_ else -1)

        labels = row["labels"]
        labels["par"].configure(text=p.get("symbol", ""))
        labels["lado"].configure(
            text=f"{p.get('leverage', '')}X {'LONG' if long_ else 'SHORT'}",
            text_color=t.GREEN if long_ else t.RED)

        labels["pos"].configure(text=t.fmt_usdt(qty * size * mark) if (mark and size) else "—")
        labels["entrada"].configure(text=t.fmt_price(entry))
        labels["mark"].configure(text=t.fmt_price(mark) if mark else "—",
                                 text_color=t.MUTED)
        if mark:
            winning = mark > entry if long_ else mark < entry
            labels["mark"].configure(text_color=t.GREEN if winning else t.RED)
        labels["liq"].configure(text=t.fmt_price(liq) if liq > 0 else "—",
                                text_color=t.GOLD)
        labels["ratio"].configure(text=f"{ratio:.2f}%" if ratio else "—",
                                  text_color=t.GOLD if ratio >= 20 else t.TEXT)

        labels["mar_val"].configure(text=f"{t.fmt_usdt(p.get('im'))} USDT")

        margin = float(p.get("im") or 0)
        roe = (pnl / margin * 100) if margin else 0.0
        labels["pnl"].configure(text=t.fmt_pnl(pnl), text_color=_pnl_color(pnl))
        labels["pnl_pct"].configure(text=f"{roe:+.2f}%", text_color=_pnl_color(pnl))
        labels["fee"].configure(text=t.fmt_fee(fee), text_color=_fee_color(fee))

        tp = float(p.get("_tp") or 0)
        sl = float(p.get("_sl") or 0)
        if tp and sl:
            labels["tp"].configure(text=t.fmt_price(tp))
            labels["sep"].configure(text="/")
            labels["sl"].configure(text=t.fmt_price(sl))
        elif tp:
            labels["tp"].configure(text=f"TP {t.fmt_price(tp)}")
            labels["sep"].configure(text="")
            labels["sl"].configure(text="")
        elif sl:
            labels["tp"].configure(text="")
            labels["sep"].configure(text="")
            labels["sl"].configure(text=f"SL {t.fmt_price(sl)}")
        else:
            labels["tp"].configure(text="—", text_color=t.MUTED)
            labels["sep"].configure(text="")
            labels["sl"].configure(text="")
        if tp:
            labels["tp"].configure(text_color=t.GREEN)
        if sl:
            labels["sl"].configure(text_color=t.RED)

        row["data"] = p

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

        self.header = _Header(self, HIST_COLS)
        self.header.pack(fill="x")

        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                           scrollbar_button_color=t.INPUT,
                                           scrollbar_button_hover_color=t.BORDER)
        self.body.pack(fill="both", expand=True, pady=(4, 0))
        self.body.grid_columnconfigure(0, weight=1)

        self.empty = ctk.CTkLabel(self.body, text="Sin operaciones registradas",
                                  font=(t.UI, 13), text_color=t.MUTED)
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
        frame = ctk.CTkFrame(self.body, fg_color=bg, corner_radius=0, height=38)
        frame.grid(row=index, column=0, sticky="ew")
        frame.grid_propagate(False)

        pnl = float(o.get("profit") or 0)
        fee = float(o.get("totalFee") or 0)
        state = int(o.get("state") or 0)
        ts = o.get("createTime") or 0
        try:
            when = datetime.fromtimestamp(ts / 1000).strftime("%d/%m %H:%M:%S")
        except Exception:
            when = "—"

        values = {
            "fecha": (when, t.MUTED),
            "par": (o.get("symbol", ""), t.TEXT),
            "tipo": (SIDES.get(int(o.get("side") or 0), "?"), t.MUTED),
            "qty": (t.fmt_qty(o.get("vol")), t.TEXT),
            "precio": (t.fmt_price(o.get("dealAvgPrice") or o.get("price")), t.TEXT),
            "pnl": (t.fmt_pnl(pnl), _pnl_color(pnl)),
            "fee": (t.fmt_fee(fee), _fee_color(fee)),
            "estado": (STATES.get(state, str(state)),
                       t.GREEN if state == 3 else t.MUTED),
        }

        for col, (key, _, width, anchor) in enumerate(HIST_COLS):
            frame.grid_columnconfigure(col, minsize=width + 8, weight=0)
            text, color = values[key]
            ctk.CTkLabel(frame, text=text, font=(t.NUM, 13), text_color=color,
                         anchor=anchor, width=width).grid(
                row=0, column=col, sticky="ew", padx=(6, 2), pady=5)

        self.rows[o.get("orderId")] = frame
