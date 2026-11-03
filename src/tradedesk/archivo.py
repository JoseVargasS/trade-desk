"""Archivo local de operaciones: el broker borra su historial, esto no.

Cada operación se guarda en `operaciones.json` (en la raíz, ignorado por git) con
una clave estable, así un refresco la **actualiza** —un cierre parcial que después
se completa, o una fee que se ajusta— en vez de duplicarla. Con esto la pestaña
Historial sigue mostrando lo viejo aunque el exchange ya no lo devuelva.
"""

import json
import os
from pathlib import Path


class Archivo:
    """Operaciones guardadas en disco, indexadas por `_clave`."""

    def __init__(self, ruta):
        self.ruta = Path(ruta)
        self.filas = {}
        self._cargar()

    def _cargar(self):
        try:
            datos = json.loads(self.ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(datos, list):
            return
        for fila in datos:
            if isinstance(fila, dict) and fila.get("_clave"):
                self.filas[fila["_clave"]] = fila

    def fusionar(self, nuevas):
        """Guarda las operaciones nuevas o cambiadas y devuelve todo lo archivado."""
        cambio = False
        for fila in nuevas or ():
            clave = fila.get("_clave")
            if not clave:
                continue
            if self.filas.get(clave) != fila:
                self.filas[clave] = fila
                cambio = True
        if cambio:
            self._guardar()
        return self.todas()

    def todas(self):
        """Todas las operaciones, de la más nueva a la más vieja."""
        return sorted(self.filas.values(), key=lambda fila: fila.get("apertura") or 0, reverse=True)

    def _guardar(self):
        """Escribe el archivo completo de forma atómica (tmp + replace)."""
        texto = json.dumps(self.todas(), ensure_ascii=False, indent=1)
        temporal = self.ruta.with_name(self.ruta.name + ".tmp")
        try:
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            temporal.write_text(texto, encoding="utf-8")
            os.replace(temporal, self.ruta)
        except OSError:
            try:
                temporal.unlink(missing_ok=True)
            except OSError:
                pass
