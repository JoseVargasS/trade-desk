"""Casos de uso de la mesa: abrir, cerrar, reverse, TP/SL, margen y órdenes.

No sabe de widgets: habla con `Session` (MEXC y cola) y con un `UiPort`, que es
lo único que cada ventana implementa (confirmar, avisar, formularios, avisos y
barra de estado). Así la app Tk y la vista Qt operan con el mismo código.

Los mensajes que publica en `session.q` son los mismos que ya pinta la app Tk:
`("closed", texto)`, `("status", texto)`, `("notice", (titulo, texto, danger))`,
`("order", (ok, texto))`, `("positions", ...)` y `("orders", ...)`.
"""

import threading
import time

from . import theme as t
from .mexc import (
    MexcError,
    break_even_price,
    close_vol,
    es_editable,
    mark_price,
    plan_tp_sl,
)


class Control:
    """Acciones de la mesa. `dry` es un callable: DRY-RUN siempre arranca prendido."""

    def __init__(self, session, port, dry=None):
        self.session = session
        self.port = port
        self.dry = dry or (lambda: True)

    # --------------------------------------------------------------- utilidades
    @property
    def mx(self):
        return self.session.mx

    @property
    def q(self):
        return self.session.q

    def _escala(self, symbol):
        return int(self.session.contract_for(symbol).get("priceScale") or 2)

    # ------------------------------------------------------------------- abrir
    def abrir(self, side, form, al_enviar=None):
        """Confirma y envía la orden de la tarjeta (mercado o límite)."""
        price = form.get("price")
        px = price or self.session.precios.get(form["symbol"], 0)
        exact = t.fmt_price_exact(px, self._escala(form["symbol"]))
        dry = bool(self.dry())
        rows = [
            ("Par", form["symbol"]),
            ("Tipo", f"Límite {exact}" if price else "Mercado"),
            ("Precio", exact if price else t.fmt_price(px)),
            ("Tamaño", f"{form['size']:,.2f} USDT ({form['size_mode']})"),
            ("Nocional", f"{form['notional']:,.2f} USDT"),
            ("Apalancamiento", f"{form['lev']}x ({form['margin_mode']})"),
            ("TP / SL", f"{form['tp'] or '—'} / {form['sl'] or '—'}"),
        ]
        warn = "DRY-RUN: no se enviara nada." if dry else "ESTO ES REAL"
        if price:
            warn += "\nOrden límite: puede quedar sin llenar."
        if not self.port.confirm(
            f"Confirmar {side}", rows=rows, warn=warn, danger=not dry, ok=side
        ):
            return
        if al_enviar:
            al_enviar()
        threading.Thread(target=self._do_abrir, args=(side, form, dry), daemon=True).start()

    def _do_abrir(self, side, form, dry):
        symbol = form["symbol"]
        try:
            precio = form.get("price")
            if dry:
                px = precio or self.mx.price(symbol)
                vol = self.mx.size_to_vol(symbol, form["notional"], px)
                mensaje = (
                    f"DRY-RUN {side} {t.fmt_qty(vol)} contratos @ {t.fmt_price(px)} (no enviado)"
                )
                self.session.log("OK  " + mensaje)
                self.q.put(("order", (True, mensaje)))
                self.q.put(("closed", mensaje))
                self.q.put(
                    (
                        "notice",
                        (
                            "DRY-RUN: no se envio nada",
                            mensaje + "\n\nApaga DRY-RUN para operar de verdad.",
                            False,
                        ),
                    )
                )
                return
            data, vol, px = self.mx.open_market(
                symbol,
                side,
                form["notional"],
                form["lev"],
                form["open_type"],
                form["tp"],
                form["sl"],
                precio,
            )
            order_id = (data or {}).get("orderId", "?")
            mensaje = (
                f"{side} enviado: {t.fmt_qty(vol)} contratos @ {t.fmt_price(px)} · id {order_id}"
            )
            self.session.log("OK  " + mensaje)
            self.q.put(("order", (True, mensaje)))
            self.q.put(("closed", mensaje))
            self.q.put(("notice", ("Orden enviada", mensaje, False)))
            # una limite sin llenar no abre posicion: hay que refrescar ordenes
            self.session.refresh_positions()
            self.session.refresh_orders()
        except Exception as exc:
            self.session.log(f"ERR {side} {symbol}: {exc}")
            self.q.put(("order", (False, str(exc))))
            self.q.put(("closed", str(exc)))
            self.q.put(("notice", ("Orden rechazada", str(exc), True)))

    # ------------------------------------------------------------------ cierres
    def cerrar(self, pos, info=None):
        if self.dry():
            self.port.status(f"DRY-RUN: no se cerro {pos.get('symbol')}")
            return
        info = info or {}
        pct = float(info.get("pct") or 100)
        price = info.get("price") or None
        vol = close_vol(pos.get("holdVol"), pct)
        if vol < 1:
            self.port.show(
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
        if not self.port.confirm("Cerrar posicion", rows=rows, warn=warn, danger=True, ok="Cerrar"):
            return
        threading.Thread(
            target=self._do_cerrar, args=([pos],), kwargs={"vol": vol, "price": price}, daemon=True
        ).start()

    def cerrar_seleccionadas(self, positions):
        if not positions:
            self.port.status("Marca al menos una posicion con el checkbox.")
            return
        if self.dry():
            self.port.status(f"DRY-RUN: no se cerro {len(positions)} posicion(es)")
            return
        if not self.port.confirm(
            f"Cerrar {len(positions)} posicion(es)",
            rows=[(p.get("symbol"), t.fmt_qty(p.get("holdVol"))) for p in positions],
            warn="Se cierran a mercado.",
            danger=True,
            ok="Cerrar",
        ):
            return
        threading.Thread(target=self._do_cerrar, args=(positions,), daemon=True).start()

    def _do_cerrar(self, positions, vol=None, price=None):
        failed, done = [], 0
        single = len(positions) == 1  # solo el cierre de una fila lleva vol/precio
        for i, pos in enumerate(positions):
            try:
                self.mx.close_position(pos, vol if single else None, price if single else None)
                done += 1
                self.session.log(
                    f"OK  cerrada {pos.get('symbol')} vol={vol or pos.get('holdVol')}"
                    f"{' limite ' + str(price) if price else ''}"
                )
            except Exception as e:
                failed.append(f"{pos.get('symbol')}: {e}")
                self.session.log(f"ERR cerrar {pos.get('symbol')}: {e}")
            if i < len(positions) - 1:
                time.sleep(0.6)
        msg = f"Cerradas {done}" + (f" · fallaron {len(failed)}" if failed else "")
        self.q.put(("closed", msg))
        if failed:
            self.q.put(("status", " | ".join(failed)))
        self.session.refresh_positions()

    def reverse(self, pos):
        if self.dry():
            self.port.status(f"DRY-RUN: no se revirtio {pos.get('symbol')}")
            return
        if not self.port.confirm(
            "Reverse",
            rows=[
                ("Par", pos.get("symbol")),
                ("Lado actual", "LONG" if int(pos.get("positionType") or 1) == 1 else "SHORT"),
                ("Qty", t.fmt_qty(pos.get("holdVol"))),
            ],
            warn="Cierra la posicion y abre la contraria, al mercado.",
            danger=True,
            ok="Reverse",
        ):
            return

        def run():
            try:
                self.mx.reverse(pos)
                self.session.log(f"OK  reverse {pos.get('symbol')} vol={pos.get('holdVol')}")
                self.q.put(("closed", f"Revertida {pos.get('symbol')}"))
            except Exception as e:
                self.session.log(f"ERR reverse {pos.get('symbol')}: {e}")
                self.q.put(("closed", f"Error reverse: {e}"))
            self.session.refresh_positions()

        threading.Thread(target=run, daemon=True).start()

    def cerrar_todo(self, cuantas=0):
        if self.dry():
            self.port.status("DRY-RUN: no se cerro nada")
            return
        if not self.port.confirm(
            "Cerrar TODO",
            rows=[("Posiciones", cuantas or "todas")],
            warn="Se cierran TODAS las posiciones a mercado.\nNo se puede deshacer.",
            danger=True,
            ok="Cerrar todo",
        ):
            return

        def run():
            try:
                self.mx.close_all()
                self.session.log("OK  close_all")
                self.q.put(("closed", "Todas las posiciones cerradas"))
            except Exception as e:
                self.session.log(f"ERR close_all: {e}")
                self.q.put(("closed", f"Error: {e}"))
            self.session.refresh_positions()

        threading.Thread(target=run, daemon=True).start()

    # -------------------------------------------------------------------- tp/sl
    def tpsl(self, pos):
        # el TP/SL es gestion de riesgo: se permite aunque DRY-RUN este activo
        precio = mark_price(pos) or self.session.precios.get(pos.get("symbol")) or 0
        long_ = int(pos.get("positionType") or 1) == 1
        escala = int(pos.get("_priceScale") or 2)

        res = self.port.tpsl(pos, precio)
        if res is None:
            return
        try:
            tp = float(res["tp"].replace(",", "")) if res["tp"] else None
            sl = float(res["sl"].replace(",", "")) if res["sl"] else None
        except ValueError:
            self.port.show("Numero invalido", "TP y SL deben ser numeros o quedar vacios.")
            return
        # medio tick de margen: el campo pudo redondear el texto del break-even
        be, _ = break_even_price(pos, long_)
        es_be = bool(sl and be and abs(sl - be) < 0.5 * 10**-escala)
        threading.Thread(target=self._tpsl_worker, args=(pos, tp, sl, es_be), daemon=True).start()

    def _tpsl_worker(self, pos, tp, sl, es_be=False):
        symbol = pos.get("symbol")
        try:
            price = self.mx.price(symbol)
            long_ = int(pos.get("positionType") or 1) == 1
            if es_be and sl and (sl > price if long_ else sl < price):
                # sin esta guarda plan_tp_sl lo guardaria como TP
                raise MexcError(
                    "El precio se movio y el break-even ya no cubre las comisiones. Reintenta."
                )
            # MEXC mide la direccion contra el precio actual, no contra la entrada
            tp, sl, avisos = plan_tp_sl(long_, price, tp, sl)
            # se cancelan TODOS los stop de la posicion: un id viejo deja duplicados
            ids = [
                o.get("id")
                for o in self.mx.tpsl_list()
                if int(o.get("positionId") or 0) == int(pos["positionId"])
            ]
            for stop_id in [i for i in ids if i]:
                try:
                    self.mx.tpsl_cancel(stop_id)
                except MexcError as e:
                    if "ya no existe" not in str(e):
                        raise
            # el cancel es asincrono: recolocar de inmediato da 5004
            if ids and not self._wait_tpsl_clear(pos["positionId"]):
                raise MexcError(
                    "MEXC todavia esta cancelando la orden anterior. Reintenta en un segundo."
                )
            if tp or sl:
                self.mx.tpsl_place(pos["positionId"], pos["holdVol"], tp, sl)
            self.session.log(f"OK  tpsl {symbol} tp={tp} sl={sl}")
            msg = f"TP/SL actualizado · {symbol}"
            self.q.put(("closed", msg))
            if avisos:
                self.q.put(("notice", ("SL en ganancia", "\n\n".join(avisos), False)))
        except Exception as e:
            self.session.log(f"ERR tpsl {symbol}: {e}")
            self.q.put(("closed", f"Error TP/SL: {e}"))
            self.q.put(("notice", ("TP / SL rechazado", str(e), True)))
        self.session.refresh_positions()

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

    # --------------------------------------------------------- ordenes abiertas
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
            target=self._cancel_worker, args=([order.get("orderId")],), daemon=True
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
        threading.Thread(
            target=self._cancel_worker,
            args=([o.get("orderId") for o in orders],),
            daemon=True,
        ).start()

    def modificar(self, order):
        """Editar una orden. MEXC no deja modificarla: se cancela y se reenvía.

        Reenviar es abrir una orden, así que DRY-RUN lo frena. La orden de cierre
        (lado 2/4) no se puede reenviar así: solo cancelar.
        """
        if not es_editable(order):
            self.port.status("Una orden de cierre solo se puede cancelar.")
            return
        if self.dry():
            self.port.status("DRY-RUN: no se reenvía la orden modificada")
            return
        symbol = order.get("symbol")
        contract = self.session.contract_for(symbol)
        if not contract:
            self.port.status(f"Falta el contrato de {symbol}: espera a que cargue el catálogo.")
            return

        def to_vol(notional, price):
            # contrato ya cacheado: el editor no pide nada a la red
            return self.mx.size_to_vol(symbol, notional, price, contract)

        form = self.port.editar_orden(order, contract, to_vol)
        if not form:
            return
        threading.Thread(target=self._replace_worker, args=(order, form), daemon=True).start()

    def _replace_worker(self, order, form):
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

    def _cancel_worker(self, ids):
        try:
            self.mx.cancel(ids)
            self.session.log(f"OK  cancel {len(ids)} orden(es) {ids}")
            if len(ids) == 1:
                self.q.put(("closed", "Orden cancelada"))
            else:
                self.q.put(("closed", f"{len(ids)} órdenes canceladas"))
        except Exception as e:
            self.session.log(f"ERR cancel {ids}: {e}")
            self.q.put(("closed", f"Error al cancelar: {e}"))
            self.q.put(("notice", ("No se pudo cancelar", str(e), True)))
        self.session.refresh_orders()

    # ------------------------------------------------------------------- margen
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
            self.mx.change_margin(pos["positionId"], amount, "ADD")
            self.session.log(f"OK  margen +{amount} {pos.get('symbol')}")
            self.q.put(("closed", f"Margen añadido · {pos.get('symbol')}"))
        except Exception as e:
            self.session.log(f"ERR margen {pos.get('symbol')}: {e}")
            self.q.put(("closed", f"Error margen: {e}"))
        self.session.refresh_positions()


__all__ = ["Control"]
