# AGENTS.md

Documento de traspaso para quien retome **Trade Desk**. Léelo completo antes de tocar código.
Si algo aquí no coincide con el código, el código manda: corrige este archivo en el mismo cambio.

---

## 0. Cómo empezar a trabajar aquí

**Dónde está cada cosa.** El código vive en `src/tradedesk/` (layout `src`), los tests en
`tests/`, los assets **dentro del paquete** (`src/tradedesk/assets/`), los scripts sueltos en
`tools/` y los datos del usuario (`config.json`, `trades.log`) en la raíz del repo,
nunca dentro del paquete: esas rutas las resuelve `tradedesk/paths.py`.

**Arranque.** `app.py` en la raíz es **solo el lanzador** (el acceso directo del escritorio
apunta a `pythonw app.py`): agrega `src` al path y llama a `tradedesk.__main__:main`. Los `.bat`
hacen lo mismo con `python -m tradedesk`. No borres ni muevas `app.py` de la raíz sin actualizar
el acceso directo, o la app deja de abrir con doble clic.

**Entorno y verificación** (Windows, Python 3.11+):

```powershell
pip install -e ".[dev]"     # deps de la app + pytest/ruff/pre-commit
python -m pytest            # ~70 tests (~15 s): logica pura, payloads y parseo
python -m ruff check .      # lint
python -m ruff format .     # formato (obligatorio: CI corre --check)
scripts\check.bat           # lint + formato + tests de una
```

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
  archivo se cruza, se parte por responsabilidad (`view.py` ya salió de `shell.py`).
- Colores, fuentes y formatos numéricos **solo** en `theme.py`. La vista Qt usa
  `qt.style.fnt`, que da el tamaño en **píxeles** (no en puntos).
- **Solo se corre el test que cubre lo que se tocó** (matriz en §9). Nunca la suite entera "por
  si acaso": cuesta ~15 s y gasta cuota del usuario sin aportar nada si el cambio fue de un
  texto o un decimal. Si no hay test para esa zona, alcanza con mirar el resultado (captura).
- Después de tocar UI: `python tools/smoke_live.py 9` (arranca 9 s, pinta las posiciones reales y
  cierra sola; no envía órdenes). Si se tocaron tablas, `python tools/qt_probe.py` mide el
  repintado con 8 tarjetas y 200 filas.
- Antes de commitear: `scripts\check.bat` en verde (una sola vez, no en cada paso).

---

## 1. Qué es y por qué existe

App de escritorio Windows para operar **futuros de MEXC a mercado** (solo market orders).
No es un bot: no hay estrategias, ni trailing, ni nada automático. Es una mesa de ejecución.

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
2. `+ Añadir par` → buscador modal → escribe (`btc`, `sol`) → `Enter` toma el primero.
3. Configura apalancamiento (entry o presets 1/5/10/15/20/50), margen (Aislado por defecto),
   modo de tamaño (Margen o Nocional) y escribe el **tamaño en USDT** (vacío por defecto).
4. Opcional: TP y SL.
5. Mira el resumen de la tarjeta: contratos, nocional real, fee estimada, liquidación L/S.
6. `LONG` o `SHORT` → diálogo de confirmación → orden a mercado. El chip `Mercado ▾`
   de la tarjeta (al lado de *Tamaño*) permite abrir **a límite**: escribe el precio y
   la orden sale `type=1`; sin tocarlo sigue saliendo a mercado.
7. Abajo, pestaña **Posiciones**: cada fila trae `[Mercado ▾]`, `[% ▾]` y el botón
   `Cerrar LONG` / `Cerrar SHORT` (del color del PnL). Sin tocar nada cierra **a mercado y
   al 100 %**, con el mismo diálogo de siempre; un precio en el primer campo la vuelve orden
   **límite** (puede quedar sin llenar) y el `%` permite cerrar una parte. También:
   checkboxes + `Cerrar seleccionadas`, `Reverse` y `CERRAR TODO` (siempre a mercado).
   El **lápiz de TP/SL** abre el editor con dos líneas vivas (`TP 101,200.0 → +15.2400 USDT`
   y `SL 99,500.0 → -6.3500 USDT`) y un botón `Break-even` que rellena el SL con el precio
   que deja la operación en cero (comisión de entrada + salida + funding). Se habilita solo
   cuando el precio ya lo pasó; si no alcanza, el botón sale gris y la nota dice cuánto falta.
