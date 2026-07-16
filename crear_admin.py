"""Crea el administrador inicial usando variables de entorno.

Este script es manual y no se ejecuta durante el arranque de Doko. No contiene
credenciales ni valores predeterminados de producción.
"""

import os

import psycopg2
from werkzeug.security import generate_password_hash

from config_bunker import DB_CONFIG


def registrar_admin() -> None:
    correo = os.environ.get("DOKO_BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("DOKO_BOOTSTRAP_ADMIN_PASSWORD", "")
    nombre = os.environ.get("DOKO_BOOTSTRAP_ADMIN_NAME", "Administrador Doko").strip()

    if not correo or "@" not in correo:
        raise RuntimeError("Define DOKO_BOOTSTRAP_ADMIN_EMAIL con un correo valido.")
    if len(password) < 12:
        raise RuntimeError(
            "Define DOKO_BOOTSTRAP_ADMIN_PASSWORD con al menos 12 caracteres."
        )

    password_hash = generate_password_hash(password)
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO USUARIOS_INTERNOS
                    (nombre, correo, password_hash, rol, activo)
                VALUES (%s, %s, %s, 'admin', TRUE)
                ON CONFLICT (correo) DO NOTHING
                """,
                (nombre, correo, password_hash),
            )

    print("Administrador creado o ya existente.")


if __name__ == "__main__":
    registrar_admin()
