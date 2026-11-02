"""Medidas de las tablas y del deck, sin UI: las comparten vista y tests.

Los anchos y altos son los que ya estaban fijados en la app de Tkinter; aquí no
se toca ninguno (la fila de posiciones no crece).
"""

# -------------------------------------------------------------- posiciones
POS_COLS = (
    ("par", "Par", 132, "w"),
    ("lado", "Lado", 74, "w"),
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

PENCIL_GUTTER = 24
PENCIL_COLS = {"margen", "tpsl"}

HIST_COLS = (
    ("fecha", "Fecha", 142, "w"),
    ("par", "Par", 126, "w"),
    ("tipo", "Tipo", 92, "w"),
    ("qty", "Qty", 90, "e"),
    ("precio", "Precio", 112, "e"),
    ("pnl", "PnL", 118, "e"),
    ("fee", "Fee", 94, "e"),
    ("estado", "Estado", 106, "w"),
)

SIDES = {1: "LONG", 2: "CLOSE S", 3: "SHORT", 4: "CLOSE L"}
STATES = {1: "Pendiente", 2: "Sin llenar", 3: "Ejecutada", 4: "Cancelada", 5: "Invalida"}

ROW_H = 56
ACTION_W = 200

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
