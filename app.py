"""
Servidor API cloud para la app de carpintería (Faenas).
Expone los mismos endpoints que el servidor Windows local más
nuevos endpoints de IA (Google Gemini).

Compatible con Supabase (PostgreSQL) y desplegable en Railway/Render.

Variables de entorno requeridas:
  DATABASE_URL  — cadena de conexión PostgreSQL (Supabase)
  GEMINI_API_KEY — clave de la API de Google Gemini
  PORT          — (opcional) puerto, por defecto 5000
"""

import os
import json
import re
import base64
import logging
from datetime import datetime, date
from decimal import Decimal

from flask import Flask, request
from flask_cors import CORS
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Configuración ────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Inicializar Gemini si la clave está disponible
_gemini_model = None
if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        _gemini_model = genai.GenerativeModel("gemini-1.5-flash")
        print("✓ Gemini inicializado correctamente")
    except Exception as exc:
        print(f"⚠ No se pudo inicializar Gemini: {exc}")


# ─── Base de datos ────────────────────────────────────────────────────────────
def get_db():
    """Abre y retorna una conexión a PostgreSQL con cursor de diccionario."""
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


# ─── Serialización JSON ───────────────────────────────────────────────────────
def _json_serial(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Tipo no serializable: {type(obj)}")


def ok(data=None, **extra):
    payload = {"ok": True, "data": data, **extra}
    return app.response_class(
        json.dumps(payload, default=_json_serial, ensure_ascii=False),
        mimetype="application/json",
    )


def err(msg, code=400):
    payload = {"ok": False, "error": msg}
    return (
        app.response_class(
            json.dumps(payload, ensure_ascii=False),
            mimetype="application/json",
        ),
        code,
    )


def server_err(exc, public_msg="Error interno del servidor"):
    """Registra la excepción completa y devuelve un mensaje genérico al cliente."""
    logger.exception("Error interno: %s", exc)
    return err(public_msg, 500)


# ─── Utilidades ───────────────────────────────────────────────────────────────
def gen_numero_faena(conn):
    """Genera el siguiente número de faena (F0001, F0002 …)."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM faenas")
        total = cur.fetchone()["total"] or 0
    return f"F{total + 1:04d}"


def extract_json(text):
    """Extrae el primer objeto JSON de un texto que puede contener markdown."""
    text = re.sub(r"```(?:json)?\n?", "", text).strip()
    text = re.sub(r"```\n?", "", text).strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return json.loads(match.group())
    return json.loads(text)


def rows_to_list(rows):
    """Convierte filas de psycopg2 a lista de dicts planos."""
    return [dict(r) for r in rows]


# ─── Estado del servidor ──────────────────────────────────────────────────────
@app.route("/api/sync/estado")
def sync_estado():
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return ok({"status": "ok", "version": "cloud-1.0"})
    except Exception as exc:
        return server_err(exc, "No se pudo conectar a la base de datos")

# ─── Clientes ─────────────────────────────────────────────────────────────────
@app.route("/api/clientes", methods=["GET"])
def get_clientes():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nombre, telefono, email, intermediario_id "
                "FROM clientes ORDER BY nombre"
            )
            return ok(rows_to_list(cur.fetchall()))


@app.route("/api/clientes", methods=["POST"])
def create_cliente():
    d = request.json or {}
    nombre = (d.get("nombre") or "").strip()
    if not nombre:
        return err("El nombre del cliente es obligatorio")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO clientes (nombre, telefono, email, intermediario_id) "
                "VALUES (%s,%s,%s,%s) RETURNING id, nombre",
                (
                    nombre,
                    d.get("telefono", ""),
                    d.get("email", ""),
                    d.get("intermediario_id", 0),
                ),
            )
            row = dict(cur.fetchone())
            conn.commit()
    return ok({"id": row["id"], "nombre": row["nombre"]})


# ─── Faenas ───────────────────────────────────────────────────────────────────
@app.route("/api/faenas", methods=["GET"])
def get_faenas():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT f.id, f.numero, f.cliente_id, f.intermediario_id, "
                "f.intermediario_nombre, f.direccion, f.tipo_trabajo, "
                "f.importe, f.fecha_inicio, f.archivada, "
                "COALESCE(c.nombre, '—') AS cliente_nombre "
                "FROM faenas f LEFT JOIN clientes c ON f.cliente_id = c.id "
                "ORDER BY f.id DESC"
            )
            return ok(rows_to_list(cur.fetchall()))


@app.route("/api/faenas", methods=["POST"])
def create_faena():
    d = request.json or {}
    with get_db() as conn:
        numero = gen_numero_faena(conn)
        with conn.cursor() as cur:
            # Resolver nombre del cliente
            cliente_nombre = "—"
            if d.get("cliente_id"):
                cur.execute(
                    "SELECT nombre FROM clientes WHERE id=%s", (d["cliente_id"],)
                )
                row = cur.fetchone()
                if row:
                    cliente_nombre = row["nombre"]

            cur.execute(
                "INSERT INTO faenas "
                "(numero, cliente_id, intermediario_id, intermediario_nombre, "
                " direccion, tipo_trabajo, importe, fecha_inicio) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id, numero",
                (
                    numero,
                    d.get("cliente_id"),
                    d.get("intermediario_id", 0),
                    d.get("intermediario_nombre", "Cliente directo"),
                    d.get("direccion", ""),
                    d.get("tipo_trabajo", ""),
                    d.get("importe", 0),
                    d.get("fecha_inicio") or date.today().isoformat(),
                ),
            )
            row = dict(cur.fetchone())
            conn.commit()
    return ok({"id": row["id"], "numero": row["numero"]})


@app.route("/api/faenas/<int:faena_id>", methods=["PUT"])
def update_faena(faena_id):
    d = request.json or {}
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE faenas SET direccion=%s, tipo_trabajo=%s, importe=%s, fecha_inicio=%s "
                "WHERE id=%s",
                (
                    d.get("direccion", ""),
                    d.get("tipo_trabajo", ""),
                    d.get("importe", 0),
                    d.get("fecha_inicio"),
                    faena_id,
                ),
            )
            conn.commit()
    return ok()


# ─── Anotaciones ──────────────────────────────────────────────────────────────
@app.route("/api/faenas/<int:faena_id>/anotaciones", methods=["GET"])
def get_anotaciones(faena_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, faena_id, tipo, contenido, fecha "
                "FROM anotaciones WHERE faena_id=%s ORDER BY fecha DESC",
                (faena_id,),
            )
            return ok(rows_to_list(cur.fetchall()))


@app.route("/api/faenas/<int:faena_id>/anotaciones", methods=["POST"])
def create_anotacion(faena_id):
    d = request.json or {}
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO anotaciones (faena_id, tipo, contenido) "
                "VALUES (%s,%s,%s) RETURNING id",
                (faena_id, d.get("tipo", "texto"), d.get("contenido", "")),
            )
            row = cur.fetchone()
            conn.commit()
    return ok({"id": row["id"]})


@app.route("/api/anotaciones/<int:anot_id>", methods=["PUT"])
def update_anotacion(anot_id):
    d = request.json or {}
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE anotaciones SET tipo=%s, contenido=%s WHERE id=%s",
                (d.get("tipo", "texto"), d.get("contenido", ""), anot_id),
            )
            conn.commit()
    return ok()


@app.route("/api/anotaciones/<int:anot_id>", methods=["DELETE"])
def delete_anotacion(anot_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM anotaciones WHERE id=%s", (anot_id,))
            conn.commit()
    return ok()


# ─── Materiales ───────────────────────────────────────────────────────────────
@app.route("/api/materiales", methods=["GET"])
def get_materiales():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT m.id, m.nombre, m.unidad, m.categoria, m.definicion, "
                "COALESCE( "
                "  json_agg( "
                "    json_build_object('proveedor', p.proveedor, 'precio_unitario', p.precio_unitario) "
                "  ) FILTER (WHERE p.id IS NOT NULL), '[]' "
                ") AS precios "
                "FROM materiales m "
                "LEFT JOIN precios_materiales p ON m.id = p.material_id "
                "GROUP BY m.id "
                "ORDER BY m.categoria, m.nombre"
            )
            rows = []
            for row in cur.fetchall():
                r = dict(row)
                # psycopg2 puede devolver el json_agg como string
                if isinstance(r.get("precios"), str):
                    r["precios"] = json.loads(r["precios"])
                rows.append(r)
    return ok(rows)


@app.route("/api/materiales", methods=["POST"])
def create_material():
    d = request.json or {}
    nombre = (d.get("nombre") or "").strip()
    if not nombre:
        return err("El nombre del material es obligatorio")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM materiales WHERE LOWER(nombre)=LOWER(%s)", (nombre,)
            )
            existing = cur.fetchone()
            if existing:
                mat_id = existing["id"]
            else:
                cur.execute(
                    "INSERT INTO materiales (nombre, unidad, categoria) "
                    "VALUES (%s,%s,%s) RETURNING id",
                    (nombre, d.get("unidad", "ud"), d.get("categoria", "Otros")),
                )
                mat_id = cur.fetchone()["id"]

            if d.get("proveedor") and d.get("precio_unitario") is not None:
                cur.execute(
                    "INSERT INTO precios_materiales (material_id, proveedor, precio_unitario) "
                    "VALUES (%s,%s,%s) "
                    "ON CONFLICT (material_id, proveedor) DO UPDATE SET precio_unitario=%s",
                    (mat_id, d["proveedor"], d["precio_unitario"], d["precio_unitario"]),
                )
            conn.commit()
    return ok({"id": mat_id})


@app.route("/api/materiales/<int:mat_id>/definicion", methods=["PUT"])
def update_definicion(mat_id):
    d = request.json or {}
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE materiales SET definicion=%s WHERE id=%s",
                (d.get("definicion", ""), mat_id),
            )
            conn.commit()
    return ok()


@app.route("/api/materiales/<int:mat_id>/precio", methods=["POST"])
def add_precio(mat_id):
    d = request.json or {}
    proveedor = (d.get("proveedor") or "").strip()
    precio = d.get("precio_unitario")
    if not proveedor or precio is None:
        return err("Proveedor y precio_unitario son obligatorios")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO precios_materiales (material_id, proveedor, precio_unitario) "
                "VALUES (%s,%s,%s) "
                "ON CONFLICT (material_id, proveedor) DO UPDATE "
                "SET precio_unitario=%s, updated_at=NOW()",
                (mat_id, proveedor, precio, precio),
            )
            conn.commit()
    return ok()


# ─── Sync: descarga completa ──────────────────────────────────────────────────
@app.route("/api/sync/datos", methods=["GET"])
def sync_datos():
    """Devuelve todas las faenas activas con anotaciones, fotos y gastos."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT f.id, f.numero, f.cliente_id, f.intermediario_id, "
                "f.intermediario_nombre, f.direccion, f.tipo_trabajo, "
                "f.importe, f.fecha_inicio, f.archivada, "
                "COALESCE(c.nombre, '—') AS cliente_nombre "
                "FROM faenas f LEFT JOIN clientes c ON f.cliente_id = c.id "
                "WHERE f.archivada = 0 "
                "ORDER BY f.id DESC"
            )
            faenas = [dict(r) for r in cur.fetchall()]

            for f in faenas:
                fid = f["id"]
                cur.execute(
                    "SELECT id, tipo, contenido, fecha FROM anotaciones "
                    "WHERE faena_id=%s ORDER BY fecha DESC",
                    (fid,),
                )
                f["anotaciones"] = [dict(r) for r in cur.fetchall()]

                cur.execute(
                    "SELECT id, nombre, url, data, fecha FROM fotos "
                    "WHERE faena_id=%s ORDER BY fecha DESC",
                    (fid,),
                )
                f["fotos"] = [dict(r) for r in cur.fetchall()]
                f["gastos"] = []

    return ok(faenas)


