# AGENTS.md

Documento de traspaso para quien retome **Trade Desk**. Léelo completo antes de tocar código.
Si algo aquí no coincide con el código, el código manda: corrige este archivo en el mismo cambio.

---

## 0. Cómo empezar a trabajar aquí

**Dónde está cada cosa.** El código vive en `src/tradedesk/` (layout `src`), los tests en
`tests/`, los assets **dentro del paquete** (`src/tradedesk/assets/`), los scripts sueltos en
`tools/` y los datos del usuario (`config.json`, `trades.log`) en la raíz del repo,
nunca dentro del paquete: esas rutas las resuelve `tradedesk/paths.py`.

**Arranque.** `app.py` en la raíz es **solo el lanzador**: agrega `src` al path y llama a
`tradedesk.__main__:main`. `Iniciar.bat` ejecuta `tools/instalar.ps1`, que usa un Python 3.11+
existente o instala 3.13 con uv, prepara las dependencias, crea el acceso directo del escritorio y
abre la app con el `pythonw.exe` del entorno virtual. `Iniciar-con-consola.bat` usa el mismo
proceso y deja visible la consola para diagnosticar errores. No borres ni muevas `app.py` de la
raíz sin actualizar el instalador y el acceso directo, o la app deja de abrir.

**Entorno y verificación** (Windows, Python 3.11+):

```powershell
uv sync --locked --extra dev
uv run --locked python -m pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
scripts\check.bat           # lint + formato + tests de una
```

**El plan de trabajo vive en `docs/PLAN.md`.** Ahí están las fases pendientes, el estado de
cada una y la bitácora con el commit de cada paso. Se actualiza al cerrar cada paso; este
documento (AGENTS) describe cómo está el código **hoy**, no cómo debería estar.

**Reglas para no romper lo que ya funciona**

- **La ruta de órdenes tiene red de seguridad**: `tests/test_mexc_orders.py` fija los payloads de
  `open_market` y `close_position` (side, type, vol, precio redondeado a `priceScale`). Si cambias
  un payload, cambia el test en el mismo commit. Nunca se prueba contra la cuenta real en tests.
- **Ningún hilo toca widgets**: `tests/test_no_threaded_widgets.py` lee el fuente (controller y
  la vista Qt) y falla si un `*_worker` llama a `configure` / `set_*`. Los hilos solo hablan por
  `session.q`; Qt no es thread-safe.
- **La fila de posiciones no crece**: `tests/test_layout.py` fija el ancho total. Si se pasa,
  recorta columnas; no ensanches la ventana.
- **Ruff mandó el formato**: los archivos ocupan ~15 % más líneas que antes (una llamada con
  muchos argumentos queda un argumento por línea). El tope real es **~700 líneas**; si un
  archivo se cruza, se parte por responsabilidad y el viejo queda de fachada.
- Colores, fuentes y formatos numéricos **solo** en `theme.py`. La vista Qt usa
  `qt.style.fnt`, que da el tamaño en **píxeles** (no en puntos).
- La familia es **Geist** y viaja con la app (`assets/fonts`). `qt.style.fnt` la pide con
  `setFamilies(["Geist", "Segoe UI", "Arial"])`: si un día no se registra, cae en Segoe
  UI y no en Tahoma. No hacen falta familias CJK ni de macOS: Qt resuelve los glifos que
  falten y Geist ya cubre todo lo que pinta la app (✕ ▾ ≈ → · — ¿ ¡ acentos).
- **Solo se corre el test que cubre lo que se tocó** (matriz en §9). Nunca la suite entera "por
  si acaso": cuesta ~15 s y gasta cuota del usuario sin aportar nada si el cambio fue de un
  texto o un decimal. Si no hay test para esa zona, alcanza con mirar el resultado (captura).
- Después de tocar UI: `python tools/smoke_live.py 9` (arranca 9 s, pinta las posiciones reales y
  cierra sola; no envía órdenes). Si se tocaron tablas, `python tools/qt_probe.py` mide el
  repintado con 8 tarjetas y 200 filas.
- Antes de commitear: `scripts\check.bat` en verde (una sola vez, no en cada paso).
- **Los mensajes de commit siguen la skill `git-commit`** (`~/.agents/skills/git-commit`):
  `tipo(scope): descripcion` en imperativo, descripción de **72 caracteres máximo** y bullets
  de **una sola línea** con lenguaje claro (qué cambia y por qué, no cómo). Cargar la skill
  antes de escribir el mensaje; no confiarse de la memoria.
- **El formato lo valida un hook**: `scripts/commit-msg` se copia a `.git/hooks/commit-msg`
  (`Copy-Item scripts\commit-msg .git\hooks\commit-msg`). Rechaza los mensajes sin tipo
  válido o con descripción de más de 72 caracteres.
- **Solo commits y push directo a `main`.** El usuario es el único que maneja el repo: no se
  abren pull requests ni se activa Dependabot, porque ensucian el historial con merges. Las
  actions se actualizan a mano en el mismo commit.
- **No se crean ramas nuevas**: todo se trabaja y se commitea en `main`.

---

## 1. Qué es y por qué existe

App de escritorio Windows para operar **futuros de MEXC, Bitunix y BingX**, a mercado por
defecto y con límite opcional. No es un bot: no hay estrategias, trailing ni ejecución
automática. Es una mesa de ejecución.

**Contexto de origen.** El usuario operaba en el terminal web de MEXC (BTC + ETH en pestañas
separadas). El navegador llegaba a ~3.4 GB en RAM y 85 % de CPU por la consola de DevTools
acumulando errores. Esta app resuelve eso: **~70 MB** y ~20-30 ms por orden (el terminal web
tarda 300-800 ms porque pasa por su gateway, su sesión y su render).

Decisiones de fondo que **no** están en discusión:

- Escritorio nativo (**PySide6**), **no** web local. Un servidor local abre un
  puerto que no hace falta, y un navegador reintroduce el costo que se quería eliminar.
- **No** `.exe` por ahora: PyInstaller sin firmar dispara SmartScreen/Defender. Se usa un
  acceso directo con ícono, que para el usuario se comporta igual.
