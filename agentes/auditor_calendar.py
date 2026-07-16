import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build
from psycopg2.extras import RealDictCursor

from helpers.calendar_events import leer_marcador_doko
from helpers.db import get_connection
from helpers.google_auth import TokenNoEncontrado, get_valid_token


TZ_TIJUANA = ZoneInfo('America/Tijuana')
DIAS_AUDITORIA_ADELANTE = 10
# La restricción histórica de RADAR_EVENTOS_CITAS usa este valor con mayúscula
# inicial. Las consultas actuales normalizan con UPPER(), pero el INSERT debe
# respetar exactamente el valor permitido por la base existente.
ESTADO_PENDIENTE = 'Pendiente'


class AuditorCalendar:
    """Sincroniza el calendario Google con RADAR_EVENTOS_CITAS."""

    def ejecutar(self) -> dict:
        conn = None
        resumen = {'insertadas': 0, 'reprogramadas': 0, 'canceladas': 0, 'actualizadas': 0}
        procesados, errores = 0, []
        try:
            conn = get_connection()
            if not conn:
                raise RuntimeError('No fue posible conectar con PostgreSQL.')
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('SELECT correo_doctor, nombre_doctor FROM DOCTORES WHERE activo = TRUE')

            for doctor in cur.fetchall():
                correo = doctor['correo_doctor']
                try:
                    resultado = self._auditar_doctor(correo, cur)
                    for clave in resumen:
                        resumen[clave] += resultado.get(clave, 0)
                    conn.commit()
                    procesados += 1
                except TokenNoEncontrado:
                    conn.rollback()
                    errores.append(f'{correo}: sin autorización de Google')
                except Exception as exc:
                    conn.rollback()
                    errores.append(f"{doctor['nombre_doctor']}: {exc}")

            resultado = {'ok': True, 'doctores_procesados': procesados, 'errores': errores, **resumen}
            # Telemetría segura: no expone tokens ni datos de pacientes.
            print(json.dumps({
                'evento': 'AUDITOR_CALENDAR_RESUMEN',
                'doctores_procesados': procesados,
                'insertadas': resumen['insertadas'],
                'reprogramadas': resumen['reprogramadas'],
                'canceladas': resumen['canceladas'],
                'errores': len(errores),
            }))
            return resultado
        except Exception as exc:
            if conn:
                conn.rollback()
            return {'ok': False, 'error': str(exc), 'errores': errores, **resumen}
        finally:
            if conn:
                conn.close()

    def _auditar_doctor(self, correo_doctor: str, db_cursor) -> dict:
        """Inyecta, actualiza y cancela citas próximas de un solo doctor.

        Los timestamps se guardan sin tzinfo, siempre interpretados como hora local
        de Tijuana. El bloqueo advisory evita que dos invocaciones del Scheduler
        inserten el mismo evento mientras no exista aún una restricción única.
        """
        resumen = {'insertadas': 0, 'reprogramadas': 0, 'canceladas': 0, 'actualizadas': 0}
        db_cursor.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (correo_doctor,))

        def fecha_google_a_tijuana(evento: dict):
            inicio = evento.get('start') or {}
            valor = inicio.get('dateTime') or inicio.get('date')
            if not valor:
                return None
            if 'T' not in valor:
                return datetime.strptime(valor, '%Y-%m-%d')
            fecha = datetime.fromisoformat(valor.replace('Z', '+00:00'))
            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=TZ_TIJUANA)
            return fecha.astimezone(TZ_TIJUANA).replace(tzinfo=None)

        def fecha_bd_a_tijuana(fecha):
            if not fecha:
                return None
            return fecha if fecha.tzinfo is None else fecha.astimezone(TZ_TIJUANA).replace(tzinfo=None)

        def datos_paciente(evento: dict) -> dict:
            summary = (evento.get('summary') or '').strip()
            description = (evento.get('description') or '').strip()
            correo, nombre = '', ''
            for attendee in evento.get('attendees') or []:
                email = (attendee.get('email') or '').strip()
                if email and email.lower() != correo_doctor.lower():
                    correo = email
                    nombre = (attendee.get('displayName') or '').strip()
                    break
            telefono_match = re.search(r'(?<!\d)(?:\+?52[\s.-]?)?(\d{3}[\s.-]?\d{3}[\s.-]?\d{4})(?!\d)', description)
            datos = {
                'nombre': nombre or summary or 'Paciente',
                'correo': correo,
                'telefono': re.sub(r'\D', '', telefono_match.group(1)) if telefono_match else '',
                'origen': 'google_calendar',
                'summary': summary,
                'description': description,
            }
            if not leer_marcador_doko(description):
                texto = f"{summary}\n{description}".lower()
                texto = (texto
                         .replace('á', 'a').replace('é', 'e').replace('í', 'i')
                         .replace('ó', 'o').replace('ú', 'u').replace('ü', 'u'))
                if re.search(r'\b(primera\s+vez|primera\s+visita|primera\s+consulta|1ra\s+vez|1\s*vez|nuevo\s+paciente|nueva\s+paciente)\b', texto):
                    datos['tipo_visita'] = 'Primera vez'
                elif re.search(r'\b(seguimiento|subsecuente|control|revision|revison|revicion)\b', texto):
                    datos['tipo_visita'] = 'Seguimiento'
            return datos

        def clasificar_evento(evento: dict, datos: dict):
            marcador = leer_marcador_doko(evento.get('description') or '')
            tipos = {'CITA_PACIENTE', 'BLOQUEO_HORARIO', 'APARTADO_TEMPORAL', 'EVENTO_INTERNO'}
            if marcador and marcador.get('tipo_evento') in tipos:
                return marcador['tipo_evento'], marcador.get('origen') or 'doko'
            if datos.get('correo') or datos.get('telefono'):
                return 'CITA_PACIENTE', 'google_calendar'
            return 'EVENTO_INTERNO', 'google_externo'

        def estatus_por_tipo(tipo_evento: str):
            return ESTADO_PENDIENTE

        service = build('calendar', 'v3', credentials=get_valid_token(correo_doctor), cache_discovery=False)
        ahora = datetime.now(timezone.utc)
        limite = ahora + timedelta(days=DIAS_AUDITORIA_ADELANTE)
        eventos_google = {}
        page_token = None
        while True:
            respuesta = service.events().list(
                calendarId=correo_doctor,
                timeMin=ahora.isoformat(),
                timeMax=limite.isoformat(),
                singleEvents=True,
                orderBy='startTime',
                pageToken=page_token,
            ).execute()
            for evento in respuesta.get('items', []):
                if evento.get('id') and evento.get('status') != 'cancelled':
                    eventos_google[evento['id']] = evento
            page_token = respuesta.get('nextPageToken')
            if not page_token:
                break

        for google_event_id, evento in eventos_google.items():
            fecha_cita = fecha_google_a_tijuana(evento)
            if not fecha_cita:
                continue
            datos = datos_paciente(evento)
            tipo_evento, origen_evento = clasificar_evento(evento, datos)
            id_radar = str(uuid.uuid4())
            db_cursor.execute("""
                INSERT INTO RADAR_EVENTOS_CITAS (
                    id_radar, correo_doctor, google_event_id, fecha_cita,
                    datos_paciente, estatus_confirmacion, segundo_aviso_enviado,
                    fecha_registro, tipo_evento, origen_evento, estado_operativo
                )
                SELECT %s, %s, %s, %s, %s, %s, FALSE, NOW(), %s, %s, 'activo'
                WHERE NOT EXISTS (
                    SELECT 1 FROM RADAR_EVENTOS_CITAS
                    WHERE correo_doctor = %s AND google_event_id = %s
                )
            """, (
                id_radar, correo_doctor, google_event_id, fecha_cita,
                json.dumps(datos), estatus_por_tipo(tipo_evento), tipo_evento, origen_evento,
                correo_doctor, google_event_id,
            ))
            insertadas = db_cursor.rowcount
            resumen['insertadas'] += insertadas
            if insertadas and origen_evento == 'google_externo':
                db_cursor.execute("""
                    INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle)
                    VALUES (%s, %s, %s, %s)
                """, ('EVENTO_GOOGLE_EXTERNO_SIN_CLASIFICAR', correo_doctor, 'sistema', json.dumps({
                    'id_radar': id_radar,
                    'google_event_id': google_event_id,
                    'paciente': datos.get('nombre') or 'Evento interno',
                    'fecha_cita': str(fecha_cita),
                    'motivo': 'Evento creado fuera de Doko sin correo ni teléfono. Revísalo antes de tratarlo como cita.',
                })))

        inicio_local = ahora.astimezone(TZ_TIJUANA).replace(tzinfo=None)
        limite_local = limite.astimezone(TZ_TIJUANA).replace(tzinfo=None)
        db_cursor.execute("""
            SELECT id_radar, google_event_id, datos_paciente, fecha_cita, estatus_confirmacion, tipo_evento
            FROM RADAR_EVENTOS_CITAS
            WHERE correo_doctor = %s
              AND google_event_id IS NOT NULL
              AND fecha_cita >= %s AND fecha_cita < %s
              AND UPPER(COALESCE(estatus_confirmacion, '')) NOT LIKE 'CANCEL%%'
              AND COALESCE(estado_operativo, 'activo') = 'activo'
            FOR UPDATE
        """, (correo_doctor, inicio_local, limite_local))

        for cita in db_cursor.fetchall():
            evento = eventos_google.get(cita['google_event_id'])
            if not evento:
                db_cursor.execute("""
                    UPDATE RADAR_EVENTOS_CITAS
                    SET estatus_confirmacion = 'CANCELADO_MANUALMENTE',
                        token_confirmacion = NULL,
                        token_expiracion = NULL,
                        segundo_aviso_enviado = FALSE,
                        confirmacion_enviada_en = NULL,
                        confirmacion_error_en = NULL,
                        confirmacion_error_motivo = NULL,
                        recordatorio_manana_enviado_en = NULL,
                        recordatorio_tarde_enviado_en = NULL,
                        cancelacion_automatica_en = NULL,
                        motivo_cancelacion = NULL,
                        estado_operativo = CASE
                            WHEN COALESCE(tipo_evento, 'CITA_PACIENTE') = 'CITA_PACIENTE' THEN 'cancelado'
                            ELSE 'cancelado'
                        END
                    WHERE id_radar = %s
                """, (cita['id_radar'],))
                resumen['canceladas'] += 1
                continue

            anterior = cita.get('datos_paciente') or {}
            if not isinstance(anterior, dict):
                anterior = {}
            actual = datos_paciente(evento)
            combinado = {**anterior, **{k: v for k, v in actual.items() if v}}
            if combinado != anterior:
                db_cursor.execute('UPDATE RADAR_EVENTOS_CITAS SET datos_paciente = %s WHERE id_radar = %s',
                                  (json.dumps(combinado), cita['id_radar']))
                resumen['actualizadas'] += 1

            fecha_google = fecha_google_a_tijuana(evento)
            if fecha_google and fecha_bd_a_tijuana(cita['fecha_cita']) != fecha_google:
                # Una reprogramación exige nueva confirmación, por eso vuelve a Pendiente.
                nuevo_estatus = ESTADO_PENDIENTE if (cita.get('tipo_evento') or 'CITA_PACIENTE') == 'CITA_PACIENTE' else cita.get('estatus_confirmacion')
                db_cursor.execute("""
                    UPDATE RADAR_EVENTOS_CITAS
                    SET fecha_cita = %s,
                        estatus_confirmacion = %s,
                        token_confirmacion = NULL,
                        token_expiracion = NULL,
                        segundo_aviso_enviado = FALSE
                    WHERE id_radar = %s
                """, (fecha_google, nuevo_estatus, cita['id_radar']))
                db_cursor.execute("""
                    INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle)
                    VALUES (%s, %s, %s, %s)
                """, ('CITA_REPROGRAMADA', correo_doctor, 'sistema', json.dumps({
                    'id_radar': str(cita['id_radar']),
                    'fecha_anterior': str(fecha_bd_a_tijuana(cita['fecha_cita'])),
                    'fecha_nueva': str(fecha_google),
                })))
                resumen['reprogramadas'] += 1

        return resumen