# ─── Sync: subida en lote ─────────────────────────────────────────────────────
@app.route("/api/sync/anotaciones", methods=["POST"])
def sync_anotaciones():
    """Procesa un lote de anotaciones nuevas desde el móvil."""
    d = request.json or {}
    anotaciones = d.get("anotaciones", [])
    procesadas = 0
    with get_db() as conn:
        with conn.cursor() as cur:
            for a in anotaciones:
                faena_id = a.get("faena_id")
                if not faena_id or str(faena_id).startswith("TEMP"):
                    continue
                try:
                    cur.execute(
                        "INSERT INTO anotaciones (faena_id, tipo, contenido, fecha) "
                        "VALUES (%s,%s,%s,%s)",
                        (
                            int(faena_id),
                            a.get("tipo", "texto"),
                            a.get("contenido", ""),
                            a.get("fecha") or datetime.now().isoformat(),
                        ),
                    )
                    procesadas += 1
                except Exception:
                    pass
        conn.commit()
    return ok({"procesadas": procesadas})


@app.route("/api/sync/anotaciones-editar", methods=["POST"])
def sync_anotaciones_editar():
    d = request.json or {}
    ediciones = d.get("ediciones", [])
    with get_db() as conn:
        with conn.cursor() as cur:
            for e in ediciones:
                try:
                    cur.execute(
                        "UPDATE anotaciones SET tipo=%s, contenido=%s WHERE id=%s",
                        (e.get("tipo", "texto"), e.get("contenido", ""), int(e["id"])),
                    )
                except Exception:
                    pass
        conn.commit()
    return ok()


