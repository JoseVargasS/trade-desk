"""Barra de cierre de una fila de posiciones: precio, cantidad y botones.

Vive aparte de table.py porque trae sus dos popups (precio y porcentaje) y
table.py ya esta cerca del tope de lineas. No habla con la API: solo junta
lo que el usuario eligio y se lo pasa a la accion de cerrar.
"""
import math

import customtkinter as ctk

import theme as t
from mexc import close_vol

W_PRICE = 106
W_PCT = 78
W_CLOSE = 102
W_REVERSE = 82
H_FIELD = 22
H_BTN = 26


class _Popup(ctk.CTkToplevel):
    """Panel chico pegado debajo del control que lo abre. Modal, Escape lo cierra."""

    def __init__(self, anchor, width):
        super().__init__(anchor)
        self.anchor = anchor
        self.overrideredirect(True)
        self.configure(fg_color=t.LINE)
        self.transient(anchor.winfo_toplevel())
        self.wrap = ctk.CTkFrame(self, fg_color=t.CARD, corner_radius=t.R_CARD,
                                 width=width)
        self.wrap.pack(fill="both", expand=True, padx=1, pady=1)
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Button-1>", self._click_out)
        self.grab_set()

    def _click_out(self, event):
        # con grab, el clic fuera de la ventana llega al propio toplevel
        if event.widget in (self, self.wrap):
            self.destroy()

    def show(self):
        self.update_idletasks()
        try:
            x = self.anchor.winfo_rootx()
            y = self.anchor.winfo_rooty() + self.anchor.winfo_height() + 4
            w = self.winfo_reqwidth()
            if x + w > self.winfo_screenwidth() - 8:
                x = self.winfo_screenwidth() - 8 - w
        except Exception:
            x, y = 200, 200
        self.geometry(f"+{max(0, x)}+{y}")
        self.focus_force()

    def destroy(self):
        super().destroy()
        try:
            self.anchor.focus_set()
        except Exception:
            pass


class _PercentPopup(_Popup):
    """Barra de % con la casilla exacta y lo que se va a cerrar."""

    def __init__(self, bar):
        super().__init__(bar.pct_btn, 250)
        self.bar = bar
        self.low = bar.min_pct()

        self.lines = ctk.CTkLabel(self.wrap, text="", font=(t.NUM, 10),
                                  text_color=t.MUTED, justify="left", anchor="w")
        self.lines.pack(fill="x", padx=12, pady=(10, 8))

        self.slider = ctk.CTkSlider(
            self.wrap, width=214, height=14, from_=self.low, to=100,
            number_of_steps=max(1, int(100 - self.low)),
            fg_color=t.BORDER, progress_color=t.TEXT,
            button_color=t.TEXT, button_hover_color=t.TEXT,
            command=self._slide)
        self.slider.set(max(self.low, bar.pct))
        self.slider.pack(padx=12, pady=(0, 2))

        ticks = ctk.CTkFrame(self.wrap, fg_color="transparent")
        ticks.pack(fill="x", padx=14)
        for i, label in enumerate(("1", "25", "50", "75", "100")):
            ticks.grid_columnconfigure(i, weight=1, uniform="tick")
            ctk.CTkLabel(ticks, text=label, font=(t.NUM, 9),
                         text_color=t.BORDER).grid(row=0, column=i, sticky="nsew")

        row = ctk.CTkFrame(self.wrap, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(8, 10))
        self.var = ctk.StringVar(value=f"{bar.pct:.0f}")
        self.entry = ctk.CTkEntry(row, textvariable=self.var, width=54, height=24,
                                  fg_color=t.INPUT, border_color=t.BORDER,
                                  text_color=t.TEXT, font=(t.NUM, 12), justify="right")
        self.entry.pack(side="left")
        ctk.CTkLabel(row, text="%", font=(t.NUM, 12), text_color=t.MUTED).pack(
            side="left", padx=(4, 0))
        self.entry.bind("<KeyRelease>", self._typed)
        self.entry.bind("<Return>", lambda e: self.destroy())
        self.entry.bind("<FocusOut>", lambda e: self.var.set(f"{self.bar.pct:.0f}"))
        ctk.CTkButton(row, text="Listo", width=64, height=24, corner_radius=t.R_CHIP,
                      fg_color=t.INPUT, hover_color=t.BORDER, border_width=1,
                      border_color=t.BORDER, text_color=t.TEXT, font=(t.UI, 11),
                      command=self.destroy).pack(side="right")

        self._render()
        self.show()
        self.entry.focus_set()
        self.entry.select_range(0, "end")

    def _slide(self, value):
        self.bar.set_pct(value)
        self.var.set(f"{self.bar.pct:.0f}")
        self.slider.set(self.bar.pct)
        self._render()

    def _typed(self, _event=None):
        try:
            value = float(self.var.get().replace(",", ".").strip())
        except ValueError:
            return
        self.bar.set_pct(value)
        self.slider.set(self.bar.pct)
        self._render()

    def _render(self):
        pct = self.bar.pct
        minimo = self.bar.unit * self.bar.size * self.bar.mark
        self.lines.configure(text=(
            f"Cerrable: {t.fmt_fee(self.bar.notional)} USDT\n"
            f"Cierras: {t.fmt_fee(self.bar.notional * pct / 100)} USDT "
            f"≈ {t.fmt_qty(close_vol(self.bar.hold, pct))} contratos\n"
            f"Mínimo: {t.fmt_qty(self.bar.unit)} contrato ({t.fmt_fee(minimo)} USDT)"))


