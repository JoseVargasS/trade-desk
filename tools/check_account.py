"""Diagnostico de solo lectura contra la cuenta real: saldo, posiciones y ordenes.

python tools/check_account.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tradedesk import creds  # noqa: E402
from tradedesk.mexc import Mexc, MexcError  # noqa: E402


def show(titulo, fn):
    print(f"\n=== {titulo} ===")
    try:
        print(json.dumps(fn(), indent=2, ensure_ascii=False)[:3000])
    except MexcError as e:
        print("ERROR:", e)
    except Exception as e:
        print("ERROR INESPERADO:", type(e).__name__, e)


def main():
    key, secret = creds.load("mexc")
    print("key guardada:", bool(key), "| secret guardado:", bool(secret))
    if not key:
        raise SystemExit("NO HAY KEY GUARDADA en el Credential Manager.")

    mx = Mexc(key, secret)
    show("saldo", mx.assets)
    show("posiciones abiertas", mx.positions)
    show("ordenes abiertas", mx.open_orders)
    show("historial de ordenes", lambda: mx.history(20))


if __name__ == "__main__":
    main()