@app.route("/api/sync/anotaciones-eliminar", methods=["POST"])
def sync_anotaciones_eliminar():
    d = request.json or {}
    ids = d.get("ids", [])
    with get_db() as conn:
        with conn.cursor() as cur:
            for id_ in ids:
                try:
                    cur.execute(
                        "DELETE FROM anotaciones WHERE id=%s", (int(id_),)
                    )
                except Exception:
                    pass
        conn.commit()
    return ok()


@app.route("/api/sync/fotos", methods=["POST"])
def sync_fotos():
    d = request.json or {}
    faena_id = d.get("faena_id")
    if not faena_id or str(faena_id).startswith("TEMP"):
        return err("faena_id inválido o temporal")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO fotos (faena_id, nombre, data, fecha) "
                "VALUES (%s,%s,%s,%s) RETURNING id",
                (
                    int(faena_id),
                    d.get("nombre", "foto.jpg"),
                    d.get("data", ""),
                    datetime.now().isoformat(),
                ),
            )
            foto_id = cur.fetchone()["id"]
            conn.commit()
    return ok({"id": foto_id})


@app.route("/api/sync/tickets", methods=["POST"])
def sync_tickets():
    """Sincroniza tickets y actualiza el catálogo de materiales."""
    d = request.json or {}
    tickets = d.get("tickets", [])
    procesados = 0
    with get_db() as conn:
        with conn.cursor() as cur:
            for t in tickets:
                proveedor = t.get("proveedor", "")
                fecha_str = t.get("fecha") or date.today().isoformat()
                faena_id = t.get("faena_id")
                articulos = t.get("articulos", [])

                cur.execute(
                    "INSERT INTO tickets (proveedor, fecha, faena_id) "
                    "VALUES (%s,%s,%s) RETURNING id",
                    (
                        proveedor,
                        fecha_str,
                        int(faena_id) if faena_id else None,
                    ),
                )
                ticket_id = cur.fetchone()["id"]

                for art in articulos:
                    nombre = (art.get("nombre") or "").strip()
                    if not nombre:
                        continue
                    cur.execute(
                        "SELECT id FROM materiales WHERE LOWER(nombre)=LOWER(%s)",
                        (nombre,),
                    )
                    mat = cur.fetchone()
                    if mat:
                        mat_id = mat["id"]
                    else:
                        cur.execute(
                            "INSERT INTO materiales (nombre, unidad, categoria) "
                            "VALUES (%s,%s,%s) RETURNING id",
                            (nombre, art.get("unidad", "ud"), "Otros"),
                        )
                        mat_id = cur.fetchone()["id"]

                    if proveedor and art.get("precio_unitario"):
                        cur.execute(
                            "INSERT INTO precios_materiales "
                            "(material_id, proveedor, precio_unitario) "
                            "VALUES (%s,%s,%s) "
                            "ON CONFLICT (material_id, proveedor) DO UPDATE "
                            "SET precio_unitario=%s",
                            (
                                mat_id,
                                proveedor,
                                art["precio_unitario"],
                                art["precio_unitario"],
                            ),
                        )

                    cur.execute(
                        "INSERT INTO ticket_articulos "
                        "(ticket_id, material_id, nombre, unidad, cantidad, precio_unitario, total) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (
                            ticket_id,
                            mat_id,
                            nombre,
                            art.get("unidad", "ud"),
                            art.get("cantidad", 1),
                            art.get("precio_unitario", 0),
                            art.get("total", 0),
                        ),
                    )
                    procesados += 1
        conn.commit()
    return ok({"procesados": procesados})


