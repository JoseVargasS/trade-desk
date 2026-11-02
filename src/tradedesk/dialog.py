"""Dialogos propios: confirmacion, aviso y error. Mismo tema que la app."""

import customtkinter as ctk

from . import theme as t


class Modal(ctk.CTkToplevel):
    """Ventana modal que al cerrarse le devuelve el teclado a la ventana padre.

    Un dialogo se lleva el teclado con `focus_force`; si al morir no lo devuelve,
    Tk queda **sin ventana con foco** y `focus_set` sobre la ventana grande queda
    diferido: ningun input de atras acepta teclas (se ve como "el campo esta
    deshabilitado"). Es el mismo caso que `closebar._Popup`.
    """

    def destroy(self):
        padre = self.master
        super().destroy()
        try:
            padre.focus_force()
        except Exception:
            pass


class _Dialog(Modal):
    def __init__(
        self,
        parent,
        title,
        rows=None,
        message=None,
        warn=None,
        ok_text="Confirmar",
        cancel_text="Cancelar",
        danger=False,
    ):
        super().__init__(parent)
        self.result = False
        self.overrideredirect(True)
        self.configure(fg_color=t.LINE)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        wrap = ctk.CTkFrame(self, fg_color=t.CARD, corner_radius=t.R_CARD)
        wrap.pack(fill="both", expand=True, padx=1, pady=1)

        top = ctk.CTkFrame(wrap, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(14, 0))
        ctk.CTkLabel(top, text=title, font=(t.UI, 16, "bold"), text_color=t.TEXT, anchor="w").pack(
            side="left"
        )
        ctk.CTkButton(
            top,
            text="✕",
            width=22,
            height=22,
            corner_radius=t.R_CHIP,
            fg_color="transparent",
            hover_color=t.BORDER,
            text_color=t.MUTED,
            font=(t.UI, 12),
            command=self._cancel,
        ).pack(side="right")

        if message:
            ctk.CTkLabel(
                wrap,
                text=message,
                font=(t.UI, 13),
                text_color=t.MUTED,
                justify="left",
                anchor="w",
                wraplength=380,
            ).pack(anchor="w", padx=18, pady=(10, 12))

        if rows:
            grid = ctk.CTkFrame(wrap, fg_color="transparent")
            grid.pack(fill="x", padx=18, pady=(12, 6))
            grid.grid_columnconfigure(1, weight=1)
            for i, (label, value) in enumerate(rows):
                ctk.CTkLabel(
                    grid, text=label, font=(t.UI, 12), text_color=t.MUTED, anchor="w"
                ).grid(row=i, column=0, sticky="w", pady=2)
                ctk.CTkLabel(
                    grid, text=str(value), font=(t.NUM, 13), text_color=t.TEXT, anchor="e"
                ).grid(row=i, column=1, sticky="e", pady=2)

        if warn:
            ctk.CTkLabel(
                wrap,
                text=warn,
                font=(t.UI, 13, "bold"),
                text_color=t.RED if danger else t.GOLD,
                anchor="w",
            ).pack(anchor="w", padx=18, pady=(8, 0))

        buttons = ctk.CTkFrame(wrap, fg_color="transparent")
        buttons.pack(fill="x", padx=18, pady=(14, 16))
        ctk.CTkButton(
            buttons,
            text=ok_text,
            width=130,
            height=34,
            corner_radius=t.R_CTRL,
            fg_color=t.RED if danger else t.GREEN,
            hover_color="#E03A50" if danger else "#18B374",
            text_color="#150508" if danger else "#04140D",
            font=(t.UI, 13, "bold"),
            command=self._ok,
        ).pack(side="right")
        ctk.CTkButton(
            buttons,
            text=cancel_text,
            width=110,
            height=34,
            corner_radius=t.R_CTRL,
            fg_color=t.INPUT,
            hover_color=t.BORDER,
            text_color=t.TEXT,
            font=(t.UI, 13),
            command=self._cancel,
        ).pack(side="right", padx=(0, 8))

        self.bind("<Escape>", lambda e: self._cancel())
        self.bind("<Return>", lambda e: self._ok())
        self.update_idletasks()
        self._center(parent)
        self.after(50, self.focus_force)

    def _center(self, parent):
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
        except Exception:
            px = py = 0
            pw, ph = 1200, 800
        w, h = self.winfo_width(), self.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _ok(self):
        self.result = True
        self.destroy()

    def _cancel(self):
        self.result = False
        self.destroy()


