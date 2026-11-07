"""Comportamiento reutilizable de Trade Desk."""

import threading
import time

from .mexc import MexcError, break_even_price, mark_price, plan_tp_sl


class TpslMixin:
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
        incierto = False
        cliente = None
        try:
            cliente = self.broker_de(pos)
            avisos = self._aplicar_tpsl(pos, tp, sl, es_be)
            self.q.put(("closed", f"TP/SL actualizado · {symbol}"))
            if avisos:
                self.q.put(("notice", ("SL en ganancia", "\n\n".join(avisos), False)))
        except Exception as e:
            if self._resultado_desconocido(e):
                incierto = True
                mensaje = self._mensaje_desconocido("tpsl")
                self.session.log(f"ERR tpsl {symbol}: {type(e).__name__}")
                self.q.put(("closed", mensaje))
                self.q.put(("status", mensaje))
                if cliente is not None:
                    exchange = pos.get("_exchange") or "mexc"

                    def comprobar():
                        precio = cliente.price(symbol)
                        tp_final, sl_final, _ = plan_tp_sl(
                            self._lado_posicion(pos, exchange) == 1,
                            precio,
                            tp,
                            sl,
                        )
                        return self._tpsl_coincide(cliente, exchange, pos, tp_final, sl_final)

                    self._iniciar_verificacion(
                        "cambio de TP/SL",
                        comprobar,
                    )
            else:
                self.session.log(f"ERR tpsl {symbol}: {e}")
                self.q.put(("closed", f"Error TP/SL: {e}"))
                self.q.put(("notice", ("TP / SL rechazado", str(e), True)))
        if incierto:
            self.session.refresh_orders()
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
        incierto = False
        verificaciones = []
        for pos in posiciones:
            if str(pos.get("positionId")) not in ids:
                continue
            nombre = pos.get("_name") or pos.get("symbol") or ""
            cliente = None
            fila = None
            tp = None
            try:
                fila = self._fila_be(pos)
                tp = float(pos.get("_tp") or 0) or None
                cliente = self.broker_de(pos)
                self._aplicar_tpsl(pos, tp, fila["be"], True)
                hechas += 1
            except Exception as exc:
                if self._resultado_desconocido(exc):
                    incierto = True
                    fallos.append(f"{nombre}: {self._mensaje_desconocido('tpsl')}")
                    self.session.log(f"ERR be {nombre}: {type(exc).__name__}")
                    if cliente is not None:
                        exchange = pos.get("_exchange") or "mexc"
                        target_sl = fila["be"] if fila else None

                        def comprobar(
                            cliente=cliente,
                            exchange=exchange,
                            pos=pos,
                            target_tp=tp,
                            target_sl=target_sl,
                        ):
                            precio = cliente.price(pos.get("symbol"))
                            tp_final, sl_final, _ = plan_tp_sl(
                                self._lado_posicion(pos, exchange) == 1,
                                precio,
                                target_tp,
                                target_sl,
                            )
                            return self._tpsl_coincide(cliente, exchange, pos, tp_final, sl_final)

                        verificaciones.append((f"TP/SL de {nombre}", comprobar))
                else:
                    fallos.append(f"{nombre}: {exc}")
            self.q.put(("closed", f"BE {hechas}/{total} · {nombre}"))
            time.sleep(0.6)
        resultado_log = "ERR" if fallos else "OK "
        self.session.log(f"{resultado_log} be {hechas}/{total} ({len(fallos)} fallos)")
        self.q.put(("closed", f"BE aplicado en {hechas} de {total} posiciones"))
        if fallos:
            self.q.put(("notice", ("BE incompleto", "\n".join(fallos), True)))
        if incierto:
            self.q.put(("status", self._mensaje_desconocido("tpsl")))
            self.session.refresh_orders()
        self.session.refresh_positions()
        for accion, comprobar in verificaciones:
            self._iniciar_verificacion(accion, comprobar)

    def _wait_tpsl_clear(self, mx, position_id, timeout=2.5):
        """Espera a que el broker suelte el TP/SL cancelado de esa posicion."""
        end = time.time() + timeout
        while time.time() < end:
            pendientes = [
                o for o in mx.tpsl_list() if int(o.get("positionId") or 0) == int(position_id)
            ]
            if not pendientes:
                return True
            time.sleep(0.25)
        return False
