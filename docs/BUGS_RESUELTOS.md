# 8. Bugs ya resueltos (no reintroducirlos)

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
los avisos se encolan fuera del drain (`docs/UI_REGLAS.md` §6).

---

