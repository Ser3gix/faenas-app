# ============================================================
# polyboard.py — Lectura de TXT/PDF de PolyBoard y generación PDF
# ============================================================

import os
import re
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

_RE_ESPESOR = re.compile(
    r"(?:^|[^\d])(?:x|×|\bespesor\s*)?(\d{1,2})\s*(?:mm)?(?:\s*$|,|\s)",
    re.I,
)
_RE_ESPESOR_FIN = re.compile(r"(?:^|[^\d])(\d{1,2})\s*$")
_RE_ESPESOR_X = re.compile(r"[x×]\s*(\d{1,2})\s*(?:mm)?\b", re.I)


def espesor_de_material(nombre):
    """Extrae espesor en mm del nombre PolyBoard/almacén (19, 10, 18…)."""
    t = str(nombre or "").strip()
    if not t:
        return None
    # "PINO 19, 19" / "Melamina 10, 10"
    m = re.search(r",\s*(\d{1,2})\s*$", t)
    if m:
        return int(m.group(1))
    m = _RE_ESPESOR_X.search(t)
    if m:
        return int(m.group(1))
    # "Mel 19", "PINO 19"
    m = re.search(r"\b(\d{1,2})\b", t)
    if m:
        v = int(m.group(1))
        if 3 <= v <= 40:
            return v
    return None


def clave_espesor(mm):
    if mm is None:
        return ""
    return f"{int(mm)} mm"


def agrupar_por_espesor(piezas_por_material):
    """
    Reagrupa piezas por espesor (ignora nombre comercial).
    Clave: \"19 mm\", \"10 mm\". Omite Separacion / espesor 0.
    """
    out = {}
    for material, piezas in (piezas_por_material or {}).items():
        mat = str(material or "").strip()
        if not mat:
            continue
        low = mat.lower()
        if "separac" in low:
            continue
        esp = espesor_de_material(mat)
        if not esp:
            continue
        clave = clave_espesor(esp)
        bucket = out.setdefault(clave, [])
        for p in piezas or []:
            item = dict(p)
            item["material"] = clave
            item["material_origen"] = mat
            item["espesor"] = esp
            bucket.append(item)
    return out


def _parsear_lineas_polyboard(lineas):
    """Parsea líneas TXT PolyBoard → piezas agrupadas por material."""
    piezas_por_material = {}
    for linea in lineas:
        linea = (linea or "").strip()
        if not linea:
            continue
        partes = linea.split(";")
        if len(partes) < 9:
            continue
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
            continue
        material = pieza["material"]
        if material not in piezas_por_material:
            piezas_por_material[material] = []
        piezas_por_material[material].append(pieza)
    return piezas_por_material


def leer_contenido_polyboard(texto):
    """
    Lee el contenido (texto) de un TXT PolyBoard y agrupa piezas por material.
    Misma forma de salida que leer_txt_polyboard.
    """
    if texto is None:
        raise ValueError("Contenido vacío")
    if isinstance(texto, bytes):
        texto = texto.decode(POLYBOARD_ENCODING, errors="replace")
    return _parsear_lineas_polyboard(str(texto).splitlines())


def leer_txt_polyboard(ruta_txt):
    """
    Lee un archivo TXT de PolyBoard y devuelve las piezas agrupadas por material.

    Formato del TXT (separado por ;):
    cantidad ; largo ; canto_der ; canto_izq ; ancho ; canto_arr ; canto_ab ; pieza ; material
    """
    if not os.path.exists(ruta_txt):
        raise FileNotFoundError(f"Archivo no encontrado: {ruta_txt}")

    with open(ruta_txt, encoding=POLYBOARD_ENCODING, errors="replace") as f:
        return _parsear_lineas_polyboard(f)


def _lineas_words_pagina(page):
    """Agrupa palabras de PyMuPDF por Y aproximada → texto de línea + palabras."""
    words = page.get_text("words") or []
    lineas = {}
    for w in words:
        y = round(float(w[1]) / 2.0) * 2
        lineas.setdefault(y, []).append((float(w[0]), str(w[4])))
    out = []
    for y in sorted(lineas):
        items = sorted(lineas[y], key=lambda t: t[0])
        txt = " ".join(t for _, t in items)
        out.append((y, txt, items))
    return out


_RE_FILA_PANEL = re.compile(
    r"^(.+?),\s*(\d+)\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(S[ií]|No)\b(.*)$",
    re.I,
)


def _cantos_desde_cola(cola):
    """Cuenta menciones Textil/Canto en la cola y las reparte CI, CD, CA, CB."""
    cola = (cola or "").strip()
    if not cola:
        return 0, 0, 0, 0
    # Cada aparición de un canto tipográfico
    n = len(re.findall(r"textil|canto|pvc|cancun", cola, re.I))
    flags = [1 if i < n else 0 for i in range(4)]
    # Orden cabecera PDF: Izquier, Derecho, Inferior, Superior → izq, der, ab, arr
    return flags[1], flags[0], flags[3], flags[2]  # der, izq, arr, ab


