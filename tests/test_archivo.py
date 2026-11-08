"""Archivo local de operaciones: sobrevive a fallos y al borrado del broker."""

import json
from pathlib import Path

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


def _fila_operacion(clave, **cambios):
    fila = {
        "_clave": clave,
        "_exchange": "bitunix",
        "symbol": "BTCUSDT",
        "lado": "LONG",
        "qty": 1.0,
        "entrada": 100.0,
        "salida": 101.0,
        "abierta": 1.0,
        "cerrada": 1.0,
        "cierre": 2000,
        "pnl": 1.0,
        "fee": 0.2,
        "estado": "Cerrada",
    }
    fila.update(cambios)
    return fila


def test_fusionar_reemplaza_un_cierre_huerfano_solo_con_match_unico(tmp_path):
    archivo = Archivo(tmp_path / "operaciones.json")
    huerfana = _fila_operacion(
        "cierre|bitunix|BTCUSDT|2000|LONG|1",
        entrada=0.0,
        fee=0.1,
    )
    fifo = _fila_operacion(
        "fifo|bitunix|BTCUSDT|LONG|1000|1",
        fee=0.3,
    )

    filas = archivo.fusionar([huerfana])
    filas = archivo.fusionar([fifo])

    assert len(filas) == 1
    assert filas[0]["_clave"] == fifo["_clave"]
    assert filas[0]["entrada"] == 100.0
    assert filas[0]["fee"] == 0.3


def test_fusionar_conserva_cierres_huerfanos_si_el_match_es_ambiguo(tmp_path):
    archivo = Archivo(tmp_path / "operaciones.json")
    huerfana = _fila_operacion("cierre|bitunix|BTCUSDT|2000|LONG|1", entrada=0.0)
    fifo_a = _fila_operacion("fifo|bitunix|BTCUSDT|LONG|1000|1")
    fifo_b = _fila_operacion("fifo|bitunix|BTCUSDT|LONG|1100|1")

    filas = archivo.fusionar([huerfana, fifo_a, fifo_b])

    assert {fila["_clave"] for fila in filas} == {
        huerfana["_clave"],
        fifo_a["_clave"],
        fifo_b["_clave"],
    }


def test_fusionar_no_borra_dos_cierres_que_compiten_por_la_misma_fifo(tmp_path):
    archivo = Archivo(tmp_path / "operaciones.json")
    cierre_a = _fila_operacion(
        "cierre|bitunix|BTCUSDT|1900|LONG|1",
        entrada=0.0,
        cierre=1900,
    )
    cierre_b = _fila_operacion(
        "cierre|bitunix|BTCUSDT|2100|LONG|1",
        entrada=0.0,
        cierre=2100,
    )
    fifo = _fila_operacion("fifo|bitunix|BTCUSDT|LONG|1000|1", cierre=2000)

    filas = archivo.fusionar([cierre_a, cierre_b, fifo])

    assert {fila["_clave"] for fila in filas} == {
        cierre_a["_clave"],
        cierre_b["_clave"],
        fifo["_clave"],
    }


def test_fusionar_no_reconcilia_por_cercania_si_no_coinciden_los_datos(tmp_path):
    archivo = Archivo(tmp_path / "operaciones.json")
    huerfana = _fila_operacion("cierre|bitunix|BTCUSDT|2000|LONG|1", entrada=0.0)
    fifo = _fila_operacion("fifo|bitunix|BTCUSDT|LONG|1000|1", pnl=2.0)

    filas = archivo.fusionar([huerfana, fifo])

    assert len(filas) == 2


def test_fusionar_no_reconcilia_filas_sin_cantidad_cerrada(tmp_path):
    archivo = Archivo(tmp_path / "operaciones.json")
    huerfana = _fila_operacion(
        "cierre|bitunix|BTCUSDT|2000|LONG|1",
        entrada=0.0,
        cerrada=0.0,
        salida=0.0,
    )
    fifo = _fila_operacion(
        "fifo|bitunix|BTCUSDT|LONG|1000|1",
        cerrada=0.0,
        salida=0.0,
    )

    filas = archivo.fusionar([huerfana, fifo])

    assert len(filas) == 2


