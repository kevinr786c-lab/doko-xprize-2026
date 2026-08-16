import json
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from flask import Blueprint, jsonify, request, session
from googleapiclient.discovery import build
from psycopg2.extras import RealDictCursor

import config_bunker
from agentes.asistente_panel import (
    clasificar_con_gemini,
    clasificar_local,
    construir_paquete_intencion,
    describir_flujo_correo,
    explicacion_operativa,
    interpretar_busqueda_agenda,
    metadatos_flujo_guardado,
    paquete_tiene_contexto,
    respuesta_desde_explicacion,
)
from agentes.asistente_uso import finalizar_gemini, hash_actor, registrar_regla, reservar_gemini
from agentes.contexto_asistente import (
    CONTEXT_KEY,
    contexto_habilitado_para_doctor,
    crear_contexto,
    huella_contextual,
    resolver_continuidad,
    validar_contexto,
)
from helpers.calendar_events import MARKER_PREFIX, actualizar_evento_doko, borrar_evento_doko, crear_evento_doko, leer_marcador_doko, marcar_evento_confirmado_doko
from helpers.db import get_connection
from helpers.google_auth import TokenNoEncontrado, get_valid_token
from helpers.jwt_auth import requiere_jwt
from helpers.notificaciones_citas import enviar_correo_cita_confirmada, enviar_correo_cita_registrada
from helpers.storage import subir_archivo

panel_bp = Blueprint("panel_bp", __name__)
TZ_TIJUANA = ZoneInfo("America/Tijuana")
TIPOS_EVENTO = {"CITA_PACIENTE", "BLOQUEO_HORARIO", "APARTADO_TEMPORAL", "EVENTO_INTERNO"}
ESTADOS_OPERATIVOS = {"activo", "liberado", "convertido_a_cita", "cancelado"}


def _mensaje_error_operativo(exc) -> str:
    """Devuelve un mensaje breve para UI sin exponer respuestas crudas de Google."""
    texto = str(exc or "")
    texto_bajo = texto.lower()
    es_google = any(
        clave in texto_bajo
        for clave in (
            "google",
            "calendar",
            "gmail",
            "oauth",
            "invalid_grant",
            "googleapiclient",
            "refresherror",
            "insufficient authentication scopes",
        )
    )
    if isinstance(exc, TokenNoEncontrado) or "invalid_grant" in texto_bajo or "expired or revoked" in texto_bajo:
        return "Conecta con Google para continuar."
    if "doctores_color_tema_check" in texto_bajo or "color_tema" in texto_bajo:
        return "Color de tema no válido o pendiente de actualización."
    if es_google and ("insufficient" in texto_bajo or "scope" in texto_bajo or "permission" in texto_bajo):
        return "Google no autorizó esta acción. Revisa permisos y conecta de nuevo."
    if es_google and ("google calendar" in texto_bajo or "calendar" in texto_bajo):
        return "Google no pudo completar la acción. Intenta de nuevo o conecta de nuevo."
    if es_google and "gmail" in texto_bajo:
        return "Gmail no pudo enviar el correo. Revisa permisos o intenta de nuevo."
    if isinstance(exc, PermissionError):
        return texto or "No tienes permiso para realizar esta acción."
    return texto or "No se pudo completar la acción."


def _usuario_interno_actual():
    if getattr(request, "jwt_actor_rol", None) == "asistente":
        return getattr(request, "jwt_id_usuario", None)
    return None


def _rol_actor_actual():
    return "asistente" if getattr(request, "jwt_actor_rol", None) == "asistente" else "doctor"


def _asegurar_doctora_asignada_si_asistente(cur, correo_doctor):
    if getattr(request, "jwt_actor_rol", None) != "asistente":
        return
    id_usuario = getattr(request, "jwt_id_usuario", None)
    if not id_usuario:
        raise PermissionError("Sesión de asistente requerida.")
    cur.execute("""
        SELECT 1
        FROM ASISTENTES_DOCTORES
        WHERE id_usuario = %s
          AND LOWER(TRIM(correo_doctor)) = LOWER(TRIM(%s))
    """, (id_usuario, correo_doctor))
    if not cur.fetchone():
        raise PermissionError("La asistente no está asignada a esta doctora.")


def _busqueda_asistente_habilitada(correo_doctor: str) -> bool:
    correo = str(correo_doctor or "").strip().lower()
    return (
        "*" in config_bunker.PANEL_ASSISTANT_SEARCH_DOCTORS
        or correo in config_bunker.PANEL_ASSISTANT_SEARCH_DOCTORS
    )


def _parse_inicio(data):
    valor = (data.get("inicio") or data.get("fecha_cita") or "").strip()
    if not valor:
        fecha = (data.get("fecha") or "").strip()
        hora = (data.get("hora") or "").strip()
        valor = f"{fecha}T{hora}" if fecha and hora else ""
    if not valor:
        raise ValueError("Selecciona fecha y hora.")
    try:
        inicio = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Fecha u hora no válida.") from exc
    if inicio.tzinfo:
        inicio = inicio.astimezone(TZ_TIJUANA).replace(tzinfo=None)
    return inicio


def _duracion(data):
    try:
        valor = int(data.get("duracion_minutos") or data.get("duracion") or 30)
    except (TypeError, ValueError):
        valor = 30
    if valor < 10 or valor > 480:
        raise ValueError("La duración debe estar entre 10 y 480 minutos.")
    return valor


def _normalizar_tipo(tipo):
    tipo = (tipo or "CITA_PACIENTE").strip().upper()
    if tipo not in TIPOS_EVENTO:
        raise ValueError("Tipo de evento no permitido.")
    return tipo


def _estatus_inicial(tipo_evento, confirmado=False):
    return "CONFIRMADO" if confirmado else "Pendiente"


def _limpiar_metadatos_doko(texto):
    """Oculta marcadores técnicos sin borrar notas reales del consultorio."""
    valor = str(texto or "").strip()
    if not valor:
        return ""
    if MARKER_PREFIX not in valor and "Creado desde Doko (" not in valor:
        return valor

    limpias = []
    for linea in valor.splitlines():
        visible = linea.strip()
        normalizada = visible.lower()
        if not visible or visible.startswith(MARKER_PREFIX):
            continue
        if normalizada.startswith("creado desde doko ("):
            continue
        if normalizada.startswith(("telefono:", "teléfono:", "correo:")):
            continue
        if normalizada.startswith("notas internas:"):
            visible = visible.split(":", 1)[1].strip()
        if visible:
            limpias.append(visible)
    return "\n".join(limpias)


def _datos_evento(data, tipo_evento, duracion_minutos):
    nombre = (data.get("nombre_paciente") or data.get("paciente") or data.get("titulo") or "").strip()
    correo = (data.get("correo") or data.get("correo_paciente") or "").strip()
    telefono = (data.get("telefono") or data.get("telefono_paciente") or "").strip()
    notas = _limpiar_metadatos_doko(data.get("notas_internas") or data.get("notas") or "")
    motivo = (data.get("motivo") or "").strip()
    if tipo_evento == "CITA_PACIENTE" and not nombre:
        raise ValueError("El nombre del paciente es obligatorio.")
    if tipo_evento in {"BLOQUEO_HORARIO", "EVENTO_INTERNO"} and not nombre:
        nombre = motivo or "Bloqueo de horario"
    if tipo_evento == "APARTADO_TEMPORAL" and not nombre:
        nombre = motivo or "Apartado temporal"
    return {
        "nombre": nombre or "Paciente",
        "correo": correo,
        "telefono": "".join(ch for ch in telefono if ch.isdigit()),
        "origen": "doko",
        "summary": nombre,
        "description": notas or motivo,
        "motivo": motivo,
        "duracion_minutos": duracion_minutos,
    }


def _es_cita_cercana_con_comprobante(tipo_evento, inicio, datos):
    if tipo_evento != "CITA_PACIENTE" or not (datos.get("correo") or "").strip():
        return False
    inicio_local = inicio.replace(tzinfo=TZ_TIJUANA) if inicio.tzinfo is None else inicio.astimezone(TZ_TIJUANA)
    hoy = datetime.now(TZ_TIJUANA).date()
    return hoy <= inicio_local.date() <= hoy + timedelta(days=1)


def _enviar_y_registrar_comprobante(conn, cur, cita, doctor):
    """El correo es secundario: nunca revierte una cita ya creada."""
    try:
        resultado = enviar_correo_cita_registrada(cita, doctor)
        if resultado.get("ok"):
            cur.execute("""
                UPDATE RADAR_EVENTOS_CITAS
                SET correo_registro_enviado_en = NOW(),
                    correo_registro_error_en = NULL,
                    correo_registro_error_motivo = NULL
                WHERE id_radar = %s
                  AND correo_registro_enviado_en IS NULL
            """, (cita["id_radar"],))
            evento = "CORREO_CITA_REGISTRADA_ENVIADO"
        else:
            categoria = resultado.get("categoria")
            cur.execute("""
                UPDATE RADAR_EVENTOS_CITAS
                SET correo_registro_error_en = NOW(),
                    correo_registro_error_motivo = %s
                WHERE id_radar = %s
                  AND correo_registro_enviado_en IS NULL
            """, ((resultado.get("motivo") or "No se pudo enviar el comprobante.")[:220], cita["id_radar"]))
            evento = (
                "CORREO_CITA_REGISTRADA_TOKEN_FALLIDO"
                if categoria == "oauth"
                else "CORREO_CITA_REGISTRADA_FALLIDO"
            )
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            evento,
            cita["correo_doctor"],
            _rol_actor_actual(),
            json.dumps({"id_radar": str(cita["id_radar"]), "ok": bool(resultado.get("ok"))}),
            request.remote_addr,
        ))
        conn.commit()
        return bool(resultado.get("ok"))
    except Exception:
        conn.rollback()
        return False


def _descripcion_google(datos, notas, tipo_evento):
    partes = [f"Creado desde Doko ({tipo_evento})."]
    if datos.get("telefono"):
        partes.append(f"Telefono: {datos['telefono']}")
    if datos.get("correo"):
        partes.append(f"Correo: {datos['correo']}")
    if notas:
        partes.append(f"Notas internas: {notas}")
    return "\n".join(partes)


def _fecha_google_a_tijuana(evento):
    inicio = evento.get("start") or {}
    valor = inicio.get("dateTime") or inicio.get("date")
    if not valor:
        return None
    if "T" not in valor:
        return datetime.strptime(valor, "%Y-%m-%d")
    fecha = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=TZ_TIJUANA)
    return fecha.astimezone(TZ_TIJUANA).replace(tzinfo=None)


def _datos_desde_google(evento, correo_doctor):
    summary = (evento.get("summary") or "").strip()
    description = (evento.get("description") or "").strip()
    correo, nombre = "", ""
    for attendee in evento.get("attendees") or []:
        email = (attendee.get("email") or "").strip()
        if email and email.lower() != correo_doctor.lower():
            correo = email
            nombre = (attendee.get("displayName") or "").strip()
            break
    if not correo:
        email_match = re.search(r'[\w.\-+%]+@[\w.\-]+\.[A-Za-z]{2,}', description)
        correo = email_match.group(0) if email_match else ""
    if not nombre:
        reserva_match = re.search(r'Reservada por[:\s]*([^<\n\r]+)', description, re.IGNORECASE)
        nombre = reserva_match.group(1).strip() if reserva_match else ""
    telefono_match = re.search(r'(?<!\d)(?:\+?52[\s.-]?)?(\d{3}[\s.-]?\d{3}[\s.-]?\d{4})(?!\d)', description)
    datos = {
        "nombre": nombre or summary or "Paciente",
        "correo": correo,
        "telefono": re.sub(r"\D", "", telefono_match.group(1)) if telefono_match else "",
        "origen": "google_calendar",
        "summary": summary,
        "description": description,
    }
    marcador = leer_marcador_doko(description)
    if marcador:
        datos["origen"] = marcador.get("origen") or "doko"
        datos["description"] = _limpiar_metadatos_doko(description)
        return datos
    texto = f"{summary}\n{description}".lower()
    texto = (texto
             .replace("?", "a").replace("?", "e").replace("?", "i")
             .replace("?", "o").replace("?", "u").replace("?", "u"))
    if re.search(r'\b(primera\s+vez|primera\s+visita|primera\s+consulta|1ra\s+vez|1\s*vez|nuevo\s+paciente|nueva\s+paciente)\b', texto):
        datos["tipo_visita"] = "Primera vez"
    elif re.search(r'\b(seguimiento|subsecuente|control|revision|revison|revicion)\b', texto):
        datos["tipo_visita"] = "Seguimiento"
    return datos


