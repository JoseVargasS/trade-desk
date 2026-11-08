"""Diagnostica duplicados y netos mensuales en operaciones.json, sin escribir archivos."""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tradedesk import calendario  # noqa: E402
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


def _marca(fila):
    return (
        str(fila.get("_exchange") or ""),
        str(fila.get("symbol") or ""),
        str(fila.get("lado") or ""),
    )


def _cierre_ms(fila):
    try:
        cierre = float(fila.get("cierre") or 0)
    except (TypeError, ValueError):
        return None
    return cierre if cierre > 0 else None


def _posibles_duplicados(filas):
    fifo_por_marca = defaultdict(list)
    for fila in filas:
        if str(fila.get("_clave") or "").startswith("fifo|"):
            fifo_por_marca[_marca(fila)].append(fila)

    pares = []
    cierres_duplicados = set()
    for cierre in filas:
        if not str(cierre.get("_clave") or "").startswith("cierre|"):
            continue
        cierre_ms = _cierre_ms(cierre)
        if cierre_ms is None:
            continue
        for fifo in fifo_por_marca[_marca(cierre)]:
            fifo_ms = _cierre_ms(fifo)
            if fifo_ms is not None and abs(cierre_ms - fifo_ms) < 1000:
                pares.append((cierre, fifo))
                cierres_duplicados.add(id(cierre))
    return pares, cierres_duplicados


def _netos_mensuales(filas):
    dias = calendario.por_dia(filas)
    periodos = sorted({(dia.year, dia.month) for dia in dias})
    return {periodo: calendario.resumen(dias, *periodo)["neto"] for periodo in periodos}


def _mostrar_fila(etiqueta, fila):
    neto = neto_operacion(fila.get("pnl"), fila.get("fee"))
    print(f"  {etiqueta}: neto={neto:.4f} | {json.dumps(fila, ensure_ascii=False, sort_keys=True)}")


def auditar(filas):
    """Imprime el inventario, posibles duplicados y netos mensuales."""
    print("Filas por broker:")
    conteo = Counter(str(fila.get("_exchange") or "(sin broker)") for fila in filas)
    for broker, cantidad in sorted(conteo.items()):
        print(f"  {broker}: {cantidad}")
    if not conteo:
        print("  (sin filas)")

    cierres = [fila for fila in filas if str(fila.get("_clave") or "").startswith("cierre|")]
    pares, cierres_duplicados = _posibles_duplicados(filas)
    fifos_por_cierre = defaultdict(list)
    for cierre, fifo in pares:
        fifos_por_cierre[id(cierre)].append(fifo)

    print(f'\nFilas con _clave "cierre|": {len(cierres)}')
    if not cierres:
        print("  (ninguna)")
    for fila in cierres:
        fifos = fifos_por_cierre[id(fila)]
        if not fifos:
            _mostrar_fila("sin FIFO cercano", fila)
        else:
            for fifo in fifos:
                print("  POSIBLE DUPLICADO")
                _mostrar_fila("cierre|", fila)
                _mostrar_fila("fifo|", fifo)
    print(f"\nPares POSIBLE DUPLICADO: {len(pares)}")
    if not pares:
        print("  (ninguno)")

    filas_sin_duplicados = [fila for fila in filas if id(fila) not in cierres_duplicados]
    netos = _netos_mensuales(filas)
    netos_sin_duplicados = _netos_mensuales(filas_sin_duplicados)
    periodos = sorted(set(netos) | set(netos_sin_duplicados))
    print("\nNeto mensual (hora local del equipo; neto = PnL - fee):")
    if not periodos:
        print("  (sin operaciones cerradas)")
    for anio, mes in periodos:
        print(
            f"  {anio:04d}-{mes:02d}: con posibles duplicados "
            f"{netos.get((anio, mes), 0.0):.4f}; sin posibles duplicados "
            f"{netos_sin_duplicados.get((anio, mes), 0.0):.4f}"
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
