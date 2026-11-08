# Design system: tokens, patrones y reglas visuales

Público: agentes o humanos que toquen cualquier UI de trade-desk.
UI de trading oscura: densidad de información y legibilidad numérica antes que decoración.
Mismo lenguaje visual que la app Android *DeFi Tracker* (`docs/DESIGN.md` de ese repo),
adaptado a escritorio.

> Las reglas están en `AGENTS.md`. Este documento es el inventario: qué token existe,
> dónde vive y qué está fuera de norma. Si los dos se contradicen, gana `AGENTS.md`.

---

## 1. No negociables

- **Fuente única de tokens: `theme.py`.** No agregues colores, fuentes o radios ad hoc.
  Los SVG de marca conservan sus colores propios y la barra DWM de Windows requiere valores
  equivalentes en la llamada nativa.
- **Todo en `Geist`.** Los números usan `theme.NUM`, que apunta a la misma familia.
  Se probó `Geist Mono` para tener cifras tabulares, pero es ~19 % más ancho; como los
  números van alineados a la derecha, el borde derecho queda fijo y no hace falta tabular.
- **Sin decoración:** ni gradientes, sombras ni emojis decorativos. La única animación
  funcional actual es el reordenamiento del deck (150 ms, `OutCubic`); no agregues movimiento
  ornamental.
- Todo número pasa por `theme.fmt_price / fmt_pnl / fmt_fee / fmt_usdt / fmt_qty / fmt_pct`.
- Los errores de API se muestran; no se convierten en estados vacíos.

---

## 2. Color (`theme.py`)

Superficies y texto:

| Token | Valor | Uso |
|---|---|---|
| `BG` | `#0A0A0A` | fondo de la ventana |
| `SURFACE` | `#121212` | cabecera de tabla |
| `CARD` | `#1A1D23` | tarjetas, filas pares |
| `INPUT` | `#1E2026` | inputs, chips, botones secundarios |
| `LINE` | `#2A2E35` | bordes de tarjeta y divisores |
| `BORDER` | `#3A3F47` | contornos de control, hover |
| `TEXT` | `#E8EAED` | texto principal |
| `MUTED` | `#9AA0A8` | etiquetas, texto secundario, valor neutro |

Semánticos:

| Token | Valor | Uso |
|---|---|---|
| `GREEN` | `#1ECB81` | LONG, PnL no negativo, conectado |
| `RED` | `#F6465D` | SHORT, PnL negativo, costo, error |
| `GOLD` | `#FFD60A` | DRY-RUN, advertencias |
| `SELECT` | `#243044` | selección de texto en listbox |
| `ACCENT_SOFT` | `#26405F` | segmento activo, preset activo, botón primario suave |
| `ROW_ALT` | `#16191F` | fila alterna de tabla |
| `GREEN_HOVER` / `RED_HOVER` | `#18B374` / `#E03A50` | hover de los botones llenos |
| `ON_GREEN` / `ON_RED` | `#04140D` / `#150508` | texto oscuro sobre verde / rojo |
| `DANGER_SOFT` / `DANGER_SOFT_HOVER` | `#3A1A1E` / `#4A2226` | acciones destructivas suaves: `CERRAR TODO`, `Cancelar todo` |

`ACCENT_SOFT` existe porque un segmento activo del color del input se leía como
"no seleccionado". No volver a usar `INPUT` para el estado activo.

Para el Calendario, `theme.mezclar(color, fondo, alfa)` mezcla dos hex (la usa `CurvaMes`
para el relleno de la curva) y el círculo del día de hoy usa `ACCENT_SOFT`. Es la única
forma de obtener un color nuevo: nada de colores literales en la vista. **No hay fondo de
color por día**: el PnL se pinta en el número, no en la celda.

---

## 3. Tipografía

- `Geist` (regular/medium/semibold/bold) — se registra con `AddFontResourceExW` (FR_PRIVATE)
  y, para que Qt/DirectWrite la encuentre, también con
  `QFontDatabase.addApplicationFont` en `qt/style.py::cargar_fuentes()` antes de crear widgets.
  No se instala en Windows.
- `theme.NUM` = `Geist`. **No es tabular** (`1111` mide 28 px, `8888` 40 px), pero las
  columnas numéricas van alineadas a la derecha, así que el borde derecho no se mueve.