- Cada exchange tendrá **su propio módulo**, sin capas de abstracción que unifiquen firmas
  que no se parecen.

---

## 2. Cómo lo usa el usuario (flujo real)

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
7. Abajo, pestaña **Posiciones**: cada fila trae `[Mercado]`, `[%]` y el botón
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
8. Pestaña **Órdenes** (panel estilo MEXC): las límite que todavía no se llenaron, con par
   (+`Perpetual` y el % llenado debajo), fecha, dirección (`Compra LONG` / `Venta SHORT`),
   apalancamiento, monto, precio, llenado, margen usado, TP/SL en dos líneas, fee y estado.
   Los **lápices** de Monto, Precio y TP/SL abren el editor (lado, apalancamiento, margen,
   precio, TP y SL); en la columna de acciones están `Modificar` y `Cancelar`, y arriba a la
   derecha `Cancelar todo`. Una orden límite no aparece en Posiciones hasta que se llena.
   Las condicionales TP/SL de BingX se muestran y pueden cancelarse, pero no ofrecen lápiz
   ni `Modificar` desde esta pestaña.
9. Pestaña **Historial**: las últimas órdenes de los **tres** brokers, **agrupadas en
   operaciones** (una fila por operación, no por orden): hora de apertura y de cierre, par
   con el wordmark del broker, lado, **tamaño en USDT**, entrada, salida, PnL, fee, **neto**
   (PnL − fee) y estado (`Cerrada` / `Parcial` / `Abierta`). Los cierres parciales se suman
   en la misma fila en vez de aparecer sueltos.
10. Pestaña **Calendario**: un mes en cuadrícula con el resultado de cada día. El mes es
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

## 3. Arquitectura

```
raiz/
  app.py                    lanzador del acceso directo (no tiene logica)
  src/tradedesk/            (8.540 líneas Python; conteo de referencia al 2026-11-07)
    __init__.py              inicialización del paquete                      2
    __main__.py              arranque: AppUserModelID + vista Qt            14
    paths.py                 DATA_DIR (raíz) y ASSETS (paquete)             10
    creds.py                 Windows Credential Manager                    16
    brokers.py               nombres y títulos de los brokers                6
    theme.py                 color, tipografía, radios, formatos            88
    layout.py                anchos/altos de las tablas (sin UI)             72
    pairs.py                 filtro puro del buscador de pares               36
    forms.py                 parseo puro de tarjeta y editor de orden       100
    pnl.py                   neto de una operación del historial              9
    calendario.py            agregación por día del historial (puro)          298
    archivo.py               operaciones guardadas en disco (upsert)        179
    operaciones.py           empareja órdenes en operaciones (historial)    213
    session.py               pollers, cola, config y caches sin UI          627
    controller.py            fachada de casos de uso                         443
    controller_verificacion.py cotejo de estado tras errores                 203
    controller_tpsl.py       casos de uso TP/SL y Break-even                 216
    controller_ordenes.py    órdenes y margen                                204
    mexc.py                  firma, endpoints, USDT->contratos, fee, liq    572
    bitunix.py               firma, endpoints, monedas (qty), specs        567
    bingx.py                 firma, endpoints, monedas (qty), specs        607
    assets/                 icon.ico, icon.png, fonts/*.ttf
    qt/
      __init__.py           inicialización del paquete                       0
      __main__.py           abre la ventana                                 31
      view.py               fachada: reexporta VistaQt                       6
      ventana.py            cabecera, deck arrastrable, pestañas, drenaje   565
      tabla_posiciones.py   filas, resumen bruto/neto, globo de la fee     306
      tabla_ordenes.py      órdenes abiertas (panel estilo MEXC)           115
      tabla_historial.py    una fila por operación, con su neto            138
      calendario.py         mes en cuadrícula, métricas y detalle del día  576
      calendario_widgets.py delegado del mes y curva acumulada             112
      tarjeta.py            tarjeta de par                                 349
      cierre.py             barra de cierre de la fila (slider, botones)   328
      dialogs.py            fachada: reexporta los diálogos                 40
      dialogos_base.py      Modal, confirm, show, form y claves            296
      editor_orden.py       editor de una orden abierta                    153
      tpsl.py               editor de TP/SL con las líneas vivas            73
      be.py                 ventana de "Poner a BE"                        111
      panel_brokers.py      panel de brokers                                52
      port.py               UiPort de la vista Qt                           39
      formato.py            fecha y tamaño en USDT de las celdas            19
      style.py              fuentes, widgets, QSS y logos                  229
      cells.py              delegado, celdas con lápiz, spinner, bocadillo 295
      search.py             buscador de pares                               72
      shell.py              ventana de prueba para medir repintado        134
  tests/                    pytest (241 tests recopilados): lógica, payloads y UI fake
  tools/                  make_icon, smoke_api, smoke_live, check_account, qt_probe, instalar.ps1
  scripts/check.bat         lint + formato + tests
  docs/DESIGN.md            sistema de diseno
  docs/PLAN.md              plan de trabajo vivo (fases, estado, bitacora)
```

**El objetivo es mantener los módulos cerca o por debajo de ~700 líneas.**
`controller.py` y `qt/calendario.py` ya están partidos por responsabilidad y quedan bajo el tope;
siguen `bingx.py` (607) y
`qt/ventana.py` (565). `qt/view.py` y `qt/dialogs.py` quedaron como
**fachadas** que reexportan: así los imports de `__main__.py`, `tools/smoke_live.py` y de la
propia vista no cambiaron. Si un archivo se acerca al tope, se parte igual: módulo nuevo +
fachada, sin tocar los call sites.

Las tres tablas (`tabla_posiciones`, `tabla_ordenes`, `tabla_historial`) y la pestaña
`calendario` son **mixins** de `VistaQt`: usan el estado de la ventana y se pintan igual que
antes. Al tocar una tabla, recordá que el método vive en el mixin, no en `ventana.py`.

### Flujo de datos

Todo pasa por **una cola** (`session.q`) y un solo consumidor en el hilo de la UI
(`VistaQt._drenar`, cada 120 ms). Ningún worker toca widgets ni abre diálogos. Las consultas
de red y los resultados de acciones publican mensajes; la UI los procesa en `_drenar`.

