import base64
import html
import json
import secrets
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from psycopg2.extras import RealDictCursor

from config_bunker import BASE_URL, PORTAL_BASE_URL, PRESENCIA_BASE_DOMAIN
from helpers.db import get_connection
from helpers.google_auth import TokenNoEncontrado, get_valid_token


TZ_TIJUANA = ZoneInfo('America/Tijuana')
MODOS = {'manual', 'confirmar_24h', 'confirmar_48h_cancelar_24h'}


def _es_falla_autorizacion_google(exc):
    """Distingue una cuenta sin acceso de un fallo aislado de Calendar."""
    if isinstance(exc, TokenNoEncontrado):
        return True

    texto = str(exc or '').lower()
    marcadores_token = (
        'invalid_grant',
        'expired or revoked',
        'token has been expired',
        'debe reconectarse',
        'no hay registros de token oauth',
        'invalid credentials',
    )
    if any(marcador in texto for marcador in marcadores_token):
        return True

    if isinstance(exc, HttpError):
        estado = getattr(getattr(exc, 'resp', None), 'status', None)
        if estado == 401:
            return True
        if estado == 403 and any(
            marcador in texto
            for marcador in ('insufficient permission', 'authentication scope', 'permission denied')
        ):
            return True
    return False


def _base_confirmacion_publica():
    base = (PORTAL_BASE_URL or BASE_URL or '').strip().rstrip('/')
    if 'run.app' in base and PRESENCIA_BASE_DOMAIN:
        return f"https://{PRESENCIA_BASE_DOMAIN.strip().lower()}"
    if base:
        return base
    return f"https://{PRESENCIA_BASE_DOMAIN.strip().lower()}"


