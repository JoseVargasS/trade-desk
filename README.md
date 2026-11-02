# Trade Desk

Ventana local para operar futuros de MEXC **a mercado o a límite**. Sin navegador, sin servidor, sin puertos abiertos.

## Arrancar

Doble clic en **`trade-desk`** (el acceso directo del escritorio) o en `Iniciar.bat`.

Si no abre nada, usa `Iniciar-con-consola.bat` para ver el error.

## Primera vez

La app pide tu API key y secret y los verifica contra MEXC antes de guardarlos.
Quedan en el **Administrador de credenciales de Windows**, no en archivos.

Crear la key en MEXC → perfil → API Management:

- Permisos: futuros/trading ✅ y lectura ✅
- **Withdraw ❌** y transfer ❌ (no negociable)
- API Usage: **Open API**
- Link IP Address: **agrega tu IP** (sin IP la key dura 90 días)

La app muestra tu IP arriba a la derecha, con botón para copiarla.

## Uso

- **Tarjetas en fila.** Cada tarjeta es un par con su propio apalancamiento, margen,
  tamaño, TP/SL. La app arranca **sin tarjetas**: **`+ Añadir par`** agrega la primera a la
  izquierda y las siguientes a su derecha. Clic en el nombre del par de una tarjeta lo cambia.
  El nombre se muestra como en MEXC (`GOLD(XAU)USDT`, no `XAU_USDT`).
- **Apalancamiento**: escribes el valor o usas los presets `1 / 5 / 10 / 15 / 20 / 50`.
- **Margen**: `Aislado` por defecto, `Cruzado` si lo cambias.
- **Tamaño** + toggle `Margen` / `Nocional`:
  - `Margen` 100 a 10x → 1,000 USDT nocionales
  - `Nocional` 1,000 → 1,000 USDT nocionales
- **Abrir a mercado o a límite**: el chip `Mercado ▾` al lado de *Tamaño* abre un panel con
  `Mercado | Límite` y el precio (viene con el último). Si no lo tocas, la orden sale a
  mercado; si eliges límite, puede quedar sin llenar y queda como orden pendiente.
- **TP / SL**: opcionales. Vacíos = entra sin ellos. Ojo: MEXC mide la dirección contra el
  **precio actual**, no contra la entrada. Un SL puesto del lado de la ganancia (por encima
  del precio en un LONG) no es un stop loss para MEXC: la app lo guarda como **TP** y te avisa.
- **Resumen** en cada tarjeta: contratos, nocional real, fee estimada y liquidación
  estimada (long / short, solo en margen aislado).
- **DRY-RUN** viene **activado**: no abre ni cierra posiciones. El **TP/SL** y el
  **margen** sí funcionan, porque son gestión de riesgo.
  El indicador de abajo dice `DRY-RUN ACTIVO` o `REAL` en rojo.
- **Buscar par**: `+ Añadir par` abre una ventana flotante. Escribes, `Enter` toma el
  primer resultado (los pares USDT van primero), `Esc` cierra.

## Posiciones e historial

**Pestaña Posiciones**

| Acción | Cómo |
|---|---|
| Cerrar una | botón **Cerrar LONG / SHORT** al final de la fila (toma el color del PnL) |
| Cerrar una parte | campo `%` de la fila: abre el slider con `Cerrable / Cierras / Mínimo` |
| Cerrar a precio límite | campo `Mercado` de la fila: elige `Límite` y escribe el precio |
| Cerrar varias | marca los checkboxes → **Cerrar seleccionadas (N)** |
| Reverse | botón **Reverse** en la fila (endpoint nativo de MEXC) |
| Cerrar todo | botón **CERRAR TODO** con confirmación |

Sin tocar los dos campos, el botón cierra **a mercado y al 100 %**. El checkbox del encabezado
marca/desmarca todas. La tabla se refresca cada 3 s y mantiene tu selección. PnL y fee van con
color (verde ganancia, rojo pérdida/costo), con su importe en USDT, el % que representan del
margen y del nocional, y el **ahorro de fees** cuando MEXC lo reporta (`lowSaveTotalFee`).

**Pestaña Historial**

Las últimas 50 órdenes (ejecutadas, canceladas, pendientes) con fecha, par, tipo,
cantidad, precio, PnL, fee y estado. Se refresca cada 15 s mientras esté abierta.

## Seguridad

- La key no puede retirar fondos.
- Cada orden lleva un `externalOid` único: un reintento no abre una segunda posición.
- Nada corre en segundo plano. Cierras la ventana y no queda nada vivo.
- Las posiciones y los TP/SL viven en MEXC, no en tu PC.
- `trades.log` guarda cada intento (hora, resultado, `orderId`), nunca la key.

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
  controller.py         abrir, cerrar, reverse, TP/SL, margen y órdenes
  forms.py              parseo de tarjetas y del editor de orden
  layout.py             anchos y altos de las tablas
  pairs.py              filtro del buscador de pares
  theme.py              tokens de color, fuente y formatos
  mexc.py               firma HMAC, endpoints, USDT → contratos, fee, liquidación
  creds.py              Windows Credential Manager
  paths.py              dónde viven los datos y los assets
  qt/                   ventana, diálogos, estilos y buscador (PySide6)
  assets/               iconos y fuentes Geist
tests/                  pruebas (pytest)
tools/                  utilidades: icono, chequeos contra la API y la cuenta
docs/DESIGN.md          sistema de diseño
AGENTS.md               reglas para agentes
```

Los datos (`config.json`, `trades.log`) viven en la raíz del repo y git los ignora.

Requiere Python 3.11+: `pip install -e ".[dev]"` (o `pip install PySide6-Essentials httpx keyring`).

Verificación:

```powershell
scripts\check.bat             # lint + formato + tests
python -m pytest              # solo los tests
python tools/smoke_api.py     # red: precio, contrato, conversión de tamaño
python tools/smoke_live.py 9  # abre la app 9 s con la cuenta real y la cierra
python tools/check_account.py # consulta la cuenta: saldo, posiciones, historial
```