def _clasificar_google(evento, datos):
    marcador = leer_marcador_doko(evento.get("description") or "")
    if marcador and marcador.get("tipo_evento") in TIPOS_EVENTO:
        return marcador["tipo_evento"], marcador.get("origen") or "doko"
    if datos.get("correo") or datos.get("telefono"):
        return "CITA_PACIENTE", "google_calendar"
    return "EVENTO_INTERNO", "google_externo"


def _guardar_evento_google_en_radar(cur, correo_doctor, evento):
    google_event_id = evento.get("id")
    if not google_event_id or evento.get("status") == "cancelled":
        return
    fecha_cita = _fecha_google_a_tijuana(evento)
    if not fecha_cita:
        return
    datos = _datos_desde_google(evento, correo_doctor)
    tipo_evento, origen_evento = _clasificar_google(evento, datos)
    id_radar = str(uuid.uuid4())
    cur.execute("""
        INSERT INTO RADAR_EVENTOS_CITAS (
            id_radar, correo_doctor, google_event_id, fecha_cita, datos_paciente,
            estatus_confirmacion, segundo_aviso_enviado, fecha_registro,
            tipo_evento, origen_evento, estado_operativo
        )
        SELECT %s, %s, %s, %s, %s, 'Pendiente', FALSE, NOW(), %s, %s, 'activo'
        WHERE NOT EXISTS (
            SELECT 1 FROM RADAR_EVENTOS_CITAS
            WHERE correo_doctor = %s AND google_event_id = %s
        )
    """, (
        id_radar, correo_doctor, google_event_id, fecha_cita, json.dumps(datos),
        tipo_evento, origen_evento, correo_doctor, google_event_id,
    ))
    if cur.rowcount == 0:
        cur.execute("""
            UPDATE RADAR_EVENTOS_CITAS
            SET fecha_cita = %s,
                datos_paciente = COALESCE(datos_paciente, '{}'::jsonb) || %s::jsonb,
                tipo_evento = COALESCE(tipo_evento, %s),
                origen_evento = COALESCE(origen_evento, %s)
            WHERE correo_doctor = %s
              AND google_event_id = %s
              AND COALESCE(estado_operativo, 'activo') <> 'liberado'
        """, (fecha_cita, json.dumps(datos), tipo_evento, origen_evento, correo_doctor, google_event_id))


