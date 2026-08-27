import os
import sqlite3
from datetime import date, datetime
from decimal import Decimal

from config import (
    APP_DIR,
    CARPETA_RAIZ,
    DB_BACKEND,
    DB_PATH,
    MYSQL_CHARSET,
    MYSQL_DATABASE,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_CREATE_DATABASE,
    MYSQL_SSL,
    MYSQL_USER,
)

MYSQL_CONNECT_TIMEOUT = int(os.environ.get("MYSQL_CONNECT_TIMEOUT", "10") or 10)

try:
    import mysql.connector
except Exception:
    mysql = None
else:
    mysql = mysql.connector


def _usar_mysql():
    return DB_BACKEND == "mysql" and not _MYSQL_DESHABILITADO


_MYSQL_DESHABILITADO = False
_MYSQL_ERROR = None


def _serializar_valor(valor):
    if isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


def fila_a_dict(fila):
    if fila is None:
        return None
    if isinstance(fila, dict):
        items = fila.items()
    else:
        items = dict(fila).items()
    return {clave: _serializar_valor(valor) for clave, valor in items}


def filas_a_lista(filas):
    return [fila_a_dict(f) for f in filas]


def _adaptar_sql(sql):
    sql = sql.replace("INSERT OR IGNORE", "INSERT IGNORE")
    sql = sql.replace("datetime('now')", "CURRENT_TIMESTAMP")
    sql = sql.replace('datetime("now")', "CURRENT_TIMESTAMP")
    sql = sql.replace("?", "%s")
    return sql


def _adaptar_params(params):
    if params is None:
        return ()
    if isinstance(params, tuple):
        return params
    if isinstance(params, list):
        return tuple(params)
    return (params,)


class _CursorCompat:
    def __init__(self, cursor, backend):
        self._cursor = cursor
        self._backend = backend

    def execute(self, sql, params=None):
        if self._backend == "mysql":
            sql = _adaptar_sql(sql)
            params = _adaptar_params(params)
        elif params is None:
            params = ()
        self._cursor.execute(sql, params)
        return self

    def executemany(self, sql, seq_of_params):
        if self._backend == "mysql":
            sql = _adaptar_sql(sql)
            seq_of_params = [_adaptar_params(p) for p in seq_of_params]
        self._cursor.executemany(sql, seq_of_params)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def close(self):
        return self._cursor.close()

    @property
    def lastrowid(self):
        return getattr(self._cursor, "lastrowid", None)

    @property
    def rowcount(self):
        return getattr(self._cursor, "rowcount", -1)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _ConnectionCompat:
    def __init__(self, connection, backend):
        self._connection = connection
        self._backend = backend

    def cursor(self):
        if self._backend == "mysql":
            return _CursorCompat(self._connection.cursor(dictionary=True), self._backend)
        return _CursorCompat(self._connection.cursor(), self._backend)

    def execute(self, sql, params=None):
        return self.cursor().execute(sql, params)

    def commit(self):
        return self._connection.commit()

    def close(self):
        return self._connection.close()

    def __getattr__(self, name):
        return getattr(self._connection, name)


def _mysql_ssl_params():
    if not MYSQL_SSL:
        return {}
    ca_path = os.path.join(APP_DIR, "isrgrootx1.pem")
    if os.path.exists(ca_path):
        return {
            "ssl_ca": ca_path,
            "ssl_verify_cert": True,
            "ssl_verify_identity": False,
        }
    return {
        "ssl_disabled": False,
        "ssl_verify_cert": False,
        "ssl_verify_identity": False,
    }


def _mysql_params(include_database=True):
    if mysql is None:
        raise RuntimeError("Falta la dependencia mysql-connector-python. Instala requirements.txt primero.")
    params = dict(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        charset=MYSQL_CHARSET,
        use_unicode=True,
        autocommit=False,
        connection_timeout=MYSQL_CONNECT_TIMEOUT,
    )
    if include_database:
        params["database"] = MYSQL_DATABASE
    params.update(_mysql_ssl_params())
    return params


def _mysql_conectar_sin_bd():
    return mysql.connect(**_mysql_params(include_database=False))


