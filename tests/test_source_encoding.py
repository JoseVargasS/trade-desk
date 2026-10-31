"""El codigo esta en UTF-8 limpio: sin BOM y sin mojibake.

Un `Get-Content | Set-Content` de PowerShell en Windows convierte "✕" en "âœ•" y
"Tamaño" en "TamaÃ±o" sin que nada falle: se ve raro en la app y nadie sabe por que.
La firma del mojibake es que la linea se puede codificar en cp1252 y leer como UTF-8.
"""

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CARPETAS = ("src", "tests", "tools")


def _archivos():
    for carpeta in CARPETAS:
        for path in (RAIZ / carpeta).rglob("*.py"):
            if "__pycache__" not in path.parts:
                yield path


def test_sin_bom():
    con_bom = [
        str(p.relative_to(RAIZ)) for p in _archivos() if p.read_bytes().startswith(b"\xef\xbb\xbf")
    ]
    assert not con_bom, f"archivos con BOM: {con_bom}"


def test_sin_mojibake():
    rotos = []
    for path in _archivos():
        for numero, linea in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if not any(ord(c) > 127 for c in linea):
                continue
            try:
                arreglada = linea.encode("cp1252").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            if arreglada != linea:
                rotos.append(f"{path.relative_to(RAIZ)}:{numero}")
    assert not rotos, f"lineas con mojibake (UTF-8 leido como cp1252): {rotos}"
