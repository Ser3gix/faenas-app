import socket
import os
import subprocess
import time
import re
import json
import base64
import urllib.request
import urllib.error
from flask import Flask, jsonify, request, send_from_directory, Response, stream_with_context
from flask_cors import CORS

import shutil
from config import HOST, PORT, CURSOR_PATH, CARPETA_RAIZ, APP_DIR
from database import (
    inicializar_db, get_connection,
    generar_numero_faena, crear_carpeta_faena,
    fila_a_dict, filas_a_lista
)

try:
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from PIL import Image, ImageFilter, ImageOps, ImageEnhance
except Exception:
    Image = None
    ImageFilter = None
    ImageOps = None
    ImageEnhance = None

try:
    import pytesseract
except Exception:
    pytesseract = None

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "180"))

if pytesseract is not None:
    posibles_tesseract = [
        shutil.which("tesseract"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for ruta_tesseract in posibles_tesseract:
        if ruta_tesseract and os.path.exists(ruta_tesseract):
            pytesseract.pytesseract.tesseract_cmd = ruta_tesseract
            break

app = Flask(
    __name__,
    static_folder=os.path.join(APP_DIR, "static"),
    template_folder=os.path.join(APP_DIR, "templates")
)
CORS(app, origins="*", allow_headers=["Content-Type"], supports_credentials=False)

@app.after_request
def after_request(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return response


def limpiar_data_b64(data_b64):
    if not data_b64:
        return ""
    if "," in data_b64:
        return data_b64.split(",", 1)[1]
    return data_b64


def _parse_numero(texto):
    if texto is None:
        return 0.0
    valor = str(texto).strip().replace(" ", "")
    if not valor:
        return 0.0
    if valor.count(",") and valor.count("."):
        if valor.rfind(",") > valor.rfind("."):
            valor = valor.replace(".", "").replace(",", ".")
        else:
            valor = valor.replace(",", "")
    else:
        valor = valor.replace(",", ".")
    try:
        return float(valor)
    except Exception:
        return 0.0
def ollama_disponible():
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status < 400
    except Exception:
        return False


def ollama_model_preferido():
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=4) as resp:
            datos = json.loads(resp.read().decode("utf-8"))
        modelos = [m.get("name") or m.get("model") for m in datos.get("models", []) if m.get("name") or m.get("model")]
        candidatos = [OLLAMA_MODEL, "llama3.2:3b", "carpintero:latest", "llama3.2:latest", "TinyLlama:latest"]
        for candidato in candidatos:
            if candidato in modelos:
                return candidato
        return modelos[0] if modelos else OLLAMA_MODEL
    except Exception:
        return OLLAMA_MODEL


def ollama_chat(messages, model=None, format_schema=None):
    payload = {
        "model": model or ollama_model_preferido(),
        "messages": messages,
        "stream": False,
        "options": {
            "num_predict": 128,
            "temperature": 0.2,
        },
    }
    if format_schema is not None:
        payload["format"] = format_schema

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def prompt_contexto_faena(faena_id):
    if not faena_id:
        return None
    conn = get_connection()
    try:
        faena = conn.execute(
            """
            SELECT f.*, c.nombre AS cliente_nombre, c.telefono AS cliente_telefono,
                   i.nombre AS intermediario_nombre
            FROM faenas f
            LEFT JOIN clientes c ON f.cliente_id = c.id
            LEFT JOIN intermediarios i ON f.intermediario_id = i.id
            WHERE f.id = ?
            """,
            (faena_id,)
        ).fetchone()
        if not faena:
            return None
        anotaciones = conn.execute(
            "SELECT * FROM anotaciones WHERE faena_id=? ORDER BY fecha DESC",
            (faena_id,)
        ).fetchall()
        gastos = conn.execute(
            "SELECT * FROM gastos_faena WHERE faena_id=? ORDER BY fecha DESC, id DESC",
            (faena_id,)
        ).fetchall()
    finally:
        conn.close()

    return {
        "faena": fila_a_dict(faena),
        "anotaciones": filas_a_lista(anotaciones),
        "gastos": filas_a_lista(gastos),
    }


def buscar_materiales_catalogo(descripcion):
    texto = (descripcion or "").strip().lower()
    if not texto:
        return [], []

    palabras = [p for p in re.split(r"[^\wáéíóúüñÁÉÍÓÚÜÑ]+", texto) if len(p) > 2]
    conn = get_connection()
    try:
        materiales = conn.execute(
            """
            SELECT m.id, m.nombre, m.unidad, m.categoria,
                   MIN(p.precio_unitario) AS precio_min,
                   (
                       SELECT p2.proveedor
                       FROM precios p2
                       WHERE p2.material_id = m.id
                       ORDER BY p2.precio_unitario ASC
                       LIMIT 1
                   ) AS proveedor_min
            FROM materiales m
            LEFT JOIN precios p ON p.material_id = m.id
            GROUP BY m.id
            ORDER BY m.categoria, m.nombre
            """
        ).fetchall()
    finally:
        conn.close()

    resultados = []
    vistos = set()
    for fila in materiales:
        nombre = (fila["nombre"] or "").strip()
        hay_match = any(p in nombre.lower() for p in palabras) or any(p in (fila["categoria"] or "").lower() for p in palabras)
        if hay_match:
            item = fila_a_dict(fila)
            item["cantidad_sugerida"] = 1
            resultados.append(item)
            vistos.add(nombre.lower())

    no_encontrados = [p for p in palabras if not any(p in nombre.lower() for nombre in vistos)]
    return resultados[:20], no_encontrados[:12]


# -------------------- RUTAS PRINCIPALES --------------------
@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(os.path.join(APP_DIR, "static"), filename)

@app.route("/")
@app.route("/index.html")
def index():
    return send_from_directory(os.path.join(APP_DIR, "templates"), "index.html")

@app.route("/movil")
def movil():
    return send_from_directory(os.path.join(APP_DIR, "templates"), "movil.html")

@app.route("/movil2")
def movil2():
    return send_from_directory(os.path.join(APP_DIR, "templates"), "movil2.html")

@app.route("/api/info/ip", methods=["GET"])
def get_ip():
    ips = []
    try:
        hostname = socket.gethostname()
        infos = socket.getaddrinfo(hostname, None)
        for info in infos:
            ip = info[4][0]
            if ":" not in ip and not ip.startswith("127.") and not ip.startswith("172."):
                ips.append(ip)
    except Exception:
        pass
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            if not ip.startswith("172."):
                ips.append(ip)
        except Exception:
            pass
    ip_final = ips[0] if ips else "127.0.0.1"
    return jsonify({"ok": True, "data": {"ip": ip_final, "url": f"http://{ip_final}:5000/movil", "todas": ips}})

# -------------------- INTERMEDIARIOS --------------------
@app.route("/api/intermediarios", methods=["GET"])
def get_intermediarios():
    conn = get_connection()
    filas = conn.execute("SELECT * FROM intermediarios ORDER BY id").fetchall()
    conn.close()
    return jsonify({"ok": True, "data": filas_a_lista(filas)})

@app.route("/api/intermediarios", methods=["POST"])
def crear_intermediario():
    datos = request.json
    nombre = datos.get("nombre", "").strip()
    if not nombre:
        return jsonify({"ok": False, "error": "El nombre es obligatorio"}), 400
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO intermediarios (nombre, telefono, email) VALUES (?, ?, ?)",
        (nombre, datos.get("telefono", ""), datos.get("email", ""))
    )
    conn.commit()
    nuevo_id = cursor.lastrowid
    conn.close()
    return jsonify({"ok": True, "data": {"id": nuevo_id, "nombre": nombre}})

@app.route("/api/intermediarios/<int:id>", methods=["PUT"])
def editar_intermediario(id):
    if id == 0:
        return jsonify({"ok": False, "error": "El intermediario 0 no se puede editar"}), 400
    datos = request.json
    conn = get_connection()
    conn.execute(
        "UPDATE intermediarios SET nombre=?, telefono=?, email=? WHERE id=?",
        (datos.get("nombre"), datos.get("telefono", ""), datos.get("email", ""), id)
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

# -------------------- CLIENTES --------------------
@app.route("/api/clientes", methods=["GET"])
def get_clientes():
    conn = get_connection()
    filas = conn.execute("""
        SELECT c.*, i.nombre AS intermediario_nombre
        FROM clientes c
        LEFT JOIN intermediarios i ON c.intermediario_id = i.id
        ORDER BY c.nombre
    """).fetchall()
    conn.close()
    return jsonify({"ok": True, "data": filas_a_lista(filas)})

@app.route("/api/clientes", methods=["POST"])
def crear_cliente():
    datos = request.json
    nombre = datos.get("nombre", "").strip()
    if not nombre:
        return jsonify({"ok": False, "error": "El nombre es obligatorio"}), 400
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO clientes (nombre, telefono, direccion, email, intermediario_id, notas) VALUES (?, ?, ?, ?, ?, ?)",
        (
            nombre,
            datos.get("telefono", ""),
            datos.get("direccion", ""),
            datos.get("email", ""),
            datos.get("intermediario_id", 0),
            datos.get("notas", "")
        )
    )
    conn.commit()
    nuevo_id = cursor.lastrowid
    conn.close()
    return jsonify({"ok": True, "data": {"id": nuevo_id, "nombre": nombre}})

@app.route("/api/clientes/<int:id>", methods=["PUT"])
def editar_cliente(id):
    datos = request.json
    conn = get_connection()
    conn.execute("""
        UPDATE clientes
        SET nombre=?, telefono=?, direccion=?, email=?, intermediario_id=?, notas=?
        WHERE id=?
    """, (
        datos.get("nombre"),
        datos.get("telefono", ""),
        datos.get("direccion", ""),
        datos.get("email", ""),
        datos.get("intermediario_id", 0),
        datos.get("notas", ""),
        id
    ))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

# -------------------- FAENAS --------------------
@app.route("/api/faenas", methods=["GET"])
def get_faenas():
    conn = get_connection()
    filas = conn.execute("""
        SELECT f.*, c.nombre AS cliente_nombre, i.nombre AS intermediario_nombre
        FROM faenas f
        LEFT JOIN clientes c ON f.cliente_id = c.id
        LEFT JOIN intermediarios i ON f.intermediario_id = i.id
        WHERE f.archivada = 0
        ORDER BY f.id DESC
    """).fetchall()
    conn.close()
    return jsonify({"ok": True, "data": filas_a_lista(filas)})

@app.route("/api/faenas/archivadas", methods=["GET"])
def get_faenas_archivadas():
    conn = get_connection()
    filas = conn.execute("""
        SELECT f.*, c.nombre AS cliente_nombre, i.nombre AS intermediario_nombre
        FROM faenas f
        LEFT JOIN clientes c ON f.cliente_id = c.id
        LEFT JOIN intermediarios i ON f.intermediario_id = i.id
        WHERE f.archivada = 1
        ORDER BY f.id DESC
    """).fetchall()
    conn.close()
    return jsonify({"ok": True, "data": filas_a_lista(filas)})

@app.route("/api/faenas/<int:id>", methods=["GET"])
def get_faena(id):
    conn = get_connection()
    fila = conn.execute("""
        SELECT f.*, c.nombre AS cliente_nombre, c.telefono AS cliente_telefono, i.nombre AS intermediario_nombre
        FROM faenas f
        LEFT JOIN clientes c ON f.cliente_id = c.id
        LEFT JOIN intermediarios i ON f.intermediario_id = i.id
        WHERE f.id = ?
    """, (id,)).fetchone()
    conn.close()
    if not fila:
        return jsonify({"ok": False, "error": "Faena no encontrada"}), 404
    return jsonify({"ok": True, "data": fila_a_dict(fila)})

@app.route("/api/faenas", methods=["POST"])
def crear_faena():
    datos = request.json
    cliente_id = datos.get("cliente_id")
    if not cliente_id:
        return jsonify({"ok": False, "error": "El cliente es obligatorio"}), 400
    conn = get_connection()
    cliente = conn.execute("SELECT nombre FROM clientes WHERE id=?", (cliente_id,)).fetchone()
    if not cliente:
        conn.close()
        return jsonify({"ok": False, "error": "Cliente no encontrado"}), 404
    intermediario_id = datos.get("intermediario_id", 0)
    numero = generar_numero_faena(intermediario_id, cliente_id)
    carpeta = crear_carpeta_faena(numero, cliente["nombre"])
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO faenas
            (numero, cliente_id, intermediario_id, direccion, tipo_trabajo, importe, fecha_inicio, carpeta)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        numero,
        cliente_id,
        intermediario_id,
        datos.get("direccion", ""),
        datos.get("tipo_trabajo", ""),
        datos.get("importe", 0),
        datos.get("fecha_inicio", ""),
        carpeta
    ))
    conn.commit()
    nuevo_id = cursor.lastrowid
    conn.close()
    return jsonify({"ok": True, "data": {"id": nuevo_id, "numero": numero, "carpeta": carpeta}})

