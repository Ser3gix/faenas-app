# secretario.py — Jimmi: consulta, memoria en TiDB y propuestas
MAX_RESUMEN = 8000
MAX_MEMORIA_MODO = 2500

import json

from database import get_connection, get_sqlite_local, fila_a_dict, filas_a_lista


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


_STOP_CONSULTA = {
    "cual", "cuales", "cuanto", "cuanta", "cuantos", "cuantas",
    "de", "del", "la", "el", "los", "las", "le", "lo",
    "es", "son", "tiene", "tienen", "hay", "para", "una", "un", "unos", "unas",
    "y", "o", "me", "te", "se", "mi", "tu", "dime", "quiero", "ver", "dame",
    "por", "favor", "puedo", "podrias", "podria", "ser", "al", "en", "con", "sin", "sobre",
    "que", "quien", "como", "donde", "cuando", "esta", "este", "estos", "estas",
    "lista", "listado", "todos", "todas", "algun", "alguno", "alguna",
    "existe", "existen", "consulta", "consultar", "app", "datos",
    "registro", "registros", "ficha", "fichas", "numero", "mas", "menos",
}

_QUITAR_BUSQUEDA = {
    "material", "materiales", "precio", "precios", "coste", "costo",
    "proveedor", "proveedores", "almacen", "catalogo",
    "faena", "faenas", "cliente", "clientes", "presupuesto", "importe",
    "direccion", "trabajo", "trabajos", "activa", "activas", "activo", "activos",
    "terminada", "terminadas", "archivada", "archivadas", "abierta", "abiertas",
    "curso", "pendiente", "pendientes", "taller",
    "nota", "notas", "anotacion", "anotaciones",
    "informacion", "datos", "resumen", "gastos", "tiempos", "fotos",
    "telefono",
}

_CLAVES_MATERIALES = (
    "material", "materiales", "precio", "precios", "proveedor", "proveedores",
    "almacen", "catalogo", "tablero", "tableros", "herraje", "herrajes",
    "bisagra", "bisagras",
)
_CLAVES_FAENAS = (
    "faena", "faenas", "cliente", "clientes", "presupuesto", "importe",
    "direccion", "trabajo", "trabajos", "activa", "activas", "terminada",
    "terminadas", "archivada", "archivadas",
    "nota", "notas", "anotacion", "anotaciones",
    "informacion", "datos", "resumen", "ficha", "gastos", "tiempos", "fotos",
    "telefono",
)


def _norm_txt(texto):
    t = (texto or "").lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ü", "u"), ("ñ", "n")):
        t = t.replace(a, b)
    limpio = []
    for ch in t:
        limpio.append(ch if ch.isalnum() or ch.isspace() else " ")
    return " ".join("".join(limpio).split())


def _tokens_consulta(pregunta):
    return [t for t in _norm_txt(pregunta).split() if len(t) > 1 and t not in _STOP_CONSULTA]


def _tokens_busqueda(pregunta):
    return [t for t in _tokens_consulta(pregunta) if t not in _QUITAR_BUSQUEDA]


def _score_texto(texto, tokens):
    t = _norm_txt(texto)
    n = 0
    for tok in tokens:
        variantes = [tok]
        if len(tok) > 4 and tok.endswith("s"):
            variantes.append(tok[:-1])
        if any(v in t for v in variantes):
            n += 1
    return n


def _filtra_por_tokens(items, tokens, campos_fn):
    if not tokens:
        return list(items)
    estrictos = []
    amplios = []
    for item in items:
        sc = _score_texto(campos_fn(item), tokens)
        if sc >= len(tokens):
            estrictos.append((sc, item))
        elif sc > 0:
            amplios.append((sc, item))
    elegidos = estrictos or amplios
    elegidos.sort(key=lambda x: -x[0])
    return [i for _, i in elegidos]


def _pide_web(pregunta):
    txt = _norm_txt(pregunta)
    return any(k in txt for k in ("internet", "google", "en la web", "online", "busca en web"))


def _huele_materiales(pregunta, modo):
    if modo == "materiales":
        return True
    txt = _norm_txt(pregunta)
    return any(k in txt for k in _CLAVES_MATERIALES)


def _huele_faenas(pregunta, modo):
    if modo == "faenas":
        return True
    txt = _norm_txt(pregunta)
    return any(k in txt for k in _CLAVES_FAENAS)


