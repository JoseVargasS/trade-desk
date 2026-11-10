"""Comportamiento reutilizable de Trade Desk."""

import threading
import time

from . import theme as t
from .bingx_comun import es_condicional
from .mexc import MexcError, es_editable
from .ritmo import en_paralelo


class OrdenesMixin:
    def cancelar(self, order):
        """Cancelar una orden abierta. Es gestion de riesgo: pasa con DRY-RUN."""
        side = int(order.get("side") or 0)
        rows = [
            ("Par", order.get("_name") or order.get("symbol")),
            ("Lado", "LONG" if side in (1, 4) else "SHORT"),
            ("Tipo", "Límite" if int(order.get("orderType") or 0) == 1 else "Mercado"),
            ("Precio", t.fmt_price_exact(order.get("price"), order.get("_priceScale") or 2)),
            ("Contratos", t.fmt_qty(order.get("vol"))),
        ]
        if not self.port.confirm(
            "Cancelar orden",
            rows=rows,
            warn="Deja de estar en el libro. Si se llenó mientras confirmabas,\n"
            "ya no se puede cancelar: aparece como posición.",
            danger=True,
            ok="Cancelar orden",
        ):
            return
        threading.Thread(
            target=self._cancel_varios,
            args=({order.get("_exchange") or "mexc": [order.get("orderId")]},),
            daemon=True,
        ).start()

    def cancelar_todo(self, orders):
        if not orders:
            self.port.status("No hay órdenes pendientes.")
            return
        rows = [
            (
                o.get("_name") or o.get("symbol"),
                f"{t.fmt_price_exact(o.get('price'), o.get('_priceScale') or 2)} · "
                f"{t.fmt_qty(o.get('vol'))} contratos",
            )
            for o in orders
        ]
        if not self.port.confirm(
            f"Cancelar {len(orders)} orden(es)",
            rows=rows,
            warn="Se cancelan TODAS las órdenes abiertas.",
            danger=True,
            ok="Cancelar todas",
        ):
            return
        grupos = {}
        for orden in orders:
            grupos.setdefault(orden.get("_exchange") or "mexc", []).append(orden.get("orderId"))
        threading.Thread(target=self._cancel_varios, args=(grupos,), daemon=True).start()

    def _cancel_varios(self, grupos):
        """Cancela por broker: Bitunix necesita el símbolo y MEXC no."""

        def cancelar(par):
            nombre, ids = par
            try:
                cliente = self._cliente_de(nombre)
                cliente.cancel(ids)
                self.session.log(f"OK  canceladas {nombre} {ids}")
                self.q.put(("status", f"{len(ids)} orden(es) cancelada(s) en {nombre}."))
            except Exception as exc:
                self.session.log(f"ERR cancelar {nombre}: {type(exc).__name__}")
                self.q.put(("error", f"Error al cancelar en {nombre}: {exc}"))

        # los brokers van a la vez: cada uno tiene su propio límite
        en_paralelo(cancelar, list(grupos.items()), 3)
        self.session.refresh_orders()

    def modificar(self, order):
        """Editar una orden.

        MEXC no deja modificarla: se cancela y se reenvía. Bitunix tiene
        `modify_order` nativo, así que ahí se cambia en el lugar (sin ventana de
        riesgo). Reenviar es abrir una orden: DRY-RUN lo frena.
        """
        if not es_editable(order):
            self.port.status("Una orden de cierre solo se puede cancelar.")
            return
        if es_condicional(order):
            self.port.status("Las condicionales TP/SL de BingX se gestionan desde Posiciones.")
            return
        if self.dry():
            self.port.status("DRY-RUN: no se reenvía la orden modificada")
            return
        symbol = order.get("symbol")
        exchange = order.get("_exchange") or "mexc"
        try:
            cliente = self.broker_de(order)
            contract = (
                cliente.contract(symbol)
                if exchange in ("bitunix", "bingx")
                else self.session.contract_for(symbol)
            )
        except Exception as exc:
            self.port.status(f"No se pudo cargar el contrato de {symbol}: {exc}")
            return
        if not contract:
            self.port.status(f"Falta el contrato de {symbol}: espera a que cargue el catálogo.")
            return

        def to_vol(notional, price):
            # contrato ya cacheado: el editor no pide nada a la red
            if exchange == "mexc":
                return cliente.size_to_vol(symbol, notional, price, contract)
            return cliente.size_to_qty(symbol, notional, price)

        form = self.port.editar_orden(order, contract, to_vol)
        if not form:
            return
        threading.Thread(target=self._replace_worker, args=(order, form), daemon=True).start()

    def _replace_worker(self, order, form):
        symbol = order.get("symbol")
        es_bnx = (order.get("_exchange") or "mexc") == "bitunix"
        try:
            cliente = self.broker_de(order)
            if es_bnx:
                # nativo: no hay ventana entre cancelar y reenviar
                cliente.modify_order(order, form)
                self.session.log(f"OK  modificada {symbol} (bitunix) vol={form['vol']}")
                self.q.put(("closed", f"Orden modificada · {symbol}"))
            else:
                cliente.cancel([order["orderId"]])
                # el cancel es asincrono: reenviar de inmediato puede tocar el margen
                # que el broker todavia tiene reservado para la orden vieja
                if not self._wait_order_gone(order["orderId"], cliente=cliente):
                    raise MexcError(
                        "El broker todavía no liberó la orden anterior. Reintenta en un segundo."
                    )
                cliente.open_market(
                    symbol,
                    form["side"],
                    form["notional"],
                    form["lev"],
                    int(order.get("openType") or 1),
                    form["tp"],
                    form["sl"],
                    form["price"],
                )
            self.session.log(
                f"OK  reenviada {symbol} {form['side']} vol={form['vol']} "
                f"px={form['price']} lev={form['lev']} mrg={form['margin']}"
            )
            self.q.put(("closed", f"Orden reenviada · {symbol}"))
        except Exception as e:
            self.session.log(f"ERR modificar {symbol}: {e}")
            self.q.put(("closed", f"Error al modificar: {e}"))
            self.q.put(
                (
                    "notice",
                    (
                        "No se pudo reenviar",
                        f"{e}\n\nLa orden anterior ya se canceló: revisa la pestaña Órdenes.",
                        True,
                    ),
                )
            )
        self.session.refresh_orders()

    def _wait_order_gone(self, order_id, timeout=2.0, cliente=None):
        """Espera a que la orden cancelada desaparezca de `open_orders`.

        Sondear cada 0,5 s: son 4 consultas como máximo, contra las 8 que
        salen con 0,35 s.
        """
        dueno = cliente or self.mx
        fin = time.time() + timeout
        while time.time() < fin:
            try:
                abiertas = dueno.open_orders()
            except Exception:
                return False
            if all(str(o.get("orderId")) != str(order_id) for o in abiertas):
                return True
            time.sleep(0.5)
        return False

    def margen(self, pos):
        if int(pos.get("openType") or 1) != 1:
            self.port.status("El margen solo se ajusta en modo aislado.")
            return
        # añadir margen tambien es gestion de riesgo: no lo bloquea DRY-RUN
        res = self.port.form(
            f"Añadir margen · {pos.get('symbol')}",
            [("amount", "Monto (USDT)", "")],
            nota=f"Margen actual {t.fmt_usdt(pos.get('im'))} USDT",
            ok="Añadir",
        )
        if res is None:
            return
        try:
            amount = float(res["amount"])
        except ValueError:
            self.port.show("Numero invalido", "El monto debe ser un numero.")
            return
        if amount <= 0:
            self.port.show("Monto invalido", "El monto debe ser mayor a 0.")
            return
        threading.Thread(target=self._margin_worker, args=(pos, amount), daemon=True).start()

    def _margin_worker(self, pos, amount):
        try:
            cliente = self.broker_de(pos)
            cliente.change_margin(
                pos["positionId"],
                amount,
                "ADD",
                simbolo=pos.get("symbol"),
                side=int(pos.get("positionType") or 1) == 1,
            )
            self.session.log(f"OK  margen +{amount} {pos.get('symbol')}")
            self.q.put(("closed", f"Margen añadido · {pos.get('symbol')}"))
        except Exception as e:
            self.session.log(f"ERR margen {pos.get('symbol')}: {e}")
            self.q.put(("closed", f"Error margen: {e}"))
        self.session.refresh_positions()
