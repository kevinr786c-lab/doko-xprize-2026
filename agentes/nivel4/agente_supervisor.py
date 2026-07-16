import time
import uuid

import psycopg2.extras

from agentes.gemini_client import generar_texto
from agentes.nivel4.agente_auditor import AgenteAuditor
from agentes.nivel4.agente_metricas import AgenteMetricas
from agentes.nivel4.agente_riesgo import AgenteRiesgo
from helpers.db import get_connection


def _nivel_determinista(auditoria: str, riesgo: str) -> str:
    """La salud operativa nunca depende unicamente de una respuesta de IA."""
    texto = f'{auditoria} {riesgo}'.upper()
    indicadores_criticos = [
        'ERROR_SISTEMA',
        'TOKEN O PERMISOS',
        'FALLA(S) DE GOOGLE CALENDAR',
        'FALLA(S) DE GMAIL',
        'AUDITOR CALENDAR SIN EJECUCION',
    ]
    if any(indicador in texto for indicador in indicadores_criticos):
        return 'CRITICO'
    if 'ATENCION' in texto or 'ATENCIÓN' in texto:
        return 'ATENCION'
    return 'OK'


class AgenteSupervisor:
    """Consolida datos reales y usa Gemini solo para resumirlos."""

    def ejecutar(self, origen: str) -> dict:
        inicio = time.monotonic()
        conn = None
        try:
            conn = get_connection()
            if not conn:
                raise RuntimeError('sin_conexion_bd')
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            texto_auditor = AgenteAuditor().generar_micro_reporte(cur)
            agente_metricas = AgenteMetricas()
            texto_metricas = agente_metricas.generar_micro_reporte(cur)
            contexto_ia = agente_metricas.generar_contexto_ia(cur)
            texto_riesgo = AgenteRiesgo().generar_micro_reporte(cur)
            nivel = _nivel_determinista(texto_auditor, texto_riesgo)

            prompt = f"""Eres el supervisor operativo de Doko.
Resume solamente los datos reales siguientes en maximo dos lineas. No inventes cifras,
no propongas acciones automaticas y no des consejos medicos.
El contexto excluye datos brutos, agregados o derivados de Google Workspace.

CONTEXTO PROPIO DE DOKO: {contexto_ia}
RIESGO: {texto_riesgo}
"""
            try:
                resumen_ia = generar_texto(prompt)
            except Exception:
                # La operacion sigue visible aunque Gemini este limitado o caido.
                resumen_ia = texto_riesgo

            # La auditoria de Workspace se muestra de forma determinista, pero
            # nunca se transfiere a Gemini ni a otro servicio de IA.
            reporte = f'{texto_auditor} {resumen_ia}'

            duracion_ms = int((time.monotonic() - inicio) * 1000)
            cur.execute("""
                INSERT INTO LOGS_SUPERVISOR
                    (id_log, fecha_ejecucion, origen, micro_reporte_auditor,
                     micro_reporte_metricas, micro_reporte_riesgo, reporte_gemini,
                     nivel_alerta, duracion_ms)
                VALUES (%s, NOW(), %s, %s, %s, %s, %s, %s, %s)
            """, (
                str(uuid.uuid4()), origen, texto_auditor, texto_metricas,
                texto_riesgo, reporte, nivel, duracion_ms,
            ))
            conn.commit()
            return {
                'ok': True,
                'nivel_alerta': nivel,
                'reporte': reporte,
                'duracion_ms': duracion_ms,
            }
        except Exception as exc:
            if conn:
                conn.rollback()
            return {'ok': False, 'error': str(exc)}
        finally:
            if conn:
                conn.close()
