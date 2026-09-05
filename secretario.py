# secretario.py — Jimmi: consulta, memoria en TiDB y propuestas
MAX_RESUMEN = 8000

from database import get_connection, fila_a_dict, filas_a_lista


def leer_contexto():
    conn = get_connection()
    try:
        fila = conn.execute("SELECT resumen FROM secretario_contexto WHERE id=1").fetchone()
        if not fila:
            return ""
        return (fila["resumen"] if isinstance(fila, dict) else fila[0]) or ""
    except Exception:
        return ""
    finally:
        conn.close()


def leer_contexto_detalle():
    conn = get_connection()
    try:
        fila = conn.execute("SELECT resumen FROM secretario_contexto WHERE id=1").fetchone()
        if not fila:
            return {"resumen": "", "lineas": [], "actualizado_en": ""}
        resumen = (fila["resumen"] if isinstance(fila, dict) else fila[0]) or ""
        actualizado = ""
        try:
            fila2 = conn.execute("SELECT actualizado_en FROM secretario_contexto WHERE id=1").fetchone()
            if fila2:
                actualizado = str(fila2["actualizado_en"] if isinstance(fila2, dict) else fila2[0] or "")
        except Exception:
            actualizado = ""
        lineas = [ln.strip().lstrip("- ").strip() for ln in resumen.splitlines() if ln.strip()]
        return {"resumen": resumen, "lineas": lineas, "actualizado_en": actualizado}
    except Exception:
        return {"resumen": "", "lineas": [], "actualizado_en": ""}
    finally:
        conn.close()


def borrar_linea_contexto(indice):
    detalle = leer_contexto_detalle()
    lineas = detalle.get("lineas") or []
    try:
        idx = int(indice)
    except Exception:
        return False
    if idx < 0 or idx >= len(lineas):
        return False
    lineas.pop(idx)
    texto = "\n".join(f"- {ln}" for ln in lineas)
    escribir_contexto(texto)
    return True


def escribir_contexto(resumen):
    texto = (resumen or "").strip()[:MAX_RESUMEN]
    conn = get_connection()
    try:
        existe = conn.execute("SELECT id FROM secretario_contexto WHERE id=1").fetchone()
        if existe:
            conn.execute(
                "UPDATE secretario_contexto SET resumen=?, actualizado_en=datetime('now') WHERE id=1",
                (texto,),
            )
        else:
            conn.execute(
                "INSERT INTO secretario_contexto (id, resumen, actualizado_en) VALUES (1, ?, datetime('now'))",
                (texto,),
            )
        conn.commit()
    finally:
        conn.close()


def anotar_contexto(nota):
    nota = (nota or "").strip()
    if not nota:
        return
    actual = leer_contexto()
    if nota in actual:
        return
    mezclado = (actual + "\n- " + nota).strip()
    if len(mezclado) > MAX_RESUMEN:
        mezclado = _compactar_resumen(mezclado)
    escribir_contexto(mezclado)


def _compactar_resumen(texto):
    try:
        from server2 import _peticion_gemini, IA_API_KEY
        if not IA_API_KEY:
            return texto[-MAX_RESUMEN:]
        raw = _peticion_gemini(
            contents=[{"role": "user", "parts": [{"text": "Resume en español, viñetas cortas, sin inventar:\n" + texto}]}],
            system_instruction="Eres Jimmi, secretario de carpintería. Resume solo hechos útiles.",
            max_tokens=800,
            temperature=0.1,
        )
        from server2 import _gemini_extraer_texto
        compacto = (_gemini_extraer_texto(raw) or "").strip()
        return compacto[:MAX_RESUMEN] if compacto else texto[-MAX_RESUMEN:]
    except Exception:
        return texto[-MAX_RESUMEN:]


def _normalizar(texto):
    t = (texto or "").lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ü", "u"), ("ñ", "n")):
        t = t.replace(a, b)
    return " ".join(t.split())


