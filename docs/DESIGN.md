# Design system: tokens, patrones y reglas visuales

Público: agentes o humanos que toquen cualquier UI de trade-desk.
UI de trading oscura: densidad de información y legibilidad numérica antes que decoración.
Mismo lenguaje visual que la app Android *DeFi Tracker* (`docs/DESIGN.md` de ese repo),
adaptado a escritorio.

> Las reglas están en `AGENTS.md`. Este documento es el inventario: qué token existe,
> dónde vive y qué está fuera de norma. Si los dos se contradicen, gana `AGENTS.md`.

---

## 1. No negociables

- **Fuente única de tokens: `theme.py`.** Ningún color, fuente o radio fuera de ahí.
- **Todo en `Geist`.** Los números usan `theme.NUM`, que apunta a la misma familia.
  Se probó `Geist Mono` para tener cifras tabulares, pero es ~19 % más ancho; como los
  números van alineados a la derecha, el borde derecho queda fijo y no hace falta tabular.
- **Sin decoración:** ni gradientes, ni sombras, ni emojis decorativos, ni animaciones.
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
| `GREEN` | `#1ECB81` | LONG, PnL positivo, fee negativa (rebate), conectado |
| `RED` | `#F6465D` | SHORT, PnL negativo, fee positiva (costo), error |
| `GOLD` | `#FFD60A` | DRY-RUN, advertencias |
| `BLUE` | `#2196F3` | reservado (no usado) |
| `SELECT` | `#243044` | selección de texto en listbox |
| `ACCENT_SOFT` | `#26405F` | segmento activo, preset activo, botón primario suave |
| `SELECT_SOFT` | `#1B2534` | reservado para hover de fila |
| `ROW_ALT` | `#16191F` | fila alterna de tabla |
| `GREEN_HOVER` / `RED_HOVER` | `#18B374` / `#E03A50` | hover de los botones llenos |
| `ON_GREEN` / `ON_RED` | `#04140D` / `#150508` | texto oscuro sobre verde / rojo |
| `DANGER_SOFT` / `DANGER_SOFT_HOVER` | `#3A1A1E` / `#4A2226` | acciones destructivas suaves: `CERRAR TODO`, `Cancelar todo` |

`ACCENT_SOFT` existe porque un segmento activo del color del input se leía como
"no seleccionado". No volver a usar `INPUT` para el estado activo.

---

## 3. Tipografía

- `Geist` (regular/medium/semibold/bold) — registrada en el proceso con
  `AddFontResourceExW` (FR_PRIVATE); no se instala en Windows.
- `theme.NUM` = `Geist`. **No es tabular** (`1111` mide 28 px, `8888` 40 px), pero las
  columnas numéricas van alineadas a la derecha, así que el borde derecho no se mueve.
- Fallback: `Segoe UI` (`theme.resolve_fonts`).

| Rol | Fuente | Tamaño |
|---|---|---|
| Marca | Geist bold | 18 |
| Título de diálogo | Geist bold | 16 |
| Precio de tarjeta | Geist bold | 19 |
| Cambio 24h | Geist | 12 |
| Etiqueta | Geist | 10–13 |
| Input de tamaño | Geist bold | 15 |
| Tabla | Geist | 13 (negrita en Mark price, Posición, PnL, Par, Lado) |
| Botón principal | Geist bold | 14–16 |

Los widgets nativos de las tablas (`tk.Label`) no aceptan los tamaños de CustomTkinter: la
fuente se pide con `theme.num_font(size, bold)` / `theme.ui_font(...)`, que la devuelven en
**píxeles** y ya escalada (`size` negativo). Un `13` suelto en un `tk.Label` serían 13 **pt**
(≈17 px) y rompería la tipografía.

---

## 4. Formas y espaciado

- Radios: `R_CHIP = 6`, `R_CTRL = 8`, `R_CARD = 12`.
- Padding interno de tarjeta: 12 px. Padding de ventana: 16 px.
- Tarjeta de operación: **286 px de ancho, 436 px de alto** (fija). `LONG` y `SHORT` van en
  la misma fila; apilados costaban 40 px que ahora usa la tabla.
