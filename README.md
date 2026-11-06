# Trade Desk

Ventana local para operar futuros de **MEXC, Bitunix y BingX** a mercado o a límite. Sin navegador, sin servidor, sin puertos abiertos.

## Arrancar

Doble clic en **`trade-desk`** (el acceso directo del escritorio) o en `Iniciar.bat`.

Si no abre nada, usa `Iniciar-con-consola.bat` para ver el error.

## Primera vez

La app pide tu API key y secret, los prueba contra el broker antes de guardarlos y quedan en el
**Administrador de credenciales de Windows**, no en archivos. Cada broker se carga por separado
desde el botón **Brokers** de la cabecera: ahí se ve cuál está conectado y su saldo.

Crear la key en MEXC → perfil → API Management:

- Permisos: futuros/trading ✅ y lectura ✅
- **Withdraw ❌** y transfer ❌ (no negociable)
- API Usage: **Open API**
- Link IP Address: **agrega tu IP** (sin IP la key dura 90 días)

En Bitunix y BingX la key también tiene que ir atada a la IP; la app fuerza IPv4 porque las
keys se validan contra la dirección desde la que sale la conexión.

La app muestra tu IP arriba a la derecha, con botón para copiarla.

## Uso

- **Tarjetas en fila.** Cada tarjeta es un par con su propio apalancamiento, margen,
  tamaño, TP/SL y **broker**. La app arranca **sin tarjetas**: **`+ Añadir par`** agrega la
  primera y las siguientes van a la derecha; se arrastran desde la cabecera para reordenarlas.
  El nombre se muestra como en MEXC (`GOLD(XAU)USDT`, no `XAU_USDT`). El botón del broker
  (a la derecha del nombre) elige en cuál opera esa tarjeta; arranca **sin broker** y con
  `LONG`/`SHORT` apagados hasta que elijas uno.
- **Apalancamiento**: escribes el valor o usas los presets `1 / 5 / 10 / 15 / 20 / 50`.
- **Margen**: `Aislado` por defecto, `Cruzado` si lo cambias.
- **Tamaño** + toggle `Margen` / `Nocional`:
  - `Margen` 100 a 10x → 1,000 USDT nocionales
  - `Nocional` 1,000 → 1,000 USDT nocionales
- **Abrir a mercado o a límite**: el chip `Mercado` al lado de *Tamaño* abre el menú con
  `Mercado` y `Límite…` (el precio viene con el último). Si no lo tocas, la orden sale a
  mercado; si eliges límite, puede quedar sin llenar y queda como orden pendiente.
- **TP / SL**: opcionales. Vacíos = entra sin ellos. Ojo: la dirección se mide contra el
  **precio actual**, no contra la entrada. Un SL puesto del lado de la ganancia (por encima
  del precio en un LONG) no es un stop loss: la app lo guarda como **TP** y te avisa.
- **Resumen** en cada tarjeta: contratos, nocional real, fee estimada y liquidación
  estimada (long / short, solo en margen aislado). En Bitunix se muestran monedas y nocional;
  en BingX el resumen todavía no se calcula (ver `docs/PLAN.md`).
- **DRY-RUN** viene **activado**: no abre ni cierra posiciones. El **TP/SL**, el **margen**,
  el **BE** y **cancelar órdenes** sí funcionan, porque son gestión de riesgo.
  El checkbox `DRY-RUN` de la cabecera pasa a `REAL` en rojo cuando lo apagas.
- **Buscar par**: `+ Añadir par` abre una ventana flotante. Escribes, `Enter` toma el
  primer resultado (los pares USDT van primero), `Esc` cierra.

## Posiciones e historial

**Pestaña Posiciones**

| Acción | Cómo |
|---|---|
| Cerrar una | botón **Cerrar LONG / SHORT** al final de la fila (toma el color del PnL) |
| Cerrar una parte | campo `%` de la fila: abre el panel con el slider (`Cierras: N USDT ≈ M contratos`). Una posición de una sola unidad no se puede partir: el `%` sale deshabilitado con el motivo en el tooltip |
| Cerrar a precio límite | campo `Mercado` de la fila: elige `Límite…` y escribe el precio |
| Cerrar varias | marca los checkboxes → **Cerrar seleccionadas** |
| Reverse | botón **Reverse** en la fila (nativo en MEXC; en Bitunix y BingX cierra y reabre) |
| Cerrar todo | botón **CERRAR TODO** con confirmación |
| Mover a break-even | botón **Poner a BE**: abre la lista de posiciones, las que todavía no llegan salen apagadas con el motivo, `Todos` marca las que se pueden |

