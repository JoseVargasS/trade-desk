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
| Tabla | Geist | 13 (negrita en Mark, Posición, PnL, Par, Lado) |
| Botón principal | Geist bold | 14–16 |

---

## 4. Formas y espaciado

- Radios: `R_CHIP = 6`, `R_CTRL = 8`, `R_CARD = 12`.
- Padding interno de tarjeta: 12 px. Padding de ventana: 16 px.
- Tarjeta de operación: **286 px de ancho, 486 px de alto** (fija).
- Filas de tabla: 46 px (posiciones, PnL en dos líneas) y 38 px (historial). Cabecera: 36 px.
---

## 5. Componentes

| Componente | Archivo | Notas |
|---|---|---|
| `TradeCard` | `cards.py` | par + apalancamiento + margen + tamaño + TP/SL + LONG/SHORT |
| `PositionsTable` | `table.py` | celdas compuestas con color, checkbox y botón Cerrar |
| `Pencil` | `table.py` | lápiz dibujado en `Canvas`, sin glifo de fuente |
| `HistoryTable` | `table.py` | solo lectura, 50 filas |
| `SearchPopup` | `search.py` | ventana flotante, `Enter` toma el primero |
| `_Dialog` | `dialog.py` | confirmación / aviso, borderless |
| `Card` (contenedor) | — | reemplazado por `CTkFrame` en cada componente |

**Estructura de la fila de posiciones**

| Celda | Contenido |
|---|---|
| `Par` | símbolo, mono 13 bold |
| `Lado` | `10X LONG` verde / `5X SHORT` rojo (apalancamiento incluido) |
| `Posición` | nocional en USDT (`qty × contractSize × mark`), bold |
| `Entrada`, `Mark` | precio; Mark verde/rojo contra la entrada |
| `Liquidación` | precio en `GOLD` |
| `Margen %` | `1.42%`; `GOLD` desde 20 % |
| `Margen` | `502.11 USDT` bold + lápiz |
| `PnL`, `Fee` | 4 decimales, color por signo |
| `TP / SL` | TP `GREEN` · `/` muted · SL `RED` + lápiz |

Todas las filas son de **una línea** (40 px). El modo de margen (aislado/cruzado) no se
muestra en la fila: se deduce del lápiz de margen, que aparece deshabilitado en cruzado.

**Reglas de la tabla**
- No usar `ttk.Treeview`: no permite color por celda y el PnL debe ir verde/rojo.
- Cada fila es un `CTkFrame` con `grid` y `minsize` por columna (mismo ancho en cabecera
  y filas) más `weight=1` para repartir el espacio sobrante.
- Actualización en sitio; reconstrucción solo si cambia el conjunto de `positionId`.
- Selección por **checkbox** por fila + checkbox maestro en la cabecera.
- Columna de acciones (200 px): **Cerrar** en pastilla verde llena y **Reverse** con borde.
  Los lápices viven dentro de su celda (Margen y TP/SL).
- Las cabeceras van **centradas** (`anchor="center"`), no siguen el alineado del dato.
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
| `fmt_price` | `78,549.5` / `2,239.10` / `0.90560` | precios, mark, liquidación |
| `fmt_pnl` | `+12.4021` / `-3.1502` | PnL, signo siempre, 4 decimales |
| `fmt_fee` | `0.1997` | comisiones, 4 decimales |
| `fmt_usdt` | `502.11` / `+502.11` | márgenes, nocional |
| `fmt_qty` | `127` / `0.0134` | contratos y cantidades |
| `fmt_pct` | `+1.24%` / `-3.92%` | variación 24h |

Reglas de color en tablas:

| Celda | Regla |
|---|---|
| PnL | `> 0` verde · `< 0` rojo · `= 0` gris |
| Fee | `> 0` rojo (costo) · `< 0` verde (rebate) · `= 0` gris |
| Mark | verde si va ganando vs entrada, rojo si perdiendo, gris si falta |
| Lado | LONG verde · SHORT rojo |
| Estado (historial) | Ejecutada verde · resto gris |

---

## 7. Ventanas flotantes

- Diálogos y buscador son `overrideredirect(True)` con borde de 1 px (`LINE`) y
  `corner_radius = R_CARD`.
- Siempre llevan ✕ propia y responden a `Escape`; el diálogo responde a `Enter`.
- Se centran sobre la ventana padre al abrir.

---

## 8. Deuda visual conocida

- Las filas-widget son más caras que un Treeview: con 30+ posiciones habría que pasar a
  actualización incremental por columna o virtualizar.
- El scroll horizontal de tarjetas no responde a la rueda sin `Shift`.
- El popup de búsqueda puede quedar 1-2 px desalineado con escalado DPI distinto.
- El historial se re-renderiza completo cada 15 s; con más de ~100 filas conviene paginar.
- La fee es una estimación: MEXC devuelve `takerFeeRate` distinto entre llamadas.
