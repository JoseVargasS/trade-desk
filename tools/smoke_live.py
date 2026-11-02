"""Arranca la vista Qt real N segundos y reporta lo que pinto.

Sirve para comprobar que un cambio de UI no rompio nada sin tocar la cuenta: no
envia ordenes y cierra sola.

    python tools/smoke_live.py 9
"""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from tradedesk import creds, theme  # noqa: E402
from tradedesk.paths import ASSETS, DATA_DIR  # noqa: E402
from tradedesk.qt.view import VistaQt  # noqa: E402


def main(seconds=9.0):
    key, secret = creds.load("mexc")
    print("datos:", DATA_DIR)
    print("assets:", ASSETS, "| fuentes:", (ASSETS / "fonts").is_dir())
    print("credenciales:", "si" if key and secret else "no")

    errors = []

    def guardar(exc_type, exc, tb):
        errors.append("".join(traceback.format_exception(exc_type, exc, tb)))
        print("EXCEPCION:", exc)

    sys.excepthook = guardar

    theme.load_fonts()
    app = QApplication(sys.argv)
    ventana = VistaQt()
    ventana.show()
    pintado = {}

    def terminar():
        try:
            pintado["pos"] = [
                (
                    p.get("positionId"),
                    p.get("_name") or p.get("symbol"),
                    p.get("holdVol"),
                    p.get("unRealizedPnl"),
                )
                for p in ventana._posiciones
            ]
            pintado["ord"] = [
                (
                    o.get("orderId"),
                    o.get("_name") or o.get("symbol"),
                    o.get("price"),
                    o.get("vol"),
                )
                for o in ventana._ordenes
            ]
        except Exception:
            traceback.print_exc()
        ventana.close()
        app.quit()

    QTimer.singleShot(int(seconds * 1000), terminar)
    app.exec()

    filas = pintado.get("pos", [])
    print("filas pintadas:", len(filas))
    for pid, par, vol, pnl in filas:
        print("  ", pid, "|", par, "|", vol, "|", pnl)

    ordenes = pintado.get("ord", [])
    print("ordenes pintadas:", len(ordenes))
    for oid, par, precio, vol in ordenes:
        print("  ", oid, "|", par, "|", precio, "|", vol)

    print("errores:", len(errors))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(float(sys.argv[1]) if len(sys.argv) > 1 else 9.0))