def test_fusionar_conserva_fila_mexc_completa_ante_un_refresco_parcial(tmp_path):
    archivo = Archivo(tmp_path / "operaciones.json")
    completa = _fila_operacion(
        "pos|mexc|7",
        _exchange="mexc",
        symbol="BTC_USDT",
        qty=2.0,
        abierta=2.0,
        cerrada=1.0,
        entrada=100.0,
        fee=0.5,
    )
    parcial = _fila_operacion(
        "pos|mexc|7",
        _exchange="mexc",
        symbol="BTC_USDT",
        qty=1.0,
        abierta=0.0,
        cerrada=1.0,
        entrada=0.0,
        fee=0.2,
    )

    archivo.fusionar([completa])
    filas = archivo.fusionar([parcial])

    assert filas == [completa]


def test_fusionar_actualiza_fila_mexc_cuando_llega_una_version_completa(tmp_path):
    archivo = Archivo(tmp_path / "operaciones.json")
    inicial = _fila_operacion(
        "pos|mexc|7",
        _exchange="mexc",
        symbol="BTC_USDT",
        qty=1.0,
        abierta=1.0,
        cerrada=0.0,
        cierre=0,
        fee=0.1,
        estado="Abierta",
    )
    actualizada = {**inicial, "cerrada": 1.0, "cierre": 3000, "fee": 0.3, "estado": "Cerrada"}

    archivo.fusionar([inicial])
    filas = archivo.fusionar([actualizada])

    assert filas == [actualizada]


def test_archivo_corrupto_va_a_cuarentena(tmp_path):
    ruta = tmp_path / "operaciones.json"
    ruta.write_text("{esto no es json", encoding="utf-8")
    archivo = Archivo(ruta)
    assert archivo.todas() == []
    assert archivo.aviso is not None
    cuarentena = list(tmp_path.glob("operaciones.corrupto-*.json"))
    assert len(cuarentena) == 1
    assert "{esto no es json" in cuarentena[0].read_text(encoding="utf-8")
    assert ruta.read_text(encoding="utf-8") == "{esto no es json"


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


def test_error_de_lectura_respalda_y_no_sobrescribe_el_original(tmp_path, monkeypatch):
    ruta = tmp_path / "operaciones.json"
    original = b'{"archivo":"no legible"}'
    ruta.write_bytes(original)
    leer = Path.read_text

    def falla_en_operaciones(path, *args, **kwargs):
        if path == ruta:
            raise PermissionError("sin permiso")
        return leer(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", falla_en_operaciones)
    archivo = Archivo(ruta)
    copias = list(tmp_path.glob("operaciones.corrupto-*.json"))

    assert len(copias) == 1
    assert copias[0].read_bytes() == original
    assert ruta.read_bytes() == original
    assert archivo.estado
    archivo.fusionar([_op("nueva")])
    assert ruta.read_bytes() == original


def test_respaldos_fechados_rotan_sin_pisar_los_recientes(tmp_path, monkeypatch):
    ruta = tmp_path / "operaciones.json"
    leer = Path.read_text
    monkeypatch.setattr(
        Path, "read_text", lambda *_a, **_k: (_ for _ in ()).throw(PermissionError())
    )
    for indice in range(4):
        ruta.write_bytes(f"copia-{indice}".encode())
        archivo = Archivo(ruta)
        assert archivo.estado
    monkeypatch.setattr(Path, "read_text", leer)

    copias = sorted(tmp_path.glob("operaciones.corrupto-*.json"))
    assert len(copias) == 3
    assert {path.read_bytes() for path in copias} == {b"copia-1", b"copia-2", b"copia-3"}


def test_fallo_al_crear_backup_queda_reportado_y_guarda_el_historial(tmp_path, monkeypatch):
    ruta = tmp_path / "operaciones.json"
    archivo = Archivo(ruta)
    archivo.fusionar([_op("anterior")])

    def falla(*_args, **_kwargs):
        raise OSError("disco lleno")

    monkeypatch.setattr("tradedesk.archivo.shutil.copy2", falla)
    archivo.fusionar([_op("nueva")])

    assert archivo.estado and "respaldo" in archivo.estado.lower()
    assert {fila["_clave"] for fila in json.loads(ruta.read_text(encoding="utf-8"))} == {
        "anterior",
        "nueva",
    }
