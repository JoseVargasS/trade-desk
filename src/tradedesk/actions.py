"""Acciones sobre posiciones: cerrar, reverse, TP/SL y margen.

Se mezcla en App (mixin) porque todo depende de su estado: cliente, cola, tabla.
"""

import threading
import time

from . import dialog
from . import theme as t
from .mexc import MexcError, close_vol, decorate_orders, plan_tp_sl
from .orders import edit_order, es_editable


class ActionsMixin:
    # ------------------------------------------------------------------ cierres
    def _close_position(self, pos, info=None):
        if self.var_dry.get():
            self._status(f"DRY-RUN: no se cerro {pos.get('symbol')}")
            return
        info = info or {}
        pct = float(info.get("pct") or 100)
        price = info.get("price") or None
        vol = close_vol(pos.get("holdVol"), pct)
        if vol < 1:
            dialog.show(
                self.root,
                "Cantidad invalida",
                f"Ese {pct:.0f}% deja 0 contratos: la posicion tiene "
                f"{t.fmt_qty(pos.get('holdVol'))}. Sube el porcentaje.",
            )
            return
        tipo = (
            f"Límite {t.fmt_price_exact(price, pos.get('_priceScale') or 2)}"
            if price
            else "Mercado"
        )
        rows = [
            ("Par", pos.get("symbol")),
            ("Lado", "LONG" if int(pos.get("positionType") or 1) == 1 else "SHORT"),
            ("Tipo", tipo),
            ("Cerrar", f"{pct:.0f}% · {t.fmt_qty(vol)} contratos"),
            ("PnL", t.fmt_pnl(pos.get("unRealizedPnl"))),
        ]
        if pct < 100:
            rows.append(("Queda", f"{100 - pct:.0f}% abierto"))
        warn = "Orden límite: puede quedar sin llenar." if price else "Se cierra a mercado."
        if not dialog.confirm(
            self.root, "Cerrar posicion", rows=rows, warn=warn, danger=True, ok_text="Cerrar"
        ):
            return
        threading.Thread(
            target=self._do_close, args=([pos],), kwargs={"vol": vol, "price": price}, daemon=True
        ).start()

    def _close_selected(self):
        positions = self.table.selected()
        if not positions:
            self._status("Marca al menos una posicion con el checkbox.")
            return
        if self.var_dry.get():
            self._status(f"DRY-RUN: no se cerro {len(positions)} posicion(es)")
            return
        if not dialog.confirm(
            self.root,
            f"Cerrar {len(positions)} posicion(es)",
            rows=[(p.get("symbol"), t.fmt_qty(p.get("holdVol"))) for p in positions],
            warn="Se cierran a mercado.",
            danger=True,
            ok_text="Cerrar",
        ):
            return
        threading.Thread(target=self._do_close, args=(positions,), daemon=True).start()

    def _do_close(self, positions, vol=None, price=None):
        failed, done = [], 0
        single = len(positions) == 1  # solo el cierre de una fila lleva vol/precio
        for i, pos in enumerate(positions):
            try:
                self.mx.close_position(pos, vol if single else None, price if single else None)
                done += 1
                self._log(
                    f"OK  cerrada {pos.get('symbol')} vol={vol or pos.get('holdVol')}"
                    f"{' limite ' + str(price) if price else ''}"
                )
            except Exception as e:
                failed.append(f"{pos.get('symbol')}: {e}")
                self._log(f"ERR cerrar {pos.get('symbol')}: {e}")
            if i < len(positions) - 1:
                time.sleep(0.6)
        msg = f"Cerradas {done}" + (f" · fallaron {len(failed)}" if failed else "")
        self.q.put(("closed", msg))
        if failed:
            self.q.put(("status", " | ".join(failed)))
        self._refresh_positions()

    def _reverse_position(self, pos):
        if self.var_dry.get():
            self._status(f"DRY-RUN: no se revirtio {pos.get('symbol')}")
            return
        if not dialog.confirm(
            self.root,
            "Reverse",
            rows=[
                ("Par", pos.get("symbol")),
                ("Lado actual", "LONG" if int(pos.get("positionType") or 1) == 1 else "SHORT"),
                ("Qty", t.fmt_qty(pos.get("holdVol"))),
            ],
            warn="Cierra la posicion y abre la contraria, al mercado.",
            danger=True,
            ok_text="Reverse",
        ):
            return

        def run():
            try:
                self.mx.reverse(pos)
                self._log(f"OK  reverse {pos.get('symbol')} vol={pos.get('holdVol')}")
                self.q.put(("closed", f"Revertida {pos.get('symbol')}"))
            except Exception as e:
                self._log(f"ERR reverse {pos.get('symbol')}: {e}")
                self.q.put(("closed", f"Error reverse: {e}"))
            self._refresh_positions()

        threading.Thread(target=run, daemon=True).start()

    def _close_all(self):
        if self.var_dry.get():
            self._status("DRY-RUN: no se cerro nada")
            return
        if not dialog.confirm(
            self.root,
            "Cerrar TODO",
            rows=[("Posiciones", self.table.checked_count() or "todas")],
            warn="Se cierran TODAS las posiciones a mercado.\nNo se puede deshacer.",
            danger=True,
            ok_text="Cerrar todo",
        ):
            return

        def run():
            try:
                self.mx.close_all()
                self._log("OK  close_all")
                self.q.put(("closed", "Todas las posiciones cerradas"))
            except Exception as e:
                self._log(f"ERR close_all: {e}")
                self.q.put(("closed", f"Error: {e}"))
            self._refresh_positions()

        threading.Thread(target=run, daemon=True).start()

    # --------------------------------------------------------------- tp/sl
    def _edit_tpsl(self, pos):
        # el TP/SL es gestion de riesgo: se permite aunque DRY-RUN este activo
        price = (self._prices or {}).get(pos.get("symbol")) or 0
        long_ = int(pos.get("positionType") or 1) == 1
        lado = ("SL debajo" if long_ else "SL arriba") if price else "SL en contra"
        res = dialog.form(
            self.root,
            f"TP / SL · {pos.get('symbol')}",
            [
                ("tp", "Take profit", pos.get("_tp") or ""),
                ("sl", "Stop loss", pos.get("_sl") or ""),
            ],
            ok_text="Guardar",
            note=f"Qty {t.fmt_qty(pos.get('holdVol'))} contratos · "
            f"precio actual {t.fmt_price(price) if price else '—'} ({lado})",
        )
        if res is None:
            return
        try:
            tp = float(res["tp"]) if res["tp"] else None
            sl = float(res["sl"]) if res["sl"] else None
        except ValueError:
            dialog.show(self.root, "Numero invalido", "TP y SL deben ser numeros o quedar vacios.")
            return
        threading.Thread(target=self._tpsl_worker, args=(pos, tp, sl), daemon=True).start()

    def _tpsl_worker(self, pos, tp, sl):
        symbol = pos.get("symbol")
        try:
            price = self.mx.price(symbol)
            long_ = int(pos.get("positionType") or 1) == 1
            # MEXC mide la direccion contra el precio actual, no contra la entrada
            tp, sl, avisos = plan_tp_sl(long_, price, tp, sl)
            if pos.get("_tpsl_id"):
                try:
                    self.mx.tpsl_cancel(pos["_tpsl_id"])
                except MexcError as e:
                    if "ya no existe" not in str(e):
                        raise
                # el cancel es asincrono: recolocar de inmediato da 5004
                if not self._wait_tpsl_clear(pos["positionId"]):
                    raise MexcError(
                        "MEXC todavia esta cancelando la orden anterior. Reintenta en un segundo."
                    )
            if tp or sl:
                self.mx.tpsl_place(pos["positionId"], pos["holdVol"], tp, sl)
            self._log(f"OK  tpsl {symbol} tp={tp} sl={sl}")
            msg = f"TP/SL actualizado · {symbol}"
            self.q.put(("closed", msg))
            if avisos:
                self.q.put(("notice", ("SL en ganancia", "\n\n".join(avisos), False)))
        except Exception as e:
            self._log(f"ERR tpsl {symbol}: {e}")
            self.q.put(("closed", f"Error TP/SL: {e}"))
            self.q.put(("notice", ("TP / SL rechazado", str(e), True)))
        self._refresh_positions()

    def _wait_tpsl_clear(self, position_id, timeout=2.5):
        """Espera a que MEXC suelte el TP/SL cancelado de esa posicion."""
        end = time.time() + timeout
        while time.time() < end:
            try:
                pendientes = [
                    o
                    for o in self.mx.tpsl_list()
                    if int(o.get("positionId") or 0) == int(position_id)
                ]
            except Exception:
                pendientes = []
            if not pendientes:
                return True
            time.sleep(0.25)
        return False

    # -------------------------------------------------------- ordenes abiertas
    def _cancel_order(self, order):
        """Cancelar una orden abierta. Es gestion de riesgo: pasa con DRY-RUN."""
        side = int(order.get("side") or 0)
        rows = [
            ("Par", order.get("_name") or order.get("symbol")),
            ("Lado", "LONG" if side in (1, 4) else "SHORT"),
            ("Tipo", "Límite" if int(order.get("orderType") or 0) == 1 else "Mercado"),
            ("Precio", t.fmt_price_exact(order.get("price"), order.get("_priceScale") or 2)),
            ("Contratos", t.fmt_qty(order.get("vol"))),
        ]
        if not dialog.confirm(
            self.root,
            "Cancelar orden",
            rows=rows,
            warn="Deja de estar en el libro. Si se llenó mientras confirmabas,\n"
            "ya no se puede cancelar: aparece como posición.",
            danger=True,
            ok_text="Cancelar orden",
        ):
            return
        threading.Thread(
            target=self._cancel_orders_worker, args=([order.get("orderId")],), daemon=True
        ).start()

    def _cancel_all_orders(self):
        orders = self.orders.all()
        if not orders:
            self._status("No hay órdenes pendientes.")
            return
        rows = [
            (
                o.get("_name") or o.get("symbol"),
                f"{t.fmt_price_exact(o.get('price'), o.get('_priceScale') or 2)} · "
                f"{t.fmt_qty(o.get('vol'))} contratos",
            )
            for o in orders
        ]
        if not dialog.confirm(
            self.root,
            f"Cancelar {len(orders)} orden(es)",
            rows=rows,
            warn="Se cancelan TODAS las órdenes abiertas.",
            danger=True,
            ok_text="Cancelar todas",
        ):
            return
        threading.Thread(
            target=self._cancel_orders_worker,
            args=([o.get("orderId") for o in orders],),
            daemon=True,
        ).start()

    def _modify_order(self, order):
        """Editar una orden. MEXC no deja modificarla: se cancela y se reenvía.

        Reenviar es abrir una orden, así que DRY-RUN lo frena. La orden de cierre
        (lado 2/4) no se puede reenviar así: solo cancelar.
        """
        if not es_editable(order):
            self._status("Una orden de cierre solo se puede cancelar.")
            return
        if self.var_dry.get():
            self._status("DRY-RUN: no se reenvía la orden modificada")
            return
        symbol = order.get("symbol")
        contract = self._contract_for(symbol)
        if not contract:
            self._status(f"Falta el contrato de {symbol}: espera a que cargue el catálogo.")
            return

        def to_vol(notional, price):
            # contrato ya cacheado: el editor no pide nada a la red
            return self.mx.size_to_vol(symbol, notional, price, contract)

        form = edit_order(self.root, order, contract, to_vol)
        if not form:
            return
        threading.Thread(target=self._replace_order_worker, args=(order, form), daemon=True).start()

    def _replace_order_worker(self, order, form):
        symbol = order.get("symbol")
        try:
            self.mx.cancel([order["orderId"]])
            # el cancel es asincrono: reenviar de inmediato puede tocar el margen
            # que MEXC todavia tiene reservado para la orden vieja
            if not self._wait_order_gone(order["orderId"]):
                raise MexcError(
                    "MEXC todavía no liberó la orden anterior. Reintenta en un segundo."
                )
            self.mx.open_market(
                symbol,
                form["side"],
                form["notional"],
                form["lev"],
                int(order.get("openType") or 1),
                form["tp"],
                form["sl"],
                form["price"],
            )
            self._log(
                f"OK  reenviada {symbol} {form['side']} vol={form['vol']} "
                f"px={form['price']} lev={form['lev']} mrg={form['margin']}"
            )
            self.q.put(("closed", f"Orden reenviada · {symbol}"))
        except Exception as e:
            self._log(f"ERR modificar {symbol}: {e}")
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
        self._refresh_orders()

    def _wait_order_gone(self, order_id, timeout=2.5):
        """Espera a que la orden cancelada desaparezca de `open_orders`."""
        fin = time.time() + timeout
        while time.time() < fin:
            try:
                abiertas = self.mx.open_orders()
            except Exception:
                return False
            if all(str(o.get("orderId")) != str(order_id) for o in abiertas):
                return True
            time.sleep(0.35)
        return False

    def _cancel_orders_worker(self, ids):
        try:
            self.mx.cancel(ids)
            self._log(f"OK  cancel {len(ids)} orden(es) {ids}")
            if len(ids) == 1:
                self.q.put(("closed", "Orden cancelada"))
            else:
                self.q.put(("closed", f"{len(ids)} órdenes canceladas"))
        except Exception as e:
            self._log(f"ERR cancel {ids}: {e}")
            self.q.put(("closed", f"Error al cancelar: {e}"))
            self.q.put(("notice", ("No se pudo cancelar", str(e), True)))
        self._refresh_orders()

    def _refresh_orders(self):
        try:
            self.q.put(("orders", decorate_orders(self.mx, self.mx.open_orders())))
        except Exception as e:
            self.q.put(("status", f"ordenes: {e}"))

    # ---------------------------------------------------------------- margen
    def _add_margin(self, pos):
        if int(pos.get("openType") or 1) != 1:
            self._status("El margen solo se ajusta en modo aislado.")
            return
        # añadir margen tambien es gestion de riesgo: no lo bloquea DRY-RUN
        res = dialog.form(
            self.root,
            f"Añadir margen · {pos.get('symbol')}",
            [("amount", "Monto (USDT)", "")],
            ok_text="Añadir",
            note=f"Margen actual {t.fmt_usdt(pos.get('im'))} USDT",
        )
        if res is None:
            return
        try:
            amount = float(res["amount"])
        except ValueError:
            dialog.show(self.root, "Numero invalido", "El monto debe ser un numero.")
            return
        if amount <= 0:
            dialog.show(self.root, "Monto invalido", "El monto debe ser mayor a 0.")
            return
        threading.Thread(target=self._margin_worker, args=(pos, amount), daemon=True).start()

    def _margin_worker(self, pos, amount):
        try:
            self.mx.change_margin(pos["positionId"], amount, "ADD")
            self._log(f"OK  margen +{amount} {pos.get('symbol')}")
            self.q.put(("closed", f"Margen añadido · {pos.get('symbol')}"))
        except Exception as e:
            self._log(f"ERR margen {pos.get('symbol')}: {e}")
            self.q.put(("closed", f"Error margen: {e}"))
        self._refresh_positions()