@app.route("/api/sync/book", methods=["GET"])
def sync_book():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, faena_id, faena_numero, titulo, descripcion, data, fecha "
                "FROM book ORDER BY fecha DESC"
            )
            return ok(rows_to_list(cur.fetchall()))


@app.route("/api/book", methods=["POST"])
def add_book():
    d = request.json or {}
    with get_db() as conn:
        with conn.cursor() as cur:
            faena_id = d.get("faena_id")
            faena_numero = None
            if faena_id:
                cur.execute(
                    "SELECT numero FROM faenas WHERE id=%s", (faena_id,)
                )
                row = cur.fetchone()
                if row:
                    faena_numero = row["numero"]

            cur.execute(
                "INSERT INTO book (faena_id, faena_numero, titulo, descripcion, data) "
                "VALUES (%s,%s,%s,%s,%s) RETURNING id",
                (
                    faena_id,
                    faena_numero,
                    d.get("titulo", ""),
                    d.get("descripcion", ""),
                    d.get("data", ""),
                ),
            )
            book_id = cur.fetchone()["id"]
            conn.commit()
    return ok({"id": book_id})


# ─── Prompts ──────────────────────────────────────────────────────────────────
@app.route("/api/prompts/ticket", methods=["GET"])
def get_prompt_ticket():
    prompt = (
        "Analiza la imagen del ticket de compra y extrae todos los artículos.\n\n"
        "Devuelve ÚNICAMENTE un JSON válido con esta estructura (sin texto adicional):\n"
        '{\n'
        '  "proveedor": "nombre de la tienda",\n'
        '  "fecha": "YYYY-MM-DD",\n'
        '  "articulos": [\n'
        '    {\n'
        '      "nombre": "nombre del artículo",\n'
        '      "unidad": "ud",\n'
        '      "cantidad": 1,\n'
        '      "precio_unitario": 0.00,\n'
        '      "total": 0.00\n'
        '    }\n'
        '  ]\n'
        "}"
    )
    return ok({"prompt": prompt})


