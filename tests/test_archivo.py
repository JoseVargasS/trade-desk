"""Archivo local de operaciones: sobrevive a fallos y al borrado del broker."""

import json

from tradedesk.archivo import Archivo


def _op(clave, pnl=0.0, estado="Cerrada", apertura=1000):
    return {
        "_clave": clave,
        "apertura": apertura,
        "pnl": pnl,
        "estado": estado,
        "symbol": "BTC_USDT",
    }


def test_guarda_y_recarga(tmp_path):
    ruta = tmp_path / "operaciones.json"
    filas = Archivo(ruta).fusionar([_op("a"), _op("b")])
    assert len(filas) == 2
    otra = Archivo(ruta)
    assert {fila["_clave"] for fila in otra.todas()} == {"a", "b"}


def test_actualiza_sin_duplicar(tmp_path):
    ruta = tmp_path / "operaciones.json"
    archivo = Archivo(ruta)
    archivo.fusionar([_op("a", pnl=0.01, estado="Parcial")])
    archivo.fusionar([_op("a", pnl=0.05, estado="Cerrada")])
    assert len(archivo.todas()) == 1
    assert archivo.todas()[0]["pnl"] == 0.05
    assert archivo.todas()[0]["estado"] == "Cerrada"


def test_archivo_corrupto_va_a_cuarentena(tmp_path):
    ruta = tmp_path / "operaciones.json"
    ruta.write_text("{esto no es json", encoding="utf-8")
    archivo = Archivo(ruta)
    assert archivo.todas() == []
    assert archivo.aviso is not None
    cuarentena = list(tmp_path.glob("operaciones.corrupto-*.json"))
    assert len(cuarentena) == 1
    assert "{esto no es json" in cuarentena[0].read_text(encoding="utf-8")


def test_archivo_corrupto_recupera_desde_backup(tmp_path):
    ruta = tmp_path / "operaciones.json"
    backup = tmp_path / "operaciones.json.bak"
    backup.write_text(json.dumps([_op("vieja", pnl=1.5)]), encoding="utf-8")
    ruta.write_text("{roto", encoding="utf-8")
    archivo = Archivo(ruta)
    assert [fila["_clave"] for fila in archivo.todas()] == ["vieja"]
    assert archivo.aviso is not None
    assert "respaldo" in archivo.aviso[1].lower()
    assert list(tmp_path.glob("operaciones.corrupto-*.json"))


def test_guarda_crea_backup(tmp_path):
    ruta = tmp_path / "operaciones.json"
    archivo = Archivo(ruta)
    archivo.fusionar([_op("a", pnl=1.0)])
    assert not ruta.with_name("operaciones.json.bak").exists()
    archivo.fusionar([_op("b", pnl=2.0)])
    backup = json.loads(ruta.with_name("operaciones.json.bak").read_text(encoding="utf-8"))
    assert {fila["_clave"] for fila in backup} == {"a"}


def test_sin_clave_se_ignora(tmp_path):
    archivo = Archivo(tmp_path / "operaciones.json")
    assert archivo.fusionar([{"pnl": 1.0}]) == []


def test_ordena_de_la_mas_nueva_a_la_mas_vieja(tmp_path):
    archivo = Archivo(tmp_path / "operaciones.json")
    filas = archivo.fusionar([_op("a", apertura=1), _op("b", apertura=3), _op("c", apertura=2)])
    assert [fila["_clave"] for fila in filas] == ["b", "c", "a"]
