import json
import os
from psycopg2.extras import RealDictCursor
from agentes.gemini_client import generar_texto
from helpers.db import get_connection


class AgenteTrazabilidad:
    """Busca doctores afectados por un lote. Bajo demanda."""

    def ejecutar(self, id_lote_buscado: str, solicitado_por: str = 'admin') -> dict:
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("SELECT lote_proveedor FROM INVENTARIO_LOTES WHERE id_lote = %s", (id_lote_buscado,))
            lote = cur.fetchone()
            if not lote:
                return {'ok': False, 'error': 'Lote no encontrado'}

            cur.execute("""
                SELECT DISTINCT v.correo_doctor, d.nombre_doctor, SUM(dvl.cantidad) as piezas
                FROM DETALLE_VENTA_LOTES dvl
                JOIN VENTAS_PEDIDOS_ELITE v ON dvl.id_pedido = v.id_pedido
                JOIN DOCTORES d ON v.correo_doctor = d.correo_doctor
                WHERE dvl.id_lote = %s
                  AND v.estatus_entrega IN ('preparando', 'en_camino', 'entregado')
                GROUP BY v.correo_doctor, d.nombre_doctor
            """, (id_lote_buscado,))
            afectados = cur.fetchall()
            total_piezas = sum(int(a['piezas']) for a in afectados)
            reporte = self._listar_afectados(lote['lote_proveedor'], afectados)

            cur.execute("""
                INSERT INTO LOGS_TRAZABILIDAD
                (id_lote_buscado, lote_proveedor, doctoras_afectadas, total_piezas, reporte_gemini, solicitado_por)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (id_lote_buscado, lote['lote_proveedor'],
                  json.dumps([dict(a) for a in afectados]), total_piezas, reporte, solicitado_por))
            conn.commit()
            return {'ok': True, 'afectados': len(afectados), 'total_piezas': total_piezas, 'reporte': reporte}
        except Exception as e:
            if conn:
                conn.rollback()
            return {'ok': False, 'error': str(e)}
        finally:
            if conn:
                conn.close()

    def _listar_afectados(self, lote_proveedor: str, afectados: list) -> str:
        if not afectados:
            return f"Lote {lote_proveedor}: sin doctores afectados en ventas registradas."
        lineas = [f"- {a['nombre_doctor']}: {a['piezas']} pzs." for a in afectados]
        try:
            prompt = f"Trazabilidad lote {lote_proveedor}. Doctores:\n" + "\n".join(lineas) + "\nLista en texto claro."
            return generar_texto(prompt)
        except Exception:
            return f"Lote {lote_proveedor} — doctores afectados:\n" + "\n".join(lineas)
