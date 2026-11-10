"""Comportamiento reutilizable de Trade Desk."""

import threading
import time


class VerificacionMixin:
    @staticmethod
    def _clave_symbol(symbol):
        return str(symbol or "").replace("_", "").replace("-", "").upper()

    @staticmethod
    def _numero(valor):
        try:
            return abs(float(valor or 0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _lado_posicion(fila, exchange):
        if fila.get("positionType") is not None:
            return 1 if int(fila.get("positionType") or 1) == 1 else 2
        if exchange == "mexc":
            return 1 if int(fila.get("positionType") or 1) == 1 else 2
        if exchange == "bitunix":
            return 1 if str(fila.get("side") or "").upper() in ("BUY", "LONG") else 2
        lado = str(fila.get("positionSide") or "").upper()
        if lado in ("LONG", "SHORT"):
            return 1 if lado == "LONG" else 2
        return 1 if float(fila.get("positionAmt") or 0) >= 0 else 2

    @staticmethod
    def _volumen_posicion(fila, exchange):
        if "holdVol" in fila:
            return Control._numero(fila.get("holdVol"))
        campo = {"mexc": "holdVol", "bitunix": "qty", "bingx": "positionAmt"}[exchange]
        return Control._numero(fila.get(campo))

    def _volumen_cache(self, exchange, symbol, side):
        return sum(
            self._volumen_posicion(fila, exchange)
            for fila in getattr(self.session, "ultimas_posiciones", ())
            if (fila.get("_exchange") or "mexc") == exchange
            and self._clave_symbol(fila.get("symbol")) == self._clave_symbol(symbol)
            and self._lado_posicion(fila, exchange) == side
        )

    def _ids_cache_ordenes(self, exchange):
        return {
            str(fila.get("orderId") or "")
            for fila in getattr(self.session, "ultimas_ordenes", ())
            if (fila.get("_exchange") or "mexc") == exchange
        }

    def _volumen_lado(self, cliente, exchange, symbol, side):
        filas = cliente.positions()
        total = 0.0
        for fila in filas or ():
            if self._clave_symbol(fila.get("symbol")) != self._clave_symbol(symbol):
                continue
            if self._lado_posicion(fila, exchange) == side:
                total += self._volumen_posicion(fila, exchange)
        return total

    def _orden_nueva(self, cliente, exchange, symbol, side, precio, ids_anteriores, cierre=False):
        for fila in cliente.open_orders() or ():
            if self._clave_symbol(fila.get("symbol")) != self._clave_symbol(symbol):
                continue
            if str(fila.get("orderId") or fila.get("id") or "") in ids_anteriores:
                continue
            tipo = str(fila.get("type") or fila.get("origType") or "").upper()
            if "STOP" in tipo or "TAKE_PROFIT" in tipo:
                continue
            trade_side = str(fila.get("tradeSide") or "").upper()
            if (
                exchange == "bitunix"
                and trade_side
                and trade_side != ("CLOSE" if cierre else "OPEN")
            ):
                continue
            if exchange == "mexc":
                lado = int(fila.get("side") or 0)
                codigos = (4, 2) if cierre else (1, 3)
                lado = 1 if lado == codigos[0] else 2 if lado == codigos[1] else 0
            elif exchange == "bitunix":
                lado = 1 if str(fila.get("side") or "").upper() in ("BUY", "LONG") else 2
            else:
                side_name = str(fila.get("positionSide") or "").upper()
                if side_name in ("LONG", "SHORT"):
                    lado = 1 if side_name == "LONG" else 2
                else:
                    lado = 1 if str(fila.get("side") or "").upper() == "BUY" else 2
            if lado != side:
                continue
            if precio is not None and abs(self._numero(fila.get("price")) - precio) > 1e-8:
                continue
            return True
        return False

    def _tpsl_coincide(self, cliente, exchange, pos, tp, sl):
        symbol = pos.get("symbol")
        side = self._lado_posicion(pos, exchange)
        if exchange == "bingx":
            ordenes = cliente.open_orders(symbol)
            posiciones = [
                posicion
                for posicion in cliente.positions() or ()
                if self._clave_symbol(posicion.get("symbol")) == self._clave_symbol(symbol)
            ]
            if not any(self._lado_posicion(posicion, exchange) == side for posicion in posiciones):
                return False
            lado_ambiguo = len(posiciones) > 1
            actual_tp = actual_sl = 0.0
            for orden in ordenes or ():
                if self._clave_symbol(orden.get("symbol")) != self._clave_symbol(symbol):
                    continue
                lado = str(orden.get("positionSide") or "").upper()
                if lado in ("LONG", "SHORT") and (1 if lado == "LONG" else 2) != side:
                    continue
                if lado_ambiguo and lado not in ("LONG", "SHORT"):
                    continue
                tipo = str(orden.get("type") or orden.get("origType") or "").upper()
                precio = self._numero(orden.get("stopPrice"))
                if "TAKE_PROFIT" in tipo:
                    actual_tp = precio
                elif "STOP" in tipo:
                    actual_sl = precio
        else:
            stops = cliente.tpsl_list()
            actual_tp = actual_sl = 0.0
            for stop in stops or ():
                if exchange == "mexc":
                    if str(stop.get("positionId")) != str(pos.get("positionId")):
                        continue
                    actual_tp = self._numero(stop.get("takeProfitPrice")) or actual_tp
                    actual_sl = self._numero(stop.get("stopLossPrice")) or actual_sl
                elif self._clave_symbol(stop.get("symbol")) == self._clave_symbol(symbol):
                    actual_tp = (
                        self._numero(stop.get("tpPrice") or stop.get("takeProfitPrice"))
                        or actual_tp
                    )
                    actual_sl = (
                        self._numero(stop.get("slPrice") or stop.get("stopLossPrice")) or actual_sl
                    )
            if exchange == "bitunix":
                posiciones = [
                    posicion
                    for posicion in cliente.positions() or ()
                    if self._clave_symbol(posicion.get("symbol")) == self._clave_symbol(symbol)
                ]
                if len(posiciones) != 1 or self._lado_posicion(posiciones[0], exchange) != side:
                    return False
        escala = int(pos.get("_priceScale") or 2)
        tolerancia = 10**-escala
        return abs(actual_tp - (tp or 0)) <= tolerancia and abs(actual_sl - (sl or 0)) <= tolerancia

    def _iniciar_verificacion(self, accion, comprobar):
        """Consulta solo lectura hasta recuperar conexión y cotejar el estado."""
        self.q.put(("status", f"Consultando al broker para verificar {accion}…"))

        def verificar():
            detener = getattr(self.session, "_parar", None)
            muestras = 0
            while detener is None or not detener.is_set():
                try:
                    confirmado = comprobar()
                except Exception as exc:
                    if not self._resultado_desconocido(exc):
                        self.session.log(f"ERR verificar {accion}: {type(exc).__name__}")
                        self.q.put(
                            (
                                "status",
                                f"No se pudo verificar {accion}: {exc}. Revisa Posiciones/Órdenes.",
                            )
                        )
                        self.session.refresh_positions()
                        self.session.refresh_orders()
                        return
                    muestras = 0
                    if detener is None:
                        self.q.put(
                            (
                                "status",
                                f"La conexión sigue sin responder; no se pudo verificar {accion}. "
                                "Revisa Posiciones/Órdenes.",
                            )
                        )
                        break
                    if detener.wait(self.VERIFICACION_INTERVALO):
                        return
                    continue
                if confirmado:
                    texto = f"El broker confirmó la operación: {accion}."
                    self.session.log(f"OK  verificado {accion}")
                    self.q.put(("status", texto))
                    self.session.refresh_positions()
                    self.session.refresh_orders()
                    return
                muestras += 1
                if muestras >= self.VERIFICACION_MUESTRAS:
                    self.q.put(
                        (
                            "status",
                            f"No se encontró evidencia de {accion}. Revisa Posiciones/Órdenes "
                            "antes de decidir si vuelves a intentarlo.",
                        )
                    )
                    self.session.refresh_positions()
                    self.session.refresh_orders()
                    return
                # la primera reconsulta va rápido: el broker suele reflejar el
                # cambio en menos de un segundo
                espacios = getattr(self, "VERIFICACION_ESPACIOS", (2.0,))
                espera = espacios[min(muestras, len(espacios)) - 1]
                if detener is None:
                    time.sleep(espera)
                elif detener.wait(espera):
                    return

        threading.Thread(target=verificar, daemon=True).start()


Control = VerificacionMixin
