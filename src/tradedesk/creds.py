"""Credenciales en el Administrador de credenciales de Windows.

Las variables de entorno MEXC_KEY / MEXC_SECRET sirven de respaldo.
"""

import os

import keyring

SERVICE = "trade-desk"


def load(exchange):
    key = keyring.get_password(SERVICE, f"{exchange}.key")
    secret = keyring.get_password(SERVICE, f"{exchange}.secret")
    if not key:
        key = os.environ.get(f"{exchange.upper()}_KEY", "")
        secret = os.environ.get(f"{exchange.upper()}_SECRET", "")
    return key or "", secret or ""


def save(exchange, key, secret):
    keyring.set_password(SERVICE, f"{exchange}.key", key)
    keyring.set_password(SERVICE, f"{exchange}.secret", secret)


def has(exchange):
    key, secret = load(exchange)
    return bool(key and secret)
