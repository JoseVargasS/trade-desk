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
from .forms import volumen_cerrar
from .mexc import (
    MexcError,
    break_even_price,
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
    def _cliente_de(self, nombre):
        """Cliente de ese broker; si la sesión no sabe de brokers, MEXC."""
        traer = getattr(self.session, "cliente", None)
        if callable(traer):
            encontrado = traer(nombre)
            if encontrado is not None:
                return encontrado
        return self.mx

    def _brokers(self):
        """(nombre, cliente) de los brokers conectados."""
        traer = getattr(self.session, "cliente", None)
        if not callable(traer):
            return [("mexc", self.mx)]
        lista = [(n, traer(n)) for n in ("mexc", "bitunix", "bingx") if traer(n) is not None]
        return lista or [("mexc", self.mx)]

    def broker_de(self, objeto, defecto="mexc"):
        """Cliente del broker de esa posición u orden (MEXC si no dice nada)."""
        return self._cliente_de((objeto or {}).get("_exchange") or defecto)

    def _aviso_bitunix(self, que):
        self.port.show(
            "Bitunix",
            f"{que} en Bitunix llega en el próximo paso.\n\n"
            "Ya funcionan: abrir, cerrar, cerrar todo y cancelar órdenes.",
        )

    def abrir(self, side, form, al_enviar=None, exchange="mexc"):
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
        threading.Thread(
            target=self._do_abrir, args=(side, form, dry, exchange), daemon=True
        ).start()

    def _do_abrir(self, side, form, dry, exchange="mexc"):
        symbol = form["symbol"]
        mx = self._cliente_de(exchange)
        try:
            precio = form.get("price")
            if dry:
                px = precio or mx.price(symbol)
                vol = mx.size_to_vol(symbol, form["notional"], px)
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
            data, vol, px = mx.open_market(
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
        paso = float(pos.get("_qtyStep") or 1.0)
        vol = volumen_cerrar(pos.get("holdVol"), pct, paso)
        if vol <= 0:
            unidad = "contratos" if (pos.get("_exchange") or "mexc") == "mexc" else "monedas"
            self.port.show(
                "Cantidad invalida",
                f"Ese {pct:.0f}% deja 0 {unidad}: la posicion tiene "
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
        # se deja rastro de lo que se manda: asi un parcial que "no hace nada"
        # se puede seguir en la barra y en trades.log
        unidad = "contratos" if (pos.get("_exchange") or "mexc") == "mexc" else "monedas"
        self.port.status(f"Cerrar {pct:.0f}% · {t.fmt_qty(vol)} {unidad} de {pos.get('symbol')}")
        self.session.log(
            f"cierre {pos.get('symbol')} {pct:.0f}% vol={vol} ({pos.get('_exchange')})"
        )
        if not self.port.confirm("Cerrar posicion", rows=rows, warn=warn, danger=True, ok="Cerrar"):
            self.port.status("Cierre cancelado")
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
                self.broker_de(pos).close_position(
                    pos, vol if single else None, price if single else None
                )
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
                self.broker_de(pos).reverse(pos)
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
            fallos = []
            for nombre, cliente in self._brokers():
                try:
                    cliente.close_all()
                    self.session.log(f"OK  close_all {nombre}")
                except Exception as e:
                    fallos.append(f"{nombre}: {e}")
                    self.session.log(f"ERR close_all {nombre}: {e}")
            if fallos:
                self.q.put(("closed", " | ".join(fallos)))
            else:
                self.q.put(("closed", "Todas las posiciones cerradas"))
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

    def _aplicar_tpsl(self, pos, tp, sl, es_be=False):
        """Coloca el TP/SL de una posicion. Lanza si el broker lo rechaza.

        Lo usan el lapiz (que envuelve con dialogos) y el "poner a BE" masivo.
        """
        symbol = pos.get("symbol")
        mx = self.broker_de(pos)
        price = mx.price(symbol)
        long_ = int(pos.get("positionType") or 1) == 1
        if es_be and sl and (sl > price if long_ else sl < price):
            # sin esta guarda plan_tp_sl lo guardaria como TP
            raise MexcError(
                "El precio se movio y el break-even ya no cubre las comisiones. Reintenta."
            )
        # el TP/SL se mide contra el precio actual, no contra la entrada
        tp, sl, avisos = plan_tp_sl(long_, price, tp, sl)
        # BingX no tiene stop orders por posicion: `tpsl_place` cancela sus
        # condicionales y pone las nuevas, sin ids que esperar. Con `tpsl_list`
        # (MEXC y Bitunix) se cancelan todos los stops de la posicion porque un
        # id viejo deja duplicados.
        es_bingx = (pos.get("_exchange") or "mexc") == "bingx"
        if not es_bingx:
            ids = [
                o.get("id")
                for o in mx.tpsl_list()
                if int(o.get("positionId") or 0) == int(pos["positionId"])
            ]
            for stop_id in [i for i in ids if i]:
                try:
                    mx.tpsl_cancel(stop_id, simbolo=pos.get("symbol"))
                except MexcError as e:
                    if "ya no existe" not in str(e):
                        raise
            # el cancel es asincrono: recolocar de inmediato da 5004
            if ids and not self._wait_tpsl_clear(mx, pos["positionId"]):
                raise MexcError(
                    "El broker todavía está cancelando la orden anterior. Reintenta en un segundo."
                )
        if tp or sl:
            mx.tpsl_place(pos["positionId"], pos["holdVol"], tp, sl, simbolo=pos.get("symbol"))
        elif es_bingx:
            # borrar el TP/SL: en BingX las condicionales las cancela
            # `tpsl_place`, asi que hay que llamarlo aunque no se ponga nada
            mx.tpsl_place(pos["positionId"], pos["holdVol"], None, None, simbolo=pos.get("symbol"))
        self.session.log(f"OK  tpsl {symbol} tp={tp} sl={sl} ({pos.get('_exchange')})")
        return avisos

    def _tpsl_worker(self, pos, tp, sl, es_be=False):
        symbol = pos.get("symbol")
        try:
            avisos = self._aplicar_tpsl(pos, tp, sl, es_be)
            self.q.put(("closed", f"TP/SL actualizado · {symbol}"))
            if avisos:
                self.q.put(("notice", ("SL en ganancia", "\n\n".join(avisos), False)))
        except Exception as e:
            self.session.log(f"ERR tpsl {symbol}: {e}")
            self.q.put(("closed", f"Error TP/SL: {e}"))
            self.q.put(("notice", ("TP / SL rechazado", str(e), True)))
        self.session.refresh_positions()

    def be_todas(self, posiciones):
        """Pone a BE las posiciones que el usuario elija en la ventana."""
        if not posiciones:
            self.port.status("No hay posiciones abiertas.")
            return
        filas = [self._fila_be(pos) for pos in posiciones]
        elegidas = self.port.be_lista(filas)
        if not elegidas:
            return
        ids = {str(ident) for ident in elegidas}
        threading.Thread(target=self._be_worker, args=(posiciones, ids), daemon=True).start()

    def _fila_be(self, pos):
        """Lo que muestra la ventana de BE: precio, break-even y si se puede."""
        symbol = pos.get("symbol")
        largo = int(pos.get("positionType") or 1) == 1
        escala = int(pos.get("_priceScale") or 2)
        precio = mark_price(pos) or self.session.precios.get(symbol) or 0
        be, _ = break_even_price(pos, largo)
        sl = float(pos.get("_sl") or 0)
        motivo = ""
        if not be:
            motivo = "sin datos de entrada"
        elif not precio:
            motivo = "sin precio"
        elif be > precio if largo else be < precio:
            motivo = "todavía no llega al break-even"
        elif sl and abs(sl - be) <= max(10.0**-escala, 1e-12):
            motivo = "BE ya colocado"
        return {
            "id": str(pos.get("positionId")),
            "nombre": pos.get("_name") or symbol or "",
            "broker": pos.get("_exchange") or "mexc",
            "lado": "LONG" if largo else "SHORT",
            "pnl": float(pos.get("unRealizedPnl") or 0),
            "entrada": float(pos.get("holdAvgPrice") or 0),
            "precio": float(precio or 0),
            "be": float(be or 0),
            "escala": escala,
            "puede": not motivo,
            "motivo": motivo,
        }

    def _be_worker(self, posiciones, ids):
        total = len(ids)
        hechas, fallos = 0, []
        for pos in posiciones:
            if str(pos.get("positionId")) not in ids:
                continue
            nombre = pos.get("_name") or pos.get("symbol") or ""
            try:
                fila = self._fila_be(pos)
                tp = float(pos.get("_tp") or 0) or None
                self._aplicar_tpsl(pos, tp, fila["be"], True)
                hechas += 1
            except Exception as exc:
                fallos.append(f"{nombre}: {exc}")
            self.q.put(("closed", f"BE {hechas}/{total} · {nombre}"))
            time.sleep(0.6)
        self.session.log(f"OK  be {hechas}/{total} ({len(fallos)} fallos)")
        self.q.put(("closed", f"BE aplicado en {hechas} de {total} posiciones"))
        if fallos:
            self.q.put(("notice", ("BE incompleto", "\n".join(fallos), True)))
        self.session.refresh_positions()

    def _wait_tpsl_clear(self, mx, position_id, timeout=2.5):
        """Espera a que el broker suelte el TP/SL cancelado de esa posicion."""
        end = time.time() + timeout
        while time.time() < end:
            try:
                pendientes = [
                    o for o in mx.tpsl_list() if int(o.get("positionId") or 0) == int(position_id)
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
        for nombre, ids in grupos.items():
            cliente = self._cliente_de(nombre)
            try:
                cliente.cancel(ids)
                self.session.log(f"OK  canceladas {nombre} {ids}")
            except Exception as exc:
                self.session.log(f"ERR cancelar {nombre}: {exc}")
                self.q.put(("closed", f"Error al cancelar en {nombre}: {exc}"))
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
        if self.dry():
            self.port.status("DRY-RUN: no se reenvía la orden modificada")
            return
        symbol = order.get("symbol")
        cliente = self.broker_de(order)
        if (order.get("_exchange") or "mexc") in ("bitunix", "bingx"):
            contract = cliente.contract(symbol)
        else:
            contract = self.session.contract_for(symbol)
        if not contract:
            self.port.status(f"Falta el contrato de {symbol}: espera a que cargue el catálogo.")
            return

        def to_vol(notional, price):
            # contrato ya cacheado: el editor no pide nada a la red
            return cliente.size_to_vol(symbol, notional, price, contract)

        form = self.port.editar_orden(order, contract, to_vol)
        if not form:
            return
        threading.Thread(target=self._replace_worker, args=(order, form), daemon=True).start()

    def _replace_worker(self, order, form):
        symbol = order.get("symbol")
        cliente = self.broker_de(order)
        es_bnx = (order.get("_exchange") or "mexc") == "bitunix"
        try:
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

    def _wait_order_gone(self, order_id, timeout=2.5, cliente=None):
        """Espera a que la orden cancelada desaparezca de `open_orders`."""
        dueno = cliente or self.mx
        fin = time.time() + timeout
        while time.time() < fin:
            try:
                abiertas = dueno.open_orders()
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


__all__ = ["Control"]
