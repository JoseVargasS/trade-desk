# AGENTS.md

Documento de traspaso para quien retome **Trade Desk**. Léelo completo antes de tocar código.
Si algo aquí no coincide con el código, el código manda: corrige este archivo en el mismo cambio.

---

## 0. Cómo empezar a trabajar aquí

**Dónde está cada cosa.** El código vive en `src/tradedesk/` (layout `src`), los tests en
`tests/`, los assets **dentro del paquete** (`src/tradedesk/assets/`), los scripts sueltos en
`tools/` y los datos del usuario (`config.json`, `trades.log`, `perf.log`) en la raíz del repo,
nunca dentro del paquete: esas rutas las resuelve `tradedesk/paths.py`.

**Arranque.** `app.py` en la raíz es **solo el lanzador** (el acceso directo del escritorio
apunta a `pythonw app.py`): agrega `src` al path y llama a `tradedesk.__main__:main`. Los `.bat`
hacen lo mismo con `python -m tradedesk`. No borres ni muevas `app.py` de la raíz sin actualizar
el acceso directo, o la app deja de abrir con doble clic.

**Entorno y verificación** (Windows, Python 3.11+):

```powershell
pip install -e ".[dev]"     # deps de la app + pytest/ruff/pre-commit
python -m pytest            # 44 tests (~10 s); los `ui` se saltan sin ventana
python -m ruff check .      # lint
python -m ruff format .     # formato (obligatorio: CI corre --check)
scripts\check.bat           # lint + formato + tests de una
```

**Reglas para no romper lo que ya funciona**

- **La ruta de órdenes tiene red de seguridad**: `tests/test_mexc_orders.py` fija los payloads de
  `open_market` y `close_position` (side, type, vol, precio redondeado a `priceScale`). Si cambias
  un payload, cambia el test en el mismo commit. Nunca se prueba contra la cuenta real en tests.
- **Ningún hilo toca widgets**: `tests/test_no_threaded_widgets.py` lee el fuente y falla si un
  `*_worker` llama a `configure` / `set_*`. Los hilos solo hablan por `self.q`.
- **La fila de posiciones no crece**: `tests/test_ui_smoke.py` mide anchos, alto y los cuatro
  controles de la barra de cierre. Si se pasa, recorta columnas; no ensanches la ventana.
- **Ruff mandó el formato**: los archivos ocupan ~15 % más líneas que antes (una llamada de
  Tkinter con muchos argumentos queda un argumento por línea). El tope real ahora es **~700
  líneas**; `app.py` está cerca, así que lo siguiente que se le agregue va a un módulo nuevo.
- Colores, fuentes y formatos numéricos **solo** en `theme.py`.
- Después de tocar UI: `python tools/smoke_live.py 9` (arranca 9 s, pinta las posiciones reales y
  cierra sola; no envía órdenes).
- Antes de commitear: `scripts\check.bat` en verde.

---

## 1. Qué es y por qué existe

App de escritorio Windows para operar **futuros de MEXC a mercado** (solo market orders).
No es un bot: no hay estrategias, ni trailing, ni nada automático. Es una mesa de ejecución.

**Contexto de origen.** El usuario operaba en el terminal web de MEXC (BTC + ETH en pestañas
separadas). El navegador llegaba a ~3.4 GB en RAM y 85 % de CPU por la consola de DevTools
acumulando errores. Esta app resuelve eso: **~70 MB** y ~20-30 ms por orden (el terminal web
tarda 300-800 ms porque pasa por su gateway, su sesión y su render).

Decisiones de fondo que **no** están en discusión:

- Escritorio nativo (Tkinter + CustomTkinter), **no** web local. Un servidor local abre un
  puerto que no hace falta, y un navegador reintroduce el costo que se quería eliminar.
- **No** `.exe` por ahora: PyInstaller sin firmar dispara SmartScreen/Defender. Se usa un
  acceso directo con ícono, que para el usuario se comporta igual.
