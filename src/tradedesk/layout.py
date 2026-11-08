"""Medidas de las tablas y del deck, sin UI: las comparten vista y tests.

Los anchos y altos son los que ya estaban fijados en la app de Tkinter; aquí no
se toca ninguno (la fila de posiciones no crece).
"""

# -------------------------------------------------------------- posiciones
POS_COLS = (
    ("par", "Par", 132, "w"),
    # 96 px: "100X SHORT" mide 81 px y el delegado deja 6 de cada lado; con 74
    # se cortaba en "10X SHOR"
    ("lado", "Lado", 96, "w"),
    ("apertura", "Apertura", 84, "w"),
    ("pos", "Posición", 112, "e"),
    ("entrada", "Entrada", 94, "e"),
    ("mark", "Mark price", 94, "e"),
    ("liq", "Liquidación", 100, "e"),
    ("ratio", "Margin ratio", 98, "e"),
    ("margen", "Margen", 132, "e"),
    ("pnl", "PnL", 122, "e"),
    ("fee", "Fee · %mrg / pos", 140, "e"),
    ("tpsl", "TP / SL", 188, "e"),
)

PENCIL_COLS = {"margen", "tpsl"}

# Historial agrupado: una fila por operación (apertura + cierres juntos)
OPER_COLS = (
    ("apertura", "Apertura", 142, "w"),
    ("cierre", "Cierre", 142, "w"),
    ("par", "Par", 132, "w"),
    ("lado", "Lado", 74, "w"),
    ("qty", "Tamaño (USDT)", 128, "e"),
    ("entrada", "Entrada", 110, "e"),
    ("salida", "Salida", 110, "e"),
    ("pnl", "PnL", 118, "e"),
    ("fee", "Fee", 104, "e"),
    ("neto", "Neto", 118, "e"),
    ("estado", "Estado", 106, "w"),
)

STATES = {1: "Pendiente", 2: "Sin llenar", 3: "Ejecutada", 4: "Cancelada", 5: "Invalida"}

# Detalle de un día en la pestaña Calendario
CAL_COLS = (
    ("par", "Par", 160, "w"),
    ("lado", "Lado", 74, "w"),
    ("entrada", "Entrada", 110, "e"),
    ("salida", "Salida", 110, "e"),
    ("pnl", "PnL", 118, "e"),
    ("fee", "Fee", 104, "e"),
    ("neto", "Neto", 118, "e"),
    ("hora", "Hora", 90, "w"),
)

ROW_H = 56
ACTION_W = 200

# Pestaña Calendario: medidas de las celdas y ancho del panel de métricas
CAL_ALTO_DIA = 48
CAL_ANCHO_DIA = 88
CAL_PANEL_W = 350
CAL_ALTO_CABECERA = 26

# ------------------------------------------------------------------ ordenes
ORDER_COLS = (
    ("par", "Par", 180, "w"),
    ("fecha", "Fecha", 148, "w"),
    ("dir", "Dirección", 108, "w"),
    ("apal", "Apal.", 84, "w"),
    ("monto", "Monto", 130, "e"),
    ("precio", "Precio", 130, "e"),
    ("llenado", "Llenado", 96, "e"),
    ("margen", "Margen usado", 124, "e"),
    ("stops", "TP / SL", 190, "e"),
    ("fee", "Fee (USDT)", 92, "e"),
    ("estado", "Estado", 96, "w"),
)

ORDER_PENCILS = {"monto", "precio", "stops"}
ORDER_ACTION_W = 190
ORDER_ROW_H = 54
