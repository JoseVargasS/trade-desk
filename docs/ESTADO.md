# 10. Estado actual y pendientes

**Funciona y está verificado con dinero real:** abrir a mercado, cerrar una posición,
cerrar todas, DRY-RUN, historial, búsqueda, conversión de tamaño, **abrir una límite, verla
en la pestaña Órdenes, cancelarla y modificarla** (crear → listar → cancelar → editar y
reenviar, todo probado contra la cuenta con órdenes de prueba a mitad de precio).

**Migración a Qt terminada:**

- `python app.py` y el acceso directo abren la **vista Qt**; `python -m tradedesk.qt` hace lo
  mismo. La app de Tkinter y sus módulos (`app.py` del paquete, `ui.py`, `cards.py`,
  `closebar.py`, `table.py`, `orders.py`, `search.py`, `dialog.py`, `tooltip.py`, `actions.py`)
  se borraron; `customtkinter` salió de las dependencias.
- `session.py` carga config/catálogo, pollers y caches. `controller.py` tiene los casos de uso
  (abrir, cerrar, cerrar todo, reverse, TP/SL, margen, modificar/cancelar) y `qt/port.py`
  implementa el `UiPort`. Los payloads y mensajes son los mismos de antes.
- La vista Qt ya opera: LONG/SHORT, barra de cierre con `Mercado` / `%`, checkboxes +
  `Cerrar seleccionadas`, `CERRAR TODO`, `Reverse`, lápices de TP/SL y margen, editor de
  órdenes, `Cancelar todo`, buscador, historial, IP copiable, saldos por broker en la
  cabecera (cada 15 s), el envío por lote (`ENVIAR TODAS`) y DRY-RUN siempre encendido.
- El Historial se actualiza incrementalmente y conserva el scroll; sus logos se cachean.
  Los workers de ticker, cuenta y tareas secundarias son independientes, aunque las tareas
  auxiliares son secuenciales dentro de su worker.
- Medido con `tools/qt_probe.py` (8 tarjetas y 200 filas): **~50 ms** al restaurar contra
  **943 ms** del caso equivalente en Tk.

**Sin probar contra posición real:** `Reverse` y el cierre desde el botón de la fila
(la ruta existe y la firma está validada, pero no se ejecutó con posición abierta).
El **cierre parcial** (`vol < holdVol`) y el **cierre límite** (`type=1`) están probados
solo en el payload (`tests/test_mexc_orders.py`): falta ejecutarlos una vez contra una
posición real. El **Break-even** también: la cuenta solo en `test_mexc_pure.py` (que el SL
cubra comisiones y que nunca quede del lado de la pérdida por el redondeo) y en el
diálogo; falta ponerlo una vez con una posición en ganancia y comprobar que el PnL queda
en ~0 al ejecutarse.

**Bitunix (segundo broker), estado:**

- **Funciona:** elegir broker por tarjeta, precio y variación propios, contrato y
  `qty` en monedas, posiciones y órdenes mezcladas en las mismas tablas (con el
  wordmark del broker), **abrir** (mercado y límite, con TP/SL en la misma orden),
  **cerrar** (total por `flash_close_position`, parcial y límite por `place_order`
  reduce-only), **cerrar todo** (una por una: el endpoint masivo responde OK aunque no
  cierre nada), **cancelar** (una o todas) y **apalancamiento**.
- **Todo lo de la interfaz funciona igual que en MEXC:** editar TP/SL de una posición
  (nivel de posición, verificado: 70.000/90.000 y luego 71.000/95.000), modificar una orden
(nativa, verificado 60.052,6 → 60.552,6 con qty 0,0002), cambiar margen (verificado
+1 USDT: 15,4077 → 16,4077), historial, y el mismo par en dos brokers (`BTC_USDT#2`).
- Tests de payload: `tests/test_bitunix_orders.py` (11 casos, sin red).
- **Probado con dinero real (27-jul), todo cerrado:**
  - SHORT `0.0001` BTC 1x con TP 70.000 / SL 90.000, ~2 min, cerrado con flash: saldo
    `309,6128 → 309,6074` (≈ 0,0054 USDT). Destapó tres mapeos: `side` `SELL` se leía
    como LONG, la entrada viene en `avgOpenPrice` y el TP/SL en dos registros.
  - Límite `0.0001` a 60.006 (lejos) → apareció en abiertas y se canceló con
    `cancel_orders`; la orden decorada sale bien (`side` 1, `price`, `_exchange`).
  - Parcial: `0.0002` short, cierre de `0.0001` (reduceOnly) → quedó `0.0001`, y el
    resto con flash. Confirma que el `side` documentado (BUY para cerrar un long) sirve.
  - `reverse`: SHORT `0.0002` → LONG `0.0002` en 1,2 s (con el cierre reduceOnly).
- **Sin probar:** que un TP/SL se **dispare** (lo prueba el usuario; la colocación ya está
  verificada) y el cierre límite de una posición.

**F7 (opcional, no empezada):** gráficos de velas con TP/SL arrastrables (`pyqtgraph`).

**Lote de velocidad (sin commitear, sin verificar con dinero real):** consultas de cuenta
por broker en paralelo, cierres y cancellations por broker en paralelo, BE masivo con una
sola lista de stops por broker, TP/SL de MEXC con reintento ante 5004 (en vez de sondear la
lista), precio de referencia para no pedir un ticker extra por orden, caché de apalancamiento
de 60 s en Bitunix/BingX y reconsultas de verificación más rápidas (0,4 / 1 / 2 / 3 s).
Todo está cubierto con dobles de prueba; **falta probarlo con la cuenta real** (una apertura,
un cierre, un TP/SL y un BE) antes de darlo por bueno.

**Pendiente / ideas descartadas por ahora:**

- Guardar más de un TP parcial por posición (MEXC admite un TP y un SL por stop order).
- Cambiar el par de una tarjeta sin quitarla y volver a añadirla.
- **BingX funciona y está verificado con dinero real** (0,0001-0,0002 BTC, ~0,03 USDT de
  fees entre todas las rondas): abrir long/short a mercado, límite + cancelar, TP/SL al
  abrir y con el lápiz, cierre parcial, reverse y cierre total. Pendiente chico: la fee de
  una posición abierta (BingX no la expone) y el funding del par.
- `.exe` con PyInstaller `--onedir` si algún día aceptan el aviso de SmartScreen.

---