```
_cargar_tarjetas ─► contratos/precios iniciales y saldos
_cargar_catalogo ─► ("markets", ...), disponibilidad por broker (solo futuros)
_cargar_ip       ─► ("ip", ...)                   IP inicial
_poll(broker)    ─► ("ticker", ...)               un hilo por broker, rota tarjetas cada 0,70 s
_poll_cuenta     ─► ("positions", ...), ("orders", ...) cada 3 s en estado normal
_poll_secundario ─► historial (15 s, solo en su pestaña), saldos (15 s),
                    funding (60 s) e IP (900 s); tareas secuenciales en este worker
```

Cada broker tiene su propio hilo de precios (`_poll("mexc")`, `_poll("bitunix")`,
`_poll("bingx")`), así que una consulta colgada o un backoff afectan solo a ese broker
y no congelan los precios de los demás. Dentro de `_poll_cuenta`, posiciones y órdenes se
consultan en secuencia; dentro de `_poll_secundario`, historial, saldos, funding e IP también.
Los tickers son públicos: `_poll` usa el cliente de mercado aunque no haya API key. `Session.cliente()`
sigue reservado para operaciones privadas que requieren credenciales.
El índice de `_poll` persiste entre vueltas para que cada tarjeta del broker reciba su ticker;
reordenar una copia recién creada de la lista no rota entre tarjetas.
Ticker y cuenta aplican backoff si fallan (tope de 5 s). No describas al worker secundario
como cuatro hilos separados. `Session.start()` conserva las referencias a los workers daemon;
`stop()` señala el evento de cierre.

`controller.Control` recibe `session` y un `UiPort` (`qt.dialogs.QtPort`) con
`confirm`, `show`, `form`, `tpsl`, `editar_orden` y `status`. La UI solo pinta y lee
los controles; los casos de uso y los payloads viven en el controlador.

### Persistencia

`config.json` (ignorado por git) guarda **solo** `symbol`, `leverage`, `margin`, `size_mode`
y `exchange` por tarjeta. **No** guarda tamaño, TP, SL ni DRY-RUN (ver §7). Se escribe primero
a un archivo temporal y se reemplaza con `os.replace`; si falla, el error queda en el log y
se publica en la barra de estado.

`operaciones.json` (también ignorado) es el **archivo de operaciones**: cada operación
cerrada se guarda con una clave estable (`_clave`) y se actualiza en sitio (un parcial que
después se cierra, o una fee que se ajusta). Existe porque los exchanges purgan su
historial (~3 meses): sin esto, lo viejo desaparece de la pestaña. Antes de guardar se crea
`operaciones.json.bak` y el archivo principal se reemplaza atómicamente. Si el JSON está
corrupto, se pone en cuarentena y se intenta recuperar el respaldo; la vista recibe un aviso
explícito. Al arrancar se pinta lo guardado antes de tocar la red (`docs/PLAN.md` §3.2 y §3.3).
Al fusionar, una fila `cierre|` solo se quita si coincide de forma única con una `fifo|`
por broker, símbolo, lado, cierre (menos de 1 s), cantidad cerrada, PnL y salida. Matches
ambiguos o incompletos se conservan; por eso una posible duplicación sin evidencia
suficiente puede seguir visible. Es una heurística basada en esos campos, no una identidad
de orden: dos operaciones legítimas idénticas dentro de ese intervalo aún podrían coincidir.
Un refresco MEXC menos completo tampoco reemplaza una fila archivada mejor.

`trades.log` registra cada intento: hora, resultado, `orderId`, símbolo, `vol`. Nunca la key.
Rota al alcanzar 1 MB y conserva hasta tres copias; los errores de escritura se notifican
(§3.4 del plan).

---

## 4. MEXC Futures API — lo que hay que saber

| Tema | Detalle |
|---|---|
| Base | `https://contract.mexc.com` |
| Firma | `HMAC-SHA256(apiKey + timestamp_ms + paramString)` |
| POST | se firma el **string JSON** exacto que se envía |
| GET | parámetros ordenados alfabéticamente y unidos con `&` |
| Headers | `ApiKey`, `Request-Time`, `Signature`, `Recv-Window` opcional (≤60 s) |
| **User-Agent** | **obligatorio uno de navegador**. Con el de `httpx` el WAF responde **403 Access Denied** |

Endpoints en uso:

```
GET  /api/v1/contract/ticker?symbol=BTC_USDT     precio (público)
GET  /api/v1/contract/ticker                     todos los tickers (~250 KB, NO en loop)
GET  /api/v1/contract/detail?symbol=BTC_USDT     contrato individual (fuente autoritativa)
GET  /api/v1/contract/detail                     catálogo completo (1.171 pares)
POST /api/v1/private/order/create                abrir/cerrar (type=5 mercado, type=1 límite)
POST /api/v1/private/order/cancel                body: [id, ...]  (array, NO {"orderIds": []})
POST /api/v1/private/position/close_all
POST /api/v1/private/position/reverse            reversible nativo
POST /api/v1/private/position/change_margin      ADD/SUB, solo aislado
GET  /api/v1/private/stoporder/list/orders       TP/SL vigentes por positionId
POST /api/v1/private/stoporder/place             crear/reemplazar TP/SL
POST /api/v1/private/stoporder/cancel            body: [{ "stopPlanOrderId": id }]
GET  /api/v1/private/position/open_positions
GET  /api/v1/private/order/list/open_orders
GET  /api/v1/private/order/list/history_orders
```

**Unidades.** `vol` siempre en **contratos**, entero. Verificado: los 1.171 pares tienen
`volUnit = 1`, no existe el contrato fraccionario. Lo que varía es `contractSize`
(BTC `0.0001`, ETH `0.01`, SOL `0.1`, SUI `1`, DOGE `100`). Nocional = `vol × contractSize × precio`.

**Redondeo.** `size_to_vol` hace **floor** al step. Nunca se pasa de lo pedido: con 1,000 USDT
en BTC obtienes 127 contratos = ~996 USDT. Se eligió floor y no "el más cercano" porque
redondear hacia arriba puede exigir más margen del que el usuario escribió y hacer que MEXC
rechace la orden por saldo insuficiente.