def cruzar_articulos(articulos):
    conn = get_connection()
    try:
        mats = filas_a_lista(conn.execute("SELECT id, nombre, unidad, categoria FROM materiales").fetchall())
        precios = filas_a_lista(conn.execute(
            "SELECT material_id, proveedor, precio_unitario FROM precios"
        ).fetchall())
        por_mat = {}
        for p in precios:
            por_mat.setdefault(p.get("material_id"), []).append(p)
        idx = {_normalizar(m.get("nombre")): m for m in mats if m.get("nombre")}
        resultado = []
        for art in articulos or []:
            if not isinstance(art, dict):
                continue
            nombre = str(art.get("nombre") or "").strip()
            if not nombre:
                continue
            match = idx.get(_normalizar(nombre))
            precio_ticket = art.get("precio_unitario")
            try:
                precio_ticket = float(str(precio_ticket).replace(",", ".") or 0)
            except Exception:
                precio_ticket = 0
            item = dict(art)
            item["nombre"] = nombre
            if not match:
                item["accion_almacen"] = "crear"
                item["material_id"] = None
                item["precio_almacen"] = None
                item["nota_almacen"] = "No está en el almacén"
            else:
                item["material_id"] = match.get("id")
                item["accion_almacen"] = "mantener"
                item["nota_almacen"] = "Ya está en el almacén"
                propios = por_mat.get(match.get("id")) or []
                if propios:
                    mejor = min(propios, key=lambda x: float(x.get("precio_unitario") or 0) or 999999)
                    item["precio_almacen"] = mejor.get("precio_unitario")
                    item["proveedor_almacen"] = mejor.get("proveedor")
                    try:
                        pa = float(mejor.get("precio_unitario") or 0)
                    except Exception:
                        pa = 0
                    if precio_ticket and pa and abs(precio_ticket - pa) >= 0.01:
                        item["accion_almacen"] = "actualizar_precio"
                        item["nota_almacen"] = f"Tu precio: {pa:.2f} €. Ticket: {precio_ticket:.2f} €"
                unid = str(art.get("unidad") or "").strip()
                if unid and unid != str(match.get("unidad") or ""):
                    item["accion_almacen"] = "actualizar_datos"
                    item["nota_almacen"] = (item.get("nota_almacen") or "") + f" Unidad almacén: {match.get('unidad')}"
            resultado.append(item)
        return resultado
    finally:
        conn.close()


def snapshot_negocio(faena_id=None):
    conn = get_connection()
    try:
        try:
            faenas = filas_a_lista(conn.execute(
                """SELECT f.id, f.numero, f.tipo_trabajo, f.importe, f.direccion, f.archivada, f.fase,
                          c.nombre AS cliente_nombre
                   FROM faenas f LEFT JOIN clientes c ON f.cliente_id=c.id
                   WHERE f.archivada=0 AND COALESCE(f.fase,'')<>'terminada'
                   ORDER BY f.id DESC LIMIT 40"""
            ).fetchall())
        except Exception:
            faenas = filas_a_lista(conn.execute(
                """SELECT f.id, f.numero, f.tipo_trabajo, f.importe, f.direccion, f.archivada,
                          c.nombre AS cliente_nombre
                   FROM faenas f LEFT JOIN clientes c ON f.cliente_id=c.id
                   WHERE f.archivada=0 ORDER BY f.id DESC LIMIT 40"""
            ).fetchall())
        try:
            terminadas = filas_a_lista(conn.execute(
                """SELECT f.id, f.numero, f.tipo_trabajo, f.importe,
                          c.nombre AS cliente_nombre
                   FROM faenas f LEFT JOIN clientes c ON f.cliente_id=c.id
                   WHERE f.archivada=1 OR f.fase='terminada'
                   ORDER BY f.id DESC LIMIT 40"""
            ).fetchall())
        except Exception:
            terminadas = filas_a_lista(conn.execute(
                """SELECT f.id, f.numero, f.tipo_trabajo, f.importe,
                          c.nombre AS cliente_nombre
                   FROM faenas f LEFT JOIN clientes c ON f.cliente_id=c.id
                   WHERE f.archivada=1 ORDER BY f.id DESC LIMIT 40"""
            ).fetchall())
        mats = filas_a_lista(conn.execute(
            "SELECT m.id, m.nombre, m.unidad, m.categoria, p.proveedor, p.precio_unitario "
            "FROM materiales m LEFT JOIN precios p ON p.material_id=m.id "
            "ORDER BY m.nombre LIMIT 80"
        ).fetchall())
        extra = {}
        if faena_id:
            pres = filas_a_lista(conn.execute(
                "SELECT descripcion, cantidad, precio_unitario, total FROM presupuestos_faena WHERE faena_id=? LIMIT 40",
                (faena_id,),
            ).fetchall())
            gastos = filas_a_lista(conn.execute(
                "SELECT descripcion, cantidad, precio_unitario, total FROM gastos_faena "
                "WHERE faena_id=? AND LOWER(COALESCE(tipo,''))<>'presupuesto' LIMIT 40",
                (faena_id,),
            ).fetchall())
            extra = {"presupuesto": pres, "gastos": gastos}
        return {"faenas": faenas, "faenas_terminadas": terminadas, "materiales": mats, "faena_detalle": extra}
    finally:
        conn.close()


