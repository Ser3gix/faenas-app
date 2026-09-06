# secretario.py — Jimmi: consulta, memoria en TiDB y propuestas
MAX_RESUMEN = 8000
MAX_MEMORIA_MODO = 2500

import json

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


def normalizar_modo(modo):
    m = str(modo or "").strip().lower()
    if m in ("materiales", "material"):
        return "materiales"
    if m in ("faenas", "trabajos", "trabajo"):
        return "faenas"
    return "todo"


def _etiquetas_linea(linea):
    tags = []
    rest = (linea or "").lstrip("- ").strip()
    while rest.startswith("["):
        fin = rest.find("]")
        if fin <= 0:
            break
        tags.append(rest[1:fin].strip().lower())
        rest = rest[fin + 1:].lstrip()
    return tags, rest


def _es_correccion(tags):
    return any(t.replace("ó", "o") == "correccion" for t in tags)


def memoria_para_modo(modo):
    modo = normalizar_modo(modo)
    lineas = leer_contexto_detalle().get("lineas") or []
    elegidas = []
    for ln in lineas:
        tags, _cuerpo = _etiquetas_linea(ln)
        if _es_correccion(tags):
            elegidas.append(ln)
            continue
        if modo == "todo":
            if not tags or "todo" in tags or "general" in tags:
                elegidas.append(ln)
        elif modo == "faenas":
            if "faenas" in tags or "trabajos" in tags:
                elegidas.append(ln)
        elif modo == "materiales":
            if "materiales" in tags:
                elegidas.append(ln)
    texto = "\n".join(f"- {ln}" for ln in elegidas)
    return texto[:MAX_MEMORIA_MODO]


def anotar_contexto(nota, modo=None):
    nota = (nota or "").strip()
    if not nota:
        return
    if not nota.startswith("["):
        nota = f"[{normalizar_modo(modo)}] {nota}"
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


def _faenas_activas(conn, limite):
    try:
        return filas_a_lista(conn.execute(
            """SELECT f.id, f.numero, f.tipo_trabajo, f.importe, f.direccion, f.archivada, f.fase,
                      c.nombre AS cliente_nombre
               FROM faenas f LEFT JOIN clientes c ON f.cliente_id=c.id
               WHERE f.archivada=0 AND COALESCE(f.fase,'')<>'terminada'
               ORDER BY f.id DESC LIMIT ?""",
            (limite,),
        ).fetchall())
    except Exception:
        return filas_a_lista(conn.execute(
            """SELECT f.id, f.numero, f.tipo_trabajo, f.importe, f.direccion, f.archivada,
                      c.nombre AS cliente_nombre
               FROM faenas f LEFT JOIN clientes c ON f.cliente_id=c.id
               WHERE f.archivada=0 ORDER BY f.id DESC LIMIT ?""",
            (limite,),
        ).fetchall())


def _faenas_terminadas(conn, limite):
    try:
        return filas_a_lista(conn.execute(
            """SELECT f.id, f.numero, f.tipo_trabajo, f.importe,
                      c.nombre AS cliente_nombre
               FROM faenas f LEFT JOIN clientes c ON f.cliente_id=c.id
               WHERE f.archivada=1 OR f.fase='terminada'
               ORDER BY f.id DESC LIMIT ?""",
            (limite,),
        ).fetchall())
    except Exception:
        return filas_a_lista(conn.execute(
            """SELECT f.id, f.numero, f.tipo_trabajo, f.importe,
                      c.nombre AS cliente_nombre
               FROM faenas f LEFT JOIN clientes c ON f.cliente_id=c.id
               WHERE f.archivada=1 ORDER BY f.id DESC LIMIT ?""",
            (limite,),
        ).fetchall())


