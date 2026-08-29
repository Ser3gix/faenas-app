import socket
import os
import subprocess
import time
import re
import json
import base64
import io
import urllib.request
import urllib.error
from flask import Flask, jsonify, request, send_from_directory, Response, stream_with_context, render_template, redirect, send_file
from flask_cors import CORS

import shutil
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from config import HOST, PORT, PUBLIC_BASE_URL, CURSOR_PATH, CARPETA_RAIZ, APP_DIR, OBJECT_STORAGE_BUCKET
from database import (
    inicializar_db, get_connection, get_sqlite_local, get_db_status,
    generar_numero_faena, crear_carpeta_faena,
    fila_a_dict, filas_a_lista
)
from object_storage import r2_activo, r2_listo, r2_error, subir_bytes, borrar_objeto, descargar_bytes, clave_objeto, url_publica
from secretario import chat_jimmi, cruzar_articulos, anotar_contexto

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
IA_API_KEY = (os.environ.get("CLAVE_API") or os.environ.get("IA_API_KEY") or "").strip()
TICKET_IA_API_KEY = (os.environ.get("TICKET_CLAVE_API") or "").strip()
IA_PROVIDER = (os.environ.get("IA_PROVIDER") or "gemini").strip().lower()
IA_API_URL = os.environ.get("IA_API_URL", "").strip()
IA_MODEL = (os.environ.get("IA_MODEL") or "").strip()
TICKET_IA_MODEL = (os.environ.get("TICKET_IA_MODEL") or "gemini-flash-latest").strip()
IA_MODO = (os.environ.get("IA_MODO") or "local").strip().lower()
_GEMINI_MODEL_CACHE = {}

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


_EXTS_FOTO = {".jpg", ".jpeg", ".png", ".webp"}
_EXTS_PDF = {".pdf"}


def _extension(nombre):
    return os.path.splitext(nombre or "")[1].lower()


def _mime_archivo(nombre):
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".pdf": "application/pdf",
    }.get(_extension(nombre), "application/octet-stream")


def _es_foto_nombre(nombre):
    return _extension(nombre) in _EXTS_FOTO


def _es_pdf_nombre(nombre):
    return _extension(nombre) in _EXTS_PDF


def _guardar_binario(faena, carpeta_rel, nombre, data, content_type):
    numero = str(faena.get("numero") or faena.get("id") or "faena").strip()
    if r2_activo():
        key = clave_objeto(numero, carpeta_rel, nombre)
        res = subir_bytes(key, data, content_type)
        if not res.get("ok"):
            raise RuntimeError(res.get("error") or "No se pudo subir a Cloudflare")
        return res.get("url") or key, key, res.get("url") or "", "r2"
    carpeta = faena.get("carpeta") or ""
    if not carpeta:
        raise RuntimeError("Configura Cloudflare R2; el disco de Render no guarda archivos")
    destino_dir = os.path.join(carpeta, carpeta_rel)
    os.makedirs(destino_dir, exist_ok=True)
    ruta = os.path.join(destino_dir, nombre)
    with open(ruta, "wb") as fh:
        fh.write(data)
    return ruta, "", "", "local"


def _payload_foto(fila):
    ruta = (fila.get("ruta_foto") or "").strip()
    contenido = (fila.get("data_base64") or "").strip()
    if contenido:
        data = f"data:{_mime_por_extension(fila.get('nombre'))};base64,{contenido}"
    else:
        data = _url_desde_ruta(ruta)
        if not data and ruta and os.path.exists(ruta):
            try:
                with open(ruta, "rb") as f:
                    data = f"data:{_mime_por_extension(fila.get('nombre'))};base64," + base64.b64encode(f.read()).decode()
            except Exception:
                data = ""
    return {
        "id": fila.get("id"),
        "nombre": fila.get("nombre"),
        "ruta": ruta,
        "data": data,
    }


def _url_desde_ruta(ruta):
    ruta = (ruta or "").strip()
    if not ruta:
        return ""
    if ruta.startswith("http://") or ruta.startswith("https://"):
        return ruta
    if os.path.exists(ruta):
        return ""
    if r2_activo():
        return url_publica(ruta)
    return ""


def _borrar_binario(ruta, object_key=""):
    clave = (object_key or "").strip() or ((ruta or "").strip() if not os.path.exists(ruta or "") else "")
    if clave and not os.path.exists(clave):
        borrar_objeto(clave)
    if ruta and os.path.exists(ruta):
        try:
            os.remove(ruta)
        except Exception:
            pass


def _registrar_archivo(conn, faena_id, tipo, nombre, backend, object_key, public_url, mime, tamano):
    conn.execute(
        """INSERT INTO archivos_faena
        (faena_id, tipo, nombre, storage_backend, bucket, object_key, public_url, mime_type, tamaño)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            faena_id,
            tipo,
            nombre,
            backend,
            OBJECT_STORAGE_BUCKET if backend == "r2" else "",
            object_key or "",
            public_url or "",
            mime or "",
            int(tamano or 0),
        ),
    )



def _ia_provider_activo():
    if IA_PROVIDER in {"gemini", "google", "google_gemini"}:
        return "gemini"
    return "gemini" if "generativelanguage.googleapis.com" in (IA_API_URL or "") else "gemini"


def _prompt_ticket_base():
    return """Analiza la imagen del ticket o factura de compra que te adjunto.
Extrae todos los artículos y devuelve ÚNICAMENTE el siguiente JSON, sin texto adicional antes ni después:

Lee la imagen por zonas y revisa dos veces cada línea de artículos. No inventes artículos ni importes.
Respeta la separación entre columnas: cantidad es el número de unidades, precio_unitario es el precio de una unidad y total es cantidad multiplicada por precio_unitario. No uses el subtotal, IVA o total del ticket como precio de un artículo.
Si una línea tiene descuento, conserva el importe final pagado en total y calcula precio_unitario = total / cantidad cuando la cantidad sea conocida.
Convierte los importes con coma decimal a números JSON usando punto decimal. Si una cifra o nombre no se lee con seguridad, usa null en ese campo, pero conserva la línea si el artículo se puede identificar.

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


def _prompt_documento_base(nombre="documento"):
    return f"""Analiza el documento '{nombre}' y devuelve ÚNICAMENTE este JSON, sin texto adicional:

El documento puede ser la impresión o exportación de un correo electrónico. Ignora cabeceras del correo (De, Para, CC, Asunto), fechas de envío, firmas, avisos legales, respuestas repetidas y texto de conversación que no sea una compra. Busca en todo el cuerpo del mensaje, incluido el contenido reenviado, las tablas de pedido o factura y las líneas de materiales.
Si el correo describe una compra sin tabla formal, convierte cada material mencionado con cantidad y precio en un artículo. No conviertas teléfonos, fechas, números de pedido, códigos postales ni importes de transporte o IVA en materiales. Usa el remitente, la empresa o el vendedor como proveedor solo cuando esté claro.
Separa cantidad, precio unitario y total. Si solo aparece un importe total de línea, úsalo como total y calcula el precio unitario cuando haya cantidad. Si un dato no aparece o no se lee con seguridad, usa null.

{{
    "proveedor": "Nombre del establecimiento",
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
    "total_ticket": 0.00
}}

Si no puedes leer algún dato con claridad, usa null para ese campo.
Las unidades pueden ser: ud (unidades), ml (mililitros), kg (kilogramos), caja, m2 (metro cuadrado), litro."""


def _gemini_endpoint(model=None, api_key=None):
    modelo = (model or _gemini_model_activo(api_key=api_key, modelo_preferido=IA_MODEL or None) or IA_MODEL or "gemini-flash-latest").strip()
    clave = (api_key or IA_API_KEY).strip()
    return f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={clave}"


def _gemini_model_activo(api_key=None, modelo_preferido=None):
    clave = (api_key or IA_API_KEY or "").strip()
    cache_key = clave or "default"
    if cache_key in _GEMINI_MODEL_CACHE:
        return _GEMINI_MODEL_CACHE[cache_key]
    if not clave:
        return modelo_preferido or TICKET_IA_MODEL or IA_MODEL or "gemini-flash-latest"
    candidatos_prioritarios = [
        modelo_preferido,
        TICKET_IA_MODEL,
        IA_MODEL,
        "gemini-flash-latest",
        "gemini-flash-lite-latest",
        "gemini-pro-latest",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-pro",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "gemini-pro",
    ]
    try:
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={clave}",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = json.loads(resp.read().decode("utf-8", "ignore"))
        modelos = raw.get("models") if isinstance(raw, dict) else []
        disponibles = []
        for modelo in modelos or []:
            nombre = (modelo.get("name") or "").split("/")[-1]
            metodos = modelo.get("supportedGenerationMethods") or []
            if nombre and ("generateContent" in metodos or not metodos):
                disponibles.append(nombre)
        for candidato in candidatos_prioritarios:
            if candidato and candidato in disponibles:
                _GEMINI_MODEL_CACHE[cache_key] = candidato
                return candidato
        if disponibles:
            _GEMINI_MODEL_CACHE[cache_key] = disponibles[0]
            return disponibles[0]
    except Exception:
        pass
    return modelo_preferido or TICKET_IA_MODEL or IA_MODEL or "gemini-flash-latest"


def _gemini_extraer_texto(raw):
    candidates = raw.get("candidates") if isinstance(raw, dict) else None
    if not candidates:
        raise RuntimeError("Respuesta IA sin candidates")
    content = (candidates[0] or {}).get("content") or {}
    parts = content.get("parts") or []
    texto = "".join((p.get("text") or "") for p in parts if isinstance(p, dict)).strip()
    if not texto:
        raise RuntimeError("Respuesta IA vacia")
    return texto


def _gemini_imagen_part(data_url):
    data = limpiar_data_b64(data_url)
    if not data:
        return None
    mime_type = "image/jpeg"
    if isinstance(data_url, str) and data_url.startswith("data:") and ";base64," in data_url:
        mime_type = data_url[5:data_url.index(";base64,")] or "image/jpeg"
    return {"inline_data": {"mime_type": mime_type, "data": data}}


def _peticion_gemini(contents, system_instruction=None, response_mime_type=None, max_tokens=1200, temperature=0.2, api_key=None, model=None, timeout=90, tools=None):
    clave = (api_key or IA_API_KEY or "").strip()
    if not clave:
        raise RuntimeError("No hay API key configurada")
    modelo_solicitado = (model or "").strip() or _gemini_model_activo(api_key=clave, modelo_preferido=IA_MODEL or None)
    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
    if response_mime_type:
        payload["generationConfig"]["responseMimeType"] = response_mime_type
    if tools:
        payload["tools"] = tools

    def _enviar(modelo_en_uso):
        req = urllib.request.Request(
            _gemini_endpoint(model=modelo_en_uso, api_key=clave),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "ignore"))

    try:
        raw = _enviar(modelo_solicitado)
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "ignore") if hasattr(e, "read") else ""
        if e.code == 401:
            raise RuntimeError(f"La API key de .env fue rechazada por Gemini (401). Revisa TICKET_CLAVE_API. {detalle}".strip())
        if e.code == 429:
            retry_delay = 0
            try:
                payload_error = json.loads(detalle or "{}")
                retry_info = (payload_error.get("error") or {}).get("details") or []
                for item in retry_info:
                    if isinstance(item, dict) and item.get("@type", "").endswith("RetryInfo"):
                        retry_delay = item.get("retryDelay", "0s")
                        break
            except Exception:
                pass
            raise RuntimeError(f"Gemini sin cuota temporal (429). Reintenta en {retry_delay or 'unos segundos'}. {detalle}".strip())
        if e.code == 404:
            cache_key = clave or "default"
            if cache_key in _GEMINI_MODEL_CACHE:
                _GEMINI_MODEL_CACHE.pop(cache_key, None)
            candidatos = []
            modelo_descubierto = _gemini_model_activo(api_key=clave, modelo_preferido=None)
            if modelo_descubierto:
                candidatos.append(modelo_descubierto)
            for m in ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-pro-latest", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]:
                if m not in candidatos:
                    candidatos.append(m)
            for alt in candidatos:
                if not alt or alt == modelo_solicitado:
                    continue
                try:
                    return _enviar(alt)
                except urllib.error.HTTPError as e_alt:
                    if e_alt.code == 404:
                        continue
                    detalle_alt = e_alt.read().decode("utf-8", "ignore") if hasattr(e_alt, "read") else ""
                    raise RuntimeError(f"Error de Gemini: {e_alt.reason or str(e_alt)} {detalle_alt}".strip())
            raise RuntimeError(f"Error de Gemini: modelo no disponible ({modelo_solicitado}). {detalle}".strip())
        if e.code == 503:
            # Un modelo puede estar saturado aunque la API key sea valida.
            candidatos = [
                "gemini-2.5-flash-lite",
                "gemini-2.5-flash",
                "gemini-flash-lite-latest",
            ]
            for alt in candidatos:
                if not alt or alt == modelo_solicitado:
                    continue
                try:
                    return _enviar(alt)
                except urllib.error.HTTPError as e_alt:
                    if e_alt.code == 503:
                        continue
                    detalle_alt = e_alt.read().decode("utf-8", "ignore") if hasattr(e_alt, "read") else ""
                    raise RuntimeError(f"Error de Gemini: {e_alt.reason or str(e_alt)} {detalle_alt}".strip())
            raise RuntimeError(f"Gemini no disponible temporalmente (503). {detalle}".strip())
        raise RuntimeError(f"Error de Gemini: {e.reason or str(e)} {detalle}".strip())
    return raw


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
    return render_template("index.html", faenas_api_base=_url_api_publica())