@app.route("/api/faenas/<int:id>", methods=["PUT"])
def editar_faena(id):
    datos = request.json
    conn = get_connection()
    conn.execute("""
        UPDATE faenas
        SET direccion=?, tipo_trabajo=?, importe=?, fecha_inicio=?
        WHERE id=?
    """, (
        datos.get("direccion", ""),
        datos.get("tipo_trabajo", ""),
        datos.get("importe", 0),
        datos.get("fecha_inicio", ""),
        id
    ))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/faenas/<int:id>", methods=["DELETE"])
def eliminar_faena(id):
    conn = get_connection()
    conn.execute("DELETE FROM anotaciones WHERE faena_id=?", (id,))
    conn.execute("DELETE FROM gastos_faena WHERE faena_id=?", (id,))
    conn.execute("DELETE FROM fotos_faena WHERE faena_id=?", (id,))
    conn.execute("DELETE FROM faenas WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/faenas/<int:id>/archivar", methods=["POST"])
def archivar_faena(id):
    conn = get_connection()
    conn.execute("UPDATE faenas SET archivada=1 WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

# -------------------- ANOTACIONES --------------------
@app.route("/api/faenas/<int:id>/anotaciones", methods=["GET"])
def get_anotaciones(id):
    conn = get_connection()
    filas = conn.execute(
        "SELECT * FROM anotaciones WHERE faena_id=? ORDER BY fecha DESC", (id,)
    ).fetchall()
    conn.close()
    return jsonify({"ok": True, "data": filas_a_lista(filas)})

@app.route("/api/faenas/<int:id>/anotaciones", methods=["POST"])
def crear_anotacion(id):
    datos = request.json
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO anotaciones (faena_id, tipo, contenido) VALUES (?, ?, ?)",
        (id, datos.get("tipo", "texto"), datos.get("contenido", ""))
    )
    conn.commit()
    nuevo_id = cursor.lastrowid
    conn.close()
    return jsonify({"ok": True, "data": {"id": nuevo_id}})

@app.route("/api/anotaciones/<int:id>", methods=["DELETE"])
def eliminar_anotacion(id):
    conn = get_connection()
    conn.execute("DELETE FROM anotaciones WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/anotaciones/<int:id>", methods=["PUT"])
