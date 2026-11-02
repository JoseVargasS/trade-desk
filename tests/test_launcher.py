"""El lanzador del acceso directo abre la vista Qt."""

import tradedesk.__main__ as lanzador
import tradedesk.qt.__main__ as vista


def test_el_lanzador_abre_la_vista_qt(monkeypatch):
    llamado = []
    monkeypatch.setattr(vista, "main", lambda: llamado.append(True) or 0)

    resultado = lanzador.main()

    assert resultado == 0
    assert llamado == [True]
