"""Tarjeta de operacion: un par con su apalancamiento, margen, tamano y TP/SL."""
import tkinter as tk

import customtkinter as ctk

import theme as t

PRESETS = (1, 5, 10, 15, 20, 50)
WIDTH = 286


class TradeCard(ctk.CTkFrame):
    def __init__(self, parent, symbol, cfg, on_remove, on_symbol, on_trade, on_change):
        super().__init__(parent, fg_color=t.CARD, corner_radius=t.R_CARD,
                         border_width=1, border_color=t.LINE, width=WIDTH, height=486)
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        # el simbolo crudo es el que opera; el boton muestra el nombre de MEXC
        self._symbol = symbol
        self._lev_lock = False
        self.on_remove = on_remove
        self.on_symbol = on_symbol
        self.on_trade = on_trade
        self.on_change = on_change

        pad = {"padx": 12}
        row = 0

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=row, column=0, sticky="ew", pady=(10, 0), **pad)
        ctk.CTkButton(head, text="✕", width=24, height=24, corner_radius=t.R_CHIP,
                      fg_color="transparent", hover_color=t.BORDER, text_color=t.MUTED,
                      font=(t.UI, 13), command=lambda: self.on_remove(self)).pack(side="right")
        self.btn_symbol = ctk.CTkButton(head, text=symbol, height=24,
                                        corner_radius=t.R_CHIP, fg_color=t.INPUT,
                                        hover_color=t.BORDER, text_color=t.TEXT,
                                        font=(t.UI, 13, "bold"), anchor="w",
                                        command=lambda: self.on_symbol(self))
        self.btn_symbol.pack(side="left", fill="x", expand=True)
        row += 1

        price = ctk.CTkFrame(self, fg_color="transparent")
        price.grid(row=row, column=0, sticky="ew", pady=(4, 8), **pad)
        self.lbl_price = ctk.CTkLabel(price, text="—", font=(t.NUM, 19, "bold"),
                                      text_color=t.TEXT, anchor="w")
        self.lbl_price.pack(side="left")
        self.lbl_change = ctk.CTkLabel(price, text="", font=(t.NUM, 12),
                                       text_color=t.MUTED, anchor="e")
        self.lbl_change.pack(side="right")
        row += 1

        lev = ctk.CTkFrame(self, fg_color="transparent")
        lev.grid(row=row, column=0, sticky="ew", **pad)
        ctk.CTkLabel(lev, text="Apalancamiento", font=(t.UI, 12),
                     text_color=t.MUTED).pack(side="left")
        ctk.CTkLabel(lev, text="x", font=(t.NUM, 12),
                     text_color=t.MUTED).pack(side="right")
        self.var_lev = tk.StringVar(value=str(cfg.get("leverage", 10)))
        ctk.CTkEntry(lev, textvariable=self.var_lev, width=46, height=24,
                     border_width=0, fg_color=t.INPUT, text_color=t.TEXT,
                     font=(t.NUM, 13, "bold"), justify="right").pack(side="right", padx=(0, 4))
        row += 1

        presets = ctk.CTkFrame(self, fg_color="transparent")
        presets.grid(row=row, column=0, sticky="ew", pady=(4, 0), **pad)
        self.preset_btns = {}
        for p in PRESETS:
            b = ctk.CTkButton(presets, text=str(p), width=32, height=24,
                              corner_radius=t.R_CHIP, fg_color=t.INPUT,
                              hover_color=t.BORDER, text_color=t.MUTED,
                              font=(t.UI, 11), command=lambda v=p: self._set_leverage(v))
            b.pack(side="left", padx=(0, 3))
            self.preset_btns[p] = b
        row += 1

        self.var_margin = tk.StringVar(value=cfg.get("margin", "Aislado"))
        self.seg_margin = ctk.CTkSegmentedButton(
            self, values=["Aislado", "Cruzado"], variable=self.var_margin,
            height=26, corner_radius=t.R_CTRL, font=(t.UI, 12),
            fg_color=t.BORDER, border_width=1, selected_color=t.ACCENT_SOFT,
            selected_hover_color=t.ACCENT_SOFT, unselected_color=t.INPUT,
            unselected_hover_color=t.BORDER, text_color=t.TEXT,
            text_color_disabled=t.MUTED, command=lambda _v: self.on_change(self))
        self.seg_margin.grid(row=row, column=0, sticky="ew", pady=(10, 0), **pad)
        row += 1

        self.var_mode = tk.StringVar(value=cfg.get("size_mode", "Margen"))
        self.seg_mode = ctk.CTkSegmentedButton(
            self, values=["Margen", "Nocional"], variable=self.var_mode,
            height=26, corner_radius=t.R_CTRL, font=(t.UI, 12),
            fg_color=t.BORDER, border_width=1, selected_color=t.ACCENT_SOFT,
            selected_hover_color=t.ACCENT_SOFT, unselected_color=t.INPUT,
            unselected_hover_color=t.BORDER, text_color=t.TEXT,
            text_color_disabled=t.MUTED, command=lambda _v: self.on_change(self))
        self.seg_mode.grid(row=row, column=0, sticky="ew", pady=(6, 0), **pad)
        row += 1

        size = ctk.CTkFrame(self, fg_color="transparent")
        size.grid(row=row, column=0, sticky="ew", pady=(10, 0), **pad)
        size.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(size, text="Tamaño (USDT)", font=(t.UI, 10),
                     text_color=t.MUTED, anchor="w").grid(row=0, column=0, sticky="w",
                                                          columnspan=2, pady=(0, 2))
        self.var_size = tk.StringVar(value="")
        ctk.CTkEntry(size, textvariable=self.var_size, fg_color=t.INPUT,
                     border_color=t.BORDER, border_width=1, corner_radius=t.R_CTRL,
                     text_color=t.TEXT, font=(t.NUM, 16, "bold"), justify="right",
                     height=36).grid(row=1, column=0, sticky="ew")
        ctk.CTkLabel(size, text="USDT", font=(t.UI, 10),
                     text_color=t.MUTED).grid(row=1, column=1, padx=(6, 10))
        row += 1

        tpsl = ctk.CTkFrame(self, fg_color="transparent")
        tpsl.grid(row=row, column=0, sticky="ew", pady=(8, 0), **pad)
        tpsl.grid_columnconfigure(0, weight=1)
        tpsl.grid_columnconfigure(1, weight=1)
        self.var_tp = tk.StringVar()
        self.var_sl = tk.StringVar()
        for col, (label, var) in enumerate((("TP", self.var_tp), ("SL", self.var_sl))):
            off = (0, 4) if col == 0 else (4, 0)
            ctk.CTkLabel(tpsl, text=label, font=(t.UI, 10), text_color=t.MUTED,
                         anchor="w").grid(row=0, column=col, sticky="w", padx=off,
                                            pady=(0, 2))
            ctk.CTkEntry(tpsl, textvariable=var, fg_color=t.INPUT,
                         border_color=t.BORDER, border_width=1, corner_radius=t.R_CTRL,
                         text_color=t.TEXT, font=(t.NUM, 12), height=34).grid(
                row=1, column=col, sticky="ew", padx=off)
        row += 1

        self.lbl_calc = ctk.CTkLabel(self, text="—", font=(t.NUM, 12),
                                     text_color=t.MUTED, anchor="w", justify="left")
        self.lbl_calc.grid(row=row, column=0, sticky="ew", pady=(8, 0), **pad)
        row += 1

        self.btn_long = ctk.CTkButton(self, text="LONG", height=34, corner_radius=t.R_CTRL,
                                      fg_color=t.GREEN, hover_color="#18B374",
                                      text_color="#04140D", font=(t.UI, 14, "bold"),
                                      command=lambda: self.on_trade(self, "LONG"))
        self.btn_long.grid(row=row, column=0, sticky="ew", pady=(10, 0), **pad)
        row += 1
        self.btn_short = ctk.CTkButton(self, text="SHORT", height=34, corner_radius=t.R_CTRL,
                                       fg_color=t.RED, hover_color="#E03A50",
                                       text_color="#150508", font=(t.UI, 14, "bold"),
                                       command=lambda: self.on_trade(self, "SHORT"))
        self.btn_short.grid(row=row, column=0, sticky="ew", pady=(6, 12), **pad)

        self.var_lev.trace_add("write", lambda *_: self._changed())
        self.var_size.trace_add("write", lambda *_: self._changed())
        self.var_mode.trace_add("write", lambda *_: self._changed())
        self.var_lev.trace_add("write", lambda *_: self._sync_lev())
        self._sync_presets()

    # ------------------------------------------------------------------ estado
    @property
    def symbol(self):
        return self._symbol

    def config(self):
        # el tamaño no se guarda: cada sesion arranca vacia a proposito
        return {
            "symbol": self.symbol,
            "leverage": self.var_lev.get(),
            "margin": self.var_margin.get(),
            "size_mode": self.var_mode.get(),
        }

    def form(self):
        """Valores ya parseados, o None si algo no es numero."""
        try:
            lev = int(float(self.var_lev.get()))
            size = float(self.var_size.get())
        except ValueError:
            return None
        if lev < 1 or size <= 0:
            return None
        tp = self.var_tp.get().strip()
        sl = self.var_sl.get().strip()
        for value in (tp, sl):
            if value:
                try:
                    float(value)
                except ValueError:
                    return None
        notional = size * lev if self.var_mode.get() == "Margen" else size
        return {
            "symbol": self.symbol,
            "lev": lev,
            "size": size,
            "notional": notional,
            "tp": float(tp) if tp else None,
            "sl": float(sl) if sl else None,
            "open_type": 1 if self.var_margin.get() == "Aislado" else 2,
            "margin_mode": self.var_margin.get(),
            "size_mode": self.var_mode.get(),
        }

    def set_symbol(self, symbol):
        self._symbol = symbol
        self.btn_symbol.configure(text=symbol)
        self.lbl_price.configure(text="—")
        self.lbl_change.configure(text="")
        self._changed()

    def set_name(self, name):
        """Nombre tal como lo muestra MEXC: GOLD(XAU)USDT."""
        self.btn_symbol.configure(text=name or self._symbol)

    def set_price(self, price, change):
        self.lbl_price.configure(text=t.fmt_price(price))
        self.lbl_change.configure(text=t.fmt_pct(change),
                                  text_color=t.GREEN if change >= 0 else t.RED)

    def set_preview(self, text):
        self.lbl_calc.configure(text=text)

    def set_busy(self, busy):
        state = "disabled" if busy else "normal"
        self.btn_long.configure(state=state)
        self.btn_short.configure(state=state)

    # ---------------------------------------------------------------- interno
    def _changed(self):
        self.on_change(self)

    def _set_leverage(self, value):
        self._lev_lock = True
        self.var_lev.set(str(value))
        self._lev_lock = False
        self._sync_presets()

    def _sync_lev(self):
        self._sync_presets()

    def _sync_presets(self):
        try:
            current = int(float(self.var_lev.get()))
        except ValueError:
            current = 0
        if current == getattr(self, "_last_preset", None):
            return
        self._last_preset = current
        for value, button in self.preset_btns.items():
            button.configure(fg_color=t.ACCENT_SOFT if value == current else t.INPUT,
                             text_color=t.TEXT if value == current else t.MUTED)
