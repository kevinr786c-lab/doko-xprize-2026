import os
import json
from datetime import datetime, timedelta
import psycopg2.extras
from agentes.gemini_client import generar_texto
from helpers.db import get_connection


class AgenteFinanciero:
    """Calcula margen real via precio_compra de INVENTARIO_LOTES / FACTURAS_COMPRA."""

    def ejecutar(self, periodo: str = 'mes_actual') -> dict:
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            ahora = datetime.now()
            if periodo == 'semana':
                fecha_inicio = ahora - timedelta(days=7)
            elif periodo == '60_dias':
                fecha_inicio = ahora - timedelta(days=60)
            else:
                fecha_inicio = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                periodo = 'mes_actual'
            fecha_fin = ahora

            cur.execute("""
                SELECT p.nombre_comercial, dvl.precio_unitario AS precio_venta,
                       il.precio_compra,
                       (dvl.precio_unitario - il.precio_compra) AS margen_unitario,
                       ROUND(((dvl.precio_unitario - il.precio_compra) / NULLIF(dvl.precio_unitario, 0)) * 100, 2) AS margen_porcentaje,
                       dvl.cantidad,
                       (dvl.precio_unitario - il.precio_compra) * dvl.cantidad AS margen_total
                FROM DETALLE_VENTA_LOTES dvl
                JOIN INVENTARIO_LOTES il ON dvl.id_lote = il.id_lote
                JOIN CAT_PRODUCTOS_MAESTRO p ON dvl.id_producto = p.id_producto
                WHERE dvl.id_pedido IN (
                    SELECT id_pedido FROM VENTAS_PEDIDOS_ELITE
                    WHERE fecha_pedido BETWEEN %s AND %s
                ) AND il.precio_compra IS NOT NULL
            """, (fecha_inicio, fecha_fin))
            filas = cur.fetchall()

            if not filas:
                return {'ok': True, 'mensaje': 'Sin ventas en el período', 'margen_promedio': 0}

            facturacion = sum(float(f['precio_venta']) * int(f['cantidad']) for f in filas)
            costo = sum(float(f['precio_compra']) * int(f['cantidad']) for f in filas)
            utilidad = facturacion - costo
            margen_promedio = (utilidad / facturacion * 100) if facturacion > 0 else 0

            texto = (f"Período: {periodo}. Facturación: ${facturacion:,.2f}. "
                     f"Costo: ${costo:,.2f}. Utilidad: ${utilidad:,.2f}. Margen: {margen_promedio:.1f}%.")

            reporte = self._narrar(texto)
            desglose = [{
                'producto': f['nombre_comercial'], 'margen_total': float(f['margen_total']),
                'cantidad': int(f['cantidad'])
            } for f in filas]

            cur.execute("""
                INSERT INTO LOGS_FINANCIERO
                (periodo, facturacion_total, costo_total, utilidad_total, margen_promedio, reporte_gemini, detalles_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (periodo, facturacion, costo, utilidad, margen_promedio, reporte, json.dumps(desglose)))
            conn.commit()
            return {'ok': True, 'margen_promedio': round(margen_promedio, 2), 'reporte': reporte}
        except Exception as e:
            if conn:
                conn.rollback()
            return {'ok': False, 'error': str(e)}
        finally:
            if conn:
                conn.close()

    def _narrar(self, texto: str) -> str:
        try:
            prompt = f"Analista financiero Doko Hub Logistics. Resumen ejecutivo en 3 líneas:\n{texto}"
            return generar_texto(prompt)
        except Exception:
            return texto
