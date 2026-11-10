"""Envío de varias órdenes con una confirmación: los brokers en paralelo."""

import threading

from .ritmo import en_paralelo


def resumen_lote(resultados, dry):
    """(titulo, mensaje, hay_problema) para el único aviso de un lote."""
    resultados = list(resultados or ())
    hay_problema = any(estado != "ok" for _symbol, _side, estado, _aviso in resultados)
    if dry:
        titulo = "DRY-RUN: no se envio nada"
        lineas = [f"Se simularon {len(resultados)} ordenes; ninguna se envio."]
    else:
        titulo = "Lote con problemas" if hay_problema else "Lote enviado"
        lineas = []

    for symbol, side, estado, aviso in resultados:
        if dry and estado == "ok":
            linea = f"✓ {symbol} {side}: simulada (no enviada)"
        elif estado == "ok":
            linea = f"✓ {symbol} {side}: enviada"
        elif estado == "desconocida":
            linea = (
                f"? {symbol} {side}: estado desconocido, revisa Posiciones y Órdenes "
                "antes de reintentar"
            )
        else:
            linea = f"✗ {symbol} {side}: {str(aviso).replace(chr(10), ' ')}"
        lineas.append(linea)
    return titulo, "\n".join(lineas), hay_problema


class LoteMixin:
    def abrir_lote(self, items, al_enviar=None, omitidos=()):
        """Confirma una vez y procesa en orden el lote completo."""
        items = list(items or ())
        if not items:
            return False
        dry = bool(self.dry())
        rows = [
            (
                f"{item['side']} {item['form']['symbol']}",
                f"{item['form']['size']:,.2f} USDT · {item['form']['lev']}x "
                f"{item['form']['margin_mode']} · {item['exchange']}",
            )
            for item in items
        ]
        total = sum(float(item["form"]["notional"]) for item in items)
        rows.append(("Nocional total", f"{total:,.2f} USDT"))
        warn = (
            "DRY-RUN: no se enviara nada."
            if dry
            else f"ESTO ES REAL: se envian {len(items)} ordenes"
        )
        if omitidos:
            warn += "\nSe omitieron: " + "; ".join(omitidos)
        if not self.port.confirm(
            f"Confirmar {len(items)} ordenes",
            rows=rows,
            warn=warn,
            danger=not dry,
            ok=f"ENVIAR {len(items)}",
        ):
            return False
        if al_enviar:
            al_enviar()
        threading.Thread(
            target=self._do_abrir_lote,
            args=(items, dry),
            daemon=True,
        ).start()
        return True

    def _do_abrir_lote(self, items, dry):
        items = list(items or ())
        resultados = []

        def enviar_una(indice, item):
            salida = []
            try:
                self._do_abrir(
                    item["side"],
                    item["form"],
                    dry,
                    item["exchange"],
                    lote=salida,
                    refrescar=False,
                )
            except Exception as exc:
                self.session.log(f"ERR lote {item['side']} {item['form']['symbol']}: {exc}")
                salida.append((item["form"]["symbol"], item["side"], "rechazada", str(exc)))
            return indice, salida

        def enviar_broker(grupo):
            return [enviar_una(indice, item) for indice, item in grupo]

        try:
            por_broker = {}
            for indice, item in enumerate(items):
                por_broker.setdefault(item["exchange"], []).append((indice, item))
            # Los brokers salen a la vez (cada uno con su límite). Dentro de un
            # broker van en orden: ahí sí comparten ticker, apalancamiento y ordenes.
            salidas = en_paralelo(enviar_broker, list(por_broker.values()), 3)
            # el resumen se arma por índice de tarjeta, no por orden de llegada
            ordenadas = [salida for grupo in salidas for salida in grupo]
            resultados = [fila for _indice, salida in sorted(ordenadas) for fila in salida]
        finally:
            # el aviso sale primero: el refresco puede tardar y las órdenes ya se mandaron
            self.q.put(("lote", {"dry": dry, "resultados": resultados}))
            self.session.refresh_positions()
            self.session.refresh_orders()
