"""Reglas del auditor de `operaciones.json` (tools/auditar_archivo.py)."""

import importlib.util
from pathlib import Path

RUTA = Path(__file__).resolve().parents[1] / "tools" / "auditar_archivo.py"
_spec = importlib.util.spec_from_file_location("auditar_archivo", RUTA)
auditar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(auditar)


def _fila(clave, **cambios):
    base = {
        "_clave": clave,
        "_exchange": "bitunix",
        "symbol": "BTCUSDT",
        "lado": "SHORT",
        "qty": 0.0212,
        "entrada": 75760.1,
        "salida": 75749.9,
        "cierre": 1789506146979,
        "cerrada": 0.0212,
        "pnl": 0.21624,
        "fee": 1.603,
    }
    base.update(cambios)
    return base


def test_cierre_con_fifo_unico_se_marca_para_borrar():
    fifo = _fila("fifo|bitunix|BTCUSDT|SHORT|1789506103842|0.0212")
    cierre = _fila("cierre|bitunix|BTCUSDT|1789506146979|SHORT|0.0212", entrada=0.0)
    borrables, ambiguos, huerfanos = auditar._duplicados([cierre, fifo])
    assert len(borrables) == 1
    assert not ambiguos and not huerfanos


def test_pnl_distinto_no_es_duplicado():
    fifo = _fila("fifo|bitunix|BTCUSDT|SHORT|1789506103842|0.0212", pnl=1.15752)
    cierre = _fila("cierre|bitunix|BTCUSDT|1789506146979|SHORT|0.0212", entrada=0.0)
    borrables, ambiguos, huerfanos = auditar._duplicados([cierre, fifo])
    assert not borrables and not ambiguos
    assert huerfanos == [cierre]


def test_dos_cierre_compartiendo_un_fifo_es_ambiguo():
    fifo = _fila("fifo|bitunix|BTCUSDT|SHORT|1789506103842|0.0212")
    uno = _fila("cierre|bitunix|BTCUSDT|1789506146979|SHORT|0.0212", entrada=0.0)
    otro = _fila("cierre|bitunix|BTCUSDT|1789506146996|SHORT|0.0212", entrada=0.0)
    borrables, ambiguos, huerfanos = auditar._duplicados([uno, otro, fifo])
    assert not borrables and not huerfanos
    assert len(ambiguos) == 2


def test_dos_fifo_iguales_es_ambiguo():
    uno = _fila("fifo|bitunix|BTCUSDT|SHORT|1789506085919|0.0212")
    otro = _fila("fifo|bitunix|BTCUSDT|SHORT|1789506103842|0.0212")
    cierre = _fila("cierre|bitunix|BTCUSDT|1789506146979|SHORT|0.0212", entrada=0.0)
    borrables, ambiguos, huerfanos = auditar._duplicados([cierre, uno, otro])
    assert not borrables and not huerfanos
    assert len(ambiguos) == 1 and len(ambiguos[0][1]) == 2