def chat_jimmi(pregunta, historial=None, faena_id=None):
    from server2 import _peticion_gemini, _gemini_extraer_texto, IA_API_KEY
    pregunta = (pregunta or "").strip()
    if not pregunta:
        return {"ok": False, "error": "Escribe una pregunta"}
    if not IA_API_KEY:
        return {"ok": False, "error": "Jimmi necesita CLAVE_API (Gemini) en Render"}

    memoria = leer_contexto()
    datos = snapshot_negocio(faena_id)
    hist = []
    for m in (historial or [])[-8:]:
        if isinstance(m, dict) and m.get("texto"):
            hist.append(f"{m.get('rol', 'usuario')}: {m.get('texto')}")
    system = (
        "Eres Jimmi, secretario de un taller de carpintería. Hablas español, claro y breve. "
        "Usa los datos de la app y tu memoria. No inventes precios ni faenas. "
        "Las faenas en curso están en datos_app.faenas. Las terminadas están en datos_app.faenas_terminadas. "
        "Si preguntan cuáles están terminadas, usa esa lista. Las correcciones del usuario en memoria_jimmi prevalecen. "
        "Si piden precios de tiendas, busca en internet si puedes y compara con el almacén. "
        "Si algo requiere cambiar datos, descríbelo y di que el usuario debe pulsar Aceptar. "
        "No borres faenas ni clientes."
    )
    user = {
        "pregunta": pregunta,
        "faena_id": faena_id,
        "memoria_jimmi": memoria,
        "datos_app": datos,
        "historial": hist,
    }
    import json
    contents = [{"role": "user", "parts": [{"text": json.dumps(user, ensure_ascii=False)}]}]
    try:
        raw = _peticion_gemini(
            contents=contents,
            system_instruction=system,
            max_tokens=1200,
            temperature=0.25,
            timeout=90,
            tools=[{"googleSearch": {}}],
        )
    except Exception:
        raw = _peticion_gemini(
            contents=contents,
            system_instruction=system,
            max_tokens=1200,
            temperature=0.25,
            timeout=90,
        )
    texto = (_gemini_extraer_texto(raw) or "").strip()
    if not texto:
        return {"ok": False, "error": "Jimmi no ha podido responder"}
    anotar_contexto(f"Pregunta: {pregunta[:200]} → {texto[:280]}")
    propuestas = []
    return {"ok": True, "data": {"respuesta": texto, "propuestas": propuestas, "motor": "jimmi"}}
