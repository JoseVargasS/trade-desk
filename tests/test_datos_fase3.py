"""Escritura segura de config y rotación de log (fase 3)."""

import json
import os
import queue

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
