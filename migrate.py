#!/usr/bin/env python3
"""
Script de migración de datos hacia la base de datos cloud (Supabase/PostgreSQL).

Modos de uso:
  python migrate.py sqlite <ruta/a/base.db>
      Importa datos desde la base de datos SQLite del PC Windows.

  python migrate.py json <ruta/a/datos.json>
      Importa datos desde un archivo JSON exportado del localStorage del móvil.
      El JSON debe tener claves: "clientes", "faenas", "materiales".

Variables de entorno requeridas:
  DATABASE_URL — cadena de conexión PostgreSQL (Supabase)
"""

import os
import sys
import json
import sqlite3
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "")


def connect_pg():
    if not DATABASE_URL:
        print("ERROR: La variable DATABASE_URL no está configurada.")
        sys.exit(1)
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


# ─── Migración desde SQLite (PC Windows) ─────────────────────────────────────
def migrate_from_sqlite(sqlite_path: str):
    print(f"Abriendo SQLite: {sqlite_path}")
    sq = sqlite3.connect(sqlite_path)
    sq.row_factory = sqlite3.Row
    pg = connect_pg()

    def copy_table(table, columns, pg_sql, transform=None):
        try:
            rows = sq.execute(f"SELECT {columns} FROM {table}").fetchall()
        except sqlite3.OperationalError as e:
            print(f"  ⚠ Tabla '{table}' no encontrada en SQLite: {e}")
            return 0
        ok_count = 0
        with pg.cursor() as cur:
            for row in rows:
                values = tuple(row[c] for c in columns.split(", "))
                if transform:
                    values = transform(values)
                try:
                    cur.execute(pg_sql, values)
                    ok_count += 1
                except Exception as e:
                    print(f"  ⚠ Fila ignorada: {e}")
        pg.commit()
        print(f"  ✓ {table}: {ok_count}/{len(rows)} registros importados")
        return ok_count

    print("→ Clientes")
    copy_table(
        "clientes",
        "id, nombre, telefono, email, intermediario_id",
        "INSERT INTO clientes (id, nombre, telefono, email, intermediario_id) "
        "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
    )

    print("→ Faenas")
    copy_table(
        "faenas",
        "id, numero, cliente_id, intermediario_id, intermediario_nombre, "
        "direccion, tipo_trabajo, importe, fecha_inicio, archivada",
        "INSERT INTO faenas (id, numero, cliente_id, intermediario_id, intermediario_nombre, "
        "direccion, tipo_trabajo, importe, fecha_inicio, archivada) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
    )

    print("→ Anotaciones")
    copy_table(
        "anotaciones",
        "id, faena_id, tipo, contenido, fecha",
        "INSERT INTO anotaciones (id, faena_id, tipo, contenido, fecha) "
        "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
    )

    print("→ Materiales")
    copy_table(
        "materiales",
        "id, nombre, unidad, categoria, definicion",
        "INSERT INTO materiales (id, nombre, unidad, categoria, definicion) "
        "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
    )

    print("→ Precios")
    copy_table(
        "precios_materiales",
        "id, material_id, proveedor, precio_unitario",
        "INSERT INTO precios_materiales (id, material_id, proveedor, precio_unitario) "
        "VALUES (%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
    )

    # Resetear secuencias para evitar colisiones de IDs
    print("→ Ajustando secuencias de IDs...")
    with pg.cursor() as cur:
        for table in ("clientes", "faenas", "anotaciones", "materiales", "precios_materiales"):
            cur.execute(
                f"SELECT setval('{table}_id_seq', COALESCE((SELECT MAX(id) FROM {table}), 1))"
            )
    pg.commit()

    sq.close()
    pg.close()
    print("✓ Migración desde SQLite completada.")