def editar_anotacion(id):
    datos = request.json
    conn = get_connection()
    conn.execute(
        "UPDATE anotaciones SET tipo=?, contenido=? WHERE id=?",
        (datos.get("tipo", "texto"), datos.get("contenido", ""), id)
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

# -------------------- MATERIALES Y PRECIOS --------------------
@app.route("/api/materiales", methods=["GET"])
def get_materiales():
    conn = get_connection()
    materiales = conn.execute(
        "SELECT * FROM materiales ORDER BY categoria, nombre"
    ).fetchall()
    resultado = []
    for m in materiales:
        mat = fila_a_dict(m)
        precios = conn.execute(
            "SELECT * FROM precios WHERE material_id=? ORDER BY precio_unitario",
            (m["id"],)
        ).fetchall()
        mat["precios"] = filas_a_lista(precios)
        resultado.append(mat)
    conn.close()
    return jsonify({"ok": True, "data": resultado})

@app.route("/api/materiales", methods=["POST"])
def crear_material():
    datos = request.json
    nombre = datos.get("nombre", "").strip()
    if not nombre:
        return jsonify({"ok": False, "error": "El nombre es obligatorio"}), 400
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO materiales (nombre, unidad, categoria) VALUES (?, ?, ?)",
        (nombre, datos.get("unidad", "ud"), datos.get("categoria", "Herraje"))
    )
    conn.commit()
    nuevo_id = cursor.lastrowid
    conn.close()
    return jsonify({"ok": True, "data": {"id": nuevo_id}})
@app.route("/api/materiales/<int:id>/precio", methods=["POST"])
def actualizar_precio(id):
    datos = request.json
    proveedor = datos.get("proveedor", "").strip()
    precio = datos.get("precio_unitario")
    if not proveedor or precio is None:
        return jsonify({"ok": False, "error": "Proveedor y precio son obligatorios"}), 400
    conn = get_connection()
    conn.execute("""
        INSERT INTO precios (material_id, proveedor, precio_unitario, fecha_actualizacion)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(material_id, proveedor)
        DO UPDATE SET precio_unitario=excluded.precio_unitario,
                      fecha_actualizacion=excluded.fecha_actualizacion
    """, (id, proveedor, precio))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

# -------------------- GASTOS --------------------
def separar_conceptos_faena(filas):
    presupuesto = []
    gastos = []
    for fila in filas:
        concepto = fila_a_dict(fila)
        if str(concepto.get("tipo", "")).strip().lower() == "presupuesto":
            presupuesto.append(concepto)
        else:
            gastos.append(concepto)
    return presupuesto, gastos

@app.route("/api/faenas/<int:id>/gastos", methods=["GET"])
def get_gastos(id):
    conn = get_connection()
    filas = conn.execute(
        "SELECT * FROM gastos_faena WHERE faena_id=? ORDER BY fecha DESC", (id,)
    ).fetchall()
    conn.close()
    return jsonify({"ok": True, "data": filas_a_lista(filas)})

@app.route("/api/faenas/<int:id>/conceptos", methods=["GET"])
def get_conceptos_faena(id):
    conn = get_connection()
    faena = conn.execute("SELECT carpeta FROM faenas WHERE id=?", (id,)).fetchone()
    presupuesto = asegurar_presupuesto_editable(conn, id, faena["carpeta"] if faena else None)
    try:
        gastos = conn.execute(
            "SELECT * FROM gastos_faena WHERE faena_id=? AND LOWER(COALESCE(tipo,''))<>'presupuesto' ORDER BY fecha DESC, id DESC", (id,)
        ).fetchall()
    except Exception:
        gastos = []
    conn.close()
    return jsonify({"ok": True, "data": {"presupuesto": presupuesto, "gastos": filas_a_lista(gastos)}})

@app.route("/api/faenas/<int:id>/gastos", methods=["POST"])
def crear_gasto(id):
    datos = request.json
    cantidad = datos.get("cantidad", 1)
    precio_unitario = datos.get("precio_unitario", 0)
    total = cantidad * precio_unitario
    ticket_foto = datos.get("ticket_foto", "")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO gastos_faena
            (faena_id, tipo, descripcion, cantidad, precio_unitario, total, ticket_foto)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        id,
        datos.get("tipo", "otro"),
        datos.get("descripcion", ""),
        cantidad,
        precio_unitario,
        total,
        ticket_foto
    ))
    conn.commit()
    nuevo_id = cursor.lastrowid
    conn.close()
    return jsonify({"ok": True, "data": {"id": nuevo_id, "total": total}})

@app.route("/api/gastos/<int:id>", methods=["DELETE"])
def eliminar_gasto(id):
    conn = get_connection()
    conn.execute("DELETE FROM gastos_faena WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/gastos/<int:id>", methods=["PUT"])
def editar_gasto(id):
    datos = request.json
    cantidad = datos.get("cantidad", 1)
    precio_unitario = datos.get("precio_unitario", 0)
    total = cantidad * precio_unitario
    conn = get_connection()
    conn.execute("""
        UPDATE gastos_faena
        SET tipo=?, descripcion=?, cantidad=?, precio_unitario=?, total=?
        WHERE id=?
    """, (
        datos.get("tipo", "otro"),
        datos.get("descripcion", ""),
        cantidad,
        precio_unitario,
        total,
        id
    ))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "data": {"id": id, "total": total}})

def sincronizar_importe_faena(conn, faena_id):
    fila = conn.execute(
        "SELECT COALESCE(SUM(total), 0) AS total FROM presupuestos_faena WHERE faena_id=?",
        (faena_id,)
    ).fetchone()
    total = float(fila["total"] or 0)
    conn.execute("UPDATE faenas SET importe=? WHERE id=?", (total, faena_id))
    return total

@app.route("/api/faenas/<int:id>/presupuesto/item", methods=["POST"])
def crear_presupuesto_item(id):
    datos = request.json
    cantidad = float(datos.get("cantidad", 1) or 1)
    precio_unitario = float(datos.get("precio_unitario", 0) or 0)
    total = cantidad * precio_unitario
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO presupuestos_faena
            (faena_id, tipo, descripcion, cantidad, precio_unitario, total)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        id,
        datos.get("tipo", "material"),
        datos.get("descripcion", ""),
        cantidad,
        precio_unitario,
        total,
    ))
    total_faena = sincronizar_importe_faena(conn, id)
    conn.commit()
    nuevo_id = cursor.lastrowid
    conn.close()
    return jsonify({"ok": True, "data": {"id": nuevo_id, "total": total, "importe": total_faena}})

@app.route("/api/presupuestos/<int:id>", methods=["PUT"])
def editar_presupuesto_item(id):
    datos = request.json
    cantidad = float(datos.get("cantidad", 1) or 1)
    precio_unitario = float(datos.get("precio_unitario", 0) or 0)
    total = cantidad * precio_unitario
    conn = get_connection()
    fila = conn.execute("SELECT faena_id FROM presupuestos_faena WHERE id=?", (id,)).fetchone()
    cursor = conn.execute("""
        UPDATE presupuestos_faena
        SET tipo=?, descripcion=?, cantidad=?, precio_unitario=?, total=?
        WHERE id=?
    """, (
        datos.get("tipo", "material"),
        datos.get("descripcion", ""),
        cantidad,
        precio_unitario,
        total,
        id,
    ))
    total_faena = sincronizar_importe_faena(conn, fila["faena_id"]) if fila else 0
    conn.commit()
    conn.close()
    if cursor.rowcount == 0:
        return jsonify({"ok": False, "error": "Partida de presupuesto no encontrada"}), 404
    return jsonify({"ok": True, "data": {"id": id, "total": total, "importe": total_faena}})

@app.route("/api/presupuestos/<int:id>", methods=["DELETE"])
def eliminar_presupuesto_item(id):
    conn = get_connection()
    fila = conn.execute("SELECT faena_id FROM presupuestos_faena WHERE id=?", (id,)).fetchone()
    cursor = conn.execute("DELETE FROM presupuestos_faena WHERE id=?", (id,))
    total_faena = sincronizar_importe_faena(conn, fila["faena_id"]) if fila else 0
    conn.commit()
    conn.close()
    if cursor.rowcount == 0:
        return jsonify({"ok": False, "error": "Partida de presupuesto no encontrada"}), 404
    return jsonify({"ok": True, "data": {"importe": total_faena}})

