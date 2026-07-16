from psycopg2.extras import RealDictCursor
from helpers.db import get_connection


class FAQBuilder:
    """Construye dataset de FAQs para el chatbot desde PostgreSQL."""

    @staticmethod
    def para_doctor(id_publico: str) -> list:
        conn = get_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT palabras_clave, respuesta, orden
                FROM FAQ_CHATBOT
                WHERE (id_doctor_app = %s OR id_doctor_app IS NULL) AND activo = TRUE
                ORDER BY orden ASC
            """, (id_publico,))
            return cur.fetchall()
        finally:
            conn.close()

    @staticmethod
    def servicios_doctor(correo_doctor: str) -> list:
        conn = get_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT nombre_servicio, precio, descripcion
                FROM CAT_SERVICIOS_CONSULTORIO
                WHERE correo_doctor = %s AND activo = TRUE
            """, (correo_doctor,))
            return cur.fetchall()
        finally:
            conn.close()