- Fallback: la familia del sistema si Geist no está disponible.

| Rol | Fuente | Tamaño |
|---|---|---|
| Marca | Geist bold | 14 |
| Título de diálogo | Geist bold | 15 |
| Precio de tarjeta | Geist bold | 24 |
| Etiqueta | Geist | 10–13 |
| Tabla | Geist | 13 (negrita en Mark price, Posición, PnL, Par, Lado) |
| Botón principal | Geist bold | 14 |

Los tamaños se piden con `qt/style.py::fnt(size, bold)`, que los devuelve en **píxeles**
(como CustomTkinter), no en puntos: un `13` suelto serían 13 pt (≈17 px) y rompería la
tipografía.

---

## 4. Formas y espaciado

- Radios: `R_CHIP = 6`, `R_CTRL = 8`, `R_CARD = 12`.
- Padding interno de tarjeta: 12 px. Padding de ventana: 16 px.
- Tarjeta de operación: **286 px de ancho, 436 px de alto** (fija). `LONG` y `SHORT` van en
  la misma fila; apilados costaban 40 px que ahora usa la tabla.
- Filas de tabla: **56 px** (posiciones: PnL en dos lineas, fee en tres y la barra de
  cierre en dos de 22/26 px, todo centrado verticalmente sin tocar los bordes), 54 px
  (ordenes: par con el % llenado debajo y TP/SL en dos lineas) y 38 px (historial).
  Cabecera: 36 px. Los altos están en `layout.py` (`ROW_H`, `ORDER_ROW_H`) y se usan tal cual:
  Qt ya trabaja en píxeles, no hay escala DPI que aplicar.
- Ventana: tamaño inicial **1800 × 1000**; no se declara un tamaño mínimo. La fila de
  posiciones suma **1622 px** (30 del checkbox + 1392 de columnas + 200 de acciones); al
  reducir la ventana, la tabla puede recortar la última columna (no hay scroll horizontal).
---

## 5. Componentes

| Componente | Archivo | Notas |
|---|---|---|
| `VistaQt` | `qt/ventana.py` | arma cabecera, deck, barra de estado y las cuatro pestañas |
| pestaña Posiciones | `qt/tabla_posiciones.py` | mixin: filas, resumen bruto/neto y globo de la fee |
| pestaña Órdenes | `qt/tabla_ordenes.py` | mixin: órdenes abiertas, panel estilo MEXC |
| pestaña Historial | `qt/tabla_historial.py` | mixin: una fila por operación, con su neto |
| pestaña Calendario | `qt/calendario.py` | mixin: mes en cuadrícula, métricas del período y detalle del día |
| `calendario.py` | `calendario.py` | módulo puro: agrega el historial por día, calcula las métricas y arma el CSV |
| `Tarjeta` | `qt/tarjeta.py` | par + apalancamiento + margen + tamaño (+ chip `Mercado`) + TP/SL + LONG/SHORT |
| `BarraCierre` | `qt/cierre.py` | precio (Mercado / límite), % de la posición y los dos botones de la fila |
| `Tarjeta` / `BarraCierre` (formularios) | `forms.py` | parseo puro de lo escrito; nada de widgets |
| `EditorOrden` | `qt/editor_orden.py` | editor de la orden: lado, apalancamiento, margen, precio y TP/SL |
| `Modal`, `confirm`, `show`, `form`, `ask_key` | `qt/dialogos_base.py` | diálogos propios, borderless, sin `QMessageBox` |
| `QtPort` | `qt/port.py` | `UiPort` que usa `controller.Control` |
| `tabla` + `DelegadoCeldas` | `qt/cells.py` | tabla, celdas compuestas con color, spinner y bocadillo |
| `BuscarPar` | `qt/search.py` | buscador modal, `Enter` toma el primero |
| `Segmentado`, `boton`, `etiqueta`, `qss` | `qt/style.py` | factories de widgets, para no repetir estilos |
| `cuando`, `tamano_usdt` | `qt/formato.py` | fecha de las celdas y tamaño en USDT del historial |

**Estructura de la fila de posiciones**