# -------------------- PROMPTS --------------------
@app.route("/api/prompts/ticket", methods=["GET"])
def prompt_ticket():
    prompt = """Analiza la imagen del ticket o factura de compra que te adjunto.
Extrae todos los artículos y devuelve ÚNICAMENTE el siguiente JSON, sin texto adicional antes ni después:

{
  "proveedor": "Nombre del establecimiento",
  "fecha": "YYYY-MM-DD",
  "articulos": [
    {
      "nombre": "Nombre del artículo",
      "cantidad": 1,
      "precio_unitario": 0.00,
      "total": 0.00,
      "unidad": "ud"
    }
  ],
  "total_ticket": 0.00
}

Si no puedes leer algún dato con claridad, usa null para ese campo.
Las unidades pueden ser: ud (unidades), ml (mililitros), kg (kilogramos), caja, m2 (metro cuadrado), litro."""
    return jsonify({"ok": True, "data": {"prompt": prompt}})


@app.route("/api/prompts/materiales", methods=["GET"])
def prompt_materiales():
    conn = get_connection()
    try:
        materiales = conn.execute(
            """
            SELECT m.nombre, m.unidad, m.categoria,
                   COALESCE(MIN(p.precio_unitario), 0) AS precio_min,
                   COALESCE(MAX(p.precio_unitario), 0) AS precio_max
            FROM materiales m
            LEFT JOIN precios p ON p.material_id = m.id
            GROUP BY m.id
            ORDER BY m.categoria, m.nombre
            """
        ).fetchall()
    finally:
        conn.close()

    lineas = []
    for fila in materiales[:200]:
        lineas.append(
            f"- {fila['nombre']} | unidad: {fila['unidad']} | categoria: {fila['categoria']} | precio_min: {float(fila['precio_min'] or 0):.2f} | precio_max: {float(fila['precio_max'] or 0):.2f}"
        )

        catalogo = "\n".join(lineas) or "Sin materiales guardados todavía."
        prompt = f"""Actualiza los precios de estos materiales de carpintería usando el JSON que te pegue el usuario.
Devuelve SOLO JSON válido con esta estructura:

{{
    "actualizaciones": [
        {{
            "nombre": "Nombre del material",
            "proveedor": "Nombre del proveedor",
            "precio_unitario": 0.00,
            "unidad": "ud"
        }}
    ]
}}

Catálogo actual:
---
{catalogo}
---"""

    return jsonify({"ok": True, "data": {"prompt": prompt}})


@app.route("/api/prompts/faena/<int:id>", methods=["GET"])
def prompt_faena(id):
    contexto = prompt_contexto_faena(id)
    if not contexto:
        return jsonify({"ok": False, "error": "Faena no encontrada"}), 404

    faena = contexto["faena"]
    anotaciones = contexto["anotaciones"]
    gastos = contexto["gastos"]

    prompt = f"""Resume y analiza esta faena de carpintería.
Devuélveme una respuesta clara, práctica y en español.

Datos de la faena:
- Número: {faena.get('numero', '')}
- Cliente: {faena.get('cliente_nombre', '')}
- Intermediario: {faena.get('intermediario_nombre', '')}
- Dirección: {faena.get('direccion', '')}
- Tipo de trabajo: {faena.get('tipo_trabajo', '')}
- Importe: {float(faena.get('importe') or 0):.2f} €

Anotaciones:
{json.dumps(anotaciones, ensure_ascii=False, indent=2)}

Gastos:
{json.dumps(gastos, ensure_ascii=False, indent=2)}"""

    return jsonify({"ok": True, "data": {"prompt": prompt}})


@app.route("/api/ollama/estado", methods=["GET"])
def ollama_estado():
    return jsonify({"ok": True, "data": {"disponible": ollama_disponible(), "modelo": ollama_model_preferido(), "url": OLLAMA_URL}})


@app.route("/api/ollama/buscar-materiales", methods=["POST"])
def ollama_buscar_materiales():
    datos = request.json or {}
    descripcion = (datos.get("descripcion") or "").strip()
    if not descripcion:
        return jsonify({"ok": False, "error": "Falta la descripción"}), 400

    resultados, no_encontrados = buscar_materiales_catalogo(descripcion)
    return jsonify({"ok": True, "data": {"materiales": resultados, "no_encontrados": no_encontrados}})


@app.route("/api/ollama/consulta", methods=["POST"])
def ollama_consulta():
    datos = request.json or {}
    pregunta = (datos.get("pregunta") or "").strip()
    faena_id = datos.get("faena_id")
    if not pregunta:
        return jsonify({"ok": False, "error": "Falta la pregunta"}), 400

    contexto = prompt_contexto_faena(faena_id) if faena_id else None
    mensajes = [
        {
            "role": "system",
            "content": "Eres un asistente experto en gestión de faenas de carpintería. Responde en español, con respuestas útiles y concretas.",
        }
    ]
    if contexto:
        mensajes.append({
            "role": "system",
            "content": "Contexto de la faena: " + json.dumps(contexto, ensure_ascii=False),
        })
    mensajes.append({"role": "user", "content": pregunta})

    if not ollama_disponible():
        return jsonify({"ok": False, "error": "Ollama no está disponible en el equipo"}), 503

    try:
        respuesta = ollama_chat(mensajes)
        texto = ((respuesta.get("message") or {}).get("content") or "").strip()
        if not texto:
            texto = "Ollama respondió sin contenido."
        return jsonify({"ok": True, "data": {"respuesta": texto}})
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "ignore") if hasattr(e, "read") else ""
        return jsonify({"ok": False, "error": f"Error de Ollama: {e.reason or str(e)}", "detalle": detalle}), 502
    except Exception as e:
        return jsonify({"ok": False, "error": f"Error de Ollama: {str(e)}"}), 502

# -------------------- SINCRONIZACIÓN WiFi --------------------
@app.route("/api/sync/estado", methods=["GET"])
def sync_estado():
    return jsonify({"ok": True, "data": {"estado": "disponible"}})

@app.route("/api/sync/datos", methods=["GET"])
def sync_datos():
    conn = get_connection()
    faenas = conn.execute("""
        SELECT f.*, c.nombre AS cliente_nombre, c.telefono AS cliente_telefono
        FROM faenas f
        LEFT JOIN clientes c ON f.cliente_id = c.id
        WHERE f.archivada = 0
        ORDER BY f.id DESC
    """).fetchall()
    resultado = []
    for f in faenas:
        faena = fila_a_dict(f)
        anotaciones = conn.execute(
            "SELECT * FROM anotaciones WHERE faena_id=? ORDER BY fecha DESC",
            (f["id"],)
        ).fetchall()
        faena["anotaciones"] = filas_a_lista(anotaciones)
        presupuesto_lista = asegurar_presupuesto_editable(conn, f["id"], f["carpeta"])
        if presupuesto_lista:
            faena["importe"] = sum(float(p.get("total", 0) or 0) for p in presupuesto_lista)
        try:
            gastos = conn.execute(
                "SELECT * FROM gastos_faena WHERE faena_id=? AND LOWER(COALESCE(tipo,''))<>'presupuesto' ORDER BY fecha DESC, id DESC",
                (f["id"],)
            ).fetchall()
            gastos_lista = filas_a_lista(gastos)
        except Exception:
            gastos_lista = []
        faena["presupuesto"] = presupuesto_lista
        faena["gastos"] = gastos_lista
        resultado.append(faena)
    conn.close()
    return jsonify({"ok": True, "data": resultado})

@app.route("/api/sync/anotaciones", methods=["POST"])
def sync_anotaciones():
    datos = request.json
    anotaciones = datos.get("anotaciones", [])
    conn = get_connection()
    insertadas = 0
    for a in anotaciones:
        try:
            conn.execute(
                "INSERT INTO anotaciones (faena_id, tipo, contenido, fecha) VALUES (?, ?, ?, ?)",
                (a["faena_id"], a.get("tipo", "texto"), a.get("contenido", ""), a.get("fecha", ""))
            )
            insertadas += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "data": {"insertadas": insertadas}})

