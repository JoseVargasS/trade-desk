from tradedesk.layout import OPER_COLS
from tradedesk.qt import tabla_historial


class ScrollBar:
    def value(self):
        return 12

    def maximum(self):
        return 100

    def setValue(self, value):
        self.valor = value


class FakeTable:
    def __init__(self):
        self.filas = []
        self.escrituras = 0
        self.scroll = ScrollBar()

    def verticalScrollBar(self):
        return self.scroll

    def rowCount(self):
        return len(self.filas)

    def setRowCount(self, cantidad):
        self.filas = self.filas[:cantidad]
        self.filas.extend([[None] * len(OPER_COLS) for _ in range(cantidad - len(self.filas))])

    def insertRow(self, indice):
        self.filas.insert(indice, [None] * len(OPER_COLS))

    def removeRow(self, indice):
        self.filas.pop(indice)

    def setUpdatesEnabled(self, _enabled):
        pass

    def setItem(self, fila, columna, item):
        self.filas[fila][columna] = item
        self.escrituras += 1

    def setCellWidget(self, fila, columna, widget):
        self.filas[fila][columna] = widget
        self.escrituras += 1


class FakeItem:
    def setData(self, *_args):
        pass

    def setTextAlignment(self, *_args):
        pass


class FakeLabel:
    def setText(self, texto):
        self.texto = texto


class Probe(tabla_historial.TablaHistorial):
    def __init__(self):
        self._tabla_hist = FakeTable()
        self._lbl_hist = FakeLabel()


def _operacion(clave, pnl=0):
    return {
        "_clave": clave,
        "_exchange": "mexc",
        "symbol": "BTCUSDT",
        "lado": "LONG",
        "qty": 0.001,
        "entrada": 60000,
        "salida": 0,
        "pnl": pnl,
        "fee": 0.01,
        "apertura": 1700000000000,
        "cierre": 0,
        "estado": "Abierta",
    }


def test_historial_no_repinta_lo_que_no_cambio(monkeypatch):
    monkeypatch.setattr(tabla_historial, "QTableWidgetItem", FakeItem)
    monkeypatch.setattr(tabla_historial, "CeldaPar", lambda *_args, **_kwargs: object())
    probe = Probe()
    filas = [_operacion("primera"), _operacion("segunda")]

    probe._pintar_historial(filas)
    escrituras = probe._tabla_hist.escrituras
    probe._pintar_historial(filas)

    assert escrituras == 22
    assert probe._tabla_hist.escrituras == escrituras
    assert probe._lbl_hist.texto == "2 operaciones"
    assert probe._tabla_hist.scroll.valor == 12


def test_historial_actualiza_o_inserta_solo_las_filas_afectadas(monkeypatch):
    monkeypatch.setattr(tabla_historial, "QTableWidgetItem", FakeItem)
    monkeypatch.setattr(tabla_historial, "CeldaPar", lambda *_args, **_kwargs: object())
    probe = Probe()
    primera, segunda = _operacion("primera"), _operacion("segunda")
    probe._pintar_historial([primera, segunda])
    escrituras = probe._tabla_hist.escrituras

    segunda = _operacion("segunda", pnl=1)
    probe._pintar_historial([primera, segunda])
    assert probe._tabla_hist.escrituras == escrituras + len(OPER_COLS)

    escrituras = probe._tabla_hist.escrituras
    nueva = _operacion("nueva")
    probe._pintar_historial([nueva, primera, segunda])
    assert probe._historial_ids == [
        (("mexc", "nueva"), 0),
        (("mexc", "primera"), 0),
        (("mexc", "segunda"), 0),
    ]
    assert probe._tabla_hist.rowCount() == 3
    assert probe._tabla_hist.escrituras == escrituras + len(OPER_COLS)

    escrituras = probe._tabla_hist.escrituras
    probe._pintar_historial([segunda, nueva, primera])
    assert probe._historial_ids[0] == (("mexc", "segunda"), 0)
    assert probe._tabla_hist.escrituras == escrituras + len(OPER_COLS)
