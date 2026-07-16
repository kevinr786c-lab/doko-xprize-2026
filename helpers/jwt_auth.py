from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import jsonify, request, session
from psycopg2.extras import RealDictCursor

from config_bunker import JWT_EXPIRATION_HOURS, JWT_SECRET
from helpers.db import get_connection


def generar_jwt(correo_doctor: str, actor_rol: str = 'doctor', id_usuario: str | None = None) -> str:
    payload = {
        'correo_doctor': (correo_doctor or '').strip(),
        'actor_rol': actor_rol if actor_rol in {'doctor', 'asistente'} else 'doctor',
        'exp': datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS),
    }
    if id_usuario:
        payload['id_usuario'] = str(id_usuario)
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')


def verificar_jwt(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def requiere_jwt(func):
    @wraps(func)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'token_requerido'}), 401

        payload = verificar_jwt(auth_header.split(' ', 1)[1])
        correo_doctor = (payload.get('correo_doctor') or '').strip() if payload else None
        if not correo_doctor:
            return jsonify({'error': 'token_invalido_o_expirado'}), 401

        # Un token de hasta 24h no conserva acceso cuando administración desactiva
        # al médico. Esto también impide que datos de un doctor inactivo se filtren.
        conn = get_connection()
        if not conn:
            return jsonify({'error': 'servicio_no_disponible'}), 503
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                """
                SELECT correo_doctor, activo
                FROM DOCTORES
                WHERE LOWER(TRIM(correo_doctor)) = LOWER(TRIM(%s))
                """,
                (correo_doctor,),
            )
            doctor = cur.fetchone()
        finally:
            conn.close()
        if not doctor or not doctor['activo']:
            return jsonify({'error': 'doctor_inactivo'}), 403

        actor_rol = payload.get('actor_rol')
        if actor_rol not in {'doctor', 'asistente'}:
            actor_rol = 'asistente' if session.get('tipo') == 'interno' and session.get('rol') == 'asistente' else 'doctor'
        request.correo_doctor = doctor['correo_doctor']
        request.jwt_actor_rol = actor_rol
        request.jwt_id_usuario = payload.get('id_usuario') or (session.get('id_usuario') if actor_rol == 'asistente' else None)
        return func(*args, **kwargs)
    return decorated