# ─── IA: procesar ticket con imagen ──────────────────────────────────────────
@app.route("/api/ia/procesar-ticket", methods=["POST"])
def ia_procesar_ticket():
    """Recibe una imagen base64 de un ticket y devuelve los artículos en JSON."""
    if not _gemini_model:
        return err(
            "IA no disponible. Configura GEMINI_API_KEY en el servidor.", 503
        )

    d = request.json or {}
    imagen = d.get("imagen", "")
    if not imagen:
        return err("El campo 'imagen' (base64) es obligatorio")

    # Eliminar el prefijo data URL si viene incluido
    imagen_b64 = imagen.split(",")[1] if "," in imagen else imagen

    prompt = (
        "Analiza este ticket de compra de materiales de construcción o carpintería.\n"
        "Extrae TODOS los artículos visibles.\n\n"
        "Devuelve ÚNICAMENTE un JSON válido (sin markdown, sin texto adicional):\n"
        '{\n'
        '  "proveedor": "nombre del establecimiento",\n'
        '  "fecha": "YYYY-MM-DD o null si no se ve",\n'
        '  "articulos": [\n'
        '    {\n'
        '      "nombre": "nombre del artículo",\n'
        '      "unidad": "ud/m/m2/kg/l",\n'
        '      "cantidad": 1,\n'
        '      "precio_unitario": 0.00,\n'
        '      "total": 0.00\n'
        '    }\n'
        '  ]\n'
        "}"
    )

    try:
        image_part = {
            "mime_type": "image/jpeg",
            "data": base64.b64decode(imagen_b64),
        }
        response = _gemini_model.generate_content([prompt, image_part])
        resultado = extract_json(response.text)

        # Guardar el ticket en la BD si viene con faena_id
        faena_id = d.get("faena_id")
        if resultado.get("articulos"):
            with get_db() as conn:
                _guardar_ticket(conn, resultado, faena_id)

        return ok(resultado)
    except json.JSONDecodeError as exc:
        logger.warning("Gemini JSON decode error: %s", exc)
        return err("La IA no devolvió JSON válido. Intenta de nuevo o usa el método manual.")
    except Exception as exc:
        return server_err(exc, "Error al procesar el ticket con IA")


