"""Buscador de pares: filtro puro y ventana flotante de seleccion rapida."""
import tkinter as tk

import customtkinter as ctk

import theme as t

FAVORITOS = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT"]


def _is_usdt(contract):
    return (contract.get("quoteCoin") or "USDT").upper() == "USDT"


def contract_line(c):
    return (f"{c['symbol']}    {c.get('maxLeverage', '')}x    "
            f"1 = {t.fmt_qty(c.get('contractSize'))} {c.get('baseCoin', '')}")


def filter_markets(markets, text, limit=60):
    """USDT primero, luego prefijo exacto, luego 'contiene'."""
    query = (text or "").strip().upper().replace("-", "_").replace("/", "_")
    items = list(markets.values())

    if not query:
        top = [markets[s] for s in FAVORITOS if s in markets]
        seen = {c["symbol"] for c in top}
        rest = [c for c in items if c["symbol"] not in seen and _is_usdt(c)]
        return top + rest[:limit]

    starts, contains = [], []
    for c in items:
        symbol = c["symbol"]
        base = (c.get("baseCoin") or "").upper()
        if symbol.startswith(query) or base == query:
            starts.append(c)
        elif query in symbol:
            contains.append(c)

    # orden estable: los pares USDT primero dentro de cada grupo
    starts.sort(key=lambda c: 0 if _is_usdt(c) else 1)
    contains.sort(key=lambda c: 0 if _is_usdt(c) else 1)
    return (starts + contains)[:limit]


class SearchPopup(ctk.CTkToplevel):
    """Ventana chica: escribes, Enter toma el primero, Esc cierra."""

    def __init__(self, parent, markets, on_select, title="Buscar par"):
        super().__init__(parent)
        self.markets = markets or {}
        self.on_select = on_select
        self._results = []

        self.title(title)
        self.geometry("440x430")
        self.overrideredirect(True)
        self.configure(fg_color=t.LINE)
        self.resizable(False, False)
        self.transient(parent)

        wrap = ctk.CTkFrame(self, fg_color=t.CARD, corner_radius=t.R_CARD)
        wrap.pack(fill="both", expand=True, padx=1, pady=1)
        self._wrap = wrap

        head = ctk.CTkFrame(wrap, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(head, text=title, font=(t.UI, 14, "bold"),
                     text_color=t.TEXT, anchor="w").pack(side="left")
        ctk.CTkButton(head, text="✕", width=22, height=22, corner_radius=t.R_CHIP,
                      fg_color="transparent", hover_color=t.BORDER, text_color=t.MUTED,
                      font=(t.UI, 12), command=self.destroy).pack(side="right")

        self.entry = ctk.CTkEntry(wrap, placeholder_text="BTC, sol, eth…",
                                  height=34, fg_color=t.INPUT, border_color=t.BORDER,
                                  text_color=t.TEXT, placeholder_text_color=t.MUTED,
                                  font=(t.NUM, 14))
        self.entry.pack(fill="x", padx=14)
        self.entry.bind("<KeyRelease>", self._on_key)
        self.entry.bind("<Return>", self._choose_first)
        self.entry.bind("<Down>", lambda e: self._move(1))
        self.entry.bind("<Up>", lambda e: self._move(-1))

        self.listbox = tk.Listbox(
            wrap, bg=t.INPUT, fg=t.TEXT, selectbackground=t.SELECT,
            selectforeground=t.TEXT, borderwidth=0, highlightthickness=0,
            font=(t.NUM, 12), activestyle="none", exportselection=False)
        self.listbox.pack(fill="both", expand=True, padx=14, pady=(8, 12))
        self.listbox.bind("<Double-Button-1>", self._choose_click)
        self.listbox.bind("<ButtonRelease-1>", self._choose_click)
        self.listbox.bind("<Return>", self._choose_first)

        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Button-1>", self._click_background)
        self.after(40, self._center)

        self._show(self._filter(""))
        # modal: mientras este abierto no se puede clicar la ventana de atras,
        # asi que nunca queda flotando encima de las tarjetas
        self.grab_set()
        self.after(140, self._focus_entry)

    def _click_background(self, event):
        if event.widget in (self, getattr(self, "_wrap", None)):
            self.destroy()

    def destroy(self):
        parent = self.master
        super().destroy()
        try:
            parent.focus_force()
        except Exception:
            pass

    def _focus_entry(self):
        try:
            self.focus_force()
            self.entry.focus_force()
            self.entry.icursor("end")
        except Exception:
            pass

    def _center(self):
        parent = self.master
        try:
            x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
            y = parent.winfo_rooty() + 90
        except Exception:
            x, y = 200, 120
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _on_key(self, _evt=None):
        self._show(self._filter(self.entry.get()))

    def _filter(self, text):
        return filter_markets(self.markets, text, limit=200)

    def _show(self, results):
        self._results = results
        self.listbox.delete(0, "end")
        if not self.markets:
            self.listbox.insert("end", "  cargando catalogo…")
            return
        if not results:
            self.listbox.insert("end", "  sin resultados")
            return
        for c in results:
            self.listbox.insert("end", contract_line(c))
        self.listbox.selection_set(0)
        self.listbox.activate(0)

    def _move(self, delta):
        if not self._results:
            return "break"
        current = self.listbox.curselection()
        index = max(0, min((current[0] if current else 0) + delta,
                           len(self._results) - 1))
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(index)
        self.listbox.activate(index)
        self.listbox.see(index)
        return "break"

    def _choose_first(self, _evt=None):
        if not self._results:
            return "break"
        self._select(0)
        return "break"

    def _choose_click(self, _evt=None):
        current = self.listbox.curselection()
        if current:
            self._select(current[0])

    def _select(self, index):
        if not (0 <= index < len(self._results)):
            return
        symbol = self._results[index]["symbol"]
        self.destroy()
        self.on_select(symbol)
