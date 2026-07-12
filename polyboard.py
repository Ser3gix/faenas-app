# ============================================================
# polyboard.py — Lectura de TXT de PolyBoard y generación PDF
# ============================================================

import os
from config import POLYBOARD_ENCODING
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT


# ============================================================
# LECTURA DEL TXT
# ============================================================

def leer_txt_polyboard(ruta_txt):
    """
    Lee un archivo TXT de PolyBoard y devuelve las piezas agrupadas por material.

    Formato del TXT (separado por ;):
    cantidad ; largo ; canto_der ; canto_izq ; ancho ; canto_arr ; canto_ab ; pieza ; material

    Devuelve:
    {
      "Mel 19": [
        { "cantidad": 2, "largo": 1400, "canto_der": 1, "canto_izq": 0,
          "ancho": 580, "canto_arr": 0, "canto_ab": 0, "pieza": "Costado De" }
      ],
      "Melamina 10": [ ... ]
    }
    """
    if not os.path.exists(ruta_txt):
        raise FileNotFoundError(f"Archivo no encontrado: {ruta_txt}")

    piezas_por_material = {}

    with open(ruta_txt, encoding=POLYBOARD_ENCODING, errors="replace") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue

            partes = linea.split(";")
            if len(partes) < 9:
                continue  # Línea incompleta, ignorar

            try:
                pieza = {
                    "cantidad":   int(partes[0].strip()),
                    "largo":      int(partes[1].strip()),
                    "canto_der":  int(partes[2].strip()),
                    "canto_izq":  int(partes[3].strip()),
                    "ancho":      int(partes[4].strip()),
                    "canto_arr":  int(partes[5].strip()),
                    "canto_ab":   int(partes[6].strip()),
                    "pieza":      partes[7].strip(),
                    "material":   partes[8].strip()
                }
            except (ValueError, IndexError):
                continue  # Línea con datos inválidos, ignorar

            material = pieza["material"]
            if material not in piezas_por_material:
                piezas_por_material[material] = []
            piezas_por_material[material].append(pieza)

    return piezas_por_material


def calcular_resumen(piezas_por_material):
    """
    Calcula un resumen con el total de piezas por material.
    """
    resumen = {}
    for material, piezas in piezas_por_material.items():
        total_piezas = sum(p["cantidad"] for p in piezas)
        resumen[material] = {
            "total_piezas": total_piezas,
            "num_referencias": len(piezas)
        }
    return resumen


# ============================================================
# GENERACIÓN DEL PDF DE PEDIDO
# ============================================================

