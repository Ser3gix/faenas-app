# ============================================================
# polyboard_optimizar.py — Optimización de corte, canto y costes
# ============================================================
# Entrada: piezas de leer_txt_polyboard() (por material).
# ============================================================

from __future__ import annotations

import base64
import io
from typing import Any, Dict, List, Optional

try:
    import rectpack
except Exception:  # pragma: no cover
    rectpack = None

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
except Exception:  # pragma: no cover
    plt = None
    patches = None


def _to_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _to_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _metros_canto_pieza(p: dict) -> float:
    """Suma solo los lados con canto activo × longitud de ese lado (mm → m)."""
    largo = _to_float(p.get("largo"))
    ancho = _to_float(p.get("ancho"))
    ml = 0.0
    if _to_int(p.get("canto_der")):
        ml += ancho
    if _to_int(p.get("canto_izq")):
        ml += ancho
    if _to_int(p.get("canto_arr")):
        ml += largo
    if _to_int(p.get("canto_ab")):
        ml += largo
    return ml / 1000.0


def _esquema_png_b64(ancho_util, alto_util, rects, mapping, espesor_sierra, titulo):
    if plt is None or patches is None:
        return None
    fig, ax = plt.subplots(figsize=(9, 5))
    tablero_rect = patches.Rectangle(
        (0, 0), ancho_util, alto_util,
        linewidth=2, edgecolor="black", facecolor="#f7f9fa",
    )
    ax.add_patch(tablero_rect)
    for rect in rects:
        _, x, y, w, h, rid = rect
        info = mapping.get(rid, {})
        w_real = max(10, w - espesor_sierra)
        h_real = max(10, h - espesor_sierra)
        p_rect = patches.Rectangle(
            (x, y), w_real, h_real,
            linewidth=1, edgecolor="#1f77b4", facecolor="#aec7e8", alpha=0.8,
        )
        ax.add_patch(p_rect)
        ax.text(
            x + w_real / 2, y + h_real / 2,
            f"{info.get('nombre', 'P')}\n{int(info.get('ancho', w_real))}x{int(info.get('alto', h_real))}",
            color="black", fontsize=8, ha="center", va="center", weight="bold",
        )
    ax.set_xlim(-60, ancho_util + 60)
    ax.set_ylim(-60, alto_util + 60)
    ax.set_aspect("equal")
    ax.set_title(titulo)
    ax.set_xlabel("Ancho (mm)")
    ax.set_ylabel("Alto (mm)")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=110)
    plt.close(fig)
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode("ascii")


