"""Fixtures compartidas."""

import types

import pytest

from tests.fakes import FakeMexc, InlineThread, control
from tests.fakes import posicion as make_posicion
from tradedesk import controller


@pytest.fixture
def mx():
    return FakeMexc()


@pytest.fixture
def posicion():
    return make_posicion()


@pytest.fixture
def app(mx, monkeypatch):
    """Control con la mesa falsa: sin red y sin esperar a los hilos."""
    fake_threading = types.SimpleNamespace(Thread=InlineThread)
    monkeypatch.setattr(controller, "threading", fake_threading)
    monkeypatch.setattr("tradedesk.controller_verificacion.threading", fake_threading)
    monkeypatch.setattr("tradedesk.controller_tpsl.threading", fake_threading)
    monkeypatch.setattr("tradedesk.controller_ordenes.threading", fake_threading)
    ctl = control(mx)
    ctl.port.avisos = []
    ctl.verificaciones = []
    ctl._iniciar_verificacion = lambda accion, comprobar: ctl.verificaciones.append(
        (accion, comprobar)
    )
    return ctl
