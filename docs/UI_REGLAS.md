# 6. Reglas de UI

- Los tokens de color, tipografía, radio y formato numérico viven en `theme.py`; la vista los
  consume desde ahí y el QSS se arma en `qt/style.py::qss()`. No agregues colores/fuentes ad hoc.
  Excepciones delimitadas: colores de marca ya incrustados en assets SVG y los valores
  equivalentes que requiere la API de la barra DWM de Windows.
- UI en `Geist`, **todo número en `theme.NUM`**, que es la misma familia (proporcional,
  no tabular): las columnas van alineadas a la derecha, así que el borde derecho no se mueve.
  Se probó `Geist Mono` y se descartó por ~19 % más ancha. Se registran en el proceso con
  `AddFontResourceExW`; no se instalan en Windows. **En Qt además hay que registrarlas con
  `QFontDatabase.addApplicationFont`** (`qt/style.cargar_fuentes()`, se llama en
  `qt/__main__.py` antes de crear widgets): `AddFontResourceExW` es GDI y DirectWrite no
  las ve, así que sin eso la ventana cae en Tahoma.
- Todo número se formatea con `theme.fmt_*`. PnL y fee con 4 decimales; precios de orden
  límite con `fmt_price_exact` (`priceScale` del contrato).
- La fila de posiciones no crece: la barra de cierre va en dos líneas dentro de los 200 px
  de la columna de acciones (`[Mercado][100%]` / `[Cerrar LONG][Reverse]`).
- Nada de `QMessageBox` ni de messagebox clásico: usar `qt.dialogs.confirm` / `show` /
  `ask_key` / `form` (QDialog sin marco, borde de 1 px, `Esc` cancela y `Enter` acepta).
- **Ningún worker toca widgets.** Los hilos solo hacen `q.put`; el hilo de la UI pinta.
  Comprobado por `tests/test_no_threaded_widgets.py`.
- **Ningún request desde el hilo de la UI.** El catálogo lo carga `Session` en su hilo y la
  vista abre el buscador por la cola. El editor de órdenes calcula los contratos con
  `size_to_vol(..., contract=cacheado)`, sin pedir nada.
- **Ningún `show`/`confirm` dentro de `_drenar`.** Un modal ahí adentro congela el refresco.
  Los avisos pasan por `VistaQt._notificar`, que los encola y abre uno por vez fuera del drain.
- Los avisos de la API se ven en la UI (barra de estado o diálogo), nunca se silencian.
- **Los errores del poller no abren modal**: van a la barra de estado y el poller afloja
  el ritmo (0.7 s → 5 s si algo falla). Un modal por cada reintento de 510 tapaba la app.
- **El `%` de cierre abre un panel con slider lineal de 1 a 100** (el 50 % queda al medio)
  y los números 0/25/50/75/100 pintados por el propio slider, debajo de sus puntos. El
  mínimo se calcula con el **paso de la unidad**: `ceil(100 * paso / holdVol)`, donde paso
  es **1** en MEXC (contratos) y el `qtyStep` del par en Bitunix (`_qtyStep`, 0.0001 BTC).
  Antes se usaba `ceil(100/holdVol)` a secas y en Bitunix daba 100 % (0,0003 → 333.334):
  el slider no se movía. **Una posición de una sola unidad** (BTC 0,0001 o un contrato)
  no se puede partir: `min_pct()` da 100 y el chip del `%` queda **deshabilitado** con un
  tooltip que lo explica. Antes se podía arrastrar y volvía solo a 100 %, que parecía roto.
  **El panel es un `QDialog` con `Qt.Popup` que se muestra con `show()`, nunca con
  `exec()`**: con `exec()` quedaba **modal** y el clic en Cerrar no llegaba al controlador
  (se elegía 30 % y "no pasaba nada"). Además se cierra solo en `leaveEvent` (salir con el
  mouse), así el clic siguiente ya cae en el botón. Por debajo del mínimo la bolita vuelve y esa zona se pinta
  apagada; el resumen dice `Cierras: X USDT ≈ N contratos|monedas`. El volumen del cierre
  sale de `forms.volumen_cerrar(hold, pct, paso)`, que el controlador usa igual: floor al
  paso y 100 % exacto (un cierre total no puede fallar por redondeo). El clic y el arrastre los mapea `SliderPct`
  sobre la misma geometría que dibuja: el estilo de Qt usa la caja del handle y el primer
  clic caía en otro valor. El chip `Mercado` y el `%` van sin `▾`, y los segmentados de la
  tarjeta van uno debajo del otro a todo el ancho, como en la Tk.