| Celda | Contenido |
|---|---|
| `Par` | nombre de MEXC (`GOLD(XAU)USDT`, de `baseCoinName + quoteCoin`), 13 bold |
| `Lado` | `10X LONG` verde / `5X SHORT` rojo (apalancamiento incluido) |
| `Apertura` | `dd/mm hh:mm` en `MUTED`, de `createTime` de `open_positions` |
| `Posición` | nocional con su unidad: `4,990.76 USDT`, bold |
| `Entrada`, `Mark price` | precio con los decimales del contrato (`fmt_price_exact`, mínimo 2): `3,900.75`; Mark price verde/rojo contra la entrada |
| `Liquidación` | precio igual que Mark price, en `GOLD` |
| `Margin ratio` | `0.50%`; `GOLD` desde 20 %. La cabecera dice **Margin ratio**, no `Margen %` |
| `Margen` | `500.69 USDT` bold + lápiz; la unidad va en el valor, no en la cabecera |
| `PnL` | dos líneas: `-6.0976 USDT` en 13 bold y `ROE` (`-1.22%`) en `MUTED` 11 |
| `Fee · %mrg / pos` | Total en 13 bold, rojo si no es cero y gris si es cero, **con subrayado punteado**, `0.30% / 0.03%` en `MUTED` 11 (parte del margen y del nocional) y `ahorro 1.7489` en `GREEN` 11. El total es **comisión + funding** (`mexc.fee_desglose`): `totalFee` = comisión cobrada al abrir y `holdFee` = funding; `lowSaveTotalFee` es "Fees saved" y **no** suma. Al entrar a la celda, `qt/cells.py::Bocadillo` muestra un panel inmediato con `Comisión pagada / Funding cobrado / Fee pagada / Fees saved / próximo funding / costo estimado de cierre`. Ojo: el terminal de MEXC pinta su "Fees" como `totalFee + lowSaveTotalFee`, así que allí el número es más alto |
| `TP / SL` | todo alineado a la derecha: `3,990.5 / 3,880.2`, o `TP 3,990.5`, o `SL 3,880.2`, o `—`; lápiz al final |

La fila mide 56 px y cada celda queda centrada verticalmente sin tocar los bordes: las líneas
se dibujan con el delegado, que centra el bloque de 1 a 3 líneas dentro de la fila (el alto de
cada línea sale del `QFontMetrics`). El modo de margen (aislado/cruzado) no se muestra en la
fila: se deduce del lápiz de margen, que aparece deshabilitado en cruzado.

**Reglas de la tabla**
- `QTableWidget` con `DelegadoCeldas`: las celdas simples pintan varias líneas con colores
  distintos (`lineas`), y las celdas con lápiz llevan un widget propio.
- La prueba anterior con `ttk.Treeview` se descartó porque no permite color por celda; en Qt
  el delegado resuelve lo mismo sin widgets por celda.
- **La cabecera hereda la alineación de su columna**: texto a la izquierda (`Par`, `Lado`,
  `Apertura`), números a la derecha. No se centra: centrar deja el título flotando sobre
  un dato pegado al borde y se lee peor.
- **Columnas con lápiz (`margen`, `tpsl`)**: el lápiz va al final de la celda, dentro de los
  6 px de padding. La cabecera **no** reserva ese hueco: el título de esas dos columnas
  termina ~20 px a la derecha del valor (está en la deuda visual de §8).
- Anchos: `par 132 · lado 96 · apertura 84 · pos 112 · entrada 94 · mark 94 · liq 100 ·
  ratio 98 · margen 132 · pnl 122 · fee 140 · tpsl 188` (1392 px de columnas). `Lado` está
  en 96 porque `100X SHORT` ocupa ~81 px y con 74 se cortaba en `10X SHOR`; `Par` en 132 para que entre `GOLD(XAU)USDT` (107); `Posición` en 112 por el
  sufijo `USDT` (108 en el peor caso); `Apertura` en 84 (74 reales); `TP / SL` en 188
  (110 del par de precios + 24 del lápiz + separador).
- La selección se restaura por `positionId` en cada refresco del poller.
- Columna de acciones (200 px): `BarraCierre` en dos líneas dentro de los 190 útiles.
  Línea 1: `[Mercado]` (106) + `[100%]` (78). Línea 2: `[Cerrar LONG/SHORT]` (102) +
  `[Reverse]` (82). El botón de cerrar toma el color del PnL (verde, rojo o gris) y el texto
  lleva el lado; el marcado del lado en la fila (`Lado`) no cambia.
  Los lápices viven dentro de su celda (Margen y TP/SL).
