"""trade-desk: ventana local para operar futuros de MEXC a mercado.

Tarjetas de par en fila + tabla de posiciones e historial.
Sin servidor web, sin puertos abiertos.
"""

import json
import os
import queue
import threading
import time
import tkinter as tk
from datetime import datetime

import customtkinter as ctk
import httpx

from . import creds, dialog
from . import theme as t
from .actions import ActionsMixin
from .cards import TradeCard
from .mexc import Mexc, decorate_positions, display_name
from .paths import ASSETS, DATA_DIR
from .search import SearchPopup
from .table import HistoryTable, PositionsTable

EXCHANGE = "mexc"
CONFIG_PATH = str(DATA_DIR / "config.json")


class App(ActionsMixin):
    def __init__(self, root):
        self.root = root
        ctk.set_appearance_mode("dark")

        self.q = queue.Queue()
        self.cfg = self._load_config()
        self.cards = []
        self._prices = {}
        self._changes = {}
        self._markets = {}
        self._auth = False
        self._polling = False
        self._calc_jobs = {}
        self._last_refresh = ""
        self._avisos = []
        self._aviso_abierto = False

        key, secret = creds.load(EXCHANGE)
        self.mx = Mexc(key, secret)
        self._auth = bool(key and secret)

        t.resolve_fonts(root)
        self._build_ui()
        self._restore_cards()

        self.root.after(120, self._drain)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        threading.Thread(target=self._fetch_ip, daemon=True).start()
        threading.Thread(target=self._load_markets, daemon=True).start()
        threading.Thread(target=self._poll, daemon=True).start()
        if not self._auth:
            self.root.after(250, self._ask_key)
        else:
            threading.Thread(target=self._refresh_positions, daemon=True).start()

    # ------------------------------------------------------------------ config
    def _load_config(self):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_config(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({"cards": [c.config() for c in self.cards]}, f, indent=2)
        except Exception:
            pass

    def _restore_cards(self):
        for item in (self.cfg.get("cards") or [])[:8]:
            self._add_card(item.get("symbol", "BTC_USDT"), item)
        if not self.cards:
            self._status("Añade un par con «+ Añadir par»")

    # ---------------------------------------------------------------------- ui
    def _build_ui(self):
        self.root.title("Trade Desk")
        # 12 columnas en la tabla de posiciones + acciones: la fila mide 1700 px,
        # asi que por debajo de 1760 se recorta en silencio (no hay scroll horizontal).
        self.root.geometry("1800x1000")
        self.root.minsize(1760, 860)
        self.root.configure(fg_color=t.BG)
        try:
            self.root.iconbitmap(str(ASSETS / "icon.ico"))
        except Exception:
            pass
        try:
            self._icon = tk.PhotoImage(file=str(ASSETS / "icon.png"))
            self.root.iconphoto(True, self._icon)
        except Exception:
            pass

        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 8))

        ctk.CTkLabel(header, text="Trade Desk", font=(t.UI, 18, "bold"), text_color=t.TEXT).pack(
            side="left"
        )
        ctk.CTkLabel(
            header,
            text=" MEXC ",
            font=(t.UI, 12, "bold"),
            fg_color=t.INPUT,
            corner_radius=t.R_CHIP,
            text_color=t.GREEN,
        ).pack(side="left", padx=(10, 14))

        self.dot = ctk.CTkLabel(header, text="●", font=(t.UI, 15), text_color=t.MUTED)
        self.dot.pack(side="left")

        ctk.CTkButton(
            header,
            text="+  Añadir par",
            width=132,
            height=32,
            corner_radius=t.R_CTRL,
            fg_color=t.ACCENT_SOFT,
            hover_color="#2E4E75",
            text_color=t.TEXT,
            font=(t.UI, 13, "bold"),
            command=self._add_from_search,
        ).pack(side="right")

        self.lbl_ip = ctk.CTkLabel(header, text="IP …", font=(t.NUM, 12), text_color=t.MUTED)
        self.lbl_ip.pack(side="right", padx=(0, 10))
        ctk.CTkButton(
            header,
            text="IP",
            width=30,
            height=24,
            corner_radius=t.R_CHIP,
            fg_color=t.INPUT,
            hover_color=t.BORDER,
            text_color=t.MUTED,
            font=(t.UI, 11),
            command=self._copy_ip,
        ).pack(side="right", padx=(0, 6))

        self.deck = ctk.CTkScrollableFrame(
            self.root,
            fg_color="transparent",
            orientation="horizontal",
            height=450,
            scrollbar_button_color=t.INPUT,
            scrollbar_button_hover_color=t.BORDER,
        )
        self.deck.pack(fill="x", padx=16, pady=(0, 8))

        status = ctk.CTkFrame(self.root, fg_color="transparent")
        status.pack(side="bottom", fill="x", padx=16, pady=(4, 12))
        self.var_dry = tk.BooleanVar(value=True)
        ctk.CTkSwitch(
            status,
            text="DRY-RUN",
            variable=self.var_dry,
            onvalue=True,
            offvalue=False,
            font=(t.UI, 12),
            text_color=t.MUTED,
            progress_color=t.GOLD,
            button_color=t.GOLD,
            button_hover_color=t.GOLD,
            width=104,
            command=self._sync_dry,
        ).pack(side="left")
        self.lbl_dry = ctk.CTkLabel(status, text="", font=(t.UI, 12, "bold"), text_color=t.GOLD)
        self.lbl_dry.pack(side="left", padx=12)
        self.lbl_status = ctk.CTkLabel(status, text="Listo.", font=(t.UI, 12), text_color=t.MUTED)
        self.lbl_status.pack(side="left", padx=8)
        self.lbl_refresh = ctk.CTkLabel(status, text="", font=(t.NUM, 11), text_color=t.MUTED)
        self.lbl_refresh.pack(side="right")
        self._sync_dry()
        self.root.after(30, self._dark_titlebar)

        self.tabs = ctk.CTkTabview(
            self.root,
            fg_color=t.BG,
            segmented_button_fg_color=t.INPUT,
            segmented_button_selected_color=t.ACCENT_SOFT,
            segmented_button_selected_hover_color=t.ACCENT_SOFT,
            segmented_button_unselected_color=t.INPUT,
            segmented_button_unselected_hover_color=t.BORDER,
            text_color=t.TEXT,
            corner_radius=t.R_CARD,
            border_width=0,
        )
        self.tabs.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        tab_pos = self.tabs.add("Posiciones")
        tab_his = self.tabs.add("Historial")
        self.tabs.configure(command=self._on_tab)

        self.lbl_count = ctk.CTkLabel(tab_pos, text="0", font=(t.UI, 13), text_color=t.MUTED)
        self.lbl_count.pack(anchor="w", padx=4)

        bar = ctk.CTkFrame(tab_pos, fg_color="transparent")
        bar.pack(side="bottom", fill="x", pady=(4, 2))
        self.btn_sel = ctk.CTkButton(
            bar,
            text="Cerrar seleccionadas",
            width=180,
            height=30,
            corner_radius=t.R_CTRL,
            fg_color=t.INPUT,
            hover_color=t.BORDER,
            text_color=t.TEXT,
            font=(t.UI, 13),
            command=self._close_selected,
        )
        self.btn_sel.pack(side="left")
        ctk.CTkButton(
            bar,
            text="CERRAR TODO",
            width=130,
            height=30,
            corner_radius=t.R_CTRL,
            fg_color="#3A1A1E",
            hover_color="#4A2226",
            text_color=t.RED,
            font=(t.UI, 13, "bold"),
            command=self._close_all,
        ).pack(side="right")

        self.table = PositionsTable(
            tab_pos,
            on_close=self._close_position,
            on_selection=self._sync_selection,
            on_tpsl=self._edit_tpsl,
            on_margin=self._add_margin,
            on_reverse=self._reverse_position,
        )
        self.table.pack(fill="both", expand=True, pady=(2, 6))

        self.history = HistoryTable(tab_his)
        self.history.pack(fill="both", expand=True, pady=2)

    def _dark_titlebar(self):
        if os.name != "nt":
            return
        import ctypes

        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            value = ctypes.c_int(1)
            for attr in (20, 19):
                if (
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)
                    )
                    == 0
                ):
                    break
        except Exception:
            pass

    # ------------------------------------------------------------------ tarjetas
    def _contract_for(self, symbol):
        """Contrato del par: catalogo o cache. Sin red."""
        return self._markets.get(symbol) or self.mx.cached_contract(symbol) or {}

    def _name_for(self, symbol):
        """Nombre del par como en MEXC. Sin red: catalogo o cache de contratos."""
        contract = self._contract_for(symbol)
        return display_name(contract) if contract else symbol

    def _scale_for(self, symbol):
        """Decimales del precio que admite el contrato (priceScale)."""
        return int(self._contract_for(symbol).get("priceScale") or 2)

    def _add_card(self, symbol, cfg=None):
        cfg = cfg or {}
        card = TradeCard(
            self.deck,
            symbol,
            cfg,
            on_remove=self._remove_card,
            on_symbol=self._pick_symbol,
            on_trade=self._trade,
            on_change=self._schedule_calc,
        )
        card.set_name(self._name_for(symbol))
        card.set_scale(self._scale_for(symbol))
        card.pack(side="left", padx=(0, 10), pady=2, anchor="n")
        self.cards.append(card)
        self._schedule_calc(card)
        self._save_config()
        return card

    def _remove_card(self, card):
        self.cards.remove(card)
        card.destroy()
        if not self.cards:
            self._status("Añade un par con «+ Añadir par»")
        self._save_config()

    def _add_from_search(self):
        self._open_search(self._on_new_symbol)

    def _open_search(self, on_select):
        """Abre el buscador. Nunca pide el catalogo desde el hilo de la UI:
        markets() tarda ~0.5 s y hasta 8 s si el request se cuelga."""
        if self._markets:
            SearchPopup(self.root, self._markets, on_select)
            return
        self._status("Cargando catálogo…")

        def load():
            try:
                self.q.put(("markets", self.mx.markets()))
                self.q.put(("open_search", on_select))
            except Exception as e:
                self.q.put(("status", f"catalogo: {e}"))

        threading.Thread(target=load, daemon=True).start()

    def _load_markets(self):
        try:
            self.q.put(("markets", self.mx.markets()))
            self.q.put(("conn", True))
        except Exception as e:
            self.q.put(("status", f"catalogo: {e}"))

    def _on_new_symbol(self, symbol):
        if any(c.symbol == symbol for c in self.cards):
            self._status(f"{symbol} ya esta en pantalla.")
            return
        self._add_card(symbol)
        self._status(f"{symbol} agregado.")

    def _pick_symbol(self, card):
        self._open_search(lambda s: self._set_card_symbol(card, s))

    def _set_card_symbol(self, card, symbol):
        card.set_symbol(symbol)
        card.set_name(self._name_for(symbol))
        card.set_scale(self._scale_for(symbol))
        self._save_config()

    # -------------------------------------------------------------------- datos
    def _fetch_ip(self):
        try:
            ip = httpx.get("https://api.ipify.org", timeout=5).text.strip()
        except Exception:
            ip = "desconocida"
        self.q.put(("ip", ip))

    def _poll(self):
        if self._polling:
            return
        self._polling = True
        # ticker: 10 req/2s en MEXC. Vamos a ~1.4 req/s para dejar aire:
        # el navegador del usuario tambien consume el mismo cupo por IP.
        delay = 0.70
        last_pos = 0.0
        last_hist = 0.0
        index = 0

        while True:
            now = time.time()
            cards = list(self.cards)
            symbols = list(dict.fromkeys(c.symbol for c in cards if c.symbol))

            if symbols:
                symbol = symbols[index % len(symbols)]
                index += 1
                if symbol:
                    try:
                        data = self.mx.ticker(symbol)
                        self.q.put(
                            (
                                "ticker",
                                (
                                    symbol,
                                    float(data["lastPrice"]),
                                    float(data.get("riseFallRate") or 0) * 100,
                                ),
                            )
                        )
                        delay = max(0.70, delay * 0.90)
                        self._fails = 0
                    except Exception as e:
                        self._fails = getattr(self, "_fails", 0) + 1
                        if self._fails >= 3:
                            self.q.put(("conn", False))
                        self.q.put(("status", f"precio {symbol}: {e}"))
                        delay = min(5.0, delay * 2.5)

            if self._auth and now - last_pos >= 3.0:
                last_pos = now
                try:
                    positions = self._decorate(self.mx.positions())
                    self.q.put(("positions", positions))
                    self.q.put(("orders", self.mx.open_orders()))
                except Exception as e:
                    self.q.put(("status", f"posiciones: {e}"))

            if self._auth and now - last_hist >= 15 and self._history_visible():
                last_hist = now
                try:
                    self.q.put(("history", self.mx.history(50)))
                except Exception as e:
                    self.q.put(("status", f"historial: {e}"))

            time.sleep(delay)

    def _history_visible(self):
        try:
            return self.tabs.get() == "Historial"
        except Exception:
            return False

    def _on_tab(self):
        if self._history_visible() and self._auth:
            threading.Thread(target=self._load_history, daemon=True).start()

    def _load_history(self):
        try:
            self.q.put(("history", self.mx.history(50)))
        except Exception as e:
            self.q.put(("status", f"historial: {e}"))

    def _decorate(self, positions):
        """contrato, nombre de MEXC y TP/SL vigente (ver mexc.decorate_positions)."""
        return decorate_positions(self.mx, positions)

    def _refresh_positions(self):
        try:
            self.q.put(("positions", self._decorate(self.mx.positions())))
        except Exception as e:
            self.q.put(("status", f"posiciones: {e}"))

    # ---------------------------------------------------------------- preview
    def _schedule_calc(self, card):
        job = self._calc_jobs.get(id(card))
        if job:
            self.root.after_cancel(job)
        self._calc_jobs[id(card)] = self.root.after(220, lambda: self._calc(card))

    def _calc(self, card):
        self._calc_jobs.pop(id(card), None)
        form = card.form()
        if not form:
            card.set_preview(
                "escribe el tamaño en USDT"
                if not card.var_size.get().strip()
                else "revisa apalancamiento y tamaño"
            )
            return
        threading.Thread(target=self._calc_worker, args=(card, form), daemon=True).start()

    def _calc_worker(self, card, form):
        try:
            symbol = form["symbol"]
            # con orden limite el tamaño se convierte al precio limite, no al de mercado
            px = form.get("price") or self._prices.get(symbol)
            if not px:
                # nunca tocar widgets desde un hilo: Tk se bloquea varios segundos
                self.q.put(("preview", (card, "esperando precio…")))
                return
            vol = self.mx.size_to_vol(symbol, form["notional"], px)
            real = self.mx.vol_to_usdt(symbol, vol, px)
            fee = self.mx.est_fee(symbol, real)
            liq = "—"
            if form["margin_mode"] == "Aislado":
                liq = (
                    f"{t.fmt_price(self.mx.est_liq(symbol, px, form['lev'], 'LONG'))} / "
                    f"{t.fmt_price(self.mx.est_liq(symbol, px, form['lev'], 'SHORT'))}"
                )
            text = (
                f"{t.fmt_qty(vol)} contratos · {t.fmt_usdt(real)} USDT\n"
                f"fee {t.fmt_fee(fee)} · liq {liq}"
            )
            self.q.put(("preview", (card, text)))
        except Exception as e:
            self.q.put(("preview", (card, str(e)[:70])))

    # ------------------------------------------------------------------- drain
    def _drain(self):
        started = time.perf_counter()
        hechos = []
        try:
            while True:
                kind, payload = self.q.get_nowait()
                hechos.append(kind)
                if kind == "ticker":
                    symbol, price, change = payload
                    self._prices[symbol] = price
                    self._changes[symbol] = change
                    for card in self.cards:
                        if card.symbol == symbol:
                            card.set_price(price, change)
                            if card.lbl_calc.cget("text") in ("", "—", "esperando precio…"):
                                self._schedule_calc(card)
                    self.dot.configure(text_color=t.GREEN)
                elif kind == "conn":
                    self.dot.configure(text_color=t.GREEN if payload else t.RED)
                elif kind == "positions":
                    self._render_positions(payload)
                elif kind == "orders":
                    self._count_orders = len(payload)
                elif kind == "history":
                    self.history.render(payload)
                elif kind == "ip":
                    self.lbl_ip.configure(text=f"IP {payload}")
                elif kind == "markets":
                    self._markets = payload
                    for card in self.cards:
                        card.set_name(self._name_for(card.symbol))
                        card.set_scale(self._scale_for(card.symbol))
                elif kind == "open_search":
                    SearchPopup(self.root, self._markets, payload)
                elif kind == "preview":
                    card, text = payload
                    card.set_preview(text)
                elif kind == "status":
                    self._status(payload)
                elif kind == "order":
                    self._on_order_done(*payload)
                elif kind == "closed":
                    self._status(payload)
                elif kind == "notice":
                    self._notice(*payload)
        except queue.Empty:
            pass
        spent = time.perf_counter() - started
        if spent > 0.2:
            # que mensajes lo causaron: sin esto el log dice cuanto, no por que
            como = ", ".join(dict.fromkeys(hechos)) or "vacio"
            self._perf(f"drain {spent * 1000:.0f} ms · {como}")
        self.root.after(120, self._drain)

    def _notice(self, title, text, danger=False):
        """Avisos uno por vez y fuera de `_drain`: un modal abierto no encola la UI."""
        self._avisos.append((title, text, danger))
        if not self._aviso_abierto:
            self._next_notice()

    def _next_notice(self):
        if not self._avisos:
            self._aviso_abierto = False
            return
        self._aviso_abierto = True
        title, text, danger = self._avisos.pop(0)
        dialog.show(self.root, title, text, danger=danger)
        self.root.after_idle(self._next_notice)

    def _perf(self, msg):
        """Registra callbacks lentos de la UI: si algo bloquea, queda la prueba."""
        try:
            with open(str(DATA_DIR / "perf.log"), "a", encoding="utf-8") as f:
                f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")
        except Exception:
            pass

    def _render_positions(self, positions):
        self.table.render(positions)
        count = len(positions)
        extra = (
            f" · {getattr(self, '_count_orders', 0)} ordenes pendientes"
            if getattr(self, "_count_orders", 0)
            else ""
        )
        self.lbl_count.configure(text=f"{count} abiertas{extra}")
        total = sum(float(p.get("unRealizedPnl") or 0) for p in positions)
        self.lbl_refresh.configure(
            text=f"total {t.fmt_pnl(total)} · act. {datetime.now():%H:%M:%S}",
            text_color=t.GREEN if total >= 0 else t.RED,
        )
        self._sync_selection()

    def _sync_selection(self):
        count = self.table.checked_count()
        self.btn_sel.configure(
            text=f"Cerrar seleccionadas ({count})" if count > 1 else "Cerrar seleccionadas"
        )

    # ------------------------------------------------------------------ ordenes
    def _trade(self, card, side):
        if not self._auth:
            self._ask_key()
            return
        form = card.form()
        if not form:
            dialog.show(
                self.root,
                "Datos invalidos",
                "Revisa el apalancamiento y el tamaño: deben ser numeros "
                "positivos, y TP/SL vacios o numericos.",
            )
            return
        price = form.get("price")
        px = price or self._prices.get(form["symbol"], 0)
        exact = t.fmt_price_exact(px, self._scale_for(form["symbol"]))
        dry = bool(self.var_dry.get())
        rows = [
            ("Par", form["symbol"]),
            ("Tipo", f"Límite {exact}" if price else "Mercado"),
            ("Precio", exact if price else t.fmt_price(px)),
            ("Tamaño", f"{form['size']:,.2f} USDT ({form['size_mode']})"),
            ("Nocional", f"{form['notional']:,.2f} USDT"),
            ("Apalancamiento", f"{form['lev']}x ({form['margin_mode']})"),
            ("TP / SL", f"{form['tp'] or '—'} / {form['sl'] or '—'}"),
        ]
        warn = "DRY-RUN: no se enviara nada." if dry else "ESTO ES REAL"
        if price:
            warn += "\nOrden límite: puede quedar sin llenar."
        if not dialog.confirm(
            self.root,
            f"Confirmar {side}",
            rows=rows,
            warn=warn,
            danger=not dry,
            ok_text=side,
        ):
            return
        card.set_busy(True)
        threading.Thread(target=self._do_trade, args=(card, side, form, dry), daemon=True).start()

    def _do_trade(self, card, side, form, dry):
        try:
            precio = form.get("price")
            if dry:
                px = precio or self.mx.price(form["symbol"])
                vol = self.mx.size_to_vol(form["symbol"], form["notional"], px)
                self.q.put(
                    (
                        "order",
                        (
                            True,
                            f"DRY-RUN {side} {t.fmt_qty(vol)} contratos "
                            f"@ {t.fmt_price(px)} (no enviado)",
                            card,
                        ),
                    )
                )
                return
            data, vol, px = self.mx.open_market(
                form["symbol"],
                side,
                form["notional"],
                form["lev"],
                form["open_type"],
                form["tp"],
                form["sl"],
                precio,
            )
            order_id = (data or {}).get("orderId", "?")
            self.q.put(
                (
                    "order",
                    (
                        True,
                        f"{side} enviado: {t.fmt_qty(vol)} contratos "
                        f"@ {t.fmt_price(px)} · id {order_id}",
                        card,
                    ),
                )
            )
        except Exception as e:
            self.q.put(("order", (False, str(e), card)))

    def _on_order_done(self, ok, msg, card):
        card.set_busy(False)
        self._status(msg)
        self._log(("OK  " if ok else "ERR ") + msg)
        if not ok:
            self._notice("Orden rechazada", msg, danger=True)
        elif msg.startswith("DRY-RUN"):
            self._notice(
                "DRY-RUN: no se envio nada",
                msg + "\n\nApaga DRY-RUN para operar de verdad.",
            )
        else:
            self._notice("Orden enviada", msg)
            threading.Thread(target=self._refresh_positions, daemon=True).start()

    # --------------------------------------------------------------------- key
    def _ask_key(self):
        got = dialog.ask_key(self.root, lambda k, s: Mexc(k, s).positions())
        if not got:
            return
        creds.save(EXCHANGE, *got)
        self.mx = Mexc(*got)
        self._auth = True
        threading.Thread(target=self._refresh_positions, daemon=True).start()
        self._status("Key guardada. Listo para operar.")

    # ------------------------------------------------------------------ varios
    def _sync_dry(self):
        if self.var_dry.get():
            self.lbl_dry.configure(
                text="DRY-RUN ACTIVO · no abre ni cierra posiciones", text_color=t.GOLD
            )
        else:
            self.lbl_dry.configure(text="REAL · las ordenes se envian", text_color=t.RED)

    def _status(self, msg):
        self.lbl_status.configure(text=msg)

    def _log(self, msg):
        try:
            with open(str(DATA_DIR / "trades.log"), "a", encoding="utf-8") as f:
                f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")
        except Exception:
            pass

    def _copy_ip(self):
        ip = self.lbl_ip.cget("text").replace("IP", "").strip()
        self.root.clipboard_clear()
        self.root.clipboard_append(ip)
        self._status(f"IP {ip} copiada.")

    def _on_close(self):
        self._save_config()
        self.root.destroy()