def confirm(
    parent, title, rows=None, warn=None, ok_text="Confirmar", cancel_text="Cancelar", danger=False
):
    d = _Dialog(
        parent, title, rows=rows, warn=warn, ok_text=ok_text, cancel_text=cancel_text, danger=danger
    )
    parent.wait_window(d)
    return d.result


def show(parent, title, message, warn=None, danger=False):
    d = _Dialog(
        parent,
        title,
        message=message,
        warn=warn,
        ok_text="Aceptar",
        cancel_text="Cerrar",
        danger=danger,
    )
    parent.wait_window(d)


class _KeyDialog(Modal):
    def __init__(self, parent, verify):
        super().__init__(parent)
        self.result = None
        self.verify = verify
        self.overrideredirect(True)
        self.configure(fg_color=t.LINE)
        self.transient(parent)
        self.grab_set()

        wrap = ctk.CTkFrame(self, fg_color=t.CARD, corner_radius=t.R_CARD)
        wrap.pack(fill="both", expand=True, padx=1, pady=1)

        head = ctk.CTkFrame(wrap, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(16, 0))
        ctk.CTkLabel(head, text="Conectar MEXC", font=(t.UI, 16, "bold"), text_color=t.TEXT).pack(
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

        self.e_key = ctk.CTkEntry(
            wrap,
            placeholder_text="API key",
            width=400,
            height=34,
            fg_color=t.INPUT,
            border_color=t.BORDER,
            text_color=t.TEXT,
            font=(t.NUM, 13),
        )
        self.e_key.pack(padx=20, pady=(14, 0))
        self.e_secret = ctk.CTkEntry(
            wrap,
            placeholder_text="Secret",
            width=400,
            height=34,
            show="*",
            fg_color=t.INPUT,
            border_color=t.BORDER,
            text_color=t.TEXT,
            font=(t.NUM, 13),
        )
        self.e_secret.pack(padx=20, pady=(8, 0))

        ctk.CTkLabel(
            wrap,
            text="Se guardan en el Administrador de credenciales de Windows.",
            font=(t.UI, 12),
            text_color=t.MUTED,
            anchor="w",
        ).pack(anchor="w", padx=20, pady=(10, 0))
        self.lbl = ctk.CTkLabel(
            wrap,
            text="",
            font=(t.UI, 12),
            text_color=t.GOLD,
            wraplength=400,
            anchor="w",
            justify="left",
        )
        self.lbl.pack(anchor="w", padx=20, pady=(4, 0))

        ctk.CTkButton(
            wrap,
            text="Guardar y verificar",
            width=400,
            height=36,
            corner_radius=t.R_CTRL,
            fg_color=t.GREEN,
            hover_color="#18B374",
            text_color="#04140D",
            font=(t.UI, 14, "bold"),
            command=self._save,
        ).pack(padx=20, pady=(16, 18))

        self.bind("<Escape>", lambda e: self.destroy())
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.after(60, self.e_key.focus_force)

    def _save(self):
        key, secret = self.e_key.get().strip(), self.e_secret.get().strip()
        if not key or not secret:
            self.lbl.configure(text="Faltan datos.", text_color=t.RED)
            return
        self.lbl.configure(text="Verificando…", text_color=t.MUTED)
        self.update_idletasks()
        try:
            self.verify(key, secret)
        except Exception as e:
            self.lbl.configure(text=f"No funciono: {e}", text_color=t.RED)
            return
        self.result = (key, secret)
        self.destroy()


def ask_key(parent, verify):
    """Devuelve (key, secret) ya verificados, o None."""
    d = _KeyDialog(parent, verify)
    parent.wait_window(d)
    return d.result


class _FormDialog(Modal):
    """Formulario chico: N campos etiquetados, devuelve dict o None."""

    def __init__(
        self, parent, title, fields, ok_text="Guardar", note=None, extras=(), resumen=None
    ):
        super().__init__(parent)
        self.result = None
        self.fields = fields
        self._resumen = resumen
        self.overrideredirect(True)
        self.configure(fg_color=t.LINE)
        self.transient(parent)
        self.grab_set()

        wrap = ctk.CTkFrame(self, fg_color=t.CARD, corner_radius=t.R_CARD)
        wrap.pack(fill="both", expand=True, padx=1, pady=1)

        head = ctk.CTkFrame(wrap, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(14, 0))
        ctk.CTkLabel(head, text=title, font=(t.UI, 14, "bold"), text_color=t.TEXT).pack(side="left")
        ctk.CTkButton(
            head,
            text="✕",
            width=22,
            height=22,
            corner_radius=t.R_CHIP,
            fg_color="transparent",
            hover_color=t.BORDER,
            text_color=t.MUTED,
            font=(t.UI, 10),
            command=self.destroy,
        ).pack(side="right")

        if note:
            ctk.CTkLabel(wrap, text=note, font=(t.UI, 10), text_color=t.MUTED, anchor="w").pack(
                anchor="w", padx=18, pady=(8, 0)
            )

        self.entries = {}
        grid = ctk.CTkFrame(wrap, fg_color="transparent")
        grid.pack(fill="x", padx=18, pady=(12, 0))
        grid.grid_columnconfigure(1, weight=1)
        for i, (key, label, default) in enumerate(fields):
            ctk.CTkLabel(grid, text=label, font=(t.UI, 11), text_color=t.MUTED, anchor="w").grid(
                row=i, column=0, sticky="w", pady=4
            )
            var = ctk.StringVar(value=str(default or ""))
            entry = ctk.CTkEntry(
                grid,
                textvariable=var,
                width=170,
                height=32,
                fg_color=t.INPUT,
                border_color=t.BORDER,
                text_color=t.TEXT,
                font=(t.NUM, 13),
                justify="right",
            )
            entry.grid(row=i, column=1, sticky="ew", padx=(10, 0), pady=4)
            self.entries[key] = var

        self.lbl_resumen = None
        if resumen:
            self.lbl_resumen = ctk.CTkLabel(
                wrap,
                text=resumen(self.entries),
                font=(t.UI, 10),
                text_color=t.MUTED,
                anchor="w",
                justify="left",
            )
            self.lbl_resumen.pack(anchor="w", padx=18, pady=(10, 0))
            for var in self.entries.values():
                var.trace_add("write", self._actualizar_resumen)

        buttons = ctk.CTkFrame(wrap, fg_color="transparent")
        buttons.pack(fill="x", padx=18, pady=(14, 16))
        for texto, comando, activo in extras:
            extra = ctk.CTkButton(
                buttons,
                text=texto,
                width=110,
                height=34,
                corner_radius=t.R_CTRL,
                fg_color=t.INPUT,
                hover_color=t.BORDER,
                text_color=t.TEXT,
                font=(t.UI, 11),
                command=lambda c=comando: c(self.entries),
            )
            extra.pack(side="left", padx=(0, 8))
            if not activo:
                extra.configure(state="disabled")
        ctk.CTkButton(
            buttons,
            text=ok_text,
            width=130,
            height=34,
            corner_radius=t.R_CTRL,
            fg_color=t.GREEN,
            hover_color="#18B374",
            text_color="#04140D",
            font=(t.UI, 11, "bold"),
            command=self._ok,
        ).pack(side="right")
        ctk.CTkButton(
            buttons,
            text="Cancelar",
            width=110,
            height=34,
            corner_radius=t.R_CTRL,
            fg_color=t.INPUT,
            hover_color=t.BORDER,
            text_color=t.TEXT,
            font=(t.UI, 11),
            command=self.destroy,
        ).pack(side="right", padx=(0, 8))

        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Return>", lambda e: self._ok())
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.after(80, self.focus_force)

    def _actualizar_resumen(self, *_):
        if self.lbl_resumen is not None:
            self.lbl_resumen.configure(text=self._resumen(self.entries))

    def _ok(self):
        self.result = {k: v.get().strip() for k, v in self.entries.items()}
        self.destroy()


def form(parent, title, fields, ok_text="Guardar", note=None, extras=(), resumen=None):
    d = _FormDialog(parent, title, fields, ok_text, note, extras, resumen)
    parent.wait_window(d)
    return d.result