- El lápiz se dibuja con `QPainter` sobre un `QPixmap` de 20 px (`qt/cells.icono_lapiz`):
  cuerpo inclinado 135°, banda y punta. Sin glifo Unicode (evita tofu y look genérico).

**Reglas de las tarjetas**
- Fila horizontal con scroll; `+ Añadir par` agrega a la derecha.
- Ancho fijo de 286 px y alto fijo de 436 px (`setFixedSize`), como antes: el deck no se
  reajusta al contenido.
- La ✕ de quitar va en la cabecera, a la derecha del nombre.

---

## 6. Formatos numéricos (`theme.py`)

| Función | Salida | Uso |
|---|---|---|
| `fmt_price` | `78,549.5` / `2,239.10` / `0.90560` | resúmenes, precios de referencia e historial |
| `fmt_price_exact` | `3,900.75` | posiciones (Entrada, Mark price y Liquidación; respeta escala con mínimo 2 decimales), precios de órdenes límite y TP/SL: lo que se ve en órdenes es lo que se envía |
| `fmt_pnl` | `+12.4021` / `-3.1502` | PnL, signo siempre, 4 decimales |
| `fmt_fee` | `0.1997` | comisiones, 4 decimales |
| `fmt_usdt` | `502.11` / `+502.11` | márgenes, nocional |
| `fmt_qty` | `127` / `0.0134` | contratos y cantidades |
| `fmt_pct` | `+1.24%` / `-3.92%` | variación 24h |
| `fmt_share` | `0.20%` / `<0.01%` | parte de un total (fee sobre margen y nocional), sin signo |
| `qt.formato.cuando` | `30/10 12:11` | fecha de las celdas de posiciones, órdenes e historial; fuera de `theme` porque es fecha, no número |

Reglas de color en tablas:

| Celda | Regla |
|---|---|
| PnL en Posiciones | `>= 0` verde · `< 0` rojo |
| Fee en Posiciones | distinto de cero rojo · cero gris |
| Fee en Historial | positivo rojo (costo) · cero o negativo gris |
| Mark price | verde si va ganando vs entrada, rojo si perdiendo, gris si falta |
| Lado | LONG verde · SHORT rojo |
| Dirección (órdenes) | compra (lado 1, 2) verde · venta (lado 3, 4) rojo |
| Llenado (órdenes) | algo llenado en `GOLD`, nada en `MUTED` |
| Estado (órdenes) | `Sin llenar` / `Pendiente` en `TEXT`, el resto en `MUTED` |
| Estado (historial) | `Cerrada` verde · `Parcial` dorado · otros estados gris |

**Estructura de la fila de órdenes abiertas** (54 px, `qt/tabla_ordenes.py`, imita el panel de MEXC)

| Celda | Contenido |
|---|---|
| `Par` | nombre de MEXC + `Perpetual` en gris; debajo el % llenado (`0.00%`) |
| `Fecha` | `2026-10-30 23:52:10` (con segundos, como MEXC) |
| `Dirección` | `Compra LONG` / `Venta SHORT` / `Cierra SHORT` / `Cierra LONG` |
| `Apal.` | `10X`, del color de la dirección |
| `Monto` | nocional con el `contractSize` del par: `100.00 USDT` + lápiz |
| `Precio` | precio límite con los decimales del contrato (`fmt_price_exact`) + lápiz |
| `Llenado` | `dealVol/vol`: `0/5` |
| `Margen usado` | `orderMargin` de la orden: `10.16 USDT` |
| `TP / SL` | dos líneas: `TP 2,500.00` verde y `SL 1,500.00` roja, con lápiz |
| `Fee (USDT)` | comisión de la orden (`totalFee`), 4 decimales |
| `Estado` | `Sin llenar` (state 2) / `Pendiente` / `Cancelada`… |
| `Acción` | `[Modificar]` y `[Cancelar]` (84 px cada uno); arriba a la derecha, `[Cancelar todo]` con el color de peligro |

