import json
from flask import Blueprint, render_template, jsonify, request
from psycopg2.extras import RealDictCursor
from googleapiclient.discovery import build

from helpers.db import get_connection
from helpers.calendar_events import marcar_evento_confirmado_doko
from helpers.google_auth import get_valid_token
from helpers.notificaciones_citas import enviar_correo_cita_confirmada

confirmacion_bp = Blueprint("confirmacion_bp", __name__)

# ==============================================================================
# RUTA DE INTERFAZ GRÁFICA (GET)
# ==============================================================================

@confirmacion_bp.route("/c/<token>", methods=["GET"])
def ver_accion(token):
    """
    Renderiza la página donde el paciente confirma o cancelo.
    Solo verifica si el token es válido y no ha expirado.
    """
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id_radar, correo_doctor, datos_paciente, fecha_cita FROM RADAR_EVENTOS_CITAS
            WHERE token_confirmacion = %s AND token_expiracion > NOW()
        """, (token,))
        cita = cur.fetchone()
        
        valido = bool(cita)
        doctor = None
        if valido:
            cur.execute("""
                SELECT nombre_doctor, especialidad, telefono_consultorio, direccion_consultorio,
                       maps_url, foto_perfil_url, color_tema
                FROM DOCTORES WHERE correo_doctor = %s
            """, (cita["correo_doctor"],))
            doctor = cur.fetchone()
        
        return render_template("confirmacion/accion.html", estado="valido", cita=cita, doctor=doctor, token=token) if valido else render_template("confirmacion/accion.html", estado="invalido")
    finally:
        conn.close()

# ==============================================================================
# RUTA DE EJECUCIÓN TÁCTICA (POST) - REGLA DE NEGOCIO 2.3
# ==============================================================================

@confirmacion_bp.route("/c/<token>/accion", methods=["POST"])
def procesar_accion(token):
    """
    Implementación EXACTA del flujo 2.3:
    Solo se invalida el token si Google Calendar responde OK.
    """
    data = request.get_json(silent=True) or {}
    accion = data.get("accion")

    if accion not in ["confirmar", "cancelar"]:
        return jsonify({"ok": False, "error": "Acción no permitida"}), 400

    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 1. Validar token
        cur.execute("""
            SELECT id_radar, correo_doctor, google_event_id, datos_paciente, fecha_cita
            FROM RADAR_EVENTOS_CITAS
            WHERE token_confirmacion = %s AND token_expiracion > NOW()
              AND UPPER(COALESCE(estatus_confirmacion, '')) LIKE 'PEND%%'
            FOR UPDATE
        """, (token,))
        cita = cur.fetchone()
        
        if not cita:
            return render_template("confirmacion/accion.html", estado="invalido"), 400

        # Fetch doctor info for the template
        cur.execute("""
            SELECT nombre_doctor, especialidad, telefono_consultorio, direccion_consultorio,
                   maps_url, foto_perfil_url, color_tema
            FROM DOCTORES WHERE correo_doctor = %s
        """, (cita["correo_doctor"],))
        doctor = cur.fetchone()

        # 2. Actualizar estatus en la BD
        nuevo_estatus = "CANCELADO" if accion == "cancelar" else "CONFIRMADO"
        cur.execute("""
            UPDATE RADAR_EVENTOS_CITAS 
            SET estatus_confirmacion = %s,
                estado_operativo = CASE
                    WHEN %s = 'cancelar' THEN 'cancelado'
                    ELSE COALESCE(estado_operativo, 'activo')
                END
            WHERE id_radar = %s
        """, (nuevo_estatus, accion, cita["id_radar"]))

        # 3. Sincronización con Google Calendar (Punto Crítico)
        # Si falla aquí, el except atrapa el error y el rollback salva el token
        if accion == "cancelar" and cita["google_event_id"]:
            creds = get_valid_token(cita["correo_doctor"])
            service = build("calendar", "v3", credentials=creds)
            
            # Llamada destructiva a la API de Google
            service.events().delete(
                calendarId=cita["correo_doctor"], 
                eventId=cita["google_event_id"]
            ).execute()

        # 4. Solo si Google OK (o si es confirmación): invalidar token
        cur.execute("""
            UPDATE RADAR_EVENTOS_CITAS 
            SET token_confirmacion = NULL, token_expiracion = NULL 
            WHERE id_radar = %s
        """, (cita["id_radar"],))

        # 5. Auditoría de Seguridad
        tipo_evento = "CANCELACION_PACIENTE" if accion == "cancelar" else "CONFIRMACION_PACIENTE"
        detalle_json = json.dumps({
            "id_radar": str(cita["id_radar"]), 
            "accion": accion
        })
        
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, detalle) 
            VALUES (%s, %s, %s)
        """, (tipo_evento, token[:8] + "...", detalle_json))

        if accion == "confirmar":
            try:
                marcar_evento_confirmado_doko(cita["correo_doctor"], cita.get("google_event_id"))
            except Exception as exc:
                cur.execute("""
                    INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle)
                    VALUES (%s, %s, %s, %s)
                """, (
                    "CALENDAR_CONFIRMADA_FALLIDA",
                    cita["correo_doctor"],
                    "sistema",
                    json.dumps({"id_radar": str(cita["id_radar"]), "error": str(exc)[:220]}),
                ))
        
        # Un solo commit al final. Todo o nada.
        conn.commit()
        if accion == "confirmar":
            enviar_correo_cita_confirmada(cita, doctor)
        return render_template("confirmacion/accion.html", estado="resultado_cancelado", doctor=doctor) if accion == "cancelar" else render_template("confirmacion/accion.html", estado="resultado_confirmado", doctor=doctor)

    except Exception as e:
        conn.rollback()   # ¡El token sobrevive para un reintento!
        print(f"Error crítico procesando token {token[:8]}: {str(e)}")
        return render_template("confirmacion/accion.html", estado="error")
    finally:
        conn.close()
