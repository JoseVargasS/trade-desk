"""Rutas del proyecto: datos del usuario y assets del paquete.

Los datos (config, logs) viven en la raiz del repo, fuera del paquete: git los
ignora y `pythonw -m tradedesk` funciona desde cualquier copia del proyecto.
"""

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT = PACKAGE_DIR.parents[1]  # src/tradedesk -> raiz del repo
DATA_DIR = Path(os.environ.get("TRADEDESK_DATA") or ROOT)
ASSETS = PACKAGE_DIR / "assets"