Los tres lápices (Monto, Precio y TP/SL) abren el mismo **editor de orden**, como en MEXC.
Las órdenes de cierre (lado 2/4) no se pueden reenviar: `Modificar` avisa que solo se puede
cancelar. Las condicionales TP/SL de BingX se muestran y se pueden cancelar, pero no tienen
lápices ni acción `Modificar` desde esta pestaña. La tabla se actualiza con el poller (cada 3 s).

### Pestaña Calendario

Un mes en cuadrícula con el resultado de cada día. Todo el contenido sale de las mismas
filas que pinta el Historial: **la pestaña no pide nada a la red**.

El mes es **una tabla** (`QTableWidget` + `DelegadoMes`), no una tarjeta por día: una sola
superficie `SURFACE` con separadores de pelo en `LINE` y encabezado `Lun Mar…` sobre
`SURFACE`. Esto es a propósito: 42 cajas con borde se leían como 42 tarjetas sueltas y el
color de fondo competía con el texto.

| Pieza | Detalle |
|---|---|
| Celda del día | número del día (14 px, negrita, `TEXT`; `MUTED` si no tiene operaciones) y debajo su **neto** (13 px, negrita, `GREEN`/`RED`, `theme.fmt_pnl`). El color va **en el número**, nunca en el fondo |
| Día de hoy | círculo de 11 px de radio en `ACCENT_SOFT` detrás del número (azul, para no confundirse con la semántica verde/rojo del PnL) |
| Día elegido | tinte de fondo `INPUT`; **hover** en `SURFACE`. El delegado no pinta el resto de la celda: si rellenara todo, taparía los separadores |
| Fuera de mes | celda vacía (sin número ni importe) |
| Ancho | siete columnas fijas de 88 px (`CAL_ANCHO_DIA`); la grilla no se estira con la ventana |
| Neto diario | una línea; si no cabe en 88 px, se elide a la derecha y el tooltip conserva el neto completo |
| Conteo de operaciones | ya no está en la celda: va al tooltip al pasar el mouse (`04 nov · 7 operaciones · -443.6607`) |
| Altura | fija: `CAL_ALTO_CABECERA + filas × CAL_ALTO_DIA` (`layout.py`). Si no, el `QScrollArea` estira la tabla y las filas crecen hasta el alto del panel |
| Tarjeta **Neto del mes** | número grande (18 px, coloreado) + `59 operaciones · 38.98% win rate` + `CurvaMes`, la polilínea de `cal.curva()` (28 px, verde o rojo según el acumulado final, con la línea del cero marcada si la cruza y un punto en el último valor) |
| Tarjeta **Resumen del mes** | seis filas etiqueta/valor (mejor día, peor día, profit factor, drawdown, rachas, fees), un pelo separador, el desglose por broker (wordmark + cantidad + neto), los totales por semana (enriquecido, verde/rojo) y la nota del funding |
| Detalle del día | tabla con `CAL_COLS` (`layout.py`): par (con wordmark), lado, entrada, salida, PnL, fee, neto y hora de cierre. Va debajo de la cuadrícula, a lo ancho. Al elegir un día la vista **baja sola** hasta él |
| Barra | `‹ Mes ›`, `‹ Año ›`, **Hoy**, filtros de broker y par (menús con el mismo estilo del selector de la tarjeta), **Ocultar montos**, **Exportar CSV** y **Cargar más historial** |

- El **neto** es `pnl.neto_operacion(pnl, fee)`: la misma cuenta que la columna Neto del
  Historial. **No incluye el funding** (la fee del Historial es solo comisión) y la vista lo
  dice debajo de las métricas.
- Los **totales por semana** van de lunes a domingo y cuentan solo los días del mes visible.
- **Ocultar montos** reemplaza los importes por `••••` (también vacía la curva, para que la
  forma no filtre el monto); el CSV siempre lleva los números reales.
- El **CSV** sale con `;` como separador y punto decimal, con una fila por operación y una
  fila `TOTAL` al final. El destino lo elige el usuario (diálogo *Guardar como*).
