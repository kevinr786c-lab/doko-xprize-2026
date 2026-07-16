import json
import os
from psycopg2.extras import RealDictCursor
from agentes.gemini_client import generar_texto
from helpers.db import get_connection


class AgenteInventario:
    """Analiza rotación de inventario. Disparado post-commit del pedido."""

    def ejecutar(self, trigger_evento: str = 'nuevo_pedido') -> dict:
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                SELECT p.id_producto, p.nombre_comercial,
                       COALESCE(SUM(l.cantidad_piezas_actual), 0) as stock
                FROM CAT_PRODUCTOS_MAESTRO p
                LEFT JOIN INVENTARIO_LOTES l ON p.id_producto = l.id_producto AND l.activo = TRUE
                WHERE p.estatus_producto = 'activo'
                GROUP BY p.id_producto, p.nombre_comercial
            """)
            productos = cur.fetchall()

            cur.execute("""
                SELECT dvl.id_producto, SUM(dvl.cantidad) as vendidos
                FROM DETALLE_VENTA_LOTES dvl
                JOIN VENTAS_PEDIDOS_ELITE v ON dvl.id_pedido = v.id_pedido
                WHERE v.fecha_pedido >= NOW() - INTERVAL '60 days'
                  AND v.estatus_entrega IN ('preparando', 'en_camino', 'entregado')
                GROUP BY dvl.id_producto
            """)
            ventas_map = {str(r['id_producto']): int(r['vendidos']) for r in cur.fetchall()}

            lentos, criticos = [], []
            for p in productos:
                pid = str(p['id_producto'])
                stock = int(p['stock'])
                vendidos = ventas_map.get(pid, 0)
                if stock > 20 and vendidos < 3:
                    lentos.append({'producto': p['nombre_comercial'], 'stock': stock, 'vendidos_60d': vendidos})
                if stock <= 5:
                    criticos.append({'producto': p['nombre_comercial'], 'stock': stock})

            reporte = self._interpretar(lentos, criticos)
            cur.execute("""
                INSERT INTO LOGS_INVENTARIO (trigger_evento, productos_lentos, productos_criticos, reporte_gemini)
                VALUES (%s, %s, %s, %s)
            """, (trigger_evento, json.dumps(lentos), json.dumps(criticos), reporte))
            conn.commit()
            return {'ok': True, 'lentos': len(lentos), 'criticos': len(criticos), 'reporte': reporte}
        except Exception as e:
            if conn:
                conn.rollback()
            return {'ok': False, 'error': str(e)}
        finally:
            if conn:
                conn.close()

    def _interpretar(self, lentos: list, criticos: list) -> str:
        if not lentos and not criticos:
            return "Inventario estable. Sin alertas."
        texto = f"Lentos: {len(lentos)}. Críticos: {len(criticos)}."
        try:
            prompt = f"Alerta inventario B2B Doko Hub Logistics. {texto} Resume en 2 líneas."
            return generar_texto(prompt)
        except Exception:
            return texto
