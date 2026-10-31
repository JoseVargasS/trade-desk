"""Fixtures compartidas."""

import pytest

from tests.fakes import FakeMexc
from tests.fakes import posicion as make_posicion


@pytest.fixture
def mx():
    return FakeMexc()


@pytest.fixture
def posicion():
    return make_posicion()