def _url_api_publica():
    base = (PUBLIC_BASE_URL or "").rstrip("/")
    return f"{base}/api" if base else ""

@app.route("/movil2")
def movil2():
    return render_template("movil2.html", faenas_api_base=_url_api_publica())

@app.route("/movil")
@app.route("/movil4")
def movil_obsoleto():
    return redirect("/movil2", code=301)

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
    url_local = f"http://{ip_final}:{PORT}/movil2"
    url_publica = f"{PUBLIC_BASE_URL}/movil2" if PUBLIC_BASE_URL else url_local
    return jsonify({"ok": True, "data": {"ip": ip_final, "url": url_publica, "url_local": url_local, "url_publica": PUBLIC_BASE_URL, "todas": ips}})

@app.route("/api/info/db", methods=["GET"])
def get_db_info():
    return jsonify({"ok": True, "data": get_db_status()})

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

def _conn_para_faena(faena_id):
    """Devuelve la conexión donde vive la faena (nube activa o SQLite archivado)."""
    conn = get_connection()
    existe = conn.execute("SELECT id FROM faenas WHERE id=?", (faena_id,)).fetchone()
    if existe:
        return conn
    conn.close()
    return get_sqlite_local()

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
    _SQL = """
        SELECT f.*, c.nombre AS cliente_nombre, c.telefono AS cliente_telefono, i.nombre AS intermediario_nombre
        FROM faenas f
        LEFT JOIN clientes c ON f.cliente_id = c.id
        LEFT JOIN intermediarios i ON f.intermediario_id = i.id
        WHERE f.id = ?
    """
    conn = get_connection()
    fila = conn.execute(_SQL, (id,)).fetchone()
    conn.close()
    if not fila:
        conn2 = get_sqlite_local()
        fila = conn2.execute(_SQL, (id,)).fetchone()
        conn2.close()
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
    faena = conn.execute("SELECT * FROM faenas WHERE id=?", (id,)).fetchone()
    if not faena:
        conn.close()
        return jsonify({"ok": False, "error": "Faena no encontrada"}), 404
    conn.execute("UPDATE faenas SET archivada=1 WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "data": {"zip": f"/api/faenas/{id}/archivo-zip"}})


@app.route("/api/faenas/<int:id>/archivo-zip", methods=["GET"])
def descargar_zip_faena(id):
    import zipfile
    conn = _conn_para_faena(id)
    faena = fila_a_dict(conn.execute("SELECT * FROM faenas WHERE id=?", (id,)).fetchone())
    if not faena:
        conn.close()
        return jsonify({"ok": False, "error": "Faena no encontrada"}), 404
    fotos = filas_a_lista(conn.execute("SELECT * FROM fotos_faena WHERE faena_id=?", (id,)).fetchall())
    archivos = []
    try:
        archivos = filas_a_lista(conn.execute("SELECT * FROM archivos_faena WHERE faena_id=?", (id,)).fetchall())
    except Exception:
        archivos = []
    conn.close()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        lista_docs = []
        for foto in fotos:
            nombre = foto.get("nombre") or "foto.jpg"
            contenido = None
            ruta = foto.get("ruta_foto") or ""
            if ruta and os.path.exists(ruta):
                with open(ruta, "rb") as fh:
                    contenido = fh.read()
            elif foto.get("data_base64"):
                contenido = base64.b64decode(limpiar_data_b64(foto["data_base64"]))
            else:
                contenido = descargar_bytes(ruta)
            if contenido:
                zf.writestr(f"fotos/{nombre}", contenido)
        for arch in archivos:
            nombre = arch.get("nombre") or "documento"
            lista_docs.append(nombre)
            if _es_pdf_nombre(nombre) or (arch.get("storage_backend") == "r2" and arch.get("object_key")):
                contenido = descargar_bytes(arch.get("object_key") or "")
                if contenido:
                    carpeta = "pdf" if _es_pdf_nombre(nombre) else "documentos"
                    zf.writestr(f"{carpeta}/{nombre}", contenido)
            elif faena.get("carpeta"):
                local = os.path.join(faena["carpeta"], "Documentos", nombre)
                if os.path.exists(local):
                    with open(local, "rb") as fh:
                        zf.writestr(f"documentos/{nombre}", fh.read())
        if lista_docs:
            zf.writestr("documentos/lista.txt", "\n".join(lista_docs) + "\n")
        zf.writestr("faena.txt", f"{faena.get('numero') or id}\n{faena.get('direccion') or ''}\n")
    buf.seek(0)
    numero = str(faena.get("numero") or id).replace("/", "-")
    return send_file(buf, as_attachment=True, download_name=f"faena_{numero}.zip", mimetype="application/zip")


# -------------------- ANOTACIONES --------------------
@app.route("/api/faenas/<int:id>/anotaciones", methods=["GET"])
def get_anotaciones(id):
    conn = _conn_para_faena(id)
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

@app.route("/api/materiales/<int:id>", methods=["PUT"])
def editar_material(id):
    datos = request.json or {}
    nombre = str(datos.get("nombre", "")).strip()
    unidad = str(datos.get("unidad", "ud")).strip() or "ud"
    categoria = str(datos.get("categoria", "Herraje")).strip() or "Herraje"
    definicion = str(datos.get("definicion", "")).strip()
    if not nombre:
        return jsonify({"ok": False, "error": "El nombre es obligatorio"}), 400
    conn = get_connection()
    existente = conn.execute("SELECT id FROM materiales WHERE id=?", (id,)).fetchone()
    if not existente:
        conn.close()
        return jsonify({"ok": False, "error": "Material no encontrado"}), 404
    conn.execute(
        "UPDATE materiales SET nombre=?, unidad=?, categoria=?, definicion=? WHERE id=?",
        (nombre, unidad, categoria, definicion, id)
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/materiales/<int:id>", methods=["DELETE"])
def eliminar_material(id):
    conn = get_connection()
    existente = conn.execute("SELECT id FROM materiales WHERE id=?", (id,)).fetchone()
    if not existente:
        conn.close()
        return jsonify({"ok": False, "error": "Material no encontrado"}), 404
    conn.execute("DELETE FROM precios WHERE material_id=?", (id,))
    conn.execute("DELETE FROM materiales WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/materiales/<int:id>/definicion", methods=["PUT"])
def editar_definicion_material(id):
    datos = request.json or {}
    definicion = str(datos.get("definicion", "")).strip()
    conn = get_connection()
    existente = conn.execute("SELECT id FROM materiales WHERE id=?", (id,)).fetchone()
    if not existente:
        conn.close()
        return jsonify({"ok": False, "error": "Material no encontrado"}), 404
    conn.execute("UPDATE materiales SET definicion=? WHERE id=?", (definicion, id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

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

@app.route("/api/materiales/<int:id>/precios", methods=["PUT"])
def reemplazar_precios_material(id):
    datos = request.json or {}
    precios = datos.get("precios") if isinstance(datos.get("precios"), list) else []
    conn = get_connection()
    existente = conn.execute("SELECT id FROM materiales WHERE id=?", (id,)).fetchone()
    if not existente:
        conn.close()
        return jsonify({"ok": False, "error": "Material no encontrado"}), 404
    conn.execute("DELETE FROM precios WHERE material_id=?", (id,))
    for precio in precios:
        proveedor = str(precio.get("proveedor", "")).strip()
        valor = precio.get("precio_unitario")
        if not proveedor or valor is None:
            continue
        conn.execute(
            "INSERT INTO precios (material_id, proveedor, precio_unitario, fecha_actualizacion) VALUES (?, ?, ?, datetime('now'))",
            (id, proveedor, valor)
        )
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
    conn = _conn_para_faena(id)
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
        return jsonify({"ok": True, "data": {"prompt": _prompt_ticket_base()}})


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


def _extraer_json_de_texto(texto):
    bruto = (texto or "").strip()
    if not bruto:
        return None

    # Quita fences tipo ```json ... ``` si vienen en la respuesta.
    bruto = re.sub(r"^```(?:json)?\s*", "", bruto, flags=re.IGNORECASE)
    bruto = re.sub(r"\s*```$", "", bruto).strip()

    try:
        return json.loads(bruto)
    except Exception:
        pass

    # A veces el modelo devuelve un JSON serializado como string.
    if (bruto.startswith('"') and bruto.endswith('"')) or (bruto.startswith("'") and bruto.endswith("'")):
        try:
            desescapado = json.loads(bruto)
            if isinstance(desescapado, str):
                try:
                    return json.loads(desescapado)
                except Exception:
                    pass
        except Exception:
            pass

    m = re.search(r"\{[\s\S]*\}", bruto)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _normalizar_json_materiales_con_ia(texto_crudo, tipo="ticket", api_key=None, model=None):
    txt = (texto_crudo or "").strip()
    if not txt:
        return None
    system = (
        f"Convierte la salida de un extractor de {tipo} a JSON estricto. "
        "Devuelve SOLO un objeto JSON con: proveedor, fecha, total_ticket, articulos:[{nombre,cantidad,precio_unitario,total,unidad}]. "
        "Si faltan campos, usa null. No añadas explicaciones."
    )
    raw = _peticion_gemini(
        contents=[{"role": "user", "parts": [{"text": txt}]}],
        system_instruction=system,
        response_mime_type="application/json",
        max_tokens=1200,
        temperature=0,
        api_key=api_key,
        model=model,
    )
    salida = _gemini_extraer_texto(raw)
    return _extraer_json_de_texto(salida)


def _normalizar_articulo(art):
    faena_item = _parse_faena_id_seguro(art.get("faena_id")) if isinstance(art, dict) else None
    cantidad = _to_float_seguro(art.get("cantidad") if isinstance(art, dict) else 0)
    precio = _to_float_seguro(art.get("precio_unitario") if isinstance(art, dict) else 0)
    total = _to_float_seguro(art.get("total") if isinstance(art, dict) else 0)
    if total <= 0:
        total = cantidad * precio
    return {
        "nombre": str(art.get("nombre") or "").strip(),
        "cantidad": cantidad if cantidad > 0 else 1.0,
        "precio_unitario": precio,
        "total": total,
        "unidad": str(art.get("unidad") or "ud").strip() or "ud",
        "categoria": str(art.get("categoria") or "").strip(),
        "definicion": str(art.get("definicion") or "").strip(),
        "faena_id": faena_item,
    }


def _parse_faena_id_seguro(valor):
    try:
        faena_id = int(valor or 0)
        return faena_id if faena_id > 0 else None
    except Exception:
        return None


def _parse_bool_seguro(valor, por_defecto=True):
    if valor is None:
        return por_defecto
    if isinstance(valor, bool):
        return valor
    txt = str(valor).strip().lower()
    if txt in ("1", "true", "si", "sí", "yes", "y", "on"):
        return True
    if txt in ("0", "false", "no", "n", "off"):
        return False
    return por_defecto


def _persistir_resultado_ia_en_nube(faena_id, origen, data):
    faena_id_ok = _parse_faena_id_seguro(faena_id)
    proveedor_global = str((data or {}).get("proveedor") or "").strip()
    articulos = (data or {}).get("articulos") or []
    resumen = {
        "origen": (origen or "ticket").strip().lower(),
        "faena_id": faena_id_ok,
        "materiales_creados": 0,
        "materiales_actualizados": 0,
        "precios_actualizados": 0,
        "gastos_creados": 0,
        "errores": [],
    }
    if not isinstance(articulos, list):
        return resumen

    conn = get_connection()
    try:
        mats = filas_a_lista(conn.execute("SELECT id, nombre, unidad, categoria, definicion FROM materiales").fetchall())
        idx_mat = {}
        for m in mats:
            nombre = (m.get("nombre") or "").strip()
            if nombre:
                idx_mat[_normalizar_texto_busqueda(nombre)] = m

        for i, art in enumerate(articulos):
            if not isinstance(art, dict):
                continue
            try:
                a = _normalizar_articulo(art)
                nombre = (a.get("nombre") or "").strip()
                if not nombre:
                    continue

                norm = _normalizar_texto_busqueda(nombre)
                mat = idx_mat.get(norm)
                mat_id = None
                if mat:
                    mat_id = mat.get("id")
                    unidad = a.get("unidad") or mat.get("unidad") or "ud"
                    categoria = a.get("categoria") or mat.get("categoria") or "Otro"
                    definicion = a.get("definicion")
                    if not definicion:
                        definicion = mat.get("definicion") or ""
                    conn.execute(
                        "UPDATE materiales SET unidad=?, categoria=?, definicion=? WHERE id=?",
                        (unidad, categoria, definicion, mat_id),
                    )
                    resumen["materiales_actualizados"] += 1
                else:
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO materiales (nombre, unidad, categoria, definicion) VALUES (?, ?, ?, ?)",
                        (nombre, a.get("unidad") or "ud", a.get("categoria") or "Otro", a.get("definicion") or ""),
                    )
                    mat_id = cur.lastrowid
                    idx_mat[norm] = {"id": mat_id, "nombre": nombre}
                    resumen["materiales_creados"] += 1

                precio = _to_float_seguro(a.get("precio_unitario"))
                proveedor_linea = str(a.get("proveedor") or proveedor_global or "").strip()
                if mat_id and proveedor_linea and precio > 0:
                    ex = conn.execute(
                        "SELECT id FROM precios WHERE material_id=? AND proveedor=?",
                        (mat_id, proveedor_linea),
                    ).fetchone()
                    if ex:
                        conn.execute(
                            "UPDATE precios SET precio_unitario=?, fecha_actualizacion=datetime('now') WHERE id=?",
                            (precio, ex["id"]),
                        )
                    else:
                        conn.execute(
                            "INSERT INTO precios (material_id, proveedor, precio_unitario, fecha_actualizacion) VALUES (?, ?, ?, datetime('now'))",
                            (mat_id, proveedor_linea, precio),
                        )
                    resumen["precios_actualizados"] += 1

                faena_linea = _parse_faena_id_seguro(a.get("faena_id")) or faena_id_ok
                if faena_linea:
                    conn.execute(
                        "INSERT INTO gastos_faena (faena_id, tipo, descripcion, cantidad, precio_unitario, total, ticket_foto) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            faena_linea,
                            resumen["origen"],
                            nombre,
                            _to_float_seguro(a.get("cantidad") or 1),
                            _to_float_seguro(a.get("precio_unitario") or 0),
                            _to_float_seguro(a.get("total") or 0),
                            "",
                        ),
                    )
                    resumen["gastos_creados"] += 1
            except Exception as e:
                resumen["errores"].append(f"articulo[{i}]: {str(e)}")

        conn.commit()
        return resumen
    finally:
        conn.close()


def _to_float_seguro(valor):
    try:
        if isinstance(valor, str):
            valor = valor.replace("€", "").replace(" ", "").replace(",", ".")
        return float(valor or 0)
    except Exception:
        return 0.0


def _normalizar_texto_busqueda(texto):
    txt = (texto or "").lower()
    txt = txt.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    txt = txt.replace("ü", "u").replace("ñ", "n")
    txt = re.sub(r"[^a-z0-9\s]", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def _tokens_memoria(texto):
    stop = {
        "que", "quien", "cual", "cuales", "cuanto", "cuanta", "cuantos", "cuantas", "de", "del", "la", "el", "los", "las",
        "es", "son", "tiene", "tienen", "hay", "para", "una", "un", "y", "o", "me", "dime", "quiero", "ver",
        "por", "favor", "puedo", "podrias", "podrias", "podria", "ser", "al", "en", "con", "sin", "sobre"
    }
    return [t for t in _normalizar_texto_busqueda(texto).split() if len(t) > 1 and t not in stop]


def _guardar_memoria_ia(pregunta, respuesta, contexto_tipo="general", alcance="general", faena_id=0, fuente="local"):
    try:
        conn = get_connection()
        try:
            tokens = " ".join(_tokens_memoria(pregunta))[:2000]
            conn.execute(
                """
                INSERT INTO ia_memoria (pregunta, respuesta, contexto_tipo, alcance, faena_id, tokens, fuente)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (pregunta[:5000], respuesta[:15000], contexto_tipo or "general", alcance or "general", int(faena_id or 0), tokens, fuente or "local"),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"[AVISO] No se pudo guardar memoria IA: {e}")


def _buscar_memoria_ia(pregunta, contexto_tipo="general", alcance="general", faena_id=0):
    tokens = _tokens_memoria(pregunta)
    if not tokens:
        return None
    pregunta_normalizada = _normalizar_texto_busqueda(pregunta)
    conn = get_connection()
    try:
        filas = conn.execute(
            """
            SELECT pregunta, respuesta, contexto_tipo, alcance, faena_id, tokens
            FROM ia_memoria
            ORDER BY id DESC
            LIMIT 200
            """
        ).fetchall()
    finally:
        conn.close()

    mejor = None
    for fila in filas_a_lista(filas):
        misma_pregunta = _normalizar_texto_busqueda(fila.get("pregunta") or "") == pregunta_normalizada
        mismo_contexto = str(fila.get("contexto_tipo") or "") == str(contexto_tipo or "")
        mismo_alcance = str(fila.get("alcance") or "") == str(alcance or "")
        misma_faena = int(fila.get("faena_id") or 0) == int(faena_id or 0)
        if misma_pregunta and mismo_contexto and mismo_alcance and misma_faena:
            return fila
    return mejor


def _tokens_pregunta(texto):
    stop = {
        "cual", "cuales", "cuanto", "cuanta", "cuantos", "cuantas", "de", "del", "la", "el", "los", "las",
        "es", "son", "tiene", "hay", "para", "una", "un", "y", "o", "me", "dime", "quiero", "ver",
        "presupuesto", "importe", "direccion", "cliente", "faena", "trabajo", "armario"
    }
    return [t for t in _normalizar_texto_busqueda(texto).split() if len(t) > 1 and t not in stop]


def _buscar_faenas_db():
    conn = get_connection()
    try:
        filas = conn.execute(
            """
            SELECT f.id, f.numero, f.tipo_trabajo, f.importe, f.archivada, f.direccion,
                   c.nombre AS cliente_nombre
            FROM faenas f
            LEFT JOIN clientes c ON c.id = f.cliente_id
            ORDER BY f.id DESC
            """
        ).fetchall()
        return filas_a_lista(filas)
    finally:
        conn.close()


def _mejor_faena_para_tokens(faenas, tokens, exigir_tipo=False):
    mejor = None
    mejor_score = -1
    for faena in faenas:
        cliente = _normalizar_texto_busqueda(faena.get("cliente_nombre") or "")
        trabajo = _normalizar_texto_busqueda(faena.get("tipo_trabajo") or "")
        score = 0
        for tk in tokens:
            if tk in cliente:
                score += 3
            if tk in trabajo:
                score += 2
        if exigir_tipo and not any(tk in trabajo for tk in tokens):
            score -= 2
        if score > mejor_score:
            mejor = faena
            mejor_score = score
    return mejor if mejor_score > 0 else None


def _respuesta_ia_local(pregunta, contexto, faena_id=None):
    txt = (pregunta or "").strip().lower()
    ctx = contexto if isinstance(contexto, dict) else {}
    contexto_tipo = (ctx.get("contexto_tipo") or ctx.get("tipo") or "general") if isinstance(ctx, dict) else "general"
    alcance = (ctx.get("alcance") or "general") if isinstance(ctx, dict) else "general"

    faenas = ctx.get("faenas") if isinstance(ctx.get("faenas"), list) else []
    materiales = ctx.get("materiales") if isinstance(ctx.get("materiales"), list) else []

    memoria = _buscar_memoria_ia(pregunta, contexto_tipo=contexto_tipo, alcance=alcance, faena_id=faena_id or 0)
    consulta_precio_material = any(k in txt for k in ["material", "materiales", "precio", "precios", "coste", "costo", "bisagra", "bisagras"])
    respuesta_memoria = (memoria.get("respuesta") or "").strip() if memoria else ""
    if memoria and respuesta_memoria and not (consulta_precio_material and respuesta_memoria.startswith("Puedo ayudarte")):
        return memoria.get("respuesta")

    if not faenas:
        conn = get_connection()
        try:
            filas = conn.execute(
                """
                SELECT f.id, f.numero, f.tipo_trabajo, f.importe, f.archivada,
                       c.nombre AS cliente_nombre
                FROM faenas f
                LEFT JOIN clientes c ON c.id = f.cliente_id
                ORDER BY f.id DESC
                """
            ).fetchall()
            faenas = filas_a_lista(filas)
        finally:
            conn.close()

    if not materiales:
        conn = get_connection()
        try:
            filas = conn.execute(
                """
                SELECT m.nombre, m.categoria, m.definicion, p.proveedor, p.precio_unitario
                FROM materiales m
                LEFT JOIN precios p ON p.material_id = m.id
                """
            ).fetchall()
            tmp = {}
            for fila in filas_a_lista(filas):
                clave = (fila.get("nombre") or "").strip()
                if not clave:
                    continue
                if clave not in tmp:
                    tmp[clave] = {
                        "nombre": clave,
                        "categoria": fila.get("categoria") or "",
                        "definicion": fila.get("definicion") or "",
                        "precios": []
                    }
                if fila.get("precio_unitario") is not None:
                    tmp[clave]["precios"].append({
                        "proveedor": fila.get("proveedor") or "",
                        "precio": _to_float_seguro(fila.get("precio_unitario")),
                    })
            materiales = list(tmp.values())
        finally:
            conn.close()

    faenas_activas = [f for f in faenas if int(_to_float_seguro(f.get("archivada"))) == 0]
    total_activas = sum(_to_float_seguro(f.get("importe")) for f in faenas_activas)
    total_global = sum(_to_float_seguro(f.get("importe")) for f in faenas)
    faena_seleccionada = next((f for f in faenas if str(f.get("id")) == str(faena_id)), None) if faena_id else None

    if faena_seleccionada and any(k in txt for k in ["presupuesto", "importe", "cuanto cuesta", "cuanto es"]):
        return (
            f"El presupuesto de la faena {faena_seleccionada.get('numero', '')}"
            f" de {faena_seleccionada.get('cliente_nombre', 'sin cliente')}"
            f" ({faena_seleccionada.get('tipo_trabajo', faena_seleccionada.get('trabajo', 'sin tipo'))})"
            f" es de {_to_float_seguro(faena_seleccionada.get('importe')):.2f} EUR."
        )

    if faena_seleccionada and any(k in txt for k in ["direccion", "dirección", "donde", "dónde"]):
        direccion_sel = (faena_seleccionada.get("direccion") or "").strip()
        if direccion_sel:
            return f"La dirección de {faena_seleccionada.get('cliente_nombre', 'esa faena')} es: {direccion_sel}."
        return f"No tengo dirección guardada para {faena_seleccionada.get('cliente_nombre', 'esa faena')}."

    if any(k in txt for k in ["presupuesto", "importe", "cuanto cuesta", "cuanto es"]) and any(k in txt for k in ["puri", "armario", "maria", "jose", "susana"]):
        faenas_db = _buscar_faenas_db()
        tokens = _tokens_pregunta(pregunta)
        match = _mejor_faena_para_tokens(faenas_db, tokens, exigir_tipo=("armario" in _normalizar_texto_busqueda(pregunta)))
        if match:
            return (
                f"El presupuesto de la faena {match.get('numero', '')}"
                f" de {match.get('cliente_nombre', 'sin cliente')}"
                f" ({match.get('tipo_trabajo', 'sin tipo')}) es de {_to_float_seguro(match.get('importe')):.2f} EUR."
            )

    if any(k in txt for k in ["direccion", "dirección", "donde", "dónde"]):
        faenas_db = _buscar_faenas_db()
        tokens = _tokens_pregunta(pregunta)
        match = _mejor_faena_para_tokens(faenas_db, tokens)
        if match:
            direccion = (match.get("direccion") or "").strip()
            if direccion:
                return f"La dirección de {match.get('cliente_nombre', 'ese cliente')} es: {direccion}."
            return f"No tengo dirección guardada para {match.get('cliente_nombre', 'ese cliente')}."

    if any(k in txt for k in ["cuánto he cobrado", "cuanto he cobrado", "total cobrado", "importe total", "he cobrado en total"]):
        respuesta = (
            f"Total cobrado en faenas activas: {total_activas:.2f} EUR.\n"
            f"Total acumulado (activas + archivadas): {total_global:.2f} EUR.\n"
            f"Faenas activas: {len(faenas_activas)} de {len(faenas)} en total."
        )
        _guardar_memoria_ia(pregunta, respuesta, contexto_tipo=contexto_tipo, alcance=alcance, faena_id=faena_id or 0)
        return respuesta

    if ("faena" in txt or "faenas" in txt) and any(k in txt for k in ["tiene", "tengo", "de", "del"]):
        tokens = _tokens_pregunta(pregunta)
        candidatas = []
        for faena in faenas:
            cliente = _normalizar_texto_busqueda(faena.get("cliente_nombre") or faena.get("cliente") or "")
            trabajo = _normalizar_texto_busqueda(faena.get("tipo_trabajo") or faena.get("trabajo") or "")
            numero = _normalizar_texto_busqueda(faena.get("numero") or "")
            score = 0
            for tk in tokens:
                if tk in cliente:
                    score += 3
                if tk in trabajo:
                    score += 1
                if tk in numero:
                    score += 1
            if score > 0:
                candidatas.append((score, faena))

        if candidatas:
            candidatas.sort(key=lambda item: (-item[0], -(item[1].get("id") or 0)))
            mejor_score = candidatas[0][0]
            faenas_cliente = [f for score, f in candidatas if score == mejor_score]
            nombre_cliente = faenas_cliente[0].get("cliente_nombre") or faenas_cliente[0].get("cliente") or "ese cliente"
            lineas = [
                f"- {f.get('numero', '')} | {f.get('tipo_trabajo', f.get('trabajo', 'Sin descripción'))} | {_to_float_seguro(f.get('importe')):.2f} EUR"
                for f in faenas_cliente[:10]
            ]
            extra = "" if len(faenas_cliente) <= 10 else f"\nY {len(faenas_cliente) - 10} más."
            respuesta = f"{nombre_cliente} tiene {len(faenas_cliente)} faena(s):\n" + "\n".join(lineas) + extra
            _guardar_memoria_ia(pregunta, respuesta, contexto_tipo=contexto_tipo, alcance=alcance, faena_id=faena_id or 0)
            return respuesta

    if ("faena" in txt or "faenas" in txt) and any(k in txt for k in ["activ", "pendient", "no archiv", "abierta"]):
        if not faenas_activas:
            return "No hay faenas activas ahora mismo."
        top = faenas_activas[:8]
        lineas = [f"- {f.get('numero', '')} | {f.get('cliente_nombre', '')} | {f.get('tipo_trabajo', '')}" for f in top]
        extra = "" if len(faenas_activas) <= len(top) else f"\nY {len(faenas_activas) - len(top)} más."
        respuesta = "Faenas activas:\n" + "\n".join(lineas) + extra
        _guardar_memoria_ia(pregunta, respuesta, contexto_tipo=contexto_tipo, alcance=alcance, faena_id=faena_id or 0)
        return respuesta

    if any(k in txt for k in ["cliente con más faenas", "cliente con mas faenas", "mejor cliente", "cliente más activo", "cliente mas activo"]):
        conteo = {}
        for f in faenas_activas or faenas:
            nombre = (f.get("cliente_nombre") or f.get("cliente") or "Sin cliente").strip() or "Sin cliente"
            conteo[nombre] = conteo.get(nombre, 0) + 1
        if not conteo:
            return "No hay datos de clientes suficientes para calcularlo."
        cliente, cantidad = sorted(conteo.items(), key=lambda x: x[1], reverse=True)[0]
        respuesta = f"El cliente con más faenas es {cliente} con {cantidad} faena(s)."
        _guardar_memoria_ia(pregunta, respuesta, contexto_tipo=contexto_tipo, alcance=alcance, faena_id=faena_id or 0)
        return respuesta

    tokens_material = [
        tk for tk in _tokens_pregunta(pregunta)
        if tk not in {"material", "materiales", "precio", "precios", "coste", "costo", "cuanto", "cuanta", "cuantos", "cuantas", "tiene", "tienen", "hay", "proveedor", "proveedores"}
    ]
    if (contexto_tipo == "materiales" or any(k in txt for k in ["material", "materiales", "precio", "precios", "proveedor", "proveedores"])) and tokens_material:
        coincidencias = []
        for material in materiales:
            precios_material = material.get("precios") or []
            campos = [material.get("nombre"), material.get("categoria"), material.get("definicion")]
            for precio in precios_material:
                campos.extend([precio.get("proveedor"), precio.get("precio"), precio.get("precio_unitario"), precio.get("fecha_actualizacion")])
            texto_material = _normalizar_texto_busqueda(" ".join(str(c or "") for c in campos))
            coincidencias_material = 0
            for token in tokens_material:
                variantes = [token]
                if len(token) > 4 and token.endswith("s"):
                    variantes.append(token[:-1])
                if any(variante in texto_material for variante in variantes):
                    coincidencias_material += 1
            if coincidencias_material:
                coincidencias.append((material, coincidencias_material))
        if coincidencias:
            coincidencias.sort(key=lambda item: (-item[1], str(item[0].get("nombre") or "").lower()))
            lineas = []
            for material, _ in coincidencias[:15]:
                precios = material.get("precios") or []
                detalle = ", ".join(
                    f"{p.get('proveedor') or 'sin proveedor'}: {_to_float_seguro(p.get('precio') if 'precio' in p else p.get('precio_unitario')):.2f} EUR"
                    for p in precios
                ) or "sin precio registrado"
                lineas.append(f"- {material.get('nombre') or 'Sin nombre'} | {material.get('categoria') or 'Sin categoría'} | {detalle}")
            respuesta = "Materiales encontrados:\n" + "\n".join(lineas)
            _guardar_memoria_ia(pregunta, respuesta, contexto_tipo=contexto_tipo, alcance=alcance, faena_id=faena_id or 0)
            return respuesta

    if any(k in txt for k in ["material", "materiales"]) and any(k in txt for k in ["caro", "caros", "más caro", "mas caro", "precio"]):
        ranking = []
        for m in materiales:
            nombre = (m.get("nombre") or "").strip()
            if not nombre:
                continue
            for p in (m.get("precios") or []):
                precio = _to_float_seguro(p.get("precio") if "precio" in p else p.get("precio_unitario"))
                if precio > 0:
                    ranking.append((precio, nombre, p.get("proveedor") or ""))
        if not ranking:
            return "No hay precios registrados para calcular materiales más caros."
        ranking.sort(reverse=True, key=lambda x: x[0])
        top = ranking[:5]
        lineas = [f"- {nombre}: {precio:.2f} EUR ({proveedor or 'sin proveedor'})" for precio, nombre, proveedor in top]
        respuesta = "Materiales más caros registrados:\n" + "\n".join(lineas)
        _guardar_memoria_ia(pregunta, respuesta, contexto_tipo=contexto_tipo, alcance=alcance, faena_id=faena_id or 0)
        return respuesta

    tokens_trabajo = [
        tk for tk in _tokens_pregunta(pregunta)
        if tk not in {"trabajo", "trabajos", "faena", "faenas", "datos", "general"}
    ]
    if contexto_tipo in {"general", "trabajos"} and tokens_trabajo:
        coincidencias_trabajo = []
        for faena in faenas:
            texto_faena = _normalizar_texto_busqueda(json.dumps(faena, ensure_ascii=False))
            coincidencias = sum(1 for token in tokens_trabajo if token in texto_faena or (token.endswith("s") and token[:-1] in texto_faena))
            if coincidencias:
                coincidencias_trabajo.append((faena, coincidencias))
        if coincidencias_trabajo:
            coincidencias_trabajo.sort(key=lambda item: (-item[1], -(int(item[0].get("id") or 0))))
            lineas = []
            for faena, _ in coincidencias_trabajo[:10]:
                lineas.append(
                    f"- {faena.get('numero') or faena.get('id') or ''} | "
                    f"{faena.get('cliente_nombre') or 'Sin cliente'} | "
                    f"{faena.get('tipo_trabajo') or faena.get('trabajo') or 'Sin trabajo'} | "
                    f"Importe: {_to_float_seguro(faena.get('importe')):.2f} EUR"
                )
            respuesta = "Trabajos encontrados:\n" + "\n".join(lineas)
            _guardar_memoria_ia(pregunta, respuesta, contexto_tipo=contexto_tipo, alcance=alcance, faena_id=faena_id or 0)
            return respuesta

    if faena_id:
        faena = next((f for f in faenas if str(f.get("id")) == str(faena_id)), None)
        if faena:
            respuesta = (
                "Resumen de la faena seleccionada:\n"
                f"- Número: {faena.get('numero', '')}\n"
                f"- Cliente: {faena.get('cliente_nombre', '')}\n"
                f"- Trabajo: {faena.get('tipo_trabajo', '')}\n"
                f"- Importe: {_to_float_seguro(faena.get('importe')):.2f} EUR"
            )
            _guardar_memoria_ia(pregunta, respuesta, contexto_tipo=contexto_tipo, alcance=alcance, faena_id=faena_id or 0)
            return respuesta

    respuesta = (
        "Puedo ayudarte con estas consultas:\n"
        "- Cuánto has cobrado (activas y total).\n"
        "- Qué faenas siguen activas.\n"
        "- Qué cliente tiene más faenas.\n"
        "- Materiales más caros según precios registrados."
    )
    _guardar_memoria_ia(pregunta, respuesta, contexto_tipo=contexto_tipo, alcance=alcance, faena_id=faena_id or 0)
    return respuesta


def _respuesta_ia_cloud(pregunta, contexto, faena_id=None):
    if not IA_API_KEY:
        raise RuntimeError("No hay API key configurada")
    if _ia_provider_activo() == "gemini":
        raw = _peticion_gemini(
            contents=[
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "pregunta": pregunta,
                                    "faena_id": faena_id,
                                    "contexto": contexto,
                                },
                                ensure_ascii=False,
                            )
                        }
                    ],
                }
            ],
            system_instruction=(
                "Eres un asistente general para gestionar faenas de carpinteria. "
                "Responde en espanol, de forma concreta pero flexible, entendiendo preguntas nuevas sin depender de frases prefijadas. "
                "Usa SOLO los datos del contexto aportado. El contexto seleccionado puede ser general, materiales o trabajos. "
                "Si preguntan por materiales o precios, cita material, proveedor y precio. Si preguntan por trabajos, cita faena, cliente, estado, importes y datos relevantes. "
                "Si no hay datos suficientes, dilo claramente y no inventes información."
            ),
            max_tokens=500,
            temperature=0.2,
        )
        return _gemini_extraer_texto(raw)

    raise RuntimeError("Proveedor IA no soportado")


def _leer_texto_documento_para_ia(ruta):
    if not ruta or not os.path.exists(ruta):
        return ""
    ext = os.path.splitext(ruta)[1].lower()
    try:
        if ext in [".txt", ".md", ".csv", ".log"]:
            with open(ruta, "r", encoding="utf-8", errors="ignore") as f:
                return f.read().strip()
        if ext == ".pdf":
            try:
                import fitz
            except Exception:
                return ""
            doc = fitz.open(ruta)
            texto = []
            for page in doc:
                try:
                    texto.append(page.get_text())
                except Exception:
                    pass
            doc.close()
            return "\n".join(texto).strip()
    except Exception:
        return ""
    return ""


def _leer_texto_documento_base64_para_ia(archivo_base64, nombre="", mime_type=""):
    if not archivo_base64:
        return ""
    try:
        bruto = base64.b64decode(limpiar_data_b64(archivo_base64))
    except Exception:
        return ""

    ext = os.path.splitext((nombre or "").strip())[1].lower()
    mime = (mime_type or "").lower().strip()

    if ext == ".pdf" or "pdf" in mime:
        try:
            import fitz
            doc = fitz.open(stream=bruto, filetype="pdf")
            texto = []
            for page in doc:
                try:
                    texto.append(page.get_text())
                except Exception:
                    pass
            doc.close()
            texto_extraido = "\n".join(texto).strip()
            if texto_extraido:
                return texto_extraido

            # Algunos tickets son PDFs escaneados y no tienen capa de texto.
            # Renderizamos solo las primeras paginas para mantener el tiempo bajo control.
            if pytesseract is None or Image is None:
                return ""
            doc = fitz.open(stream=bruto, filetype="pdf")
            paginas_ocr = []
            for indice, page in enumerate(doc):
                if indice >= 3:
                    break
                try:
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    imagen = Image.open(io.BytesIO(pixmap.tobytes("png")))
                    ocr = _texto_ocr_desde_imagen_base64(
                        "data:image/png;base64," + base64.b64encode(pixmap.tobytes("png")).decode("ascii")
                    )
                    if ocr:
                        paginas_ocr.append(ocr)
                except Exception:
                    continue
            doc.close()
            return "\n\n".join(paginas_ocr).strip()
        except Exception:
            return ""

    for enc in ("utf-8", "latin-1"):
        try:
            return bruto.decode(enc, errors="ignore").strip()
        except Exception:
            continue
    return ""


def _primera_pagina_pdf_base64(archivo_base64, nombre="", mime_type=""):
    if not archivo_base64:
        return ""
    ext = os.path.splitext((nombre or "").strip())[1].lower()
    if ext != ".pdf" and "pdf" not in (mime_type or "").lower():
        return ""
    try:
        import fitz
        bruto = base64.b64decode(limpiar_data_b64(archivo_base64))
        doc = fitz.open(stream=bruto, filetype="pdf")
        if not len(doc):
            return ""
        pixmap = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        imagen = base64.b64encode(pixmap.tobytes("jpg")).decode("ascii")
        doc.close()
        return "data:image/jpeg;base64," + imagen
    except Exception:
        return ""


def _texto_ocr_desde_imagen_base64(data_b64):
    if not data_b64 or pytesseract is None or Image is None:
        return ""
    try:
        bruto = limpiar_data_b64(data_b64)
        img_bytes = base64.b64decode(bruto)
        img = Image.open(io.BytesIO(img_bytes))
        variantes = [img]
        try:
            gris = ImageOps.grayscale(img) if ImageOps is not None else img
            if ImageEnhance is not None:
                gris = ImageEnhance.Contrast(gris).enhance(1.8)
            variantes.append(gris)
        except Exception:
            pass

        mejor = ""
        for v in variantes:
            for lang in ["spa+eng", "eng"]:
                try:
                    txt = pytesseract.image_to_string(v, lang=lang, timeout=8)
                    if txt and len(txt) > len(mejor):
                        mejor = txt
                except Exception:
                    continue
        return (mejor or "").strip()
    except Exception:
        return ""


def _json_ticket_desde_ocr(texto):
    if not texto:
        return None
    lineas = [re.sub(r"\s+", " ", l).strip() for l in (texto or "").splitlines()]
    lineas = [l for l in lineas if l]
    if not lineas:
        return None

    proveedor = None
    for l in lineas[:8]:
        if any(ch.isalpha() for ch in l) and not re.search(r"\d{2,}", l):
            proveedor = l[:120]
            break
    if not proveedor:
        proveedor = lineas[0][:120]

    fecha = None
    m_fecha = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", texto)
    if m_fecha:
        fecha = m_fecha.group(1)

    total_ticket = None
    for l in lineas:
        if "total" in l.lower():
            nums = re.findall(r"\d+[.,]\d{2}", l)
            if nums:
                total_ticket = _parse_numero(nums[-1])
                break
    if total_ticket is None:
        todos = re.findall(r"\d+[.,]\d{2}", texto)
        if todos:
            total_ticket = _parse_numero(todos[-1])

    articulos = []
    for l in lineas:
        if " x " not in l.lower() and not re.search(r"\bx\b", l.lower()):
            continue
        qty_m = re.search(r"(\d+(?:[.,]\d+)?)\s*x", l.lower())
        if not qty_m:
            continue
        qty = _parse_numero(qty_m.group(1))
        decs = re.findall(r"\d+[.,]\d{2}", l)
        if not decs:
            continue
        precio_unitario = _parse_numero(decs[0])
        total = _parse_numero(decs[-1]) if len(decs) > 1 else round(qty * precio_unitario, 2)
        nombre = re.sub(r"\s+\d+(?:[.,]\d+)?\s*x.*$", "", l, flags=re.IGNORECASE).strip(" -:\t")
        if not nombre or len(nombre) < 2:
            continue
        articulos.append({
            "nombre": nombre,
            "cantidad": qty or 1,
            "precio_unitario": precio_unitario,
            "total": total,
            "unidad": "ud",
        })

    if not articulos:
        return None
    return {
        "proveedor": proveedor,
        "fecha": fecha,
        "total_ticket": total_ticket,
        "articulos": articulos,
    }


def _extraer_materiales_json_con_ia(prompt, texto=None, imagen=None, tipo="ticket"):
    instrucciones = prompt or ""
    esquema = {
        "type": "object",
        "properties": {
            "proveedor": {"type": ["string", "null"]},
            "fecha": {"type": ["string", "null"]},
            "total_ticket": {"type": ["number", "integer", "null"]},
            "articulos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "nombre": {"type": "string"},
                        "cantidad": {"type": ["number", "integer", "null"]},
                        "precio_unitario": {"type": ["number", "integer", "null"]},
                        "total": {"type": ["number", "integer", "null"]},
                        "unidad": {"type": ["string", "null"]},
                    },
                    "required": ["nombre"],
                },
            },
        },
        "required": ["articulos"],
    }

    system = (
        f"Eres un extractor de materiales desde {tipo}. Devuelve SOLO JSON válido, sin texto extra. "
        "Usa este formato: {proveedor, fecha, total_ticket, articulos:[{nombre,cantidad,precio_unitario,total,unidad}]}. "
        "Si un campo no existe, usa null. Normaliza nombres de artículos."
    )
    user_txt = instrucciones.strip()
    if texto:
        user_txt += "\n\nTEXTO:\n" + texto.strip()
    if imagen:
        user_content = [
            {"type": "text", "text": user_txt or "Extrae los materiales del ticket."},
            {"type": "image_url", "image_url": {"url": imagen, "detail": "high"}},
        ]
    else:
        user_content = user_txt or "Extrae los materiales y devuelve JSON válido."

    ticket_key = TICKET_IA_API_KEY or IA_API_KEY
    ticket_model = TICKET_IA_MODEL or IA_MODEL
    if ticket_key and _ia_provider_activo() == "gemini":
        contents = [
            {
                "role": "user",
                "parts": [
                    {"text": user_txt or "Extrae los materiales y devuelve JSON válido."},
                ] + ([ _gemini_imagen_part(imagen) ] if imagen else []),
            }
        ]
        contents[0]["parts"] = [p for p in contents[0]["parts"] if p]
        try:
            raw = _peticion_gemini(
                contents=contents,
                system_instruction=system,
                response_mime_type="application/json",
                max_tokens=1200,
                temperature=0,
                api_key=ticket_key,
                model=ticket_model,
                timeout=15 if tipo in {"ticket", "documento"} and imagen else 90,
            )
            contenido = _gemini_extraer_texto(raw)
            data = _extraer_json_de_texto(contenido)
            if not isinstance(data, dict) and tipo != "ticket":
                data = _normalizar_json_materiales_con_ia(contenido, tipo=tipo, api_key=ticket_key, model=ticket_model)
            if isinstance(data, dict):
                return data
        except Exception as e:
            mensaje = str(e).lower()
            is_timeout = any(k in mensaje for k in ["timeout", "timed out", "time out", "socket timeout", "read timed out"])
            is_quota = any(k in mensaje for k in ["429", "quota", "rate limit", "rate", "too many requests"])
            is_unavailable = any(k in mensaje for k in ["503", "service unavailable", "temporarily unavailable", "currently experiencing high demand"])
            if not (is_timeout or is_quota or is_unavailable):
                raise
            # Fallback local cuando Gemini tarda demasiado o se queda sin cuota.
            if imagen:
                texto_ocr = _texto_ocr_desde_imagen_base64(imagen)
                data = _json_ticket_desde_ocr(texto_ocr)
                if isinstance(data, dict):
                    return data
            if texto:
                data = _json_ticket_desde_ocr(texto)
                if isinstance(data, dict):
                    return data
            data = _extraer_json_de_texto(texto or user_txt or "")
            if isinstance(data, dict):
                return data
            if tipo in {"ticket", "documento"}:
                return {"proveedor": None, "fecha": None, "total_ticket": None, "articulos": [], "fallback_local": True}
            if is_timeout:
                raise RuntimeError(f"La IA tardó demasiado en responder. Se intentó fallback local y no pudo extraer artículos. {e}")
            raise RuntimeError(f"La IA no devolvió JSON válido. Fallback local insuficiente. {e}")
        if imagen:
            texto_ocr = _texto_ocr_desde_imagen_base64(imagen)
            data = _json_ticket_desde_ocr(texto_ocr)
            if isinstance(data, dict):
                return data
        if texto:
            data = _json_ticket_desde_ocr(texto)
            if isinstance(data, dict):
                return data
        if tipo in {"ticket", "documento"}:
            return {"proveedor": None, "fecha": None, "total_ticket": None, "articulos": [], "fallback_local": True}
        raise RuntimeError("La IA no devolvió JSON válido")

    # Fallback local con Ollama
    mensajes = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_txt or "Extrae los materiales y devuelve JSON válido."},
    ]
    if imagen:
        mensajes[-1]["images"] = [imagen]
    respuesta = ollama_chat(mensajes, format_schema=esquema)
    contenido = ((respuesta.get("message") or {}).get("content") or "").strip()
    data = _extraer_json_de_texto(contenido)
    if not isinstance(data, dict):
        raise RuntimeError("La IA no devolvió JSON válido")
    return data


# -------------------- JIMMI --------------------
@app.route("/api/secretario/chat", methods=["POST"])
def secretario_chat():
    datos = request.json or {}
    pregunta = (datos.get("pregunta") or datos.get("mensaje") or "").strip()
    historial = datos.get("historial") if isinstance(datos.get("historial"), list) else []
    faena_id = _parse_faena_id_seguro(datos.get("faena_id"))
    try:
        res = chat_jimmi(pregunta, historial=historial, faena_id=faena_id)
        if not res.get("ok"):
            return jsonify(res), 400
        return jsonify(res)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Jimmi: {str(e)}"}), 500


@app.route("/api/secretario/cruzar", methods=["POST"])
def secretario_cruzar():
    datos = request.json or {}
    articulos = datos.get("articulos") or []
    try:
        return jsonify({"ok": True, "data": cruzar_articulos(articulos)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/secretario/aplicar", methods=["POST"])
def secretario_aplicar():
    datos = request.json or {}
    tipo = (datos.get("tipo") or "ticket").strip().lower()
    try:
        if tipo in {"ticket", "almacen", "gastos"}:
            faena_id = _parse_faena_id_seguro(datos.get("faena_id")) if tipo != "almacen" else None
            payload = datos.get("data") or datos
            if isinstance(payload, str):
                payload = _extraer_json_de_texto(payload)
            articulos = payload.get("articulos") if isinstance(payload, dict) else []
            if not articulos and isinstance(datos.get("articulos"), list):
                articulos = datos.get("articulos")
                payload = {"articulos": articulos, "proveedor": datos.get("proveedor") or ""}
            origen = "ticket" if tipo != "almacen" else "almacen"
            resumen = _persistir_resultado_ia_en_nube(faena_id, origen, payload if isinstance(payload, dict) else {"articulos": articulos})
            destino = f"faena {faena_id}" if faena_id else "almacén"
            anotar_contexto(f"Aceptó ticket → {destino}: {resumen.get('gastos_creados', 0)} gastos, {resumen.get('materiales_creados', 0)} materiales nuevos, {resumen.get('precios_actualizados', 0)} precios")
            return jsonify({"ok": True, "data": resumen})
        if tipo == "presupuesto":
            faena_id = _parse_faena_id_seguro(datos.get("faena_id"))
            if not faena_id:
                return jsonify({"ok": False, "error": "Falta la faena"}), 400
            desc = str(datos.get("descripcion") or "").strip()
            cantidad = _to_float_seguro(datos.get("cantidad") or 1)
            precio = _to_float_seguro(datos.get("precio_unitario") or 0)
            total = cantidad * precio
            conn = get_connection()
            conn.execute(
                "INSERT INTO presupuestos_faena (faena_id, tipo, descripcion, cantidad, precio_unitario, total) VALUES (?, ?, ?, ?, ?, ?)",
                (faena_id, "presupuesto", desc, cantidad, precio, total),
            )
            conn.commit()
            conn.close()
            anotar_contexto(f"Aceptó partida de presupuesto en faena {faena_id}: {desc} {total:.2f} €")
            return jsonify({"ok": True, "data": {"faena_id": faena_id}})
        return jsonify({"ok": False, "error": "Tipo no reconocido"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/ollama/consulta", methods=["POST"])
@app.route("/api/ia/consulta", methods=["POST"])
def ollama_consulta():
    datos = request.json or {}
    pregunta = (datos.get("pregunta") or "").strip()
    faena_id = datos.get("faena_id")
    contexto = datos.get("contexto") if isinstance(datos.get("contexto"), dict) else {}
    contexto_tipo = (datos.get("contexto_tipo") or contexto.get("contexto_tipo") or contexto.get("tipo") or "general")
    alcance = (datos.get("alcance") or contexto.get("alcance") or "general")
    if not pregunta:
        return jsonify({"ok": False, "error": "Falta la pregunta"}), 400

    try:
        consulta_proveedor_material = (
            str(contexto_tipo).lower() == "materiales"
            and any(k in pregunta.lower() for k in ["material", "materiales"])
            and any(k in pregunta.lower() for k in ["tiene", "tienen", "hay", "proveedor"])
        )
        if consulta_proveedor_material:
            texto = _respuesta_ia_local(pregunta, contexto, faena_id=faena_id)
            _guardar_memoria_ia(pregunta, texto, contexto_tipo=contexto_tipo, alcance=alcance, faena_id=faena_id or 0)
            return jsonify({"ok": True, "data": {"respuesta": texto, "motor": "local_catalogo"}})

        if IA_API_KEY and _ia_provider_activo() == "gemini":
            try:
                texto = _respuesta_ia_cloud(pregunta, contexto, faena_id=faena_id)
                _guardar_memoria_ia(pregunta, texto, contexto_tipo=contexto_tipo, alcance=alcance, faena_id=faena_id or 0, fuente="api_key")
                return jsonify({"ok": True, "data": {"respuesta": texto, "motor": "api_key"}})
            except Exception as e_cloud:
                # Fallback seguro para no cortar la funcionalidad de consulta.
                texto = _respuesta_ia_local(pregunta, contexto, faena_id=faena_id)
                return jsonify({"ok": True, "data": {"respuesta": texto, "motor": "local_fallback", "detalle": str(e_cloud)}})

        texto = _respuesta_ia_local(pregunta, contexto, faena_id=faena_id)
        return jsonify({"ok": True, "data": {"respuesta": texto, "motor": "local"}})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Error en consulta IA: {str(e)}"}), 500


@app.route("/api/ia/procesar-texto", methods=["POST"])
def ia_procesar_texto():
    datos = request.json or {}
    texto = (datos.get("texto") or "").strip()
    prompt = (datos.get("prompt") or "").strip()
    tipo_fuente = (datos.get("tipo_fuente") or "texto").strip()
    faena_id = _parse_faena_id_seguro(datos.get("faena_id"))
    guardar = _parse_bool_seguro(datos.get("guardar"), True)
    if not texto:
        return jsonify({"ok": False, "error": "Falta el texto"}), 400
    try:
        prompt_base = prompt or _prompt_ticket_base()
        data = _extraer_materiales_json_con_ia(prompt_base, texto=texto, tipo="texto")
        articulos = data.get("articulos") or []
        data["articulos"] = [_normalizar_articulo(a) for a in articulos if isinstance(a, dict) and (a.get("nombre") or "").strip()]
        data["tipo_fuente"] = tipo_fuente
        data["guardado_en_nube"] = guardar
        if guardar:
            data["resumen_guardado"] = _persistir_resultado_ia_en_nube(faena_id, "texto", data)
        return jsonify({"ok": True, "data": data})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Error procesando texto con IA: {str(e)}"}), 502


@app.route("/api/ia/procesar-ticket", methods=["POST"])
def ia_procesar_ticket():
    datos = request.json or {}
    imagen = datos.get("imagen") or datos.get("ticketFotoBase64") or datos.get("data")
    imagen = limpiar_data_b64(imagen)
    prompt = (datos.get("prompt") or "").strip()
    faena_id = _parse_faena_id_seguro(datos.get("faena_id"))
    guardar = _parse_bool_seguro(datos.get("guardar"), True)
    if not imagen:
        return jsonify({"ok": False, "error": "Falta la imagen del ticket"}), 400
    try:
        prompt_base = prompt or _prompt_ticket_base()
        data = _extraer_materiales_json_con_ia(prompt_base, imagen=imagen, tipo="ticket")
        articulos = data.get("articulos") or []
        data["articulos"] = [_normalizar_articulo(a) for a in articulos if isinstance(a, dict) and (a.get("nombre") or "").strip()]
        data["tipo_fuente"] = "ticket"
        data["guardado_en_nube"] = guardar
        if guardar:
            data["resumen_guardado"] = _persistir_resultado_ia_en_nube(faena_id, "ticket", data)
        return jsonify({"ok": True, "data": data})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Error procesando ticket con IA: {str(e)}"}), 502


@app.route("/api/ia/procesar-documento", methods=["POST"])
def ia_procesar_documento():
    datos = request.json or {}
    texto = (datos.get("texto") or "").strip()
    ruta = (datos.get("ruta") or "").strip()
    nombre = (datos.get("nombre") or "documento").strip()
    prompt = (datos.get("prompt") or "").strip()
    faena_id = _parse_faena_id_seguro(datos.get("faena_id"))
    guardar = _parse_bool_seguro(datos.get("guardar"), True)
    archivo_base64 = (datos.get("archivo_base64") or datos.get("archivo") or datos.get("data") or "").strip()
    mime_type = (datos.get("mime_type") or datos.get("mime") or "").strip()
    if not texto and ruta:
        texto = _leer_texto_documento_para_ia(ruta)
    if not texto and archivo_base64:
        texto = _leer_texto_documento_base64_para_ia(archivo_base64, nombre=nombre, mime_type=mime_type)
    imagen_documento = ""
    if not texto and archivo_base64:
        imagen_documento = _primera_pagina_pdf_base64(archivo_base64, nombre=nombre, mime_type=mime_type)
    if not texto and not imagen_documento:
        return jsonify({"ok": False, "error": "No se pudo leer el PDF. Prueba con una foto del ticket o un PDF con OCR."}), 400
    try:
        prompt_base = prompt or _prompt_documento_base(nombre)
        data = _extraer_materiales_json_con_ia(
            prompt_base,
            texto=texto,
            imagen=imagen_documento or None,
            tipo="documento",
        )
        articulos = data.get("articulos") or []
        data["articulos"] = [_normalizar_articulo(a) for a in articulos if isinstance(a, dict) and (a.get("nombre") or "").strip()]
        data["tipo_fuente"] = "documento"
        data["nombre_documento"] = nombre
        data["guardado_en_nube"] = guardar
        if guardar:
            data["resumen_guardado"] = _persistir_resultado_ia_en_nube(faena_id, "pdf", data)
        return jsonify({"ok": True, "data": data})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Error procesando documento con IA: {str(e)}"}), 502


@app.route("/api/ia/guardar-json", methods=["POST"])
def ia_guardar_json():
    try:
        datos = request.json or {}
        origen = (datos.get("origen") or "ticket").strip().lower()
        faena_id = _parse_faena_id_seguro(datos.get("faena_id"))
        payload = datos.get("data")
        if isinstance(payload, str):
            payload = _extraer_json_de_texto(payload)
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "Falta JSON válido en data"}), 400
        articulos = payload.get("articulos") or []
        payload["articulos"] = [_normalizar_articulo(a) for a in articulos if isinstance(a, dict) and (a.get("nombre") or "").strip()]
        if not payload["articulos"]:
            return jsonify({"ok": False, "error": "No hay artículos para guardar"}), 400
        resumen = _persistir_resultado_ia_en_nube(faena_id, origen, payload)
        return jsonify({"ok": True, "data": {"resumen_guardado": resumen}})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Error guardando en nube: {str(e)}"}), 502

# -------------------- SINCRONIZACIÓN WiFi --------------------
@app.route("/api/sync/estado", methods=["GET"])
def sync_estado():
    return jsonify({
        "ok": True,
        "data": {
            "estado": "disponible",
            "r2": r2_listo(),
            "r2_error": r2_error(),
        },
    })

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
        faena["fotos"] = []
        resultado.append(faena)
    if resultado:
        ids = [f["id"] for f in resultado]
        placeholders = ",".join(["?"] * len(ids))
        filas_fotos = conn.execute(
            f"SELECT * FROM fotos_faena WHERE faena_id IN ({placeholders}) ORDER BY id ASC",
            ids,
        ).fetchall()
        por_faena = {}
        for fila in filas_a_lista(filas_fotos):
            por_faena.setdefault(fila.get("faena_id"), []).append(_payload_foto(fila))
        for faena in resultado:
            faena["fotos"] = por_faena.get(faena["id"], [])
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
    nombre_original = datos.get("nombre") or f"foto_{int(time.time())}.jpg"
    data_b64 = datos.get("data", "")
    if not faena_id or not data_b64:
        return jsonify({"ok": False, "error": "Faltan datos"}), 400
    conn = get_connection()
    faena = conn.execute("SELECT numero, carpeta FROM faenas WHERE id=?", (faena_id,)).fetchone()
    if not faena:
        conn.close()
        return jsonify({"ok": False, "error": "Faena no encontrada"}), 404
    if not faena["carpeta"] and not r2_activo():
        conn.close()
        return jsonify({"ok": False, "error": "Faena o carpeta no encontrada"}), 404

    total_previas = conn.execute(
        "SELECT COUNT(*) AS n FROM fotos_faena WHERE faena_id=?", (faena_id,)
    ).fetchone()["n"]
    ext = os.path.splitext(nombre_original)[1].lower() or ".jpg"
    numero_faena = (faena["numero"] or str(faena_id)).strip()
    nombre = f"{numero_faena}_{int(total_previas) + 1:03d}{ext}"

    if "," in data_b64:
        data_b64 = data_b64.split(",")[1]
    img_bytes = base64.b64decode(data_b64)
    try:
        ruta, object_key, _url, _backend = _guardar_binario(fila_a_dict(faena), "fotos", nombre, img_bytes, _mime_archivo(nombre))
    except Exception as exc:
        conn.close()
        return jsonify({"ok": False, "error": str(exc)}), 500

    conn.execute(
        "INSERT INTO fotos_faena (faena_id, nombre, ruta_foto, data_base64, fecha) VALUES (?, ?, ?, ?, datetime('now'))",
        (faena_id, nombre, object_key or ruta, ""),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "data": {"ruta": object_key or ruta, "nombre": nombre}})

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
            item["data"] = _url_desde_ruta(ruta)
        resultado.append(item)
    conn.close()
    return jsonify({"ok": True, "data": resultado})

# -------------------- FOTOS DE FAENA (PC) --------------------
def _mime_por_extension(nombre):
    ext = os.path.splitext(nombre or "")[1].lower()
    return {".png": "image/png", ".webp": "image/webp", ".jpeg": "image/jpeg"}.get(ext, "image/jpeg")


@app.route("/api/faenas/<int:id>/fotos", methods=["GET"])
def listar_fotos(id):
    import base64
    conn = _conn_para_faena(id)
    faena = conn.execute("SELECT carpeta FROM faenas WHERE id=?", (id,)).fetchone()
    if not faena:
        conn.close()
        return jsonify({"ok": False, "error": "Faena no encontrada"}), 404

    filas = conn.execute(
        "SELECT * FROM fotos_faena WHERE faena_id=? ORDER BY id ASC", (id,)
    ).fetchall()
    fotos = [_payload_foto(fila) for fila in filas_a_lista(filas)]

    # Compatibilidad: fotos que ya existan en el disco pero no en la BD (subidas antiguas).
    if faena["carpeta"]:
        carpeta_fotos = os.path.join(faena["carpeta"], "fotos")
        if os.path.exists(carpeta_fotos):
            registrados = {f["nombre"] for f in fotos}
            extensiones = {".jpg", ".jpeg", ".png", ".webp"}
            for nombre in sorted(os.listdir(carpeta_fotos)):
                if nombre in registrados or os.path.splitext(nombre)[1].lower() not in extensiones:
                    continue
                ruta = os.path.join(carpeta_fotos, nombre)
                try:
                    with open(ruta, "rb") as f:
                        data = f"data:{_mime_por_extension(nombre)};base64," + base64.b64encode(f.read()).decode()
                except Exception:
                    continue
                fotos.append({"id": None, "nombre": nombre, "ruta": ruta, "data": data})

    conn.close()
    return jsonify({"ok": True, "data": fotos})

@app.route("/api/faenas/<int:id>/fotos/<path:nombre>", methods=["DELETE"])
def eliminar_foto(id, nombre):
    conn = get_connection()
    faena = conn.execute("SELECT carpeta FROM faenas WHERE id=?", (id,)).fetchone()
    if not faena:
        conn.close()
        return jsonify({"ok": False, "error": "Faena no encontrada"}), 404
    fila_foto = conn.execute(
        "SELECT ruta_foto FROM fotos_faena WHERE faena_id=? AND nombre=?", (id, nombre)
    ).fetchone()
    ruta_foto = fila_foto["ruta_foto"] if fila_foto else ""
    conn.execute("DELETE FROM fotos_faena WHERE faena_id=? AND nombre=?", (id, nombre))
    conn.commit()
    conn.close()
    _borrar_binario(ruta_foto, ruta_foto)
    if faena["carpeta"]:
        ruta = os.path.join(faena["carpeta"], "fotos", nombre)
        if os.path.exists(ruta):
            os.remove(ruta)
    return jsonify({"ok": True})

@app.route("/api/faenas/<int:id>/fotos/carpeta", methods=["POST"])
def abrir_carpeta_fotos(id):
    conn = _conn_para_faena(id)
    faena = conn.execute("SELECT carpeta FROM faenas WHERE id=?", (id,)).fetchone()
    conn.close()
    if not faena:
        return jsonify({"ok": False, "error": "Faena no encontrada"}), 404
    if os.name != "nt" or not faena["carpeta"]:
        return jsonify({"ok": False, "error": "Las fotos están en Cloudflare. Ábrelas desde esta pantalla."}), 400
    carpeta_fotos = os.path.join(faena["carpeta"], "fotos")
    os.makedirs(carpeta_fotos, exist_ok=True)
    subprocess.Popen(["explorer", carpeta_fotos])
    return jsonify({"ok": True})

# -------------------- DOCUMENTOS --------------------
@app.route("/api/faenas/<int:id>/documentos", methods=["GET"])
def listar_documentos(id):
    conn = _conn_para_faena(id)
    faena = conn.execute("SELECT carpeta FROM faenas WHERE id=?", (id,)).fetchone()
    if not faena:
        conn.close()
        return jsonify({"ok": False, "error": "Faena no encontrada"}), 404
    vistos = set()
    archivos = []
    try:
        filas = filas_a_lista(conn.execute(
            "SELECT * FROM archivos_faena WHERE faena_id=? ORDER BY id DESC", (id,)
        ).fetchall())
    except Exception:
        filas = []
    conn.close()
    for fila in filas:
        nombre = fila.get("nombre") or ""
        if not nombre or nombre in vistos:
            continue
        vistos.add(nombre)
        archivos.append({
            "id": fila.get("id"),
            "nombre": nombre,
            "ruta": fila.get("public_url") or fila.get("object_key") or "",
            "tamaño": fila.get("tamaño") or 0,
            "fecha": fila.get("fecha") or "",
            "extension": _extension(nombre),
            "storage": fila.get("storage_backend") or "",
            "descarga": f"/api/faenas/{id}/documentos/{nombre}/descargar",
        })
    carpeta = faena["carpeta"] if faena else ""
    if carpeta:
        carpeta_docs = os.path.join(carpeta, "Documentos")
        if os.path.isdir(carpeta_docs):
            for nombre in sorted(os.listdir(carpeta_docs)):
                if nombre in vistos:
                    continue
                ruta = os.path.join(carpeta_docs, nombre)
                if not os.path.isfile(ruta):
                    continue
                vistos.add(nombre)
                stat = os.stat(ruta)
                archivos.append({
                    "nombre": nombre,
                    "ruta": ruta,
                    "tamaño": stat.st_size,
                    "fecha": stat.st_mtime,
                    "extension": _extension(nombre),
                    "storage": "pc",
                    "descarga": f"/api/faenas/{id}/documentos/{nombre}/descargar",
                })
    return jsonify({"ok": True, "data": archivos})

@app.route("/api/faenas/<int:id>/documentos", methods=["POST"])
def subir_documento(id):
    ficheros = request.files.getlist("archivos") or request.files.getlist("file")
    if not ficheros and request.files:
        ficheros = list(request.files.values())
    if not ficheros:
        return jsonify({"ok": False, "error": "Selecciona archivos desde el navegador"}), 400
    conn = get_connection()
    faena = conn.execute("SELECT id, numero, carpeta FROM faenas WHERE id=?", (id,)).fetchone()
    if not faena:
        conn.close()
        return jsonify({"ok": False, "error": "Faena no encontrada"}), 404
    faena_d = fila_a_dict(faena)
    copiados = []
    for fichero in ficheros:
        nombre = os.path.basename(fichero.filename or "")
        if not nombre:
            continue
        data = fichero.read()
        mime = fichero.mimetype or _mime_archivo(nombre)
        if _es_pdf_nombre(nombre) or _es_foto_nombre(nombre):
            tipo = "pdf" if _es_pdf_nombre(nombre) else "foto"
            carpeta_rel = "pdf" if tipo == "pdf" else "fotos"
            try:
                _url, object_key, public_url, backend = _guardar_binario(faena_d, carpeta_rel, nombre, data, mime)
            except Exception as exc:
                conn.close()
                return jsonify({"ok": False, "error": str(exc)}), 500
            _registrar_archivo(conn, id, tipo, nombre, backend, object_key, public_url, mime, len(data))
        else:
            backend = "pc"
            object_key = ""
            public_url = ""
            if r2_activo():
                try:
                    _url, object_key, public_url, backend = _guardar_binario(faena_d, "documentos", nombre, data, mime)
                except Exception:
                    backend = "pc"
                    object_key = ""
                    public_url = ""
            elif faena_d.get("carpeta"):
                destino_dir = os.path.join(faena_d["carpeta"], "Documentos")
                os.makedirs(destino_dir, exist_ok=True)
                with open(os.path.join(destino_dir, nombre), "wb") as fh:
                    fh.write(data)
            _registrar_archivo(conn, id, "documento", nombre, backend, object_key, public_url, mime, len(data))
        copiados.append(nombre)
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "data": {"copiados": copiados, "analisis": []}})

@app.route("/api/faenas/<int:id>/documentos/<path:nombre>", methods=["DELETE"])
def eliminar_documento(id, nombre):
    conn = get_connection()
    faena = conn.execute("SELECT carpeta FROM faenas WHERE id=?", (id,)).fetchone()
    if not faena:
        conn.close()
        return jsonify({"ok": False, "error": "Faena no encontrada"}), 404
    fila = None
    try:
        fila = conn.execute(
            "SELECT * FROM archivos_faena WHERE faena_id=? AND nombre=?", (id, nombre)
        ).fetchone()
    except Exception:
        fila = None
    if fila:
        fila = fila_a_dict(fila)
        _borrar_binario(fila.get("object_key") or "", fila.get("object_key") or "")
        conn.execute("DELETE FROM archivos_faena WHERE faena_id=? AND nombre=?", (id, nombre))
        conn.commit()
    conn.close()
    if faena["carpeta"]:
        ruta = os.path.join(faena["carpeta"], "Documentos", nombre)
        if os.path.exists(ruta):
            os.remove(ruta)
    return jsonify({"ok": True})

@app.route("/api/faenas/<int:id>/documentos/<path:nombre>/descargar", methods=["GET"])
def descargar_documento(id, nombre):
    conn = _conn_para_faena(id)
    faena = conn.execute("SELECT carpeta FROM faenas WHERE id=?", (id,)).fetchone()
    fila = None
    try:
        fila = conn.execute(
            "SELECT * FROM archivos_faena WHERE faena_id=? AND nombre=?", (id, nombre)
        ).fetchone()
    except Exception:
        fila = None
    conn.close()
    if fila:
        fila = fila_a_dict(fila)
        if fila.get("public_url"):
            return redirect(fila["public_url"])
        if fila.get("object_key"):
            contenido = descargar_bytes(fila["object_key"])
            if contenido:
                buf = io.BytesIO(contenido)
                return send_file(buf, as_attachment=True, download_name=nombre, mimetype=fila.get("mime_type") or _mime_archivo(nombre))
    if faena and faena["carpeta"]:
        ruta = os.path.join(faena["carpeta"], "Documentos", nombre)
        if os.path.exists(ruta):
            return send_file(ruta, as_attachment=True, download_name=nombre)
    return jsonify({"ok": False, "error": "Archivo no encontrado. Si es un plano de PolyBoard, está en el PC."}), 404

@app.route("/api/faenas/<int:id>/documentos/<path:nombre>/abrir", methods=["POST"])
def abrir_documento(id, nombre):
    return descargar_documento(id, nombre)

@app.route("/api/faenas/<int:id>/documentos/carpeta", methods=["POST"])
def abrir_carpeta_documentos(id):
    conn = get_connection()
    faena = conn.execute("SELECT carpeta FROM faenas WHERE id=?", (id,)).fetchone()
    conn.close()
    if faena and faena["carpeta"] and os.name == "nt":
        carpeta_docs = os.path.join(faena["carpeta"], "Documentos")
        os.makedirs(carpeta_docs, exist_ok=True)
        subprocess.Popen(["explorer", carpeta_docs])
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Los planos se guardan en el PC. En la nube usa Añadir o Archivar (ZIP)."}), 400


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


@app.route("/api/book", methods=["POST"])
def crear_book():
    import base64 as b64mod
    datos = request.json or {}
    faena_id = datos.get("faena_id") or 0
    titulo = datos.get("titulo", "")
    descripcion = datos.get("descripcion", "")
    foto_b64 = datos.get("data", "")
    if not foto_b64:
        return jsonify({"ok": False, "error": "Se requiere data"}), 400
    conn = get_connection()
    numero_faena = "generico"
    if faena_id and faena_id != 0:
        faena = conn.execute("SELECT numero FROM faenas WHERE id=?", (faena_id,)).fetchone()
        if not faena:
            conn.close()
            return jsonify({"ok": False, "error": "Faena no encontrada"}), 404
        numero_faena = faena["numero"]
    nombre_foto = f"book_{numero_faena}_{int(time.time() * 1000)}.jpg"
    try:
        raw = foto_b64.split(",")[1] if "," in foto_b64 else foto_b64
        img_bytes = b64mod.b64decode(raw)
        if r2_activo():
            key = clave_objeto("_book", nombre_foto)
            res = subir_bytes(key, img_bytes, "image/jpeg")
            if not res.get("ok"):
                conn.close()
                return jsonify({"ok": False, "error": res.get("error") or "No se pudo subir al book"}), 500
            ruta_foto = res.get("url") or key
        else:
            carpeta_book = os.path.join(CARPETA_RAIZ, "_book")
            os.makedirs(carpeta_book, exist_ok=True)
            ruta_foto = os.path.join(carpeta_book, nombre_foto)
            with open(ruta_foto, "wb") as f:
                f.write(img_bytes)
    except Exception as e:
        conn.close()
        return jsonify({"ok": False, "error": str(e)}), 500
    cursor = conn.cursor()
    max_orden = conn.execute("SELECT COALESCE(MAX(orden),0) AS max_orden FROM book_fotos").fetchone()["max_orden"]
    cursor.execute(
        "INSERT INTO book_fotos (faena_id, ruta_foto, titulo, descripcion, orden) VALUES (?,?,?,?,?)",
        (faena_id or None, ruta_foto, titulo, descripcion, max_orden + 1)
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
    try:
        hostname = socket.gethostname()
        infos = socket.getaddrinfo(hostname, None)
        ips_validas = []
        for info in infos:
            ip = info[4][0]
            if ":" not in ip and not ip.startswith("127.") and not ip.startswith("172."):
                if ip not in ips_validas:
                    ips_validas.append(ip)
        if not ips_validas:
            ips_validas = ["127.0.0.1"]
    except Exception:
        ips_validas = ["127.0.0.1"]
    print(f"✓ Servidor en:  http://localhost:{PORT}")
    for ip in ips_validas:
        print(f"✓ IP para móvil: http://{ip}:{PORT}/movil2")
    if PUBLIC_BASE_URL:
        print(f"✓ URL cloud para móvil: {PUBLIC_BASE_URL}/movil2")
    print("=" * 50)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", PORT))
    except OSError:
        print(f"✗ El puerto {PORT} ya está en uso. Cierra la otra instancia de Faenas o libera el puerto antes de abrir el exe.")
        raise SystemExit(1)
    finally:
        sock.close()
    app.run(host=HOST, port=PORT, debug=False)