# 3. Arquitectura

```
raiz/
  app.py                    lanzador del acceso directo (no tiene logica)
  src/tradedesk/            (10.629 líneas Python; conteo de referencia al 2026-11-10)
    __init__.py              inicialización del paquete                          3
    __main__.py              arranque: AppUserModelID + vista Qt                20
    paths.py                 DATA_DIR (raíz) y ASSETS (paquete)                 13
    creds.py                 Windows Credential Manager                         24
    brokers.py               nombres y títulos de los brokers                    9
    theme.py                 color, tipografía, radios, formatos               134
    layout.py                anchos/altos de las tablas (sin UI)                86
    pairs.py                 filtro puro del buscador de pares                  48
    forms.py                 parseo puro de tarjeta y editor de orden          115
    pnl.py                   neto de una operación del historial                14
    calendario.py            agregación por día del historial (puro)           343
    archivo.py               operaciones guardadas en disco (upsert)           351
    operaciones.py           empareja órdenes en operaciones (historial)       284
    session.py               pollers, cola, config y caches sin UI             658
    session_cuenta.py        consultas de cuenta por broker (posiciones/órdenes) 149
    ritmo.py                 ritmo de envío y trabajo en paralelo                36
    controller.py            fachada de casos de uso                           580
    controller_verificacion.py cotejo de estado tras errores                   223
    controller_tpsl.py       casos de uso TP/SL y Break-even                   331
    controller_ordenes.py    órdenes y margen                                  228
    controller_lote.py       enviar varias tarjetas con una confirmación       113
    mexc.py                  firma, endpoints, USDT->contratos, fee, liq       683
    bitunix.py               firma, endpoints, monedas (qty), specs            690
    bingx.py                 firma, endpoints, monedas (qty), specs            540
    bingx_comun.py           helpers y filas de BingX (tabla)                  208
    assets/                 icon.ico, icon.png, fonts/*.ttf
    qt/
      __init__.py              inicialización del paquete                        0
      __main__.py              abre la ventana                                  38
      view.py                  fachada: reexporta VistaQt                        9
      ventana.py               cabecera, deck arrastrable, pestañas, drenaje   652
      lote.py                  mixin: botón ENVIAR TODAS y resumen del lote     78
      tabla_posiciones.py      filas, resumen bruto/neto, globo de la fee      332
      tabla_ordenes.py         órdenes abiertas (panel estilo MEXC)            125
      tabla_historial.py       una fila por operación, con su neto             155
      calendario.py            mes en cuadrícula, métricas y detalle del día   617
      calendario_widgets.py    delegado del mes y curva acumulada              112
      tarjeta.py               tarjeta de par                                  491
      cierre.py                barra de cierre de la fila (slider, botones)    371
      dialogs.py               fachada: reexporta los diálogos                  43
      dialogos_base.py         Modal, confirm, show, form y claves             343
      editor_orden.py          editor de una orden abierta                     171
      tpsl.py                  editor de TP/SL con las líneas vivas             81
      be.py                    ventana de "Poner a BE"                         125
      panel_brokers.py         panel de brokers                                 60
      port.py                  UiPort de la vista Qt                            50
      formato.py               fecha y tamaño en USDT de las celdas             26
      style.py                 fuentes, widgets, QSS y logos                   270
      cells.py                 delegado, celdas con lápiz, spinner, bocadillo  340
      search.py                buscador de pares                                88
      shell.py                 ventana de prueba para medir repintado          153
  tests/                    pytest (291 tests recopilados): lógica, payloads y UI fake
  tools/                  make_icon, smoke_api, smoke_live, check_account, qt_probe, instalar.ps1
  scripts/check.bat         lint + formato + tests
  docs/DESIGN.md            sistema de diseno
  docs/FLUJO_USUARIO.md     seccion 2: el recorrido real de uso
  docs/ARQUITECTURA.md      seccion 3: este documento
  docs/API_BROKERS.md       seccion 4: firmas y endpoints de los tres brokers
  docs/UI_REGLAS.md         seccion 6: reglas de widgets, tablas y deck
  docs/BUGS_RESUELTOS.md    seccion 8: bugs que no se deben reintroducir
  docs/ESTADO.md            seccion 10: que esta probado y que falta
```

**El objetivo es mantener los módulos cerca o por debajo de ~700 líneas.**
`controller.py` y `qt/calendario.py` ya están partidos por responsabilidad y quedan bajo el tope;
los más grandes hoy son `bitunix.py` (690), `mexc.py` (683), `session.py` (658, partido en
`session.py` + `session_cuenta.py`) y `qt/ventana.py` (652, ya con el lote en `qt/lote.py`).
`bingx.py` bajó a 540 al partir las filas a `bingx_comun.py`. `qt/view.py` y `qt/dialogs.py`
quedaron como **fachadas** que reexportan: así los imports de `__main__.py`,
`tools/smoke_live.py` y de la propia vista no cambiaron. Si un archivo se acerca al tope, se
parte igual: módulo nuevo + fachada, sin tocar los call sites.

Las tres tablas (`tabla_posiciones`, `tabla_ordenes`, `tabla_historial`), la pestaña
`calendario` y el envío por lote (`lote.py`) son **mixins** de `VistaQt`: usan el estado de
la ventana y se pintan igual que antes. Al tocar una tabla, recordá que el método vive en el
mixin, no en `ventana.py`.

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
y `exchange` por tarjeta. **No** guarda tamaño, TP, SL ni DRY-RUN (ver `AGENTS.md` §7). Se escribe primero
a un archivo temporal y se reemplaza con `os.replace`; si falla, el error queda en el log y
se publica en la barra de estado.

`operaciones.json` (también ignorado) es el **archivo de operaciones**: cada operación
cerrada se guarda con una clave estable (`_clave`) y se actualiza en sitio (un parcial que
después se cierra, o una fee que se ajusta). Existe porque los exchanges purgan su
historial (~3 meses): sin esto, lo viejo desaparece de la pestaña. Antes de guardar se crea
`operaciones.json.bak` y el archivo principal se reemplaza atómicamente. Si el JSON está
corrupto, se pone en cuarentena y se intenta recuperar el respaldo; la vista recibe un aviso
explícito. Al arrancar se pinta lo guardado antes de tocar la red.
Al fusionar, la heurística antigua solo quita una fila `cierre|` si coincide de forma única
con una `fifo|` por broker, símbolo, lado, cierre (menos de 1 s), cantidad cerrada, PnL y
salida. Matches ambiguos o incompletos se conservan; por eso una posible duplicación sin
evidencia suficiente puede seguir visible. No es una identidad de orden: dos operaciones
legítimas idénticas dentro de ese intervalo aún podrían coincidir.
R1. Para la misma `_clave`, una lista nueva de `_ordenes` no vacía que sea subconjunto estricto conserva la fila archivada; igualdad sí actualiza datos como la fee.
R2. Una fila nueva con `_ordenes` no vacío que sea subconjunto estricto de otra fila archivada no se agrega.
R3. Tras fusionar, se borran las filas con `_ordenes` no vacíos que sean subconjuntos estrictos de otra fila archivada.
R4. Filas sin `_ordenes` (archivos antiguos) no participan en R1–R3; la heurística `cierre|`/`fifo|` anterior sigue vigente.
Un refresco MEXC menos completo tampoco reemplaza una fila archivada mejor.

`trades.log` registra cada intento: hora, resultado, `orderId`, símbolo, `vol`. Nunca la key.
Rota al alcanzar 1 MB y conserva hasta tres copias; los errores de escritura se notifican
en la barra de estado.

---