def _pide_ficha(pregunta):
    pal = set(_norm_txt(pregunta).split())
    return bool(pal & {
        "nota", "notas", "anotacion", "anotaciones",
        "informacion", "datos", "resumen", "ficha",
        "presupuesto", "direccion", "gastos", "tiempos", "fotos", "telefono",
    })


def _numeros_pregunta(pregunta):
    numeros = []
    for tok in _norm_txt(pregunta).split():
        dig = "".join(ch for ch in tok if ch.isdigit())
        if len(dig) >= 3 and dig not in numeros:
            numeros.append(dig)
    return numeros


def _variantes_numero(numero):
    n = "".join(ch for ch in str(numero or "") if ch.isdigit())
    if not n:
        return []
    vars_ = [n, n.lstrip("0") or "0"]
    if len(n) < 5:
        vars_.append(n.zfill(5))
    out = []
    for v in vars_:
        if v not in out:
            out.append(v)
    return out


def _sql_faena_campos():
    return (
        "SELECT f.id, f.numero, f.tipo_trabajo, f.importe, f.direccion, f.archivada, f.fase, "
        "f.fecha_inicio, f.carpeta, "
        "c.nombre AS cliente_nombre, c.telefono AS cliente_telefono, "
        "c.direccion AS cliente_direccion, c.email AS cliente_email, c.notas AS cliente_notas, "
        "i.nombre AS intermediario_nombre, i.telefono AS intermediario_telefono "
        "FROM faenas f "
        "LEFT JOIN clientes c ON f.cliente_id=c.id "
        "LEFT JOIN intermediarios i ON f.intermediario_id=i.id"
    )


def _sql_faena_campos_min():
    return (
        "SELECT f.id, f.numero, f.tipo_trabajo, f.importe, f.direccion, f.archivada, "
        "c.nombre AS cliente_nombre "
        "FROM faenas f LEFT JOIN clientes c ON f.cliente_id=c.id"
    )


def _fila_faena(conn, sql, params):
    try:
        fila = conn.execute(sql, params).fetchone()
        return fila_a_dict(fila) if fila else None
    except Exception:
        return None


def _faena_por_id(conn, faena_id):
    f = _fila_faena(conn, _sql_faena_campos() + " WHERE f.id=?", (faena_id,))
    if f:
        return f
    return _fila_faena(conn, _sql_faena_campos_min() + " WHERE f.id=?", (faena_id,))


def _buscar_faena_por_numero(conn, numero):
    for v in _variantes_numero(numero):
        like = f"%{v}%"
        for sql in (_sql_faena_campos(), _sql_faena_campos_min()):
            f = _fila_faena(
                conn,
                sql + " WHERE f.numero=? OR REPLACE(f.numero,'-','')=? OR REPLACE(REPLACE(f.numero,'-',''),'.','')=? OR f.numero LIKE ?",
                (v, v, v, like),
            )
            if f:
                return f
    return None


def _todas_faenas(conn):
    filas = _filas_faena_sql(conn, _sql_faena_campos() + " ORDER BY f.id DESC", ())
    if filas:
        return filas
    return _faenas_activas(conn, 800) + _faenas_terminadas(conn, 800)


def _mejor_faena_por_tokens(conn, tokens):
    if not tokens:
        return None
    pool = _filtra_por_tokens(
        _todas_faenas(conn),
        tokens,
        lambda f: " ".join(str(f.get(k) or "") for k in (
            "numero", "tipo_trabajo", "cliente_nombre", "direccion", "fase", "importe",
        )),
    )
    if not pool:
        return None
    return _faena_por_id(conn, pool[0].get("id")) or pool[0]


def _pide_listado_faenas(pregunta):
    txt = _norm_txt(pregunta)
    return any(k in txt for k in (
        "cuantas", "cuantos", "activas", "terminadas", "listado", "todas las faenas", "que faenas",
    ))