**Cierre parcial y límite.** `close_vol(holdVol, pct)` hace floor al contrato entero, salvo
100 %, que devuelve `holdVol` exacto (un cierre total no puede fallar por redondeo).
`open_market(..., price)` y `close_position(pos, vol, price)` reparten la orden:
`price=None` → `type=5` (mercado);
con precio → `type=1` y el precio redondeado a `priceScale` del contrato (si no, **2015**:
"precisión inválida"). El precio con el que se manda se formatea con `theme.fmt_price_exact`,
no con `fmt_price`, que recorta a 1 decimal desde 1000.

**`side`** (¡no es buy/sell!): `1` abre long, `2` cierra short, `3` abre short, `4` cierra long.

**Rate limits** (documentados y comprobados):

| Endpoint | Límite |
|---|---|
| ticker | 10 / 2 s |
| order/create | 4 / 2 s |
| order/cancel | 20 / 2 s |
| change_leverage | 10 / 10 s |
| posiciones / órdenes | 20 / 2 s |

Cada hilo de precios va a **~1.4 req/s** de su broker (0.70 s entre requests) con backoff
multiplicativo (0.70 s → 5.0 s) si algo falla. El ritmo se mantiene por broker, así que
bajar esos tiempos produce `510 Demasiadas peticiones`.

**TP/SL: la dirección se mide contra el precio actual, no contra la entrada.**
LONG → TP por encima y SL por debajo; SHORT al revés. Un `stopLossPrice` del lado
de la ganancia se rechaza con **5003** aunque esté lejos; ese mismo nivel sí entra
como `takeProfitPrice`. `mexc.plan_tp_sl()` aplica la regla antes de enviar.
El `stoporder/cancel` es **asíncrono**: recolocar de inmediato da **5004**
("greater than the closable amount"), por eso se espera a que la lista quede vacía.

**Idempotencia (lo que hay y lo que no).** Cada apertura (y el cierre de MEXC) lleva un
`externalOid` único, pero **no existe ningún reintento automático**: ni `httpx` reintenta
POSTs ni hay bucle en `_post`. Si el usuario reenvía a mano, se genera otro `externalOid` y el
broker no puede deduplicar. Por eso, ante un timeout, hay que **mirar Posiciones antes de
reenviar** (`docs/PLAN.md` §5.1).

**Fee estimada.** `takerFeeRate` viene del endpoint individual. Ojo: MEXC devuelve valores
distintos entre llamadas (se observó `0.0002` y `0.0004` en la misma sesión). Es una
**estimación**, no un dato contable.

La columna Fee de posiciones muestra **comisión + funding** (`mexc.fee_desglose`):
`totalFee` es la comisión ya cobrada al abrir y `holdFee` el funding; `lowSaveTotalFee` es
"Fees saved" y **no** suma. El importe lleva subrayado punteado y al pasar el puntero aparece
el desglose en el `Bocadillo` propio (`qt/cells.py`), no en un `QToolTip` nativo. Ojo: el terminal de MEXC pinta su "Fees" como
`totalFee + lowSaveTotalFee`, así que su número es más alto que el real.

### Bitunix (segundo broker)

| Tema | Detalle |
|---|---|
| Base | `https://fapi.bitunix.com` |
| Firma | `SHA256(SHA256(nonce + timestamp + apiKey + queryParams + body) + secret)` |
| Cabeceras | `api-key`, `nonce` (32 hex), `timestamp` ms, `sign`, `Content-Type` |
| Errores | **HTTP 200 también con error**: el código de negocio va en `code` (0 = éxito) |
| Símbolo | `BTCUSDT` (la app lo canonicaliza; MEXC usa `BTC_USDT`) |
| Tamaño | **monedas** (`qty` 0.01 = 0.01 BTC), no contratos |

```
GET  /api/v1/futures/market/tickers            precio (`lastPrice`, `markPrice`, `open`)
GET  /api/v1/futures/market/trading_pairs      specs: `minTradeVolume`, `basePrecision`,
                                               `quotePrecision`, `maxLeverage`
GET  /api/v1/futures/account                   saldo por `marginCoin`
GET  /api/v1/futures/position/get_pending_positions
GET  /api/v1/futures/trade/get_pending_orders  devuelve `{total, orderList}`
GET  /api/v1/futures/tpsl/get_pending_orders
POST /api/v1/futures/trade/place_order         abrir/cerrar
POST /api/v1/futures/trade/flash_close_position cierre total a mercado
POST /api/v1/futures/trade/close_all_position   cerrar todo
POST /api/v1/futures/trade/cancel_orders        body {symbol, orderList:[{orderId}]}
POST /api/v1/futures/account/change_leverage    {marginCoin, symbol, leverage}
POST /api/v1/futures/account/adjust_position_margin
GET  /api/v1/futures/account/position_mode      HEDGE | ONE_WAY
```

**Firma de GET con query params**: Bitunix firma los parámetros **sin separadores**
(`id=1&uid=200` se firma como `id1uid200`, ordenados por clave). Con `&`/`=` responde
`10007 Signature Error`; los GET sin params funcionan porque la cadena queda vacía.
Cualquier `limit`/`skip`/`symbol` en un GET necesita esta forma.

**Modificar y TP/SL**: `POST /trade/modify_order` cambia qty/precio/TP-SL de una orden viva
sin cancelar (MEXC no tiene esto: ahí se cancela y reenvía). `POST /tpsl/position/place_order`
pone TP/SL **a nivel de posición** (uno por posición, sin `qty`, cierra todo al dispararse) y
`POST /tpsl/cancel_order {symbol, orderId}` lo cancela. En el historial, `price` viene como
`"MARKET"` en las órdenes a mercado: el precio ejecutado es `avgPrice`.

**Campos reales** (confirmados con una posición abierta y cerrada el 27-jul): la
posición trae `qty`, `avgOpenPrice` (no `entryPrice`), `side` `BUY`/`SELL` (BUY = long),
`margin`, `marginRate`, `unrealizedPNL`, `liqPrice`, `fee` y `funding`. El TP/SL viene
**partido en dos registros** (`tpsl/get_pending_orders`: uno con `tpPrice` y otro con
`slPrice`), por eso se juntan por símbolo al decorar la posición.