@app.route("/api/sync/anotaciones-editar", methods=["POST"])
def sync_anotaciones_editar():
    datos = request.json
    ediciones = datos.get("ediciones", [])
    conn = get_connection()
    actualizadas = 0
    for e in ediciones:
        try:
            conn.execute(
                "UPDATE anotaciones SET tipo=?, contenido=? WHERE id=?",
                (e.get("tipo", "texto"), e.get("contenido", ""), e["id"])
            )
            actualizadas += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "data": {"actualizadas": actualizadas}})

@app.route("/api/sync/anotaciones-eliminar", methods=["POST"])
def sync_anotaciones_eliminar():
    datos = request.json
    ids = datos.get("ids", [])
    conn = get_connection()
    eliminadas = 0
    for id_ in ids:
        try:
            conn.execute("DELETE FROM anotaciones WHERE id=?", (id_,))
            eliminadas += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "data": {"eliminadas": eliminadas}})

@app.route("/api/sync/gastos", methods=["POST"])
@app.route("/sync/gastos", methods=["POST"])
def sync_gastos():
    datos = request.json
    operaciones = datos.get("operaciones", [])
    conn = get_connection()
    creados = 0
    actualizados = 0
    eliminados = 0
    creados_detalle = []
    for op in operaciones:
        try:
            tipo_op = op.get("op")
            if tipo_op == "create":
                cantidad = op.get("cantidad", 1)
                precio_unitario = op.get("precio_unitario", 0)
                total = cantidad * precio_unitario
                cursor = conn.execute(
                    "INSERT INTO gastos_faena (faena_id, tipo, descripcion, cantidad, precio_unitario, total, ticket_foto) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (op.get("faena_id"), op.get("tipo", "gasto"), op.get("descripcion", ""), cantidad, precio_unitario, total, op.get("ticket_foto", ""))
                )
                gasto_id = cursor.lastrowid
                creados_detalle.append({"temp_id": op.get("id"), "id": gasto_id, "faena_id": op.get("faena_id")})
                creados += 1
            elif tipo_op == "update":
                gasto_id = op.get("id")
                if str(gasto_id).startswith("temp_"):
                    cantidad = op.get("cantidad", 1)
                    precio_unitario = op.get("precio_unitario", 0)
                    total = cantidad * precio_unitario
                    cursor = conn.execute(
                        "INSERT INTO gastos_faena (faena_id, tipo, descripcion, cantidad, precio_unitario, total, ticket_foto) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (op.get("faena_id"), op.get("tipo", "gasto"), op.get("descripcion", ""), cantidad, precio_unitario, total, op.get("ticket_foto", ""))
                    )
                    nuevo_id = cursor.lastrowid
                    creados_detalle.append({"temp_id": gasto_id, "id": nuevo_id, "faena_id": op.get("faena_id")})
                    creados += 1
                else:
                    cantidad = op.get("cantidad", 1)
                    precio_unitario = op.get("precio_unitario", 0)
                    total = cantidad * precio_unitario
                    cursor = conn.execute(
                        "UPDATE gastos_faena SET tipo=?, descripcion=?, cantidad=?, precio_unitario=?, total=? WHERE id=?",
                        (op.get("tipo", "gasto"), op.get("descripcion", ""), cantidad, precio_unitario, total, gasto_id)
                    )
                    actualizados += cursor.rowcount
            elif tipo_op == "delete":
                gasto_id = op.get("id")
                if gasto_id and not str(gasto_id).startswith("temp_"):
                    cursor = conn.execute("DELETE FROM gastos_faena WHERE id=?", (gasto_id,))
                    eliminados += cursor.rowcount
        except Exception:
            pass
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "data": {"creados": creados, "actualizados": actualizados, "eliminados": eliminados, "creados_detalle": creados_detalle}})

@app.route("/api/sync/fotos", methods=["POST"])
def sync_fotos():
    import base64
    datos = request.json
    faena_id = datos.get("faena_id")
    nombre   = datos.get("nombre") or f"foto_{int(time.time())}.jpg"
    data_b64 = datos.get("data", "")
    if not faena_id or not data_b64:
        return jsonify({"ok": False, "error": "Faltan datos"}), 400
    conn = get_connection()
    faena = conn.execute("SELECT carpeta FROM faenas WHERE id=?", (faena_id,)).fetchone()
    conn.close()
    if not faena or not faena["carpeta"]:
        return jsonify({"ok": False, "error": "Faena o carpeta no encontrada"}), 404
    carpeta_fotos = os.path.join(faena["carpeta"], "fotos")
    os.makedirs(carpeta_fotos, exist_ok=True)
    if "," in data_b64:
        data_b64 = data_b64.split(",")[1]
    img_bytes = base64.b64decode(data_b64)
    ruta = os.path.join(carpeta_fotos, nombre)
    with open(ruta, "wb") as f:
        f.write(img_bytes)
    return jsonify({"ok": True, "data": {"ruta": ruta, "nombre": nombre}})

@app.route("/api/sync/book", methods=["GET"])
def sync_book():
    import base64
    conn = get_connection()
    filas = conn.execute("""
        SELECT b.*, f.numero AS faena_numero, c.nombre AS cliente_nombre
        FROM book_fotos b
        LEFT JOIN faenas f ON b.faena_id = f.id
        LEFT JOIN clientes c ON f.cliente_id = c.id
        ORDER BY b.orden ASC, b.id DESC
    """).fetchall()
    resultado = []
    for fila in filas:
        item = fila_a_dict(fila)
        ruta = item.get("ruta_foto", "")
        if ruta and os.path.exists(ruta):
            try:
                with open(ruta, "rb") as f:
                    item["data"] = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
            except Exception as e:
                item["data"] = ""
                print(f"Error leyendo foto {ruta}: {e}")
        else:
            item["data"] = ""
        resultado.append(item)
    conn.close()
    return jsonify({"ok": True, "data": resultado})

# -------------------- FOTOS DE FAENA (PC) --------------------
@app.route("/api/faenas/<int:id>/fotos", methods=["GET"])
def listar_fotos(id):
    import base64
    conn = get_connection()
    faena = conn.execute("SELECT carpeta FROM faenas WHERE id=?", (id,)).fetchone()
    conn.close()
    if not faena or not faena["carpeta"]:
        return jsonify({"ok": False, "error": "Faena no encontrada"}), 404
    carpeta_fotos = os.path.join(faena["carpeta"], "fotos")
    if not os.path.exists(carpeta_fotos):
        return jsonify({"ok": True, "data": []})
    fotos = []
    extensiones = {".jpg", ".jpeg", ".png", ".webp"}
    for nombre in sorted(os.listdir(carpeta_fotos)):
        if os.path.splitext(nombre)[1].lower() in extensiones:
            ruta = os.path.join(carpeta_fotos, nombre)
            with open(ruta, "rb") as f:
                data = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
            fotos.append({"nombre": nombre, "ruta": ruta, "data": data})
    return jsonify({"ok": True, "data": fotos})

@app.route("/api/faenas/<int:id>/fotos/<path:nombre>", methods=["DELETE"])
def eliminar_foto(id, nombre):
    conn = get_connection()
    faena = conn.execute("SELECT carpeta FROM faenas WHERE id=?", (id,)).fetchone()
    conn.close()
    if not faena or not faena["carpeta"]:
        return jsonify({"ok": False, "error": "Faena no encontrada"}), 404
    ruta = os.path.join(faena["carpeta"], "fotos", nombre)
    if not os.path.exists(ruta):
        return jsonify({"ok": False, "error": "Foto no encontrada"}), 404
    os.remove(ruta)
    return jsonify({"ok": True})

@app.route("/api/faenas/<int:id>/fotos/carpeta", methods=["POST"])
def abrir_carpeta_fotos(id):
    conn = get_connection()
    faena = conn.execute("SELECT carpeta FROM faenas WHERE id=?", (id,)).fetchone()
    conn.close()
    if not faena or not faena["carpeta"]:
        return jsonify({"ok": False, "error": "Faena no encontrada"}), 404
    carpeta_fotos = os.path.join(faena["carpeta"], "fotos")
    os.makedirs(carpeta_fotos, exist_ok=True)
    subprocess.Popen(["explorer", carpeta_fotos])
    return jsonify({"ok": True})

