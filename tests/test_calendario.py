"""Tests del módulo puro del calendario: agregación por día y métricas.

Sin Qt y sin red: el calendario solo agrupa las filas que ya trajo el
historial. Las reglas que se prueban aquí están en AGENTS.md.
"""

from datetime import UTC, date, datetime, timedelta, timezone

from tradedesk import calendario

LIMA = timezone(timedelta(hours=-5))


def _ms(dia, mes=11, anio=2026, hora=12, minuto=0, tz=None):
    """Momento en ms epoch. Sin `tz` es hora local (la misma de la app)."""
    momento = datetime(anio, mes, dia, hora, minuto)
    if tz is not None:
        momento = momento.replace(tzinfo=tz)
    return int(momento.timestamp() * 1000)


def _fila(
    dia,
    mes=11,
    anio=2026,
    pnl=10.0,
    fee=1.0,
    symbol="BTC_USDT",
    exchange="mexc",
    lado="LONG",
    estado="Cerrada",
    cierre=None,
    **extra,
):
    fila = {
        "symbol": symbol,
        "_exchange": exchange,
        "lado": lado,
        "qty": 1.0,
        "entrada": 100.0,
        "salida": 110.0,
        "pnl": pnl,
        "fee": fee,
        "apertura": _ms(dia, mes, anio, hora=10),
        "cierre": _ms(dia, mes, anio) if cierre is None else cierre,
        "estado": estado,
        "_clave": f"{exchange}|{symbol}|{dia}|{mes}|{anio}",
    }
    fila.update(extra)
    return fila


# ------------------------------------------------------------------- vacío
def test_archivo_vacio_no_rompe_nada():
    assert calendario.por_dia([]) == {}
    assert calendario.cerradas([]) == []
    assert calendario.filtrar([]) == []
    assert calendario.pares([]) == []
    assert calendario.brokers([]) == []

    metricas = calendario.metricas([])
    assert metricas["neto"] == 0
    assert metricas["operaciones"] == 0
    assert metricas["win_rate"] == 0
    assert metricas["mejor_dia"] is None
    assert metricas["peor_dia"] is None
    assert metricas["profit_factor"] is None
    assert metricas["drawdown"] == 0
    assert metricas["racha_ganadora"] == 0
    assert metricas["racha_perdedora"] == 0
    assert calendario.resumen({}, 2026, 11)["neto"] == 0
    assert calendario.semanas({}, 2026, 11)[0]["neto"] == 0


def test_csv_sin_operaciones_solo_tiene_encabezado_y_total():
    texto = calendario.a_csv([])
    lineas = texto.strip().split("\n")
    assert lineas[0].startswith("Cierre;Hora;Par")
    assert lineas[-1].startswith("TOTAL")


# --------------------------------------------------------- días con y sin
def test_los_dias_sin_operaciones_no_aparecen():
    filas = [_fila(3), _fila(5)]
    dias = calendario.por_dia(filas)
    assert sorted(dias) == [date(2026, 11, 3), date(2026, 11, 5)]
    assert date(2026, 11, 4) not in dias
    assert dias[date(2026, 11, 3)]["n"] == 1


def test_cambio_de_mes_no_mezcla_los_meses():
    filas = [_fila(30, mes=10), _fila(3, mes=11)]
    assert calendario.resumen(calendario.por_dia(filas), 2026, 10)["n"] == 1
    assert calendario.resumen(calendario.por_dia(filas), 2026, 11)["n"] == 1
    assert calendario.resumen(calendario.por_dia(filas), 2026, 12)["n"] == 0
    assert calendario.resumen(calendario.por_dia(filas), 2026, 10)["neto"] == 9.0


def test_el_mes_visible_solo_cuenta_sus_dias():
    dias = calendario.por_dia([_fila(30, mes=10), _fila(3, mes=11)])
    total = calendario.resumen(dias, 2026, 11)
    assert total["neto"] == 9.0
    assert total["dias"] == 1


