import json
import os
from psycopg2.extras import RealDictCursor
from agentes.gemini_client import generar_texto
from helpers.db import get_connection


class AgenteCompras:
    """Propone lista de compra según stock. Admin aprueba antes de ordenar."""

    def ejecutar(self) -> dict:
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                SELECT p.id_producto, p.nombre_comercial,
                       COALESCE(SUM(l.cantidad_piezas_actual), 0) as stock_total
                FROM CAT_PRODUCTOS_MAESTRO p
                LEFT JOIN INVENTARIO_LOTES l ON p.id_producto = l.id_producto
                    AND l.activo = TRUE AND l.cantidad_piezas_actual > 0
                WHERE p.estatus_producto = 'activo'
                GROUP BY p.id_producto, p.nombre_comercial
                HAVING COALESCE(SUM(l.cantidad_piezas_actual), 0) <= 10
                ORDER BY stock_total ASC
            """)
            criticos = cur.fetchall()
            if not criticos:
                return {'ok': True, 'mensaje': 'Sin productos críticos para compra'}

            propuesta_json = [
                {'id_producto': str(c['id_producto']), 'nombre': c['nombre_comercial'],
                 'stock': int(c['stock_total']), 'sugerido': max(20 - int(c['stock_total']), 5)}
                for c in criticos
            ]
            texto = self._generar_propuesta(criticos)
            contexto = {'productos_criticos': len(criticos)}

            cur.execute("""
                INSERT INTO LOGS_COMPRAS (propuesta_texto, propuesta_json, contexto_sql)
                VALUES (%s, %s, %s)
            """, (texto, json.dumps(propuesta_json), json.dumps(contexto)))
            conn.commit()
            return {'ok': True, 'productos': len(criticos), 'propuesta': texto}
        except Exception as e:
            if conn:
                conn.rollback()
            return {'ok': False, 'error': str(e)}
        finally:
            if conn:
                conn.close()

    def _generar_propuesta(self, criticos: list) -> str:
        lineas = [f"- {c['nombre_comercial']}: stock {c['stock_total']} uds." for c in criticos[:15]]
        prompt = f"""Eres comprador de insumos médicos B2B. Productos con stock bajo:
{chr(10).join(lineas)}
Propón orden de compra en máximo 5 líneas. Solo texto, sin ejecutar."""
        try:
            return generar_texto(prompt)
        except Exception:
            return "Propuesta: reabastecer productos con stock <= 10 unidades.\n" + "\n".join(lineas)
