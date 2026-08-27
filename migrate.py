#!/usr/bin/env python3
"""
Migración de datos desde una base SQLite local hacia MySQL/Hostinger.

Uso:
  python migrate.py sqlite <ruta/a/base.db>

Variables de entorno requeridas para MySQL:
  MYSQL_HOST
  MYSQL_PORT
  MYSQL_USER
  MYSQL_PASSWORD
  MYSQL_DATABASE
"""

import os
import sqlite3
import sys

from config import MYSQL_CHARSET, MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER

try:
    import mysql.connector
except Exception:
    mysql = None
else:
    mysql = mysql.connector


TABLAS = [
    "intermediarios",
    "clientes",
    "faenas",
    "anotaciones",
    "materiales",
    "precios",
    "gastos_faena",
    "presupuestos_faena",
    "fotos_faena",
    "book_fotos",
]


def connect_mysql(include_database=True):
    if mysql is None:
        print("ERROR: Falta la dependencia mysql-connector-python.")
        sys.exit(1)
    if not MYSQL_HOST or not MYSQL_USER or not MYSQL_DATABASE:
        print("ERROR: Configura MYSQL_HOST, MYSQL_USER y MYSQL_DATABASE antes de migrar.")
        sys.exit(1)
    params = {
        "host": MYSQL_HOST,
        "port": MYSQL_PORT,
        "user": MYSQL_USER,
        "password": MYSQL_PASSWORD,
        "charset": MYSQL_CHARSET,
        "use_unicode": True,
        "autocommit": False,
    }
    if include_database:
        params["database"] = MYSQL_DATABASE
    return mysql.connect(**params)


def ensure_database_exists():
    conexion = connect_mysql(include_database=False)
    cursor = conexion.cursor()
    cursor.execute(
        f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    conexion.commit()
    cursor.close()
    conexion.close()


def migrate_from_sqlite(sqlite_path):
    if not os.path.exists(sqlite_path):
        print(f"ERROR: No existe la base SQLite: {sqlite_path}")
        sys.exit(1)

    ensure_database_exists()

    print(f"Abriendo SQLite: {sqlite_path}")
    sq = sqlite3.connect(sqlite_path)
    sq.row_factory = sqlite3.Row
    my = connect_mysql(include_database=True)

    total_insertados = 0

    try:
        for table in TABLAS:
            try:
                columnas = [fila["name"] for fila in sq.execute(f"PRAGMA table_info({table})").fetchall()]
            except sqlite3.OperationalError as exc:
                print(f"  ⚠ Tabla '{table}' no encontrada en SQLite: {exc}")
                continue

            if not columnas:
                print(f"  ⚠ Tabla '{table}' vacía o inexistente.")
                continue

            columnas_sqlite = ", ".join(f'`{col}`' for col in columnas)
            placeholders = ", ".join(["%s"] * len(columnas))
            insert_sql = f"INSERT IGNORE INTO `{table}` ({columnas_sqlite}) VALUES ({placeholders})"

            filas = sq.execute(f"SELECT {columnas_sqlite} FROM {table}").fetchall()
            insertados = 0

            cursor = my.cursor()
            for fila in filas:
                valores = tuple(fila[col] for col in columnas)
                cursor.execute(insert_sql, valores)
                if cursor.rowcount and cursor.rowcount > 0:
                    insertados += 1
            my.commit()
            cursor.close()

            total_insertados += insertados
            print(f"  ✓ {table}: {insertados}/{len(filas)} registros importados")

        cursor = my.cursor()
        for table in TABLAS:
            try:
                cursor.execute(f"SELECT COALESCE(MAX(id), 0) FROM `{table}`")
                max_id = cursor.fetchone()[0]
                cursor.execute(f"ALTER TABLE `{table}` AUTO_INCREMENT = {int(max_id) + 1}")
            except Exception:
                continue
        my.commit()
        cursor.close()
    finally:
        sq.close()
        my.close()

    print(f"✓ Migración completada. Registros procesados: {total_insertados}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    modo = sys.argv[1].lower()
    ruta = sys.argv[2]

    if modo != "sqlite":
        print(f"Modo desconocido: '{modo}'. Usa 'sqlite'.")
        sys.exit(1)

    migrate_from_sqlite(ruta)