# ------------------------------------------------------------------ neto y signo
def test_el_neto_es_el_pnl_menos_la_comision():
    dias = calendario.por_dia([_fila(3, pnl=10.0, fee=1.5)])
    assert dias[date(2026, 11, 3)]["neto"] == 8.5


def test_un_rebate_suma_al_neto():
    dias = calendario.por_dia([_fila(3, pnl=10.0, fee=-0.5)])
    assert dias[date(2026, 11, 3)]["neto"] == 10.5


def test_las_perdidas_son_negativas():
    dias = calendario.por_dia([_fila(3, pnl=-10.0, fee=1.0)])
    assert dias[date(2026, 11, 3)]["neto"] == -11.0


# ------------------------------------------------------------- zona horaria
def test_el_dia_es_la_fecha_local_del_cierre():
    # 23:30 en Lima (UTC-5) es 04:30 del día siguiente en UTC
    cierre = _ms(6, hora=23, minuto=30, tz=LIMA)
    assert calendario.fecha_cierre({"cierre": cierre}, tz=LIMA) == date(2026, 11, 6)
    assert calendario.fecha_cierre({"cierre": cierre}, tz=UTC) == date(2026, 11, 7)


def test_sin_zona_explícita_se_usa_la_hora_local():
    cierre = _ms(6, hora=23, minuto=30)
    esperado = datetime.fromtimestamp(cierre / 1000).date()
    assert calendario.fecha_cierre({"cierre": cierre}) == esperado


# ------------------------------------------------------------------- parcial
def test_una_parcial_cuenta_en_el_dia_de_su_ultimo_cierre():
    filas = [_fila(3, estado="Parcial", cierre=_ms(5))]
    dias = calendario.por_dia(filas)
    assert list(dias) == [date(2026, 11, 5)]
    assert dias[date(2026, 11, 5)]["n"] == 1
    assert dias[date(2026, 11, 5)]["neto"] == 9.0


def test_las_operaciones_abiertas_no_cuentan():
    filas = [_fila(3, cierre=0, estado="Abierta")]
    assert calendario.por_dia(filas) == {}
    assert calendario.cerradas(filas) == []
    assert calendario.metricas(filas)["operaciones"] == 0


# ------------------------------------------------------------------ métricas
def test_metricas_del_periodo():
    filas = [
        _fila(1, pnl=10.0, fee=1.0),
        _fila(2, pnl=-4.0, fee=1.0),
        _fila(3, pnl=-3.0, fee=1.0),
        _fila(4, pnl=2.0, fee=1.0),
    ]
    metricas = calendario.metricas(filas)
    assert metricas["neto"] == 1.0
    assert metricas["operaciones"] == 4
    assert metricas["ganadoras"] == 2
    assert metricas["win_rate"] == 0.5
    assert metricas["mejor_dia"] == (date(2026, 11, 1), 9.0)
    assert metricas["peor_dia"] == (date(2026, 11, 2), -5.0)
    assert metricas["profit_factor"] == 10 / 9
    assert metricas["racha_ganadora"] == 1
    assert metricas["racha_perdedora"] == 2
    # acumulado 9, 4, 0, 1: la mayor caída es de 9 a 0
    assert metricas["drawdown"] == -9.0
    assert metricas["fee"] == 4.0


def test_un_dia_sin_operaciones_interrumpe_la_racha():
    filas = [_fila(1, pnl=10.0, fee=0.0), _fila(3, pnl=10.0, fee=0.0)]
    metricas = calendario.metricas(filas)
    assert metricas["racha_ganadora"] == 1


def test_profit_factor_infinito_sin_perdidas():
    metricas = calendario.metricas([_fila(1, pnl=10.0, fee=0.0)])
    assert metricas["profit_factor"] == float("inf")


def test_desglose_por_broker():
    filas = [
        _fila(1, exchange="mexc", pnl=10.0, fee=1.0),
        _fila(2, exchange="bitunix", pnl=-4.0, fee=1.0),
        _fila(3, exchange="mexc", pnl=5.0, fee=1.0),
    ]
    por_broker = calendario.metricas(filas)["por_broker"]
    assert por_broker["mexc"]["neto"] == 13.0
    assert por_broker["mexc"]["n"] == 2
    assert por_broker["mexc"]["ganadoras"] == 2
    assert por_broker["bitunix"]["neto"] == -5.0
    assert por_broker["bitunix"]["ganadoras"] == 0


