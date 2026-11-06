"""Archivo local de operaciones: el broker borra su historial, esto no.

Cada operación se guarda en `operaciones.json` (en la raíz, ignorado por git) con
una clave estable, así un refresco la **actualiza** —un cierre parcial que después
se completa, o una fee que se ajusta— en vez de duplicarla. Con esto la pestaña
Historial sigue mostrando lo viejo aunque el exchange ya no lo devuelva.
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path


class Archivo:
    """Operaciones guardadas en disco, indexadas por `_clave`."""

    def __init__(self, ruta):
        self.ruta = Path(ruta)
        self.filas = {}
        # aviso para la UI: (titulo, mensaje, detalle, danger) o None
        self.aviso = None
        self._cargar()

    @property
    def backup(self):
        return self.ruta.with_name(self.ruta.name + ".bak")

    def _cargar(self):
        try:
            texto = self.ruta.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        except OSError:
            return
        try:
            datos = json.loads(texto)
        except ValueError:
            self._recuperar_corrupto()
            return
        if not isinstance(datos, list):
            self._recuperar_corrupto()
            return
        for fila in datos:
            if isinstance(fila, dict) and fila.get("_clave"):
                self.filas[fila["_clave"]] = fila

    def _cargar_backup(self):
        try:
            datos = json.loads(self.backup.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if not isinstance(datos, list):
            return False
        cargadas = 0
        for fila in datos:
            if isinstance(fila, dict) and fila.get("_clave"):
                self.filas[fila["_clave"]] = fila
                cargadas += 1
        return cargadas > 0

    def _cuarentena(self):
        sello = datetime.now().strftime("%Y%m%d-%H%M%S")
        destino = self.ruta.with_name(f"{self.ruta.stem}.corrupto-{sello}{self.ruta.suffix}")
        try:
            os.replace(self.ruta, destino)
            return destino.name
        except OSError:
            try:
                shutil.copy2(self.ruta, destino)
                self.ruta.unlink(missing_ok=True)
                return destino.name
            except OSError:
                return None

    def _recuperar_corrupto(self):
        nombre = self._cuarentena()
        recupero = self._cargar_backup()
        if recupero and nombre:
            self.aviso = (
                "Historial recuperado",
                "El archivo de operaciones estaba dañado. Se cargó el último respaldo.",
                f"Copia guardada como {nombre}",
                True,
            )
        elif recupero:
            self.aviso = (
                "Historial recuperado",
                "El archivo de operaciones estaba dañado. Se cargó el último respaldo.",
                None,
                True,
            )
        elif nombre:
            self.aviso = (
                "Historial dañado",
                "No se pudo leer el archivo de operaciones y no había respaldo.",
                f"Copia guardada como {nombre}",
                True,
            )
        else:
            self.aviso = (
                "Historial dañado",
                "No se pudo leer el archivo de operaciones.",
                "Revisa operaciones.json en la carpeta de la app.",
                True,
            )

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

    def _respaldar(self):
        if not self.ruta.exists():
            return
        try:
            shutil.copy2(self.ruta, self.backup)
        except OSError:
            pass

    def _guardar(self):
        """Escribe el archivo completo de forma atómica (tmp + replace)."""
        texto = json.dumps(self.todas(), ensure_ascii=False, indent=1)
        temporal = self.ruta.with_name(self.ruta.name + ".tmp")
        try:
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            self._respaldar()
            temporal.write_text(texto, encoding="utf-8")
            os.replace(temporal, self.ruta)
        except OSError:
            try:
                temporal.unlink(missing_ok=True)
            except OSError:
                pass