def _mysql_asegurar_base():
    if not MYSQL_DATABASE:
        raise RuntimeError("No has configurado MYSQL_DATABASE.")
    if not MYSQL_CREATE_DATABASE:
        return
    conexion = _mysql_conectar_sin_bd()
    cursor = conexion.cursor()
    cursor.execute(
        f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    conexion.commit()
    cursor.close()
    conexion.close()


def _mysql_conectar_con_bd():
    _mysql_asegurar_base()
    conexion = mysql.connect(**_mysql_params(include_database=True))
    return _ConnectionCompat(conexion, "mysql")


def _sqlite_conectar_local():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return _ConnectionCompat(conn, "sqlite")


def get_sqlite_local():
    """Siempre SQLite local — para leer/escribir faenas archivadas."""
    return _sqlite_conectar_local()


def inicializar_sqlite_local():
    """Asegura que el esquema SQLite local existe (necesario cuando el backend es MySQL)."""
    os.makedirs(CARPETA_RAIZ, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = _CursorCompat(conn.cursor(), "sqlite")
    _crear_esquema_sqlite(cur)
    conn.commit()
    conn.close()


def mysql_configurado():
    return DB_BACKEND == "mysql" or bool(MYSQL_HOST and MYSQL_USER and MYSQL_DATABASE)


def get_db_status():
    conn = get_connection()
    activo = conn._backend
    conn.close()
    return {
        "backend_configurado": DB_BACKEND,
        "backend_activo": activo,
        "mysql_configurado": mysql_configurado(),
        "mysql_deshabilitado": _MYSQL_DESHABILITADO,
        "mysql_error": _MYSQL_ERROR,
    }


def get_connection():
    global _MYSQL_DESHABILITADO, _MYSQL_ERROR

    if _usar_mysql():
        try:
            return _mysql_conectar_con_bd()
        except Exception as exc:
            _MYSQL_DESHABILITADO = True
            _MYSQL_ERROR = str(exc)
            print("[AVISO] No se pudo conectar a MySQL. Se usara SQLite local.")
            print(f"[AVISO] Motivo MySQL: {_MYSQL_ERROR}")

    return _sqlite_conectar_local()


def _crear_esquema_sqlite(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS intermediarios (
            id INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL,
            telefono TEXT DEFAULT '',
            email TEXT DEFAULT ''
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO intermediarios (id, nombre) VALUES (0, 'Cliente directo')")

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS materiales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            unidad TEXT DEFAULT 'ud',
            categoria TEXT DEFAULT 'Herraje'
        )
    """)

    try:
        cursor.execute("ALTER TABLE materiales ADD COLUMN definicion TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

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

    try:
        cursor.execute("ALTER TABLE fotos_faena ADD COLUMN data_base64 TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS archivos_faena (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            faena_id INTEGER NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'documento',
            nombre TEXT NOT NULL,
            storage_backend TEXT NOT NULL DEFAULT 'local',
            bucket TEXT DEFAULT '',
            object_key TEXT NOT NULL DEFAULT '',
            public_url TEXT DEFAULT '',
            mime_type TEXT DEFAULT '',
            tamaño INTEGER DEFAULT 0,
            hash_sha256 TEXT DEFAULT '',
            origen_local TEXT DEFAULT '',
            estado_ia TEXT NOT NULL DEFAULT 'pendiente',
            metadata_json TEXT DEFAULT '',
            fecha TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (faena_id) REFERENCES faenas(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analisis_archivos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            archivo_id INTEGER NOT NULL,
            agente TEXT NOT NULL DEFAULT '',
            tipo_analisis TEXT NOT NULL DEFAULT 'extraccion',
            version_modelo TEXT DEFAULT '',
            estado TEXT NOT NULL DEFAULT 'pendiente',
            resumen TEXT DEFAULT '',
            datos_json TEXT DEFAULT '',
            confianza REAL DEFAULT 0,
            fecha TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (archivo_id) REFERENCES archivos_faena(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ia_memoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pregunta TEXT NOT NULL,
            respuesta TEXT NOT NULL,
            contexto_tipo TEXT NOT NULL DEFAULT 'general',
            alcance TEXT NOT NULL DEFAULT 'general',
            faena_id INTEGER DEFAULT 0,
            tokens TEXT NOT NULL DEFAULT '',
            fuente TEXT NOT NULL DEFAULT 'local',
            creado_en TEXT DEFAULT (datetime('now'))
        )
    """)


def _crear_esquema_mysql(cursor):
    sentencias = [
        """
        CREATE TABLE IF NOT EXISTS intermediarios (
            id INT NOT NULL PRIMARY KEY,
            nombre VARCHAR(255) NOT NULL,
            telefono VARCHAR(50) NOT NULL DEFAULT '',
            email VARCHAR(255) NOT NULL DEFAULT ''
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        "INSERT IGNORE INTO intermediarios (id, nombre) VALUES (0, 'Cliente directo')",
        """
        CREATE TABLE IF NOT EXISTS clientes (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            nombre VARCHAR(255) NOT NULL,
            telefono VARCHAR(50) NOT NULL DEFAULT '',
            direccion VARCHAR(255) NOT NULL DEFAULT '',
            email VARCHAR(255) NOT NULL DEFAULT '',
            intermediario_id INT NOT NULL DEFAULT 0,
            notas VARCHAR(2000) NOT NULL DEFAULT '',
            CONSTRAINT fk_clientes_intermediarios
                FOREIGN KEY (intermediario_id) REFERENCES intermediarios(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS faenas (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            numero VARCHAR(50) UNIQUE,
            cliente_id INT NOT NULL,
            intermediario_id INT NOT NULL DEFAULT 0,
            direccion VARCHAR(255) NOT NULL DEFAULT '',
            tipo_trabajo VARCHAR(255) NOT NULL DEFAULT '',
            importe DOUBLE NOT NULL DEFAULT 0,
            fecha_inicio VARCHAR(32) NOT NULL DEFAULT '',
            archivada TINYINT(1) NOT NULL DEFAULT 0,
            carpeta VARCHAR(255) NOT NULL DEFAULT '',
            CONSTRAINT fk_faenas_clientes
                FOREIGN KEY (cliente_id) REFERENCES clientes(id),
            CONSTRAINT fk_faenas_intermediarios
                FOREIGN KEY (intermediario_id) REFERENCES intermediarios(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS anotaciones (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            faena_id INT NOT NULL,
            tipo VARCHAR(50) NOT NULL DEFAULT 'texto',
            contenido VARCHAR(5000) NOT NULL DEFAULT '',
            fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_anotaciones_faenas
                FOREIGN KEY (faena_id) REFERENCES faenas(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS materiales (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            nombre VARCHAR(255) NOT NULL,
            unidad VARCHAR(20) NOT NULL DEFAULT 'ud',
            categoria VARCHAR(100) NOT NULL DEFAULT 'Herraje',
            definicion VARCHAR(5000) NOT NULL DEFAULT ''
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS precios (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            material_id INT NOT NULL,
            proveedor VARCHAR(255) NOT NULL,
            precio_unitario DOUBLE NOT NULL,
            fecha_actualizacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uk_precios_material_proveedor (material_id, proveedor),
            CONSTRAINT fk_precios_materiales
                FOREIGN KEY (material_id) REFERENCES materiales(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS gastos_faena (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            faena_id INT NOT NULL,
            tipo VARCHAR(50) NOT NULL DEFAULT 'otro',
            descripcion VARCHAR(5000) NOT NULL DEFAULT '',
            cantidad DOUBLE NOT NULL DEFAULT 1,
            precio_unitario DOUBLE NOT NULL DEFAULT 0,
            total DOUBLE NOT NULL DEFAULT 0,
            fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ticket_foto VARCHAR(500) NOT NULL DEFAULT '',
            CONSTRAINT fk_gastos_faena
                FOREIGN KEY (faena_id) REFERENCES faenas(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS presupuestos_faena (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            faena_id INT NOT NULL,
            tipo VARCHAR(50) NOT NULL DEFAULT 'material',
            descripcion VARCHAR(5000) NOT NULL DEFAULT '',
            cantidad DOUBLE NOT NULL DEFAULT 1,
            precio_unitario DOUBLE NOT NULL DEFAULT 0,
            total DOUBLE NOT NULL DEFAULT 0,
            fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_presupuestos_faena
                FOREIGN KEY (faena_id) REFERENCES faenas(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS fotos_faena (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            faena_id INT NOT NULL,
            nombre VARCHAR(255) NOT NULL,
            ruta_foto VARCHAR(500) NOT NULL,
            data_base64 LONGTEXT,
            fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_fotos_faena
                FOREIGN KEY (faena_id) REFERENCES faenas(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS book_fotos (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            faena_id INT NOT NULL DEFAULT 0,
            ruta_foto VARCHAR(500) NOT NULL,
            titulo VARCHAR(255) NOT NULL DEFAULT '',
            descripcion VARCHAR(5000) NOT NULL DEFAULT '',
            fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            orden INT NOT NULL DEFAULT 0
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS archivos_faena (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            faena_id INT NOT NULL,
            tipo VARCHAR(50) NOT NULL DEFAULT 'documento',
            nombre VARCHAR(255) NOT NULL,
            storage_backend VARCHAR(50) NOT NULL DEFAULT 'local',
            bucket VARCHAR(255) NOT NULL DEFAULT '',
            object_key VARCHAR(500) NOT NULL DEFAULT '',
            public_url VARCHAR(1000) NOT NULL DEFAULT '',
            mime_type VARCHAR(255) NOT NULL DEFAULT '',
            tamaño BIGINT NOT NULL DEFAULT 0,
            hash_sha256 VARCHAR(128) NOT NULL DEFAULT '',
            origen_local VARCHAR(500) NOT NULL DEFAULT '',
            estado_ia VARCHAR(50) NOT NULL DEFAULT 'pendiente',
            metadata_json LONGTEXT,
            fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            KEY idx_archivos_faena_faena (faena_id),
            KEY idx_archivos_faena_object_key (object_key),
            CONSTRAINT fk_archivos_faena
                FOREIGN KEY (faena_id) REFERENCES faenas(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS analisis_archivos (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            archivo_id INT NOT NULL,
            agente VARCHAR(100) NOT NULL DEFAULT '',
            tipo_analisis VARCHAR(100) NOT NULL DEFAULT 'extraccion',
            version_modelo VARCHAR(255) NOT NULL DEFAULT '',
            estado VARCHAR(50) NOT NULL DEFAULT 'pendiente',
            resumen VARCHAR(5000) NOT NULL DEFAULT '',
            datos_json LONGTEXT,
            confianza DOUBLE NOT NULL DEFAULT 0,
            fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            KEY idx_analisis_archivos_archivo (archivo_id),
            CONSTRAINT fk_analisis_archivos
                FOREIGN KEY (archivo_id) REFERENCES archivos_faena(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS ia_memoria (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            pregunta VARCHAR(5000) NOT NULL,
            respuesta LONGTEXT NOT NULL,
            contexto_tipo VARCHAR(50) NOT NULL DEFAULT 'general',
            alcance VARCHAR(50) NOT NULL DEFAULT 'general',
            faena_id INT NOT NULL DEFAULT 0,
            tokens VARCHAR(2000) NOT NULL DEFAULT '',
            fuente VARCHAR(50) NOT NULL DEFAULT 'local',
            creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            KEY idx_ia_memoria_tokens (tokens(255)),
            KEY idx_ia_memoria_faena (faena_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
    ]
    for sentencia in sentencias:
        cursor.execute(sentencia)

    try:
        cursor.execute("ALTER TABLE fotos_faena ADD COLUMN data_base64 LONGTEXT")
    except Exception:
        pass


def inicializar_db():
    os.makedirs(CARPETA_RAIZ, exist_ok=True)
    if _usar_mysql():
        inicializar_sqlite_local()  # siempre mantener SQLite para faenas archivadas
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if _usar_mysql():
            _crear_esquema_mysql(cursor)
        else:
            _crear_esquema_sqlite(cursor)
        conn.commit()
    finally:
        conn.close()

    destino = MYSQL_DATABASE if _usar_mysql() else DB_PATH
    print(f"✓ Base de datos lista en: {destino}")


def generar_numero_faena(intermediario_id, cliente_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS total FROM faenas WHERE cliente_id = ?", (cliente_id,))
    count = cursor.fetchone()["total"]
    conn.close()
    return f"{int(intermediario_id):02d}{int(cliente_id):02d}{count + 1:02d}"


def crear_carpeta_faena(numero_faena, nombre_cliente):
    nombre_limpio = nombre_cliente.replace(" ", "_")
    nombre_limpio = "".join(c for c in nombre_limpio if c.isalnum() or c == "_")
    nombre_carpeta = f"{numero_faena}_{nombre_limpio}"
    ruta = os.path.join(CARPETA_RAIZ, nombre_carpeta)
    os.makedirs(os.path.join(ruta, "Documentos"), exist_ok=True)
    os.makedirs(os.path.join(ruta, "fotos"), exist_ok=True)
    os.makedirs(os.path.join(ruta, "tickets"), exist_ok=True)
    return ruta