class _PricePopup(_Popup):
    """Mercado o precio limite, en el mismo campo."""

    def __init__(self, bar):
        super().__init__(bar.price_btn, 236)
        self.bar = bar
        self.seg = ctk.CTkSegmentedButton(
            self.wrap, values=["Mercado", "Límite"], height=26, width=204,
            fg_color=t.INPUT, selected_color=t.ACCENT_SOFT,
            selected_hover_color=t.ACCENT_SOFT, unselected_color=t.INPUT,
            unselected_hover_color=t.BORDER, text_color=t.TEXT,
            font=(t.UI, 11), command=self._mode)
        self.seg.pack(fill="x", padx=12, pady=(10, 8))

        self.var = ctk.StringVar(value=t.fmt_price_exact(bar.limit_price or bar.mark,
                                                         bar.scale))
        self.entry = ctk.CTkEntry(self.wrap, textvariable=self.var, height=26,
                                  width=204, fg_color=t.INPUT, border_color=t.BORDER,
                                  text_color=t.TEXT, font=(t.NUM, 12), justify="right")
        self.entry.pack(fill="x", padx=12)
        ctk.CTkButton(self.wrap, text="Listo", width=78, height=26,
                      corner_radius=t.R_CHIP, fg_color=t.INPUT, hover_color=t.BORDER,
                      border_width=1, border_color=t.BORDER, text_color=t.TEXT,
                      font=(t.UI, 11), command=self._apply).pack(
            anchor="e", padx=12, pady=(8, 10))
        self.entry.bind("<Return>", lambda e: self._apply())

        self.seg.set("Límite" if bar.limit_price else "Mercado")
        self._mode(self.seg.get())
        self.show()

    def _mode(self, value):
        if value == "Límite":
            self.var.set(t.fmt_price_exact(self.bar.limit_price or self.bar.mark,
                                          self.bar.scale))
            self.entry.configure(state="normal", text_color=t.TEXT)
            self.entry.focus_set()
            self.entry.select_range(0, "end")
        else:
            self.entry.configure(state="disabled")

    def _apply(self):
        if self.seg.get() == "Mercado":
            self.bar.set_price(None)
            self.destroy()
            return
        try:
            price = float(self.var.get().replace(",", "").strip())
        except ValueError:
            price = 0.0
        if price <= 0:
            self.var.set(t.fmt_price_exact(self.bar.mark, self.bar.scale))
            return
        self.bar.set_price(price)
        self.destroy()