def _resolver_faena(conn, pregunta, faena_id=None):
    for num in _numeros_pregunta(pregunta):
        faena = _buscar_faena_por_numero(conn, num)
        if faena:
            return faena
    if faena_id:
        f = _faena_por_id(conn, faena_id)
        if f:
            return f
    hallada = _mejor_faena_por_tokens(conn, _tokens_busqueda(pregunta))
    if hallada:
        return hallada
    if getattr(conn, "_backend", "") == "mysql":
        sqlite = None
        try:
            sqlite = get_sqlite_local()
            for num in _numeros_pregunta(pregunta):
                faena = _buscar_faena_por_numero(sqlite, num)
                if faena:
                    return faena
            if faena_id:
                f = _faena_por_id(sqlite, faena_id)
                if f:
                    return f
            return _mejor_faena_por_tokens(sqlite, _tokens_busqueda(pregunta))
        except Exception as e:
            print("jimmi sqlite faena:", e)
            return None
        finally:
            if sqlite:
                sqlite.close()
    return None


def _anotaciones_de_faena(conn, faena_id, limite=80, numero=""):
    acc = []
    vistos = set()

    def ids_en(cn):
        hallados = set()
        if faena_id not in (None, ""):
            try:
                hallados.add(int(faena_id))
            except Exception:
                pass
        if numero:
            for v in _variantes_numero(numero):
                for r in _filas_faena_sql(
                    cn,
                    "SELECT id FROM faenas WHERE numero=? OR REPLACE(numero,'-','')=?",
                    (v, v),
                ):
                    if r.get("id") is not None:
                        hallados.add(int(r["id"]))
        return hallados

    def leer(cn, fid):
        try:
            filas = filas_a_lista(cn.execute(
                "SELECT * FROM anotaciones WHERE faena_id=? ORDER BY id DESC",
                (int(fid),),
            ).fetchall())
        except Exception as e:
            print("jimmi anotaciones:", e)
            return
        for a in filas:
            contenido = str(a.get("contenido") or a.get("texto") or a.get("nota") or "")
            clave = (str(a.get("fecha") or ""), contenido[:240], str(a.get("tipo") or ""))
            if clave in vistos:
                continue
            vistos.add(clave)
            acc.append(a)

    for fid in ids_en(conn):
        leer(conn, fid)
    if getattr(conn, "_backend", "") == "mysql":
        sqlite = None
        try:
            sqlite = get_sqlite_local()
            for fid in ids_en(sqlite):
                leer(sqlite, fid)
        except Exception as e:
            print("jimmi anotaciones sqlite:", e)
        finally:
            if sqlite:
                sqlite.close()
    return acc[:limite]


def _filas_faena_sql(conn, sql, params):
    try:
        return filas_a_lista(conn.execute(sql, params).fetchall())
    except Exception:
        return []


def _cargar_faena_completa(conn, faena):
    fid = faena.get("id")
    gastos = _filas_faena_sql(
        conn,
        "SELECT tipo, descripcion, cantidad, precio_unitario, total, fecha FROM gastos_faena "
        "WHERE faena_id=? ORDER BY id DESC LIMIT 40",
        (fid,),
    )
    presupuesto = _filas_faena_sql(
        conn,
        "SELECT tipo, descripcion, cantidad, precio_unitario, total FROM presupuestos_faena "
        "WHERE faena_id=? ORDER BY id LIMIT 40",
        (fid,),
    )
    fotos = _filas_faena_sql(
        conn,
        "SELECT nombre, fecha FROM fotos_faena WHERE faena_id=? ORDER BY id DESC LIMIT 30",
        (fid,),
    )
    extracciones = _filas_faena_sql(
        conn,
        "SELECT origen, proveedor, fecha_documento, resumen FROM extracciones_compra "
        "WHERE faena_id=? ORDER BY id DESC LIMIT 10",
        (fid,),
    )
    return {
        "faena": faena,
        "anotaciones": _anotaciones_de_faena(conn, fid, numero=faena.get("numero") or ""),
        "gastos": gastos,
        "presupuesto": presupuesto,
        "tiempos": _tiempos_de_faena(conn, fid),
        "tiempos_resumen": _tiempos_resumen_faena(conn, fid),
        "fotos": fotos,
        "compras": extracciones,
    }


def _linea_importe(item):
    desc = (item.get("descripcion") or "").strip() or "sin descripción"
    cant = item.get("cantidad")
    total = _fmt_precio(item.get("total") if item.get("total") not in (None, "") else None)
    if total == "sin precio":
        total = _fmt_precio(item.get("precio_unitario"))
    extra = f" x {cant}" if cant not in (None, "", 1, 1.0) else ""
    return f"- {desc}{extra}: {total}"


