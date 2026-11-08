"""Archivo local de operaciones: el broker borra su historial, esto no.

Cada operación se guarda en `operaciones.json` (en la raíz, ignorado por git) con
una clave estable, así un refresco la **actualiza** —un cierre parcial que después
se completa, o una fee que se ajusta— en vez de duplicarla. Con esto la pestaña
Historial sigue mostrando lo viejo aunque el exchange ya no lo devuelva.
"""

import json
import math
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
        self.estado = None
        self._lectura_fallida = False
        self._cargar()

    @property
    def backup(self):
        return self.ruta.with_name(self.ruta.name + ".bak")

    def _cargar(self):
        try:
            texto = self.ruta.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        except (OSError, UnicodeError):
            self._lectura_fallida = True
            nombre = self._copia_fechada()
            recupero = self._cargar_backup()
            if nombre and recupero:
                self.estado = (
                    "No se pudo leer operaciones.json. Se cargó el respaldo anterior; "
                    f"se guardó una copia fechada ({nombre}). No se escribirá sobre el original."
                )
            elif nombre:
                self.estado = (
                    "No se pudo leer operaciones.json ni recuperar el respaldo; "
                    f"se conservó una copia fechada ({nombre}). No se escribirá sobre el original."
                )
            else:
                self.estado = (
                    "No se pudo leer ni respaldar operaciones.json. Se conserva el original "
                    "sin modificarlo."
                )
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
        return self._copia_fechada()

    def _copia_fechada(self):
        sello = datetime.now().strftime("%Y%m%d-%H%M%S")
        for numero in range(100):
            sufijo = f"-{numero}" if numero else ""
            destino = self.ruta.with_name(
                f"{self.ruta.stem}.corrupto-{sello}{sufijo}{self.ruta.suffix}"
            )
            try:
                with self.ruta.open("rb") as original, destino.open("xb") as respaldo:
                    shutil.copyfileobj(original, respaldo)
            except FileExistsError:
                continue
            except OSError:
                try:
                    destino.unlink(missing_ok=True)
                except OSError:
                    pass
                return None
            self._rotar_copias_fechadas()
            return destino.name
        return None

    def _rotar_copias_fechadas(self, conservar=3):
        prefijo = f"{self.ruta.stem}.corrupto-"

        def antiguedad(copia):
            sello = copia.stem[len(prefijo) :]
            numero = int(sello[16:]) if len(sello) > 16 and sello[15] == "-" else 0
            return sello[:15], numero

        copias = sorted(self.ruta.parent.glob(f"{prefijo}*{self.ruta.suffix}"), key=antiguedad)
        for copia in copias[:-conservar]:
            try:
                copia.unlink()
            except OSError:
                pass

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

    @staticmethod
    def _numero(fila, campo):
        try:
            return float(fila.get(campo) or 0)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _es_cierre_huerfano_duplicado(cls, cierre, fifo):
        if not str(cierre.get("_clave") or "").startswith("cierre|"):
            return False
        if not str(fifo.get("_clave") or "").startswith("fifo|"):
            return False
        if any(cierre.get(campo) != fifo.get(campo) for campo in ("_exchange", "symbol", "lado")):
            return False
        ms_cierre = cls._numero(cierre, "cierre")
        ms_fifo = cls._numero(fifo, "cierre")
        if ms_cierre <= 0 or ms_fifo <= 0 or abs(ms_cierre - ms_fifo) >= 1000:
            return False
        cerrada = cls._numero(cierre, "cerrada")
        salida = cls._numero(cierre, "salida")
        if cerrada <= 0 or salida <= 0:
            return False
        if not math.isclose(
            cerrada,
            cls._numero(fifo, "cerrada"),
            rel_tol=1e-9,
            abs_tol=1e-12,
        ):
            return False
        if not math.isclose(
            cls._numero(cierre, "pnl"),
            cls._numero(fifo, "pnl"),
            rel_tol=1e-9,
            abs_tol=1e-10,
        ):
            return False
        return math.isclose(
            salida,
            cls._numero(fifo, "salida"),
            rel_tol=1e-9,
            abs_tol=1e-12,
        )

    @classmethod
    def _menos_completa(cls, nueva, anterior):
        es_posicion_mexc = nueva.get("_exchange") == "mexc" and str(
            nueva.get("_clave") or ""
        ).startswith("pos|")
        if not es_posicion_mexc:
            return False
        if cls._numero(anterior, "entrada") > 0 and cls._numero(nueva, "entrada") <= 0:
            return True
        return any(
            cls._numero(nueva, campo) + 1e-12 < cls._numero(anterior, campo)
            for campo in ("qty", "abierta", "cerrada")
        )

    def _quitar_cierres_huerfanos_duplicados(self):
        cierres = [
            fila
            for fila in self.filas.values()
            if str(fila.get("_clave") or "").startswith("cierre|")
        ]
        fifos = [
            fila
            for fila in self.filas.values()
            if str(fila.get("_clave") or "").startswith("fifo|")
        ]
        matches = {
            id(cierre): [fifo for fifo in fifos if self._es_cierre_huerfano_duplicado(cierre, fifo)]
            for cierre in cierres
        }
        conteo_fifo = {id(fifo): 0 for fifo in fifos}
        for candidatos in matches.values():
            for fifo in candidatos:
                conteo_fifo[id(fifo)] += 1
        borrar = [
            cierre["_clave"]
            for cierre in cierres
            if len(matches[id(cierre)]) == 1 and conteo_fifo[id(matches[id(cierre)][0])] == 1
        ]
        for clave in borrar:
            del self.filas[clave]
        return bool(borrar)

    def fusionar(self, nuevas):
        """Guarda las operaciones nuevas o cambiadas y devuelve todo lo archivado."""
        cambio = False
        for fila in nuevas or ():
            clave = fila.get("_clave")
            if not clave:
                continue
            anterior = self.filas.get(clave)
            if anterior and self._menos_completa(fila, anterior):
                continue
            if self.filas.get(clave) != fila:
                self.filas[clave] = fila
                cambio = True
        cambio = self._quitar_cierres_huerfanos_duplicados() or cambio
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
        except OSError as exc:
            self.estado = f"No se pudo crear el respaldo de operaciones.json: {exc}"

    def _guardar(self):
        """Escribe el archivo completo de forma atómica (tmp + replace)."""
        if self._lectura_fallida:
            return
        texto = json.dumps(self.todas(), ensure_ascii=False, indent=1)
        temporal = self.ruta.with_name(self.ruta.name + ".tmp")
        try:
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            self._respaldar()
            temporal.write_text(texto, encoding="utf-8")
            os.replace(temporal, self.ruta)
        except OSError as exc:
            self.estado = f"No se pudo guardar operaciones.json: {exc}"
            try:
                temporal.unlink(missing_ok=True)
            except OSError:
                pass