class AgenteAvisos:
    """Opera confirmaciones por doctora sin duplicar correos ni cancelaciones."""

    def correr_avisos_programados(self) -> dict:
        ahora = datetime.now(TZ_TIJUANA).replace(tzinfo=None)
        resultado = {'ok': True, 'confirmaciones': 0, 'recordatorios': 0, 'cancelaciones': 0, 'alertas': 0, 'fallidos': 0}
        for clave, cantidad in self._procesar_confirmaciones(ahora).items():
            resultado[clave] += cantidad
        for clave, cantidad in self._procesar_cancelaciones(ahora).items():
            resultado[clave] += cantidad
        if ahora.hour in (9, 14) and ahora.minute < 15:
            for clave, cantidad in self._procesar_manual_legacy(ahora, 'primer' if ahora.hour == 9 else 'segundo').items():
                resultado[clave] += cantidad
        if ahora.hour in (9, 14) and ahora.minute < 15:
            for clave, cantidad in self._procesar_recordatorios_confirmados(ahora, 'manana' if ahora.hour == 9 else 'tarde').items():
                resultado[clave] += cantidad
        resultado['modo'] = 'politicas_por_doctora'
        return resultado

    @staticmethod
    def _detalles(cita, motivo):
        datos = cita.get('datos_paciente') or {}
        return {'id_radar': str(cita['id_radar']), 'paciente': datos.get('nombre') or 'Paciente',
                'fecha_cita': str(cita.get('fecha_cita')), 'motivo': motivo}

    def _auditar(self, cur, evento, cita, motivo):
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle)
            VALUES (%s, %s, 'sistema', %s)
        """, (evento, cita['correo_doctor'], json.dumps(self._detalles(cita, motivo))))

    def _tomar(self, cur, sql, params):
        cur.execute(sql, params)
        return cur.fetchone()

    def _doctor(self, cur, correo):
        cur.execute("""
            SELECT nombre_doctor, especialidad, telefono_consultorio, direccion_consultorio,
                   maps_url, modo_confirmacion
            FROM DOCTORES WHERE correo_doctor = %s AND activo = TRUE
        """, (correo,))
        return cur.fetchone()

    def _enviar(self, cita, doctor, asunto, cuerpo, texto_plano=None):
        datos = cita.get('datos_paciente') or {}
        correo = (datos.get('correo') or '').strip()
        if not correo:
            raise ValueError('No hay correo del paciente disponible en Google Calendar.')
        service = build('gmail', 'v1', credentials=get_valid_token(cita['correo_doctor']), cache_discovery=False)
        mensaje = MIMEMultipart('alternative')
        mensaje['to'] = correo
        mensaje['from'] = cita['correo_doctor']
        mensaje['subject'] = asunto
        if texto_plano:
            mensaje.attach(MIMEText(texto_plano, 'plain', 'utf-8'))
        mensaje.attach(MIMEText(cuerpo, 'html', 'utf-8'))
        raw = base64.urlsafe_b64encode(mensaje.as_bytes()).decode()
        service.users().messages().send(userId='me', body={'raw': raw}).execute()

    def _html_confirmacion(self, cita, doctor, link, limite):
        datos = cita.get('datos_paciente') or {}
        fecha = cita['fecha_cita'].replace(tzinfo=TZ_TIJUANA) if cita['fecha_cita'].tzinfo is None else cita['fecha_cita'].astimezone(TZ_TIJUANA)
        nombre = html.escape(str(datos.get('nombre') or 'Paciente'))
        doctora = html.escape(str(doctor.get('nombre_doctor') or ''))
        limite_texto = limite.strftime('%d/%m/%Y %I:%M %p').lstrip('0')
        return f'''<div style="font-family:Arial,sans-serif;max-width:600px;color:#111827;line-height:1.55;">
          <p>Hola {nombre}, el consultorio de {doctora} necesita confirmar tu asistencia.</p>
          <p><strong>Fecha:</strong> {fecha.strftime('%d/%m/%Y')}<br><strong>Hora:</strong> {fecha.strftime('%I:%M %p').lstrip('0')}<br><strong>Doctora:</strong> {doctora}</p>
          <p>Por favor revisa tu cita antes del <strong>{limite_texto}</strong>.</p>
          <p><a href="{link}" style="background:#173a63;color:#fff;padding:12px 20px;text-decoration:none;border-radius:8px;display:inline-block;font-weight:bold;">Ir a confirmar cita</a></p>
          <p style="color:#4b5563;font-size:13px;">El enlace abre una p&aacute;gina segura de Doko donde podr&aacute;s confirmar o cancelar tu cita.</p>
          <p style="color:#4b5563;font-size:13px;">Si esperabas este correo y no lo ves en tu bandeja de entrada, revisa tambi&eacute;n spam o correo no deseado.</p>
          <p style="color:#4b5563;font-size:13px;">Mensaje enviado por el consultorio mediante Doko.</p>
        </div>'''

    def _texto_confirmacion(self, cita, doctor, link, limite):
        datos = cita.get('datos_paciente') or {}
        fecha = cita['fecha_cita'].replace(tzinfo=TZ_TIJUANA) if cita['fecha_cita'].tzinfo is None else cita['fecha_cita'].astimezone(TZ_TIJUANA)
        nombre = str(datos.get('nombre') or 'Paciente')
        doctora = str(doctor.get('nombre_doctor') or '')
        return (
            f"Hola {nombre}, el consultorio de {doctora} necesita confirmar tu asistencia.\n\n"
            f"Fecha: {fecha.strftime('%d/%m/%Y')}\n"
            f"Hora: {fecha.strftime('%I:%M %p').lstrip('0')}\n"
            f"Doctora: {doctora}\n"
            f"Confirma antes del: {limite.strftime('%d/%m/%Y %I:%M %p').lstrip('0')}\n\n"
            f"Abre este enlace para confirmar o cancelar tu cita:\n{link}\n\n"
            "Si esperabas este correo y no lo ves en tu bandeja de entrada, revisa tambien spam o correo no deseado.\n\n"
            "Mensaje enviado por el consultorio mediante Doko."
        )

    def _html_recordatorio(self, cita, doctor):
        datos = cita.get('datos_paciente') or {}
        fecha = cita['fecha_cita'].replace(tzinfo=TZ_TIJUANA) if cita['fecha_cita'].tzinfo is None else cita['fecha_cita'].astimezone(TZ_TIJUANA)
        nombre = html.escape(str(datos.get('nombre') or 'Paciente'))
        return f'''<div style="font-family:Arial,sans-serif;max-width:600px;color:#111827;">
          <p>Hola {nombre}, te recordamos tu cita confirmada.</p>
          <p><strong>Fecha:</strong> {fecha.strftime('%d/%m/%Y')}<br><strong>Hora:</strong> {fecha.strftime('%I:%M %p').lstrip('0')}<br>
          <strong>Doctora:</strong> {html.escape(str(doctor.get('nombre_doctor') or ''))}<br>
          <strong>Direcci&oacute;n:</strong> {html.escape(str(doctor.get('direccion_consultorio') or ''))}</p>
          <p style="color:#4b5563;font-size:13px;">Si no encuentras los correos del consultorio, revisa tambi&eacute;n spam o correo no deseado.</p>
        </div>'''

    @staticmethod
    def _limite_confirmacion(cita, ahora):
        if cita.get('modo_confirmacion') == 'confirmar_48h_cancelar_24h':
            return ahora + timedelta(hours=24)
        return cita['fecha_cita']

    def _procesar_confirmaciones(self, ahora):
        resultado = {'confirmaciones': 0, 'recordatorios': 0, 'cancelaciones': 0, 'alertas': 0, 'fallidos': 0}
        conn = get_connection()
        if not conn:
            resultado['ok'] = False
            resultado['fallidos'] = 1
            return resultado
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            while True:
                cita = self._tomar(cur, """
                    SELECT r.*, d.modo_confirmacion FROM RADAR_EVENTOS_CITAS r
                    JOIN DOCTORES d ON d.correo_doctor = r.correo_doctor AND d.activo = TRUE
                    WHERE UPPER(COALESCE(r.estatus_confirmacion, '')) = 'PENDIENTE'
                      AND COALESCE(r.tipo_evento, 'CITA_PACIENTE') = 'CITA_PACIENTE'
                      AND COALESCE(r.estado_operativo, 'activo') = 'activo'
                      AND d.modo_confirmacion IN ('confirmar_24h', 'confirmar_48h_cancelar_24h')
                      AND COALESCE(r.requiere_confirmacion_enlace, TRUE) = TRUE
                      AND NULLIF(TRIM(COALESCE(r.datos_paciente->>'correo', r.correo_manual, '')), '') IS NOT NULL
                      AND r.confirmacion_enviada_en IS NULL
                      AND (r.confirmacion_error_en IS NULL OR r.confirmacion_error_en < %s - INTERVAL '1 hour')
                      AND r.fecha_cita > %s
                      AND (
                        (d.modo_confirmacion = 'confirmar_24h' AND r.fecha_cita <= %s + INTERVAL '24 hours')
                        OR (
                          d.modo_confirmacion = 'confirmar_48h_cancelar_24h'
                          AND r.fecha_cita >= DATE_TRUNC('day', %s::timestamp + INTERVAL '2 days')
                          AND r.fecha_cita < DATE_TRUNC('day', %s::timestamp + INTERVAL '3 days')
                          AND (
                            (%s::time >= TIME '08:00' AND %s::time < TIME '09:00' AND r.fecha_cita::time < TIME '14:00')
                            OR %s::time >= TIME '09:00'
                          )
                        )
                      )
                    ORDER BY r.fecha_cita ASC FOR UPDATE SKIP LOCKED LIMIT 1
                """, (ahora, ahora, ahora, ahora, ahora, ahora, ahora, ahora))
                if not cita:
                    conn.rollback()
                    break
                doctor = self._doctor(cur, cita['correo_doctor'])
                limite = self._limite_confirmacion(cita, ahora)
                try:
                    token = secrets.token_urlsafe(32)
                    link = f"{_base_confirmacion_publica()}/c/{token}"
                    asunto = f"Confirma tu cita con {doctor.get('nombre_doctor') or 'tu consultorio'}"
                    self._enviar(
                        cita,
                        doctor,
                        asunto,
                        self._html_confirmacion(cita, doctor, link, limite),
                        self._texto_confirmacion(cita, doctor, link, limite),
                    )
                    cur.execute("""
                        UPDATE RADAR_EVENTOS_CITAS SET token_confirmacion=%s, token_expiracion=%s,
                            confirmacion_enviada_en=%s, confirmacion_error_en=NULL, confirmacion_error_motivo=NULL,
                            segundo_aviso_enviado=FALSE WHERE id_radar=%s
                    """, (token, limite, ahora, cita['id_radar']))
                    conn.commit(); resultado['confirmaciones'] += 1
                except TokenNoEncontrado:
                    cur.execute("UPDATE RADAR_EVENTOS_CITAS SET confirmacion_error_en=%s, confirmacion_error_motivo=%s WHERE id_radar=%s", (ahora, 'Autorización de Gmail no disponible.', cita['id_radar']))
                    self._auditar(cur, 'CONFIRMACION_TOKEN_GOOGLE_FALLIDO', cita, 'No se pudo usar Gmail de la doctora.')
                    conn.commit(); resultado['alertas'] += 1
                except Exception as exc:
                    motivo = str(exc)[:220]
                    if isinstance(exc, ValueError):
                        evento = 'CONFIRMACION_SIN_CORREO'
                    elif _es_falla_autorizacion_google(exc):
                        evento = 'CONFIRMACION_TOKEN_GOOGLE_FALLIDO'
                    else:
                        evento = 'CONFIRMACION_ENVIO_FALLIDO'
                    cur.execute("UPDATE RADAR_EVENTOS_CITAS SET confirmacion_error_en=%s, confirmacion_error_motivo=%s WHERE id_radar=%s", (ahora, motivo, cita['id_radar']))
                    self._auditar(cur, evento, cita, motivo)
                    conn.commit(); resultado['alertas'] += 1; resultado['fallidos'] += 1
        finally:
            conn.close()
        return resultado

    def _procesar_manual_legacy(self, ahora, tipo):
        """Conserva el aviso de mañana para doctoras que aún usan modo manual."""
        resultado = {'confirmaciones': 0, 'recordatorios': 0, 'cancelaciones': 0, 'alertas': 0, 'fallidos': 0}
        inicio = ahora.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        fin = inicio + timedelta(days=1)
        conn = get_connection()
        if not conn:
            resultado['fallidos'] = 1
            return resultado
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            while True:
                condicion = 'r.token_confirmacion IS NULL' if tipo == 'primer' else "r.token_confirmacion IS NOT NULL AND (r.segundo_aviso_enviado IS NULL OR r.segundo_aviso_enviado = FALSE)"
                cita = self._tomar(cur, f"""
                    SELECT r.* FROM RADAR_EVENTOS_CITAS r JOIN DOCTORES d ON d.correo_doctor=r.correo_doctor
                    WHERE d.modo_confirmacion='manual' AND UPPER(COALESCE(r.estatus_confirmacion, ''))='PENDIENTE'
                      AND COALESCE(r.tipo_evento, 'CITA_PACIENTE') = 'CITA_PACIENTE'
                      AND COALESCE(r.estado_operativo, 'activo') = 'activo'
                      AND COALESCE(r.requiere_confirmacion_enlace, TRUE) = TRUE
                      AND NULLIF(TRIM(COALESCE(r.datos_paciente->>'correo', r.correo_manual, '')), '') IS NOT NULL
                      AND r.fecha_cita >= %s AND r.fecha_cita < %s AND {condicion}
                    ORDER BY r.fecha_cita ASC FOR UPDATE SKIP LOCKED LIMIT 1
                """, (inicio, fin))
                if not cita:
                    conn.rollback(); break
                doctor = self._doctor(cur, cita['correo_doctor'])
                try:
                    token = cita.get('token_confirmacion') or secrets.token_urlsafe(32)
                    link = f"{_base_confirmacion_publica()}/c/{token}"
                    asunto = f"Revisa tu cita con {doctor.get('nombre_doctor') or 'tu consultorio'}"
                    limite = cita['fecha_cita'] + timedelta(hours=1)
                    self._enviar(
                        cita,
                        doctor,
                        asunto,
                        self._html_confirmacion(cita, doctor, link, limite),
                        self._texto_confirmacion(cita, doctor, link, limite),
                    )
                    if tipo == 'primer':
                        cur.execute("UPDATE RADAR_EVENTOS_CITAS SET token_confirmacion=%s, token_expiracion=%s, segundo_aviso_enviado=FALSE WHERE id_radar=%s", (token, cita['fecha_cita'] + timedelta(hours=1), cita['id_radar']))
                        resultado['confirmaciones'] += 1
                    else:
                        cur.execute("UPDATE RADAR_EVENTOS_CITAS SET segundo_aviso_enviado=TRUE WHERE id_radar=%s", (cita['id_radar'],))
                        resultado['recordatorios'] += 1
                    conn.commit()
                except Exception as exc:
                    self._auditar(cur, 'CONFIRMACION_ENVIO_FALLIDO', cita, str(exc)[:220])
                    conn.commit(); resultado['alertas'] += 1; resultado['fallidos'] += 1
        finally:
            conn.close()
        return resultado

    def _procesar_cancelaciones(self, ahora):
        resultado = {'confirmaciones': 0, 'recordatorios': 0, 'cancelaciones': 0, 'alertas': 0, 'fallidos': 0}
        doctores_google_bloqueados = set()
        eventos_google_bloqueados = set()
        conn = get_connection()
        if not conn:
            resultado['fallidos'] = 1
            return resultado
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            while True:
                cita = self._tomar(cur, """
                    SELECT r.* FROM RADAR_EVENTOS_CITAS r JOIN DOCTORES d ON d.correo_doctor=r.correo_doctor
                    WHERE d.activo=TRUE AND d.modo_confirmacion='confirmar_48h_cancelar_24h'
                      AND COALESCE(r.tipo_evento, 'CITA_PACIENTE') = 'CITA_PACIENTE'
                      AND COALESCE(r.estado_operativo, 'activo') = 'activo'
                      AND (
                          UPPER(COALESCE(r.estatus_confirmacion, '')) = 'PENDIENTE'
                          OR (UPPER(COALESCE(r.estatus_confirmacion, '')) = 'CANCELADO'
                              AND r.motivo_cancelacion = 'EN_PROCESO_NO_CONFIRMADA')
                      )
                      AND r.confirmacion_enviada_en IS NOT NULL
                      AND r.confirmacion_enviada_en <= %s - INTERVAL '24 hours'
                      AND r.token_expiracion IS NOT NULL
                      AND r.token_expiracion <= %s
                      AND NOT (LOWER(TRIM(r.correo_doctor)) = ANY(%s::text[]))
                      AND NOT (r.id_radar::text = ANY(%s::text[]))
                    ORDER BY r.fecha_cita ASC FOR UPDATE SKIP LOCKED LIMIT 1
                """, (ahora, ahora, list(doctores_google_bloqueados), list(eventos_google_bloqueados)))
                if not cita:
                    conn.rollback(); break
                # The database only accepts the official CANCELADO state. The reason
                # keeps an interrupted Google Calendar deletion recoverable next cycle.
                cur.execute("""
                    UPDATE RADAR_EVENTOS_CITAS
                    SET estatus_confirmacion='CANCELADO',
                        motivo_cancelacion='EN_PROCESO_NO_CONFIRMADA',
                        cancelacion_automatica_en=%s
                    WHERE id_radar=%s
                """, (ahora, cita['id_radar']))
                conn.commit()
                try:
                    if cita.get('google_event_id'):
                        service = build('calendar', 'v3', credentials=get_valid_token(cita['correo_doctor']), cache_discovery=False)
                        try:
                            service.events().delete(calendarId=cita['correo_doctor'], eventId=cita['google_event_id']).execute()
                        except HttpError as exc:
                            if exc.resp.status != 404:
                                raise
                    cur.execute("""
                        UPDATE RADAR_EVENTOS_CITAS SET estatus_confirmacion='CANCELADO',
                            token_confirmacion=NULL, token_expiracion=NULL, motivo_cancelacion='NO_CONFIRMADA',
                            estado_operativo='cancelado'
                        WHERE id_radar=%s
                    """, (cita['id_radar'],))
                    self._auditar(cur, 'CANCELACION_AUTOMATICA_NO_CONFIRMADA', cita, 'No confirmó dentro de la ventana de 24 horas.')
                    conn.commit(); resultado['cancelaciones'] += 1
                except Exception as exc:
                    falla_autorizacion = _es_falla_autorizacion_google(exc)
                    cur.execute("""
                        UPDATE RADAR_EVENTOS_CITAS SET estatus_confirmacion='Pendiente',
                            motivo_cancelacion=NULL, cancelacion_automatica_en=NULL,
                            estado_operativo='activo',
                            confirmacion_error_en=%s, confirmacion_error_motivo=%s WHERE id_radar=%s
                    """, (ahora, str(exc)[:220], cita['id_radar']))
                    if falla_autorizacion:
                        self._auditar(
                            cur,
                            'CANCELACION_GOOGLE_AUTORIZACION_FALLIDA',
                            cita,
                            'La cuenta de Google requiere reconexion antes de liberar citas.',
                        )
                    else:
                        self._auditar(
                            cur,
                            'CANCELACION_GOOGLE_FALLIDA',
                            cita,
                            'Google Calendar no pudo liberar este evento; las demas citas siguen procesandose.',
                        )
                    conn.commit(); resultado['alertas'] += 1; resultado['fallidos'] += 1
                    eventos_google_bloqueados.add(str(cita['id_radar']))
                    if falla_autorizacion:
                        doctores_google_bloqueados.add((cita.get('correo_doctor') or '').strip().lower())
        finally:
            conn.close()
        return resultado

    def _procesar_recordatorios_confirmados(self, ahora, momento):
        resultado = {'confirmaciones': 0, 'recordatorios': 0, 'cancelaciones': 0, 'alertas': 0, 'fallidos': 0}
        columna = 'recordatorio_manana_enviado_en' if momento == 'manana' else 'recordatorio_tarde_enviado_en'
        inicio = (ahora.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))
        fin = inicio + timedelta(days=1)
        conn = get_connection()
        if not conn:
            resultado['fallidos'] = 1
            return resultado
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            while True:
                cita = self._tomar(cur, f"""
                    SELECT r.* FROM RADAR_EVENTOS_CITAS r
                    WHERE UPPER(COALESCE(r.estatus_confirmacion, '')) LIKE 'CONFIRM%%'
                      AND COALESCE(r.tipo_evento, 'CITA_PACIENTE') = 'CITA_PACIENTE'
                      AND COALESCE(r.estado_operativo, 'activo') = 'activo'
                      AND NULLIF(TRIM(COALESCE(r.datos_paciente->>'correo', r.correo_manual, '')), '') IS NOT NULL
                      AND r.fecha_cita >= %s AND r.fecha_cita < %s AND r.{columna} IS NULL
                    ORDER BY r.fecha_cita ASC FOR UPDATE SKIP LOCKED LIMIT 1
                """, (inicio, fin))
                if not cita:
                    conn.rollback(); break
                doctor = self._doctor(cur, cita['correo_doctor'])
                try:
                    self._enviar(cita, doctor, 'Recordatorio de tu cita confirmada', self._html_recordatorio(cita, doctor))
                    cur.execute(f"UPDATE RADAR_EVENTOS_CITAS SET {columna}=%s WHERE id_radar=%s", (ahora, cita['id_radar']))
                    conn.commit(); resultado['recordatorios'] += 1
                except Exception as exc:
                    if isinstance(exc, ValueError):
                        evento = 'RECORDATORIO_SIN_CORREO'
                    elif _es_falla_autorizacion_google(exc):
                        evento = 'RECORDATORIO_TOKEN_GOOGLE_FALLIDO'
                    else:
                        evento = 'RECORDATORIO_CONFIRMADO_FALLIDO'
                    self._auditar(cur, evento, cita, str(exc)[:220])
                    conn.commit(); resultado['alertas'] += 1; resultado['fallidos'] += 1
        finally:
            conn.close()
        return resultado