- El globo de la fee distingue **lo pagado**, **el próximo funding** y **lo que costaría
  cerrar**: `Comisión pagada`, `Funding cobrado` (si > 0), `Fee pagada` (la suma, que es el
  número de la celda), `Fees saved` (si > 0), `Funding hh:mm (tasa%)` con `paga`/`cobra`
  y el importe estimado, y `Al cerrar (taker X %)`.
- El fee viaja en el **mismo payload que el PnL** (se repinta cada 3 s), así que no puede
  quedar viejo: solo **cambia** cuando el broker cobra algo — funding cada 8 h o al cerrar
  una parte. `Session.refresh_fondos` pide la tasa y la hora del próximo funding cada 60 s
  (`mexc.funding` / `bitunix.funding`) y la publica en `("funding", {...})`.
  Ojo con la unidad: MEXC manda `fundingRate` en **fracción** (0.0001) y Bitunix en
  **porcentaje** (`"0.01"`); el módulo de Bitunix lo normaliza a fracción.

- El detalle de la fee es un **bocadillo propio** (`cells.Bocadillo`): ventana sin marco con
  caja redondeada y punta, sale **arriba de la celda y centrado**, apuntando al importe. No
  se usa `QToolTip` (no deja dibujar la punta ni elegir el lado) y así tampoco aparece el
  retardo de ~700 ms: `VistaQt` escucha `entered` y llama a `mostrar()` al entrar.
- La barra de título va oscura con `qt.style.barra_oscura`: `DwmSetWindowAttribute` 20
  (immersive dark; en builds viejas 19) y **`SetWindowPos` con `SWP_FRAMECHANGED`**, porque
  DWM no repinta la barra sola y se veía blanca hasta minimizar y volver. Los atributos 35/36
  (color de barra y de letras) son solo Windows 11 y fallan en Windows 10 sin problema.
- La columna TP/SL de la tabla de órdenes se muestra como MEXC: `TP: Last≥81,000.00` en
  verde y `SL: Last≤71,000.00` en rojo (y `TP: —` / `SL: —` en gris si no hay nivel).
- Las dos líneas vivas del editor de TP/SL también van con color por signo del PnL
  (`<span style>` con `setTextFormat(Qt.RichText)`): verde si gana, rojo si pierde.
- La selección de posiciones se restaura por `positionId` y las filas se **actualizan en
  sitio**: recrearlas cada 3 s reseteaba el `%` de cierre a 100 y cerraba el panel del
  slider, que cuelga de la barra de cierre de la fila.
- **Los widgets de la fila pintan su fondo** (`WA_StyledBackground` + `set_fondo` en
  `CeldaPar`, `CeldaLapiz` y `BarraCierre`): sin eso eran transparentes y en las filas
  impares mostraban el color del viewport, que se veía como cuadros grises distintos. El
  color se re-aplica en cada refresco porque sigue a la **fila**, no al widget: si las
  posiciones se reordenan, el fondo tiene que moverse con ellas.
