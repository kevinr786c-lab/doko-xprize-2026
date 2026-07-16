"""Inspecciona el esquema local sin incluir credenciales en el codigo."""

import psycopg2
from psycopg2.extras import RealDictCursor

from config_bunker import DB_CONFIG


def escanear_esquema() -> None:
    with psycopg2.connect(**DB_CONFIG, connect_timeout=5) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name ASC
                """
            )
            tablas = cursor.fetchall()
            print(f"Tablas detectadas: {len(tablas)}")

            for tabla in tablas:
                nombre_tabla = tabla["table_name"]
                print(f"\n[{nombre_tabla}]")
                cursor.execute(
                    """
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = %s
                    ORDER BY ordinal_position ASC
                    """,
                    (nombre_tabla,),
                )
                for columna in cursor.fetchall():
                    nulo = "NULL" if columna["is_nullable"] == "YES" else "NOT NULL"
                    print(
                        f"  {columna['column_name']:<24} "
                        f"{columna['data_type']:<20} {nulo}"
                    )


if __name__ == "__main__":
    escanear_esquema()