- La pestaña vive en un `QScrollArea`: con la ventana de 1800×1000 el área de pestañas queda
  en ~403 px y el mes (318 px con seis semanas) entra entero. Con un día elegido el detalle
  cae bajo el pliegue y se baja solo. La grilla y el panel quedan alineados a la izquierda;
  el espacio restante queda a la derecha. Si la ventana es demasiado angosta, desplaza el
  contenido con el scroll horizontal exterior en vez de estirar o romper las celdas.
- Los estados **vacío** y **cargando** son en línea (una etiqueta y el `Spinner` de `cells.py`),
  nunca un modal.

**Editor de orden** (`qt.dialogs.EditorOrden`, 420 px de ancho)

- Título `Modificar orden`, el par en gris debajo y ✕.
- Aviso en `GOLD`: se cancela la orden y se envía una nueva (MEXC no permite editar).
- `Dirección` con `Segmentado` LONG/SHORT; luego `Apalancamiento` (`x`),
  `Margen` (`USDT`), `Precio límite`, `TP` y `SL`, todos con etiqueta a la izquierda.
- Línea viva `≈ 5 contratos · 100.00 USDT nocional` (se recalcula al escribir).
- Pie: `[Cancelar]` y `[Guardar y reenviar]` (verde). El error se explica en una línea roja.
- El margen inicial es `nocional / apalancamiento` (`mexc.margen_inicial`), **no**
  `orderMargin` (que incluye comisión): guardar sin tocar nada reenvía la misma orden.

---

## 7. Ventanas flotantes

- Diálogos y buscador son `QDialog` con `FramelessWindowHint`, borde de 1 px (`LINE`) y
  esquina de tarjeta; se centran sobre la ventana padre y son modales.
- Siempre llevan ✕ propia y responden a `Escape`; el diálogo responde a `Enter`.
- Los chips `Mercado` y `%` de la fila abren un `QMenu` y, para el valor libre, el
  formulario propio. El precio y el porcentaje **no se guardan**: una límite vieja aplicada
  a un precio nuevo es peligrosa.
- Nada de `QMessageBox` (queda gris y fuera del estilo).

### Diálogo TP / SL

- Lo abre el lápiz de la celda TP/SL con `qt.dialogs.editar_tpsl`, que envuelve `_Formulario`
  con dos extras: `extras=((texto, comando, habilitado), ...)` (botones a la izquierda de
  Cancelar; el comando recibe el propio diálogo) y `resumen=callable(campos)` (línea gris
  bajo los campos, se repinta con cada tecla).
- `Break-even` rellena el **SL** y se habilita solo si el precio de marca ya pasó el
  break-even (`>` en LONG, `<` en SHORT). El precio va sin separador de miles: el campo
  se convierte con `float()`.
- Debajo de los campos, `TP <precio> → +x.xxxx USDT` y `SL <precio> → -x.xxxx USDT` con
  lo que se gana o pierde si se ejecuta (PnL bruto, sin fees).
- El break-even cubre comisión de entrada + funding ya cobrado + comisión de salida
  estimada (la tasa efectiva del `totalFee` aplicada al nocional del propio break-even);
  su línea muestra `→ +x.xxxx USDT` y `neto 0`.

---

## 8. Deuda visual conocida

- El título de `Margen` y `TP / SL` no queda alineado con el valor: la celda reserva ~26 px
  al final para el lápiz y la cabecera no.
- El scroll horizontal de tarjetas no responde a la rueda sin `Shift`.
- La tabla de Posiciones reconstruye sus filas en cada refresco (cada 3 s); si el volumen de
  posiciones crece, evaluar actualización por fila. El Historial ya compara IDs y snapshots:
  no repinta si nada cambió, actualiza o mueve solo las filas afectadas y conserva el scroll.
  Los pixmaps de logos tienen caché (`qt/style.py::logo`, máximo 32 entradas). En una medición
  local con 153 filas, el repintado completo equivalente fue ~167 ms y el caso sin cambios
  ~0,13 ms; no son garantías de rendimiento ni incluyen red.
- La fee es una estimación: MEXC devuelve `takerFeeRate` distinto entre llamadas.
- Los tests automáticos actuales no crean ventanas reales; los widgets se revisan con
  `tools/smoke_live.py` y capturas. Si se agregan pruebas GUI, verificar el ciclo de vida Qt
  en Windows/Python 3.14: se observó un fallo al cerrar una ventana en ese entorno.