- **Cada tarjeta elige su broker** con el selector de la cabecera, que muestra el
  **wordmark** (marca + nombre) del broker: `assets/mexc_full.svg` (letras blancas, como el
  original) y `assets/bitunix_full.svg` (marca `#28D2B0`, letras `#E8EAED`, porque Qt no
  resuelve las variables CSS del SVG). Las versiones sin `_full` son solo la marca y se usan
  en el desplegable. La lista sale de `brokers.NOMBRES`/`TITULOS` (compartida con la
  cabecera y el panel `Brokers`), asi que sumar un broker es una linea. Arranca **sin
  broker**: muestra `Broker` y `Elige un broker para
  operar`, con `LONG`/`SHORT` apagados. La elección se guarda por tarjeta en `config.json`
  (`exchange`); las tarjetas viejas sin ese campo se asumen de MEXC. Cambiar de broker **no
  republica** el deck (borraría el tamaño escrito): el contrato se pide al cliente nuevo y
  el precio llega con el siguiente ticker. El menú marca Disponible, Verificando o No
  disponible según los catálogos de futuros; un par no disponible queda deshabilitado y
  cambiar de broker invalida el precio anterior. Si el catálogo no responde, LONG/SHORT
  permanecen deshabilitados hasta poder verificarlo.
- **El deck reusa las tarjetas**: `_pintar_deck` crea solo la nueva y destruye solo la que
  se quitó (antes borraba y recreaba todas, y al añadir un par se perdía lo escrito en el
  tamaño, TP, SL y apalancamiento de las demás cajas).
- **Al borrar una tarjeta, su widget se destruye** (`_quitar_par`: sale del deck, `hide()` y
  `deleteLater()`). Si se solo la saca del mapa, la caja queda pegada en la ventana como
  fantasma y al volver a agregar el mismo par aparecen **dos tarjetas iguales**. Además
  `_pintar_deck` ignora las tarjetas que la sesión ya no tiene (un mensaje atrasado no
  resucita una tarjeta borrada) y nunca crea dos widgets para el mismo id.
- Una tarjeta que no está en el deck **no se arrastra** (`_arrastre_tarjeta` la ignora).
- Las tarjetas se **arrastran en vivo** para reordenarlas. La fila **no usa layout**: las
  tarjetas se colocan a mano en un lienzo (`_lienzo`) a `indice * (286 + 10)`, así cada una
  puede animarse sola. Al arrastrar, la tarjeta agarrada sigue al cursor por encima del
  resto y, cuando su centro cruza el slot de otra, se reordena la lista y **las demás
  animan su `pos`** (`QPropertyAnimation`, 150 ms, `OutCubic`): se ve cómo la arrastrada
  las empuja. Al soltar, la arrastrada anima hasta su slot y el orden queda guardado
  (`Session.mover_tarjeta`). Arranca solo desde la cabecera (primeros 46 px). **Sin hueco
  punteado** y sin `QDrag`: el hueco se veía como un recuadro raro encima de las tarjetas y
  el `QDrag` mostraba una copia flotante con la original quieta.
- **Cada tarjeta tiene un `id`** (`BTC_USDT`, `BTC_USDT#2`, …), así el mismo par puede estar
  en los dos brokers a la vez. El precio se cachea por `id`, no por símbolo, y el ticker
  publica `("ticker", id, broker, precio, cambio)`; descarta resultados de un broker que
  dejó de estar seleccionado. El buscador combina catálogos de futuros; el selector indica
  disponibilidad por broker y no convierte símbolos alternativos automáticamente.
- La cabecera muestra el **USDT disponible de cada broker** con su **wordmark** (`logo(nombre,
  13, completo=True)`), el número y el `USDT` en 13 px **negrita**, separados por
  un `·`; cada 15 s. La lista sale de `BROKERS` y `TITULOS` en `qt/ventana.py`, así sumar un broker
  es una línea. **El número es el saldo en vivo de la cuenta, con el PnL no realizado
  dentro** (el usuario lo quiere ver moverse con las posiciones): MEXC `equity`, Bitunix
  `available + margin + frozen`, BingX `equity`. `available()` sigue devolviendo lo libre y
  no es lo que se pinta: mostrarlo hacía parecer roto el saldo (14,79 de 313,24 con una
  posición abierta).
- En la barra de **Posiciones** se ve el **PnL bruto y neto de todas las posiciones** (`Bruto
  +X · Neto +Y`, con tooltip del desglose): neto = bruto − comisión pagada − funding cobrado −
  salida estimada (taker). Sale de `mexc.neto_posicion()` / `mexc.resumen_pnl()` (puras).
  Las filas no cambian.
