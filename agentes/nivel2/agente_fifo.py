import os
from psycopg2.extras import RealDictCursor
from agentes.gemini_client import generar_texto
from helpers.db import get_connection


class AgenteFIFO:
    """Verifica lote reportado vs lote sistema al marcar pedido preparado."""

    def verificar(self, id_pedido, id_lote_sistema, id_lote_reportado, evidencia_url: str = None) -> dict:
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            discrepancia = str(id_lote_sistema) != str(id_lote_reportado)
            detalle = "Lotes coinciden." if not discrepancia else "Discrepancia FIFO detectada."

            if discrepancia:
                cur.execute("""
                    SELECT l.lote_proveedor, p.nombre_comercial
                    FROM INVENTARIO_LOTES l
                    JOIN CAT_PRODUCTOS_MAESTRO p ON l.id_producto = p.id_producto
                    WHERE l.id_lote IN (%s, %s)
                """, (id_lote_sistema, id_lote_reportado))
                lotes = cur.fetchall()
                detalle = self._explicar_discrepancia(lotes)

            cur.execute("""
                INSERT INTO LOGS_FIFO
                (id_pedido, id_lote_correcto, id_lote_reportado, discrepancia, detalle, evidencia_url)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (id_pedido, id_lote_sistema, id_lote_reportado, discrepancia, detalle, evidencia_url))
            conn.commit()
            return {'discrepancia': discrepancia, 'detalle': detalle}
        except Exception as e:
            if conn:
                conn.rollback()
            return {'discrepancia': True, 'detalle': str(e)}
        finally:
            if conn:
                conn.close()

    def _explicar_discrepancia(self, lotes: list) -> str:
        try:
            info = ", ".join(f"{l.get('nombre_comercial')}: {l.get('lote_proveedor')}" for l in lotes)
            prompt = f"Discrepancia FIFO en bodega Doko Hub Logistics. Lotes: {info}. Explica en 2 líneas."
            return generar_texto(prompt)
        except Exception:
            return "El lote reportado no coincide con el lote sugerido por FIFO."