def snapshot_negocio(faena_id=None, modo="todo"):
    modo = normalizar_modo(modo)
    incluir_faenas = modo in ("todo", "faenas")
    incluir_mats = modo in ("todo", "materiales")
    lim_act = 25 if modo == "todo" else 40
    lim_ter = 20 if modo == "todo" else 40
    lim_mat = 40 if modo == "todo" else 60
    conn = get_connection()
    try:
        faenas = _faenas_activas(conn, lim_act) if incluir_faenas else []
        terminadas = _faenas_terminadas(conn, lim_ter) if incluir_faenas else []
        mats = []
        if incluir_mats:
            mats = filas_a_lista(conn.execute(
                "SELECT m.id, m.nombre, m.unidad, m.categoria, m.definicion, p.proveedor, p.precio_unitario, p.fecha_actualizacion "
                "FROM materiales m LEFT JOIN precios p ON p.material_id=m.id "
                "ORDER BY m.nombre LIMIT ?",
                (lim_mat,),
            ).fetchall())
        extra = {}
        if faena_id and incluir_faenas:
            pres = filas_a_lista(conn.execute(
                "SELECT descripcion, cantidad, precio_unitario, total FROM presupuestos_faena WHERE faena_id=? LIMIT 40",
                (faena_id,),
            ).fetchall())
            gastos = filas_a_lista(conn.execute(
                "SELECT descripcion, cantidad, precio_unitario, total, fecha FROM gastos_faena "
                "WHERE faena_id=? AND LOWER(COALESCE(tipo,''))<>'presupuesto' LIMIT 40",
                (faena_id,),
            ).fetchall())
            extra = {"presupuesto": pres, "gastos": gastos, "tiempos": _tiempos_de_faena(conn, faena_id)}
        return {
            "modo": modo,
            "faenas": faenas,
            "faenas_terminadas": terminadas,
            "materiales": mats,
            "extracciones_compra": _extracciones_snapshot(conn, 15) if incluir_mats or incluir_faenas else [],
            "referencias_faena": _referencias_snapshot(conn, 15) if incluir_faenas else [],
            "tiempos_resumen": _tiempos_resumen(conn, 40) if incluir_faenas else [],
            "faena_detalle": extra,
        }
    finally:
        conn.close()


def _extracciones_snapshot(conn, limite):
    try:
        filas = filas_a_lista(conn.execute(
            "SELECT id, origen, proveedor, fecha_documento, faena_id, resumen, datos_json, fecha "
            "FROM extracciones_compra ORDER BY id DESC LIMIT ?",
            (limite,),
        ).fetchall())
    except Exception:
        return []
    out = []
    for f in filas:
        datos = {}
        raw = f.get("datos_json") or ""
        if isinstance(raw, str) and raw.strip():
            try:
                datos = json.loads(raw)
            except Exception:
                datos = {}
        arts = datos.get("articulos") if isinstance(datos, dict) else []
        if not isinstance(arts, list):
            arts = []
        out.append({
            "id": f.get("id"),
            "origen": f.get("origen"),
            "proveedor": f.get("proveedor"),
            "fecha_documento": f.get("fecha_documento"),
            "faena_id": f.get("faena_id"),
            "resumen": (f.get("resumen") or "")[:400],
            "articulos": arts[:20],
        })
    return out


def _referencias_snapshot(conn, limite):
    try:
        return filas_a_lista(conn.execute(
            "SELECT faena_id, numero, tipo_trabajo, resumen FROM referencias_faena ORDER BY id DESC LIMIT ?",
            (limite,),
        ).fetchall())
    except Exception:
        return []


def _tiempos_resumen(conn, limite):
    try:
        return filas_a_lista(conn.execute(
            """SELECT t.faena_id, f.numero AS faena_numero, t.categoria, SUM(t.minutos) AS minutos
               FROM tiempos_faena t LEFT JOIN faenas f ON f.id=t.faena_id
               WHERE COALESCE(t.fin,'')<>''
               GROUP BY t.faena_id, f.numero, t.categoria
               ORDER BY minutos DESC LIMIT ?""",
            (limite,),
        ).fetchall())
    except Exception:
        return []


def _tiempos_de_faena(conn, faena_id):
    try:
        return filas_a_lista(conn.execute(
            "SELECT categoria, inicio, fin, minutos FROM tiempos_faena WHERE faena_id=? ORDER BY id DESC LIMIT 40",
            (faena_id,),
        ).fetchall())
    except Exception:
        return []


def guardar_extraccion_compra(origen, data, faena_id=None, nombre_archivo=""):
    data = data if isinstance(data, dict) else {}
    articulos = data.get("articulos") or data.get("materiales") or []
    if not isinstance(articulos, list) or not articulos:
        return None
    data = dict(data)
    data["articulos"] = articulos
    proveedor = str(data.get("proveedor") or "").strip()
    fecha_doc = str(data.get("fecha") or data.get("fecha_documento") or "").strip()
    nombres = [str(a.get("nombre") or "").strip() for a in articulos if isinstance(a, dict)]
    nombres = [n for n in nombres if n][:6]
    resumen = f"{proveedor or 'compra'} {fecha_doc}. " + ", ".join(nombres)
    resumen = resumen.strip()[:500]
    fid = 0
    try:
        fid = int(faena_id or 0)
    except Exception:
        fid = 0
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO extracciones_compra
               (origen, nombre_archivo, proveedor, fecha_documento, faena_id, resumen, datos_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                (origen or "ticket").strip().lower(),
                (nombre_archivo or data.get("nombre_documento") or "")[:255],
                proveedor[:255],
                fecha_doc[:32],
                fid,
                resumen,
                json.dumps(data, ensure_ascii=False),
            ),
        )
        conn.commit()
        return resumen
    except Exception:
        return None
    finally:
        conn.close()


