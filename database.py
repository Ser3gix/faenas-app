import sqlite3
import os
from config import DB_PATH, CARPETA_RAIZ

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def inicializar_db():
    os.makedirs(CARPETA_RAIZ, exist_ok=True)
    conn = get_connection()
    cursor = conn.cursor()

    # intermediarios
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS intermediarios (
            id INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL,
            telefono TEXT DEFAULT '',
            email TEXT DEFAULT ''
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO intermediarios (id, nombre) VALUES (0, 'Cliente directo')")

    # clientes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            telefono TEXT DEFAULT '',
            direccion TEXT DEFAULT '',
            email TEXT DEFAULT '',
            intermediario_id INTEGER DEFAULT 0,
            notas TEXT DEFAULT '',
            FOREIGN KEY (intermediario_id) REFERENCES intermediarios(id)
        )
    """)

    try:
        cursor.execute("ALTER TABLE clientes ADD COLUMN direccion TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    # faenas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS faenas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero TEXT UNIQUE,
            cliente_id INTEGER NOT NULL,
            intermediario_id INTEGER DEFAULT 0,
            direccion TEXT DEFAULT '',
            tipo_trabajo TEXT DEFAULT '',
            importe REAL DEFAULT 0,
            fecha_inicio TEXT DEFAULT '',
            archivada INTEGER DEFAULT 0,
            carpeta TEXT DEFAULT '',
            FOREIGN KEY (cliente_id) REFERENCES clientes(id),
            FOREIGN KEY (intermediario_id) REFERENCES intermediarios(id)
        )
    """)

    # anotaciones
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS anotaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            faena_id INTEGER NOT NULL,
            tipo TEXT DEFAULT 'texto',
            contenido TEXT DEFAULT '',
            fecha TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (faena_id) REFERENCES faenas(id)
        )
    """)

    # materiales
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS materiales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            unidad TEXT DEFAULT 'ud',
            categoria TEXT DEFAULT 'Herraje'
        )
    """)

    # Añadir columna 'definicion' si no existe (NUEVO)
    try:
        cursor.execute("ALTER TABLE materiales ADD COLUMN definicion TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # la columna ya existe

    # precios
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS precios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER NOT NULL,
            proveedor TEXT NOT NULL,
            precio_unitario REAL NOT NULL,
            fecha_actualizacion TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (material_id) REFERENCES materiales(id),
            UNIQUE (material_id, proveedor)
        )
    """)

    # gastos_faena
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gastos_faena (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            faena_id INTEGER NOT NULL,
            tipo TEXT DEFAULT 'otro',
            descripcion TEXT DEFAULT '',
            cantidad REAL DEFAULT 1,
            precio_unitario REAL DEFAULT 0,
            total REAL DEFAULT 0,
            fecha TEXT DEFAULT (datetime('now')),
            ticket_foto TEXT DEFAULT '',
            FOREIGN KEY (faena_id) REFERENCES faenas(id)
        )
    """)

    # presupuestos_faena
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS presupuestos_faena (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            faena_id INTEGER NOT NULL,
            tipo TEXT DEFAULT 'material',
            descripcion TEXT DEFAULT '',
            cantidad REAL DEFAULT 1,
            precio_unitario REAL DEFAULT 0,
            total REAL DEFAULT 0,
            fecha TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (faena_id) REFERENCES faenas(id)
        )
    """)

    # fotos_faena (para sincronización desde móvil)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fotos_faena (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            faena_id INTEGER NOT NULL,
            nombre TEXT NOT NULL,
            ruta_foto TEXT NOT NULL,
            fecha TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (faena_id) REFERENCES faenas(id)
        )
    """)

    # book_fotos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS book_fotos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            faena_id INTEGER DEFAULT 0,
            ruta_foto TEXT NOT NULL,
            titulo TEXT DEFAULT '',
            descripcion TEXT DEFAULT '',
            fecha TEXT DEFAULT (datetime('now')),
            orden INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()
    print(f"✓ Base de datos lista en: {DB_PATH}")

def generar_numero_faena(intermediario_id, cliente_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM faenas WHERE cliente_id = ?", (cliente_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return f"{int(intermediario_id):02d}{int(cliente_id):02d}{count+1:02d}"

def crear_carpeta_faena(numero_faena, nombre_cliente):
    nombre_limpio = nombre_cliente.replace(" ", "_")
    nombre_limpio = "".join(c for c in nombre_limpio if c.isalnum() or c == "_")
    nombre_carpeta = f"{numero_faena}_{nombre_limpio}"
    ruta = os.path.join(CARPETA_RAIZ, nombre_carpeta)
    os.makedirs(os.path.join(ruta, "Documentos"), exist_ok=True)
    os.makedirs(os.path.join(ruta, "fotos"), exist_ok=True)
    os.makedirs(os.path.join(ruta, "tickets"), exist_ok=True)
    return ruta

def fila_a_dict(fila):
    if fila is None:
        return None
    return dict(fila)

def filas_a_lista(filas):
    return [dict(f) for f in filas]