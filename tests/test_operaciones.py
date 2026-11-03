"""Emparejado del historial: una fila por operación, con PnL y fees juntos."""

from tradedesk.operaciones import operaciones


def _mexc(position, side, vol, precio, profit, fee, ms):
    return {
        "_exchange": "mexc",
        "positionId": position,
        "symbol": "BTC_USDT",
        "side": side,
        "dealVol": vol,
        "dealAvgPrice": precio,
        "profit": profit,
        "totalFee": fee,
        "createTime": ms,
    }


def _bitunix(side, qty, precio, pnl, fee, ms, reduce=False, symbol="BTCUSDT"):
    return {
        "_exchange": "bitunix",
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "avgPrice": precio,
        "profit": pnl,
        "totalFee": fee,
        "reduceOnly": reduce,
        "ctime": str(ms),
    }


def test_mexc_une_apertura_y_cierres_parciales():
    filas = operaciones(
        [
            _mexc(1, 2, 2, 76830.7, 0.01626, 0.0122, 1793674541000),
            _mexc(1, 2, 1, 76816.2, 0.00958, 0.0061, 1793674467000),
            _mexc(1, 3, 3, 76912, 0, 0.0184, 1793673885000),
        ]
    )
    assert len(filas) == 1
    fila = filas[0]
    assert fila["lado"] == "SHORT"
    assert fila["qty"] == 3
    assert fila["entrada"] == 76912
    assert abs(fila["salida"] - (2 * 76830.7 + 76816.2) / 3) < 1e-9
    assert abs(fila["pnl"] - 0.02584) < 1e-9
    assert abs(fila["fee"] - (0.0184 + 0.0122 + 0.0061)) < 1e-9
    assert fila["estado"] == "Cerrada"
    assert fila["apertura"] == 1793673885000
    assert fila["cierre"] == 1793674541000


def test_bitunix_empareja_por_lado_sin_position_id():
    filas = operaciones(
        [
            _bitunix(1, 0.0002, 76895.4, -0.00002, 0.0077, 1793672692760, reduce=True),
            _bitunix(3, 0.0002, 76891.5, 0, 0.0077, 1793672677614),
        ]
    )
    assert len(filas) == 1
    fila = filas[0]
    assert fila["_exchange"] == "bitunix"
    assert fila["lado"] == "SHORT"
    assert fila["entrada"] == 76891.5
    assert fila["salida"] == 76895.4
    assert abs(fila["pnl"] + 0.00002) < 1e-9
    assert fila["estado"] == "Cerrada"


def test_bitunix_un_cierre_puede_consumir_dos_aperturas():
    filas = operaciones(
        [
            _bitunix(1, 0.0001, 70000, 0, 0.003, 1000),
            _bitunix(1, 0.0002, 71000, 0, 0.006, 2000),
            _bitunix(3, 0.0003, 72000, 0.01, 0.009, 3000, reduce=True),
        ]
    )
    assert len(filas) == 2
    assert {round(fila["qty"], 4) for fila in filas} == {0.0001, 0.0002}
    assert all(fila["estado"] == "Cerrada" for fila in filas)
    assert all(fila["salida"] == 72000 for fila in filas)


def test_cierre_sin_apertura_no_se_pierde():
    filas = operaciones([_bitunix(3, 0.0002, 72000, 0.0016, 0.0077, 1000, reduce=True)])
    assert len(filas) == 1
    assert filas[0]["estado"] == "Cerrada"
    assert filas[0]["entrada"] == 0
    assert abs(filas[0]["pnl"] - 0.0016) < 1e-9


def test_posicion_abierta_y_parcial():
    filas = operaciones(
        [
            _bitunix(1, 0.0003, 76000, 0, 0.0115, 1000),
            _bitunix(3, 0.0001, 77000, 0.0004, 0.0038, 2000, reduce=True),
        ]
    )
    assert len(filas) == 1
    assert filas[0]["estado"] == "Parcial"
    assert filas[0]["qty"] == 0.0003
    assert abs(filas[0]["cerrada"] - 0.0001) < 1e-12
    assert abs(filas[0]["pnl"] - 0.0004) < 1e-9

    solo_abierta = operaciones([_bitunix(1, 0.0003, 76000, 0, 0.0115, 1000)])
    assert solo_abierta[0]["estado"] == "Abierta"
    assert solo_abierta[0]["cierre"] == 0


def test_no_mezcla_simbolos_ni_exchanges():
    filas = operaciones(
        [
            _bitunix(1, 0.0002, 100, 0, 0.001, 1000, symbol="ETHUSDT"),
            _bitunix(1, 0.0002, 200, 0, 0.001, 2000, symbol="BTCUSDT"),
            _mexc(5, 1, 2, 300, 0, 0.01, 3000),
        ]
    )
    assert len(filas) == 3
    assert {fila["symbol"] for fila in filas} == {"ETHUSDT", "BTCUSDT", "BTC_USDT"}


def test_ordena_de_la_mas_nueva_a_la_mas_vieja():
    filas = operaciones(
        [
            _mexc(1, 1, 1, 100, 0, 0.01, 1000),
            _mexc(2, 1, 1, 200, 0, 0.01, 3000),
            _mexc(3, 1, 1, 300, 0, 0.01, 2000),
        ]
    )
    assert [fila["entrada"] for fila in filas] == [200, 300, 100]
