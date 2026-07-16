import json
import os
from psycopg2.extras import RealDictCursor
from agentes.gemini_client import generar_texto
from helpers.db import get_connection


class AgenteComercial:
    """Detecta oportunidades comerciales. Human-in-the-loop: admin aprueba antes de enviar."""

    def ejecutar(self) -> dict:
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                SELECT d.correo_doctor, d.nombre_doctor,
                       MAX(v.fecha_pedido) as ultimo_pedido
                FROM DOCTORES d
                LEFT JOIN VENTAS_PEDIDOS_ELITE v ON d.correo_doctor = v.correo_doctor
                WHERE d.activo = TRUE
                GROUP BY d.correo_doctor, d.nombre_doctor
                HAVING MAX(v.fecha_pedido) IS NOT NULL
                   AND MAX(v.fecha_pedido) < NOW() - INTERVAL \'45 days\'
            """)
            oportunidades = cur.fetchall()
            detectados = 0

            for op in oportunidades:
                contexto = {
                    'pedidos_mes_anterior': op.get('pedidos_mes', 0),
                    'ultimo_pedido': str(op.get('ultimo_pedido', ''))
                }
                texto_sql = f"Doctor {op['nombre_doctor']} compró el mes pasado pero no este mes."
                borrador = self._redactar_borrador(op['nombre_doctor'], texto_sql)

                cur.execute("""
                    INSERT INTO LOGS_COMERCIAL
                    (correo_doctora, tipo_oportunidad, contexto_sql, borrador_correo)
                    VALUES (%s, %s, %s, %s)
                """, (op['correo_doctor'], 'reactivacion_compra', json.dumps(contexto), borrador))
                detectados += 1

            conn.commit()
            return {'ok': True, 'oportunidades_detectadas': detectados}
        except Exception as e:
            if conn:
                conn.rollback()
            return {'ok': False, 'error': str(e)}
        finally:
            if conn:
                conn.close()

    def _redactar_borrador(self, nombre: str, contexto: str) -> str:
        prompt = f"""Redacta un correo breve y profesional para el Dr(a). {nombre}.
Contexto: {contexto}
Ofrece ayuda con insumos médicos. Máximo 4 líneas. Sin enviar — solo borrador."""
        try:
            return generar_texto(prompt)
        except Exception:
            return f"Estimado(a) Dr(a). {nombre}, notamos que no ha realizado pedidos este mes. ¿Podemos ayudarle con insumos?"