8. Pestaña **Órdenes** (panel estilo MEXC): las límite que todavía no se llenaron, con par
   (+`Perpetual` y el % llenado debajo), fecha, dirección (`Compra LONG` / `Venta SHORT`),
   apalancamiento, monto, precio, llenado, margen usado, TP/SL en dos líneas, fee y estado.
   Los **lápices** de Monto, Precio y TP/SL abren el editor (lado, apalancamiento, margen,
   precio, TP y SL); en la columna de acciones están `Modificar` y `Cancelar`, y arriba a la
   derecha `Cancelar todo`. Una orden límite no aparece en Posiciones hasta que se llena.
9. Pestaña **Historial**: últimas 50 órdenes (ejecutadas, canceladas, pendientes).

`DRY-RUN` viene **siempre encendido** en cada arranque y bloquea **abrir, cerrar y reverse**.
El **TP/SL**, el **margen** y **cancelar órdenes** sí funcionan con DRY-RUN activo: son
gestión de riesgo, no abren exposición. **Modificar** una orden sí queda bloqueado: reenviarla
es abrir.

---

## 3. Arquitectura

```
raiz/
  app.py                    lanzador del acceso directo (no tiene logica)
  src/tradedesk/
    __main__.py             arranque: AppUserModelID + vista Qt           18
    paths.py                DATA_DIR (raiz) y ASSETS (paquete)            13
    session.py              pollers, cola, config y caches sin UI         210
    controller.py           casos de uso: abrir, cerrar, TP/SL, ordenes   420
    forms.py                parseo puro de tarjeta y editor de orden       60
    layout.py               anchos/altos de las tablas (sin UI)            60
    pairs.py                filtro puro del buscador de pares              60
    theme.py                color, tipografia, radios, formatos           120
    mexc.py                 firma, endpoints, USDT->contratos, fee, liq   500
    creds.py                Windows Credential Manager                     29
    assets/                 icon.ico, icon.png, fonts/*.ttf
    qt/
      __main__.py           abre la ventana                                 26
      view.py               ventana: cabecera, deck, tablas, drenaje        682
      tarjeta.py            tarjeta de par y barra de cierre de la fila    279
      dialogs.py            confirm, aviso, form, API key, TP/SL, editor   568
      style.py              fnt, etiqueta, boton, Segmentado, qss           160
      search.py             buscador de pares                               90
      cells.py              delegado de celdas + icono de lapiz             71
      shell.py              ventana de prueba para medir repintado        152
  tests/                    pytest: logica pura, payloads y parseo
  tools/                    make_icon, smoke_api, smoke_live, check_account, qt_probe
  scripts/check.bat         lint + formato + tests
```

Ningún archivo debe pasar de **~700 líneas** (el formato de ruff suma ~15 % al conteo).
Si se cruza, se divide por responsabilidad: `view.py` ya salió de `shell.py`.

### Flujo de datos

Todo pasa por **una cola** (`session.q`) y un solo consumidor en el hilo de la UI
(`VistaQt._drenar`, cada 120 ms). Ningún hilo toca widgets.

```
hilo _poll      ──►  q.put(("ticker", ...))      precio por tarjeta, round-robin
                ──►  q.put(("positions", ...))   cada 3 s
                ──►  q.put(("orders", ...))      órdenes abiertas, cada 3 s
                ──►  q.put(("history", ...))     cada 15 s, solo en su pestaña
hilo catálogo   ──►  q.put(("markets", ...))     1.171 pares del buscador
hilo ip         ──►  q.put(("ip", ...))          IP pública para la cabecera
hilo orden      ──►  q.put(("order", ...))       resultado de la orden
```

`controller.Control` recibe `session` y un `UiPort` (`qt.dialogs.QtPort`) con
`confirm`, `show`, `form`, `tpsl`, `editar_orden` y `status`. La UI solo pinta y lee
los controles; los casos de uso y los payloads viven en el controlador.

