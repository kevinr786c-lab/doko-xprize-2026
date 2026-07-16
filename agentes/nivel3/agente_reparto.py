import json
import os
from psycopg2.extras import RealDictCursor
from agentes.gemini_client import generar_texto
from helpers.db import get_connection


class AgenteReparto:
    """Sugiere rutas para pedidos ya asignados y en camino."""

    def ejecutar(self, id_repartidor: str = None) -> dict:
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)

            query = """
                SELECT p.id_pedido, p.correo_doctor, d.nombre_doctor,
                       d.direccion_consultorio, d.maps_url
                FROM VENTAS_PEDIDOS_ELITE p
                JOIN DOCTORES d ON p.correo_doctor = d.correo_doctor
                WHERE p.estatus_entrega = 'en_camino'
            """
            params = ()
            if id_repartidor:
                query += " AND p.id_repartidor = %s"
                params = (id_repartidor,)
            query += " ORDER BY p.fecha_pedido ASC"
            cur.execute(query, params)
            pedidos = cur.fetchall()

            if not pedidos:
                return {'ok': True, 'mensaje': 'Sin pedidos para rutear'}

            ruta_json = [str(p['id_pedido']) for p in pedidos]
            ruta_texto = self._sugerir_ruta(pedidos)

            cur.execute("""
                INSERT INTO LOGS_REPARTO (id_repartidor, pedidos_incluidos, ruta_sugerida, ruta_json)
                VALUES (%s, %s, %s, %s)
            """, (id_repartidor, json.dumps(ruta_json), ruta_texto, json.dumps(ruta_json)))
            conn.commit()
            return {'ok': True, 'pedidos': len(pedidos), 'ruta': ruta_texto, 'ruta_json': ruta_json}
        except Exception as e:
            if conn:
                conn.rollback()
            return {'ok': False, 'error': str(e)}
        finally:
            if conn:
                conn.close()

    def _sugerir_ruta(self, pedidos: list) -> str:
        lineas = [f"{i+1}. {p['nombre_doctor']} — {p.get('direccion_consultorio', 'sin dirección')}"
                  for i, p in enumerate(pedidos)]
        try:
            prompt = "Optimiza ruta de reparto en Doko Hub Logistics (Tijuana):\n" + "\n".join(lineas) + "\nOrden sugerido en 5 líneas."
            return generar_texto(prompt)
        except Exception:
            return "Ruta sugerida (orden cronológico):\n" + "\n".join(lineas)