**`flash_close_position` bloquea la apertura inmediata**: después de cerrar con ese
endpoint, Bitunix rechaza un `place_order` de apertura del mismo par con `30016`
(probado con 0.0001 y 0.0002, y esperando hasta 10 s). La apertura en frío del mismo
tamaño entra sin problema. Por eso `reverse` cierra con `place_order` reduceOnly y no
con flash, y el cierre normal de la fila sí puede usar flash (no reabre nada).

**Órdenes en modo HEDGE** (es el modo de la cuenta real): llevan `tradeSide`
(`OPEN`/`CLOSE`) y, al cerrar, `positionId` + `reduceOnly: true`. Para el cierre
total se usa `flash_close_position`, que evita la ambigüedad del `side` (la doc de
Bitunix pide `side` = lado de la **posición**, no de la orden). No hay reverse nativo:
`Bitunix.reverse` cierra a mercado y abre la contraria. El mínimo de BTC es
`0.0001` (≈ 7,7 USDT a 1x): si el floor deja 0 monedas, la orden **no se manda** y
se avisa, en vez de mandar `qty: 0`.

`contractSize` es **1** en Bitunix: el nocional es `qty × precio`, así que la
conversión USDT→qty divide por el precio y hace floor al `minTradeVolume` del par
(BTC: step `0.0001`). El cambio 24 h se calcula con `open` como referencia.

### BingX (tercer broker)

| Tema | Detalle |
|---|---|
| Base | `https://open-api.bingx.com` — **solo v2** (v1 responde `100400 this api is not exist`) |
| Firma | params ordenados + `timestamp` (ms) -> `HMAC-SHA256` hex, que viaja como **parámetro `signature`**; la key en la cabecera `X-BX-APIKEY` |
| Errores | **HTTP 200 también con error**: `code` (`0` = bien) y `msg` en el cuerpo |
| Símbolo | `BTC-USDT` (guion); la app lo canonicaliza a `BTC_USDT` |
| Tamaño | `quantity` en **monedas**, step = `tradeMinQuantity` (BTC `0.0001`) |

```
GET  /openApi/swap/v2/quote/ticker?symbol=BTC-USDT   precio (`lastPrice`, `openPrice`)
GET  /openApi/swap/v2/quote/contracts               1.318 pares: `size`, `quantityPrecision`,
                                                     `pricePrecision`, `tradeMinQuantity`, `tradeMinUSDT`
GET  /openApi/swap/v2/user/balance                  `availableMargin`
GET  /openApi/swap/v2/user/positions                `positionSide`, `positionAmt`, `avgPrice`
GET  /openApi/swap/v2/trade/openOrders              `orders`
GET  /openApi/swap/v2/trade/allOrders               historial (`profit`, `commission`)
POST /openApi/swap/v2/trade/order                   abrir/cerrar (`positionSide`, TP/SL en JSON)
POST /openApi/swap/v2/trade/closePosition           cierre total por `positionId`
DELETE /openApi/swap/v2/trade/order                 cancelar (una por llamada; pide `symbol`)
POST /openApi/swap/v2/trade/leverage                `symbol`, `side`, `leverage`
POST /openApi/swap/v2/trade/positionMargin          margen (`type` 1 suma / 2 resta)
```

**Verificado con la API real (3-nov-2026)**: base, forma de error, 1.318 pares, specs de
BTC-USDT (`tradeMinQuantity` 0.0001, `pricePrecision` 1, mínimo 2 USDT, taker 0,05 %). El
`quantity` está en **monedas** (DOGE mínimo 27 = 27 DOGE), no en contratos.

**Privados confirmados con la key real**: `/user/balance` devuelve `{"balance": {...}}`
(un dict **anidado**, no una lista — mapearlo como lista daba saldo 0); `/user/positions`
devuelve `{"positions": [...]}` y `/trade/openOrders` `{"orders": [...]}` (los dos pasan
por `_filas`); `/trade/allOrders` devuelve las órdenes y no acepta `page`, así que el
historial se pagina pidiendo `limit = limite + salto` y cortando el principio.
**La firma viaja como parámetro `signature`** (no como cabecera): sin eso BingX responde
`100412 Null signature`. **Sin verificar**: los campos de una posición abierta
(`positionAmt`, `avgPrice`) y las órdenes de escritura, hasta la primera operación real.

**IPv4 forzada en los tres clientes**: `httpx.HTTPTransport(local_address="0.0.0.0")`.
Las keys están atadas a la IP y sin esto la conexión puede salir por IPv6: BingX devolvía
`100419 ... does not match IP whitelist` con una IPv6 que la app no mostraba. La cabecera
muestra la IPv4 y el tooltip las dos (IPv4 e IPv6).

**Verificado con dinero real (3-nov, dos rondas de 0,0001 BTC a 1x, ~0,02 USDT de fees):**
abrir a mercado (FILLED, `avgPrice` real), leer la posición (`positionAmt`, `avgPrice`,
`unrealizedProfit`, `margin`, `leverage`, `riskRate` → los mapeos del `decorate` estaban
bien) y cerrar. El historial agrupado sale correcto (`Cerrada LONG 0.0001` con entrada,
salida, PnL y fee).

**Trampas confirmadas en vivo** (las tres ya están en el módulo):

1. **POST sin `Content-Type`**: los parámetros van en la query y el cuerpo va vacío; con
   `Content-Type: application/json` BingX responde `109400 Invalid parameters`.
2. **No existe `closePosition`** en v2 (`100400 this api is not exist`): el cierre es una
   orden al lado contrario (`trade/order`).
3. **En HEDGE `reduceOnly` no va**: `109400 In the Hedge mode, the 'ReduceOnly' field can
   not be filled`. Se manda sin el campo y se reintenta con él solo si la API lo pide
   (modo one-way).