### Persistencia

`config.json` (ignorado por git) guarda **solo** `symbol`, `leverage`, `margin`, `size_mode`
por tarjeta. **No** guarda tamaño, TP, SL ni DRY-RUN (ver §7).

`trades.log` registra cada intento: hora, resultado, `orderId`, símbolo, `vol`. Nunca la key.

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

El poller va a **~1.4 req/s** (delay base 0.70 s) con backoff multiplicativo
(0.70 s → 5.0 s) si algo falla. Subirlo produce `510 Demasiadas peticiones`.

**TP/SL: la dirección se mide contra el precio actual, no contra la entrada.**
LONG → TP por encima y SL por debajo; SHORT al revés. Un `stopLossPrice` del lado
de la ganancia se rechaza con **5003** aunque esté lejos; ese mismo nivel sí entra
como `takeProfitPrice`. `mexc.plan_tp_sl()` aplica la regla antes de enviar.
El `stoporder/cancel` es **asíncrono**: recolocar de inmediato da **5004**
("greater than the closable amount"), por eso se espera a que la lista quede vacía.

**Idempotencia.** Cada orden lleva `externalOid` único. Si la red falla y se reintenta, MEXC
rechaza el duplicado en vez de abrir dos posiciones.

**Fee estimada.** `takerFeeRate` viene del endpoint individual. Ojo: MEXC devuelve valores
distintos entre llamadas (se observó `0.0002` y `0.0004` en la misma sesión). Es una
**estimación**, no un dato contable.

La columna Fee de posiciones muestra **comisión + funding** (`mexc.fee_desglose`):
`totalFee` es la comisión ya cobrada al abrir y `holdFee` el funding; `lowSaveTotalFee` es
"Fees saved" y **no** suma. El importe lleva subrayado punteado y al pasar el puntero aparece
el desglose (`tooltip.NumeroConDetalle`). Ojo: el terminal de MEXC pinta su "Fees" como
`totalFee + lowSaveTotalFee`, así que su número es más alto que el real.

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

---

## 6. Reglas de UI (resumen; el detalle está en `docs/DESIGN.md`)

- Tokens **solo** en `theme.py`. Ningún color o fuente literal en otro archivo; el QSS sale de
  `qt/style.py::qss()`.
- UI en `Geist`, **todo número en `theme.NUM`**, que es la misma familia (proporcional,
  no tabular): las columnas van alineadas a la derecha, así que el borde derecho no se mueve.
  Se probó `Geist Mono` y se descartó por ~19 % más ancha. Se registran en el proceso con
  `AddFontResourceExW`; no se instalan en Windows.
- Todo número se formatea con `theme.fmt_*`. PnL y fee con 4 decimales; precios de orden
  límite con `fmt_price_exact` (`priceScale` del contrato).
- La fila de posiciones no crece: la barra de cierre va en dos líneas dentro de los 200 px
  de la columna de acciones (`[Mercado ▾][100% ▾]` / `[Cerrar LONG][Reverse]`).
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
- La selección de posiciones se restaura por `positionId` en cada refresco; no se pierde
  porque el poller reemplace las filas cada 3 s.

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

**Cómo diagnosticar un bloqueo de UI:** `perf.log` sigue siendo el registro histórico de la
app Tk; en Qt, un modal abierto dentro de `_drenar` volvería a congelar el refresco, así que
los avisos se encolan fuera del drain (§6).

---

## 9. Cómo correr y verificar

```powershell
python app.py                 # lanzador del acceso directo, con consola para ver errores
python -m tradedesk           # lo mismo, con PYTHONPATH=src
python -m tradedesk.qt        # abre la vista Qt directamente
python -m pytest              # ~70 tests: logica pura, payloads y parseo
python -m ruff check .        # lint
python -m ruff format --check .   # formato (lo que corre el CI)
scripts\check.bat             # las tres cosas juntas

python tools/smoke_api.py     # red real: precio, contrato, USDT -> contratos
python tools/check_account.py # consulta la cuenta real: saldo, posiciones, historial
python tools/smoke_live.py 9  # arranca 9 s, pinta posiciones y ordenes, cierra sola
python tools/qt_probe.py      # ms de repintado (objetivo <= 60)
```

