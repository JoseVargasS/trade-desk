from datetime import datetime

from tradedesk import calendario
from tradedesk.archivo import Archivo
from tradedesk.operaciones import operaciones


def ms(dia, hora):
    return int(datetime(2026, 11, dia, hora).timestamp() * 1000)


def bx(oid, side, qty, price, tiempo, reduce_only, pnl=0, fee=0.5):
    return {
        "_exchange": "bitunix",
        "symbol": "BTCUSDT",
        "side": side,
        "reduceOnly": reduce_only,
        "qty": qty,
        "price": price,
        "fee": fee,
        "realizedPNL": pnl,
        "ctime": tiempo,
        "orderId": oid,
    }


def _neto(archivo):
    dias = calendario.por_dia(archivo.todas())
    return calendario.resumen(dias, 2026, 11)["neto"]


def test_cierre_huerfano_se_reconcilia_con_su_apertura(tmp_path):
    apertura = bx("a", 1, 1, 100, ms(3, 10), False)
    cierre = bx("c", 3, 1, 110, ms(3, 12), True, 10)
    archivo = Archivo(tmp_path / "op.json")

    archivo.fusionar(operaciones([cierre]))
    filas = archivo.fusionar(operaciones([apertura, cierre]))

    assert len(filas) == 1
    assert _neto(archivo) == 9.0
    assert filas[0]["_ordenes"] == ["a", "c"]


def test_cierre_que_consumio_dos_aperturas_reconcilia_huerfana(tmp_path):
    apertura_1 = bx("a1", 1, 1, 100, ms(3, 10), False)
    apertura_2 = bx("a2", 1, 1, 100, ms(3, 11), False)
    cierre = bx("c2", 3, 2, 110, ms(3, 12), True, 20)
    archivo = Archivo(tmp_path / "op.json")

    archivo.fusionar(operaciones([cierre]))
    filas = archivo.fusionar(operaciones([apertura_1, apertura_2, cierre]))

    assert len(filas) == 2
    assert _neto(archivo) == 18.5
    assert {tuple(fila["_ordenes"]) for fila in filas} == {("a1", "c2"), ("a2", "c2")}


def test_cierres_parciales_reconcilian_las_filas_fifo(tmp_path):
    apertura = bx("a3", 1, 2, 100, ms(3, 10), False)
    cierre_1 = bx("cp1", 3, 1, 110, ms(3, 12), True, 10)
    cierre_2 = bx("cp2", 3, 1, 110, ms(3, 13), True, 10)
    archivo = Archivo(tmp_path / "op.json")

    archivo.fusionar(operaciones([cierre_1, cierre_2]))
    filas = archivo.fusionar(operaciones([apertura, cierre_1, cierre_2]))

    assert len(filas) == 1
    assert _neto(archivo) == 18.5
    assert filas[0]["_ordenes"] == ["a3", "cp1", "cp2"]


def test_cierre_parcial_huerfano_tardio_se_borra_por_subconjunto(tmp_path):
    apertura = bx("a3", 1, 2, 100, ms(3, 10), False)
    cierre_1 = bx("cp1", 3, 1, 110, ms(3, 12), True, 10)
    cierre_2 = bx("cp2", 3, 1, 110, ms(3, 13), True, 10)
    archivo = Archivo(tmp_path / "op.json")

    archivo.fusionar(operaciones([cierre_2]))
    filas = archivo.fusionar(operaciones([apertura, cierre_1, cierre_2]))

    assert len(filas) == 1
    assert _neto(archivo) == 18.5
    assert filas[0]["_ordenes"] == ["a3", "cp1", "cp2"]


def test_mexc_refresco_parcial_no_degrada_la_fila(tmp_path):
    apertura = {
        "_exchange": "mexc",
        "symbol": "BTC_USDT",
        "side": 1,
        "positionId": 7,
        "dealVol": 1,
        "dealAvgPrice": 100,
        "totalFee": 0.5,
        "createTime": ms(4, 10),
        "orderId": "m1",
    }
    cierre = {
        "_exchange": "mexc",
        "symbol": "BTC_USDT",
        "side": 4,
        "positionId": 7,
        "dealVol": 1,
        "dealAvgPrice": 110,
        "totalFee": 0.5,
        "profit": 10,
        "createTime": ms(4, 12),
        "orderId": "m2",
    }
    archivo = Archivo(tmp_path / "op.json")

    archivo.fusionar(operaciones([apertura, cierre]))
    parcial = archivo.fusionar(operaciones([cierre]))

    assert len(parcial) == 1
    assert parcial[0]["fee"] == 1.0
    assert _neto(archivo) == 9.0


def test_mexc_fee_actualizada_con_las_mismas_ordenes_si_se_aplica(tmp_path):
    apertura = {
        "_exchange": "mexc",
        "symbol": "BTC_USDT",
        "side": 1,
        "positionId": 7,
        "dealVol": 1,
        "dealAvgPrice": 100,
        "totalFee": 0.5,
        "createTime": ms(4, 10),
        "orderId": "m1",
    }
    cierre = {
        "_exchange": "mexc",
        "symbol": "BTC_USDT",
        "side": 4,
        "positionId": 7,
        "dealVol": 1,
        "dealAvgPrice": 110,
        "totalFee": 0.5,
        "profit": 10,
        "createTime": ms(4, 12),
        "orderId": "m2",
    }
    archivo = Archivo(tmp_path / "op.json")

    archivo.fusionar(operaciones([apertura, cierre]))
    actualizada = operaciones([apertura, {**cierre, "totalFee": 0.6}])
    filas = archivo.fusionar(actualizada)

    assert len(filas) == 1
    assert filas[0]["fee"] == 1.1
    assert _neto(archivo) == 8.9


def test_filas_antiguas_sin_ordenes_no_participan_en_la_dedupe(tmp_path):
    archivo = Archivo(tmp_path / "op.json")
    antigua = {
        "_clave": "legacy",
        "_exchange": "bitunix",
        "symbol": "BTCUSDT",
        "lado": "LONG",
        "qty": 1,
        "entrada": 100,
        "salida": 110,
        "pnl": 10,
        "fee": 0.5,
        "apertura": ms(3, 10),
        "cierre": ms(3, 12),
        "abierta": 1,
        "cerrada": 1,
        "estado": "Cerrada",
    }
    nueva = {**antigua, "_clave": "fifo", "_ordenes": ["a", "c"]}
    archivo.fusionar([antigua])

    filas = archivo.fusionar([nueva])

    assert {fila["_clave"] for fila in filas} == {"legacy", "fifo"}
    assert "_ordenes" not in next(fila for fila in filas if fila["_clave"] == "legacy")
