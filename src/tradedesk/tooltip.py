"""Número con subrayado punteado y detalle al pasar el puntero (estilo MEXC).

En la tabla no cabe el desglose completo de la fee, así que el importe se pinta
en un `Canvas` chico con una línea punteada debajo —la señal de "esto se puede
mirar"— y al entrar el puntero aparece un panel con el detalle.

El panel es un `Toplevel` sin foco ni `grab`: aparece y desaparece sin robarle el
teclado a nadie (ver §6 de AGENTS sobre paneles que se llevan el foco).
"""

import tkinter as tk

from . import theme as t


class Tooltip:
    """Panel flotante con filas `nombre · valor`, sin foco ni grab."""

    def __init__(self, widget):
        self.widget = widget
        self._ventana = None

    def show(self, titulo, filas):
        self.hide()
        try:
            self._ventana = tk.Toplevel(self.widget)
        except tk.TclError:
            return
        self._ventana.overrideredirect(True)
        try:
            self._ventana.attributes("-topmost", True)
        except tk.TclError:
            pass
        caja = tk.Frame(
            self._ventana, bg=t.CARD, highlightthickness=1, highlightbackground=t.BORDER
        )
        caja.pack(fill="both", expand=True)
        tk.Label(
            caja,
            text=titulo,
            bg=t.CARD,
            fg=t.MUTED,
            font=t.ui_font(11, bold=True),
            anchor="w",
        ).pack(fill="x", padx=10, pady=(8, 2))
        for nombre, valor, color in filas:
            linea = tk.Frame(caja, bg=t.CARD)
            linea.pack(fill="x", padx=10, pady=(0, 1))
            tk.Label(
                linea, text=nombre, bg=t.CARD, fg=t.MUTED, font=t.ui_font(11), anchor="w"
            ).pack(side="left")
            tk.Label(
                linea,
                text=valor,
                bg=t.CARD,
                fg=color,
                font=t.num_font(11, bold=True),
                anchor="e",
            ).pack(side="left", padx=(14, 0))
        tk.Frame(caja, bg=t.CARD, height=6).pack(fill="x")
        self._ubicar()

    def _ubicar(self):
        """Debajo del número y sin tapar el puntero (si no, entra y sale en bucle)."""
        ventana = self._ventana
        ventana.update_idletasks()
        ancho = ventana.winfo_reqwidth()
        alto = ventana.winfo_reqheight()
        x = self.widget.winfo_rootx() + self.widget.winfo_width() - ancho
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        x = max(0, min(x, self.widget.winfo_screenwidth() - ancho))
        y = max(0, min(y, self.widget.winfo_screenheight() - alto))
        ventana.geometry(f"+{x}+{y}")

    def hide(self):
        if self._ventana is not None:
            try:
                self._ventana.destroy()
            except tk.TclError:
                pass
            self._ventana = None


class NumeroConDetalle(tk.Canvas):
    """Importe con subrayado punteado: al pasar el puntero muestra el desglose."""

    def __init__(self, master, bg, titulo="", alto=None):
        super().__init__(
            master,
            bg=bg,
            height=alto or t.px(24),
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self._titulo = titulo
        self._filas = []
        self._tooltip = Tooltip(self)
        self._texto = self.create_text(
            0, self.winfo_reqheight() // 2, text="", anchor="e", font=t.num_font(13, bold=True)
        )
        self._puntos = self.create_line(0, 0, 0, 0, dash=(1, 2), fill=t.MUTED)
        self.bind("<Configure>", lambda _e: self._reubicar())
        self.bind("<Enter>", self._entrar)
        self.bind("<Leave>", lambda _e: self._tooltip.hide())
        self.bind("<Destroy>", lambda _e: self._tooltip.hide())

    def set(self, texto, color, filas):
        self.itemconfigure(self._texto, text=texto, fill=color)
        self._filas = filas
        self._reubicar()

    def detalle(self):
        """Filas `(nombre, valor, color)` que muestra el panel."""
        return list(self._filas)

    def _reubicar(self):
        alto = self.winfo_height()
        self.coords(self._texto, max(0, self.winfo_width() - 2), alto // 2)
        caja = self.bbox(self._texto)
        if not caja:
            return
        self.coords(self._puntos, caja[0] + 1, caja[3] + 1, caja[2], caja[3] + 1)

    def _entrar(self, _evento):
        if self._filas:
            self._tooltip.show(self._titulo, self._filas)