# -------------------- DOCUMENTOS --------------------
@app.route("/api/faenas/<int:id>/documentos", methods=["GET"])
def listar_documentos(id):
    conn = get_connection()
    faena = conn.execute("SELECT carpeta FROM faenas WHERE id=?", (id,)).fetchone()
    conn.close()
    if not faena or not faena["carpeta"]:
        return jsonify({"ok": False, "error": "Faena no encontrada"}), 404
    carpeta_docs = os.path.join(faena["carpeta"], "Documentos")
    os.makedirs(carpeta_docs, exist_ok=True)
    archivos = []
    for nombre in sorted(os.listdir(carpeta_docs)):
        ruta = os.path.join(carpeta_docs, nombre)
        if os.path.isfile(ruta):
            stat = os.stat(ruta)
            archivos.append({
                "nombre": nombre,
                "ruta": ruta,
                "tamaño": stat.st_size,
                "fecha": stat.st_mtime,
                "extension": os.path.splitext(nombre)[1].lower()
            })
    return jsonify({"ok": True, "data": archivos})

@app.route("/api/faenas/<int:id>/documentos", methods=["POST"])
def subir_documento(id):
    import shutil
    import tkinter as tk
    from tkinter import filedialog
    conn = get_connection()
    faena = conn.execute("SELECT carpeta FROM faenas WHERE id=?", (id,)).fetchone()
    conn.close()
    if not faena or not faena["carpeta"]:
        return jsonify({"ok": False, "error": "Faena no encontrada"}), 404
    carpeta_docs = os.path.join(faena["carpeta"], "Documentos")
    os.makedirs(carpeta_docs, exist_ok=True)
    root = tk.Tk()
    root.withdraw()
    rutas = filedialog.askopenfilenames(
        initialdir=os.path.expanduser("~"),
        title="Selecciona archivos para añadir a Documentos"
    )
    root.destroy()
    if not rutas:
        return jsonify({"ok": False, "error": "No se seleccionaron archivos"})
    copiados = []
    for ruta in rutas:
        nombre = os.path.basename(ruta)
        destino = os.path.join(carpeta_docs, nombre)
        shutil.copy2(ruta, destino)
        copiados.append(nombre)
    return jsonify({"ok": True, "data": {"copiados": copiados}})

@app.route("/api/faenas/<int:id>/documentos/<path:nombre>", methods=["DELETE"])
def eliminar_documento(id, nombre):
    conn = get_connection()
    faena = conn.execute("SELECT carpeta FROM faenas WHERE id=?", (id,)).fetchone()
    conn.close()
    if not faena or not faena["carpeta"]:
        return jsonify({"ok": False, "error": "Faena no encontrada"}), 404
    ruta = os.path.join(faena["carpeta"], "Documentos", nombre)
    if not os.path.exists(ruta):
        return jsonify({"ok": False, "error": "Archivo no encontrado"}), 404
    os.remove(ruta)
    return jsonify({"ok": True})

@app.route("/api/faenas/<int:id>/documentos/<path:nombre>/abrir", methods=["POST"])
def abrir_documento(id, nombre):
    conn = get_connection()
    faena = conn.execute("SELECT carpeta FROM faenas WHERE id=?", (id,)).fetchone()
    conn.close()
    if not faena or not faena["carpeta"]:
        return jsonify({"ok": False, "error": "Faena no encontrada"}), 404
    ruta = os.path.join(faena["carpeta"], "Documentos", nombre)
    if not os.path.exists(ruta):
        return jsonify({"ok": False, "error": "Archivo no encontrado"}), 404
    try:
        subprocess.Popen([CURSOR_PATH, ruta])
    except FileNotFoundError:
        os.startfile(ruta)
    return jsonify({"ok": True})

@app.route("/api/faenas/<int:id>/documentos/carpeta", methods=["POST"])
def abrir_carpeta_documentos(id):
    conn = get_connection()
    faena = conn.execute("SELECT carpeta FROM faenas WHERE id=?", (id,)).fetchone()
    conn.close()
    if not faena or not faena["carpeta"]:
        return jsonify({"ok": False, "error": "Faena no encontrada"}), 404
    carpeta_docs = os.path.join(faena["carpeta"], "Documentos")
    os.makedirs(carpeta_docs, exist_ok=True)
    subprocess.Popen(["explorer", carpeta_docs])
    return jsonify({"ok": True})

# -------------------- CURSOR --------------------
@app.route("/api/cursor/abrir", methods=["POST"])
def abrir_en_cursor():
    datos = request.json
    carpeta = datos.get("carpeta", "")
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    ruta_archivo = filedialog.askopenfilename(
        initialdir=carpeta if os.path.exists(carpeta) else "/",
        title="Selecciona el archivo para abrir en Cursor"
    )
    root.destroy()
    if not ruta_archivo:
        return jsonify({"ok": False, "error": "No se seleccionó ningún archivo"})
    try:
        subprocess.Popen([CURSOR_PATH, ruta_archivo])
        return jsonify({"ok": True, "data": {"archivo": ruta_archivo}})
    except FileNotFoundError:
        return jsonify({
            "ok": False,
            "error": f"No se encontró Cursor en '{CURSOR_PATH}'. Edita CURSOR_PATH en config.py"
        }), 500

# -------------------- POLYBOARD --------------------
@app.route("/api/polyboard/procesar", methods=["POST"])
def polyboard_procesar():
    datos = request.json
    ruta_txt = datos.get("ruta_txt", "")
    if not ruta_txt:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        ruta_txt = filedialog.askopenfilename(
            initialdir=CARPETA_RAIZ,
            title="Selecciona el TXT de PolyBoard",
            filetypes=[("Archivos de texto", "*.txt"), ("Todos", "*.*")]
        )
        root.destroy()
    if not ruta_txt:
        return jsonify({"ok": False, "error": "No se seleccionó ningún archivo"})
    try:
        from polyboard import leer_txt_polyboard
        piezas = leer_txt_polyboard(ruta_txt)
        return jsonify({"ok": True, "data": {"piezas": piezas, "ruta": ruta_txt}})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Error al leer el archivo: {str(e)}"}), 500

@app.route("/api/polyboard/pdf", methods=["POST"])
def polyboard_pdf():
    import tempfile
    from flask import send_file
    datos = request.json
    piezas = datos.get("piezas", {})
    faena_id = datos.get("faena_id")
    excluir = datos.get("excluir_materiales", ["Separacion"])
    piezas_filtradas = {k: v for k, v in piezas.items() if k not in excluir}
    if not piezas_filtradas:
        return jsonify({"ok": False, "error": "No hay piezas para generar el pedido"}), 400
    cliente_nombre = "Cliente"
    numero_faena = "—"
    if faena_id:
        conn = get_connection()
        faena = conn.execute("""
            SELECT f.numero, c.nombre AS cliente_nombre
            FROM faenas f LEFT JOIN clientes c ON f.cliente_id = c.id
            WHERE f.id = ?
        """, (faena_id,)).fetchone()
        conn.close()
        if faena:
            numero_faena = faena["numero"]
            cliente_nombre = faena["cliente_nombre"]
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.close()
    try:
        from polyboard import generar_pdf_pedido
        generar_pdf_pedido(piezas_filtradas, cliente_nombre, numero_faena, tmp.name)
        return send_file(
            tmp.name,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"pedido_tableros_{numero_faena}.pdf"
        )
    except Exception as e:
        return jsonify({"ok": False, "error": f"Error generando PDF: {str(e)}"}), 500