def extraer_ticket_de_texto(texto):
    if not texto:
        return None
    import re
    candidatos = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", texto, re.S | re.I)
    if "{" in texto and "}" in texto:
        candidatos.append(texto[texto.find("{"):texto.rfind("}") + 1])
    for c in candidatos:
        try:
            data = json.loads(c)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        arts = data.get("articulos") or data.get("materiales")
        if isinstance(arts, list) and any(isinstance(a, dict) and a.get("nombre") for a in arts):
            data["articulos"] = arts
            return data
    return None


def texto_sin_json_ticket(texto, ticket):
    if not texto or not ticket:
        return texto or ""
    import re
    limpio = re.sub(r"```(?:json)?\s*\{.*?\}\s*```", "", texto, flags=re.S | re.I).strip()
    return limpio or texto


def extraer_referencia_faena(faena_id):
    conn = get_connection()
    faena = None
    resumen = ""
    try:
        fila = conn.execute(
            """SELECT f.id, f.numero, f.tipo_trabajo, f.importe, c.nombre AS cliente_nombre
               FROM faenas f LEFT JOIN clientes c ON f.cliente_id=c.id WHERE f.id=?""",
            (faena_id,),
        ).fetchone()
        if not fila:
            return
        faena = fila_a_dict(fila)
        pres = filas_a_lista(conn.execute(
            "SELECT descripcion, cantidad, precio_unitario, total FROM presupuestos_faena WHERE faena_id=? LIMIT 40",
            (faena_id,),
        ).fetchall())
        gastos = filas_a_lista(conn.execute(
            "SELECT descripcion, cantidad, precio_unitario, total FROM gastos_faena WHERE faena_id=? LIMIT 40",
            (faena_id,),
        ).fetchall())
        tiempos = _tiempos_resumen_faena(conn, faena_id)
        datos = {
            "numero": faena.get("numero"),
            "tipo_trabajo": faena.get("tipo_trabajo"),
            "cliente": faena.get("cliente_nombre"),
            "importe": faena.get("importe"),
            "presupuesto": pres,
            "gastos": gastos,
            "tiempos": tiempos,
        }
        resumen = _resumen_heuristico_faena(datos)
        try:
            from server2 import _peticion_gemini, _gemini_extraer_texto, IA_API_KEY
            if IA_API_KEY:
                raw = _peticion_gemini(
                    contents=[{"role": "user", "parts": [{"text": json.dumps(datos, ensure_ascii=False)[:6000]}]}],
                    system_instruction=(
                        "Resume en español una faena de carpintería para futuros presupuestos. "
                        "JSON compacto: tipo_trabajo, materiales_tipicos, precios_pagados, horas_por_categoria, notas. "
                        "Sin IVA. No inventes."
                    ),
                    response_mime_type="application/json",
                    max_tokens=600,
                    temperature=0.1,
                    timeout=40,
                )
                parsed = extraer_ticket_de_texto(_gemini_extraer_texto(raw) or "") or {}
                if isinstance(parsed, dict) and parsed:
                    datos["ia"] = parsed
                    if parsed.get("notas"):
                        resumen = str(parsed.get("notas") or resumen)[:800]
                    elif parsed.get("tipo_trabajo"):
                        resumen = (str(parsed.get("tipo_trabajo")) + ". " + resumen)[:800]
        except Exception:
            pass
        conn.execute(
            """INSERT INTO referencias_faena (faena_id, numero, tipo_trabajo, resumen, datos_json)
               VALUES (?, ?, ?, ?, ?)""",
            (
                faena_id,
                str(faena.get("numero") or ""),
                str(faena.get("tipo_trabajo") or ""),
                resumen[:2000],
                json.dumps(datos, ensure_ascii=False),
            ),
        )
        conn.commit()
    except Exception:
        return
    finally:
        conn.close()
    if faena:
        anotar_contexto(
            f"[faenas] Archivada {faena.get('numero') or faena_id}: {resumen[:220]}",
            modo="faenas",
        )