def generar_pdf_pedido(piezas_por_material, cliente_nombre, numero_faena, ruta_salida):
    """
    Genera un PDF con el despiece para entregar al almacén de tableros.

    piezas_por_material: diccionario devuelto por leer_txt_polyboard()
                         con posibles modificaciones del usuario (cantos editados)
    cliente_nombre:      nombre del cliente para la cabecera
    numero_faena:        número de la faena
    ruta_salida:         ruta donde guardar el PDF (solo si el usuario quiere)
    """
    doc = SimpleDocTemplate(
        ruta_salida,
        pagesize=A4,
        rightMargin=15*mm,
        leftMargin=15*mm,
        topMargin=15*mm,
        bottomMargin=15*mm
    )

    estilos = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle(
        "titulo",
        parent=estilos["Normal"],
        fontSize=14,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#5C3D0E"),
        spaceAfter=4
    )
    estilo_sub = ParagraphStyle(
        "sub",
        parent=estilos["Normal"],
        fontSize=9,
        fontName="Helvetica",
        textColor=colors.HexColor("#888888"),
        spaceAfter=2
    )
    estilo_material = ParagraphStyle(
        "material",
        parent=estilos["Normal"],
        fontSize=11,
        fontName="Helvetica-Bold",
        textColor=colors.white,
        spaceAfter=0
    )

    elementos = []

    # --- CABECERA ---
    elementos.append(Paragraph("PEDIDO DE TABLEROS", estilo_titulo))
    elementos.append(Paragraph(f"Faena: {numero_faena}  ·  Cliente: {cliente_nombre}", estilo_sub))
    elementos.append(Spacer(1, 6*mm))

    # Calcular ancho disponible
    ancho_total = A4[0] - 30*mm  # A4 ancho - márgenes

    # Anchos de columnas (en puntos)
    col_cant  = 25*mm
    col_largo = 30*mm
    col_cd    = 15*mm
    col_ci    = 15*mm
    col_ancho = 30*mm
    col_ca    = 15*mm
    col_cb    = 15*mm
    col_pieza = ancho_total - col_cant - col_largo - col_cd - col_ci - col_ancho - col_ca - col_cb
    anchos = [col_cant, col_largo, col_cd, col_ci, col_ancho, col_ca, col_cb, col_pieza]

    # Colores
    color_header_mat = colors.HexColor("#5C3D0E")
    color_header_col = colors.HexColor("#8B6914")
    color_canto_on   = colors.HexColor("#C8E6C9")
    color_canto_off  = colors.white
    color_fila_par   = colors.HexColor("#FAF6EE")
    color_fila_impar = colors.white

    for material, piezas in piezas_por_material.items():
        # Fila de cabecera de material
        fila_mat = [[
            Paragraph(f"📦  {material.upper()}", estilo_material),
            "", "", "", "", "", "", ""
        ]]

        tabla_mat = Table(fila_mat, colWidths=anchos)
        tabla_mat.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), color_header_mat),
            ("SPAN", (0, 0), (-1, 0)),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        elementos.append(tabla_mat)

        # Cabecera de columnas
        cab = [["Cant.", "Largo", "CD", "CI", "Ancho", "CA", "CB", "Pieza"]]
        tabla_cab = Table(cab, colWidths=anchos)
        tabla_cab.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), color_header_col),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("ALIGN", (7, 0), (7, -1), "LEFT"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (7, 0), (7, -1), 6),
        ]))
        elementos.append(tabla_cab)

        # Filas de piezas
        filas = []
        estilos_celdas = []

        for i, p in enumerate(piezas):
            fila = [
                str(p["cantidad"]),
                str(p["largo"]),
                "✔" if p["canto_der"] else "",
                "✔" if p["canto_izq"] else "",
                str(p["ancho"]),
                "✔" if p["canto_arr"] else "",
                "✔" if p["canto_ab"]  else "",
                p["pieza"]
            ]
            filas.append(fila)

            # Color de fila
            bg = color_fila_par if i % 2 == 0 else color_fila_impar
            estilos_celdas.append(("BACKGROUND", (0, i), (-1, i), bg))

            # Color de celdas de canto activo
            for col_idx, campo in enumerate(["canto_der", "canto_izq", None, "canto_arr", "canto_ab"]):
                # Mapear índices: 2=CD, 3=CI, 5=CA, 6=CB
                mapa = {2: "canto_der", 3: "canto_izq", 5: "canto_arr", 6: "canto_ab"}
                for ci, campo_c in mapa.items():
                    if p[campo_c]:
                        estilos_celdas.append(("BACKGROUND", (ci, i), (ci, i), color_canto_on))
                        estilos_celdas.append(("TEXTCOLOR", (ci, i), (ci, i), colors.HexColor("#2E7D32")))
                        estilos_celdas.append(("FONTNAME", (ci, i), (ci, i), "Helvetica-Bold"))
                break  # Solo aplicar una vez por fila

        # Corregir el loop de colores de canto (simplificado)
        filas_data = []
        estilos_celdas = []
        for i, p in enumerate(piezas):
            fila = [
                str(p["cantidad"]),
                str(p["largo"]),
                "✔" if p["canto_der"] else "–",
                "✔" if p["canto_izq"] else "–",
                str(p["ancho"]),
                "✔" if p["canto_arr"] else "–",
                "✔" if p["canto_ab"]  else "–",
                p["pieza"]
            ]
            filas_data.append(fila)

            bg = color_fila_par if i % 2 == 0 else color_fila_impar
            estilos_celdas.append(("BACKGROUND", (0, i), (-1, i), bg))

            for ci, campo_c in {2: "canto_der", 3: "canto_izq", 5: "canto_arr", 6: "canto_ab"}.items():
                if p[campo_c]:
                    estilos_celdas.append(("BACKGROUND", (ci, i), (ci, i), color_canto_on))
                    estilos_celdas.append(("TEXTCOLOR",  (ci, i), (ci, i), colors.HexColor("#2E7D32")))
                    estilos_celdas.append(("FONTNAME",   (ci, i), (ci, i), "Helvetica-Bold"))

        tabla_piezas = Table(filas_data, colWidths=anchos)
        tabla_piezas.setStyle(TableStyle([
            ("FONTSIZE",      (0, 0), (-1, -1), 8),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("ALIGN",         (7, 0), (7, -1),  "LEFT"),
            ("LEFTPADDING",   (7, 0), (7, -1),  6),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#CCCCCC")),
            *estilos_celdas
        ]))
        elementos.append(tabla_piezas)
        elementos.append(Spacer(1, 5*mm))

    doc.build(elementos)
    return ruta_salida