- Cada exchange tendrá **su propio módulo**, sin capas de abstracción que unifiquen firmas
  que no se parecen.

---

## 2. Cómo lo usa el usuario (flujo real)

1. Abre `Trade Desk` (acceso directo del escritorio). Arranca **sin tarjetas**.
2. `+ Añadir par` → buscador flotante → escribe (`btc`, `sol`) → `Enter` toma el primero.
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
8. Pestaña **Historial**: últimas 50 órdenes (ejecutadas, canceladas, pendientes).

`DRY-RUN` viene **siempre encendido** en cada arranque y bloquea **abrir, cerrar y reverse**.
El **TP/SL** y el **margen** sí funcionan con DRY-RUN activo: son gestión de riesgo, no
abren exposición.

---

## 3. Arquitectura

```
raiz/
  app.py                    lanzador del acceso directo (no tiene logica)
  src/tradedesk/
    __main__.py             arranque: AppUserModelID + CTk + App            25
    paths.py                DATA_DIR (raiz) y ASSETS (paquete)             13
    app.py                  ventana, estado, pollers, preview             690
    actions.py              cerrar, reverse, TP/SL, margen (mixin)        260
    cards.py                TradeCard: una tarjeta por par                 346
    closebar.py             precio + % de cierre + botones de la fila     381
    table.py                PositionsTable + HistoryTable                 544
    search.py               SearchPopup + filter_markets()                209
    dialog.py               confirm / show / ask_key (sin messagebox)     376
    theme.py                color, tipografia, radios, formatos           132
    mexc.py                 firma, endpoints, USDT->contratos, fee, liq   414
    creds.py                Windows Credential Manager                     29
    assets/                 icon.ico, icon.png, fonts/*.ttf
  tests/                    pytest: logica pura, payloads, UI (`-m ui`)
  tools/                    make_icon, smoke_api, smoke_live, check_account
  scripts/check.bat         lint + formato + tests
```

Ningún archivo debe pasar de **~700 líneas** (el formato de ruff suma ~15 % al conteo).
Si se cruza, se divide por responsabilidad. `app.py` está cerca: lo siguiente que se le
agregue va a un módulo nuevo.

### Flujo de datos

Todo pasa por **una cola** (`self.q`) y un solo consumidor en el hilo de la UI (`_drain`,
cada 120 ms). Ningún hilo toca widgets.

```
hilo _poll  ──►  q.put(("ticker", ...))      precio por tarjeta, round-robin
             ──►  q.put(("positions", ...))   cada 3 s
             ──►  q.put(("orders", ...))      órdenes abiertas, cada 3 s
             ──►  q.put(("history", ...))     cada 15 s, solo en su pestaña
hilo _calc  ──►  q.put(("preview", ...))     contratos/fee/liq por tarjeta
hilo orden  ──►  q.put(("order", ...))       resultado de la orden
```

`_drain` traduce cada mensaje a widgets. Las órdenes corren en su propio hilo para no
congelar la UI; los botones de la tarjeta se deshabilitan mientras tanto (`set_busy`).

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

**Seguridad de la key.** Se crea en MEXC con permisos de futuros + lectura, **sin retiros ni
transferencias**, y con **IP vinculada** (sin IP la key expira a los 90 días). Si el ISP cambia
la IP, la API responde `406 Accessing IP is not in the whitelist`; la app muestra la IP actual
en la cabecera con botón para copiarla.

---

## 5. Seguridad

- La key vive en el **Windows Credential Manager** (`creds.py`). Nunca en el código, nunca en
  `config.json`, nunca en un log.
- `trades.log` no contiene material sensible.
- DRY-RUN bloquea abrir, cerrar y reverse; TP/SL y margen pasan siempre. Es la red de
  seguridad principal.
- La app no escucha puertos ni corre nada en segundo plano al cerrarse.

---

## 6. Reglas de UI (resumen; el detalle está en `docs/DESIGN.md`)