# -------------------- PRESUPUESTO --------------------
def leer_presupuesto_txt(ruta_txt):
    if not ruta_txt or not os.path.exists(ruta_txt):
        return []
    conceptos = []
    seccion = ""
    with open(ruta_txt, encoding="utf-8", errors="replace") as f:
        for linea in f:
            texto = linea.strip()
            if not texto:
                continue
            texto_may = texto.upper()
            if texto_may == "MATERIALES":
                seccion = "material"
                continue
            if texto_may == "MANO DE OBRA":
                seccion = "mano_obra"
                continue
            if texto.startswith("=") or texto.startswith("-") or texto_may.startswith("TARIFA HORA"):
                continue
            if texto_may.startswith("SUBTOTAL") or texto_may.startswith("TOTAL FAENA") or texto_may.startswith("PRESUPUESTO FAENA"):
                continue
            m = re.search(r"^(.*?)\s+([0-9]+(?:[.,][0-9]{2})?)\s*€$", texto)
            if not m:
                continue
            descripcion = m.group(1).strip()
            total = float(m.group(2).replace(",", "."))
            conceptos.append({
                "id": f"txt_{len(conceptos)+1}",
                "faena_id": None,
                "tipo": seccion or "material",
                "descripcion": descripcion,
                "cantidad": 1,
                "precio_unitario": total,
                "total": total,
                "fecha": "",
                "origen": "txt"
            })
    return conceptos

def asegurar_presupuesto_editable(conn, faena_id, carpeta):
    filas_db = conn.execute(
        "SELECT * FROM presupuestos_faena WHERE faena_id=? ORDER BY fecha DESC, id ASC",
        (faena_id,)
    ).fetchall()
    if filas_db:
        return filas_a_lista(filas_db)

    if not carpeta:
        return []

    presupuesto_txt = leer_presupuesto_txt(os.path.join(carpeta, "presupuesto.txt"))
    if not presupuesto_txt:
        return []

    for concepto in presupuesto_txt:
        conn.execute(
            "INSERT INTO presupuestos_faena (faena_id, tipo, descripcion, cantidad, precio_unitario, total) VALUES (?, ?, ?, ?, ?, ?)",
            (
                faena_id,
                concepto.get("tipo", "material"),
                concepto.get("descripcion", ""),
                float(concepto.get("cantidad", 1) or 1),
                float(concepto.get("precio_unitario", 0) or 0),
                float(concepto.get("total", 0) or 0),
            )
        )
    conn.commit()

    filas_db = conn.execute(
        "SELECT * FROM presupuestos_faena WHERE faena_id=? ORDER BY fecha DESC, id ASC",
        (faena_id,)
    ).fetchall()
    return filas_a_lista(filas_db)

@app.route("/api/faenas/<int:id>/presupuesto", methods=["GET"])
def get_presupuesto(id):
    conn = get_connection()
    faena = conn.execute("""
        SELECT f.*, c.nombre AS cliente_nombre
        FROM faenas f LEFT JOIN clientes c ON f.cliente_id = c.id
        WHERE f.id = ?
    """, (id,)).fetchone()
    conn.close()
    if not faena:
        return jsonify({"ok": False, "error": "Faena no encontrada"}), 404
    carpeta = faena["carpeta"]
    ruta_txt = os.path.join(carpeta, "presupuesto.txt") if carpeta else None
    contenido = None
    if ruta_txt and os.path.exists(ruta_txt):
        with open(ruta_txt, encoding="utf-8") as f:
            contenido = f.read()
    return jsonify({"ok": True, "data": {"contenido": contenido}})

@app.route("/api/faenas/<int:id>/presupuesto", methods=["POST"])
def guardar_presupuesto(id):
    datos = request.json
    conn = get_connection()
    faena = conn.execute("""
        SELECT f.*, c.nombre AS cliente_nombre
        FROM faenas f LEFT JOIN clientes c ON f.cliente_id = c.id
        WHERE f.id = ?
    """, (id,)).fetchone()
    conn.close()
    if not faena:
        return jsonify({"ok": False, "error": "Faena no encontrada"}), 404
    materiales  = datos.get("materiales", [])
    mano_obra   = datos.get("mano_obra", [])
    tarifa_hora = float(datos.get("tarifa_hora", 0))
    total_mat = sum(float(m.get("cantidad", 0)) * float(m.get("precio_unitario", 0)) for m in materiales)
    total_mo  = sum(float(l.get("cantidad", 0)) * float(l.get("precio", 0)) for l in mano_obra)
    total     = total_mat + total_mo
    conn = get_connection()
    conn.execute("DELETE FROM presupuestos_faena WHERE faena_id=?", (id,))
    for m in materiales:
        cant  = float(m.get("cantidad", 0))
        precio = float(m.get("precio_unitario", 0))
        total_linea = cant * precio
        conn.execute(
            "INSERT INTO presupuestos_faena (faena_id, tipo, descripcion, cantidad, precio_unitario, total) VALUES (?, ?, ?, ?, ?, ?)",
            (id, "material", m.get("descripcion", ""), cant, precio, total_linea)
        )
    for l in mano_obra:
        cant   = float(l.get("cantidad", 0))
        precio = float(l.get("precio", 0))
        total_linea = cant * precio
        conn.execute(
            "INSERT INTO presupuestos_faena (faena_id, tipo, descripcion, cantidad, precio_unitario, total) VALUES (?, ?, ?, ?, ?, ?)",
            (id, l.get("tipo", "hora"), l.get("descripcion", ""), cant, precio, total_linea)
        )
    total_faena = sincronizar_importe_faena(conn, id)
    conn.commit()
    conn.close()
    from datetime import datetime
    fecha = datetime.now().strftime("%d/%m/%Y")
    lineas = [
        "=" * 50,
        f"PRESUPUESTO FAENA: {faena['numero']}",
        f"Cliente: {faena['cliente_nombre']}",
        f"Tipo: {faena['tipo_trabajo'] or '—'}",
        f"Fecha: {fecha}",
        "=" * 50,
        "",
        "MATERIALES",
        "-" * 50,
    ]
    for m in materiales:
        cant  = float(m.get("cantidad", 0))
        precio = float(m.get("precio_unitario", 0))
        total_linea = cant * precio
        desc  = m.get("descripcion", "")
        lineas.append(f"{desc:<35} {total_linea:>8.2f} €")
    lineas += [
        "-" * 50,
        f"{'Subtotal materiales:':<35} {total_mat:>8.2f} €",
        "",
        "MANO DE OBRA",
        "-" * 50,
        f"Tarifa hora: {tarifa_hora:.2f} €/h",
    ]
    for l in mano_obra:
        cant   = float(l.get("cantidad", 0))
        precio = float(l.get("precio", 0))
        total_linea = cant * precio
        desc   = l.get("descripcion", "")
        tipo   = l.get("tipo", "hora")
        unidad = "h" if tipo == "hora" else "ud"
        lineas.append(f"{desc} ({cant}{unidad}){'':<10} {total_linea:>8.2f} €")
    lineas += [
        "-" * 50,
        f"{'Subtotal mano de obra:':<35} {total_mo:>8.2f} €",
        "",
        "=" * 50,
        f"{'TOTAL FAENA:':<35} {total:>8.2f} €",
        "=" * 50,
    ]
    contenido = "\n".join(lineas)
    carpeta = faena["carpeta"]
    if not carpeta or not os.path.exists(carpeta):
        return jsonify({"ok": False, "error": "La carpeta de la faena no existe"}), 400
    ruta_txt = os.path.join(carpeta, "presupuesto.txt")
    with open(ruta_txt, "w", encoding="utf-8") as f:
        f.write(contenido)
    return jsonify({"ok": True, "data": {
        "ruta": ruta_txt,
        "total_materiales": total_mat,
        "total_mano_obra": total_mo,
        "total": total_faena,
        "importe": total_faena,
        "contenido": contenido
    }})

    import base64 as b64mod
    datos = request.json
    faena_id = datos.get("faena_id") or 0  # Permitir null/0 para book genérico
    titulo = datos.get("titulo", "")
    descripcion = datos.get("descripcion", "")
    foto_b64 = datos.get("data", "")
    if not foto_b64:
        return jsonify({"ok": False, "error": "Se requiere data"}), 400
     
    conn = get_connection()
    # Validar que si faena_id != 0, la faena exista
    if faena_id and faena_id != 0:
        faena = conn.execute("SELECT numero FROM faenas WHERE id=?", (faena_id,)).fetchone()
        if not faena:
            conn.close()
            return jsonify({"ok": False, "error": "Faena no encontrada"}), 404
        numero_faena = faena["numero"]
    else:
        numero_faena = "generico"
     
    carpeta_book = os.path.join(CARPETA_RAIZ, "_book")
    os.makedirs(carpeta_book, exist_ok=True)
    nombre_foto = f"book_{numero_faena}_{int(time.time() * 1000)}.jpg"
    ruta_foto = os.path.join(carpeta_book, nombre_foto)
    try:
        data = foto_b64.split(",")[1] if "," in foto_b64 else foto_b64
        with open(ruta_foto, "wb") as f:
            f.write(b64mod.b64decode(data))
    except Exception as e:
        conn.close()
        return jsonify({"ok": False, "error": str(e)}), 500
     
    cursor = conn.cursor()
    max_orden = conn.execute("SELECT COALESCE(MAX(orden),0) FROM book_fotos").fetchone()[0]
    cursor.execute(
        "INSERT INTO book_fotos (faena_id, ruta_foto, titulo, descripcion, orden) VALUES (?,?,?,?,?)",
        (faena_id, ruta_foto, titulo, descripcion, max_orden + 1)
    )
    conn.commit()
    nuevo_id = cursor.lastrowid
    conn.close()
    return jsonify({"ok": True, "data": {"id": nuevo_id}})

