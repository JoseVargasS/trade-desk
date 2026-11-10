"""Diagnostica duplicados y netos mensuales en operaciones.json.

Solo lee: no escribe ni corrige nada. Las reglas de duplicado son las mismas que
aplica `archivo.fusionar`, así que "la app borraría" es exactamente lo que
desaparece al refrescar el Historial.

    uv run --locked python tools/auditar_archivo.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tradedesk import calendario  # noqa: E402
from tradedesk.archivo import Archivo  # noqa: E402
from tradedesk.paths import DATA_DIR  # noqa: E402
from tradedesk.pnl import neto_operacion  # noqa: E402


def _leer_filas(ruta):
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"No se pudo leer {ruta}: {exc}") from exc
    if not isinstance(datos, list) or any(not isinstance(fila, dict) for fila in datos):
        raise ValueError(f"Formato inválido en {ruta}: se esperaba una lista de filas JSON.")
    return datos


def _por_tipo(filas, prefijo):
    return [fila for fila in filas if str(fila.get("_clave") or "").startswith(prefijo)]


def _duplicados(filas):
    """(borrables, ambiguos, huérfanos) con la regla real de `fusionar`.

    `borrables` son los `cierre|` que la app elimina: un único `fifo|` coincide y
    ese FIFO no sirve a ningún otro cierre. El resto se conserva a propósito.
    """
    cierres = _por_tipo(filas, "cierre|")
    fifos = _por_tipo(filas, "fifo|")
    matches = {
        id(cierre): [fifo for fifo in fifos if Archivo._es_cierre_huerfano_duplicado(cierre, fifo)]
        for cierre in cierres
    }
    usos = Counter(id(fifo) for candidatos in matches.values() for fifo in candidatos)
    borrables, ambiguos, huerfanos = [], [], []
    for cierre in cierres:
        candidatos = matches[id(cierre)]
        if not candidatos:
            huerfanos.append(cierre)
        elif len(candidatos) == 1 and usos[id(candidatos[0])] == 1:
            borrables.append((cierre, candidatos[0]))
        else:
            ambiguos.append((cierre, candidatos))
    return borrables, ambiguos, huerfanos


def _netos_mensuales(filas):
    dias = calendario.por_dia(filas)
    periodos = sorted({(dia.year, dia.month) for dia in dias})
    return {periodo: calendario.resumen(dias, *periodo)["neto"] for periodo in periodos}


def _mostrar_fila(etiqueta, fila):
    neto = neto_operacion(fila.get("pnl"), fila.get("fee"))
    detalle = json.dumps(fila, ensure_ascii=False, sort_keys=True)
    print(f"    {etiqueta}: neto={neto:.4f} | {detalle}")


def auditar(filas):
    """Imprime el inventario, el diagnóstico de duplicados y los netos mensuales."""
    print("Filas por broker:")
    conteo = Counter(str(fila.get("_exchange") or "(sin broker)") for fila in filas)
    for broker, cantidad in sorted(conteo.items()):
        print(f"  {broker}: {cantidad}")
    if not conteo:
        print("  (sin filas)")

    borrables, ambiguos, huerfanos = _duplicados(filas)
    total_cierres = len(borrables) + len(ambiguos) + len(huerfanos)
    print(f'\nFilas con _clave "cierre|": {total_cierres}')
    if total_cierres == 0:
        print("  (ninguna)")
    if borrables:
        print(f"  La app borraría {len(borrables)} (huérfano con FIFO único):")
        for cierre, fifo in borrables:
            _mostrar_fila("cierre|", cierre)
            _mostrar_fila("fifo|", fifo)
    for cierre, candidatos in ambiguos:
        print(f"  Ambiguo: {len(candidatos)} FIFO coinciden; se conserva:")
        _mostrar_fila("cierre|", cierre)
        for fifo in candidatos:
            _mostrar_fila("fifo|", fifo)
    for cierre in huerfanos:
        print("  Sin FIFO coincidente; se conserva:")
        _mostrar_fila("cierre|", cierre)
    print(f"\nPares que la app borraría: {len(borrables)}")
    if ambiguos or huerfanos:
        print(
            "  Hay cierres que no cuadran con un FIFO único: refresca el historial "
            "de ese broker y la app los recalcula."
        )

    borrar = {id(cierre) for cierre, _fifo in borrables}
    filas_sin = [fila for fila in filas if id(fila) not in borrar]
    netos = _netos_mensuales(filas)
    netos_sin = _netos_mensuales(filas_sin)
    periodos = sorted(set(netos) | set(netos_sin))
    print("\nNeto mensual (hora local del equipo; neto = PnL - fee):")
    if not periodos:
        print("  (sin operaciones cerradas)")
    for anio, mes in periodos:
        print(
            f"  {anio:04d}-{mes:02d}: con posibles duplicados "
            f"{netos.get((anio, mes), 0.0):.4f}; sin los que la app borraría "
            f"{netos_sin.get((anio, mes), 0.0):.4f}"
        )


def main():
    ruta = DATA_DIR / "operaciones.json"
    try:
        filas = _leer_filas(ruta)
        if filas is None:
            print("sin archivo")
            return 0
        auditar(filas)
    except (TypeError, ValueError, OverflowError, OSError) as exc:
        print(f"Error al auditar {ruta}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
