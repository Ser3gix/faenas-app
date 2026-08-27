# ============================================================
# config.py — Configuración de la app Gestión de Faenas
# ============================================================
# Edita este archivo para adaptar la app a tu equipo.
# ============================================================

import os
import sys

try:
	from dotenv import load_dotenv
	load_dotenv()
except Exception:
	# Permite arrancar con la configuracion local aunque falte python-dotenv.
	_ruta_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
	if os.path.exists(_ruta_env):
		try:
			with open(_ruta_env, "r", encoding="utf-8") as _archivo_env:
				for _linea_env in _archivo_env:
					_linea_env = _linea_env.strip()
					if not _linea_env or _linea_env.startswith("#") or "=" not in _linea_env:
						continue
					_nombre_env, _valor_env = _linea_env.split("=", 1)
					_nombre_env = _nombre_env.strip()
					_valor_env = _valor_env.strip().strip("\"'")
					if _nombre_env and _nombre_env not in os.environ:
						os.environ[_nombre_env] = _valor_env
		except Exception:
			pass

# --- CARPETA RAÍZ DE LA APP ---
# Todo vive dentro de la carpeta de la app.
# La subcarpeta "datos" se crea automáticamente.
# Para migrar a otro PC solo copia toda la carpeta faenas-app.
if getattr(sys, "frozen", False):
	APP_DIR = os.path.dirname(sys.executable)
else:
	APP_DIR = os.path.dirname(os.path.abspath(__file__))

# --- CARPETA DE DATOS ---
# Aquí se guardan la base de datos y las carpetas de cada faena.
CARPETA_RAIZ = os.path.join(APP_DIR, "datos")

# --- BASE DE DATOS ---
DB_PATH = os.path.join(CARPETA_RAIZ, "faenas.db")

# --- BACKEND DE BBDD ---
# Por defecto la app sigue usando SQLite en local.
# Si defines las variables de MySQL/Hostinger, puedes cambiar a MySQL con DB_BACKEND=mysql.
MYSQL_HOST = os.environ.get("MYSQL_HOST", os.environ.get("DB_HOST", "")).strip()
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", os.environ.get("DB_PORT", "3306")) or 3306)
MYSQL_USER = os.environ.get("MYSQL_USER", os.environ.get("DB_USER", "")).strip()
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", os.environ.get("DB_PASSWORD", ""))
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", os.environ.get("DB_DATABASE", "")).strip()
MYSQL_CHARSET = os.environ.get("MYSQL_CHARSET", "utf8mb4").strip()
MYSQL_CREATE_DATABASE = os.environ.get("MYSQL_CREATE_DATABASE", "0").strip() in {"1", "true", "yes", "si", "sí"}
MYSQL_SSL = os.environ.get("MYSQL_SSL", "0").strip() in {"1", "true", "yes", "si", "sí"}

DB_BACKEND = os.environ.get("DB_BACKEND", "").strip().lower()
if not DB_BACKEND:
	if MYSQL_HOST and MYSQL_USER and MYSQL_DATABASE:
		DB_BACKEND = "mysql"
	else:
		DB_BACKEND = "sqlite"

# --- SERVIDOR ---
HOST = "0.0.0.0"       # Escucha en todas las interfaces (necesario para el móvil)
PORT = int(os.environ.get("PORT", "5000") or 5000)

_public_base_url = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
_render_url = os.environ.get("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
_railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip().strip("/")
if not _public_base_url and _render_url:
	_public_base_url = _render_url
elif not _public_base_url and _railway_domain:
	_public_base_url = f"https://{_railway_domain}"
PUBLIC_BASE_URL = _public_base_url

# --- ALMACENAMIENTO CLOUD ---
# Metadatos en TiDB; binarios en S3/R2/Supabase Storage u otro backend compatible.
OBJECT_STORAGE_BACKEND = os.environ.get("OBJECT_STORAGE_BACKEND", "local").strip().lower()
OBJECT_STORAGE_BUCKET = os.environ.get("OBJECT_STORAGE_BUCKET", "").strip()
OBJECT_STORAGE_PUBLIC_BASE_URL = os.environ.get("OBJECT_STORAGE_PUBLIC_BASE_URL", "").strip().rstrip("/")
OBJECT_STORAGE_ENDPOINT = os.environ.get("OBJECT_STORAGE_ENDPOINT", "").strip().rstrip("/")
OBJECT_STORAGE_REGION = os.environ.get("OBJECT_STORAGE_REGION", "").strip()

# --- CURSOR ---
# Ruta al ejecutable de Cursor. Si está en el PATH del sistema déjalo así.
# Si no funciona, pon la ruta completa, por ejemplo:
# CURSOR_PATH = r"C:\Users\TuUsuario\AppData\Local\Programs\cursor\Cursor.exe"
CURSOR_PATH = "cursor"

# --- CODIFICACIÓN POLYBOARD ---
# Los archivos TXT de PolyBoard usan esta codificación en Windows
POLYBOARD_ENCODING = "latin-1"
