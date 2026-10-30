"""Acciones sobre posiciones: cerrar, reverse, TP/SL y margen.

Se mezcla en App (mixin) porque todo depende de su estado: cliente, cola, tabla.
"""
import threading
import time

import dialog
import theme as t


class ActionsMixin:
    # ------------------------------------------------------------------ cierres
    def _close_position(self, pos):
        if self.var_dry.get():
            self._status(f"DRY-RUN: no se cerro {pos.get('symbol')}")
            return
        if not dialog.confirm(self.root, "Cerrar posicion", rows=[
                ("Par", pos.get("symbol")),
                ("Lado", "LONG" if int(pos.get("positionType") or 1) == 1 else "SHORT"),
                ("Qty", t.fmt_qty(pos.get("holdVol"))),
                ("PnL", t.fmt_pnl(pos.get("unRealizedPnl"))),
        ], warn="Se cierra a mercado.", danger=True, ok_text="Cerrar"):
            return
        threading.Thread(target=self._do_close, args=([pos],), daemon=True).start()

    def _close_selected(self):
        positions = self.table.selected()
        if not positions:
            self._status("Marca al menos una posicion con el checkbox.")
            return
        if self.var_dry.get():
            self._status(f"DRY-RUN: no se cerro {len(positions)} posicion(es)")
            return
        if not dialog.confirm(self.root, f"Cerrar {len(positions)} posicion(es)",
                              rows=[(p.get("symbol"), t.fmt_qty(p.get("holdVol")))
                                    for p in positions],
                              warn="Se cierran a mercado.", danger=True, ok_text="Cerrar"):
            return
        threading.Thread(target=self._do_close, args=(positions,), daemon=True).start()

    def _do_close(self, positions):
        failed, done = [], 0
        for i, pos in enumerate(positions):
            try:
                self.mx.close_position(pos)
                done += 1
                self._log(f"OK  cerrada {pos.get('symbol')} vol={pos.get('holdVol')}")
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
        if not dialog.confirm(self.root, "Reverse", rows=[
                ("Par", pos.get("symbol")),
                ("Lado actual", "LONG" if int(pos.get("positionType") or 1) == 1 else "SHORT"),
                ("Qty", t.fmt_qty(pos.get("holdVol"))),
        ], warn="Cierra la posicion y abre la contraria, al mercado.",
                danger=True, ok_text="Reverse"):
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
        if not dialog.confirm(self.root, "Cerrar TODO",
                              rows=[("Posiciones", self.table.checked_count() or "todas")],
                              warn="Se cierran TODAS las posiciones a mercado.\nNo se puede deshacer.",
                              danger=True, ok_text="Cerrar todo"):
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
        res = dialog.form(
            self.root, f"TP / SL · {pos.get('symbol')}",
            [("tp", "Take profit", pos.get("_tp") or ""),
             ("sl", "Stop loss", pos.get("_sl") or "")],
            ok_text="Guardar", note=f"Qty {t.fmt_qty(pos.get('holdVol'))} contratos")
        if res is None:
            return
        try:
            tp = float(res["tp"]) if res["tp"] else None
            sl = float(res["sl"]) if res["sl"] else None
        except ValueError:
            dialog.show(self.root, "Numero invalido",
                        "TP y SL deben ser numeros o quedar vacios.")
            return
        threading.Thread(target=self._tpsl_worker, args=(pos, tp, sl), daemon=True).start()

    def _tpsl_worker(self, pos, tp, sl):
        try:
            if pos.get("_tpsl_id"):
                self.mx.tpsl_cancel(pos["_tpsl_id"])
            if tp or sl:
                self.mx.tpsl_place(pos["positionId"], pos["holdVol"], tp, sl)
            self._log(f"OK  tpsl {pos.get('symbol')} tp={tp} sl={sl}")
            self.q.put(("closed", f"TP/SL actualizado · {pos.get('symbol')}"))
        except Exception as e:
            self._log(f"ERR tpsl {pos.get('symbol')}: {e}")
            self.q.put(("closed", f"Error TP/SL: {e}"))
        self._refresh_positions()

    # ---------------------------------------------------------------- margen
    def _add_margin(self, pos):
        if int(pos.get("openType") or 1) != 1:
            self._status("El margen solo se ajusta en modo aislado.")
            return
        # añadir margen tambien es gestion de riesgo: no lo bloquea DRY-RUN
        res = dialog.form(self.root, f"Añadir margen · {pos.get('symbol')}",
                          [("amount", "Monto (USDT)", "")], ok_text="Añadir",
                          note=f"Margen actual {t.fmt_usdt(pos.get('im'))} USDT")
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