def _texto_faena_completa(datos):
    f = datos.get("faena") or {}
    num = f.get("numero") or f.get("id") or ""
    estado = "archivada" if int(float(f.get("archivada") or 0)) else (f.get("fase") or "en_proceso")
    partes = [
        f"Faena {num}",
        f"- Cliente: {f.get('cliente_nombre') or 'sin cliente'}",
        f"- Teléfono: {f.get('cliente_telefono') or 'sin teléfono'}",
        f"- Dirección: {f.get('direccion') or f.get('cliente_direccion') or 'sin dirección'}",
        f"- Intermediario: {f.get('intermediario_nombre') or 'cliente directo'}",
        f"- Trabajo: {f.get('tipo_trabajo') or 'sin tipo'}",
        f"- Importe: {_fmt_precio(f.get('importe'))}",
        f"- Estado: {estado}",
        f"- Inicio: {f.get('fecha_inicio') or 'sin fecha'}",
    ]
    notas_cli = (f.get("cliente_notas") or "").strip()
    if notas_cli:
        partes.append(f"- Notas del cliente: {notas_cli[:400]}")

    anotaciones = datos.get("anotaciones") or []
    partes.append("Anotaciones:")
    texto_n = _texto_notas_faena(f, anotaciones)
    if "no tiene anotaciones" in texto_n:
        partes.append("- ninguna")
    else:
        partes.extend(texto_n.splitlines()[1:] or ["- ninguna"])

    pres = datos.get("presupuesto") or []
    partes.append("Presupuesto:")
    if not pres:
        partes.append("- sin líneas")
    else:
        partes.extend(_linea_importe(p) for p in pres[:20])
        if len(pres) > 20:
            partes.append(f"- Y {len(pres) - 20} más.")

    gastos = datos.get("gastos") or []
    partes.append("Gastos:")
    if not gastos:
        partes.append("- ninguno")
    else:
        partes.extend(_linea_importe(g) for g in gastos[:20])
        if len(gastos) > 20:
            partes.append(f"- Y {len(gastos) - 20} más.")

    tres = datos.get("tiempos_resumen") or []
    partes.append("Tiempos:")
    if not tres:
        partes.append("- sin tiempos cerrados")
    else:
        for t in tres:
            mins = float(t.get("minutos") or 0)
            partes.append(f"- {t.get('categoria') or 'otro'}: {mins:.0f} min ({mins/60:.1f} h)")

    fotos = datos.get("fotos") or []
    partes.append(f"Fotos: {len(fotos)}" + ("" if not fotos else ""))
    for fo in fotos[:15]:
        partes.append(f"- {fo.get('nombre') or 'foto'}")

    compras = datos.get("compras") or []
    if compras:
        partes.append("Compras leídas:")
        for c in compras:
            partes.append(f"- {c.get('origen') or 'ticket'} {c.get('proveedor') or ''} {c.get('resumen') or ''}".strip())

    return "\n".join(partes)


def _texto_notas_faena(faena, anotaciones):
    num = faena.get("numero") or faena.get("id") or ""
    cliente = faena.get("cliente_nombre") or "sin cliente"
    trabajo = faena.get("tipo_trabajo") or "sin tipo"
    if not anotaciones:
        return f"La faena {num} ({cliente}, {trabajo}) no tiene anotaciones."
    lineas = []
    for a in anotaciones:
        tipo = str(a.get("tipo") or "texto").strip().lower()
        contenido = str(a.get("contenido") or a.get("texto") or a.get("nota") or "").strip()
        fecha = str(a.get("fecha") or "").strip()
        pref = f"[{fecha}] " if fecha else ""
        if contenido.startswith("data:") or (tipo in {"foto", "imagen", "image", "photo"} and len(contenido) > 200):
            lineas.append(f"- {pref}foto".strip())
            continue
        if tipo == "archivo" and (not contenido or contenido.startswith("/") or "." in contenido[:40] and " " not in contenido):
            lineas.append(f"- {pref}archivo {contenido[:120]}".strip())
            continue
        if not contenido:
            lineas.append(f"- {pref}({tipo or 'nota vacía'})".strip())
            continue
        lineas.append(f"- {pref}{contenido[:1200]}".strip())
    if not lineas:
        return f"La faena {num} ({cliente}, {trabajo}) no tiene anotaciones de texto."
    return f"Anotaciones de la faena {num} ({cliente}, {trabajo}):\n" + "\n".join(lineas)


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