def _sincronizar_google_para_dia(cur, correo_doctor, inicio_agenda, fin_agenda):
    service = build("calendar", "v3", credentials=get_valid_token(correo_doctor), cache_discovery=False)
    respuesta = service.events().list(
        calendarId=correo_doctor,
        timeMin=inicio_agenda.replace(tzinfo=TZ_TIJUANA).astimezone(timezone.utc).isoformat(),
        timeMax=fin_agenda.replace(tzinfo=TZ_TIJUANA).astimezone(timezone.utc).isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    for evento in respuesta.get("items", []):
        _guardar_evento_google_en_radar(cur, correo_doctor, evento)


def _sincronizar_google_por_busqueda(cur, correo_doctor, inicio_agenda, fin_agenda, busqueda):
    service = build("calendar", "v3", credentials=get_valid_token(correo_doctor), cache_discovery=False)
    respuesta = service.events().list(
        calendarId=correo_doctor,
        timeMin=inicio_agenda.replace(tzinfo=TZ_TIJUANA).astimezone(timezone.utc).isoformat(),
        timeMax=fin_agenda.replace(tzinfo=TZ_TIJUANA).astimezone(timezone.utc).isoformat(),
        q=busqueda,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    for evento in respuesta.get("items", []):
        _guardar_evento_google_en_radar(cur, correo_doctor, evento)


def _validar_traslape(cur, correo_doctor, inicio, duracion_minutos, excluir_id_radar=None, solo_citas=False):
    fin = inicio + timedelta(minutes=duracion_minutos)
    cur.execute("""
        SELECT id_radar, fecha_cita, datos_paciente, tipo_evento
        FROM RADAR_EVENTOS_CITAS
        WHERE correo_doctor = %s
          AND COALESCE(estado_operativo, 'activo') = 'activo'
          AND UPPER(COALESCE(estatus_confirmacion, '')) NOT LIKE 'CANCEL%%'
          AND (%s IS NULL OR id_radar <> %s)
          AND (%s = FALSE OR COALESCE(tipo_evento, 'CITA_PACIENTE') = 'CITA_PACIENTE')
          AND fecha_cita < %s
          AND (
              fecha_cita + (
                  COALESCE(NULLIF(datos_paciente->>'duracion_minutos', '')::int, 30)
                  * INTERVAL '1 minute'
              )
          ) > %s
        LIMIT 1
    """, (correo_doctor, excluir_id_radar, excluir_id_radar, solo_citas, fin, inicio))
    ocupado = cur.fetchone()
    if ocupado:
        datos = ocupado.get("datos_paciente") or {}
        nombre = datos.get("nombre") or datos.get("summary") or "otro evento"
        fecha_ocupada = ocupado.get("fecha_cita")
        hora = fecha_ocupada.strftime("%I:%M %p").lstrip("0").replace("AM", "a. m.").replace("PM", "p. m.") if isinstance(fecha_ocupada, datetime) else "ese bloque"
        raise ValueError(f"Ese horario ya esta ocupado en Doko por {nombre} a las {hora}.")

# ==============================================================================
# 5.1 AGENDA Y PERFIL
# ==============================================================================

@panel_bp.route("/panel/agenda", methods=["GET"])
@requiere_jwt
def get_agenda():
    """Citas de los proximos 7 dias y conteo de estatus."""
    correo_doctor = request.correo_doctor
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        _asegurar_doctora_asignada_si_asistente(cur, correo_doctor)
        ahora = datetime.now(TZ_TIJUANA).replace(tzinfo=None)
        rango = (request.args.get("rango") or "semana").strip().lower()
        fecha_exacta = (request.args.get("fecha") or "").strip()
        busqueda = (request.args.get("buscar") or "").strip().lower()
        historial_canceladas = (request.args.get("historial_canceladas") or "").strip() == "1"
        modo_asistente = (request.args.get("modo_asistente") or "").strip() == "1"
        if modo_asistente and not _busqueda_asistente_habilitada(correo_doctor):
            return jsonify({"ok": False, "error": "La búsqueda guiada todavía no está habilitada para este consultorio."}), 403
        incluir_historial = modo_asistente and (request.args.get("incluir_historial") or "").strip() == "1"
        try:
            dia_mes = int(request.args.get("dia_mes") or 0) if modo_asistente else 0
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "El dia de busqueda no es valido."}), 400
        if dia_mes and not 1 <= dia_mes <= 31:
            return jsonify({"ok": False, "error": "El dia debe estar entre 1 y 31."}), 400

        inicio_hoy = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
        if modo_asistente and dia_mes and not busqueda and not fecha_exacta:
            fin_opciones = inicio_hoy + timedelta(days=367)
            cur.execute("""
                SELECT fecha_cita::date AS fecha, COUNT(*) AS total
                FROM RADAR_EVENTOS_CITAS
                WHERE correo_doctor = %s
                  AND fecha_cita >= %s
                  AND fecha_cita < %s
                  AND EXTRACT(DAY FROM fecha_cita) = %s
                  AND COALESCE(estado_operativo, 'activo') = 'activo'
                  AND UPPER(COALESCE(estatus_confirmacion, '')) NOT LIKE 'CANCEL%%'
                GROUP BY fecha_cita::date
                ORDER BY fecha_cita::date
            """, (correo_doctor, inicio_hoy, fin_opciones, dia_mes))
            opciones = [
                {"fecha": fila["fecha"].isoformat(), "total": int(fila["total"] or 0)}
                for fila in cur.fetchall()
            ]
            return jsonify({
                "citas": [],
                "totales": [],
                "alertas": [],
                "opciones_fecha": opciones,
                "resumen_busqueda": {
                    "total": sum(opcion["total"] for opcion in opciones),
                    "fechas": len(opciones),
                    "dia_mes": dia_mes,
                    "historial_disponible": 0,
                    "google_actualizado": None,
                },
                "rango": {
                    "inicio": inicio_hoy.isoformat(timespec="seconds"),
                    "fin": fin_opciones.isoformat(timespec="seconds"),
                    "dias": 367,
                    "rango": "busqueda",
                    "fecha": None,
                    "buscar": None,
                },
            })

        if historial_canceladas:
            inicio_agenda = inicio_hoy - timedelta(days=365)
            dias_rango = 732
            rango = "canceladas"
        elif busqueda and fecha_exacta:
            try:
                inicio_agenda = datetime.strptime(fecha_exacta, "%Y-%m-%d")
                dias_rango = 1
                rango = "busqueda"
            except ValueError:
                return jsonify({"ok": False, "error": "Fecha de agenda no válida."}), 400
        elif busqueda:
            if modo_asistente:
                inicio_agenda = inicio_hoy - (timedelta(days=365) if incluir_historial else timedelta(0))
                dias_rango = 732 if incluir_historial else 367
            else:
                inicio_agenda = inicio_hoy - timedelta(days=30)
                dias_rango = 210
            rango = "busqueda"
        elif fecha_exacta:
            try:
                inicio_agenda = datetime.strptime(fecha_exacta, "%Y-%m-%d")
                dias_rango = 1
                rango = "dia"
            except ValueError:
                return jsonify({"ok": False, "error": "Fecha de agenda no válida."}), 400
        else:
            dias_rango = {"dia": 1, "semana": 8, "mes": 31}.get(rango, 8)
            inicio_agenda = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
        fin_agenda = inicio_agenda + timedelta(days=dias_rango)
        alerta_sincronizacion = None
        if (fecha_exacta or busqueda) and not historial_canceladas:
            try:
                if busqueda:
                    _sincronizar_google_por_busqueda(cur, correo_doctor, inicio_agenda, fin_agenda, busqueda)
                else:
                    _sincronizar_google_para_dia(cur, correo_doctor, inicio_agenda, fin_agenda)
                conn.commit()
            except TokenNoEncontrado:
                conn.rollback()
                alerta_sincronizacion = {
                    "tipo": "GOOGLE_SIN_TOKEN",
                    "paciente": "Google Calendar",
                    "motivo": "No se pudo consultar Google Calendar porque esta doctora debe reconectar su cuenta."
                }
            except PermissionError as exc:
                conn.rollback()
                alerta_sincronizacion = {
                    "tipo": "GOOGLE_SIN_PERMISOS",
                    "paciente": "Google Calendar",
                    "motivo": str(exc)
                }
            except Exception as exc:
                conn.rollback()
                alerta_sincronizacion = {
                    "tipo": "GOOGLE_CONSULTA_FALLIDA",
                    "paciente": "Google Calendar",
                    "motivo": f"No se pudo actualizar la agenda de ese dia: {exc}"
                }
        
        filtro_busqueda = ""
        filtro_dia_mes = ""
        filtro_asistente = ""
        filtro_estado = ""
        params_citas = [correo_doctor, inicio_agenda, fin_agenda]
        if busqueda:
            patron_busqueda = f"%{busqueda}%"
            filtro_busqueda = """
              AND (
                  LOWER(COALESCE(r.datos_paciente->>'nombre', '')) LIKE %s
                  OR LOWER(COALESCE(r.datos_paciente->>'summary', '')) LIKE %s
                  OR LOWER(COALESCE(r.datos_paciente->>'telefono', '')) LIKE %s
                  OR LOWER(COALESCE(r.telefono_manual, '')) LIKE %s
                  OR LOWER(COALESCE(r.datos_paciente->>'correo', '')) LIKE %s
                  OR LOWER(COALESCE(r.correo_manual, '')) LIKE %s
              )
            """
            params_citas.extend([patron_busqueda] * 6)
        if modo_asistente and dia_mes:
            filtro_dia_mes = " AND EXTRACT(DAY FROM r.fecha_cita) = %s "
            params_citas.append(dia_mes)
        if modo_asistente:
            if not incluir_historial:
                filtro_asistente = """
                  AND COALESCE(r.estado_operativo, 'activo') = 'activo'
                  AND UPPER(COALESCE(r.estatus_confirmacion, '')) NOT LIKE 'CANCEL%%'
                """
            if busqueda:
                filtro_asistente += " AND COALESCE(r.tipo_evento, 'CITA_PACIENTE') = 'CITA_PACIENTE' "

        if historial_canceladas:
            filtro_estado = """
              AND COALESCE(r.tipo_evento, 'CITA_PACIENTE') = 'CITA_PACIENTE'
              AND (
                  UPPER(COALESCE(r.estatus_confirmacion, '')) LIKE 'CANCEL%%'
                  OR COALESCE(r.estado_operativo, 'activo') = 'cancelado'
              )
            """
        elif not modo_asistente:
            filtro_estado = """
              AND COALESCE(r.estado_operativo, 'activo') = 'activo'
              AND UPPER(COALESCE(r.estatus_confirmacion, '')) NOT LIKE 'CANCEL%%'
            """

        orden_asistente = "r.fecha_cita ASC"
        if modo_asistente and incluir_historial:
            orden_asistente = """
                CASE
                    WHEN r.fecha_cita >= CURRENT_DATE
                     AND COALESCE(r.estado_operativo, 'activo') = 'activo'
                     AND UPPER(COALESCE(r.estatus_confirmacion, '')) NOT LIKE 'CANCEL%%'
                    THEN 0 ELSE 1
                END,
                CASE WHEN r.fecha_cita >= CURRENT_DATE THEN r.fecha_cita END ASC,
                r.fecha_cita DESC
            """
        elif historial_canceladas:
            orden_asistente = "r.fecha_cita DESC"
        limite_asistente = " LIMIT 100 " if historial_canceladas else (" LIMIT 25 " if modo_asistente and busqueda else "")

        cur.execute(f"""
            SELECT r.id_radar, r.fecha_cita, r.datos_paciente, r.estatus_confirmacion, r.motivo_cancelacion,
                   r.tipo_evento, r.origen_evento, r.notas_internas, r.telefono_manual, r.correo_manual,
                   r.servicio_id, s.nombre_servicio AS servicio_nombre,
                   r.expiracion_apartado, r.estado_operativo
            FROM RADAR_EVENTOS_CITAS r
            LEFT JOIN CAT_SERVICIOS_CONSULTORIO s
              ON s.id_servicio = r.servicio_id
             AND s.correo_doctor = r.correo_doctor
            WHERE r.correo_doctor = %s
              AND r.fecha_cita >= %s
              AND r.fecha_cita < %s
              AND (
                  COALESCE(r.estado_operativo, 'activo') = 'activo'
                  OR COALESCE(r.tipo_evento, 'CITA_PACIENTE') = 'CITA_PACIENTE'
              )
              {filtro_busqueda}
              {filtro_dia_mes}
              {filtro_asistente}
              {filtro_estado}
            ORDER BY {orden_asistente}
            {limite_asistente}
        """, tuple(params_citas))
        citas = cur.fetchall()
        for cita in citas:
            fecha_cita = cita.get("fecha_cita")
            if isinstance(fecha_cita, datetime):
                cita["fecha_cita"] = fecha_cita.replace(tzinfo=None).isoformat(timespec="seconds")

        totales = []
        if not historial_canceladas:
            params_totales = [correo_doctor, inicio_agenda, fin_agenda]
            if busqueda:
                params_totales.extend([patron_busqueda] * 6)
            if modo_asistente and dia_mes:
                params_totales.append(dia_mes)
            cur.execute(f"""
                SELECT r.estatus_confirmacion, COUNT(*) as total
                FROM RADAR_EVENTOS_CITAS r
                WHERE r.correo_doctor = %s
                  AND r.fecha_cita >= %s
                  AND r.fecha_cita < %s
                  AND COALESCE(r.tipo_evento, 'CITA_PACIENTE') = 'CITA_PACIENTE'
                  AND COALESCE(r.estado_operativo, 'activo') = 'activo'
                  {filtro_busqueda}
                  {filtro_dia_mes}
                  {filtro_asistente}
                  {filtro_estado}
                GROUP BY r.estatus_confirmacion
            """, tuple(params_totales))
            totales = cur.fetchall()

        historial_disponible = 0
        if modo_asistente and busqueda and not incluir_historial:
            inicio_historial = inicio_hoy - timedelta(days=365)
            fin_historial = inicio_hoy + timedelta(days=367)
            params_historial = [correo_doctor, inicio_historial, fin_historial]
            params_historial.extend([patron_busqueda] * 6)
            if dia_mes:
                params_historial.append(dia_mes)
            cur.execute(f"""
                SELECT COUNT(*) AS total
                FROM RADAR_EVENTOS_CITAS r
                WHERE r.correo_doctor = %s
                  AND r.fecha_cita >= %s
                  AND r.fecha_cita < %s
                  AND COALESCE(r.tipo_evento, 'CITA_PACIENTE') = 'CITA_PACIENTE'
                  AND COALESCE(r.estado_operativo, 'activo') <> 'liberado'
                  {filtro_busqueda}
                  {filtro_dia_mes}
                  AND (
                      r.fecha_cita < CURRENT_DATE
                      OR UPPER(COALESCE(r.estatus_confirmacion, '')) LIKE 'CANCEL%%'
                      OR COALESCE(r.estado_operativo, 'activo') <> 'activo'
                  )
            """, tuple(params_historial))
            historial_disponible = int((cur.fetchone() or {}).get("total") or 0)

        cur.execute("""
            SELECT tipo_evento, detalle, fecha_evento
            FROM AUDITORIA_SEGURIDAD
            WHERE actor = %s
              AND tipo_evento IN ('CONFIRMACION_ENVIO_FALLIDO',
                                  'CONFIRMACION_TOKEN_GOOGLE_FALLIDO',
                                  'CORREO_CITA_REGISTRADA_TOKEN_FALLIDO',
                                  'CORREO_CITA_REGISTRADA_FALLIDO', 'CITA_ULTIMO_MINUTO',
                                  'CANCELACION_GOOGLE_FALLIDA', 'CANCELACION_GOOGLE_AUTORIZACION_FALLIDA',
                                  'EVENTO_GOOGLE_EXTERNO_SIN_CLASIFICAR', 'APARTADO_POR_VENCER')
              AND fecha_evento >= NOW() - INTERVAL '24 hours'
            ORDER BY fecha_evento DESC LIMIT 4
        """, (correo_doctor,))
        alertas = []
        if alerta_sincronizacion:
            alertas.append(alerta_sincronizacion)
        for evento in cur.fetchall():
            detalle = evento.get('detalle') if isinstance(evento.get('detalle'), dict) else {}
            alertas.append({'tipo': evento['tipo_evento'], 'paciente': detalle.get('paciente') or 'Paciente',
                            'fecha_cita': detalle.get('fecha_cita'),
                            'motivo': detalle.get('motivo') or 'Contacta directamente al paciente.'})

        citas_paciente = [
            cita for cita in citas
            if str(cita.get("tipo_evento") or "CITA_PACIENTE").upper() == "CITA_PACIENTE"
        ]
        resumen_busqueda = None
        if modo_asistente:
            resumen_busqueda = {
                "total": len(citas),
                "citas_paciente": len(citas_paciente),
                "confirmadas": sum(
                    1 for cita in citas_paciente
                    if any(valor in str(cita.get("estatus_confirmacion") or "").upper() for valor in ("CONFIRM", "VERIFIC"))
                ),
                "pendientes": sum(
                    1 for cita in citas_paciente
                    if "PEND" in str(cita.get("estatus_confirmacion") or "").upper()
                ),
                "eventos_internos": len(citas) - len(citas_paciente),
                "historial_disponible": historial_disponible,
                "google_actualizado": alerta_sincronizacion is None,
                "resultados_limitados": bool(busqueda and len(citas) >= 25),
            }

        return jsonify({
            "citas": citas,
            "totales": totales,
            "alertas": alertas,
            "opciones_fecha": [],
            "resumen_busqueda": resumen_busqueda,
            "rango": {
                "inicio": inicio_agenda.isoformat(timespec="seconds"),
                "fin": fin_agenda.isoformat(timespec="seconds"),
                "dias": dias_rango,
                "rango": rango if rango in {"dia", "semana", "mes", "busqueda", "canceladas"} else "semana",
                "fecha": fecha_exacta or None,
                "buscar": busqueda or None,
            },
        })
    except PermissionError as exc:
        return jsonify({"ok": False, "error": _mensaje_error_operativo(exc)}), 403
    finally:
        conn.close()


