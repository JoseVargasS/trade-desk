"""Agregación del historial por día para la pestaña Calendario.

Módulo puro: sin Qt, sin red y sin disco. Toma las filas que ya trae el
mensaje `history` (el archivo local fusionado con el historial del broker) y
las agrupa por día de cierre.

Reglas (documentadas en AGENTS.md):

- solo cuenta la operación con cierre (`cierre` > 0): las abiertas no cuentan;
- el día es la fecha **local** del último cierre (la del sistema: en la máquina
  del usuario es America/Lima, UTC-5);
- el neto es `pnl.neto_operacion(pnl, fee)`: PnL menos comisión, igual que la
  columna Neto del Historial;
- una operación cerrada en partes cuenta **entera** el día de su último cierre;
- el calendario solo conoce lo que la app ya cargó: no pide nada.
"""

import csv
import io
from calendar import monthrange
from datetime import date, datetime, timedelta

from .brokers import TITULOS
from .pnl import neto_operacion

DIAS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
MESES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def fecha_cierre(fila, tz=None):
    """Fecha local del último cierre de la operación; None si sigue abierta.

    `tz=None` usa la hora local del sistema (la misma que usa la columna
    Cierre del Historial). Con `tz` explícito se puede fijar otra zona: el
    cruce de medianoche depende de ella.
    """
    try:
        ms = float(fila.get("cierre") or 0)
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz).date()
    except (OverflowError, OSError, ValueError):
        return None


def cerradas(filas, tz=None):
    """Las operaciones con cierre: [(fecha local, fila)]."""
    salida = []
    for fila in filas or ():
        dia = fecha_cierre(fila, tz)
        if dia is not None:
            salida.append((dia, fila))
    return salida


def filtrar(filas, broker=None, symbol=None):
    """Filtra por broker y por par (los dos filtros son opcionales)."""
    salida = []
    for fila in filas or ():
        if broker and (fila.get("_exchange") or "") != broker:
            continue
        if symbol and (fila.get("symbol") or "") != symbol:
            continue
        salida.append(fila)
    return salida


def en_mes(filas, anio, mes, tz=None):
    """Las operaciones cerradas dentro del mes (el período de la vista)."""
    return [fila for dia, fila in cerradas(filas, tz) if dia.year == anio and dia.month == mes]


def pares(filas):
    """Símbolos presentes en lo cargado, ordenados."""
    return sorted({str(f.get("symbol") or "") for f in filas or () if f.get("symbol")})


def brokers(filas):
    """Brokers presentes en lo cargado, ordenados."""
    return sorted({str(f.get("_exchange") or "") for f in filas or () if f.get("_exchange")})


def por_dia(filas, tz=None):
    """Agrupa las operaciones cerradas por día.

    Devuelve `{fecha: {"fecha", "neto", "pnl", "fee", "n", "filas"}}`.
    """
    dias = {}
    for dia, fila in cerradas(filas, tz):
        pnl = float(fila.get("pnl") or 0)
        fee = float(fila.get("fee") or 0)
        info = dias.setdefault(
            dia,
            {"fecha": dia, "neto": 0.0, "pnl": 0.0, "fee": 0.0, "n": 0, "filas": []},
        )
        info["neto"] += neto_operacion(pnl, fee)
        info["pnl"] += pnl
        info["fee"] += fee
        info["n"] += 1
        info["filas"].append(fila)
    return dias


def dias_del_mes(anio, mes):
    """Las celdas del mes, empezando en lunes: 35 o 42 días."""
    primero = date(anio, mes, 1)
    ultimo = date(anio, mes, monthrange(anio, mes)[1])
    inicio = primero - timedelta(days=primero.weekday())
    fin = ultimo + timedelta(days=6 - ultimo.weekday())
    return [inicio + timedelta(days=i) for i in range((fin - inicio).days + 1)]


def semanas_del_mes(anio, mes):
    """[(etiqueta, fechas)] de las semanas (lunes a domingo) que tocan el mes."""
    fechas = dias_del_mes(anio, mes)
    semanas = []
    for indice in range(0, len(fechas), 7):
        semana = fechas[indice : indice + 7]
        semanas.append((f"S{indice // 7 + 1}", semana))
    return semanas


def resumen(dias, anio, mes):
    """Total del mes visible: {"neto", "pnl", "fee", "n", "dias"}."""
    total = {"neto": 0.0, "pnl": 0.0, "fee": 0.0, "n": 0, "dias": 0}
    for dia, info in dias.items():
        if dia.year != anio or dia.month != mes:
            continue
        total["neto"] += info["neto"]
        total["pnl"] += info["pnl"]
        total["fee"] += info["fee"]
        total["n"] += info["n"]
        total["dias"] += 1
    return total


def semanas(dias, anio, mes):
    """Totales por semana: solo cuentan los días del mes visible."""
    salida = []
    for etiqueta, fechas in semanas_del_mes(anio, mes):
        total = {"etiqueta": etiqueta, "neto": 0.0, "n": 0}
        for dia in fechas:
            info = dias.get(dia)
            if info is None or dia.year != anio or dia.month != mes:
                continue
            total["neto"] += info["neto"]
            total["n"] += info["n"]
        salida.append(total)
    return salida


