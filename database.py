import os
import sqlite3
from datetime import date, datetime
from decimal import Decimal

from config import (
    CARPETA_RAIZ,
    DB_BACKEND,
    DB_PATH,
    MYSQL_CHARSET,
    MYSQL_DATABASE,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_CREATE_DATABASE,
    MYSQL_USER,
)

try:
    import mysql.connector
except Exception:
    mysql = None
else:
    mysql = mysql.connector


def _usar_mysql():
    return DB_BACKEND == "mysql"


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


def _mysql_conectar_sin_bd():
    if mysql is None:
        raise RuntimeError("Falta la dependencia mysql-connector-python. Instala requirements.txt primero.")
    return mysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        charset=MYSQL_CHARSET,
        use_unicode=True,
        autocommit=False,
    )


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
    conexion = mysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset=MYSQL_CHARSET,
        use_unicode=True,
        autocommit=False,
    )
    return _ConnectionCompat(conexion, "mysql")


def get_connection():
    if _usar_mysql():
        return _mysql_conectar_con_bd()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return _ConnectionCompat(conn, "sqlite")


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
    ]
    for sentencia in sentencias:
        cursor.execute(sentencia)


def inicializar_db():
    os.makedirs(CARPETA_RAIZ, exist_ok=True)
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