"""Cuentas del historial, fuera de la vista.

Una operación cerrada tiene PnL realizado y una fee ya cobrada (que puede ser un
rebate, con signo negativo). El neto es la resta, con el mismo criterio para los
tres brokers: lo que queda en la cuenta después de la comisión.
"""


def neto_operacion(pnl, fee):
    """PnL realizado menos la fee cobrada. Rebate (fee < 0) suma."""
    return float(pnl or 0) - float(fee or 0)


__all__ = ["neto_operacion"]
