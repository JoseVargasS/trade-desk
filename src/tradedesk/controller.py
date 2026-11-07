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

import httpx

from . import theme as t
from .controller_ordenes import OrdenesMixin
from .controller_tpsl import TpslMixin
from .controller_verificacion import VerificacionMixin
from .forms import volumen_cerrar


class BrokerNoDisponibleError(RuntimeError):
    pass


class Control(VerificacionMixin, TpslMixin, OrdenesMixin):
    """Acciones de la mesa. `dry` es un callable: DRY-RUN siempre arranca prendido."""

    VERIFICACION_INTERVALO = 2.0
    VERIFICACION_MUESTRAS = 5

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

    @staticmethod
    def _resultado_desconocido(exc):
        return isinstance(exc, (httpx.TransportError, TimeoutError, ConnectionError))

    @staticmethod
    def _mensaje_desconocido(accion):
        return {
            "abrir": (
                "No pudimos confirmar si la solicitud llegó al broker. El resultado es "
                "desconocido. Revisa Posiciones y Órdenes antes de volver a intentarlo. "
                "No se volverá a enviar automáticamente."
            ),
            "cerrar": (
                "No pudimos confirmar si el cierre llegó al broker. El resultado es "
                "desconocido. Revisa Posiciones y Órdenes antes de reintentar. "
                "No se volverá a enviar automáticamente."
            ),
            "reverse": (
                "No pudimos confirmar si el reverse se completó. El resultado es desconocido. "
                "Revisa Posiciones y Órdenes antes de reintentar. "
                "No se volverá a enviar automáticamente."
            ),
            "tpsl": (
                "No pudimos confirmar si el cambio de TP/SL llegó al broker. Verifica "
                "Posiciones y Órdenes antes de volver a aplicarlo. No se reintentará "
                "automáticamente."
            ),
        }[accion]

    # ------------------------------------------------------------------- abrir
    def _cliente_de(self, nombre):
        """Cliente disponible del broker; no sustituye un broker por MEXC."""
        if nombre not in ("mexc", "bitunix", "bingx"):
            raise BrokerNoDisponibleError(f"Broker desconocido: {nombre}.")
        traer = getattr(self.session, "cliente", None)
        if not callable(traer):
            if nombre == "mexc":
                return self.mx
            raise BrokerNoDisponibleError(f"No hay cliente disponible para {nombre}.")
        encontrado = traer(nombre)
        if encontrado is None:
            raise BrokerNoDisponibleError(f"No hay credenciales disponibles para {nombre}.")
        return encontrado

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
        mx = None
        verificacion = None
        try:
            mx = self._cliente_de(exchange)
            precio = form.get("price")
            if dry:
                px = precio or mx.price(symbol)
                if exchange == "mexc":
                    vol = mx.size_to_vol(symbol, form["notional"], px)
                    unidad = "contratos"
                else:
                    vol = mx.size_to_qty(symbol, form["notional"], px)
                    unidad = symbol.split("_")[0]
                mensaje = (
                    f"DRY-RUN {side} {t.fmt_qty(vol)} {unidad} @ {t.fmt_price(px)} (no enviado)"
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
            volumen_anterior = self._volumen_cache(
                exchange, symbol, 1 if side.upper() == "LONG" else 2
            )
            ids_anteriores = self._ids_cache_ordenes(exchange)
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
            unidad = "contratos" if exchange == "mexc" else symbol.split("_")[0]
            mensaje = (
                f"{side} enviado: {t.fmt_qty(vol)} {unidad} @ {t.fmt_price(px)} · id {order_id}"
            )
            self.session.log("OK  " + mensaje)
            self.q.put(("order", (True, mensaje)))
            self.q.put(("closed", mensaje))
            self.q.put(("notice", ("Orden enviada", mensaje, False)))
            # una limite sin llenar no abre posicion: hay que refrescar ordenes
            self.session.refresh_positions()
            self.session.refresh_orders()
        except Exception as exc:
            incierto = not dry and self._resultado_desconocido(exc)
            if incierto:
                mensaje = self._mensaje_desconocido("abrir")
                self.session.refresh_positions()
                self.session.refresh_orders()
                if mx is not None:
                    lado = 1 if side.upper() == "LONG" else 2

                    def comprobar():
                        return self._volumen_lado(mx, exchange, symbol, lado) > (
                            volumen_anterior + 1e-12
                        ) or self._orden_nueva(
                            mx,
                            exchange,
                            symbol,
                            lado,
                            form.get("price"),
                            ids_anteriores,
                        )

                    verificacion = comprobar
                titulo = "Estado de la orden desconocido"
                detalle_log = type(exc).__name__
            elif isinstance(exc, BrokerNoDisponibleError):
                mensaje = str(exc)
                titulo = "Broker no disponible"
                detalle_log = type(exc).__name__
            else:
                mensaje = str(exc)
                titulo = "Orden rechazada"
                detalle_log = mensaje
            self.session.log(f"ERR {side} {symbol}: {detalle_log}")
            self.q.put(("order", (False, mensaje)))
            self.q.put(("closed", mensaje))
            self.q.put(("notice", (titulo, mensaje, True)))
            if verificacion:
                self._iniciar_verificacion("apertura", verificacion)

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
        incierto = False
        verificaciones = []
        single = len(positions) == 1  # solo el cierre de una fila lleva vol/precio
        for i, pos in enumerate(positions):
            exchange = pos.get("_exchange") or "mexc"
            cliente = None
            lado = self._lado_posicion(pos, exchange)
            volumen_anterior = self._volumen_posicion(pos, exchange)
            volumen_cerrar = vol if single and vol is not None else volumen_anterior
            ids_anteriores = self._ids_cache_ordenes(exchange)
            try:
                cliente = self.broker_de(pos)
                cliente.close_position(pos, vol if single else None, price if single else None)
                done += 1
                self.session.log(
                    f"OK  cerrada {pos.get('symbol')} vol={vol or pos.get('holdVol')}"
                    f"{' limite ' + str(price) if price else ''}"
                )
            except Exception as e:
                if self._resultado_desconocido(e):
                    incierto = True
                    mensaje = self._mensaje_desconocido("cerrar")
                    failed.append(f"{pos.get('symbol')}: {mensaje}")
                    self.session.log(f"ERR cerrar {pos.get('symbol')}: {type(e).__name__}")

                    def comprobar(
                        cliente=cliente,
                        exchange=exchange,
                        pos=pos,
                        lado=lado,
                        volumen_anterior=volumen_anterior,
                        volumen_cerrar=volumen_cerrar,
                        ids_anteriores=ids_anteriores,
                    ):
                        if cliente is None:
                            return False
                        objetivo = max(0.0, volumen_anterior - volumen_cerrar)
                        tolerancia = max(1e-12, volumen_anterior * 1e-8)
                        return self._volumen_lado(
                            cliente, exchange, pos.get("symbol"), lado
                        ) <= objetivo + tolerancia or self._orden_nueva(
                            cliente,
                            exchange,
                            pos.get("symbol"),
                            lado,
                            price if single else None,
                            ids_anteriores,
                            cierre=True,
                        )

                    verificaciones.append(comprobar)
                else:
                    failed.append(f"{pos.get('symbol')}: {e}")
                    self.session.log(f"ERR cerrar {pos.get('symbol')}: {e}")
            if i < len(positions) - 1:
                time.sleep(0.6)
        msg = f"Cerradas {done}" + (f" · fallaron {len(failed)}" if failed else "")
        self.q.put(("closed", msg))
        if failed:
            self.q.put(("status", " | ".join(failed)))
        self.session.refresh_positions()
        if incierto:
            self.session.refresh_orders()
        for comprobar in verificaciones:
            self._iniciar_verificacion("cierre", comprobar)

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
            verificacion = None
            try:
                cliente = self.broker_de(pos)
                exchange = pos.get("_exchange") or "mexc"
                lado = self._lado_posicion(pos, exchange)
                symbol = pos.get("symbol")
                volumen = self._volumen_posicion(pos, exchange)
                lado_contrario = 2 if lado == 1 else 1
                volumen_contrario = self._volumen_cache(exchange, symbol, lado_contrario)
                cliente.reverse(pos)
                self.session.log(f"OK  reverse {pos.get('symbol')} vol={pos.get('holdVol')}")
                self.q.put(("closed", f"Revertida {pos.get('symbol')}"))
            except Exception as e:
                if self._resultado_desconocido(e):
                    mensaje = self._mensaje_desconocido("reverse")
                    self.session.log(f"ERR reverse {pos.get('symbol')}: {type(e).__name__}")
                    self.q.put(("closed", mensaje))
                    self.q.put(("status", mensaje))
                    self.session.refresh_orders()
                    if "cliente" in locals():

                        def comprobar():
                            tolerancia = max(1e-12, volumen * 1e-8)
                            return (
                                self._volumen_lado(cliente, exchange, symbol, lado) <= tolerancia
                                and self._volumen_lado(cliente, exchange, symbol, lado_contrario)
                                > volumen_contrario + tolerancia
                            )

                        verificacion = comprobar
                else:
                    self.session.log(f"ERR reverse {pos.get('symbol')}: {e}")
                    self.q.put(("closed", f"Error reverse: {e}"))
            self.session.refresh_positions()
            if verificacion:
                self._iniciar_verificacion("reverse", verificacion)

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
            incierto = False
            verificaciones = []
            for nombre, cliente in self._brokers():
                posiciones_anteriores = [
                    pos
                    for pos in getattr(self.session, "ultimas_posiciones", ())
                    if (pos.get("_exchange") or "mexc") == nombre
                ]
                try:
                    cliente.close_all()
                    self.session.log(f"OK  close_all {nombre}")
                except Exception as e:
                    if self._resultado_desconocido(e):
                        incierto = True
                        fallos.append(f"{nombre}: {self._mensaje_desconocido('cerrar')}")
                        self.session.log(f"ERR close_all {nombre}: {type(e).__name__}")

                        simbolos = {
                            self._clave_symbol(pos.get("symbol")) for pos in posiciones_anteriores
                        }

                        def comprobar(cliente=cliente, nombre=nombre, simbolos=simbolos):
                            actuales = cliente.positions()
                            return not any(
                                not simbolos or self._clave_symbol(pos.get("symbol")) in simbolos
                                for pos in actuales or ()
                            )

                        verificaciones.append((f"cierre total en {nombre}", comprobar))
                    else:
                        fallos.append(f"{nombre}: {e}")
                        self.session.log(f"ERR close_all {nombre}: {e}")
            if fallos:
                self.q.put(("closed", " | ".join(fallos)))
            else:
                self.q.put(("closed", "Todas las posiciones cerradas"))
            self.session.refresh_positions()
            if incierto:
                self.session.refresh_orders()
            for accion, comprobar in verificaciones:
                self._iniciar_verificacion(accion, comprobar)

        threading.Thread(target=run, daemon=True).start()

    # -------------------------------------------------------------------- tp/sl

    # --------------------------------------------------------- ordenes abiertas

    # ------------------------------------------------------------------- margen


__all__ = ["Control"]
