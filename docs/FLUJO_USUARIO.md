# 2. Cómo lo usa el usuario (flujo real)

1. Abre `Trade Desk` (acceso directo del escritorio). Arranca **sin tarjetas**.
2. `+ Añadir par` → buscador modal de **futuros** → escribe (`btc`, `sol`) → `Enter` toma
   el primero. El catálogo viene de MEXC Futures, Bitunix Futures y BingX Swap; spot no está
   incluido.
3. Configura apalancamiento (entry o presets 1/5/10/15/20/50), margen (Aislado por defecto),
   modo de tamaño (Margen o Nocional) y escribe el **tamaño en USDT** (vacío por defecto).
4. Opcional: TP y SL.
5. Mira el resumen de la tarjeta: MEXC muestra contratos, nocional, fee y liquidación
   estimadas; Bitunix muestra monedas y nocional; BingX muestra monedas, nocional y fee.
6. `LONG` o `SHORT` → diálogo de confirmación → orden a mercado. El chip `Mercado ▾`
   de la tarjeta (al lado de *Tamaño*) permite abrir **a límite**: escribe el precio y
   la orden sale `type=1`; sin tocarlo sigue saliendo a mercado.
7. **Enviar todas**: la fila `Lote` de la tarjeta (— / LONG / SHORT) marca el lado que cada
   una manda, y el botón `ENVIAR TODAS (N)` de arriba del deck envía esas N con **una sola
   confirmación**, cada una con su propio margen, apalancamiento, tamaño y TP/SL. El selector
   arranca en `—` y no se guarda en `config.json`; las tarjetas sin cliente o con el par no
   disponible se omiten y la confirmación lo dice. Un solo aviso resume el lote (con la lista
   de errores) y las que quedaron `ok` o con estado desconocido vuelven a `—`.
8. Abajo, pestaña **Posiciones**: cada fila trae `[Mercado]`, `[%]` y el botón
   `Cerrar LONG` / `Cerrar SHORT` (del color del PnL). Sin tocar nada cierra **a mercado y
   al 100 %**, con el mismo diálogo de siempre; un precio en el primer campo la vuelve orden
   **límite** (puede quedar sin llenar) y el `%` permite cerrar una parte. También:
   checkboxes + `Cerrar seleccionadas`, `Reverse` y `CERRAR TODO` (siempre a mercado).
   El **lápiz de TP/SL** abre el editor con dos líneas vivas (`TP 101,200.0 → +15.2400 USDT`
   y `SL 99,500.0 → -6.3500 USDT`), dos campos **% del margen** que calculan el precio
   (`TP 15` → precio con +15 % de PnL sobre el margen; el SL se escribe en negativo) y un
   botón `Break-even` que rellena el SL con el precio que deja la operación en cero
   (comisión de entrada + salida + funding). Se habilita solo cuando el precio ya lo pasó; si
   no alcanza, el botón sale gris y la nota dice cuánto falta.
9. Pestaña **Órdenes** (panel estilo MEXC): las límite que todavía no se llenaron, con par
   (+`Perpetual` y el % llenado debajo), fecha, dirección (`Compra LONG` / `Venta SHORT`),
   apalancamiento, monto, precio, llenado, margen usado, TP/SL en dos líneas, fee y estado.
   Los **lápices** de Monto, Precio y TP/SL abren el editor (lado, apalancamiento, margen,
   precio, TP y SL); en la columna de acciones están `Modificar` y `Cancelar`, y arriba a la
   derecha `Cancelar todo`. Una orden límite no aparece en Posiciones hasta que se llena.
   Las condicionales TP/SL de BingX se muestran y pueden cancelarse, pero no ofrecen lápiz
   ni `Modificar` desde esta pestaña.
10. Pestaña **Historial**: las últimas órdenes de los **tres** brokers, **agrupadas en
   operaciones** (una fila por operación, no por orden): hora de apertura y de cierre, par
   con el wordmark del broker, lado, **tamaño en USDT**, entrada, salida, PnL, fee, **neto**
   (PnL − fee) y estado (`Cerrada` / `Parcial` / `Abierta`). Los cierres parciales se suman
   en la misma fila en vez de aparecer sueltos.
11. Pestaña **Calendario**: un mes en cuadrícula con el resultado de cada día. El mes es
    **una tabla** con separadores de pelo (`Lun Mar…` arriba), no una tarjeta por día: cada
    celda lleva el número del día y debajo su **neto**, con el color en el número (verde o
    rojo, `theme.fmt_pnl`); los días sin operaciones quedan neutros y el día de hoy lleva un
    círculo (`ACCENT_SOFT`). El conteo de operaciones ya no está en la celda: sale en el
    tooltip al pasar el mouse. Al lado están dos tarjetas: **Neto del mes** (número grande,
    operaciones y win rate, y la curva acumulada del mes) y **Resumen del mes** (mejor y peor
    día, profit factor, rachas, drawdown, fees totales, desglose por broker y totales por
    semana). Al hacer clic en un día se listan sus operaciones a la **derecha** del panel
    (par con wordmark, lado, entrada, salida, PnL, fee, neto y hora), en el espacio libre de
    la pestaña: la vista no baja ni cambia de forma. Se navega
    por mes y año, hay botón **Hoy**, filtros por broker y por par, un botón para **ocultar
    los montos** y otro para **exportar el mes a CSV**. La pestaña
    **no pide nada a la red**: usa las mismas filas del historial (el archivo local fusionado
    con el broker); «Cargar más historial» reutiliza la paginación del botón *Ver más*.

`DRY-RUN` viene **siempre encendido** en cada arranque y bloquea **abrir, cerrar y reverse**.
El **TP/SL**, el **margen** y **cancelar órdenes** sí funcionan con DRY-RUN activo: son
gestión de riesgo, no abren exposición. **Modificar** una orden sí queda bloqueado: reenviarla
es abrir.

---