@panel_bp.route("/panel/asistente", methods=["POST"])
@requiere_jwt
def consultar_asistente_panel():
    """Orienta sobre Doko sin ejecutar acciones ni exponer datos del paciente."""
    inicio_consulta = time.monotonic()
    correo_doctor = request.correo_doctor
    data = request.get_json(silent=True) or {}
    pregunta = str(data.get("pregunta") or "").strip()[:300]
    id_radar = str(data.get("id_radar") or "").strip()
    contexto_interfaz = str(data.get("contexto_interfaz") or "modulo_asistente").strip().lower()
    if contexto_interfaz not in {"modulo_asistente", "editar_cita", "crear_evento", "cita_seleccionada"}:
        contexto_interfaz = "modulo_asistente"
    if not pregunta:
        return jsonify({"ok": False, "error": "Escribe una pregunta sobre el uso de Doko."}), 400

    if id_radar:
        try:
            id_radar = str(uuid.UUID(id_radar))
        except (ValueError, TypeError, AttributeError):
            return jsonify({"ok": False, "error": "La referencia de la cita no es válida."}), 400

    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        _asegurar_doctora_asignada_si_asistente(cur, correo_doctor)
        cur.execute("""
            SELECT modo_confirmacion, confirmacion_dias_habiles
            FROM DOCTORES
            WHERE correo_doctor = %s AND activo = TRUE
        """, (correo_doctor,))
        doctor = cur.fetchone() or {}
        if not doctor:
            return jsonify({"ok": False, "error": "Doctora no disponible."}), 403
        modo_confirmacion = doctor.get("modo_confirmacion") or "manual"
        confirmacion_dias_habiles = bool(doctor.get("confirmacion_dias_habiles"))

        evento = None
        if id_radar:
            cur.execute("""
                SELECT r.id_radar, r.fecha_cita, r.tipo_evento, r.estatus_confirmacion,
                       r.estado_operativo, r.requiere_confirmacion_enlace,
                       r.correo_registro_enviado_en, r.correo_registro_error_en,
                       r.correo_registro_error_motivo,
                       r.confirmacion_enviada_en, r.confirmacion_error_en,
                       r.confirmacion_error_motivo, r.token_expiracion,
                       r.segundo_aviso_enviado, r.expiracion_apartado,
                       r.liberado_en, r.cancelacion_automatica_en,
                       r.motivo_cancelacion, r.origen_evento,
                       (COALESCE(r.datos_paciente->>'description', '') ~* 'Reservada[[:space:]]+por')
                           AS es_reserva_google,
                       (NULLIF(TRIM(COALESCE(r.correo_manual, r.datos_paciente->>'correo', '')), '') IS NOT NULL)
                           AS tiene_correo,
                       (NULLIF(TRIM(COALESCE(r.telefono_manual, r.datos_paciente->>'telefono', '')), '') IS NOT NULL)
                           AS tiene_telefono
                FROM RADAR_EVENTOS_CITAS r
                WHERE r.id_radar = %s AND r.correo_doctor = %s
                LIMIT 1
            """, (id_radar, correo_doctor))
            evento = cur.fetchone()
            if not evento:
                return jsonify({"ok": False, "error": "No se encontró esa cita para la doctora activa."}), 404
            evento["confirmacion_dias_habiles"] = confirmacion_dias_habiles

        actor_rol = getattr(request, "jwt_actor_rol", "doctor")
        actor = hash_actor(
            correo_doctor,
            actor_rol,
            getattr(request, "jwt_id_usuario", None),
        )
        contexto_habilitado = contexto_habilitado_para_doctor(
            correo_doctor,
            config_bunker.PANEL_ASSISTANT_CONTEXT_DEMO_EMAIL,
        )
        contexto_valido = None
        actor_context_hash = None
        doctor_context_hash = None
        id_radar_context_hash = None
        if contexto_habilitado:
            actor_context_hash = huella_contextual(actor, config_bunker.SECRET_KEY)
            doctor_context_hash = huella_contextual(correo_doctor, config_bunker.SECRET_KEY)
            id_radar_context_hash = huella_contextual(id_radar, config_bunker.SECRET_KEY)
            contexto_valido = validar_contexto(
                session.get(CONTEXT_KEY),
                actor_hash=actor_context_hash or "",
                doctor_hash=doctor_context_hash or "",
                id_radar_hash=id_radar_context_hash,
                evento_vigente=bool(evento) if id_radar else True,
            )
            if session.get(CONTEXT_KEY) and not contexto_valido:
                session.pop(CONTEXT_KEY, None)
        busqueda_habilitada = _busqueda_asistente_habilitada(correo_doctor)
        categoria = clasificar_local(
            pregunta,
            continuidad_edicion=contexto_habilitado,
        )
        accion_busqueda = interpretar_busqueda_agenda(pregunta) if busqueda_habilitada else None
        if accion_busqueda:
            if contexto_habilitado:
                session.pop(CONTEXT_KEY, None)
            duracion_ms = int((time.monotonic() - inicio_consulta) * 1000)
            registrar_regla(correo_doctor, actor, actor_rol, "buscar_agenda", duracion_ms)
            if accion_busqueda.get("tipo") == "aclarar_busqueda":
                return jsonify({
                    "ok": True,
                    "respuesta": accion_busqueda.get("mensaje"),
                    "explicacion": {"respuesta": accion_busqueda.get("mensaje")},
                    "categoria": "buscar_agenda",
                    "fuente": "reglas",
                    "contexto_cita": bool(evento),
                    "accion_ui": None,
                    "uso_ia": {"gemini": False},
                })
            if accion_busqueda.get("fecha"):
                respuesta_busqueda = "Voy a consultar esa fecha y mostrar los resultados en la agenda."
            elif accion_busqueda.get("dia_mes") and accion_busqueda.get("buscar"):
                respuesta_busqueda = "Voy a buscar las coincidencias de esa persona en los proximos dias indicados."
            elif accion_busqueda.get("dia_mes"):
                respuesta_busqueda = "Voy a revisar los proximos meses que tienen eventos en ese dia."
            else:
                respuesta_busqueda = "Voy a buscar las proximas citas y mostrar las coincidencias en la agenda."
            return jsonify({
                "ok": True,
                "respuesta": respuesta_busqueda,
                "explicacion": {"respuesta": respuesta_busqueda},
                "categoria": "buscar_agenda",
                "fuente": "reglas",
                "contexto_cita": bool(evento),
                "accion_ui": accion_busqueda,
                "uso_ia": {"gemini": False},
            })
        fuente = "reglas"
        uso_ia = {"gemini": False}
        categoria, contexto_usado, contexto_consumido = resolver_continuidad(
            habilitado=contexto_habilitado,
            pregunta=pregunta,
            categoria_actual=categoria,
            contexto_valido=contexto_valido,
        )
        if contexto_habilitado:
            if contexto_usado and contexto_consumido:
                session[CONTEXT_KEY] = contexto_consumido
            elif contexto_usado:
                session.pop(CONTEXT_KEY, None)
            elif contexto_valido:
                session.pop(CONTEXT_KEY, None)
        if contexto_usado:
            fuente = "contexto_reglas"

        if not categoria:
            paquete = construir_paquete_intencion(pregunta, contexto_interfaz)
            if paquete_tiene_contexto(paquete):
                reserva = reservar_gemini(correo_doctor, actor, actor_rol)
                uso_ia["cuota_restante_consultorio"] = reserva.restante_consultorio
                if reserva.permitida and reserva.id_uso:
                    inicio_gemini = time.monotonic()
                    try:
                        categoria, resultado_gemini = clasificar_con_gemini(paquete)
                        finalizar_gemini(
                            reserva.id_uso,
                            categoria=categoria,
                            resultado=resultado_gemini,
                            duracion_ms=int((time.monotonic() - inicio_gemini) * 1000),
                        )
                        fuente = "gemini_intent"
                        uso_ia["gemini"] = True
                    except Exception:
                        finalizar_gemini(
                            reserva.id_uso,
                            categoria="fuera_alcance",
                            duracion_ms=int((time.monotonic() - inicio_gemini) * 1000),
                            error=True,
                        )
                        categoria = "fuera_alcance"
                        fuente = "gemini_error"
                else:
                    categoria = "fuera_alcance"
                    fuente = "limite"
            else:
                categoria = "fuera_alcance"

        if contexto_habilitado and not contexto_usado:
            contexto_nuevo = crear_contexto(
                actor_hash=actor_context_hash or "",
                doctor_hash=doctor_context_hash or "",
                categoria=categoria,
                origen=fuente,
                id_radar_hash=id_radar_context_hash,
            )
            if contexto_nuevo:
                session[CONTEXT_KEY] = contexto_nuevo
            else:
                session.pop(CONTEXT_KEY, None)

        explicacion = explicacion_operativa(
            categoria,
            modo_confirmacion,
            evento,
            contexto_interfaz=contexto_interfaz,
            confirmacion_dias_habiles=confirmacion_dias_habiles,
            continuidad_edicion=contexto_habilitado,
        )
        respuesta = respuesta_desde_explicacion(explicacion)
        if fuente in {"reglas", "contexto_reglas"}:
            registrar_regla(
                correo_doctor,
                actor,
                actor_rol,
                categoria,
                int((time.monotonic() - inicio_consulta) * 1000),
            )
        flujo = describir_flujo_correo(evento, modo_confirmacion) if evento and categoria in {"correo", "confirmacion"} else None
        return jsonify({
            "ok": True,
            "respuesta": respuesta,
            "explicacion": explicacion,
            "categoria": categoria,
            "fuente": fuente,
            "contexto_cita": bool(evento),
            "contexto_interfaz": contexto_interfaz,
            "flujo_correo": flujo,
            "uso_ia": uso_ia,
        })
    except PermissionError as exc:
        return jsonify({"ok": False, "error": _mensaje_error_operativo(exc)}), 403
    except Exception as exc:
        return jsonify({"ok": False, "error": _mensaje_error_operativo(exc)}), 400
    finally:
        conn.close()