def snapshot_negocio(faena_id=None, modo="todo", pregunta=None):
    modo = normalizar_modo(modo)
    incluir_faenas = modo in ("todo", "faenas")
    incluir_mats = modo in ("todo", "materiales")
    lim_act = 25 if modo == "todo" else 40
    lim_ter = 20 if modo == "todo" else 40
    lim_mat = 40 if modo == "todo" else 60
    tokens = _tokens_busqueda(pregunta or "")
    conn = get_connection()
    try:
        scan_f = 400 if tokens else lim_act
        scan_t = 400 if tokens else lim_ter
        faenas = _faenas_activas(conn, scan_f) if incluir_faenas else []
        terminadas = _faenas_terminadas(conn, scan_t) if incluir_faenas else []
        if tokens and incluir_faenas:
            def _txt_faena(f):
                return " ".join(str(f.get(k) or "") for k in (
                    "numero", "tipo_trabajo", "cliente_nombre", "direccion", "fase", "importe",
                ))
            faenas = _filtra_por_tokens(faenas, tokens, _txt_faena)[:lim_act]
            terminadas = _filtra_por_tokens(terminadas, tokens, _txt_faena)[:lim_ter]
        else:
            faenas = faenas[:lim_act]
            terminadas = terminadas[:lim_ter]
        mats = []
        if incluir_mats:
            sql_mat = (
                "SELECT m.id, m.nombre, m.unidad, m.categoria, m.definicion, p.proveedor, p.precio_unitario, p.fecha_actualizacion "
                "FROM materiales m LEFT JOIN precios p ON p.material_id=m.id "
                "ORDER BY m.nombre"
            )
            if tokens:
                mats = filas_a_lista(conn.execute(sql_mat).fetchall())
                mats = _filtra_por_tokens(
                    mats,
                    tokens,
                    lambda m: " ".join(str(m.get(k) or "") for k in (
                        "nombre", "categoria", "definicion", "proveedor",
                    )),
                )[:lim_mat]
            else:
                mats = filas_a_lista(conn.execute(sql_mat + " LIMIT ?", (lim_mat,)).fetchall())
        extra = {}
        faenas_completas = []
        if incluir_faenas:
            ids_detalle = []
            if faena_id:
                ids_detalle.append(faena_id)
            for num in _numeros_pregunta(pregunta or ""):
                fnum = _buscar_faena_por_numero(conn, num)
                if fnum and fnum.get("id") and fnum.get("id") not in ids_detalle:
                    ids_detalle.append(fnum.get("id"))
            for fid in ids_detalle[:3]:
                fila_id = conn.execute(_sql_faena_campos() + " WHERE f.id=?", (fid,)).fetchone()
                if not fila_id:
                    continue
                completo = _cargar_faena_completa(conn, fila_a_dict(fila_id))
                faenas_completas.append({
                    "faena": completo.get("faena"),
                    "anotaciones": [
                        {
                            "tipo": a.get("tipo"),
                            "fecha": a.get("fecha"),
                            "contenido": (a.get("contenido") or "")[:500],
                        }
                        for a in (completo.get("anotaciones") or [])
                        if not str(a.get("contenido") or "").startswith("data:")
                    ],
                    "presupuesto": completo.get("presupuesto") or [],
                    "gastos": completo.get("gastos") or [],
                    "tiempos": completo.get("tiempos") or [],
                    "tiempos_resumen": completo.get("tiempos_resumen") or [],
                    "fotos": completo.get("fotos") or [],
                    "compras": completo.get("compras") or [],
                })
            if faenas_completas:
                extra = faenas_completas[0]
        return {
            "modo": modo,
            "faenas": faenas,
            "faenas_terminadas": terminadas,
            "materiales": mats,
            "extracciones_compra": _extracciones_snapshot(conn, 15) if incluir_mats or incluir_faenas else [],
            "referencias_faena": _referencias_snapshot(conn, 15) if incluir_faenas else [],
            "tiempos_resumen": _tiempos_resumen(conn, 40) if incluir_faenas else [],
            "faena_detalle": extra,
            "faenas_completas": faenas_completas,
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


def _estado_faena_pregunta(pregunta):
    txt = _norm_txt(pregunta)
    if any(k in txt for k in ("terminad", "archivad")):
        return "terminadas"
    if any(k in txt for k in ("activ", "abierta", "en curso", "pendient")):
        return "activas"
    return "todas"


def _fmt_precio(valor):
    try:
        n = float(valor or 0)
    except Exception:
        n = 0.0
    if n <= 0:
        return "sin precio"
    return f"{n:.2f} EUR"


def _texto_materiales(filas, tokens, limite=15):
    agrupados = {}
    orden = []
    for f in filas:
        nombre = (f.get("nombre") or "Sin nombre").strip() or "Sin nombre"
        if nombre not in agrupados:
            agrupados[nombre] = {
                "categoria": f.get("categoria") or "",
                "precios": [],
            }
            orden.append(nombre)
        if f.get("precio_unitario") is not None:
            agrupados[nombre]["precios"].append(
                f"{(f.get('proveedor') or 'sin proveedor')}: {_fmt_precio(f.get('precio_unitario'))}"
            )
    n = len(orden)
    q = " ".join(tokens) if tokens else "el catálogo"
    if n == 0:
        return f"No hay materiales que coincidan con «{q}»."
    lineas = []
    for nombre in orden[:limite]:
        info = agrupados[nombre]
        detalle = ", ".join(info["precios"]) or "sin precio registrado"
        cat = info["categoria"] or "Sin categoría"
        lineas.append(f"- {nombre} | {cat} | {detalle}")
    extra = "" if n <= limite else f"\nY {n - limite} más."
    return f"Hay {n} material(es) que coinciden con «{q}»:\n" + "\n".join(lineas) + extra


def _texto_faenas(filas, tokens, etiqueta, limite=12):
    n = len(filas)
    q = " ".join(tokens) if tokens else etiqueta
    if n == 0:
        return f"No hay faenas {etiqueta} que coincidan con «{q}»." if tokens else f"No hay faenas {etiqueta}."
    lineas = []
    for f in filas[:limite]:
        lineas.append(
            f"- {f.get('numero') or f.get('id') or ''} | "
            f"{f.get('cliente_nombre') or 'Sin cliente'} | "
            f"{f.get('tipo_trabajo') or 'Sin trabajo'} | "
            f"{_fmt_precio(f.get('importe'))}"
        )
    extra = "" if n <= limite else f"\nY {n - limite} más."
    cab = f"Hay {n} faena(s) {etiqueta}"
    if tokens:
        cab += f" que coinciden con «{' '.join(tokens)}»"
    return cab + ":\n" + "\n".join(lineas) + extra


def _respuesta_local_datos(pregunta, modo="todo", faena_id=None):
    modo = normalizar_modo(modo)
    tokens = _tokens_busqueda(pregunta)
    quiere_m = _huele_materiales(pregunta, modo)
    quiere_f = _huele_faenas(pregunta, modo)
    if modo == "materiales":
        quiere_f = False
    if modo == "faenas":
        quiere_m = False
    if not quiere_m and not quiere_f:
        return None

    conn = get_connection()
    try:
        texto_m = ""
        texto_f = ""
        if quiere_m:
            mats = filas_a_lista(conn.execute(
                "SELECT m.id, m.nombre, m.unidad, m.categoria, m.definicion, p.proveedor, p.precio_unitario "
                "FROM materiales m LEFT JOIN precios p ON p.material_id=m.id "
                "ORDER BY m.nombre"
            ).fetchall())
            if tokens:
                mats = _filtra_por_tokens(
                    mats,
                    tokens,
                    lambda m: " ".join(str(m.get(k) or "") for k in (
                        "nombre", "categoria", "definicion", "proveedor",
                    )),
                )
            texto_m = _texto_materiales(mats, tokens)
        if quiere_f:
            concreta = _resolver_faena(conn, pregunta, faena_id)
            listado = _pide_listado_faenas(pregunta)
            if concreta and not listado:
                texto_f = _texto_faena_completa(_cargar_faena_completa(conn, concreta))
            elif not concreta and (_pide_ficha(pregunta) or _numeros_pregunta(pregunta)) and not listado:
                if _numeros_pregunta(pregunta):
                    texto_f = f"No encuentro la faena {_numeros_pregunta(pregunta)[0]}."
                else:
                    texto_f = "Dime el número de la faena o el nombre del cliente y te paso todos los datos."
            if not texto_f:
                estado = _estado_faena_pregunta(pregunta)
                activas = _faenas_activas(conn, 500)
                terminadas = _faenas_terminadas(conn, 500)
                if estado == "activas":
                    pool, etiqueta = activas, "activas"
                elif estado == "terminadas":
                    pool, etiqueta = terminadas, "terminadas"
                else:
                    pool, etiqueta = activas + terminadas, ""
                if tokens:
                    pool = _filtra_por_tokens(
                        pool,
                        tokens,
                        lambda f: " ".join(str(f.get(k) or "") for k in (
                            "numero", "tipo_trabajo", "cliente_nombre", "direccion", "fase", "importe",
                        )),
                    )
                texto_f = _texto_faenas(pool, tokens, etiqueta or "en total")
    finally:
        conn.close()

    partes = [p for p in (texto_m, texto_f) if p]
    if not partes:
        return None
    return {"usar": True, "texto": "\n\n".join(partes)}


def chat_jimmi(pregunta, historial=None, faena_id=None, modo="todo"):
    from server2 import _peticion_gemini, _gemini_extraer_texto, IA_API_KEY
    pregunta = (pregunta or "").strip()
    if not pregunta:
        return {"ok": False, "error": "Escribe una pregunta"}

    modo = normalizar_modo(modo)
    local = None
    try:
        local = _respuesta_local_datos(pregunta, modo, faena_id=faena_id)
    except Exception as e:
        print("jimmi local:", e)
        local = None
    if local and local.get("usar") and not _pide_web(pregunta):
        return {
            "ok": True,
            "data": {
                "respuesta": local.get("texto") or "",
                "propuestas": [],
                "ticket": None,
                "motor": "datos",
                "modelo": "",
                "modo": modo,
            },
        }

    if not IA_API_KEY:
        if local and local.get("texto"):
            return {
                "ok": True,
                "data": {
                    "respuesta": local.get("texto"),
                    "propuestas": [],
                    "ticket": None,
                    "motor": "datos",
                    "modelo": "",
                    "modo": modo,
                },
            }
        return {"ok": False, "error": "Jimmi necesita CLAVE_API (Gemini) en Render"}

    memoria = memoria_para_modo(modo)
    datos = snapshot_negocio(faena_id, modo, pregunta=pregunta)
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
        "Si preguntan por una faena concreta (número, notas, datos), usa datos_app.faenas_completas: cliente, dirección, presupuesto, gastos, anotaciones, tiempos y fotos. "
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
    contents = [{"role": "user", "parts": [{"text": json.dumps(user, ensure_ascii=False)}]}]
    usa_web = _pide_web(pregunta)
    try:
        kwargs = dict(
            contents=contents,
            system_instruction=system,
            max_tokens=1200,
            temperature=0.25,
            timeout=90,
        )
        if usa_web:
            try:
                raw = _peticion_gemini(tools=[{"googleSearch": {}}], **kwargs)
            except Exception:
                raw = _peticion_gemini(**kwargs)
        else:
            raw = _peticion_gemini(**kwargs)
    except Exception as e:
        if local and local.get("texto"):
            return {
                "ok": True,
                "data": {
                    "respuesta": local.get("texto"),
                    "propuestas": [],
                    "ticket": None,
                    "motor": "datos",
                    "modelo": "",
                    "modo": modo,
                },
            }
        return {"ok": False, "error": f"Jimmi: {str(e)}"}
    from server2 import _GEMINI_ULTIMO_MODELO
    modelo = _GEMINI_ULTIMO_MODELO or ""
    texto = (_gemini_extraer_texto(raw) or "").strip()
    if not texto:
        if local and local.get("texto"):
            return {
                "ok": True,
                "data": {
                    "respuesta": local.get("texto"),
                    "propuestas": [],
                    "ticket": None,
                    "motor": "datos",
                    "modelo": modelo,
                    "modo": modo,
                },
            }
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
            "modelo": modelo,
            "modo": modo,
        },
    }
