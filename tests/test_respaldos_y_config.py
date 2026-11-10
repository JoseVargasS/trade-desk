"""Escritura segura de config y rotación de log (fase 3)."""

import json
import os
import queue
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from tradedesk import paths
from tradedesk.session import Session


class _Mx:
    api_key = ""


class _Otro:
    key = ""


def _sesion(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    return Session(mx=_Mx(), bitunix=_Otro(), bingx=_Otro())


def test_config_se_guarda_atomico(tmp_path, monkeypatch):
    sesion = _sesion(tmp_path, monkeypatch)
    sesion.tarjetas = [{"id": "BTC_USDT", "symbol": "BTC_USDT"}]
    sesion._guardar_config()
    assert (
        json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["cards"][0]["symbol"]
        == "BTC_USDT"
    )
    assert not (tmp_path / "config.json.tmp").exists()


def test_config_falla_sin_corromper_y_avisa(tmp_path, monkeypatch):
    sesion = _sesion(tmp_path, monkeypatch)
    (tmp_path / "config.json").write_text(
        json.dumps({"cards": [{"id": "viejas"}]}), encoding="utf-8"
    )

    def falla(*_a, **_k):
        raise OSError("disco lleno")

    monkeypatch.setattr(os, "replace", falla)
    sesion._guardar_config()
    assert (
        json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["cards"][0]["id"]
        == "viejas"
    )
    mensajes = []
    while True:
        try:
            mensajes.append(sesion.q.get_nowait())
        except queue.Empty:
            break
    assert any(m[0] == "status" and "config.json" in m[1] for m in mensajes)


def test_config_corrupto_se_avisa_sin_detener_el_arranque(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    (tmp_path / "config.json").write_text("{roto", encoding="utf-8")

    sesion = Session(mx=_Mx(), bitunix=_Otro(), bingx=_Otro())

    assert sesion.tarjetas == []
    assert any(
        mensaje[0] == "status" and "no se pudo leer config.json" in mensaje[1].lower()
        for mensaje in list(sesion.q.queue)
    )


def test_log_rota_a_un_mega(tmp_path, monkeypatch):
    sesion = _sesion(tmp_path, monkeypatch)
    ruta = tmp_path / "trades.log"
    ruta.write_text("x" * 1_000_005, encoding="utf-8")
    sesion.log("hola")
    assert (tmp_path / "trades.log.1").exists()
    assert "hola" in ruta.read_text(encoding="utf-8")


def test_log_rotacion_respeta_tres_copias(tmp_path, monkeypatch):
    sesion = _sesion(tmp_path, monkeypatch)
    for nombre, texto in (
        ("trades.log", "a"),
        ("trades.log.1", "b"),
        ("trades.log.2", "c"),
        ("trades.log.3", "d"),
    ):
        (tmp_path / nombre).write_text(texto, encoding="utf-8")
    (tmp_path / "trades.log").write_text("x" * 1_000_005, encoding="utf-8")
    sesion.log("nueva")
    assert (tmp_path / "trades.log.3").read_text(encoding="utf-8") == "c"
    assert (tmp_path / "trades.log.2").read_text(encoding="utf-8") == "b"
    assert (tmp_path / "trades.log.1").exists()


def test_fallo_de_rotacion_del_log_se_reporta(tmp_path, monkeypatch):
    sesion = _sesion(tmp_path, monkeypatch)
    ruta = tmp_path / "trades.log"
    ruta.write_text("x" * 1_000_005, encoding="utf-8")

    def falla(*_args, **_kwargs):
        raise OSError("archivo ocupado")

    monkeypatch.setattr(os, "replace", falla)
    sesion.log("evento")

    assert sesion.q.get_nowait() == (
        "error",
        "No se pudo escribir trades.log: archivo ocupado",
    )
    assert ruta.stat().st_size == 1_000_005


def test_operaciones_corruptas_publican_aviso(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    (tmp_path / "operaciones.json").write_text("{roto", encoding="utf-8")
    sesion = Session(mx=_Mx(), bitunix=_Otro(), bingx=_Otro())
    mensajes = []
    while True:
        try:
            mensajes.append(sesion.q.get_nowait())
        except queue.Empty:
            break
    assert any(m[0] == "notice" for m in mensajes)


def test_fallo_de_lectura_de_operaciones_publica_estado_y_preserva_original(tmp_path, monkeypatch):
    ruta = tmp_path / "operaciones.json"
    original = b'{"invalido":"por permisos"}'
    ruta.write_bytes(original)
    leer = Path.read_text

    def falla_en_operaciones(path, *args, **kwargs):
        if path == ruta:
            raise PermissionError("sin permiso")
        return leer(path, *args, **kwargs)

    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(Path, "read_text", falla_en_operaciones)
    app = Session(mx=_Mx(), bitunix=_Otro(), bingx=_Otro())
    mensajes = []
    while not app.q.empty():
        mensajes.append(app.q.get_nowait())

    assert any(m[0] == "status" and "no se pudo leer" in m[1].lower() for m in mensajes)
    assert ruta.read_bytes() == original
    assert list(tmp_path.glob("operaciones.corrupto-*.json"))


def test_log_serializa_escrituras_concurrentes(tmp_path, monkeypatch):
    app = _sesion(tmp_path, monkeypatch)
    activos = 0
    max_activos = 0
    estado_lock = threading.Lock()

    def rotacion_lenta(_ruta):
        nonlocal activos, max_activos
        with estado_lock:
            activos += 1
            max_activos = max(max_activos, activos)
        time.sleep(0.002)
        with estado_lock:
            activos -= 1

    app._rotar_log = rotacion_lenta
    hilos = [
        threading.Thread(
            target=lambda prefijo=prefijo: [app.log(f"{prefijo}-{indice}") for indice in range(10)]
        )
        for prefijo in range(5)
    ]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    lineas = (tmp_path / "trades.log").read_text(encoding="utf-8").splitlines()
    assert max_activos == 1
    assert len(lineas) == 50
    assert len({linea.split("  ", 1)[1] for linea in lineas}) == 50


def test_estado_de_archivo_se_publica_una_sola_vez():
    app = object.__new__(Session)
    app.archivo = SimpleNamespace(estado="No se pudo guardar operaciones.json")
    app._archivo_estado_publicado = None
    app.q = queue.Queue()

    app._publicar_estado_archivo()
    app._publicar_estado_archivo()

    assert app.q.get_nowait() == ("status", app.archivo.estado)
    assert app.q.empty()
