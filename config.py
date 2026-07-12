# ============================================================
# config.py — Configuración de la app Gestión de Faenas
# ============================================================
# Edita este archivo para adaptar la app a tu equipo.
# ============================================================

import os
import sys

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

# --- SERVIDOR ---
HOST = "0.0.0.0"       # Escucha en todas las interfaces (necesario para el móvil)
PORT = 5000             # Puerto del servidor Flask

# --- CURSOR ---
# Ruta al ejecutable de Cursor. Si está en el PATH del sistema déjalo así.
# Si no funciona, pon la ruta completa, por ejemplo:
# CURSOR_PATH = r"C:\Users\TuUsuario\AppData\Local\Programs\cursor\Cursor.exe"
CURSOR_PATH = "cursor"

# --- CODIFICACIÓN POLYBOARD ---
# Los archivos TXT de PolyBoard usan esta codificación en Windows
POLYBOARD_ENCODING = "latin-1"