# ─── Importación desde JSON (localStorage del móvil) ─────────────────────────
def migrate_from_json(json_path: str):
    print(f"Cargando JSON: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    pg = connect_pg()

    # Clientes
    clientes = data.get("clientes", [])
    print(f"→ Clientes ({len(clientes)})")
    ok_count = 0
    with pg.cursor() as cur:
        for c in clientes:
            if str(c.get("id", "")).startswith("TEMP"):
                continue
            try:
                cur.execute(
                    "INSERT INTO clientes (nombre, telefono, email) "
                    "VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                    (c.get("nombre", ""), c.get("telefono", ""), c.get("email", "")),
                )
                ok_count += 1
            except Exception as e:
                print(f"  ⚠ {e}")
    pg.commit()
    print(f"  ✓ {ok_count} importados")

    # Faenas
    faenas = data.get("faenas", [])
    print(f"→ Faenas ({len(faenas)})")
    ok_count = 0
    with pg.cursor() as cur:
        for f in faenas:
            if str(f.get("id", "")).startswith("TEMP") or f.get("_offline"):
                print(f"  ⚠ Faena temporal ignorada: {f.get('numero')}")
                continue
            try:
                cur.execute(
                    "INSERT INTO faenas "
                    "(numero, cliente_id, intermediario_id, intermediario_nombre, "
                    " direccion, tipo_trabajo, importe, fecha_inicio, archivada) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (
                        f.get("numero"),
                        f.get("cliente_id"),
                        f.get("intermediario_id", 0),
                        f.get("intermediario_nombre", "Cliente directo"),
                        f.get("direccion", ""),
                        f.get("tipo_trabajo", ""),
                        f.get("importe", 0),
                        f.get("fecha_inicio"),
                        f.get("archivada", 0),
                    ),
                )
                ok_count += 1
            except Exception as e:
                print(f"  ⚠ {e}")
    pg.commit()
    print(f"  ✓ {ok_count} importadas")

    # Materiales
    materiales = data.get("materiales", [])
    print(f"→ Materiales ({len(materiales)})")
    ok_count = 0
    with pg.cursor() as cur:
        for m in materiales:
            if str(m.get("id", "")).startswith("temp_"):
                continue
            try:
                cur.execute(
                    "SELECT id FROM materiales WHERE LOWER(nombre)=LOWER(%s)",
                    (m.get("nombre", ""),),
                )
                existing = cur.fetchone()
                if not existing:
                    cur.execute(
                        "INSERT INTO materiales (nombre, unidad, categoria, definicion) "
                        "VALUES (%s,%s,%s,%s) RETURNING id",
                        (
                            m.get("nombre", ""),
                            m.get("unidad", "ud"),
                            m.get("categoria", "Otros"),
                            m.get("definicion", ""),
                        ),
                    )
                    mat_id = cur.fetchone()["id"]
                    ok_count += 1
                    # Insertar precios del material si los hay
                    for p in m.get("precios", []):
                        if p.get("proveedor") and p.get("precio_unitario") is not None:
                            cur.execute(
                                "INSERT INTO precios_materiales "
                                "(material_id, proveedor, precio_unitario) "
                                "VALUES (%s,%s,%s) "
                                "ON CONFLICT (material_id, proveedor) DO NOTHING",
                                (mat_id, p["proveedor"], p["precio_unitario"]),
                            )
            except Exception as e:
                print(f"  ⚠ {e}")
    pg.commit()
    print(f"  ✓ {ok_count} importados")

    pg.close()
    print("✓ Importación desde JSON completada.")
    print(
        "\nNOTA: Las anotaciones y fotos que estaban en localStorage no se incluyen "
        "en este JSON. Sincroniza el móvil con el servidor cloud para subirlas."
    )


# ─── Entrada ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    modo = sys.argv[1].lower()
    ruta = sys.argv[2]

    if modo == "sqlite":
        migrate_from_sqlite(ruta)
    elif modo == "json":
        migrate_from_json(ruta)
    else:
        print(f"Modo desconocido: '{modo}'. Usa 'sqlite' o 'json'.")
        sys.exit(1)