# ─── IA: procesar texto libre ─────────────────────────────────────────────────
@app.route("/api/ia/procesar-texto", methods=["POST"])
def ia_procesar_texto():
    """Extrae materiales de un texto libre (lista de WhatsApp, email, etc.)."""
    if not _gemini_model:
        return err(
            "IA no disponible. Configura GEMINI_API_KEY en el servidor.", 503
        )

    d = request.json or {}
    texto = (d.get("texto") or "").strip()
    if not texto:
        return err("El campo 'texto' es obligatorio")

    prompt = (
        "Del siguiente texto, extrae una lista de materiales de carpintería "
        "o construcción.\n\n"
        "Devuelve ÚNICAMENTE un JSON válido (sin markdown, sin texto adicional):\n"
        "{\n"
        '  "proveedor": null,\n'
        '  "fecha": null,\n'
        '  "articulos": [\n'
        '    {\n'
        '      "nombre": "nombre del artículo",\n'
        '      "unidad": "ud",\n'
        '      "cantidad": 1,\n'
        '      "precio_unitario": 0.00,\n'
        '      "total": 0.00\n'
        '    }\n'
        "  ]\n"
        "}\n\n"
        f"Texto:\n{texto}"
    )

    try:
        response = _gemini_model.generate_content(prompt)
        resultado = extract_json(response.text)

        faena_id = d.get("faena_id")
        if resultado.get("articulos"):
            with get_db() as conn:
                _guardar_ticket(conn, resultado, faena_id)

        return ok({"articulos": resultado.get("articulos", [])})
    except json.JSONDecodeError:
        return err("La IA no pudo extraer materiales del texto")
    except Exception as exc:
        return server_err(exc, "Error al procesar el texto con IA")