- Tokens **solo** en `theme.py`. Ningún color o fuente literal en otro archivo.
- UI en `Geist`, **todo número en `theme.NUM`**, que es la misma familia (proporcional,
  no tabular): las columnas van alineadas a la derecha, así que el borde derecho no se mueve.
  Se probó `Geist Mono` y se descartó por ~19 % más ancha. Se registran en el proceso con
  `AddFontResourceExW`; no se instalan en Windows.
- Todo número se formatea con `theme.fmt_*`. PnL y fee con 4 decimales; precios de orden
  límite con `fmt_price_exact` (`priceScale` del contrato).
- La fila de posiciones no crece: la barra de cierre va en dos líneas dentro de los 200 px
  de la columna de acciones (`[Mercado ▾][100% ▾]` / `[Cerrar LONG][Reverse]`). Sus popups
  se anclan bajo el control, no se centran, y son modales (`grab_set`) como el buscador.
- Nada de `messagebox`: usar `dialog.confirm` / `dialog.show` / `dialog.ask_key`.
- La tabla **no usa `ttk.Treeview`** (no permite color por celda).
- `pack` reparte espacio en orden de llamada: lo que no debe encogerse va **primero**.
- **Ningún worker toca widgets.** Los hilos solo hacen `q.put`; el hilo de la UI pinta.
  Comprobado por `tests/test_no_threaded_widgets.py`: un `configure`/`set_*` desde un hilo
  deja la ventana sorda.
- **Ningún request desde el hilo de la UI.** `_open_search` carga el catálogo en un hilo y
  abre el popup por la cola. Pedirlo en línea congelaba la ventana hasta 8 s.
- El buscador es **modal** (`grab_set`): si quedaba abierto flotando sobre las tarjetas se
  comía los clics y parecía que los inputs estaban deshabilitados.
- **Ningún `dialog.show`/`confirm` dentro de `_drain`.** Un modal ahí adentro congela el
  callback todo el tiempo que el usuario lo deje abierto (`perf.log` llegó a registrar
  drains de 1.6 s). Los avisos pasan por `App._notice`, que los encola y abre uno por vez
  fuera del drain (`tests/test_app_notices.py`).

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
| **Cero dependencias de UI nuevas** | `customtkinter` + `httpx` + `keyring`. Nada de Qt (200 MB) |

---

## 8. Bugs ya resueltos (no reintroducirlos)

1. **403 del WAF** con el User-Agent por defecto de Python → hay que mandar uno de navegador.
2. **`takerFeeRate` inconsistente** entre `/contract/detail` (individual) y el catálogo.
   `markets()` **no** debe alimentar el cache de `contract()`.
3. **Rate limit del ticker**: 10/2 s. Un loop a 5/s lo rompe.
4. **`pack` y barras inferiores**: si empaquetas la tabla con `expand=True` antes que la barra
   de acciones, la barra queda en 0 px.
5. **Tarjeta cortada**: `grid_propagate(False)` exige `height` explícito.
6. **Buscador vacío al inicio**: se le pasaba `self.mx._markets` (`None` antes de la primera
   carga) y el constructor moría antes de programar el foco. Usar `App.markets()`.
7. **Ícono de Python en la barra de tareas**: hay que declarar `iconbitmap` + `iconphoto` y
   fijar `SetCurrentProcessExplicitAppUserModelID` **antes** de crear la ventana.
8. **`CTkEntry` con `placeholder_text` no acepta tecleo**: el placeholder se escribe como
   texto real y el clic en el `tk.Entry` interno no siempre lo limpia; el campo queda sordo.
   Los campos de las tarjetas y de los formularios usan **`textvariable` sin placeholder**
   y una etiqueta aparte. La excepción son el buscador y el diálogo de API key: ahí el
   foco se fuerza al abrir, así que el placeholder nunca queda delante del cursor.
9. **Chip del par encima de la ✕**: empacar la ✕ primero (`side="right"`) y el chip con
   `fill="x", expand=True`.
