"""Regla de oro: ningun hilo de trabajo toca widgets (ni Tk ni Qt).

Un `configure`/`set_*` desde un worker deja la ventana sorda varios segundos.
Este test lee el codigo fuente y falla si aparece una llamada asi.
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "tradedesk"

WIDGET_CALL = re.compile(
    r"\b(card|self\.(?:lbl_|btn_|table|tree|port))\w*"
    r"\.(configure|set_\w+|insert|delete|config)\("
)


def _workers(path):
    """(linea, funcion) para cada linea dentro de una funcion *_worker."""
    current = None
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        found = re.search(r"def (_\w*worker)\(", line)
        if found:
            current = found.group(1)
        elif current and re.match(r"\s+def ", line):
            current = None
        if current:
            yield number, current, line


def _archivos():
    yield SRC / "controller.py"
    yield from sorted((SRC / "qt").glob("*.py"))


def test_los_workers_no_tocan_widgets():
    for path in _archivos():
        for number, worker, line in _workers(path):
            assert not WIDGET_CALL.search(line), (
                f"{path.name}:{number} {worker} toca widgets desde un hilo: {line.strip()}"
            )