- Filas de tabla: **56 px** (posiciones: PnL en dos lineas, fee en tres y la barra de
  cierre en dos de 22/26 px, todo centrado verticalmente sin tocar los bordes), 54 px
  (ordenes: par con el % llenado debajo y TP/SL en dos lineas) y 38 px (historial).
  Cabecera: 36 px. Los altos pasan por `theme.px()` (escala DPI de CustomTkinter).
- Ventana: **1800 × 1000** por defecto, mínimo **1760 × 860**. La fila de posiciones mide
  1696 px; con menos de 1760 la tabla recorta la última columna en silencio (no hay scroll
  horizontal).
---

## 5. Componentes

| Componente | Archivo | Notas |
|---|---|---|
| `build_ui` | `ui.py` | arma cabecera, tarjetas, barra de estado y las tres pestañas |
| `TradeCard` | `cards.py` | par + apalancamiento + margen + tamaño (+ chip `Mercado ▾`) + TP/SL + LONG/SHORT |
| `PositionsTable` | `table.py` | celdas compuestas con color, checkbox y `CloseBar` |
| `OpenOrdersTable` | `orders.py` | órdenes límite sin llenar, estilo panel de MEXC; lápiz, `Modificar` y `Cancelar` |
| `OrderEditor` | `orders.py` | editor de la orden: lado, apalancamiento, margen, precio y TP/SL |
| `CloseBar` | `closebar.py` | precio (Mercado / límite), % de la posición y los dos botones de la fila |
| `_PercentPopup` / `PricePopup` | `closebar.py` | paneles flotantes anclados al control que los abre (cierre y tarjeta de apertura) |
| `Pencil` | `table.py` | lápiz dibujado en `Canvas`, sin glifo de fuente |
| `HistoryTable` | `table.py` | solo lectura, 50 filas |
| `SearchPopup` | `search.py` | ventana flotante, `Enter` toma el primero |
| `_Dialog` | `dialog.py` | confirmación / aviso, borderless |
| `Card` (contenedor) | — | reemplazado por `CTkFrame` en cada componente |

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
| `Fee · %mrg / pos` | Total en 13 bold (color por signo) **con subrayado punteado**, `0.30% / 0.03%` en `MUTED` 11 (parte del margen y del nocional) y `ahorro 1.7489` en `GREEN` 11. El total es **comisión + funding** (`mexc.fee_desglose`): `totalFee` = comisión cobrada al abrir y `holdFee` = funding; `lowSaveTotalFee` es "Fees saved" y **no** suma. El subrayado punteado avisa que hay detalle: al pasar el puntero, `tooltip.NumeroConDetalle` abre un panel con `Comisión / Funding / Fee total / Fees saved`. Ojo: el terminal de MEXC pinta su "Fees" como `totalFee + lowSaveTotalFee`, así que allí el número es más alto |
| `TP / SL` | todo alineado a la derecha: `3,990.5 / 3,880.2`, o `TP 3,990.5`, o `SL 3,880.2`, o `—`; lápiz al final |

La fila mide 56 px y lleva `grid_rowconfigure(0, weight=1)` para que cada celda quede
centrada verticalmente sin tocar los bordes: los labels llevan `height` explícito (19 / 15 /
13) porque el alto por defecto de 28 px desborda la fila. El modo de margen (aislado/cruzado)
no se muestra en la fila: se deduce del lápiz de margen, que aparece deshabilitado en cruzado.

**Reglas de la tabla**
- No usar `ttk.Treeview`: no permite color por celda y el PnL debe ir verde/rojo.
- **Cabecera, filas y celdas son widgets tk nativos** (`tk.Frame` / `tk.Label`), no CTk: cada
  widget de CustomTkinter es un `CTkCanvas` propio y Windows lo repinta por separado, así que
  con ~150 etiquetas la ventana tardaba ~300 ms en repintarse al restaurarla desde minimizada
  (se veía como si recargara). Con tk baja a ~100 ms. Los controles interactivos (checkbox,
  `CloseBar`, chips, lápices) siguen siendo CTk/Canvas.
- Cada fila es un `tk.Frame` con `grid` y `minsize` por columna (mismo ancho en cabecera
  y filas) más `weight=1` para repartir el espacio sobrante.
