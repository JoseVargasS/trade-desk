# Trade Desk

Ventana local para operar futuros de **MEXC, Bitunix y BingX** a mercado o a límite. Sin navegador, sin servidor, sin puertos abiertos.

## Instalar y arrancar en Windows

1. Descarga el repo desde GitHub (con **Code → Download ZIP**) o clónalo con Git. Descomprime
   el ZIP en una carpeta fija, por ejemplo `Documentos\Trade Desk`; no lo ejecutes desde la
   carpeta temporal de Descargas.
2. Abre esa carpeta y haz doble clic en **`Iniciar.bat`**. Necesitas conexión a internet la
   primera vez. El instalador prepara `uv`, usa un Python 3.11+ que ya tengas o instala Python
   3.13 si hace falta, instala las dependencias de la app, crea **Trade Desk** en tu escritorio y
   abre la ventana. No requiere permisos de administrador.
3. Las siguientes veces puedes abrirla desde el acceso directo del escritorio. Si vuelves a
   ejecutar `Iniciar.bat`, revisará que el entorno siga listo y volverá a abrir la app.

Si mueves la carpeta del repo, ejecuta `Iniciar.bat` desde la nueva ubicación para actualizar el
acceso directo.

Si aparece un error, ejecuta **`Iniciar-con-consola.bat`** para ver el detalle.

Este método ejecuta la app desde Python; el Administrador de tareas puede seguir mostrando el
proceso como **Python**. El acceso directo y la ventana sí usan el nombre y el ícono de Trade Desk.

## Primera vez: conectar los brokers

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

En otra laptop debes guardar las keys de nuevo desde **Brokers**. No se transfieren con el repo:
Windows las protege en el Administrador de credenciales de cada equipo.

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
- **Enviar todas**: la fila `Lote` de cada tarjeta (`—` / `LONG` / `SHORT`) marca el lado que
  esa tarjeta manda, y el botón **ENVIAR TODAS (N)** de arriba del deck envía esas N de una vez
  con **una sola confirmación**. Cada una usa su propio margen, apalancamiento, tamaño y TP/SL;
  las que no tienen broker o cuyo par no está disponible se omiten y la confirmación lo dice.
  El selector arranca en `—` y no se guarda.
- **Resumen** en cada tarjeta: MEXC muestra contratos, nocional, fee y liquidación estimada
  (long / short, solo en margen aislado); Bitunix muestra monedas y nocional; BingX muestra
  monedas, nocional y fee estimada.
- **DRY-RUN** viene **activado**: no abre, cierra ni revierte posiciones. El **TP/SL**, el **margen**,
  el **BE** y **cancelar órdenes** sí funcionan, porque son gestión de riesgo.
  **Modificar una orden queda bloqueado**: implica reenviarla.
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
| Mover a break-even | botón **Poner a BE** arriba de la tabla: abre la lista de posiciones, las que todavía no llegan salen apagadas con el motivo, `Todos` marca las que se pueden |

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

El historial solo actualiza las filas que cambiaron, inserta o reordena las necesarias y conserva
el scroll. En Órdenes, las condicionales TP/SL de BingX se muestran y se pueden cancelar, pero no
se editan desde esa pestaña.

**Pestaña Órdenes**

Las límite que todavía no se llenaron: par con el `Perpetual` y el % llenado, fecha, dirección
(`Compra LONG` / `Venta SHORT`), apalancamiento, monto, precio, llenado, margen usado, TP/SL, fee
y estado. Los lápices de **Monto**, **Precio** y **TP/SL** abren el editor; en acciones están
**Modificar** (cancela y reenvía, por eso DRY-RUN la bloquea) y **Cancelar**, y arriba a la
derecha **Cancelar todo**.

**Pestaña Calendario**

El mes en cuadrícula con el neto de cada día (verde/rojo) y el día de hoy marcado con un
círculo; al hacer clic en un día se listan sus operaciones al lado. Al costado, **Neto del mes**
con la curva acumulada y **Resumen del mes** (mejor y peor día, profit factor, rachas,
drawdown, fees y totales por semana). Filtra por broker y por par, permite **ocultar los
montos**, navegar por mes y año, volver a **Hoy** y **exportar el mes a CSV**. No pide nada a la
red: usa las mismas filas del historial.

## Seguridad

- La key no puede retirar fondos.
- Cada orden de apertura lleva un `externalOid` único en MEXC. En ningún broker hay reintento
  automático, así que si un envío queda en duda (timeout) hay que mirar Posiciones antes de
  reenviar.
- Mientras la ventana está abierta, workers separados actualizan precios y datos de cuenta.
  Al cerrar la app, esos workers se detienen; no queda un servicio corriendo.
- Las posiciones y los TP/SL viven en el exchange, no en tu PC.
- `trades.log` guarda cada intento (hora, resultado, `orderId`, símbolo, `vol`), nunca la key.

## Cuando algo falla (mensajes de MEXC)

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
  controller_lote.py    enviar varias tarjetas con una sola confirmación
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
tests/                  pruebas (pytest)
tools/                  utilidades: icono, chequeos contra la API y la cuenta
docs/DESIGN.md          sistema de diseño
docs/FLUJO_USUARIO.md   el recorrido real de uso, paso a paso
docs/ARQUITECTURA.md    módulos, flujo de datos y persistencia
docs/ESTADO.md          qué está probado y qué falta probar
AGENTS.md               reglas para agentes
```

Los datos (`config.json`, `operaciones.json`, `trades.log`) viven en la raíz del repo y git los
ignora. `operaciones.json` guarda localmente las operaciones para que sigan visibles cuando el
broker deje de ofrecer el historial antiguo; también se conserva un respaldo
(`operaciones.json.bak`). Estos archivos no se sincronizan entre laptops ni se incluyen al
descargar el repo. El archivo conserva lo que la app ya importó: abre la pestaña **Historial**
periódicamente para guardar las operaciones antes de que el broker las purgue, y mantén una copia
de seguridad en otro lugar.

Para llevar tu historial a otra laptop, cierra Trade Desk en la antigua y copia
`operaciones.json` y `operaciones.json.bak` a la carpeta nueva, junto a `app.py`, antes de abrir
la app por primera vez. Puedes copiar también `config.json` si quieres recuperar tus tarjetas y
preferencias; las API keys siempre se vuelven a ingresar. Conserva una copia de esos archivos en
un lugar seguro: si se pierde la carpeta del repo y no hay respaldo, se puede perder el historial
local que ya no está en el broker.

El instalador usa [uv](https://docs.astral.sh/uv/) para preparar Python y las dependencias.
Para desarrollar o correr las pruebas manualmente, instala las dependencias de desarrollo con
`uv sync --locked --extra dev`.

Verificación:

```powershell
scripts\check.bat                         # lint + formato + tests
uv run --locked python -m pytest          # solo los tests
uv run --locked python tools/smoke_api.py # red: precio, contrato, conversión de tamaño
uv run --locked python tools/smoke_live.py 9
uv run --locked python tools/check_account.py
```
