"""Ventana: cabecera, tarjetas, barra de estado y pestañas.

Se construye aparte de App porque app.py está en el tope de líneas: aquí solo
hay widgets, ningún estado de negocio ni request. `build_ui(app)` deja todo
colgado de `app` con los mismos nombres de siempre.
"""

import ctypes
import os
import tkinter as tk

import customtkinter as ctk

from . import theme as t
from .orders import OpenOrdersTable
from .paths import ASSETS
from .table import HistoryTable, PositionsTable


def dark_titlebar(root):
    """Pinta la barra de titulo de Windows del color de la app."""
    if os.name != "nt":
        return
    try:
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
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


def build_ui(app):
    root = app.root
    root.title("Trade Desk")
    # 12 columnas en la tabla de posiciones + acciones: la fila mide 1700 px,
    # asi que por debajo de 1760 se recorta en silencio (no hay scroll horizontal).
    root.geometry("1800x1000")
    root.minsize(1760, 860)
    root.configure(fg_color=t.BG)
    try:
        root.iconbitmap(str(ASSETS / "icon.ico"))
    except Exception:
        pass
    try:
        app._icon = tk.PhotoImage(file=str(ASSETS / "icon.png"))
        root.iconphoto(True, app._icon)
    except Exception:
        pass

    header = ctk.CTkFrame(root, fg_color="transparent")
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

    app.dot = ctk.CTkLabel(header, text="●", font=(t.UI, 15), text_color=t.MUTED)
    app.dot.pack(side="left")

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
        command=app._add_from_search,
    ).pack(side="right")

    app.lbl_ip = ctk.CTkLabel(header, text="IP …", font=(t.NUM, 12), text_color=t.MUTED)
    app.lbl_ip.pack(side="right", padx=(0, 10))
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
        command=app._copy_ip,
    ).pack(side="right", padx=(0, 6))

    app.deck = ctk.CTkScrollableFrame(
        root,
        fg_color="transparent",
        orientation="horizontal",
        height=450,
        scrollbar_button_color=t.INPUT,
        scrollbar_button_hover_color=t.BORDER,
    )
    app.deck.pack(fill="x", padx=16, pady=(0, 8))

    status = ctk.CTkFrame(root, fg_color="transparent")
    status.pack(side="bottom", fill="x", padx=16, pady=(4, 12))
    app.var_dry = tk.BooleanVar(value=True)
    ctk.CTkSwitch(
        status,
        text="DRY-RUN",
        variable=app.var_dry,
        onvalue=True,
        offvalue=False,
        font=(t.UI, 12),
        text_color=t.MUTED,
        progress_color=t.GOLD,
        button_color=t.GOLD,
        button_hover_color=t.GOLD,
        width=104,
        command=app._sync_dry,
    ).pack(side="left")
    app.lbl_dry = ctk.CTkLabel(status, text="", font=(t.UI, 12, "bold"), text_color=t.GOLD)
    app.lbl_dry.pack(side="left", padx=12)
    app.lbl_status = ctk.CTkLabel(status, text="Listo.", font=(t.UI, 12), text_color=t.MUTED)
    app.lbl_status.pack(side="left", padx=8)
    app.lbl_refresh = ctk.CTkLabel(status, text="", font=(t.NUM, 11), text_color=t.MUTED)
    app.lbl_refresh.pack(side="right")
    app._sync_dry()
    root.after(30, lambda: dark_titlebar(root))

    app.tabs = ctk.CTkTabview(
        root,
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
    app.tabs.pack(fill="both", expand=True, padx=16, pady=(0, 8))

    tab_pos = app.tabs.add("Posiciones")
    tab_ord = app.tabs.add("Órdenes")
    tab_his = app.tabs.add("Historial")
    app.tabs.configure(command=app._on_tab)

    app.lbl_count = ctk.CTkLabel(tab_pos, text="0", font=(t.UI, 13), text_color=t.MUTED)
    app.lbl_count.pack(anchor="w", padx=4)
    # el aviso de pendientes lleva a la pestaña donde se gestionan
    app.lbl_count.bind("<Button-1>", lambda e: app._go_orders())

    bar = ctk.CTkFrame(tab_pos, fg_color="transparent")
    bar.pack(side="bottom", fill="x", pady=(4, 2))
    app.btn_sel = ctk.CTkButton(
        bar,
        text="Cerrar seleccionadas",
        width=180,
        height=30,
        corner_radius=t.R_CTRL,
        fg_color=t.INPUT,
        hover_color=t.BORDER,
        text_color=t.TEXT,
        font=(t.UI, 13),
        command=app._close_selected,
    )
    app.btn_sel.pack(side="left")
    ctk.CTkButton(
        bar,
        text="CERRAR TODO",
        width=130,
        height=30,
        corner_radius=t.R_CTRL,
        fg_color=t.DANGER_SOFT,
        hover_color=t.DANGER_SOFT_HOVER,
        text_color=t.RED,
        font=(t.UI, 13, "bold"),
        command=app._close_all,
    ).pack(side="right")

    app.table = PositionsTable(
        tab_pos,
        on_close=app._close_position,
        on_selection=app._sync_selection,
        on_tpsl=app._edit_tpsl,
        on_margin=app._add_margin,
        on_reverse=app._reverse_position,
    )
    app.table.pack(fill="both", expand=True, pady=(2, 6))

    app.orders = OpenOrdersTable(
        tab_ord,
        on_modify=app._modify_order,
        on_cancel=app._cancel_order,
        on_cancel_all=app._cancel_all_orders,
    )
    app.orders.pack(fill="both", expand=True, pady=(2, 6))

    app.history = HistoryTable(tab_his)
    app.history.pack(fill="both", expand=True, pady=2)
