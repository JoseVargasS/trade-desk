"""Arranque de la app: `python -m tradedesk`."""

import ctypes
import os

import customtkinter as ctk

from .app import App


def main():
    if os.name == "nt":
        try:
            # debe ir antes de crear la ventana o la barra de tareas usa el icono de Python
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("tradedesk.mexc.v1")
        except Exception:
            pass
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
