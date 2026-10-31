"""Self-check contra la API real de MEXC (publica, sin key): precio, contrato
y conversion USDT -> contratos. No envia ordenes.

    python tools/smoke_api.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tradedesk.mexc import Mexc, MexcError  # noqa: E402


def main():
    m = Mexc()
    px = m.price("BTC_USDT")
    c = m.contract("BTC_USDT")
    print(
        f"BTC_USDT precio={px} contractSize={c['contractSize']} "
        f"volUnit={c['volUnit']} minVol={c['minVol']}"
    )

    # 1000 USDT nocionales deben dar el vol esperado, nunca mas
    vol = m.size_to_vol("BTC_USDT", 1000, px)
    real = m.vol_to_usdt("BTC_USDT", vol, px)
    assert 0 < real <= 1000, f"nocional {real} excede 1000"
    assert real > 1000 - m.vol_to_usdt("BTC_USDT", float(c["volUnit"]), px), (
        "redondeo demasiado conservador"
    )
    print(f"1000 USDT -> {vol} contratos = {real:.2f} USDT reales")

    # un tamano imposible debe fallar, no devolver 0 silencioso
    try:
        m.size_to_vol("BTC_USDT", 0.01, px)
    except MexcError as e:
        print(f"rechazo correcto: {e}")
    else:
        raise SystemExit("FALLO: tamano minimo no fue rechazado")

    print("OK")


if __name__ == "__main__":
    main()