def curva(filas, anio, mes, tz=None):
    """Curva acumulada del mes: [(fecha, acumulado)].

    Solo los días con operaciones, en orden. Es la línea que pinta el
    sparkline de la tarjeta «Neto del mes».
    """
    dias = por_dia(filas, tz)
    acumulado = 0.0
    salida = []
    for dia in sorted(dias):
        if dia.year != anio or dia.month != mes:
            continue
        acumulado += dias[dia]["neto"]
        salida.append((dia, acumulado))
    return salida


def _racha(orden, dias, signo):
    """Racha más larga de días seguidos con el mismo signo.

    `signo` es 1 para los ganadores y -1 para los perdedores. Un día sin
    operaciones interrumpe la racha (los días van seguidos en el calendario,
    no en la lista).
    """
    mejor = actual = 0
    anterior = None
    for dia in orden:
        if signo * dias[dia]["neto"] > 0:
            actual = actual + 1 if anterior == dia - timedelta(days=1) else 1
        else:
            actual = 0
        mejor = max(mejor, actual)
        anterior = dia
    return mejor


def metricas(filas, tz=None):
    """Las métricas del período (las que muestra el panel de la derecha)."""
    dias = por_dia(filas, tz)
    orden = sorted(dias)
    cerradas_ = cerradas(filas, tz)
    netos = [
        neto_operacion(float(f.get("pnl") or 0), float(f.get("fee") or 0)) for _dia, f in cerradas_
    ]
    ganadoras = sum(1 for neto in netos if neto > 0)
    losses = sum(neto for neto in netos if neto < 0)
    wins = sum(neto for neto in netos if neto > 0)
    acumulado = 0.0
    pico = 0.0
    caida = 0.0
    for dia in orden:
        acumulado += dias[dia]["neto"]
        pico = max(pico, acumulado)
        caida = max(caida, pico - acumulado)
    mejor = peor = None
    if orden:
        mejor = max(orden, key=lambda dia: dias[dia]["neto"])
        peor = min(orden, key=lambda dia: dias[dia]["neto"])
    por_broker = {}
    for _dia, fila in cerradas_:
        broker = str(fila.get("_exchange") or "")
        neto = neto_operacion(float(fila.get("pnl") or 0), float(fila.get("fee") or 0))
        info = por_broker.setdefault(broker, {"neto": 0.0, "fee": 0.0, "n": 0, "ganadoras": 0})
        info["neto"] += neto
        info["fee"] += float(fila.get("fee") or 0)
        info["n"] += 1
        if neto > 0:
            info["ganadoras"] += 1
    return {
        "neto": sum(netos),
        "pnl": sum(float(f.get("pnl") or 0) for _dia, f in cerradas_),
        "fee": sum(float(f.get("fee") or 0) for _dia, f in cerradas_),
        "operaciones": len(netos),
        "ganadoras": ganadoras,
        "win_rate": (ganadoras / len(netos)) if netos else 0.0,
        "mejor_dia": (mejor, dias[mejor]["neto"]) if mejor else None,
        "peor_dia": (peor, dias[peor]["neto"]) if peor else None,
        "profit_factor": (wins / abs(losses)) if losses else (float("inf") if wins else None),
        "racha_ganadora": _racha(orden, dias, 1),
        "racha_perdedora": _racha(orden, dias, -1),
        "drawdown": -caida,
        "por_broker": por_broker,
    }


def _numero(valor):
    """Número para el CSV: sin separador de miles y con punto decimal."""
    return f"{float(valor or 0):.10g}"


def a_csv(filas, tz=None):
    """El período en CSV: una fila por operación y una fila TOTAL.

    Separador `;` y punto decimal (así lo abre Excel en español sin romper
    los números); los importes van sin separador de miles.
    """
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";", lineterminator="\n")
    escritor.writerow(
        [
            "Cierre",
            "Hora",
            "Par",
            "Broker",
            "Lado",
            "Tamano (USDT)",
            "Entrada",
            "Salida",
            "PnL",
            "Fee",
            "Neto",
        ]
    )
    totales = {"pnl": 0.0, "fee": 0.0, "neto": 0.0}
    for dia, fila in sorted(cerradas(filas, tz), key=lambda par: par[0]):
        ms = float(fila.get("cierre") or 0)
        momento = datetime.fromtimestamp(ms / 1000, tz)
        pnl = float(fila.get("pnl") or 0)
        fee = float(fila.get("fee") or 0)
        neto = neto_operacion(pnl, fee)
        cantidad = float(fila.get("qty") or fila.get("cerrada") or 0)
        entrada = float(fila.get("entrada") or 0)
        totales["pnl"] += pnl
        totales["fee"] += fee
        totales["neto"] += neto
        escritor.writerow(
            [
                dia.isoformat(),
                momento.strftime("%H:%M"),
                fila.get("symbol") or "",
                TITULOS.get(str(fila.get("_exchange") or ""), fila.get("_exchange") or ""),
                fila.get("lado") or "",
                _numero(cantidad * entrada),
                _numero(entrada),
                _numero(fila.get("salida") or 0),
                _numero(pnl),
                _numero(fee),
                _numero(neto),
            ]
        )
    escritor.writerow(
        [
            "TOTAL",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            _numero(totales["pnl"]),
            _numero(totales["fee"]),
            _numero(totales["neto"]),
        ]
    )
    return buffer.getvalue()


__all__ = [
    "DIAS",
    "MESES",
    "a_csv",
    "brokers",
    "cerradas",
    "curva",
    "dias_del_mes",
    "en_mes",
    "fecha_cierre",
    "filtrar",
    "metricas",
    "pares",
    "por_dia",
    "resumen",
    "semanas",
    "semanas_del_mes",
]