- El botón **Poner a BE** abre un modal con una fila por posición: checkbox, broker, lado,
  entrada/precio/BE y PnL; las que no se pueden (el BE no quedó del lado de la pérdida, o ya
  está puesto) salen **apagadas con el motivo**. `Todos` marca los seleccionables y el botón
  ejecuta solo los marcados, conservando el TP actual (`Control.be_todas` → `_aplicar_tpsl`,
  el mismo camino del lápiz, con 600 ms entre posiciones).
- La **IP** se consulta al arrancar y se **revalida cada 15 min** (`IP_SEG`) desde el poller,
  porque la key de MEXC/Bitunix está atada a la IP y el ISP la rota: la cabecera avisa sola.
- En la tabla de posiciones la columna del par lleva el ticker y, debajo, el **wordmark del
  broker** a 12 px (`CeldaPar`), así se ve de un vistazo de dónde es cada posición.
- El **historial** es una fila por **operación**, no por orden: `operaciones.py` empareja
  aperturas y cierres. MEXC trae `positionId` (agrupa exacto); Bitunix no lo trae en el
  historial, así que se usa una cola FIFO por (exchange, símbolo, lado) con `reduceOnly`
  para saber si una fila abre o cierra. Un cierre que no encuentra apertura (posición
  anterior a la ventana de 50 órdenes) sale como fila `Cerrada` con entrada `—`.
  Columnas en `OPER_COLS` (`layout.py`): apertura, cierre, par (con el wordmark del broker
  vía `CeldaPar` compacta), lado, **tamaño en USDT** (`cantidad × entrada`, `qt/formato.py`),
  entrada, salida, PnL, fee, neto (`pnl.neto_operacion`) y estado.
  `Session.cargar_historial` mezcla los dos brokers y publica ya agrupado.
- Las operaciones se **guardan en `operaciones.json`** (`archivo.Archivo`): `cargar_historial`
  fusiona lo que trae el broker con lo archivado y publica el resultado, así que lo que ya
  no existe en el exchange sigue en la tabla. Al arrancar, `Session.__init__` publica el
  archivo de una vez (sin red) y después el refresco agrega lo nuevo.
