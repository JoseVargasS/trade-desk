"""Mide el repintado de la ventana Qt de prueba (F1 de la migracion a PySide6).

    python tools/qt_probe.py

Abre la ventana con 8 tarjetas y 200 filas, la minimiza y la restaura 5 veces
midiendo lo que tarda en quedar pintada. No habla con MEXC ni toca la cuenta.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from tradedesk import theme  # noqa: E402
from tradedesk.qt.shell import build_window  # noqa: E402


def medir(app, ventana, veces=5):
    tiempos = []
    for _ in range(veces):
        ventana.showMinimized()
        app.processEvents()
        time.sleep(0.35)
        app.processEvents()
        ventana.showNormal()
        arranque = time.perf_counter()
        app.processEvents()
        tiempos.append((time.perf_counter() - arranque) * 1000)
        app.processEvents()
        time.sleep(0.25)
    tiempos.sort()
    return [round(x) for x in tiempos]


def main():
    theme.load_fonts()
    app = QApplication(sys.argv)
    ventana = build_window()
    ventana.show()
    app.processEvents()
    time.sleep(1.0)
    app.processEvents()

    widgets = len(ventana.findChildren(QWidget))
    print(f"widgets: {widgets}")
    tiempos = medir(app, ventana)
    print(f"repintado al restaurar: {tiempos} ms  (mediana {tiempos[len(tiempos) // 2]} ms)")
    ventana.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