def optimizar_despiece(
    piezas_por_material: Dict[str, List[dict]],
    opciones: Optional[dict] = None,
) -> dict:
    """
    Optimiza corte y calcula costes por material.

    opciones:
      margen_borde, espesor_sierra, permitir_rotacion, stock_tableros,
      precio_corte_ml, precio_cantear_ml, precio_material_canto_ml,
      tableros: { material: { ancho, alto, precio_m2 } },
      excluir_materiales: [str],
      generar_esquemas: bool
    """
    if rectpack is None:
        raise RuntimeError("Falta la dependencia rectpack. Instala requirements.txt.")

    opc = opciones or {}
    margen_borde = _to_float(opc.get("margen_borde"), 10)
    espesor_sierra = _to_float(opc.get("espesor_sierra"), 4)
    permitir_rotacion = bool(opc.get("permitir_rotacion", False))
    stock_tableros = max(1, _to_int(opc.get("stock_tableros"), 50))
    precio_corte_ml = _to_float(opc.get("precio_corte_ml"), 0.50)
    precio_cantear_ml = _to_float(opc.get("precio_cantear_ml"), 0.75)
    precio_material_canto_ml = _to_float(opc.get("precio_material_canto_ml"), 0.40)
    cfg_tableros = opc.get("tableros") or {}
    excluir = {str(x).strip().lower() for x in (opc.get("excluir_materiales") or []) if str(x).strip()}
    generar_esquemas = bool(opc.get("generar_esquemas", True))

    materiales: Dict[str, Any] = {}
    coste_total = 0.0

    for material, piezas in (piezas_por_material or {}).items():
        mat_key = str(material or "").strip()
        if not mat_key:
            continue
        if mat_key.lower() in excluir or any(e and e in mat_key.lower() for e in excluir):
            continue

        cfg = cfg_tableros.get(mat_key) or cfg_tableros.get(material) or {}
        ancho_tab = _to_float(cfg.get("ancho"), 2440)
        alto_tab = _to_float(cfg.get("alto"), 1220)
        precio_m2 = _to_float(cfg.get("precio_m2"), 18.0)

        ancho_util = ancho_tab - (2 * margen_borde)
        alto_util = alto_tab - (2 * margen_borde)
        if ancho_util <= 0 or alto_util <= 0:
            materiales[mat_key] = {
                "error": "El margen de refilado supera las dimensiones del tablero.",
                "ancho_tablero": ancho_tab,
                "alto_tablero": alto_tab,
            }
            continue

        packer = rectpack.newPacker(rotation=permitir_rotacion)
        for _ in range(stock_tableros):
            packer.add_bin(ancho_util, alto_util)

        id_contador = 0
        total_piezas_ind = 0
        mapping_rects = {}
        metros_canto_total = 0.0

        for item in piezas or []:
            # En PolyBoard: largo × ancho. En empaquetado usamos ancho_p=largo, alto_p=ancho
            # (misma convención práctica que la app Streamlit: alto↔ancho intercambiados).
            largo_p = _to_float(item.get("largo"))
            ancho_p = _to_float(item.get("ancho"))
            cantidad = max(0, _to_int(item.get("cantidad"), 1))
            if largo_p <= 0 or ancho_p <= 0 or cantidad <= 0:
                continue
            ml_canto_una = _metros_canto_pieza(item)
            for _ in range(cantidad):
                packer.add_rect(
                    largo_p + espesor_sierra,
                    ancho_p + espesor_sierra,
                    id_contador,
                )
                mapping_rects[id_contador] = {
                    "nombre": item.get("pieza") or "Pieza",
                    "ancho": largo_p,
                    "alto": ancho_p,
                    "ml_canto": ml_canto_una,
                }
                metros_canto_total += ml_canto_una
                id_contador += 1
                total_piezas_ind += 1

        packer.pack()
        rects_colocados = packer.rect_list()
        piezas_colocadas = len(rects_colocados)
        bins_usados = sorted({r[0] for r in rects_colocados}) if rects_colocados else []
        tableros_usados = len(bins_usados)

        # Solo canto de piezas realmente colocadas
        metros_canto_colocado = 0.0
        for rect in rects_colocados:
            rid = rect[5]
            metros_canto_colocado += _to_float(mapping_rects.get(rid, {}).get("ml_canto"))

        area_un_tablero_m2 = (ancho_tab * alto_tab) / 1_000_000.0
        coste_tableros = tableros_usados * area_un_tablero_m2 * precio_m2
        coste_material_canto = metros_canto_colocado * precio_material_canto_ml
        coste_servicio_cantear = metros_canto_colocado * precio_cantear_ml
        metros_corte = sum((r[2] + r[3]) for r in rects_colocados) / 1000.0
        coste_corte = metros_corte * precio_corte_ml
        subtotal = coste_tableros + coste_material_canto + coste_servicio_cantear + coste_corte
        coste_total += subtotal

        esquemas = []
        if generar_esquemas and tableros_usados:
            bins_dict = {}
            for rect in rects_colocados:
                bins_dict.setdefault(rect[0], []).append(rect)
            for i, b_idx in enumerate(bins_usados):
                png = _esquema_png_b64(
                    ancho_util, alto_util,
                    bins_dict.get(b_idx, []),
                    mapping_rects,
                    espesor_sierra,
                    f"Tablero #{i + 1} de {mat_key} ({int(ancho_util)} x {int(alto_util)} mm útiles)",
                )
                if png:
                    esquemas.append({"tablero": i + 1, "png": png})

        materiales[mat_key] = {
            "tableros_usados": tableros_usados,
            "area_bruta_m2": round(area_un_tablero_m2 * tableros_usados, 3),
            "piezas_colocadas": piezas_colocadas,
            "piezas_totales": total_piezas_ind,
            "metros_canto": round(metros_canto_colocado, 3),
            "metros_corte": round(metros_corte, 3),
            "coste_tableros": round(coste_tableros, 2),
            "coste_material_canto": round(coste_material_canto, 2),
            "coste_servicio_cantear": round(coste_servicio_cantear, 2),
            "coste_corte": round(coste_corte, 2),
            "subtotal": round(subtotal, 2),
            "ancho_tablero": ancho_tab,
            "alto_tablero": alto_tab,
            "precio_m2": precio_m2,
            "ancho_util": ancho_util,
            "alto_util": alto_util,
            "aviso_stock": piezas_colocadas < total_piezas_ind,
            "esquemas": esquemas,
        }

    return {
        "materiales": materiales,
        "coste_total": round(coste_total, 2),
        "opciones": {
            "margen_borde": margen_borde,
            "espesor_sierra": espesor_sierra,
            "permitir_rotacion": permitir_rotacion,
            "stock_tableros": stock_tableros,
            "precio_corte_ml": precio_corte_ml,
            "precio_cantear_ml": precio_cantear_ml,
            "precio_material_canto_ml": precio_material_canto_ml,
        },
    }