def _parsear_herrajes_lineas(lineas_txt):
    herrajes = []
    en_herrajes = False
    vistos = set()
    for raw in lineas_txt:
        t = (raw or "").strip()
        if not t:
            continue
        low = t.lower()
        if low.startswith("herrajes"):
            en_herrajes = True
            continue
        if not en_herrajes:
            continue
        if low.startswith("total"):
            en_herrajes = False
            continue
        # Fuera del bloque resumen (fichas de pieza, etc.)
        if (
            "altura:" in low
            or "espesor:" in low
            or "taladro" in low
            or "cremallera" in low
            or low.startswith("polyboard")
            or low.startswith("página")
            or low.startswith("pagina")
            or low.startswith("lista de")
            or low.startswith("panel")
            or low.startswith("perfil")
            or low.startswith("canto ")
        ):
            en_herrajes = False
            continue
        m = re.match(
            r"^(.+?)\s+(\d+)\s+([\d]+(?:[.,][\d]+)?)\s+([\d]+(?:[.,][\d]+)?)\s*€?\s*$",
            t,
        )
        if not m:
            continue
        nombre = m.group(1).strip()
        cant = int(m.group(2))
        low_n = nombre.lower()
        if low_n in ("cantidad", "precio unitario", "precio", "cara") or len(nombre) < 2:
            continue
        if re.fullmatch(r"[\d.,\s]+", nombre):
            continue
        clave = (low_n, cant)
        if clave in vistos:
            continue
        vistos.add(clave)
        herrajes.append({"nombre": nombre, "cantidad": cant, "unidad": "ud"})
    return herrajes


def leer_pdf_resumen_polyboard(bruto):
    """
    Lee un PDF de resumen PolyBoard (Lista de Corte + Herrajes).
    Devuelve {piezas: {material: [...]}, herrajes: [...], por_espesor: {...}}.
    """
    try:
        import fitz
    except Exception as exc:
        raise RuntimeError("Falta PyMuPDF (fitz) para leer el PDF") from exc

    if not bruto:
        raise ValueError("PDF vacío")
    doc = fitz.open(stream=bruto, filetype="pdf")
    piezas_por_material = {}
    todas_lineas = []
    # Solo páginas de listados/resumen (evita 50+ fichas de pieza)
    max_paginas = min(doc.page_count, 8)
    for page in list(doc)[:max_paginas]:
        for _y, txt, _items in _lineas_words_pagina(page):
            todas_lineas.append(txt)
            m = _RE_FILA_PANEL.match(txt.strip())
            if not m:
                continue
            mat_base = m.group(1).strip()
            esp = int(m.group(2))
            ref = m.group(3).strip()
            if ref.lower() in ("referencia", "material"):
                continue
            try:
                largo = int(m.group(4))
                ancho = int(m.group(5))
                cantidad = int(m.group(6))
            except ValueError:
                continue
            fibra_si = m.group(7).lower().startswith("s")
            cola = m.group(8) or ""
            if not fibra_si and "separac" in mat_base.lower():
                continue
            cd, ci, ca, cb = _cantos_desde_cola(cola)
            material = f"{mat_base}, {esp}" if "," not in mat_base else mat_base
            if not material.lower().endswith(str(esp)) and f", {esp}" not in material:
                material = f"{mat_base}, {esp}"
            pieza = {
                "cantidad": cantidad,
                "largo": largo,
                "canto_der": cd,
                "canto_izq": ci,
                "ancho": ancho,
                "canto_arr": ca,
                "canto_ab": cb,
                "pieza": ref,
                "material": material,
                "espesor": esp,
            }
            piezas_por_material.setdefault(material, []).append(pieza)

    # Si no hubo Lista de Corte en las primeras páginas, barrer el resto solo buscando filas panel
    if not piezas_por_material and doc.page_count > max_paginas:
        for page in list(doc)[max_paginas:]:
            for _y, txt, _items in _lineas_words_pagina(page):
                m = _RE_FILA_PANEL.match(txt.strip())
                if not m:
                    continue
                mat_base = m.group(1).strip()
                esp = int(m.group(2))
                ref = m.group(3).strip()
                try:
                    largo = int(m.group(4))
                    ancho = int(m.group(5))
                    cantidad = int(m.group(6))
                except ValueError:
                    continue
                cola = m.group(8) or ""
                cd, ci, ca, cb = _cantos_desde_cola(cola)
                material = f"{mat_base}, {esp}"
                pieza = {
                    "cantidad": cantidad, "largo": largo, "canto_der": cd, "canto_izq": ci,
                    "ancho": ancho, "canto_arr": ca, "canto_ab": cb, "pieza": ref,
                    "material": material, "espesor": esp,
                }
                piezas_por_material.setdefault(material, []).append(pieza)

    herrajes = _parsear_herrajes_lineas(todas_lineas)
    por_espesor = agrupar_por_espesor(piezas_por_material)
    return {
        "piezas": piezas_por_material,
        "piezas_por_espesor": por_espesor,
        "herrajes": herrajes,
    }


def procesar_archivo_polyboard(nombre, bruto):
    """
    TXT o PDF → piezas agrupadas por espesor + herrajes.
    """
    nombre = (nombre or "").lower()
    herrajes = []
    if nombre.endswith(".pdf") or (bruto[:5] == b"%PDF-"):
        data = leer_pdf_resumen_polyboard(bruto)
        return {
            "piezas": data["piezas_por_espesor"] or agrupar_por_espesor(data["piezas"]),
            "piezas_origen": data["piezas"],
            "herrajes": data.get("herrajes") or [],
            "agrupado_por": "espesor",
        }
    piezas = leer_contenido_polyboard(bruto)
    return {
        "piezas": agrupar_por_espesor(piezas),
        "piezas_origen": piezas,
        "herrajes": herrajes,
        "agrupado_por": "espesor",
    }


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
