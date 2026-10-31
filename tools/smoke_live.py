"""Arranca la ventana real N segundos y reporta lo que pinto.

Sirve para comprobar que el reorg (rutas, fuentes, icono) no rompio nada sin
tocar la cuenta: no envia ordenes y cierra sola.

    python tools/smoke_live.py 9
"""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import customtkinter as ctk  # noqa: E402

from tradedesk import creds  # noqa: E402
from tradedesk.app import App  # noqa: E402
from tradedesk.paths import ASSETS, DATA_DIR  # noqa: E402


def main(seconds=9.0):
    key, secret = creds.load("mexc")
    print("datos:", DATA_DIR)
    print("assets:", ASSETS, "| fuentes:", (ASSETS / "fonts").is_dir())
    print("credenciales:", "si" if key and secret else "no")

    errors = []
    root = ctk.CTk()
    root.report_callback_exception = lambda *exc: (
        errors.append("".join(traceback.format_exception(*exc))),
        print("EXCEPCION:", exc[1]),
    )
    app = App(root)
    root.after(int(seconds * 1000), root.destroy)
    root.mainloop()

    print("filas pintadas:", len(app.table.rows))
    for pid, row in app.table.rows.items():
        bar = row["bar"]
        print(
            "  ",
            pid,
            "|",
            row["labels"]["pos"].cget("text"),
            "|",
            row["labels"]["mar_val"].cget("text"),
            "|",
            bar.close_btn.cget("text"),
            bar.close_btn.cget("fg_color"),
        )
    print("errores:", len(errors))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(float(sys.argv[1]) if len(sys.argv) > 1 else 9.0))