**TP/SL**: en la **orden** funcionan como JSON (`takeProfit`/`stopLoss` con
`{"type":"TAKE_PROFIT_MARKET","stopPrice":...}`) — verificado: quedan dos condicionales
`STOP_MARKET` / `TAKE_PROFIT_MARKET` vivas. La **posición no trae TP/SL**, así que se leen
de esas condicionales (`open_orders`) y `decorate_positions` las recibe como tercer
argumento. Para una posición abierta se ponen con `closePosition: "true"` **más**
`quantity` y `stopPrice` (la doc oficial exige los tres): sin `closePosition` BingX las crea
como **orden parcial al 100 %** y en su app salen como "Posición parcial" en vez de
"Posición completa". `closePosition` y `reduceOnly` no se combinan. Antes de colocar se
cancelan las condicionales viejas.
**Borrar el TP/SL** (los dos campos vacíos) llama a `tpsl_place(..., None, None)` aunque no
haya nada que poner: en BingX las condicionales las cancela esa misma llamada, así que
saltársela dejaba el SL pegado en el broker.

**Ronda final en SHORT 1x (todo verificado en vivo)**: orden límite de venta creada y
cancelada; apertura SHORT con TP/SL en la orden (la fila muestra `tp`/`sl` leídos de las
condicionales); edición de TP/SL con el lápiz (cancela las viejas y pone las nuevas);
cierre parcial (0,0002 → 0,0001) y **reverse** (SHORT → LONG). El `reverse` necesitó 1 %
de margen en el nocional: con el nocional justo de la entrada, un tick de más deja el
floor en 0 y reabría nada después de cerrar (bug real, con test).

**El apalancamiento llega como `"10X"`** en las órdenes: `_apalancamiento()` lo convierte a
número porque la tabla lo pinta con `int()` (con el string, pintar Órdenes lanzaba
`invalid literal for int() with base 10: '10X'`).

**La fee de la posición sale del historial**: `/user/positions` no la trae, pero
`/trade/allOrders` sí (`commission`, negativo) y con **`positionID` en mayúsculas** (ojo:
la posición usa `positionId`). `Bingx.comisiones()` suma la comisión por `positionID` y
`decorate_positions` la recibe como cuarto argumento; el poller la pide solo si hay
posiciones, con caché de 2 s. **El historial tarda ~3 s en indexar la apertura**, así que
la celda se llena en el primer refresco posterior (verificado: 0,003824 en 0,0001 SHORT).
Falta el funding del par (no hay endpoint implementado).

**Seguridad de la key.** Se crea en MEXC con permisos de futuros + lectura, **sin retiros ni
transferencias**, y con **IP vinculada** (sin IP la key expira a los 90 días). Si el ISP cambia
la IP, la API responde `406 Accessing IP is not in the whitelist`; la app muestra la IP actual
en la cabecera con botón para copiarla.

---

## 5. Seguridad

- La key vive en el **Windows Credential Manager** (`creds.py`). Nunca en el código, nunca en
  `config.json`, nunca en un log.
- `trades.log` no contiene material sensible.
- DRY-RUN bloquea abrir, cerrar y reverse; TP/SL, margen y cancelar pasan siempre. Es la red de
  seguridad principal.
- La app no escucha puertos ni corre nada en segundo plano al cerrarse.
- `uv.lock` fija las dependencias con versiones y hashes. CI instala con `uv sync --locked`,
  ejecuta `pip-audit` y Gitleaks, y fija cada GitHub Action por SHA. Las actions y las
  dependencias se actualizan a mano: no hay Dependabot.
- Ante timeout de abrir, cerrar, cerrar todo, reverse o TP/SL (incluido Break-even), el
  resultado puede ser desconocido: avisar, refrescar Posiciones/Órdenes y no reenviar. Un
  worker de solo lectura coteja Posiciones/Órdenes y TP/SL con el broker; confirma únicamente
  si encuentra el estado esperado. Si no puede consultar o no encuentra evidencia, lo indica
  y pide revisión manual. Se detiene al cerrar la app; nunca reenvía la escritura.
- Si no se puede leer `operaciones.json`, conservar una copia fechada (máximo tres) y no
  sobrescribir el original. Fallos de guardar o respaldar se reportan en la barra de estado.
- El fallback existente de Bitunix a `HEDGE` cuando falla la consulta de modo se conserva
  para no cambiar payloads; el fallo debe quedar visible en la UI.

**Pruebas de escritura (regla dura).** Nunca se manda una orden a un par donde el
usuario tenga posición abierta: en hedge, una apertura del mismo lado se **suma** a la
suya y una limpieza se la cierra. Para verificar aperturas, cierres, parciales, TP/SL,
reverse o margen se usa **otro par** (uno que el usuario no esté operando) o una posición
**sintética** con un cliente falso. Antes de correr un script de escritura, consultar
`positions()` y elegir un símbolo que no aparezca; y al limpiar, filtrar por símbolo y
cantidad exactos de lo que abrió el script.

---

## 6. Reglas de UI (resumen; el detalle está en `docs/DESIGN.md`)

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

## 7. Decisiones tomadas y por qué

| Decisión | Motivo |
|---|---|
| Arranca **sin tarjetas** | El usuario lo pidió: zona limpia, se añade lo que se va a operar |
| **Tamaño vacío** por tarjeta | Evita reenviar el monto de la sesión anterior por descuido |
| **TP/SL no se guardan** | Un SL viejo aplicado a un precio nuevo es peligroso |
| **DRY-RUN siempre ON** | Falla segura: si te olvidas, no operas |
| **Floor** en el tamaño | Nunca excede el nocional pedido; no rompe por margen insuficiente |
| **Reverse nativo** | `POST /position/reverse` es atómico; hacerlo con dos órdenes deja ventanas de riesgo |
| `sleep(0.6)` al cerrar varias | Límite de 4 órdenes / 2 s |
| **Límite opcional al abrir** | El chip arranca en `Mercado` y no se guarda: una límite vieja aplicada a un precio nuevo es peligrosa |
| **Cierre por defecto: mercado y 100 %** | Sin tocar los inputs se comporta igual que antes; el cierre parcial y el límite son opcionales |
| **El % no se guarda** por fila | Un 30 % viejo aplicado a otra posición es riesgo; se reinicia a 100 % |
| **El color del botón de cerrar sigue al PnL** | Es el dato que se mira antes de decidir; el lado va en el texto |
| **Modificar una orden = cancelar y reenviar** | MEXC no deja editar una orden viva: se cancela, se espera a que libere el margen (`_wait_order_gone`) y se envía la nueva. El editor lo avisa en amarillo |
| **La tabla de órdenes imita a MEXC** | Es el panel que el usuario ya conoce: par + `Perpetual` con el % llenado, TP/SL en dos líneas y lápiz en Monto/Precio/TP-SL |
| **Qt (PySide6) en vez de Tkinter** | Con 8 tarjetas y 200 filas, restaurar la ventana tarda ~50 ms contra 943 ms en Tk (`tools/qt_probe.py`). La lógica vive en `controller.py`, así que el cambio de UI no tocó payloads |

