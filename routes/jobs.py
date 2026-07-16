import hmac
import json
import time
import traceback

from flask import Blueprint, jsonify, request

from config_bunker import JOB_SECRET
from helpers.db import get_connection

jobs_bp = Blueprint('jobs_bp', __name__)


def verificar_secreto():
    """Valida el secreto de Cloud Scheduler sin comparaciones vulnerables."""
    recibido = request.headers.get('X-Job-Secret', '')
    return bool(JOB_SECRET) and hmac.compare_digest(recibido, JOB_SECRET)


def _registrar_ejecucion(nombre: str, resultado: dict, duracion_ms: int) -> None:
    """Telemetría persistente usando la tabla oficial de auditoría."""
    conn = get_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle)
            VALUES (%s, %s, %s, %s)
        """, (
            'EJECUCION_JOB',
            nombre,
            'sistema',
            json.dumps({
                'ok': bool(resultado.get('ok')),
                'duracion_ms': duracion_ms,
                'resumen': resultado,
            }, default=str),
        ))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()


def _ejecutar_job(nombre: str, funcion):
    lock_conn = get_connection()
    if not lock_conn:
        return jsonify({'ok': False, 'error': 'sin_conexion_bd'}), 503
    try:
        lock_cur = lock_conn.cursor()
        lock_cur.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (f'doko:job:{nombre}',))
        if not lock_cur.fetchone()[0]:
            # Scheduler puede reintentar sin volver a ejecutar una tarea activa.
            lock_conn.rollback()
            lock_conn.close()
            return jsonify({'ok': True, 'resultado': {'ok': True, 'estado': 'ya_en_ejecucion'}}), 200
    except Exception:
        lock_conn.close()
        return jsonify({'ok': False, 'error': 'no_se_pudo_bloquear_job'}), 503

    inicio = time.monotonic()
    try:
        resultado = funcion()
        respuesta = {'ok': bool(resultado.get('ok', True)), 'resultado': resultado}
        codigo = 200 if respuesta['ok'] else 500
    except Exception as exc:
        print(f'Error en job {nombre}: {traceback.format_exc()}')
        resultado = {'ok': False, 'error': str(exc)}
        respuesta = resultado
        codigo = 500

    finally:
        try:
            lock_cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (f'doko:job:{nombre}',))
            lock_conn.commit()
        finally:
            lock_conn.close()

    _registrar_ejecucion(nombre, resultado, int((time.monotonic() - inicio) * 1000))
    return jsonify(respuesta), codigo


@jobs_bp.route('/jobs/auditoria', methods=['POST'])
def job_auditoria():
    if not verificar_secreto():
        return jsonify({'ok': False, 'error': 'Acceso denegado.'}), 403

    from agentes.auditor_calendar import AuditorCalendar
    return _ejecutar_job('auditoria_calendar', lambda: AuditorCalendar().ejecutar())


@jobs_bp.route('/jobs/avisos', methods=['POST'])
def job_avisos():
    if not verificar_secreto():
        return jsonify({'ok': False, 'error': 'Acceso denegado.'}), 403

    from agentes.agente_avisos import AgenteAvisos
    return _ejecutar_job('avisos_citas', lambda: AgenteAvisos().correr_avisos_programados())


@jobs_bp.route('/jobs/supervisor', methods=['POST'])
def job_supervisor():
    if not verificar_secreto():
        return jsonify({'ok': False, 'error': 'Acceso denegado.'}), 403

    from agentes.nivel4.agente_supervisor import AgenteSupervisor
    return _ejecutar_job('supervisor', lambda: AgenteSupervisor().ejecutar(origen='automatico'))