@app.route("/api/book/<int:id>", methods=["PUT"])
def editar_book(id):
    datos = request.json
    conn = get_connection()
    conn.execute(
        "UPDATE book_fotos SET titulo=?, descripcion=?, orden=? WHERE id=?",
        (datos.get("titulo", ""), datos.get("descripcion", ""), datos.get("orden", 0), id)
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/book/<int:id>", methods=["DELETE"])
def eliminar_book(id):
    conn = get_connection()
    conn.execute("DELETE FROM book_fotos WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/book/fotos-faena/<int:faena_id>", methods=["GET"])
def fotos_disponibles_faena(faena_id):
    import base64
    conn = get_connection()
    faena = conn.execute("SELECT carpeta FROM faenas WHERE id=?", (faena_id,)).fetchone()
    conn.close()
    if not faena or not faena["carpeta"]:
        return jsonify({"ok": False, "error": "Faena no encontrada"}), 404
    carpeta_fotos = os.path.join(faena["carpeta"], "fotos")
    if not os.path.exists(carpeta_fotos):
        return jsonify({"ok": True, "data": []})
    fotos = []
    for nombre in sorted(os.listdir(carpeta_fotos)):
        if os.path.splitext(nombre)[1].lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            ruta = os.path.join(carpeta_fotos, nombre)
            with open(ruta, "rb") as f:
                data = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
            fotos.append({"nombre": nombre, "ruta": ruta, "data": data})
    return jsonify({"ok": True, "data": fotos})

# -------------------- IMPORTAR MATERIALES DESDE PDF --------------------
@app.route("/api/materiales/importar-pdf", methods=["POST"])
def importar_pdf_materiales():
    import fitz
    root = tk.Tk()
    root.withdraw()
    ruta_pdf = filedialog.askopenfilename(
        title="Selecciona el PDF del catálogo o factura",
        filetypes=[("PDF", "*.pdf"), ("Todos", "*.*")]
    )
    root.destroy()
    if not ruta_pdf:
        return jsonify({"ok": False, "error": "No se seleccionó ningún archivo"})
    try:
        doc = fitz.open(ruta_pdf)
        texto = ""
        for pagina in doc:
            texto += pagina.get_text()
        doc.close()
        if not texto.strip():
            return jsonify({"ok": False, "error": "El PDF no contiene texto extraíble"}), 400
        texto_truncado = texto[:8000]
        if len(texto) > 8000:
            texto_truncado += "\n[... texto truncado ...]"
        nombre_pdf = os.path.basename(ruta_pdf)
        prompt = f"""Analiza el siguiente texto extraído del PDF "{nombre_pdf}" que es un catálogo o factura de materiales de carpintería.

Extrae todos los materiales, herrajes o productos con sus precios y devuelve ÚNICAMENTE este JSON sin texto adicional:

{{
  "proveedor": "Nombre del proveedor o tienda si aparece",
  "materiales": [
    {{
      "nombre": "Nombre del material o herraje",
      "referencia": "Referencia o código si aparece",
      "unidad": "ud/ml/kg/caja/m2/litro",
      "precio_unitario": 0.00,
      "categoria": "Herraje/Consumible/Cola/Tornillería/Otro"
    }}
  ]
}}

Texto del PDF:
---
{texto_truncado}
---

Extrae solo productos con precio. Si no hay precios claros, incluye el producto con precio_unitario: null."""
        return jsonify({"ok": True, "data": {"prompt": prompt, "nombre_pdf": nombre_pdf, "caracteres": len(texto)}})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Error al leer el PDF: {str(e)}"}), 500

@app.route("/api/faenas/<int:id>/gastos/importar-pdf", methods=["POST"])
def importar_pdf_gastos(id):
    import fitz
    conn = get_connection()
    faena = conn.execute("""
        SELECT f.*, c.nombre AS cliente_nombre
        FROM faenas f LEFT JOIN clientes c ON f.cliente_id = c.id
        WHERE f.id = ?
    """, (id,)).fetchone()
    conn.close()
    if not faena:
        return jsonify({"ok": False, "error": "Faena no encontrada"}), 404
    root = tk.Tk()
    root.withdraw()
    ruta_pdf = filedialog.askopenfilename(
        title="Selecciona la factura PDF",
        filetypes=[("PDF", "*.pdf"), ("Todos", "*.*")]
    )
    root.destroy()
    if not ruta_pdf:
        return jsonify({"ok": False, "error": "No se seleccionó ningún archivo"})
    try:
        doc = fitz.open(ruta_pdf)
        texto = "".join(p.get_text() for p in doc)
        doc.close()
        if not texto.strip():
            return jsonify({"ok": False, "error": "El PDF no contiene texto extraíble"}), 400
        texto_truncado = texto[:6000] + ("\n[... truncado ...]" if len(texto) > 6000 else "")
        nombre_pdf = os.path.basename(ruta_pdf)
        prompt = f"""Analiza esta factura de materiales para una obra de carpintería.
Faena: {faena['numero']} — {faena['tipo_trabajo'] or '—'} — Cliente: {faena['cliente_nombre']}

Extrae todos los artículos comprados y devuelve ÚNICAMENTE este JSON sin texto adicional:

{{
  "proveedor": "Nombre del proveedor",
  "fecha": "YYYY-MM-DD",
  "articulos": [
    {{
      "nombre": "Nombre del artículo",
      "cantidad": 1,
      "precio_unitario": 0.00,
      "total": 0.00,
      "unidad": "ud"
    }}
  ],
  "total_factura": 0.00
}}

Texto de la factura "{nombre_pdf}":
---
{texto_truncado}
---"""
        return jsonify({"ok": True, "data": {"prompt": prompt, "nombre_pdf": nombre_pdf}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
if __name__ == "__main__":
    print("=" * 50)
    print("  🪵 Gestión de Faenas — Arrancando...")
    print("=" * 50)
    inicializar_db()
    
    # Obtener el puerto de Railway o usar 5000 por defecto
    PORT = int(os.environ.get('PORT', 5000))
    
    print(f"✓ Servidor iniciado en puerto {PORT}")
    print("=" * 50)
    
    # IMPORTANTE: host='0.0.0.0' para Railway
    app.run(host='0.0.0.0', port=PORT, debug=False)