@panel_bp.route("/panel/agenda/<id_radar>/confirmar", methods=["POST"])
@requiere_jwt
def confirmar_cita_manual(id_radar):
    """Marca una cita como confirmada desde el panel del doctor, sin tocar Google Calendar."""
    correo_doctor = request.correo_doctor
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        _asegurar_doctora_asignada_si_asistente(cur, correo_doctor)
        cur.execute("""
            UPDATE RADAR_EVENTOS_CITAS
            SET estatus_confirmacion = 'CONFIRMADO',
                token_confirmacion = NULL,
                token_expiracion = NULL
            WHERE id_radar = %s
              AND correo_doctor = %s
              AND COALESCE(tipo_evento, 'CITA_PACIENTE') = 'CITA_PACIENTE'
              AND COALESCE(estado_operativo, 'activo') = 'activo'
              AND UPPER(COALESCE(estatus_confirmacion, 'Pendiente')) LIKE 'PEND%%'
            RETURNING id_radar, estatus_confirmacion, correo_doctor, google_event_id, datos_paciente, fecha_cita
        """, (id_radar, correo_doctor))
        cita = cur.fetchone()

        if not cita:
            conn.rollback()
            return jsonify({"ok": False, "error": "La cita no est\u00e1 pendiente o no est\u00e1 disponible para confirmar"}), 404

        cur.execute("""
            SELECT nombre_doctor, especialidad, telefono_consultorio,
                   direccion_consultorio, maps_url
            FROM DOCTORES
            WHERE correo_doctor = %s
        """, (correo_doctor,))
        doctor = cur.fetchone()

        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            "CONFIRMACION_MANUAL_CITA",
            correo_doctor,
            "doctor",
            json.dumps({"id_radar": str(id_radar)}),
            request.remote_addr,
        ))

        calendario_actualizado = False
        try:
            calendario_actualizado = marcar_evento_confirmado_doko(correo_doctor, cita.get("google_event_id"))
        except Exception as exc:
            texto_error = str(exc).lower()
            evento_error = (
                "CONFIRMACION_TOKEN_GOOGLE_FALLIDO"
                if isinstance(exc, TokenNoEncontrado)
                or "invalid_grant" in texto_error
                or "expired or revoked" in texto_error
                or "debe reconectarse" in texto_error
                else "CALENDAR_CONFIRMADA_FALLIDA"
            )
            cur.execute("""
                INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                evento_error,
                correo_doctor,
                "sistema",
                json.dumps({"id_radar": str(id_radar), "error": str(exc)[:220]}),
                request.remote_addr,
            ))

        conn.commit()
        correo_enviado = enviar_correo_cita_confirmada(cita, doctor)
        return jsonify({"ok": True, "id_radar": str(cita["id_radar"]), "estatus_confirmacion": cita["estatus_confirmacion"], "correo_confirmacion_enviado": correo_enviado, "calendar_confirmada": calendario_actualizado})
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": _mensaje_error_operativo(e)}), 400
    finally:
        conn.close()


@panel_bp.route("/panel/agenda/cita", methods=["POST"])
@requiere_jwt
def crear_cita_manual():
    return _crear_evento_operativo("CITA_PACIENTE")


@panel_bp.route("/panel/agenda/bloqueo", methods=["POST"])
@requiere_jwt
def crear_bloqueo_horario():
    return _crear_evento_operativo("BLOQUEO_HORARIO")


@panel_bp.route("/panel/agenda/apartado", methods=["POST"])
@requiere_jwt
def crear_apartado_temporal():
    return _crear_evento_operativo("APARTADO_TEMPORAL")


def _crear_evento_operativo(tipo_evento):
    correo_doctor = request.correo_doctor
    data = request.get_json(silent=True) or {}
    conn = get_connection()
    google_event_id = None
    try:
        tipo_evento = _normalizar_tipo(tipo_evento)
        inicio = _parse_inicio(data)
        duracion_minutos = _duracion(data)
        datos = _datos_evento(data, tipo_evento, duracion_minutos)
        notas = _limpiar_metadatos_doko(data.get("notas_internas") or data.get("notas") or "")
        servicio_id = (data.get("servicio_id") or "").strip() or None
        expiracion = None
        if tipo_evento == "APARTADO_TEMPORAL" and data.get("expiracion_apartado"):
            expiracion = _parse_inicio({"inicio": data.get("expiracion_apartado")})
        confirmar = bool(data.get("confirmado")) and tipo_evento == "CITA_PACIENTE"
        id_radar = str(uuid.uuid4())

        cur = conn.cursor(cursor_factory=RealDictCursor)
        _asegurar_doctora_asignada_si_asistente(cur, correo_doctor)
        cur.execute("""
            SELECT nombre_doctor, especialidad, telefono_consultorio,
                   direccion_consultorio, maps_url, modo_confirmacion,
                   confirmacion_dias_habiles
            FROM DOCTORES
            WHERE correo_doctor = %s AND activo = TRUE
        """, (correo_doctor,))
        doctor = cur.fetchone()
        if not doctor:
            return jsonify({"ok": False, "error": "Doctora no disponible"}), 403
        if servicio_id:
            cur.execute(
                "SELECT id_servicio FROM CAT_SERVICIOS_CONSULTORIO WHERE id_servicio = %s AND correo_doctor = %s AND activo = TRUE",
                (servicio_id, correo_doctor),
            )
            if not cur.fetchone():
                return jsonify({"ok": False, "error": "Servicio no disponible para esta doctora"}), 400

        _validar_traslape(cur, correo_doctor, inicio, duracion_minutos)

        titulo = datos["nombre"]
        if tipo_evento == "BLOQUEO_HORARIO":
            titulo = f"Bloqueo - {datos['nombre']}"
        elif tipo_evento == "APARTADO_TEMPORAL":
            titulo = f"Apartado - {datos['nombre']}"
        elif tipo_evento == "EVENTO_INTERNO":
            titulo = f"Interno - {datos['nombre']}"
        if confirmar and tipo_evento == "CITA_PACIENTE" and not titulo.lower().startswith("confirmada"):
            titulo = f"Confirmada - {titulo}"

        evento_google = crear_evento_doko(
            correo_doctor=correo_doctor,
            id_radar=id_radar,
            tipo_evento=tipo_evento,
            titulo=titulo,
            inicio=inicio,
            duracion_minutos=duracion_minutos,
            descripcion=_descripcion_google(datos, notas, tipo_evento),
            paciente_correo=datos.get("correo") if tipo_evento == "CITA_PACIENTE" else None,
        )
        google_event_id = evento_google.get("id")
        if not google_event_id:
            return jsonify({"ok": False, "error": "Google Calendar no devolvió id de evento"}), 502

        estatus = _estatus_inicial(tipo_evento, confirmado=confirmar)
        enviar_comprobante = _es_cita_cercana_con_comprobante(tipo_evento, inicio, datos)
        cur.execute("""
            INSERT INTO RADAR_EVENTOS_CITAS (
                id_radar, correo_doctor, google_event_id, fecha_cita, datos_paciente,
                estatus_confirmacion, segundo_aviso_enviado, fecha_registro,
                tipo_evento, origen_evento, creado_por_usuario_id, notas_internas,
                telefono_manual, correo_manual, servicio_id, expiracion_apartado, estado_operativo,
                requiere_confirmacion_enlace
            )
            VALUES (%s, %s, %s, %s, %s, %s, FALSE, NOW(),
                    %s, %s, %s, %s, %s, %s, %s, %s, 'activo', %s)
        """, (
            id_radar, correo_doctor, google_event_id, inicio, json.dumps(datos), estatus,
            tipo_evento, "doko_asistente" if _rol_actor_actual() == "asistente" else "doko",
            _usuario_interno_actual(), notas, datos.get("telefono") or None,
            datos.get("correo") or None, servicio_id, expiracion, not enviar_comprobante,
        ))

        auditoria = {
            "id_radar": id_radar,
            "tipo_evento": tipo_evento,
            "google_event_id": google_event_id,
            "fecha_cita": str(inicio),
        }
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
            VALUES (%s, %s, %s, %s, %s)
        """, ("AGENDA_EVENTO_CREADO", correo_doctor, _rol_actor_actual(), json.dumps(auditoria), request.remote_addr))
        conn.commit()
        correo_registro_enviado = False
        if enviar_comprobante:
            correo_registro_enviado = _enviar_y_registrar_comprobante(conn, cur, {
                "id_radar": id_radar,
                "correo_doctor": correo_doctor,
                "correo_manual": datos.get("correo"),
                "datos_paciente": datos,
                "fecha_cita": inicio,
            }, doctor)
        flujo_correo = metadatos_flujo_guardado(
            tipo_evento=tipo_evento,
            fecha_cita=inicio,
            correo=datos.get("correo") or "",
            confirmado=confirmar,
            modo_confirmacion=doctor.get("modo_confirmacion") or "manual",
            confirmacion_dias_habiles=bool(doctor.get("confirmacion_dias_habiles")),
            intento_inmediato=enviar_comprobante,
            enviado=correo_registro_enviado,
        )
        return jsonify({
            "ok": True,
            "id_radar": id_radar,
            "google_event_id": google_event_id,
            "tipo_evento": tipo_evento,
            "correo_registro_enviado": correo_registro_enviado,
            "flujo_correo": flujo_correo,
        })
    except Exception as exc:
        conn.rollback()
        if google_event_id:
            try:
                borrar_evento_doko(correo_doctor, google_event_id)
            except Exception:
                pass
        return jsonify({"ok": False, "error": _mensaje_error_operativo(exc)}), 400
    finally:
        conn.close()