---

## 8. Bugs ya resueltos (no reintroducirlos)

1. **403 del WAF** con el User-Agent por defecto de Python → hay que mandar uno de navegador.
2. **`takerFeeRate` inconsistente** entre `/contract/detail` (individual) y el catálogo.
   `markets()` **no** debe alimentar el cache de `contract()`.
3. **Rate limit del ticker**: 10/2 s. Un loop a 5/s lo rompe.
4. **Buscador vacío al inicio**: se le pasaba el catálogo antes de la primera carga y el
   constructor moría antes de programar el foco. Ahora `Session` publica `("markets", ...)`
   cuando termina y la vista avisa "todavía se está cargando" si se abre antes.
5. **Ícono de Python en la barra de tareas**: `SetCurrentProcessExplicitAppUserModelID` tiene
   que fijarse **antes** de crear la ventana, y la app declara `QIcon` (`__main__.py`).
6. **TP/SL no vienen en `open_positions`**: hay que cruzarlos con `stoporder/list/orders`.
   Al reemplazar, cancelar primero (`stoporder/cancel`) o MEXC acumula órdenes huérfanas.
7. **`markets()` desde el hilo de la UI**: 0.5 s en frío y hasta 8 s si el request se cuelga.
   `Session._cargar_catalogo` lo pide en su hilo; la vista nunca llama a la red.
8. **Un worker tocando un widget deja la ventana sorda**: Qt tampoco es thread-safe. Un
   `Tarjeta.set_preview(...)` desde un hilo bloquea el bucle de eventos y la UI deja de
   responder varios segundos. Los hilos **solo** hablan por `session.q`.
   `tests/test_no_threaded_widgets.py` falla si un `*_worker` llama a `configure`, `set_*`,
   `insert` o `delete` sobre un widget.
9. **TP/SL rechazado con 5003 en el caso más normal**: si entras en ganancia y pones el SL
   por encima del precio (LONG), MEXC lo rechaza porque ahí el único nivel válido es el TP.
   `plan_tp_sl()` lo mueve a TP y avisa por diálogo; si el TP ya está en ese lado, explica
   que deje el SL del lado de la pérdida en vez de mostrar el error en inglés.
10. **TP/SL rechazado con 5004 al reemplazar**: cancelar y recolocar sin esperar deja la
    orden vieja contabilizada. `_wait_tpsl_clear()` sondea `stoporder/list/orders` hasta
    que la posición queda a 0 (máx. 2.5 s) antes de volver a colocar.
11. **`order/cancel` respondía 600 Parameter error**: el body es un **array de ids sueltos**
    (`["871374754337090048"]`), no `{"orderIds": [...]}`; los ids van como texto para no
    perder precisión (18 dígitos). `mexc.cancel()` lo arma así y
    `tests/test_mexc_orders.py` fija el payload. Comprobado contra la cuenta real creando
    una límite a mitad de precio y cancelándola.
12. **La fee de la posición salía congelada y más baja que en MEXC**: la celda mostraba
    `totalFee`, que es **solo la comisión cobrada al abrir**. MEXC suma también el funding
    (`holdFee`, que en su panel va en una línea aparte). Ahora `mexc.fee_desglose()` devuelve
    comisión + funding (`1.4833` con la cuenta real) y la fila pinta ese total con subrayado
    punteado: al pasar el puntero aparece el desglose (`cells.py` y el tooltip del delegado).
    Ojo con los números de MEXC: su "Fees" del panel es `totalFee + lowSaveTotalFee` (por eso
    sale más alto) y `lowSaveTotalFee` es el "Fees saved", que **no** suma.
13. **Editar el TP/SL creaba un SL nuevo en vez de reemplazarlo**: la edición anterior se
    guardaba contra el id del stop cacheado, y una segunda edición no cancelaba nada: MEXC
    acumulaba stops. Ahora `Control._tpsl_worker` cancela **todos** los stop de ese
    `positionId` (leídos de `stoporder/list/orders`), no un id cacheado, y limpia los
    duplicados que ya existan. Test:
    `test_actions_close.py::test_editar_el_tpsl_cancela_todos_los_stop_de_la_posicion`.
14. **Break-even**: el botón del diálogo TP/SL rellena el SL con
    `mexc.break_even_price()` = entrada ± (comisión de entrada + funding ya cobrado +
    comisión de salida estimada) / contratos, redondeado **hacia afuera** del precio.
    La salida no se puede saber de antemano (MEXC la cobra al cerrar con la tasa del
    contrato), así que se usa la tasa efectiva del `totalFee` sobre el nocional del propio
    break-even. Solo se habilita si el precio de marca ya lo pasó; si el precio se mueve
    entre abrir el diálogo y guardar, `_tpsl_worker` rechaza en vez de que `plan_tp_sl`
    guarde ese SL como TP.

15. **La vista Qt caía en Tahoma en vez de Geist**: `theme.load_fonts()` registra los TTF
    con `AddFontResourceExW` (GDI), que era lo que veía Tk. Qt enumera con DirectWrite y
    además escanea al arrancar, así que `QFont("Geist")` no existía y resolvía a Tahoma con
    `exactMatch: False` (toda la app con la tipografía equivocada). Ahora
    `qt/style.cargar_fuentes()` los registra con `QFontDatabase.addApplicationFont` y
    `app.setFont` deja la familia de base; se comprueba con
    `QFontInfo(w.font()).family() == "Geist"`.
