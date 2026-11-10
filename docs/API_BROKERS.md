# 4. MEXC Futures API - lo que hay que saber

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

**Lotes (ENVIAR TODAS y CERRAR TODO): los brokers salen en paralelo y las tarjetas de un
mismo broker van en serie.** Cada apertura gasta ticker + apalancamiento + orden, así que
dentro de un broker las peticiones comparten el mismo límite; entre brokers no hay nada
compartido. Los resultados siempre se ordenan por tarjeta, no por llegada.

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
reenviar** (`AGENTS.md` §5).

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
POST /api/v1/futures/trade/close_all_position   NO se usa: responde code 0 aunque no cierre nada
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

**`flash_close_position` acepta 5 req/s/uid**: `close_all` manda los cierres en
paralelo (hasta 4 a la vez), pero marcados con `Ritmo` para no pasarse de ese ritmo.
Los brokers se cierran entre sí en paralelo porque cada uno tiene su propio límite.

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

