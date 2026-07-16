"""Conexiones PostgreSQL reutilizables para instancias Cloud Run."""

import os

from psycopg2.pool import ThreadedConnectionPool

from config_bunker import DB_CONFIG, DB_POOL_MAX, DB_POOL_MIN


_pool = None


class _ConexionPooled:
    """Mantiene compatibilidad: ``close()`` devuelve la conexión al pool."""

    def __init__(self, connection, pool):
        self._connection = connection
        self._pool = pool
        self._returned = False

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def close(self):
        if not self._returned:
            self._pool.putconn(self._connection)
            self._returned = True


def _get_pool():
    global _pool
    if _pool is None:
        minimo = max(1, DB_POOL_MIN)
        maximo = max(minimo, DB_POOL_MAX)
        _pool = ThreadedConnectionPool(
            minimo,
            maximo,
            connect_timeout=int(os.environ.get('DB_CONNECT_TIMEOUT', '8')),
            **DB_CONFIG,
        )
    return _pool


def get_connection():
    try:
        pool = _get_pool()
        connection = pool.getconn()
        # Las columnas de negocio son timestamp sin zona; toda operación del
        # sistema se interpreta de forma consistente en America/Tijuana.
        with connection.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'America/Tijuana'")
        return _ConexionPooled(connection, pool)
    except Exception as exc:
        # Nunca imprime secretos: solamente el diagnóstico del driver.
        print(f"Error crítico de conexión a la BD: {exc}")
        return None