16. **El historial podía duplicar o perder datos al refrescar**: la caché actualiza la
    última versión de cada `(broker, orderId)`. El archivo local solo reconcilia cierres
    Bitunix con filas FIFO cuando la coincidencia es uno-a-uno y coincide en cantidad,
    PnL, precio de salida y tiempo; conserva los casos ambiguos. Para MEXC, un refresco con
    menos datos no pisa la fila archivada más completa.

**Cómo diagnosticar un bloqueo de UI:** `perf.log` sigue siendo el registro histórico de la
app Tk; en Qt, un modal abierto dentro de `_drenar` volvería a congelar el refresco, así que
los avisos se encolan fuera del drain (§6).

---

## 9. Cómo correr y verificar

```powershell
uv run --locked python app.py
uv run --locked python -m tradedesk
uv run --locked python -m tradedesk.qt
uv run --locked python -m pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
scripts\check.bat             # las tres cosas juntas

uv run --locked python tools/smoke_api.py
uv run --locked python tools/check_account.py
uv run --locked python tools/smoke_live.py 9
uv run --locked python tools/qt_probe.py
```

**Qué correr según lo que se tocó** (nada más que eso; la suite completa solo al commitear):

| Se tocó | Correr |
|---|---|
| `theme.py` (formato, color, fuente) | `uv run --locked python -m pytest tests/test_theme.py` |
| `layout.py` (anchos de tabla) | `uv run --locked python -m pytest tests/test_layout.py` |
| `mexc.py` (payload, `vol`, precio, fee) | `uv run --locked python -m pytest tests/test_mexc_orders.py tests/test_mexc_pure.py tests/test_phase4_visibility.py` |
| `controller.py` (hilos, cola, cierre, TP/SL, órdenes) | `uv run --locked python -m pytest tests/test_no_threaded_widgets.py tests/test_actions_close.py tests/test_mexc_orders.py` |
| `session.py` (pollers, config, catálogo, logs) | `uv run --locked python -m pytest tests/test_session_polling.py tests/test_paths.py tests/test_datos_fase3.py tests/test_phase4_visibility.py` |
| `archivo.py` (historial local y respaldos) | `uv run --locked python -m pytest tests/test_archivo.py tests/test_datos_fase3.py` |
| `bitunix.py` (modo de cuenta y payloads) | `uv run --locked python -m pytest tests/test_bitunix_orders.py` |
| `bingx.py` (fees y payloads) | `uv run --locked python -m pytest tests/test_bingx_orders.py tests/test_phase4_visibility.py` |
| `forms.py` (parseo de tarjeta/editor) | `uv run --locked python -m pytest tests/test_forms.py` |
| `pairs.py`, `qt/search.py` (buscador) | `uv run --locked python -m pytest tests/test_search.py` |
| `pnl.py` (neto del historial) | `uv run --locked python -m pytest tests/test_pnl.py` |
| `calendario.py` (agregación por día, métricas, CSV) | `uv run --locked python -m pytest tests/test_calendario.py` |
| `qt/tabla_historial.py` (actualización incremental) | `uv run --locked python -m pytest tests/test_history_render.py` |
| `qt/ventana.py`, otras `qt/tabla_*.py`, `qt/calendario.py`, `qt/cierre.py`, `qt/dialogos_base.py` (widgets) | nada automático: `python tools/smoke_live.py 9` + captura de la zona tocada |
| `__main__.py`, `app.py` (arranque) | `uv run --locked python -m pytest tests/test_launcher.py` |
| docs, comentarios, README | nada |

Si el cambio es de texto, formato o color: **captura** y listo, sin tests. Si dudas de qué test cubre algo, preguntar antes de correr la suite entera. Los tests actuales
no crean ventanas reales; los widgets Qt se verifican con captura. Si agregas pruebas GUI,
valida el ciclo de vida Qt en Windows/Python 3.14: se observó un fallo al cerrar una ventana
en ese entorno.

Antes de entregar un cambio:

- [ ] `scripts\check.bat` pasa (lint + formato + tests).
- [ ] La ventana abre sin excepciones y sin widgets cortados.
- [ ] Colores/fuentes salen de `theme.py`; números por `theme.fmt_*`.
- [ ] Los errores de API se ven en la UI, no se silencian.
- [ ] `docs/DESIGN.md` actualizado si cambió un token o componente.

Prueba real mínima: 5 USDT, 1x, DRY-RUN apagado, LONG, y cerrar con el botón de la fila.

---

## 10. Estado actual y pendientes

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
  órdenes, `Cancelar todo`, buscador, historial, IP copiable y DRY-RUN siempre encendido.
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
  reduce-only), **cerrar todo**, **cancelar** (una o todas) y **apalancamiento**.
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

**Pendiente / ideas descartadas por ahora:**

- Guardar más de un TP parcial por posición (MEXC admite un TP y un SL por stop order).
- Saldo disponible en la cabecera (`mx.assets()` ya existe, falta pintarlo).
- Cambiar el par de una tarjeta sin quitarla y volver a añadirla.
- **BingX funciona y está verificado con dinero real** (0,0001-0,0002 BTC, ~0,03 USDT de
  fees entre todas las rondas): abrir long/short a mercado, límite + cancelar, TP/SL al
  abrir y con el lápiz, cierre parcial, reverse y cierre total. Pendiente chico: la fee de
  una posición abierta (BingX no la expone) y el funding del par.
- `.exe` con PyInstaller `--onedir` si algún día aceptan el aviso de SmartScreen.

---

## 11. Glosario

- **Nocional**: `margen × apalancamiento`. Es el valor de la posición, no lo que arriesgas.
- **Contrato**: unidad de MEXC. `vol` cuenta contratos, no monedas.
- **DRY-RUN**: simula la orden y no envía nada.
- **Reverse**: cierra la posición y abre la contraria con el mismo tamaño.
- **Isolated / Cross**: margen aislado (solo esa posición) o cruzado (toda la cuenta).