@panel_bp.route("/panel/agenda/<id_radar>/liberar", methods=["POST"])
@requiere_jwt
def liberar_evento_agenda(id_radar):
    correo_doctor = request.correo_doctor
    data = request.get_json(silent=True) or {}
    motivo = (data.get("motivo_liberacion") or data.get("motivo") or "Liberado desde Doko").strip()
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        _asegurar_doctora_asignada_si_asistente(cur, correo_doctor)
        cur.execute("""
            SELECT id_radar, google_event_id, tipo_evento, estado_operativo, estatus_confirmacion
            FROM RADAR_EVENTOS_CITAS
            WHERE id_radar = %s AND correo_doctor = %s
            FOR UPDATE
        """, (id_radar, correo_doctor))
        evento = cur.fetchone()
        if not evento:
            return jsonify({"ok": False, "error": "Evento no encontrado para esta doctora"}), 404
        if evento.get("estado_operativo") == "liberado":
            conn.rollback()
            return jsonify({"ok": True, "mensaje": "El horario ya estaba liberado"})
        tipo_evento = str(evento.get("tipo_evento") or "CITA_PACIENTE").upper()
        estatus = str(evento.get("estatus_confirmacion") or "Pendiente").upper()
        if tipo_evento == "CITA_PACIENTE" and ("CONFIRM" in estatus or "VERIFIC" in estatus):
            conn.rollback()
            return jsonify({
                "ok": False,
                "error": "Una cita confirmada no puede liberarse. Usa el flujo de cancelación del consultorio.",
            }), 409

        borrar_evento_doko(correo_doctor, evento.get("google_event_id"))
        cur.execute("""
            UPDATE RADAR_EVENTOS_CITAS
            SET estado_operativo = 'liberado',
                liberado_en = NOW(),
                motivo_liberacion = %s,
                estatus_confirmacion = CASE
                    WHEN COALESCE(tipo_evento, 'CITA_PACIENTE') = 'CITA_PACIENTE' THEN 'CANCELADO'
                    ELSE estatus_confirmacion
                END,
                token_confirmacion = NULL,
                token_expiracion = NULL
            WHERE id_radar = %s AND correo_doctor = %s
        """, (motivo, id_radar, correo_doctor))
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
            VALUES (%s, %s, %s, %s, %s)
        """, ("AGENDA_EVENTO_LIBERADO", correo_doctor, _rol_actor_actual(),
              json.dumps({"id_radar": str(id_radar), "motivo": motivo, "tipo_evento": evento.get("tipo_evento")}),
              request.remote_addr))
        conn.commit()
        return jsonify({"ok": True})
    except Exception as exc:
        conn.rollback()
        return jsonify({"ok": False, "error": _mensaje_error_operativo(exc)}), 400
    finally:
        conn.close()


@panel_bp.route("/panel/agenda/<id_radar>/cancelar", methods=["POST"])
@requiere_jwt
def cancelar_cita_agenda(id_radar):
    """Cancela una cita de paciente y retira su evento sincronizado."""
    correo_doctor = request.correo_doctor
    data = request.get_json(silent=True) or {}
    motivo = (
        data.get("motivo_cancelacion")
        or data.get("motivo")
        or "Cancelada manualmente desde Doko"
    ).strip()[:240]
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        _asegurar_doctora_asignada_si_asistente(cur, correo_doctor)
        cur.execute("""
            SELECT id_radar, google_event_id, tipo_evento, origen_evento,
                   estado_operativo, estatus_confirmacion
            FROM RADAR_EVENTOS_CITAS
            WHERE id_radar = %s AND correo_doctor = %s
            FOR UPDATE
        """, (id_radar, correo_doctor))
        evento = cur.fetchone()
        if not evento:
            conn.rollback()
            return jsonify({"ok": False, "error": "Cita no encontrada para esta doctora"}), 404

        tipo_evento = str(evento.get("tipo_evento") or "CITA_PACIENTE").upper()
        origen_evento = str(evento.get("origen_evento") or "").lower()
        if tipo_evento != "CITA_PACIENTE":
            conn.rollback()
            return jsonify({
                "ok": False,
                "error": "Solo las citas de paciente se cancelan aquí. Para un bloqueo o apartado usa Liberar.",
            }), 409
        if origen_evento == "google_externo":
            conn.rollback()
            return jsonify({
                "ok": False,
                "error": "Este evento externo solo puede gestionarse desde Google Calendar.",
            }), 409

        estado_operativo = str(evento.get("estado_operativo") or "activo").lower()
        estatus = str(evento.get("estatus_confirmacion") or "").upper()
        if estado_operativo == "cancelado" or "CANCEL" in estatus:
            conn.rollback()
            return jsonify({
                "ok": True,
                "ya_cancelada": True,
                "estado_operativo": "cancelado",
                "estatus_confirmacion": "CANCELADO",
            })
        if estado_operativo != "activo":
            conn.rollback()
            return jsonify({"ok": False, "error": "Esta cita ya no está activa."}), 409

        google_event_id = evento.get("google_event_id")
        if google_event_id:
            borrar_evento_doko(correo_doctor, google_event_id)
        cur.execute("""
            UPDATE RADAR_EVENTOS_CITAS
            SET estado_operativo = 'cancelado',
                estatus_confirmacion = 'CANCELADO',
                motivo_cancelacion = %s,
                token_confirmacion = NULL,
                token_expiracion = NULL
            WHERE id_radar = %s
              AND correo_doctor = %s
              AND COALESCE(estado_operativo, 'activo') = 'activo'
        """, (motivo, id_radar, correo_doctor))
        if cur.rowcount != 1:
            conn.rollback()
            return jsonify({"ok": False, "error": "La cita cambió mientras se cancelaba. Vuelve a cargar la agenda."}), 409

        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            "AGENDA_CITA_CANCELADA",
            correo_doctor,
            _rol_actor_actual(),
            json.dumps({
                "id_radar": str(id_radar),
                "tipo_evento": evento.get("tipo_evento"),
                "origen_evento": evento.get("origen_evento"),
                "estatus_anterior": evento.get("estatus_confirmacion"),
                "motivo": motivo,
            }),
            request.remote_addr,
        ))
        conn.commit()
        return jsonify({
            "ok": True,
            "estado_operativo": "cancelado",
            "estatus_confirmacion": "CANCELADO",
        })
    except PermissionError as exc:
        conn.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 403
    except Exception as exc:
        conn.rollback()
        return jsonify({"ok": False, "error": _mensaje_error_operativo(exc)}), 400
    finally:
        conn.close()


def _titulo_evento_agenda(tipo_evento, datos, estatus=None):
    nombre = datos.get("nombre") or "Paciente"
    if tipo_evento == "BLOQUEO_HORARIO":
        return f"Bloqueo - {nombre}"
    if tipo_evento == "APARTADO_TEMPORAL":
        return f"Apartado - {nombre}"
    if tipo_evento == "EVENTO_INTERNO":
        return nombre
    if str(estatus or "").upper().startswith("CONFIRM") and not nombre.lower().startswith("confirmada"):
        return f"Confirmada - {nombre}"
    return nombre


@panel_bp.route("/panel/agenda/<id_radar>", methods=["PATCH"])
@requiere_jwt
def editar_evento_agenda(id_radar):
    correo_doctor = request.correo_doctor
    data = request.get_json(silent=True) or {}
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        _asegurar_doctora_asignada_si_asistente(cur, correo_doctor)
        cur.execute("""
            SELECT id_radar, google_event_id, fecha_cita, datos_paciente, estatus_confirmacion,
                   tipo_evento, estado_operativo, correo_registro_enviado_en,
                   confirmacion_enviada_en, requiere_confirmacion_enlace
            FROM RADAR_EVENTOS_CITAS
            WHERE id_radar = %s AND correo_doctor = %s
            FOR UPDATE
        """, (id_radar, correo_doctor))
        evento = cur.fetchone()
        if not evento:
            return jsonify({"ok": False, "error": "Evento no encontrado para esta doctora"}), 404
        cur.execute("""
            SELECT modo_confirmacion, confirmacion_dias_habiles
            FROM DOCTORES
            WHERE correo_doctor = %s
        """, (correo_doctor,))
        configuracion_doctor = cur.fetchone() or {}
        if evento.get("estado_operativo") != "activo":
            return jsonify({"ok": False, "error": "Solo se pueden editar eventos activos"}), 400
        if str(evento.get("estatus_confirmacion") or "").upper().startswith("CANCEL"):
            return jsonify({"ok": False, "error": "No se puede editar una cita cancelada"}), 400

        tipo_solicitado = _normalizar_tipo(
            data.get("tipo_evento") or evento.get("tipo_evento") or "CITA_PACIENTE"
        )
        inicio = _parse_inicio(data)
        duracion_minutos = _duracion(data)
        datos = _datos_evento(data, tipo_solicitado, duracion_minutos)
        nombre_capturado = (data.get("nombre_paciente") or data.get("paciente") or "").strip()
        convertido_automaticamente = (
            evento.get("tipo_evento") == "EVENTO_INTERNO"
            and tipo_solicitado == "EVENTO_INTERNO"
            and bool(nombre_capturado)
            and bool((datos.get("correo") or "").strip() or (datos.get("telefono") or "").strip())
        )
        tipo_evento = "CITA_PACIENTE" if convertido_automaticamente else tipo_solicitado
        notas = _limpiar_metadatos_doko(data.get("notas_internas") or data.get("notas") or "")
        servicio_id = (data.get("servicio_id") or "").strip() or None
        expiracion = None
        if tipo_evento == "APARTADO_TEMPORAL" and data.get("expiracion_apartado"):
            expiracion = _parse_inicio({"inicio": data.get("expiracion_apartado")})

        if servicio_id:
            cur.execute("""
                SELECT id_servicio
                FROM CAT_SERVICIOS_CONSULTORIO
                WHERE id_servicio = %s AND correo_doctor = %s AND activo = TRUE
            """, (servicio_id, correo_doctor))
            if not cur.fetchone():
                return jsonify({"ok": False, "error": "Servicio no disponible para esta doctora"}), 400

        convirtiendo_a_cita = evento.get("tipo_evento") != "CITA_PACIENTE" and tipo_evento == "CITA_PACIENTE"
        _validar_traslape(
            cur,
            correo_doctor,
            inicio,
            duracion_minutos,
            excluir_id_radar=id_radar,
            solo_citas=convirtiendo_a_cita,
        )

        estatus = evento.get("estatus_confirmacion") or _estatus_inicial(tipo_evento)
        if convirtiendo_a_cita:
            estatus = "CONFIRMADO" if data.get("confirmado") else "Pendiente"
        titulo = _titulo_evento_agenda(tipo_evento, datos, estatus)
        enviar_comprobante = (
            _es_cita_cercana_con_comprobante(tipo_evento, inicio, datos)
            and not evento.get("correo_registro_enviado_en")
            and not evento.get("confirmacion_enviada_en")
        )
        requiere_confirmacion = (
            False if enviar_comprobante else evento.get("requiere_confirmacion_enlace", True)
        )

        google_actualizado = False
        if evento.get("google_event_id"):
            google_actualizado = actualizar_evento_doko(
                correo_doctor=correo_doctor,
                google_event_id=evento.get("google_event_id"),
                id_radar=str(id_radar),
                tipo_evento=tipo_evento,
                titulo=titulo,
                inicio=inicio,
                duracion_minutos=duracion_minutos,
                descripcion=_descripcion_google(datos, notas, tipo_evento),
                paciente_correo=datos.get("correo") if tipo_evento == "CITA_PACIENTE" else None,
            )

        cur.execute("""
            UPDATE RADAR_EVENTOS_CITAS
            SET fecha_cita = %s,
                datos_paciente = %s,
                estatus_confirmacion = %s,
                tipo_evento = %s,
                notas_internas = NULLIF(%s, ''),
                telefono_manual = NULLIF(%s, ''),
                correo_manual = NULLIF(%s, ''),
                servicio_id = %s,
                expiracion_apartado = %s,
                requiere_confirmacion_enlace = %s,
                origen_evento = CASE WHEN %s THEN %s ELSE origen_evento END,
                confirmacion_error_en = NULL,
                confirmacion_error_motivo = NULL
            WHERE id_radar = %s AND correo_doctor = %s
        """, (
            inicio,
            json.dumps(datos),
            estatus,
            tipo_evento,
            notas,
            datos.get("telefono") or "",
            datos.get("correo") or "",
            servicio_id,
            expiracion,
            requiere_confirmacion,
            convirtiendo_a_cita,
            "doko_asistente" if _rol_actor_actual() == "asistente" else "doko",
            id_radar,
            correo_doctor,
        ))
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            "AGENDA_EVENTO_EDITADO",
            correo_doctor,
            _rol_actor_actual(),
            json.dumps({
                "id_radar": str(id_radar),
                "tipo_evento": tipo_evento,
                "google_actualizado": google_actualizado,
                "convertido_automaticamente": convertido_automaticamente,
            }),
            request.remote_addr,
        ))
        conn.commit()
        correo_registro_enviado = False
        if enviar_comprobante:
            cur.execute("""
                SELECT nombre_doctor, especialidad, telefono_consultorio,
                       direccion_consultorio, maps_url
                FROM DOCTORES
                WHERE correo_doctor = %s AND activo = TRUE
            """, (correo_doctor,))
            doctor = cur.fetchone()
            correo_registro_enviado = _enviar_y_registrar_comprobante(conn, cur, {
                "id_radar": id_radar,
                "correo_doctor": correo_doctor,
                "correo_manual": datos.get("correo"),
                "datos_paciente": datos,
                "fecha_cita": inicio,
            }, doctor)
        flujo_correo = metadatos_flujo_guardado(
            tipo_evento=tipo_evento,
            fecha_cita=inicio,
            correo=datos.get("correo") or "",
            confirmado="CONFIRM" in str(estatus or "").upper() or "VERIFIC" in str(estatus or "").upper(),
            modo_confirmacion=configuracion_doctor.get("modo_confirmacion") or "manual",
            confirmacion_dias_habiles=bool(configuracion_doctor.get("confirmacion_dias_habiles")),
            intento_inmediato=enviar_comprobante,
            enviado=(
                correo_registro_enviado
                or bool(evento.get("correo_registro_enviado_en"))
                or bool(evento.get("confirmacion_enviada_en"))
            ),
        )
        return jsonify({
            "ok": True,
            "id_radar": id_radar,
            "google_actualizado": google_actualizado,
            "tipo_evento": tipo_evento,
            "correo_registro_enviado": correo_registro_enviado,
            "convertido_automaticamente": convertido_automaticamente,
            "flujo_correo": flujo_correo,
        })
    except Exception as exc:
        conn.rollback()
        return jsonify({"ok": False, "error": _mensaje_error_operativo(exc)}), 400
    finally:
        conn.close()


@panel_bp.route("/panel/agenda/<id_radar>/convertir", methods=["POST"])
@requiere_jwt
def convertir_apartado_a_cita(id_radar):
    correo_doctor = request.correo_doctor
    data = request.get_json(silent=True) or {}
    confirmado = bool(data.get("confirmado"))
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        _asegurar_doctora_asignada_si_asistente(cur, correo_doctor)
        cur.execute("""
            SELECT id_radar, google_event_id, tipo_evento, datos_paciente, fecha_cita,
                   correo_registro_enviado_en, confirmacion_enviada_en
            FROM RADAR_EVENTOS_CITAS
            WHERE id_radar = %s AND correo_doctor = %s
              AND tipo_evento = 'APARTADO_TEMPORAL'
              AND COALESCE(estado_operativo, 'activo') = 'activo'
            FOR UPDATE
        """, (id_radar, correo_doctor))
        apartado = cur.fetchone()
        if not apartado:
            return jsonify({"ok": False, "error": "Apartado no disponible para convertir"}), 404
        datos = apartado.get("datos_paciente") or {}
        if data.get("nombre_paciente"):
            datos["nombre"] = data.get("nombre_paciente").strip()
        if data.get("correo"):
            datos["correo"] = data.get("correo").strip()
        if data.get("telefono"):
            datos["telefono"] = "".join(ch for ch in data.get("telefono", "") if ch.isdigit())
        enviar_comprobante = (
            _es_cita_cercana_con_comprobante("CITA_PACIENTE", apartado.get("fecha_cita"), datos)
            and not apartado.get("correo_registro_enviado_en")
            and not apartado.get("confirmacion_enviada_en")
        )
        cur.execute("""
            UPDATE RADAR_EVENTOS_CITAS
            SET tipo_evento = 'CITA_PACIENTE',
                estatus_confirmacion = %s,
                datos_paciente = %s,
                correo_manual = NULLIF(%s, ''),
                telefono_manual = NULLIF(%s, ''),
                expiracion_apartado = NULL,
                estado_operativo = 'activo',
                requiere_confirmacion_enlace = %s,
                confirmacion_error_en = NULL,
                confirmacion_error_motivo = NULL
            WHERE id_radar = %s AND correo_doctor = %s
        """, ("CONFIRMADO" if confirmado else "Pendiente", json.dumps(datos), datos.get("correo") or "",
              datos.get("telefono") or "", not enviar_comprobante, id_radar, correo_doctor))
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
            VALUES (%s, %s, %s, %s, %s)
        """, ("APARTADO_CONVERTIDO_A_CITA", correo_doctor, _rol_actor_actual(),
              json.dumps({"id_radar": str(id_radar), "confirmado": confirmado}), request.remote_addr))
        if confirmado:
            try:
                marcar_evento_confirmado_doko(correo_doctor, apartado.get("google_event_id"))
            except Exception as exc:
                cur.execute("""
                    INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
                    VALUES (%s, %s, %s, %s, %s)
                """, ("CALENDAR_CONFIRMADA_FALLIDA", correo_doctor, "sistema",
                      json.dumps({"id_radar": str(id_radar), "error": str(exc)[:220]}), request.remote_addr))
        conn.commit()
        correo_registro_enviado = False
        if enviar_comprobante:
            cur.execute("""
                SELECT nombre_doctor, especialidad, telefono_consultorio,
                       direccion_consultorio, maps_url
                FROM DOCTORES
                WHERE correo_doctor = %s AND activo = TRUE
            """, (correo_doctor,))
            doctor = cur.fetchone()
            correo_registro_enviado = _enviar_y_registrar_comprobante(conn, cur, {
                "id_radar": id_radar,
                "correo_doctor": correo_doctor,
                "correo_manual": datos.get("correo"),
                "datos_paciente": datos,
                "fecha_cita": apartado.get("fecha_cita"),
            }, doctor)
        return jsonify({"ok": True, "correo_registro_enviado": correo_registro_enviado})
    except Exception as exc:
        conn.rollback()
        return jsonify({"ok": False, "error": _mensaje_error_operativo(exc)}), 400
    finally:
        conn.close()


