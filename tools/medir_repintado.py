"""Cuánto tarda la ventana en quedar pintada al restaurarla desde minimizada.

    python tools/medir_repintado.py

Abre la app real (solo lectura: no envía órdenes), minimiza y restaura varias
veces y mide los milisegundos que tarda `deiconify + update()` en dejar la
ventana completa. Ese es el tiempo que el usuario ve como "parpadeo".

También cuenta los widgets: los `CTkCanvas` son los caros (cada widget de
CustomTkinter se dibuja en su propio Canvas y Windows lo repinta por separado).
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import customtkinter as ctk  # noqa: E402

from tradedesk.app import App  # noqa: E402


def esperar(segundos):
    fin = time.time() + segundos
    while time.time() < fin:
        yield
        time.sleep(0.01)


def bombear(segundos):
    for _ in esperar(segundos):
        root.update()


def inventario(widget, acumulado):
    acumulado["widgets"] = acumulado.get("widgets", 0) + 1
    nombre = type(widget).__name__
    acumulado[nombre] = acumulado.get(nombre, 0) + 1
    for hijo in widget.winfo_children():
        inventario(hijo, acumulado)
    return acumulado


def medir(veces=3):
    tiempos = []
    for _ in range(veces):
        root.iconify()
        bombear(0.7)
        root.deiconify()
        arranque = time.perf_counter()
        root.update()
        tiempos.append((time.perf_counter() - arranque) * 1000)
        bombear(0.3)
    tiempos.sort()
    return tiempos


def main():
    global root
    root = ctk.CTk()
    app = App(root)
    bombear(6.0)  # catalogo, precios y posiciones

    cuenta = inventario(root, {})
    caros = cuenta.get("CTkCanvas", 0)
    print(
        f"widgets: {cuenta['widgets']}  (CTkCanvas {caros}, CTkLabel {cuenta.get('CTkLabel', 0)}, "
        f"CTkFrame {cuenta.get('CTkFrame', 0)}, tk.Label {cuenta.get('Label', 0)}, "
        f"tk.Frame {cuenta.get('Frame', 0)})"
    )
    print(
        f"contenido: {len(app.table.rows)} posiciones · "
        f"{len(app.orders.rows)} ordenes · {len(app.cards)} tarjetas"
    )

    tiempos = medir()
    mediana = tiempos[len(tiempos) // 2]
    print(
        f"repintado al restaurar: {[round(x) for x in tiempos]} ms  (mediana {round(mediana)} ms)"
    )

    # de dónde viene el costo
    app.tabs.pack_forget()
    bombear(0.4)
    sin_tabs = medir(2)
    app.tabs.pack(fill="both", expand=True, padx=16, pady=(0, 8))
    app.deck.pack_forget()
    bombear(0.4)
    sin_deck = medir(2)
    app.deck.pack(fill="x", padx=16, pady=(0, 8))
    print(f"  sin pestañas (tablas): {[round(x) for x in sin_tabs]} ms")
    print(f"  sin tarjetas:          {[round(x) for x in sin_deck]} ms")

    root.destroy()


if __name__ == "__main__":
    main()