def _tiempos_resumen_faena(conn, faena_id):
    try:
        return filas_a_lista(conn.execute(
            "SELECT categoria, SUM(minutos) AS minutos FROM tiempos_faena WHERE faena_id=? AND COALESCE(fin,'')<>'' GROUP BY categoria",
            (faena_id,),
        ).fetchall())
    except Exception:
        return []


def _resumen_heuristico_faena(datos):
    tipo = datos.get("tipo_trabajo") or "faena"
    imp = datos.get("importe") or 0
    mats = []
    for g in (datos.get("gastos") or [])[:8]:
        n = str(g.get("descripcion") or "").strip()
        if n:
            mats.append(n)
    horas = []
    for t in datos.get("tiempos") or []:
        horas.append(f"{t.get('categoria')}: {round(float(t.get('minutos') or 0)/60, 1)} h")
    partes = [str(tipo), f"cobrado {imp} €"]
    if mats:
        partes.append("materiales " + ", ".join(mats[:5]))
    if horas:
        partes.append("; ".join(horas))
    return ". ".join(partes)[:800]


def chat_jimmi(pregunta, historial=None, faena_id=None, modo="todo"):
    from server2 import _peticion_gemini, _gemini_extraer_texto, IA_API_KEY
    pregunta = (pregunta or "").strip()
    if not pregunta:
        return {"ok": False, "error": "Escribe una pregunta"}
    if not IA_API_KEY:
        return {"ok": False, "error": "Jimmi necesita CLAVE_API (Gemini) en Render"}

    modo = normalizar_modo(modo)
    memoria = memoria_para_modo(modo)
    datos = snapshot_negocio(faena_id, modo)
    hist = []
    for m in (historial or [])[-8:]:
        if isinstance(m, dict) and m.get("texto"):
            hist.append(f"{m.get('rol', 'usuario')}: {m.get('texto')}")
    system = (
        "Eres Jimmi, secretario de un taller de carpintería. Hablas español, claro y breve. "
        "Usa los datos de la app y tu memoria. No inventes precios ni faenas. "
        f"Modo de consulta: {modo}. "
        "Las faenas en curso están en datos_app.faenas. Las terminadas en datos_app.faenas_terminadas. "
        "Las compras analizadas (PDF/tickets) están en datos_app.extracciones_compra, mismo formato que tickets (articulos). "
        "Los tiempos reales están en datos_app.tiempos_resumen (faena_id, faena_numero, categoria, minutos). "
        "Categorías de tiempo: medicion_diseno, compras_gestion, trabajo. "
        "Las referencias de faenas archivadas están en datos_app.referencias_faena. "
        "Primero usa tarifas, extracciones y tiempos propios. Si falta un precio, busca en internet y cita fuente y fecha. "
        "Ignora IVA, CIF y totales fiscales. Usa el importe pagado de cada línea. "
        "Si ofreces materiales o precios para aceptar, termina con UN bloque ```json con el formato de ticket: "
        "{proveedor, fecha, total_ticket, articulos:[{nombre,cantidad,precio_unitario,total,unidad,categoria,definicion,fuente,url}]}. "
        "fuente es catalogo o web. url solo si es web. "
        "Si preguntan cuáles están terminadas, usa faenas_terminadas. Las correcciones en memoria_jimmi prevalecen. "
        "No borres faenas ni clientes."
    )
    user = {
        "pregunta": pregunta,
        "faena_id": faena_id,
        "modo": modo,
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
    ticket = extraer_ticket_de_texto(texto)
    propuestas = []
    if ticket:
        from server2 import _normalizar_articulo
        arts = []
        for a in ticket.get("articulos") or []:
            if not isinstance(a, dict):
                continue
            n = _normalizar_articulo(a)
            n["fuente"] = a.get("fuente") or "web"
            n["url"] = a.get("url") or ""
            n["proveedor"] = a.get("proveedor") or ticket.get("proveedor") or ""
            arts.append(n)
        ticket["articulos"] = arts
        if arts:
            guardar_extraccion_compra("web", ticket, faena_id)
            propuestas = arts
        texto = texto_sin_json_ticket(texto, ticket)
    return {
        "ok": True,
        "data": {
            "respuesta": texto,
            "propuestas": propuestas,
            "ticket": ticket if ticket and ticket.get("articulos") else None,
            "motor": "jimmi",
            "modo": modo,
        },
    }