10. **Selección perdida en cada refresco**: se restaura por `positionId`, no por `iid`.
11. **TP/SL no vienen en `open_positions`**: hay que cruzarlos con `stoporder/list/orders`.
    Al reemplazar, cancelar primero (`stoporder/cancel`) o MEXC acumula órdenes huérfanas.
12. **El buscador flotando encima de las tarjetas**: `SearchPopup` es `overrideredirect` y
    antes no era modal. Si quedaba abierto tapaba los inputs y los clics no llegaban
    (se percibía como "el campo está deshabilitado unos segundos"). Ahora abre con
    `grab_set()`, se cierra con `Escape`, con clic en su fondo o al elegir, y devuelve el foco.
13. **`markets()` desde el hilo de la UI**: 0.5 s en frío y hasta 8 s si el request se cuelga.
    `_open_search` lo pide en un hilo y abre el popup por la cola.
14. **Un worker tocando un widget deja la ventana sorda**: Tkinter no es thread-safe.
    Un `card.set_preview(...)` desde un hilo bloquea el bucle de eventos y la UI deja de
    responder varios segundos (se vio como "el input está deshabilitado y luego revive").
    Los hilos **solo** hablan por `self.q`. `tests/test_no_threaded_widgets.py` falla si un
    `*_worker` llama a
    `configure`, `set_*`, `insert` o `delete` sobre un widget.
15. **TP/SL rechazado con 5003 en el caso más normal**: si entras en ganancia y pones el SL
    por encima del precio (LONG), MEXC lo rechaza porque ahí el único nivel válido es el TP.
    `plan_tp_sl()` lo mueve a TP y avisa por diálogo; si el TP ya está en ese lado, explica
    que deje el SL del lado de la pérdida en vez de mostrar el error en inglés.
16. **TP/SL rechazado con 5004 al reemplazar**: cancelar y recolocar sin esperar deja la
    orden vieja contabilizada. `_wait_tpsl_clear()` sondea `stoporder/list/orders` hasta
    que la posición queda a 0 (máx. 2.5 s) antes de volver a colocar.

**Cómo diagnosticar un bloqueo de UI:** `perf.log` registra con hora cualquier callback
de `_drain` que tarde más de 200 ms **y los mensajes que lo causaron**
(`drain 1645 ms · history,positions`). Si el archivo tiene líneas, ahí está el culpable.

---

## 9. Cómo correr y verificar

```powershell
python app.py                 # lanzador del acceso directo, con consola para ver errores
python -m tradedesk           # lo mismo, con PYTHONPATH=src
python -m pytest              # 44 tests: logica pura, payloads y UI
python -m pytest -m ui        # solo los de ventana (miden la fila y los popups)
python -m ruff check .        # lint
python -m ruff format --check .   # formato (lo que corre el CI)
scripts\check.bat             # las tres cosas juntas

python tools/smoke_api.py     # red real: precio, contrato, USDT -> contratos
python tools/check_account.py # consulta la cuenta real: saldo, posiciones, historial
python tools/smoke_live.py 9  # arranca 9 s, pinta las posiciones y cierra sola
# perf.log registra cualquier callback de la UI que tarde > 200 ms
```

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
cerrar todas, DRY-RUN, historial, búsqueda, conversión de tamaño.

**Sin probar contra posición real:** `Reverse` y el cierre desde el botón de la fila
(la ruta existe y la firma está validada, pero no se ejecutó con posición abierta).
El **cierre parcial** (`vol < holdVol`) y el **cierre límite** (`type=1`) están probados
solo en el payload (`tests/test_mexc_orders.py`): falta ejecutarlos una vez contra una
posición real.

**Pendiente / ideas descartadas por ahora:**

- Guardar más de un TP parcial por posición (MEXC admite un TP y un SL por stop order).
- Saldo disponible en la cabecera (`mx.assets()` ya existe, falta pintarlo).
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