- **La cabecera hereda el `anchor` de su columna**: texto a la izquierda (`Par`, `Lado`,
  `Apertura`), números a la derecha. No se centra: centrar deja el título flotando sobre
  un dato pegado al borde y se lee peor.
- **Columnas con lápiz (`margen`, `tpsl`)**: el lápiz ocupa 24 px al final de la celda, así
  que la cabecera reserva ese mismo hueco (`PENCIL_GUTTER`) con `width = ancho - 24` y
  `padx = (6, 26)`. Sin eso el título queda 24 px a la derecha del valor y la columna se ve
  torcida. Vale para las dos: cabecera y fila suman siempre `ancho + 8`.
- **Celdas de varias líneas**: un `tk.Label` con fuente de 13 px pide 23 px de alto (Geist
  deja mucho interlineado). La celda de fee lleva sus tres líneas en cajas fijas de 19/15/13
  con `place` dentro de un frame de 47 px; si no, la tercera línea se sale de la fila de 56.
- Anchos: `par 132 · lado 74 · apertura 84 · pos 112 · entrada 94 · mark 94 · liq 100 ·
  ratio 98 · margen 132 · pnl 122 · fee 140 · tpsl 188`, con +8 px de padding por columna
  (1696 px de fila con checkbox y acciones). `Lado` está en 74 porque `10X SHORT` ocupa
  ~72 px; `Par` en 132 para que entre `GOLD(XAU)USDT` (107); `Posición` en 112 por el
  sufijo `USDT` (108 en el peor caso); `Apertura` en 84 (74 reales); `TP / SL` en 188
  (110 del par de precios + 24 del lápiz + separador).
- Actualización en sitio; reconstrucción solo si cambia el conjunto de `positionId`.
- Selección por **checkbox** por fila + checkbox maestro en la cabecera.
- Columna de acciones (200 px): `CloseBar` en dos líneas dentro de los 190 útiles.
  Línea 1: `[Mercado ▾]` (106) + `[100% ▾]` (78). Línea 2: `[Cerrar LONG/SHORT]` (102) +
  `[Reverse]` (82). El botón de cerrar toma el color del PnL (verde, rojo o gris) y el texto
  lleva el lado; el marcado del lado en la fila (`Lado`) no cambia.
  Los lápices viven dentro de su celda (Margen y TP/SL).
- El `Pencil` se dibuja con `create_polygon` + `create_line` sobre un `Canvas` de 20 px:
  cuerpo inclinado 135°, banda y punta. Sin glifo Unicode (evita tofu y look genérico).
  Hover de `MUTED` a `TEXT`; deshabilitado en `BORDER` y sin bind.

**Reglas de las tarjetas**
- Fila horizontal con scroll; `+ Añadir par` agrega a la derecha.
- `grid_propagate(False)` + `height` explícito (sin height, el frame colapsa).
- El chip del par ocupa el espacio libre (`fill="x", expand=True`); la ✕ se empaqueta
  primero a la derecha para que nunca se superpongan.

---

## 6. Formatos numéricos (`theme.py`)

| Función | Salida | Uso |
|---|---|---|
| `fmt_price` | `78,549.5` / `2,239.10` / `0.90560` | resúmenes y precios de referencia; **no** en la fila |
| `fmt_price_exact` | `3,900.75` | precios de la fila (Entrada, Mark price, Liquidación, mínimo 2 decimales) y precio de una orden límite: lo que se ve es lo que se envía |
| `fmt_pnl` | `+12.4021` / `-3.1502` | PnL, signo siempre, 4 decimales |
| `fmt_fee` | `0.1997` | comisiones, 4 decimales |
| `fmt_usdt` | `502.11` / `+502.11` | márgenes, nocional |
| `fmt_qty` | `127` / `0.0134` | contratos y cantidades |
| `fmt_pct` | `+1.24%` / `-3.92%` | variación 24h |
| `fmt_share` | `0.20%` / `<0.01%` | parte de un total (fee sobre margen y nocional), sin signo |
| `table.fmt_when` | `30/10 12:11` | `createTime` (ms) de posiciones, órdenes e historial; fuera de `theme` porque es fecha, no número |

Reglas de color en tablas:

