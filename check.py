"""Diagnostico: que ve realmente la API de tu cuenta. Solo lectura."""
import json
import sys

import creds
from mexc import Mexc, MexcError

key, secret = creds.load("mexc")
print("key guardada:", bool(key), "| secret guardado:", bool(secret))
if not key:
    print("NO HAY KEY GUARDADA en el Credential Manager.")
    sys.exit(1)

mx = Mexc(key, secret)


def show(titulo, fn):
    print(f"\n=== {titulo} ===")
    try:
        data = fn()
        print(json.dumps(data, indent=2, ensure_ascii=False)[:3000])
    except MexcError as e:
        print("ERROR:", e)
    except Exception as e:
        print("ERROR INESPERADO:", type(e).__name__, e)


show("saldo", lambda: mx.assets())
show("posiciones abiertas", lambda: mx.positions())
show("ordenes abiertas", lambda: mx._get("/api/v1/private/order/list/open_orders", {"page_num": 1, "page_size": 20}))
show("historial de ordenes", lambda: mx._get("/api/v1/private/order/list/history_orders", {"page_num": 1, "page_size": 20}))
