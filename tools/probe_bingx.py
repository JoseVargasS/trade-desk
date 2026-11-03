"""Prueba de lectura contra BingX: fija endpoints y forma de las respuestas.

No manda ninguna orden. Uso:

    python tools/probe_bingx.py             # endpoints publicos
    python tools/probe_bingx.py --privado   # ademas los privados (pide claves)

BingX responde **HTTP 200 tambien con error**: el resultado real esta en `code`
(0 = bien) y el mensaje en `msg`.
"""

import argparse
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import httpx

from tradedesk import creds

BASE = "https://open-api.bingx.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def firma(secret, params):
    """BingX v2: params ordenados + timestamp, firmados con HMAC-SHA256."""
    orden = sorted(params.items())
    orden.append(("timestamp", str(int(time.time() * 1000))))
    consulta = "&".join(f"{clave}={valor}" for clave, valor in orden)
    sign = hmac.new(secret.encode(), consulta.encode(), hashlib.sha256).hexdigest()
    return dict(orden), sign


def muestra(datos):
    if isinstance(datos, list):
        if not datos:
            return "[]"
        primera = datos[0]
        if isinstance(primera, dict):
            return f"lista de {len(datos)}; campos: {sorted(primera.keys())}"
        return f"lista de {len(datos)}: {json.dumps(primera, ensure_ascii=False)[:120]}"
    if isinstance(datos, dict):
        return f"dict; campos: {sorted(datos.keys())}"
    return json.dumps(datos, ensure_ascii=False)[:200]


def probar(cliente, ruta, params=None, key="", secret=""):
    params = {clave: valor for clave, valor in (params or {}).items() if valor is not None}
    cabeceras = {}
    if key and secret:
        params, sign = firma(secret, params)
        cabeceras = {"X-BX-APIKEY": key, "User-Agent": UA}
        cabeceras["X-BX-SIGN"] = sign
    try:
        respuesta = cliente.get(BASE + ruta, params=params, headers=cabeceras)
        datos = respuesta.json()
    except Exception as exc:
        print(f"ERR {ruta} {params} -> {type(exc).__name__}: {exc}")
        return
    codigo = datos.get("code")
    cuerpo = datos.get("data")
    bien = str(codigo) == "0"
    visto = f" {params}" if not key else ""
    print(f"{'OK ' if bien else 'ERR'} {ruta}{visto} -> code={codigo} msg={datos.get('msg')}")
    if bien and cuerpo is not None:
        print("    data:", muestra(cuerpo))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--privado", action="store_true")
    ap.add_argument("--par", default="BTC-USDT")
    args = ap.parse_args()
    key, secret = creds.load("bingx")
    print("claves de bingx guardadas:", bool(key and secret))
    with httpx.Client(
        timeout=15.0,
        headers={"User-Agent": UA},
        transport=httpx.HTTPTransport(local_address="0.0.0.0"),
    ) as cliente:
        print("\n== publicos ==")
        probar(cliente, "/openApi/swap/v2/quote/ticker", {"symbol": args.par})
        probar(cliente, "/openApi/swap/v2/quote/contracts", {})
        probar(
            cliente,
            "/openApi/swap/v2/quote/klines",
            {"symbol": args.par, "interval": "1m", "limit": 2},
        )
        probar(cliente, "/openApi/swap/v2/quote/depth", {"symbol": args.par, "limit": 5})
        probar(cliente, "/openApi/swap/v2/quote/trades", {"symbol": args.par, "limit": 2})
        probar(cliente, "/openApi/swap/v1/quote/ticker", {"symbol": args.par})
        if args.privado and key and secret:
            print("\n== privados ==")
            for ruta, params in (
                ("/openApi/swap/v2/user/balance", {}),
                ("/openApi/swap/v2/user/positions", {}),
                ("/openApi/swap/v2/trade/openOrders", {}),
                ("/openApi/swap/v2/trade/allOrders", {"limit": 5}),
                ("/openApi/swap/v2/trade/allFillOrders", {"limit": 5}),
                ("/openApi/swap/v2/user/income", {"limit": 5}),
                ("/openApi/swap/v2/trade/positionMode", {}),
                ("/openApi/swap/v2/trade/marginType", {"symbol": args.par}),
            ):
                probar(cliente, ruta, params, key=key, secret=secret)
        else:
            print("\n(privados: guarda las claves y volve a correr con --privado)")


if __name__ == "__main__":
    main()