class CloseBar(ctk.CTkFrame):
    """Dos lineas en el hueco de acciones: [precio][%] y [Cerrar LADO][Reverse]."""

    def __init__(self, parent, on_close, on_reverse):
        super().__init__(parent, fg_color="transparent")
        self.on_close = on_close
        self.on_reverse = on_reverse
        self.pct = 100.0
        self.limit_price = None
        self.long = True
        self.hold = 0.0
        self.notional = 0.0
        self.mark = 0.0
        self.size = 0.0
        self.unit = 1.0
        self.scale = 2

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(anchor="e")
        self.price_btn = ctk.CTkButton(
            top, text="Mercado", width=W_PRICE, height=H_FIELD,
            corner_radius=t.R_CHIP, fg_color=t.INPUT, hover_color=t.BORDER,
            border_width=1, border_color=t.BORDER, text_color=t.MUTED,
            font=(t.UI, 11), command=self._open_price)
        self.price_btn.pack(side="left")
        self.pct_btn = ctk.CTkButton(
            top, text="100%", width=W_PCT, height=H_FIELD, corner_radius=t.R_CHIP,
            fg_color=t.INPUT, hover_color=t.BORDER, border_width=1,
            border_color=t.BORDER, text_color=t.TEXT, font=(t.NUM, 11),
            command=self._open_pct)
        self.pct_btn.pack(side="left", padx=(6, 0))

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(anchor="e", pady=(4, 0))
        self.close_btn = ctk.CTkButton(
            bottom, text="Cerrar", width=W_CLOSE, height=H_BTN,
            corner_radius=t.R_CHIP, fg_color=t.GREEN, hover_color=t.GREEN_HOVER,
            text_color=t.ON_GREEN, font=(t.UI, 12, "bold"), command=self._close)
        self.close_btn.pack(side="left")
        ctk.CTkButton(bottom, text="Reverse", width=W_REVERSE, height=H_BTN,
                      corner_radius=t.R_CHIP, fg_color=t.INPUT, hover_color=t.BORDER,
                      border_width=1, border_color=t.BORDER, text_color=t.TEXT,
                      font=(t.UI, 11), command=self.on_reverse).pack(
            side="left", padx=(6, 0))

    # ------------------------------------------------------------------ estado
    def set_context(self, pos, pnl, mark, notional):
        """Datos frescos de la fila: no toca lo que el usuario ya eligio."""
        self.long = int(pos.get("positionType") or 1) == 1
        self.hold = float(pos.get("holdVol") or 0)
        self.size = float(pos.get("_contractSize") or 0)
        self.unit = float(pos.get("_volUnit") or 1)
        self.scale = int(pos.get("_priceScale") or 2)
        self.mark = float(mark or 0)
        self.notional = float(notional or 0)

        if pnl > 0:
            fg, hover, on = t.GREEN, t.GREEN_HOVER, t.ON_GREEN
        elif pnl < 0:
            fg, hover, on = t.RED, t.RED_HOVER, t.ON_RED
        else:
            fg, hover, on = t.MUTED, t.BORDER, t.BG
        self.close_btn.configure(text=f"Cerrar {'LONG' if self.long else 'SHORT'}",
                                 fg_color=fg, hover_color=hover, text_color=on)

    def min_pct(self):
        """% mas chico que todavia cierra al menos un contrato."""
        if self.hold < 1:
            return 100.0
        return max(1.0, math.ceil(100.0 / self.hold))

    def set_pct(self, value):
        self.pct = min(100.0, max(self.min_pct(), float(value)))
        self.pct_btn.configure(text=f"{self.pct:.0f}%")

    def set_price(self, price):
        self.limit_price = float(price) if price else None
        if self.limit_price:
            self.price_btn.configure(
                text=t.fmt_price_exact(self.limit_price, self.scale),
                text_color=t.TEXT)
        else:
            self.price_btn.configure(text="Mercado", text_color=t.MUTED)

    # ----------------------------------------------------------------- popups
    def _open_pct(self):
        _PercentPopup(self)

    def _open_price(self):
        _PricePopup(self)

    def _close(self):
        self.on_close({"pct": self.pct, "price": self.limit_price})