# -------------------------------------------------------------------- filtros
def test_filtro_por_broker_y_por_par():
    filas = [
        _fila(1, exchange="mexc", symbol="BTC_USDT"),
        _fila(2, exchange="bingx", symbol="ETH_USDT"),
        _fila(3, exchange="mexc", symbol="ETH_USDT"),
    ]
    assert len(calendario.filtrar(filas, broker="mexc")) == 2
    assert len(calendario.filtrar(filas, symbol="ETH_USDT")) == 2
    assert len(calendario.filtrar(filas, broker="mexc", symbol="ETH_USDT")) == 1
    assert len(calendario.filtrar(filas)) == 3
    assert calendario.pares(filas) == ["BTC_USDT", "ETH_USDT"]
    assert calendario.brokers(filas) == ["bingx", "mexc"]


# --------------------------------------------------------------------- mes
def test_las_celdas_del_mes_empiezan_en_lunes():
    celdas = calendario.dias_del_mes(2026, 11)
    assert len(celdas) == 42
    assert celdas[0] == date(2026, 10, 26)
    assert celdas[-1] == date(2026, 12, 6)
    assert len(calendario.dias_del_mes(2026, 2)) == 35


def test_totales_por_semana():
    dias = calendario.por_dia([_fila(3), _fila(9), _fila(30, mes=10)])
    semanas = calendario.semanas(dias, 2026, 11)
    assert semanas[0]["neto"] == 0.0  # 26 oct - 1 nov: no hay operaciones en noviembre
    assert semanas[1]["neto"] == 9.0  # 2 - 8 nov: el 3
    assert semanas[2]["neto"] == 9.0  # 9 - 15 nov: el 9
    assert semanas[3]["neto"] == 0.0  # 23 - 29 nov
    # el 30 de octubre no entra en ninguna semana de noviembre
    assert sum(s["neto"] for s in semanas) == 18.0


# ---------------------------------------------------------------------- curva
def test_la_curva_acumula_los_dias_del_mes():
    filas = [_fila(1, pnl=10.0, fee=0.0), _fila(3, pnl=-4.0, fee=0.0), _fila(30, mes=10)]
    puntos = calendario.curva(filas, 2026, 11)
    assert puntos == [(date(2026, 11, 1), 10.0), (date(2026, 11, 3), 6.0)]
    assert calendario.curva([_fila(30, mes=10)], 2026, 11) == []


def test_la_curva_de_un_mes_vacio_esta_vacia():
    assert calendario.curva([], 2026, 12) == []
    assert calendario.curva([_fila(3, cierre=0, estado="Abierta")], 2026, 11) == []


# ---------------------------------------------------------------------- csv
def test_csv_una_fila_por_operacion_y_el_total():
    filas = [
        _fila(3, pnl=10.0, fee=1.0),
        _fila(4, exchange="bingx", symbol="ETH_USDT", pnl=-4.0, fee=2.0),
    ]
    lineas = calendario.a_csv(filas).strip().split("\n")
    assert len(lineas) == 4  # encabezado + 2 operaciones + total
    assert "2026-11-03" in lineas[1]
    assert "MEXC" in lineas[1]
    assert lineas[1].endswith("10;1;9")
    assert "BingX" in lineas[2]
    assert lineas[-1].startswith("TOTAL")
    assert lineas[-1].endswith("6;3;3")


def test_csv_usa_punto_decimal_y_punto_y_coma():
    filas = [_fila(3, pnl=1234.5, fee=0.25)]
    campos = calendario.a_csv(filas).strip().split("\n")[1].split(";")
    assert campos[8] == "1234.5"
    assert campos[9] == "0.25"
    assert "," not in calendario.a_csv(filas)