# ─── IA: consulta en lenguaje natural ────────────────────────────────────────
@app.route("/api/ia/consulta", methods=["POST"])
def ia_consulta():
    """Responde preguntas sobre los datos en lenguaje natural."""
    if not _gemini_model:
        return err(
            "IA no disponible. Configura GEMINI_API_KEY en el servidor.", 503
        )

    d = request.json or {}
    pregunta = (d.get("pregunta") or "").strip()
    if not pregunta:
        return err("El campo 'pregunta' es obligatorio")

    contexto = d.get("contexto", {})
    faenas_json = json.dumps(
        contexto.get("faenas", []), ensure_ascii=False, default=_json_serial
    )[:4000]
    materiales_json = json.dumps(
        contexto.get("materiales", []), ensure_ascii=False, default=_json_serial
    )[:2000]
    clientes_json = json.dumps(
        contexto.get("clientes", []), ensure_ascii=False, default=_json_serial
    )[:1500]

    prompt = (
        "Eres un asistente para un carpintero autónomo. "
        "Tienes acceso a sus datos de trabajo.\n\n"
        f"FAENAS (trabajos):\n{faenas_json}\n\n"
        f"MATERIALES:\n{materiales_json}\n\n"
        f"CLIENTES:\n{clientes_json}\n\n"
        "Responde esta pregunta de forma concisa y útil en español:\n"
        f"{pregunta}\n\n"
        "Si los datos no tienen información suficiente para responder con exactitud, "
        "indícalo brevemente y proporciona lo que puedas."
    )

    try:
        response = _gemini_model.generate_content(prompt)
        return ok({"respuesta": response.text})
    except Exception as exc:
        return server_err(exc, "Error al consultar la IA")


# ─── Función auxiliar: guardar ticket en BD ───────────────────────────────────
def _guardar_ticket(conn, ticket_data, faena_id=None):
    """Inserta un ticket y sus artículos; actualiza el catálogo de materiales."""
    with conn.cursor() as cur:
        proveedor = ticket_data.get("proveedor") or ""
        fecha_str = ticket_data.get("fecha") or date.today().isoformat()
        articulos = ticket_data.get("articulos", [])

        cur.execute(
            "INSERT INTO tickets (proveedor, fecha, faena_id) "
            "VALUES (%s,%s,%s) RETURNING id",
            (proveedor, fecha_str, int(faena_id) if faena_id else None),
        )
        ticket_id = cur.fetchone()["id"]

        for art in articulos:
            nombre = (art.get("nombre") or "").strip()
            if not nombre:
                continue

            cur.execute(
                "SELECT id FROM materiales WHERE LOWER(nombre)=LOWER(%s)", (nombre,)
            )
            mat = cur.fetchone()
            if mat:
                mat_id = mat["id"]
            else:
                cur.execute(
                    "INSERT INTO materiales (nombre, unidad, categoria) "
                    "VALUES (%s,%s,%s) RETURNING id",
                    (nombre, art.get("unidad", "ud"), "Otros"),
                )
                mat_id = cur.fetchone()["id"]

            if proveedor and art.get("precio_unitario"):
                cur.execute(
                    "INSERT INTO precios_materiales "
                    "(material_id, proveedor, precio_unitario) "
                    "VALUES (%s,%s,%s) "
                    "ON CONFLICT (material_id, proveedor) DO UPDATE "
                    "SET precio_unitario=%s",
                    (
                        mat_id,
                        proveedor,
                        art["precio_unitario"],
                        art["precio_unitario"],
                    ),
                )

            cur.execute(
                "INSERT INTO ticket_articulos "
                "(ticket_id, material_id, nombre, unidad, cantidad, precio_unitario, total) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    ticket_id,
                    mat_id,
                    nombre,
                    art.get("unidad", "ud"),
                    art.get("cantidad", 1),
                    art.get("precio_unitario", 0),
                    art.get("total", 0),
                ),
            )
    conn.commit()


# ─── Arranque ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