Sin tocar los dos campos, el botón cierra **a mercado y al 100 %**. La tabla se refresca cada 3 s y
mantiene tu selección. PnL y fee van con color (verde ganancia, rojo pérdida/costo), con su importe
en USDT, el % que representan del margen y del nocional, y el **ahorro de fees** cuando MEXC lo
reporta (`lowSaveTotalFee`). Arriba de la tabla está el **bruto y el neto de todas las posiciones**
(neto = bruto − comisión pagada − funding − salida estimada).

**Pestaña Historial**

Una fila por **operación** (apertura + sus cierres juntos), no por orden: apertura, cierre, par con
el broker, lado, **tamaño en USDT**, entrada, salida, PnL, fee, **neto** y estado
(`Cerrada` / `Parcial` / `Abierta`). Se refresca cada 15 s mientras esté abierta, y **Ver más**
pide la página siguiente de cada broker. Lo que el exchange ya purgó sigue apareciendo: se archiva
en `operaciones.json`.

## Seguridad

- La key no puede retirar fondos.
- Cada orden de apertura lleva un `externalOid` único. Ojo: **no** hay reintento automático, así
  que si un envío queda en duda (timeout) hay que mirar Posiciones antes de reenviar.
- Nada corre en segundo plano. Cierras la ventana y no queda nada vivo.
- Las posiciones y los TP/SL viven en el exchange, no en tu PC.
- `trades.log` guarda cada intento (hora, resultado, `orderId`, símbolo, `vol`), nunca la key.

## Cuando algo falla

| Mensaje | Que hacer |
|---|---|
| `Tu IP no esta autorizada` | Tu ISP te cambió la IP. Cópiala de la barra superior y agrégala en MEXC. |
| `Firma invalida` | El secret está mal. Vuelve a guardar la key. |
| `API key expirada` | Crea una key nueva con IP vinculada. |
| `Demasiadas peticiones` | Espera un segundo. MEXC permite 4 órdenes cada 2 s. |
| `Tamaño muy chico` | Sube el nocional: no alcanza el mínimo del contrato. |
| `HTTP 403` | El WAF de MEXC bloqueó la petición. Reintenta; si persiste, avisa. |

## Estructura

```
app.py                  lanzador (lo que abre el acceso directo)
src/tradedesk/          la app
  session.py            pollers, cola, config y caches
  controller.py         abrir, cerrar, reverse, TP/SL, margen, órdenes y BE
  operaciones.py        empareja órdenes en operaciones (historial)
  archivo.py            operaciones guardadas en disco
  forms.py              parseo de tarjetas y del editor de orden
  layout.py             anchos y altos de las tablas
  pairs.py              filtro del buscador de pares
  brokers.py            nombres y títulos de los brokers
  theme.py              tokens de color, fuente y formatos
  mexc.py               firma HMAC, endpoints, USDT → contratos, fee, liquidación
  bitunix.py            firma, endpoints, monedas (qty) y specs
  bingx.py              firma, endpoints, monedas (qty) y specs
  creds.py              Windows Credential Manager
  paths.py              dónde viven los datos y los assets
  qt/                   ventana, tarjetas, diálogos, estilos y buscador (PySide6)
  assets/               iconos y fuentes Geist
tests/                  pruebas (pytest): 141
tools/                  utilidades: icono, chequeos contra la API y la cuenta
docs/DESIGN.md          sistema de diseño
docs/PLAN.md            plan de trabajo vivo (fases, estado y bitácora)
AGENTS.md               reglas para agentes
```

Los datos (`config.json`, `operaciones.json`, `trades.log`) viven en la raíz del repo y git los
ignora.

Requiere Python 3.11+: `pip install -e ".[dev]"` (o `pip install PySide6-Essentials httpx keyring`).

Verificación:

```powershell
scripts\check.bat             # lint + formato + tests
python -m pytest              # solo los tests
python tools/smoke_api.py     # red: precio, contrato, conversión de tamaño
python tools/smoke_live.py 9  # abre la app 9 s con la cuenta real y la cierra
python tools/check_account.py # consulta la cuenta: saldo, posiciones, historial
```
