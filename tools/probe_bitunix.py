"""Prueba de lectura contra Bitunix: fija endpoints y forma de las respuestas.

No manda ninguna orden. Uso:

    python tools/probe_bitunix.py             # endpoints publicos
    python tools/probe_bitunix.py --privado   # ademas los privados (pide claves)
"""

import argparse
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import httpx

from tradedesk import creds

BASE = "https://fapi.bitunix.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def firma(key, secret, params="", cuerpo=""):
    nonce = uuid.uuid4().hex
    estamp = str(int(time.time() * 1000))
    digest = hashlib.sha256(f"{nonce}{estamp}{key}{params}{cuerpo}".encode()).hexdigest()
    sign = hashlib.sha256((digest + secret).encode()).hexdigest()
    return {
        "api-key": key,
        "nonce": nonce,
        "timestamp": estamp,
        "sign": sign,
        "Content-Type": "application/json",
        "User-Agent": UA,
    }


def probar(cliente, ruta, params=None, key="", secret=""):
    params = params or {}
    orden = "&".join(f"{k}={params[k]}" for k in sorted(params))
    cabeceras = firma(key, secret, orden, "") if key else {}
    try:
        respuesta = cliente.get(BASE + ruta, params=params, headers=cabeceras)
        datos = respuesta.json()
    except Exception as exc:
        print(f"ERR {ruta} {params} -> {type(exc).__name__}: {exc}")
        return
    codigo = datos.get("code")
    cuerpo = datos.get("data")
    bien = codigo in (0, "0")
    print(f"{'OK ' if bien else 'ERR'} {ruta} {params} -> code={codigo} msg={datos.get('msg')}")
    if bien and cuerpo is not None:
        texto = json.dumps(cuerpo, ensure_ascii=False)
        print("    data:", texto[:400])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--privado", action="store_true")
    args = ap.parse_args()
    key, secret = creds.load("bitunix")
    print("claves de bitunix guardadas:", bool(key and secret))
    with httpx.Client(timeout=15.0, headers={"User-Agent": UA}) as cliente:
        print("\n== publicos ==")
        probar(cliente, "/api/v1/futures/market/tickers", {"symbols": "BTCUSDT"})
        probar(cliente, "/api/v1/futures/market/tickers")
        for ruta in (
            "/api/v1/futures/market/contract_info",
            "/api/v1/futures/market/contracts",
        ):
            probar(cliente, ruta, {"symbols": "BTCUSDT"})
        if args.privado and key and secret:
            print("\n== privados ==")
            for ruta in (
                "/api/v1/futures/position/get_pending_positions",
                "/api/v1/futures/trade/get_pending_orders",
                "/api/v1/futures/tpsl/get_pending_orders",
                "/api/v1/futures/account",
            ):
                probar(cliente, ruta, {}, key=key, secret=secret)
        else:
            print("\n(privados: guarda las claves y volve a correr con --privado)")


if __name__ == "__main__":
    main()