- La pestaña **Calendario** agrega esas mismas filas por día (`calendario.py`, puro; la vista
  vive en `qt/calendario.py` y no calcula nada). Las reglas, que no se deben cambiar sin
  actualizar los tests:
  - **Solo cuenta la operación con cierre** (`cierre > 0`): las abiertas no cuentan.
  - **El día es la fecha local del último cierre** (la del sistema: en la máquina del
    usuario es America/Lima, UTC-5). Es la misma conversión que usa la columna *Cierre* del
    Historial, así que el calendario nunca contradice a la tabla. `zoneinfo` no se usa: en
    Windows sin el paquete `tzdata` no hay base de datos IANA.
  - **Neto = `pnl.neto_operacion(pnl, fee)`** (PnL − comisión), igual que la columna Neto del
    Historial. Un rebate (fee negativa) suma. **El neto no incluye el funding**: la fee del
    Historial es solo comisión, y la vista lo aclara debajo de las métricas.
  - **Una operación cerrada en partes cuenta entera el día de su último cierre** (limitación
    conocida: el PnL de una parcial no se reparte entre los días en que se cerró).
  - **Solo cuenta lo que la app ya cargó**: el calendario no pide nada a la red. El botón
    *Cargar más historial* reutiliza la paginación del *Ver más* (`session.cargar_historial
    (mas=True)`), y lo que llega se guarda en `operaciones.json`.
  - Métricas del mes: **win rate** por operación (netas ganadoras ÷ totales), **profit
    factor** (Σ netas positivas ÷ |Σ netas negativas|), **rachas** de días **consecutivos de
    calendario** (un día sin operaciones interrumpe la racha), **drawdown máximo** sobre la
    curva acumulada diaria (se muestra negativo) y **totales por semana** (lunes a domingo,
    contando solo los días del mes visible).
  - El **CSV** sale con `;` como separador y punto decimal (así lo abre Excel en español) y
    termina en una fila `TOTAL`. El botón *Ocultar montos* reemplaza los importes por `••••`
    en la vista; el CSV siempre lleva los números reales.
  - **El mes es una tabla, no 42 tarjetas**: `DelegadoMes` pinta número de día + PnL sobre la
    superficie `SURFACE` con `gridline-color: LINE`. **Sin fondo de color por día**: el color
    va en el número del PnL (`GREEN`/`RED`), así que no se mezclan fondos y el día negativo
    no se lee como error. El delegado **no rellena la celda entera** (si no, tapa los
    separadores): solo el tinte del día elegido (`INPUT`) y el de hover.
  - **El día de hoy** lleva un círculo `ACCENT_SOFT` detrás del número, no color de PnL: el
    verde ya significa ganancia. El **conteo de operaciones** no ocupa la celda (la 3.ª línea
    era ruido): va al tooltip (`Qt.ToolTipRole`) y al detalle de abajo.
  - **La altura de la grilla es fija** (`CAL_ALTO_CABECERA + filas × CAL_ALTO_DIA`): sin eso
    el `QScrollArea` estira la tabla y las filas crecen hasta el alto del panel. El área de
    pestañas son ~403 px con la ventana de 1000 px, y con dos tarjetas el contenido entra
    justo (sin scroll). Al elegir un día el detalle cae bajo el pliegue y la vista **baja
    sola** (`_cal_bajar`, diferido con `singleShot`: el scrollbar todavía no conoce la altura
    nueva).
  - Las siete columnas del mes miden 88 px (`CAL_ANCHO_DIA`); la grilla tiene ancho fijo,
    no muestra scroll interno y queda pegada a la izquierda junto al panel. En ventanas angostas,
    el `QScrollArea` exterior muestra el scroll horizontal; el neto diario se elide si no cabe.
  - El panel son **dos tarjetas**: *Neto del mes* (número grande + operaciones/win rate +
    `CurvaMes`, la polilínea de `cal.curva()`) y *Resumen del mes* (métricas, brokers con
    wordmark, semanas y la nota del funding). La curva se pinta en verde o rojo según el
    acumulado final y marca el cero si lo cruza.
- El historial viene **paginado** (`HISTORIAL_PAGINA = 50` órdenes por broker): la página 1
  se refresca sola cada 15 s y el botón **Ver más** pide la siguiente de cada broker
  (`mexc.history(size, pagina)` → `page_num`, `bitunix.history(limite, salto)` → `skip`).
  Las órdenes se acumulan en `Session._hist_ordenes` con clave `(broker, orderId)`, así el
  refresco actualiza los campos de una orden ya vista y `history_mas` apaga el botón cuando
  un broker devuelve menos de 50. Con una página sola se veían ~1 mes de operaciones: por
  eso "llegaba hasta setiembre".
- **Paginación (trampa resuelta)**: el refresco automático pide siempre la **página 1** y
  **no** reinicia `_hist_pagina` (antes lo hacía y `Ver más` volvía a pedir la misma página:
  parecía que no traía nada). Un candado (`_hist_candado`) descarta la carga que llegue
  mientras otra está en vuelo. `history_cargando` (true/false) maneja el **spinner**
  (`cells.Spinner`, un arco girando con `QTimer`) y el texto `Cargando…` del botón.
  Al repintar se conserva el **scroll** (`verticalScrollBar().value()`), así las filas
  nuevas quedan abajo y la vista no salta.
- Las celdas con lápiz se reasignan en cada refresco (`CeldaLapiz.set_accion`): la acción
  tiene que resolver la fila viva (`_posicion(fila)`), no cerrar sobre el dict que existía
  al crear el widget. Así se abrió el editor con un TP que ya se había borrado.
- La columna TP / SL de posiciones muestra `81,000.00 / 71,000.00`, y `--` en el lado que
  no tiene nivel (`-- / 71,000.00`, `-- / --`): los guiones se llenan solos. `set_partes`
  **crea etiquetas si hacen falta**: antes la celda se construía con un solo valor y al
  aparecer el TP (1 → 3 valores) no había dónde dibujarlo y se perdía.

---

