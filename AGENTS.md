# AGENTS.md

Documento de traspaso para quien retome **Trade Desk**. Esto es el punto de entrada: acá viven
las reglas, los comandos y la matriz de tests; el resto está partido por tema.

| Documento | Qué tiene | Cuándo leerlo |
|---|---|---|
| `docs/FLUJO_USUARIO.md` | el recorrido real, paso a paso | tocás UI o dudas de comportamiento |
| `docs/ARQUITECTURA.md` | árbol de módulos, flujo de datos y persistencia | tocás código |
| `docs/API_BROKERS.md` | firmas, endpoints y trampas de los tres brokers | tocás un cliente |
| `docs/UI_REGLAS.md` | widgets, hilos, avisos, tablas y deck | tocás `qt/` |
| `docs/ESTADO.md` | qué está verificado y qué falta probar | dudas de alcance |
| `docs/DESIGN.md` | tokens, tipografía y componentes | tocás color o estilo |

Si algo aquí no coincide con el código, el código manda: corrige el documento en el mismo
cambio.

---

## 0. Cómo empezar a trabajar aquí

**Dónde está cada cosa.** El código vive en `src/tradedesk/` (layout `src`), los tests en
`tests/`, los assets **dentro del paquete** (`src/tradedesk/assets/`), los scripts sueltos en
`tools/` y los datos del usuario (`config.json`, `operaciones.json`, `trades.log`) en la raíz
del repo, nunca dentro del paquete: esas rutas las resuelve `tradedesk/paths.py`.

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

**El estado del código vive en `docs/ESTADO.md`.** Ahí están qué está verificado con dinero
real y qué falta probar. Se actualiza al cerrar cada paso; este documento (AGENTS) describe
cómo está el código **hoy**, no cómo debería estar.

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
  si acaso": cuesta ~35 s y gasta cuota del usuario sin aportar nada si el cambio fue de un
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
El recorrido completo, paso a paso, tal como lo usa el usuario.
Vive en [`docs/FLUJO_USUARIO.md`](docs/FLUJO_USUARIO.md).

## 3. Arquitectura
Árbol de módulos con conteos, flujo de datos por la cola y persistencia.
Vive en [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md).

## 4. MEXC Futures API - lo que hay que saber
Firmas, endpoints, unidades, rate limits y trampas de MEXC, Bitunix y BingX.
Vive en [`docs/API_BROKERS.md`](docs/API_BROKERS.md): leelo antes de tocar un cliente.

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

## 6. Reglas de UI
Reglas de widgets, hilos, avisos, tablas, tarjetas y deck en
[`docs/UI_REGLAS.md`](docs/UI_REGLAS.md); tokens y componentes en
[`docs/DESIGN.md`](docs/DESIGN.md).

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
Los 16 bugs que no se deben reintroducir, con su causa y su test.
Vive en [`docs/BUGS_RESUELTOS.md`](docs/BUGS_RESUELTOS.md).

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
| `mexc.py` (payload, `vol`, precio, fee) | `uv run --locked python -m pytest tests/test_mexc_orders.py tests/test_mexc_pure.py tests/test_visibilidad_historial.py` |
| `controller.py` (hilos, cola, cierre, TP/SL, órdenes) | `uv run --locked python -m pytest tests/test_no_threaded_widgets.py tests/test_actions_close.py tests/test_actions_tpsl.py tests/test_actions_ordenes.py tests/test_mexc_orders.py tests/test_lote.py` |
| `controller_lote.py`, `qt/lote.py` (envío por lote) | `uv run --locked python -m pytest tests/test_lote.py tests/test_deck_cartas.py` |
| `session.py` (pollers, config, catálogo, logs) | `uv run --locked python -m pytest tests/test_session_polling.py tests/test_paths.py tests/test_respaldos_y_config.py tests/test_visibilidad_historial.py` |
| `archivo.py` (historial local y respaldos) | `uv run --locked python -m pytest tests/test_archivo.py tests/test_respaldos_y_config.py` |
| `bitunix.py` (modo de cuenta y payloads) | `uv run --locked python -m pytest tests/test_bitunix_orders.py` |
| `bingx.py` (fees y payloads) | `uv run --locked python -m pytest tests/test_bingx_orders.py tests/test_visibilidad_historial.py` |
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
Qué está verificado con dinero real, qué falta probar y qué quedó descartado.
Vive en [`docs/ESTADO.md`](docs/ESTADO.md).

## 11. Glosario

- **Nocional**: `margen × apalancamiento`. Es el valor de la posición, no lo que arriesgas.
- **Contrato**: unidad de MEXC. `vol` cuenta contratos, no monedas.
- **DRY-RUN**: simula la orden y no envía nada.
- **Reverse**: cierra la posición y abre la contraria con el mismo tamaño.
- **Isolated / Cross**: margen aislado (solo esa posición) o cruzado (toda la cuenta).