**Qué correr según lo que se tocó** (nada más que eso; la suite completa solo al commitear):

| Se tocó | Correr |
|---|---|
| `theme.py` (formato, color, fuente) | `python -m pytest tests/test_theme.py` |
| `layout.py` (anchos de tabla) | `python -m pytest tests/test_layout.py` |
| `mexc.py` (payload, `vol`, precio, fee) | `python -m pytest tests/test_mexc_orders.py tests/test_mexc_pure.py` |
| `controller.py` (hilos, cola, cierre, TP/SL, órdenes) | `python -m pytest tests/test_no_threaded_widgets.py tests/test_actions_close.py tests/test_mexc_orders.py` |
| `session.py` (pollers, config, catálogo) | `python -m pytest tests/test_paths.py` + `python tools/smoke_live.py 9` |
| `forms.py` (parseo de tarjeta/editor) | `python -m pytest tests/test_forms.py` |
| `pairs.py`, `qt/search.py` (buscador) | `python -m pytest tests/test_search.py` |
| `qt/view.py`, `qt/dialogs.py` (widgets) | nada automático: `python tools/smoke_live.py 9` + captura de la zona tocada |
| `__main__.py`, `app.py` (arranque) | `python -m pytest tests/test_launcher.py` |
| docs, comentarios, README | nada |

Si el cambio es de texto, formato o color: **captura** y listo, sin tests. Si dudas de qué
test cubre algo, preguntar antes de correr la suite entera. Los widgets Qt se verifican con
captura: los tests no abren ventanas (crear/destruir Qt en la misma corrida de pytest revienta
en Windows con Python 3.14).

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

**Migración a Qt terminada (F1–F6):**

- `python app.py` y el acceso directo abren la **vista Qt**; `python -m tradedesk.qt` hace lo
  mismo. La app de Tkinter y sus módulos (`app.py` del paquete, `ui.py`, `cards.py`,
  `closebar.py`, `table.py`, `orders.py`, `search.py`, `dialog.py`, `tooltip.py`, `actions.py`)
  se borraron; `customtkinter` salió de las dependencias.
- `session.py` carga config/catálogo, pollers y caches. `controller.py` tiene los casos de uso
  (abrir, cerrar, cerrar todo, reverse, TP/SL, margen, modificar/cancelar) y `qt/dialogs.py`
  implementa el `UiPort`. Los payloads y mensajes son los mismos de antes.
- La vista Qt ya opera: LONG/SHORT, barra de cierre con `Mercado ▾` / `% ▾`, checkboxes +
  `Cerrar seleccionadas`, `CERRAR TODO`, `Reverse`, lápices de TP/SL y margen, editor de
  órdenes, `Cancelar todo`, buscador, historial, IP copiable y DRY-RUN siempre encendido.
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

**F7 (opcional, no empezada):** gráficos de velas con TP/SL arrastrables (`pyqtgraph`).

**Pendiente / ideas descartadas por ahora:**

- Guardar más de un TP parcial por posición (MEXC admite un TP y un SL por stop order).
- Saldo disponible en la cabecera (`mx.assets()` ya existe, falta pintarlo).
- Cambiar el par de una tarjeta sin quitarla y volver a añadirla.
- Otros exchanges: **Bitunix** y **BingX** (documentados en la conversación de origen).
  Bitunix: firma SHA256 doble, TP/SL en la misma orden, sin close-all.
  BingX: v1 y v2 conviven, TP/SL requiere `positionId` (dos pasos).
- `.exe` con PyInstaller `--onedir` si algún día aceptan el aviso de SmartScreen.

---

## 11. Glosario

- **Nocional**: `margen × apalancamiento`. Es el valor de la posición, no lo que arriesgas.
- **Contrato**: unidad de MEXC. `vol` cuenta contratos, no monedas.
- **DRY-RUN**: simula la orden y no envía nada.
- **Reverse**: cierra la posición y abre la contraria con el mismo tamaño.
- **Isolated / Cross**: margen aislado (solo esa posición) o cruzado (toda la cuenta).
