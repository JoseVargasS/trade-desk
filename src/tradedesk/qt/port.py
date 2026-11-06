"""`UiPort` de la vista Qt: junta los diálogos que usa `controller.Control`."""

from .be import be_lista
from .dialogos_base import confirm, form, show
from .editor_orden import editar_orden
from .tpsl import editar_tpsl


class QtPort:
    """`UiPort` de la vista Qt: los diálogos de este módulo."""

    def __init__(self, ventana):
        self.ventana = ventana

    def confirm(
        self,
        titulo,
        rows=(),
        warn=None,
        danger=False,
        ok="Confirmar",
        cancel="Cancelar",
    ):
        return confirm(
            self.ventana,
            titulo,
            rows,
            warn=warn,
            danger=danger,
            ok_text=ok,
            cancel_text=cancel,
        )

    def show(self, titulo, mensaje, aviso=None, danger=False):
        show(self.ventana, titulo, mensaje, aviso=aviso, danger=danger)

    def form(self, titulo, campos, nota=None, ok="Guardar"):
        return form(self.ventana, titulo, campos, nota=nota, ok=ok)

    def status(self, texto):
        self.ventana.statusBar().showMessage(texto)

    def tpsl(self, pos, precio):
        return editar_tpsl(self.ventana, pos, int(pos.get("positionType") or 1) == 1, precio)

    def editar_orden(self, orden, contrato, a_vol):
        return editar_orden(self.ventana, orden, contrato, a_vol)

    def be_lista(self, filas):
        return be_lista(self.ventana, filas)