@panel_bp.route("/panel/informe-mensual", methods=["GET"])
@requiere_jwt
def get_informe_mensual():
    """Resumen privado del doctor, disponible al cierre de cada mes."""
    ahora_tijuana = datetime.now(TZ_TIJUANA)
    if ahora_tijuana.day < 25:
        return jsonify({"disponible": False})

    inicio_mes = datetime(ahora_tijuana.year, ahora_tijuana.month, 1)
    if ahora_tijuana.month == 12:
        inicio_siguiente_mes = datetime(ahora_tijuana.year + 1, 1, 1)
    else:
        inicio_siguiente_mes = datetime(ahora_tijuana.year, ahora_tijuana.month + 1, 1)

    if ahora_tijuana.month == 1:
        inicio_mes_anterior = datetime(ahora_tijuana.year - 1, 12, 1)
    else:
        inicio_mes_anterior = datetime(ahora_tijuana.year, ahora_tijuana.month - 1, 1)

    ahora_local = ahora_tijuana.replace(tzinfo=None)
    correo_doctor = request.correo_doctor
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT
                COUNT(*) FILTER (
                    WHERE fecha_cita >= %s AND fecha_cita < %s
                ) AS citas,
                COUNT(*) FILTER (
                    WHERE fecha_cita >= %s AND fecha_cita < %s
                      AND (
                          COALESCE(estado_operativo, 'activo') = 'activo'
                          AND (
                              UPPER(COALESCE(estatus_confirmacion, '')) LIKE 'CONFIRM%%'
                              OR UPPER(COALESCE(estatus_confirmacion, '')) LIKE 'VERIFIC%%'
                          )
                      )
                ) AS confirmadas,
                COUNT(*) FILTER (
                    WHERE fecha_cita >= %s AND fecha_cita < %s
                      AND COALESCE(estado_operativo, 'activo') = 'activo'
                      AND UPPER(COALESCE(estatus_confirmacion, 'Pendiente')) LIKE 'PEND%%'
                ) AS pendientes,
                COUNT(*) FILTER (
                    WHERE fecha_cita >= %s AND fecha_cita < %s
                      AND (
                          UPPER(COALESCE(estatus_confirmacion, '')) LIKE 'CANCEL%%'
                          OR COALESCE(estado_operativo, 'activo') = 'cancelado'
                      )
                ) AS canceladas,
                COUNT(*) FILTER (
                    WHERE fecha_cita >= %s AND fecha_cita < %s
                ) AS citas_mes_anterior,
                COUNT(*) FILTER (
                    WHERE fecha_cita >= %s AND fecha_cita < %s
                      AND COALESCE(estado_operativo, 'activo') = 'activo'
                      AND UPPER(COALESCE(estatus_confirmacion, 'Pendiente')) LIKE 'PEND%%'
                ) AS pendientes_por_confirmar
            FROM RADAR_EVENTOS_CITAS
            WHERE correo_doctor = %s
              AND COALESCE(tipo_evento, 'CITA_PACIENTE') = 'CITA_PACIENTE'
        """, (
            inicio_mes, inicio_siguiente_mes,
            inicio_mes, inicio_siguiente_mes,
            inicio_mes, inicio_siguiente_mes,
            inicio_mes, inicio_siguiente_mes,
            inicio_mes_anterior, inicio_mes,
            ahora_local, inicio_siguiente_mes,
            correo_doctor,
        ))
        resumen = cur.fetchone() or {}
    finally:
        conn.close()

    citas = int(resumen.get("citas") or 0)
    confirmadas = int(resumen.get("confirmadas") or 0)
    pendientes_por_confirmar = int(resumen.get("pendientes_por_confirmar") or 0)
    citas_mes_anterior = int(resumen.get("citas_mes_anterior") or 0)
    alertas = []
    if pendientes_por_confirmar:
        alertas.append({
            "nivel": "Atencion",
            "texto": f"Hay {pendientes_por_confirmar} citas próximas pendientes de confirmación.",
        })

    return jsonify({
        "disponible": True,
        "periodo": {"anio": ahora_tijuana.year, "mes": ahora_tijuana.month},
        "metricas": {
            "citas": citas,
            "confirmadas": confirmadas,
            "pendientes": int(resumen.get("pendientes") or 0),
            "canceladas": int(resumen.get("canceladas") or 0),
            "tasa_confirmacion": round((confirmadas / citas) * 100) if citas else 0,
            "citas_mes_anterior": citas_mes_anterior,
            "variacion_citas": citas - citas_mes_anterior,
        },
        "alertas": alertas,
    })

@panel_bp.route("/panel/perfil", methods=["GET", "POST"])
@requiere_jwt
def manejar_perfil():
    """
    GET: Devuelve datos del doctor.
    POST: Actualiza SOLO los 3 campos permitidos (Seccion 2.1).
    """
    correo_doctor = request.correo_doctor
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        _asegurar_doctora_asignada_si_asistente(cur, correo_doctor)
        
        if request.method == "GET":
            cur.execute("""
                SELECT correo_doctor, nombre_doctor, especialidad, telefono_consultorio, id_publico,
                       onboarding_completo, foto_perfil_url, calendar_booking_url, direccion_consultorio,
                       maps_url, aseguradoras_aceptadas, metodos_pago_aceptados, horarios_atencion,
                       color_tema, aviso_consultorio, aviso_activo, aviso_expira_en,
                       aviso_visible_portal, aviso_visible_chatbot, aviso_visible_web,
                       activo, fecha_registro
                FROM DOCTORES
                WHERE correo_doctor = %s
            """, (correo_doctor,))
            doctor = cur.fetchone()
            return jsonify({"doctor": doctor})
        
        if request.method == "POST":
            data = request.json or {}
            # Regla de oro: Ignoramos cualquier otro campo silenciosamente
            nombre = (data.get("nombre_doctor") or "").strip() or None
            aseguradoras = (data.get("aseguradoras_aceptadas") or "").strip() or None
            metodos_pago = (data.get("metodos_pago_aceptados") or "").strip()
            # Una PWA anterior no envia este campo: en ese caso se conserva el horario ya guardado.
            horarios_payload = data.get("horarios_atencion")
            horarios_atencion = horarios_payload.strip() if isinstance(horarios_payload, str) else None
            color_tema = (data.get("color_tema") or "marino").strip()
            if color_tema not in {"marino", "verde", "turquesa", "lila", "sakura", "vino"}:
                return jsonify({"ok": False, "error": "Color de tema no válido."}), 400
            especialidad = (data.get("especialidad") or "").strip() or None
            telefono = (data.get("telefono_consultorio") or "").strip() or None
            aviso_consultorio = (data.get("aviso_consultorio") or "").strip() or None
            aviso_activo = bool(data.get("aviso_activo"))
            aviso_expira_en = (data.get("aviso_expira_en") or "").strip() or None
            aviso_visible_portal = bool(data.get("aviso_visible_portal", True))
            aviso_visible_chatbot = bool(data.get("aviso_visible_chatbot", True))
            aviso_visible_web = bool(data.get("aviso_visible_web", True))

            cur.execute("""
                UPDATE DOCTORES 
                SET nombre_doctor = COALESCE(%s, nombre_doctor),
                    aseguradoras_aceptadas = COALESCE(%s, aseguradoras_aceptadas),
                    metodos_pago_aceptados = %s,
                    horarios_atencion = COALESCE(%s, horarios_atencion),
                    color_tema = %s,
                    especialidad = COALESCE(%s, especialidad),
                    telefono_consultorio = COALESCE(%s, telefono_consultorio),
                    aviso_consultorio = %s,
                    aviso_activo = %s,
                    aviso_expira_en = %s,
                    aviso_visible_portal = %s,
                    aviso_visible_chatbot = %s,
                    aviso_visible_web = %s
                WHERE correo_doctor = %s
            """, (
                nombre, aseguradoras, metodos_pago, horarios_atencion, color_tema, especialidad, telefono,
                aviso_consultorio, aviso_activo, aviso_expira_en, aviso_visible_portal, aviso_visible_chatbot,
                aviso_visible_web, correo_doctor,
            ))
            
            cur.execute("""
                INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, ip_origen)
                VALUES (
                    'EDICION_PERFIL',
                    %s,
                    %s,
                    %s
                )
            """, (correo_doctor, _rol_actor_actual(), request.remote_addr))
            
            conn.commit()
            return jsonify({"ok": True, "mensaje": "Perfil actualizado"})
    except PermissionError as e:
        conn.rollback()
        return jsonify({"ok": False, "error": _mensaje_error_operativo(e)}), 403
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": _mensaje_error_operativo(e)}), 500
    finally:
        conn.close()

@panel_bp.route("/panel/perfil/foto", methods=["POST"])
@requiere_jwt
def subir_foto_perfil_doctor():
    """Permite al doctor actualizar su propia foto de perfil desde el panel privado."""
    archivo = request.files.get("foto") or request.files.get("file")
    if not archivo or not archivo.filename:
        return jsonify({"ok": False, "error": "foto_requerida"}), 400

    conn = get_connection()
    try:
        cur = conn.cursor()
        _asegurar_doctora_asignada_si_asistente(cur, request.correo_doctor)
        url_foto = subir_archivo(archivo.read(), archivo.filename, "doctores")
        cur.execute(
            "UPDATE DOCTORES SET foto_perfil_url = %s WHERE correo_doctor = %s",
            (url_foto, request.correo_doctor),
        )
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            "FOTO_PERFIL_DOCTOR",
            request.correo_doctor,
            _rol_actor_actual(),
            json.dumps({"foto_perfil_url": url_foto}),
            request.remote_addr,
        ))
        conn.commit()
        return jsonify({"ok": True, "url": url_foto})
    except PermissionError as e:
        conn.rollback()
        return jsonify({"ok": False, "error": _mensaje_error_operativo(e)}), 403
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": _mensaje_error_operativo(e)}), 400
    finally:
        conn.close()

# ==============================================================================
# 5.2 SETUP Y SERVICIOS
# ==============================================================================

@panel_bp.route("/panel/setup", methods=["GET", "POST"])
@requiere_jwt
def manejar_setup():
    """Controla el Onboarding del doctor."""
    correo_doctor = request.correo_doctor
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        _asegurar_doctora_asignada_si_asistente(cur, correo_doctor)
        
        if request.method == "GET":
            cur.execute("SELECT especialidad, telefono_consultorio, onboarding_completo FROM DOCTORES WHERE correo_doctor = %s", (correo_doctor,))
            doc = cur.fetchone()
            
            cur.execute("SELECT COUNT(*) FROM CAT_SERVICIOS_CONSULTORIO WHERE correo_doctor = %s", (correo_doctor,))
            servicios = cur.fetchone()["count"]
            
            paso1_completo = bool(doc["especialidad"] and doc["telefono_consultorio"])
            paso2_completo = servicios > 0
            
            return jsonify({
                "paso1_completo": paso1_completo,
                "paso2_completo": paso2_completo,
                "onboarding_completo": doc["onboarding_completo"]
            })

        if request.method == "POST":
            # Solo se marca como completo si ya cumplio los pasos
            cur.execute("""
                SELECT especialidad, telefono_consultorio
                FROM DOCTORES
                WHERE correo_doctor = %s
            """, (correo_doctor,))
            doc = cur.fetchone()
            cur.execute("""
                SELECT COUNT(*) AS total
                FROM CAT_SERVICIOS_CONSULTORIO
                WHERE correo_doctor = %s AND activo = TRUE
            """, (correo_doctor,))
            servicios = cur.fetchone()["total"]
            if not doc or not doc["especialidad"] or not doc["telefono_consultorio"] or servicios <= 0:
                return jsonify({"ok": False, "error": "perfil_incompleto"}), 400

            cur.execute("UPDATE DOCTORES SET onboarding_completo = TRUE WHERE correo_doctor = %s", (correo_doctor,))
            conn.commit()
            return jsonify({"ok": True})
    except PermissionError as e:
        conn.rollback()
        return jsonify({"ok": False, "error": _mensaje_error_operativo(e)}), 403
    finally:
        conn.close()

@panel_bp.route("/panel/servicios", methods=["GET", "POST"])
@requiere_jwt
def manejar_servicios():
    """CRUD de servicios del consultorio."""
    correo_doctor = request.correo_doctor
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        _asegurar_doctora_asignada_si_asistente(cur, correo_doctor)
        
        if request.method == "GET":
            cur.execute("SELECT id_servicio, nombre_servicio, precio, tipo_precio, descripcion FROM CAT_SERVICIOS_CONSULTORIO WHERE correo_doctor = %s AND activo = TRUE", (correo_doctor,))
            return jsonify({"servicios": cur.fetchall()})
            
        if request.method == "POST":
            data = request.json or {}
            nombre_servicio = (data.get("nombre_servicio") or "").strip()
            if not nombre_servicio:
                return jsonify({"ok": False, "error": "Escribe el nombre del servicio."}), 400
            tipo_precio = data.get("tipo_precio", "precio_fijo")
            if tipo_precio not in {"precio_fijo", "segun_valoracion", "costo_durante_consulta"}:
                return jsonify({"ok": False, "error": "Tipo de precio no válido."}), 400
            precio = data.get("precio")
            if tipo_precio == "precio_fijo":
                try:
                    precio = float(precio)
                    if precio < 0: raise ValueError
                except (TypeError, ValueError):
                    return jsonify({"ok": False, "error": "El precio fijo es obligatorio."}), 400
            else:
                precio = None
            cur.execute("""
                INSERT INTO CAT_SERVICIOS_CONSULTORIO (correo_doctor, nombre_servicio, precio, tipo_precio, descripcion)
                VALUES (%s, %s, %s, %s, %s) RETURNING id_servicio
            """, (correo_doctor, nombre_servicio, precio, tipo_precio, data.get("descripcion", "")))
            conn.commit()
            return jsonify({"ok": True, "id_servicio": cur.fetchone()["id_servicio"]})
    except PermissionError as e:
        conn.rollback()
        return jsonify({"ok": False, "error": _mensaje_error_operativo(e)}), 403
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": _mensaje_error_operativo(e)}), 500
    finally:
        conn.close()

@panel_bp.route("/panel/servicios/<id_servicio>", methods=["PUT", "DELETE"])
@requiere_jwt
def borrar_servicio(id_servicio):
    correo_doctor = request.correo_doctor
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        _asegurar_doctora_asignada_si_asistente(cur, correo_doctor)
        # Verificamos pertenencia (403 si intenta borrar el de otro)
        cur.execute("SELECT id_servicio FROM CAT_SERVICIOS_CONSULTORIO WHERE id_servicio = %s AND correo_doctor = %s", (id_servicio, correo_doctor))
        if not cur.fetchone():
            return jsonify({"error": "No autorizado o no encontrado"}), 403

        if request.method == "PUT":
            data = request.json or {}
            nombre_servicio = (data.get("nombre_servicio") or "").strip()
            if not nombre_servicio:
                return jsonify({"ok": False, "error": "Escribe el nombre del servicio."}), 400
            tipo_precio = data.get("tipo_precio", "precio_fijo")
            if tipo_precio not in {"precio_fijo", "segun_valoracion", "costo_durante_consulta"}:
                return jsonify({"ok": False, "error": "Tipo de precio no válido."}), 400
            precio = data.get("precio")
            if tipo_precio == "precio_fijo":
                try:
                    precio = float(precio)
                    if precio < 0: raise ValueError
                except (TypeError, ValueError):
                    return jsonify({"ok": False, "error": "El precio fijo es obligatorio."}), 400
            else:
                precio = None
            cur.execute("""
                UPDATE CAT_SERVICIOS_CONSULTORIO
                SET nombre_servicio = %s,
                    precio = %s,
                    tipo_precio = %s,
                    descripcion = %s
                WHERE id_servicio = %s
                  AND correo_doctor = %s
            """, (
                nombre_servicio,
                precio,
                tipo_precio,
                data.get("descripcion", ""),
                id_servicio,
                correo_doctor,
            ))
            conn.commit()
            return jsonify({"ok": True})
            
        cur.execute("UPDATE CAT_SERVICIOS_CONSULTORIO SET activo = FALSE WHERE id_servicio = %s", (id_servicio,))
        conn.commit()
        return jsonify({"ok": True})
    except PermissionError as e:
        conn.rollback()
        return jsonify({"ok": False, "error": _mensaje_error_operativo(e)}), 403
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": _mensaje_error_operativo(e)}), 500
    finally:
        conn.close()

# ==============================================================================
# 5.3 TIENDA B2B Y PEDIDOS (Transacciones Criticas)
# ==============================================================================

@panel_bp.route("/panel/tienda", methods=["GET"])
@requiere_jwt
def get_tienda():
    """Catalogo: calcula precio en backend, nunca expone precio_compra."""
    correo_doctor = request.correo_doctor
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT nombre_doctor FROM DOCTORES WHERE correo_doctor = %s", (correo_doctor,))
        doctor = cur.fetchone() or {}
        cur.execute("""
            SELECT 
                p.id_producto, p.nombre_comercial, p.descripcion, p.galeria_fotos,
                p.precio_venta,
                COALESCE(SUM(l.cantidad_piezas_actual), 0) as stock_disponible
            FROM CAT_PRODUCTOS_MAESTRO p
            LEFT JOIN INVENTARIO_LOTES l
                ON p.id_producto = l.id_producto
                AND l.activo = TRUE
                AND l.cantidad_piezas_actual > 0
                AND l.fecha_caducidad >= CURRENT_DATE
            WHERE p.estatus_producto = 'activo'
            GROUP BY p.id_producto, p.nombre_comercial, p.descripcion, p.galeria_fotos, p.precio_venta
            ORDER BY p.nombre_comercial ASC
        """)
        return jsonify({
            "catalogo": cur.fetchall(),
            "doctor": doctor,
            "whatsapp_number": config_bunker.WHATSAPP_NUMBER,
        })
    finally:
        conn.close()

@panel_bp.route("/panel/tienda/pedido", methods=["POST"])
@requiere_jwt
def crear_pedido():
    """Crea pedido interno del doctor sin descontar inventario; bodega surte después."""
    correo_doctor = request.correo_doctor
    data = request.json or {}
    carrito = data.get("productos") or data.get("carrito") or []

    if not carrito:
        return jsonify({"ok": False, "error": "Carrito vacío"}), 400

    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        total_pedido = 0
        detalles_pedido = []

        for item in carrito:
            id_prod = item.get("id_producto")
            try:
                cant_requerida = int(item.get("cantidad", 0))
            except (TypeError, ValueError):
                cant_requerida = 0

            if not id_prod or cant_requerida <= 0:
                return jsonify({"ok": False, "error": "Producto o cantidad inválida"}), 400

            cur.execute("""
                SELECT
                    p.id_producto,
                    p.precio_venta,
                    COALESCE(SUM(l.cantidad_piezas_actual), 0) AS stock_disponible
                FROM CAT_PRODUCTOS_MAESTRO p
                LEFT JOIN INVENTARIO_LOTES l
                    ON p.id_producto = l.id_producto
                    AND l.activo = TRUE
                    AND l.cantidad_piezas_actual > 0
                    AND l.fecha_caducidad >= CURRENT_DATE
                WHERE p.id_producto = %s
                    AND p.estatus_producto = 'activo'
                GROUP BY p.id_producto, p.precio_venta
            """, (id_prod,))
            producto = cur.fetchone()

            if not producto:
                return jsonify({"ok": False, "error": "Producto no disponible"}), 400

            stock_disponible = int(producto["stock_disponible"] or 0)
            if stock_disponible < cant_requerida:
                return jsonify({"ok": False, "error": "Stock insuficiente para uno de los productos"}), 400

            cur.execute("""
                SELECT id_lote
                FROM INVENTARIO_LOTES
                WHERE id_producto = %s
                    AND activo = TRUE
                    AND cantidad_piezas_actual > 0
                    AND fecha_caducidad >= CURRENT_DATE
                ORDER BY fecha_caducidad ASC NULLS LAST
                LIMIT 1
            """, (id_prod,))
            lote_referencia = cur.fetchone()
            if not lote_referencia:
                return jsonify({"ok": False, "error": "No hay lote disponible para referencia"}), 400

            precio_unitario = producto["precio_venta"]
            total_pedido += cant_requerida * precio_unitario
            detalles_pedido.append({
                "id_producto": id_prod,
                "id_lote": lote_referencia["id_lote"],
                "cantidad": cant_requerida,
                "precio_unitario": precio_unitario,
            })

        cur.execute("""
            INSERT INTO VENTAS_PEDIDOS_ELITE (correo_doctor, fecha_pedido, total_pedido, estatus_entrega)
            VALUES (%s, NOW(), %s, 'nuevo') RETURNING id_pedido
        """, (correo_doctor, total_pedido))
        id_pedido = cur.fetchone()["id_pedido"]

        for detalle in detalles_pedido:
            cur.execute("""
                INSERT INTO DETALLE_VENTA_LOTES (id_pedido, id_producto, id_lote, cantidad, precio_unitario)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                id_pedido,
                detalle["id_producto"],
                detalle["id_lote"],
                detalle["cantidad"],
                detalle["precio_unitario"],
            ))

        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle)
            VALUES (
                'NUEVO_PEDIDO',
                %s,
                'doctor',
                %s
            )
        """, (correo_doctor, json.dumps({"id_pedido": str(id_pedido), "total": float(total_pedido)})))

        conn.commit()

    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": _mensaje_error_operativo(e)}), 400
    finally:
        conn.close()

    return jsonify({
        "ok": True,
        "id_pedido": str(id_pedido),
        "mensaje": "Pedido enviado correctamente. Doko lo preparara para surtido y entrega.",
    })
@panel_bp.route("/panel/pedidos", methods=["GET"])
@requiere_jwt
def get_mis_pedidos():
    """Historial de pedidos del doctor con estatus de entrega."""
    correo_doctor = request.correo_doctor
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id_pedido, fecha_pedido, total_pedido, estatus_entrega, evidencia_entrega_url 
            FROM VENTAS_PEDIDOS_ELITE 
            WHERE correo_doctor = %s 
            ORDER BY fecha_pedido DESC
        """, (correo_doctor,))
        return jsonify({"pedidos": cur.fetchall()})
    finally:
        conn.close()
