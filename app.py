"""Lanzador de Trade Desk.

El acceso directo del escritorio apunta a este archivo (pythonw app.py), asi que
se queda en la raiz: el codigo vive en `src/tradedesk` y aqui solo se agrega
`src` al path y se arranca la app. Doble clic = misma ventana de siempre.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from tradedesk.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