| Celda | Regla |
|---|---|
| PnL | `> 0` verde · `< 0` rojo · `= 0` gris |
| Fee | `> 0` rojo (costo) · `< 0` verde (rebate) · `= 0` gris |
| Mark price | verde si va ganando vs entrada, rojo si perdiendo, gris si falta |
| Lado | LONG verde · SHORT rojo |
| Dirección (órdenes) | compra (lado 1, 2) verde · venta (lado 3, 4) rojo |
| Llenado (órdenes) | algo llenado en `GOLD`, nada en `MUTED` |
| Estado (órdenes) | `Sin llenar` / `Pendiente` en `TEXT`, el resto en `MUTED` |
| Estado (historial) | Ejecutada verde · resto gris |

**Estructura de la fila de órdenes abiertas** (54 px, `orders.py`, imita el panel de MEXC)

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
Las órdenes de cierre (lado 2/4) no se pueden reenviar: lápiz y `Modificar` deshabilitados,
solo `Cancelar`. La tabla se refresca en sitio con el poller (cada 3 s) y solo se reconstruye
si cambia el conjunto de `orderId`; el aviso `N pendientes` de la pestaña Posiciones es
clicable y lleva a esta.

**Editor de orden** (`orders.OrderEditor`, 406 px de ancho)

- Título `Modificar orden`, el par en gris a la derecha y ✕.
- Aviso en `GOLD`: se cancela la orden y se envía una nueva (MEXC no permite editar).
- `Dirección` con el `CTkSegmentedButton` LONG/SHORT; luego `Apalancamiento` (`x`),
  `Margen` (`USDT`), `Precio límite`, `TP` y `SL`, todos con etiqueta a la izquierda.
- Línea viva `≈ 5 contratos · 100.00 USDT nocional` (se recalcula al escribir).
- Pie: `[Cancelar]` y `[Guardar y reenviar]` (verde). El error se explica en una línea roja.
- El margen inicial es `nocional / apalancamiento`, **no** `orderMargin` (que incluye
  comisión): guardar sin tocar nada reenvía la misma orden.

---

## 7. Ventanas flotantes

- Diálogos y buscador son `overrideredirect(True)` con borde de 1 px (`LINE`) y
  `corner_radius = R_CARD`.
- Siempre llevan ✕ propia y responden a `Escape`; el diálogo responde a `Enter`.
- Se centran sobre la ventana padre al abrir, **excepto** los popups de la fila
  (`_PercentPopup`, `PricePopup`), que se anclan debajo del control que los abre porque
  el dato al que se refieren está en esa fila. Esos paneles **no usan `grab_set`**: se
  cierran con el primer clic en la ventana (el clic igual llega a su destino) y no se
  llevan el foco al cerrarse por un clic afuera.
- El que se lleva el teclado **lo devuelve**: los paneles piden `focus_force` al abrir
  (sin eso su campo no recibe teclas) y al cerrarse fuerzan el foco a la ventana grande
  antes de pasárselo al chip. Si solo se usara `focus_set`, Tk quedaría sin ventana con
  foco y ningún input de la ventana aceptaría teclas. Los diálogos (`dialog._Modal`)
  hacen igual al cerrarse.

### Diálogo TP / SL

- Lo abre el lápiz de la celda TP/SL con `dialog.form`, que acepta dos extras:
  `extras=((texto, comando, habilitado), ...)` (botones a la izquierda de Cancelar; el
  comando recibe el dict de campos) y `resumen=callable(campos)` (línea gris bajo los
  campos, se repinta con cada tecla vía `trace_add`).
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

- Las filas-widget son más caras que un Treeview: medido, **~165 ms por fila** al
  construir (10 posiciones = 1.6 s de bloqueo) y **~8.5 ms por fila** al refrescar en sitio.
  Por eso solo se reconstruye cuando cambia el conjunto de `positionId`. Con 30+ posiciones
  habría que actualizar por columna o virtualizar.
- El scroll horizontal de tarjetas no responde a la rueda sin `Shift`.
- El popup de búsqueda puede quedar 1-2 px desalineado con escalado DPI distinto.
- El historial se re-renderiza completo cada 15 s; con más de ~100 filas conviene paginar.
- La fee es una estimación: MEXC devuelve `takerFeeRate` distinto entre llamadas.
