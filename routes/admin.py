import json
import re
import threading
import unicodedata
import uuid
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, session
from psycopg2.extras import RealDictCursor

from helpers.db import get_connection
from helpers.decorators import requiere_rol
from helpers.storage import subir_archivo
from config_bunker import (
    GCS_BUCKET_NAME,
    IMPLEMENTATION_AI_CLINIC_DAILY_LIMIT,
    IMPLEMENTATION_AI_GLOBAL_DAILY_LIMIT,
    PANEL_ASSISTANT_GEMINI_CLINIC_DAILY_LIMIT,
    PANEL_ASSISTANT_GEMINI_GLOBAL_DAILY_LIMIT,
    PRESENCIA_BASE_DOMAIN,
)

# Importación de Agentes
from agentes.nivel3.agente_reparto import AgenteReparto
from agentes.nivel4.agente_supervisor import AgenteSupervisor
from agentes.nivel1.agente_comercial import AgenteComercial
from agentes.nivel1.agente_compras import AgenteCompras
from agentes.nivel1.agente_financiero import AgenteFinanciero
from agentes.cerebro_gemini import CerebroGemini

admin_bp = Blueprint('admin_bp', __name__)

SEO_LOCAL_SLUGS_RESERVADOS = {
    'admin', 'app', 'c', 'login', 'oauth2callback', 'p', 'panel', 'privacidad',
    'robots.txt', 'sitemap.xml', 'static', 'sw.js', 'terminos',
    'medicos-en-tijuana', 'doctores-en-tijuana', 'especialistas-en-tijuana',
    'ginecologia-tijuana', 'colposcopia-tijuana', 'papanicolaou-tijuana',
}


def _datos_formulario():
    """Lee datos de application/x-www-form-urlencoded o JSON sin KeyError."""
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict()


def _respuesta_ajax_o_redirect(ok=True, error=None, redirect_endpoint='admin_bp.doctores', **json_extra):
    from flask import redirect, url_for
    if request.is_json or request.headers.get('Content-Type', '').startswith('application/json'):
        if ok:
            return jsonify({'ok': True, **json_extra})
        return jsonify({'ok': False, 'error': error or 'Error en la operación'}), 400
    if ok:
        return redirect(url_for(redirect_endpoint))
    return redirect(url_for(redirect_endpoint))


def _tablas_presencia_disponibles(cur) -> bool:
    cur.execute("""
        SELECT to_regclass('public.sitios_medicos') AS tabla,
               EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'sitios_medicos' AND column_name = 'hero_titulo'
               ) AS campos_sitio,
               EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'doctores' AND column_name = 'aviso_consultorio'
               ) AS campos_doctor
    """)
    estado = cur.fetchone()
    return bool(estado and estado['tabla'] and estado['campos_sitio'] and estado['campos_doctor'])


def _subdominio_valido(valor: str) -> str:
    subdominio = (valor or '').strip().lower()
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', subdominio) or subdominio == 'app':
        raise ValueError('El subdominio solo puede usar minúsculas, números y guiones.')
    return subdominio


def _url_publica_valida(valor: str, campo: str) -> str | None:
    valor = (valor or '').strip()
    if not valor or valor.lower() in {'none', 'null'}:
        return None
    prefijo_gs = f'gs://{GCS_BUCKET_NAME}/'
    prefijo_storage_web = f'https://storage.cloud.google.com/{GCS_BUCKET_NAME}/'
    if valor.startswith(prefijo_gs):
        valor = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{valor[len(prefijo_gs):]}"
    elif valor.startswith(prefijo_storage_web):
        valor = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{valor[len(prefijo_storage_web):]}"
    parsed = re.match(r'^https?://[^\s/$.?#][^\s]*$', valor, re.IGNORECASE)
    if not parsed:
        raise ValueError(f'{campo} debe usar una URL http:// o https:// válida.')
    return valor


def _bool_form(d, nombre, default=False) -> bool:
    valor = d.get(nombre)
    if valor is None:
        return default
    return str(valor).lower() in {'1', 'true', 'on', 'si', 'sí', 'yes'}


def _texto(d, nombre):
    return (d.get(nombre) or '').strip() or None


def _int_opcional(d, nombre):
    valor = (d.get(nombre) or '').strip()
    if not valor:
        return None
    return max(0, int(valor))


def _checklist_presencia(sitio):
    if not sitio:
        return []
    faltantes = []
    if not sitio.get('id_publico'):
        faltantes.append('Portal Doko / ID público')
    if not sitio.get('subdominio'):
        faltantes.append('Subdominio')
    if not (sitio.get('nombre_clinica_publico') or sitio.get('nombre_doctor')):
        faltantes.append('Nombre público')
    if not (sitio.get('especialidad_publica') or sitio.get('especialidad')):
        faltantes.append('Especialidad')
    if not sitio.get('ciudad'):
        faltantes.append('Ciudad')
    if not sitio.get('titulo_seo'):
        faltantes.append('Título SEO')
    if not sitio.get('descripcion_seo'):
        faltantes.append('Meta description')
    if not sitio.get('portada_url'):
        faltantes.append('Sub portada')
    if not sitio.get('mostrar_agenda'):
        faltantes.append('Botón Agendar activo')
    return faltantes


def _subdominio_desde_texto(texto: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', (texto or '').lower()).strip('-')
    return slug or f"doctor-{uuid.uuid4().hex[:8]}"


def _slug_seo_local(valor: str) -> str:
    normalizado = unicodedata.normalize('NFKD', (valor or '').strip().lower())
    ascii_texto = ''.join(ch for ch in normalizado if not unicodedata.combining(ch))
    slug = re.sub(r'[^a-z0-9]+', '-', ascii_texto).strip('-')
    if not slug or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
        raise ValueError('La ruta SEO debe usar letras, números y guiones.')
    if slug in SEO_LOCAL_SLUGS_RESERVADOS:
        raise ValueError('Esa ruta pertenece al sistema o ya está publicada de forma fija.')
    return slug


def _terminos_seo_local(especialidad: str, valor) -> list[str]:
    candidatos = valor if isinstance(valor, list) else str(valor or '').split(',')
    salida = []
    vistos = set()
    for termino in [especialidad, *candidatos]:
        limpio = str(termino or '').strip()
        clave = limpio.casefold()
        if limpio and clave not in vistos:
            vistos.add(clave)
            salida.append(limpio)
    return salida[:20]


def _actualizar_medico_fundador_sitio(cur, correo_doctor: str, activo: bool, subdominio_sugerido: str | None = None) -> None:
    cur.execute("""
        SELECT to_regclass('public.sitios_medicos') AS tabla,
               EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'sitios_medicos' AND column_name = 'visual_config'
               ) AS tiene_visual_config
    """)
    estado = cur.fetchone()
    if not estado or not estado[0] or not estado[1]:
        return
    cur.execute("""
        UPDATE SITIOS_MEDICOS
        SET visual_config = COALESCE(visual_config, '{}'::jsonb)
                            || jsonb_build_object('medico_fundador', %s::boolean),
            actualizado_en = NOW()
        WHERE correo_doctor = %s
    """, (activo, correo_doctor))
    if cur.rowcount or not activo:
        return
    base = _subdominio_desde_texto(subdominio_sugerido or correo_doctor.split('@')[0])
    subdominio = base
    for intento in range(2, 8):
        cur.execute("SELECT 1 FROM SITIOS_MEDICOS WHERE subdominio = %s", (subdominio,))
        if not cur.fetchone():
            break
        subdominio = f"{base}-{intento}"
    cur.execute("""
        INSERT INTO SITIOS_MEDICOS (id_sitio, correo_doctor, subdominio, estado, visual_config)
        VALUES (%s, %s, %s, 'BORRADOR', jsonb_build_object('medico_fundador', true))
        ON CONFLICT (correo_doctor) DO UPDATE
        SET visual_config = COALESCE(SITIOS_MEDICOS.visual_config, '{}'::jsonb)
                            || jsonb_build_object('medico_fundador', true),
            actualizado_en = NOW()
    """, (str(uuid.uuid4()), correo_doctor, subdominio))


FRASES_RIESGO_PUBLICIDAD_MEDICA = (
    'el mejor', 'la mejor', 'garantizado', 'garantizada', 'garantiza',
    'infalible', 'cura definitiva', 'curacion definitiva', '100% efectivo',
    '100 % efectivo', 'sin riesgo', 'milagroso', 'me curo por completo',
    'antes y despues', 'antes/despues', 'resultados asegurados',
)


def _validar_texto_publicidad_medica(*textos):
    combinado = ' '.join(str(texto or '') for texto in textos).lower()
    reemplazos = str.maketrans('áàäâéèëêíìïîóòöôúùüû', 'aaaaeeeeiiiioooouuuu')
    combinado = combinado.translate(reemplazos)
    for frase in FRASES_RIESGO_PUBLICIDAD_MEDICA:
        if frase in combinado:
            raise ValueError(f'Revisa el texto publicitario: evita la frase "{frase}".')


def extraer_calendar_src(valor: str) -> str:
    """Devuelve solo la URL src de Google Calendar Appointment Schedule."""
    valor = (valor or '').strip()
    if not valor:
        return ''

    if '<iframe' in valor.lower():
        match = re.search(r'src=[\"\']([^\"\']+)[\"\']', valor, re.IGNORECASE)
        valor = match.group(1).strip() if match else ''

    prefijo = 'https://calendar.google.com/calendar/appointments/schedules/'
    if valor.startswith(prefijo):
        return valor

    raise ValueError('Pega una URL válida de Google Calendar Appointment Schedule.')


# ==============================================================================
# BLOQUE 9.1 — DASHBOARD, DOCTORES Y UPLOADS GCS
# ==============================================================================

@admin_bp.route('/admin', methods=['GET'])
@requiere_rol('admin')
def dashboard():
    """Dashboard principal con métricas operativas reales."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT COUNT(*) FROM DOCTORES WHERE activo = TRUE")
        doctores_activos = cur.fetchone()['count']

        cur.execute("""
            SELECT correo_doctor, nombre_doctor, modo_confirmacion
            FROM DOCTORES
            WHERE activo = TRUE
            ORDER BY nombre_doctor ASC
        """)
        politicas_confirmacion = cur.fetchall()

        cur.execute("""
            SELECT
                COUNT(*) FILTER (
                    WHERE fecha_cita >= NOW()
                      AND fecha_cita < NOW() + INTERVAL '7 days'
                ) AS proximas,
                COUNT(*) FILTER (
                    WHERE fecha_cita >= NOW()
                      AND fecha_cita < NOW() + INTERVAL '7 days'
                      AND UPPER(COALESCE(estatus_confirmacion, 'Pendiente')) LIKE 'PEND%%'
                ) AS pendientes,
                COUNT(*) FILTER (
                    WHERE fecha_cita >= NOW()
                      AND fecha_cita < NOW() + INTERVAL '7 days'
                      AND (
                          UPPER(COALESCE(estatus_confirmacion, '')) LIKE 'CONFIRM%%'
                          OR UPPER(COALESCE(estatus_confirmacion, '')) LIKE 'VERIFIC%%'
                      )
                ) AS confirmadas,
                COUNT(*) FILTER (
                    WHERE fecha_cita >= NOW()
                      AND fecha_cita < NOW() + INTERVAL '7 days'
                      AND UPPER(COALESCE(estatus_confirmacion, '')) LIKE 'CANCEL%%'
                ) AS canceladas
            FROM RADAR_EVENTOS_CITAS
            WHERE COALESCE(tipo_evento, 'CITA_PACIENTE') = 'CITA_PACIENTE'
              AND COALESCE(estado_operativo, 'activo') = 'activo'
        """)
        citas_kpi = cur.fetchone()
        citas_proximas = citas_kpi['proximas'] or 0
        citas_pendientes = citas_kpi['pendientes'] or 0
        citas_confirmadas = citas_kpi['confirmadas'] or 0
        citas_canceladas = citas_kpi['canceladas'] or 0

        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE estatus_entrega IN ('PENDIENTE', 'nuevo')) AS nuevos,
                COUNT(*) FILTER (WHERE estatus_entrega = 'preparando') AS preparando,
                COUNT(*) FILTER (WHERE estatus_entrega = 'en_camino') AS en_camino,
                COUNT(*) FILTER (
                    WHERE estatus_entrega = 'entregado'
                      AND COALESCE(hora_entrega, fecha_pedido) >= DATE_TRUNC('month', NOW())
                ) AS entregados_mes,
                COALESCE(SUM(total_pedido) FILTER (
                    WHERE fecha_pedido >= DATE_TRUNC('month', NOW())
                ), 0) AS valor_mes
            FROM VENTAS_PEDIDOS_ELITE
        """)
        pedidos_kpi = cur.fetchone()
        pedidos_nuevos = pedidos_kpi['nuevos'] or 0
        pedidos_preparando = pedidos_kpi['preparando'] or 0
        pedidos_en_camino = pedidos_kpi['en_camino'] or 0
        pedidos_entregados_mes = pedidos_kpi['entregados_mes'] or 0
        valor_pedidos_mes = pedidos_kpi['valor_mes'] or 0
        pedidos_abiertos = pedidos_nuevos + pedidos_preparando + pedidos_en_camino

        cur.execute("""
            SELECT COUNT(*) AS total
            FROM (
                SELECT p.id_producto, COALESCE(SUM(l.cantidad_piezas_actual), 0) AS stock
                FROM CAT_PRODUCTOS_MAESTRO p
                LEFT JOIN INVENTARIO_LOTES l
                    ON p.id_producto = l.id_producto
                    AND l.activo = TRUE
                    AND l.cantidad_piezas_actual > 0
                    AND l.fecha_caducidad >= CURRENT_DATE
                WHERE p.estatus_producto = 'activo'
                GROUP BY p.id_producto
                HAVING COALESCE(SUM(l.cantidad_piezas_actual), 0) > 0
                   AND COALESCE(SUM(l.cantidad_piezas_actual), 0) <= 5
            ) AS productos_bajos
        """)
        productos_bajo_stock = cur.fetchone()['total'] or 0

        cur.execute("""
            SELECT COUNT(*) AS total
            FROM INVENTARIO_LOTES
            WHERE activo = TRUE
              AND cantidad_piezas_actual > 0
              AND fecha_caducidad < CURRENT_DATE
        """)
        lotes_vencidos_stock = cur.fetchone()['total'] or 0

        cur.execute("""
            SELECT COUNT(*) AS total
            FROM INVENTARIO_LOTES
            WHERE activo = TRUE
              AND cantidad_piezas_actual > 0
              AND fecha_caducidad >= CURRENT_DATE
              AND fecha_caducidad <= CURRENT_DATE + INTERVAL '30 days'
        """)
        lotes_por_caducar = cur.fetchone()['total'] or 0

        cur.execute("""
            SELECT COUNT(*) AS total
            FROM (
                SELECT p.id_producto, COALESCE(SUM(l.cantidad_piezas_actual), 0) AS stock
                FROM CAT_PRODUCTOS_MAESTRO p
                LEFT JOIN INVENTARIO_LOTES l
                    ON p.id_producto = l.id_producto
                    AND l.activo = TRUE
                    AND l.cantidad_piezas_actual > 0
                    AND l.fecha_caducidad >= CURRENT_DATE
                WHERE p.estatus_producto = 'activo'
                GROUP BY p.id_producto
                HAVING COALESCE(SUM(l.cantidad_piezas_actual), 0) = 0
            ) AS productos_sin_stock
        """)
        productos_sin_stock = cur.fetchone()['total'] or 0

        cur.execute("SELECT COUNT(*) FROM PROVEEDORES WHERE activo = TRUE")
        proveedores_activos = cur.fetchone()['count']

        cur.execute("""
            SELECT fecha_ejecucion, nivel_alerta, reporte_gemini,
                   micro_reporte_auditor, micro_reporte_metricas, micro_reporte_riesgo,
                   EXTRACT(EPOCH FROM (NOW() - fecha_ejecucion)) / 3600 AS horas_desde
            FROM LOGS_SUPERVISOR
            ORDER BY fecha_ejecucion DESC
            LIMIT 1
        """)
        ultimo_supervisor = cur.fetchone()

        cur.execute("""
            SELECT DISTINCT ON (actor)
                   actor, fecha_evento,
                   detalle->>'ok' AS ok,
                   EXTRACT(EPOCH FROM (NOW() - fecha_evento)) / 3600 AS horas_desde
            FROM AUDITORIA_SEGURIDAD
            WHERE tipo_evento = 'EJECUCION_JOB'
              AND actor IN ('auditoria_calendar', 'avisos_citas')
            ORDER BY actor, fecha_evento DESC
        """)
        ultimos_jobs = {row['actor']: row for row in cur.fetchall()}

        cur.execute("""
            SELECT
                COUNT(*) FILTER (
                    WHERE confirmacion_enviada_en >= CURRENT_DATE
                ) AS confirmaciones_hoy,
                COUNT(*) FILTER (
                    WHERE fecha_registro >= CURRENT_DATE
                      AND COALESCE(tipo_evento, 'CITA_PACIENTE') = 'CITA_PACIENTE'
                      AND COALESCE(estado_operativo, 'activo') = 'activo'
                      AND NULLIF(TRIM(COALESCE(datos_paciente->>'correo', correo_manual, '')), '') IS NULL
                ) AS sin_correo_hoy,
                COUNT(*) FILTER (
                    WHERE confirmacion_error_en >= CURRENT_DATE
                      AND COALESCE(confirmacion_error_motivo, '') NOT ILIKE 'No hay correo%%'
                      AND COALESCE(confirmacion_error_motivo, '') NOT ILIKE 'Cita reservada con menos%%'
                ) AS errores_confirmacion_hoy,
                COUNT(*) FILTER (
                    WHERE cancelacion_automatica_en >= CURRENT_DATE
                      AND motivo_cancelacion = 'NO_CONFIRMADA'
                ) AS cancelaciones_auto_hoy,
                COUNT(*) FILTER (
                    WHERE fecha_cita >= NOW()
                      AND fecha_cita < NOW() + INTERVAL '7 days'
                      AND COALESCE(tipo_evento, 'CITA_PACIENTE') = 'CITA_PACIENTE'
                      AND COALESCE(estado_operativo, 'activo') = 'activo'
                      AND UPPER(COALESCE(estatus_confirmacion, 'Pendiente')) LIKE 'PEND%%'
                      AND NULLIF(TRIM(COALESCE(datos_paciente->>'correo', correo_manual, '')), '') IS NULL
                ) AS citas_sin_correo_7d,
                COUNT(*) FILTER (
                    WHERE fecha_cita >= NOW()
                      AND fecha_cita < NOW() + INTERVAL '7 days'
                      AND COALESCE(tipo_evento, 'CITA_PACIENTE') = 'CITA_PACIENTE'
                      AND COALESCE(estado_operativo, 'activo') = 'activo'
                      AND NULLIF(TRIM(COALESCE(datos_paciente->>'telefono', telefono_manual, '')), '') IS NULL
                ) AS citas_sin_telefono_7d
            FROM RADAR_EVENTOS_CITAS
        """)
        salud_operativa = cur.fetchone() or {}

        def total_auditoria(detalles):
            return len(detalles)

        def texto_afectados(detalles):
            nombres = [str(row.get('nombre') or '').strip() for row in detalles]
            nombres = [nombre for nombre in nombres if nombre]
            if not nombres:
                return 'la operación'
            if len(nombres) == 1:
                return nombres[0]
            visibles = ', '.join(nombres[:3])
            if len(nombres) > 3:
                visibles += f' y {len(nombres) - 3} más'
            return visibles

        cur.execute("""
            WITH auditoria_clasificada AS (
                SELECT a.*,
                    CASE
                    WHEN a.tipo_evento IN (
                        'CONFIRMACION_TOKEN_GOOGLE_FALLIDO',
                        'RECORDATORIO_TOKEN_GOOGLE_FALLIDO',
                        'TOKEN_GOOGLE_FALTANTE',
                        'GOOGLE_SIN_TOKEN',
                        'GOOGLE_SIN_PERMISOS',
                        'CANCELACION_GOOGLE_AUTORIZACION_FALLIDA',
                        'CORREO_CITA_REGISTRADA_TOKEN_FALLIDO'
                    ) OR (
                        a.tipo_evento IN (
                            'CONFIRMACION_ENVIO_FALLIDO',
                            'RECORDATORIO_CONFIRMADO_FALLIDO',
                            'CALENDAR_CONFIRMADA_FALLIDA',
                            'CANCELACION_GOOGLE_FALLIDA',
                            'GOOGLE_CONSULTA_FALLIDA'
                        )
                        AND LOWER(COALESCE(a.detalle::text, '')) LIKE ANY (ARRAY[
                            '%%invalid_grant%%',
                            '%%expired or revoked%%',
                            '%%debe reconectarse%%',
                            '%%no hay registros de token oauth%%'
                        ])
                    ) THEN 'oauth'
                    WHEN a.tipo_evento IN (
                        'CALENDAR_CONFIRMADA_FALLIDA',
                        'CANCELACION_GOOGLE_FALLIDA',
                        'GOOGLE_CONSULTA_FALLIDA'
                    ) THEN 'calendar'
                    WHEN a.tipo_evento IN (
                        'CONFIRMACION_ENVIO_FALLIDO',
                        'RECORDATORIO_CONFIRMADO_FALLIDO',
                        'CORREO_CITA_REGISTRADA_FALLIDO'
                    ) THEN 'gmail'
                    END AS categoria
                FROM AUDITORIA_SEGURIDAD a
                WHERE a.fecha_evento >= NOW() - INTERVAL '24 hours'
                  AND a.tipo_evento IN (
                        'CONFIRMACION_TOKEN_GOOGLE_FALLIDO',
                        'RECORDATORIO_TOKEN_GOOGLE_FALLIDO',
                        'TOKEN_GOOGLE_FALTANTE',
                        'GOOGLE_SIN_TOKEN',
                        'GOOGLE_SIN_PERMISOS',
                        'CANCELACION_GOOGLE_AUTORIZACION_FALLIDA',
                        'CORREO_CITA_REGISTRADA_TOKEN_FALLIDO',
                        'CALENDAR_CONFIRMADA_FALLIDA',
                        'CANCELACION_GOOGLE_FALLIDA',
                        'GOOGLE_CONSULTA_FALLIDA',
                        'CONFIRMACION_ENVIO_FALLIDO',
                        'RECORDATORIO_CONFIRMADO_FALLIDO',
                        'CORREO_CITA_REGISTRADA_FALLIDO'
                  )
                  AND NOT (
                      a.tipo_evento IN (
                          'CONFIRMACION_ENVIO_FALLIDO',
                          'RECORDATORIO_CONFIRMADO_FALLIDO'
                      )
                      AND LOWER(COALESCE(a.detalle::text, '')) LIKE '%%no hay correo%%'
                  )
                  AND NOT (
                      a.tipo_evento = 'CANCELACION_GOOGLE_FALLIDA'
                      AND EXISTS (
                          SELECT 1
                          FROM AUDITORIA_SEGURIDAD recuperacion
                          WHERE recuperacion.fecha_evento > a.fecha_evento
                            AND recuperacion.tipo_evento IN (
                                'CANCELACION_AUTOMATICA_NO_CONFIRMADA',
                                'AGENDA_EVENTO_LIBERADO'
                            )
                            AND NULLIF(recuperacion.detalle->>'id_radar', '') = NULLIF(a.detalle->>'id_radar', '')
                      )
                  )
            )
            SELECT
                a.categoria,
                a.actor,
                COALESCE(
                    NULLIF(TRIM(d.nombre_doctor), ''),
                    NULLIF(TRIM(a.actor), ''),
                    'Sistema'
                ) AS nombre,
                COUNT(*) AS total
            FROM auditoria_clasificada a
            LEFT JOIN DOCTORES d
              ON LOWER(TRIM(d.correo_doctor)) = LOWER(TRIM(a.actor))
            LEFT JOIN TOKENS_OAUTH t
              ON a.categoria = 'oauth'
             AND LOWER(TRIM(t.correo_doctor)) = LOWER(TRIM(a.actor))
            WHERE (
                  a.categoria <> 'oauth'
                  OR t.updated_at IS NULL
                  OR a.fecha_evento > t.updated_at
              )
            GROUP BY a.categoria, a.actor, d.nombre_doctor
            ORDER BY a.categoria, COUNT(*) DESC, nombre ASC
        """)
        auditoria_por_categoria = {
            'oauth': [],
            'calendar': [],
            'gmail': [],
        }
        for fila in cur.fetchall():
            auditoria_por_categoria[fila['categoria']].append(fila)

        fallas_oauth_detalle = auditoria_por_categoria['oauth']
        fallas_oauth_24h = total_auditoria(fallas_oauth_detalle)
        fallas_calendar_detalle = auditoria_por_categoria['calendar']
        fallas_calendar_24h = total_auditoria(fallas_calendar_detalle)
        fallas_gmail_detalle = auditoria_por_categoria['gmail']
        fallas_gmail_24h = total_auditoria(fallas_gmail_detalle)
        datos_paciente_incompletos_24h = (
            int(salud_operativa.get('citas_sin_correo_7d') or 0)
            + int(salud_operativa.get('citas_sin_telefono_7d') or 0)
        )
        fallas_google_oauth_24h = fallas_oauth_24h + fallas_calendar_24h + fallas_gmail_24h

        cur.execute("""
            SELECT
                d.correo_doctor,
                d.nombre_doctor,
                COUNT(r.id_radar) AS citas_mes,
                COUNT(r.id_radar) FILTER (
                    WHERE COALESCE(r.estado_operativo, 'activo') = 'activo'
                      AND (
                          UPPER(COALESCE(r.estatus_confirmacion, '')) LIKE 'CONFIRM%%'
                          OR UPPER(COALESCE(r.estatus_confirmacion, '')) LIKE 'VERIFIC%%'
                      )
                ) AS confirmadas,
                COUNT(r.id_radar) FILTER (
                    WHERE COALESCE(r.estado_operativo, 'activo') = 'activo'
                      AND UPPER(COALESCE(r.estatus_confirmacion, 'Pendiente')) LIKE 'PEND%%'
                ) AS pendientes,
                COUNT(r.id_radar) FILTER (
                    WHERE UPPER(COALESCE(r.estatus_confirmacion, '')) LIKE 'CANCEL%%'
                       OR COALESCE(r.estado_operativo, 'activo') = 'cancelado'
                ) AS canceladas
            FROM DOCTORES d
            LEFT JOIN RADAR_EVENTOS_CITAS r
                ON r.correo_doctor = d.correo_doctor
                AND r.fecha_cita >= DATE_TRUNC('month', NOW())
                AND r.fecha_cita < DATE_TRUNC('month', NOW()) + INTERVAL '1 month'
                AND COALESCE(r.tipo_evento, 'CITA_PACIENTE') = 'CITA_PACIENTE'
            WHERE d.activo = TRUE
            GROUP BY d.correo_doctor, d.nombre_doctor
            ORDER BY citas_mes DESC, d.nombre_doctor ASC
            LIMIT 6
        """)
        rendimiento_doctores_mes = []
        citas_mes_total = 0
        for row in cur.fetchall():
            citas_mes = row['citas_mes'] or 0
            confirmadas = row['confirmadas'] or 0
            citas_mes_total += citas_mes
            row['tasa_confirmacion'] = round((confirmadas / citas_mes) * 100) if citas_mes else 0
            rendimiento_doctores_mes.append(row)

        cur.execute("""
            SELECT v.id_pedido, v.correo_doctor, v.fecha_pedido, v.total_pedido, v.estatus_entrega,
                   d.nombre_doctor
            FROM VENTAS_PEDIDOS_ELITE v
            LEFT JOIN DOCTORES d ON v.correo_doctor = d.correo_doctor
            WHERE v.estatus_entrega IN ('PENDIENTE', 'nuevo')
            ORDER BY v.fecha_pedido ASC NULLS LAST
            LIMIT 5
        """)
        pedidos_nuevos_detalle = cur.fetchall()

        cur.execute("""
            SELECT p.nombre_comercial, COALESCE(SUM(l.cantidad_piezas_actual), 0) AS stock
            FROM CAT_PRODUCTOS_MAESTRO p
            LEFT JOIN INVENTARIO_LOTES l
                ON p.id_producto = l.id_producto
                AND l.activo = TRUE
                AND l.cantidad_piezas_actual > 0
                AND l.fecha_caducidad >= CURRENT_DATE
            WHERE p.estatus_producto = 'activo'
            GROUP BY p.id_producto, p.nombre_comercial
            HAVING COALESCE(SUM(l.cantidad_piezas_actual), 0) <= 5
            ORDER BY stock ASC, p.nombre_comercial ASC
            LIMIT 5
        """)
        productos_riesgo_detalle = cur.fetchall()

        cur.execute("""
            SELECT l.lote_proveedor, l.fecha_caducidad, l.cantidad_piezas_actual,
                   p.nombre_comercial
            FROM INVENTARIO_LOTES l
            JOIN CAT_PRODUCTOS_MAESTRO p ON l.id_producto = p.id_producto
            WHERE l.activo = TRUE
              AND l.cantidad_piezas_actual > 0
              AND l.fecha_caducidad < CURRENT_DATE
            ORDER BY l.fecha_caducidad ASC, p.nombre_comercial ASC
            LIMIT 5
        """)
        lotes_vencidos_detalle = cur.fetchall()

        cur.execute("""
            SELECT l.lote_proveedor, l.fecha_caducidad, l.cantidad_piezas_actual,
                   p.nombre_comercial
            FROM INVENTARIO_LOTES l
            JOIN CAT_PRODUCTOS_MAESTRO p ON l.id_producto = p.id_producto
            WHERE l.activo = TRUE
              AND l.cantidad_piezas_actual > 0
              AND l.fecha_caducidad >= CURRENT_DATE
              AND l.fecha_caducidad <= CURRENT_DATE + INTERVAL '30 days'
            ORDER BY l.fecha_caducidad ASC, p.nombre_comercial ASC
            LIMIT 5
        """)
        lotes_por_caducar_detalle = cur.fetchall()

        presencia_metricas = {
            'sitios_activos': 0,
            'medicos_directorio': 0,
            'especialidades_activas': 0,
            'visitas_30': 0,
            'clics_whatsapp_30': 0,
            'clics_agenda_30': 0,
            'dominios_pendientes': 0,
            'contenido_pendiente': 0,
            'seo_incompleto': 0,
            'horarios_recuperados_hoy': 0,
        }
        if _tablas_presencia_disponibles(cur):
            cur.execute("""
                SELECT
                    COUNT(DISTINCT s.id_sitio) FILTER (WHERE s.estado = 'PUBLICADO') AS sitios_activos,
                    COUNT(DISTINCT s.id_sitio) FILTER (
                        WHERE s.estado = 'PUBLICADO'
                          AND COALESCE(NULLIF(s.visual_config->>'visible_en_directorio', ''), 'true') <> 'false'
                    ) AS medicos_directorio,
                    COUNT(DISTINCT NULLIF(TRIM(COALESCE(s.especialidad_publica, d.especialidad, '')), '')) FILTER (
                        WHERE s.estado = 'PUBLICADO'
                          AND COALESCE(NULLIF(s.visual_config->>'visible_en_directorio', ''), 'true') <> 'false'
                    ) AS especialidades_activas,
                    COUNT(DISTINCT s.id_sitio) FILTER (WHERE s.estado_dominio != 'VERIFICADO') AS dominios_pendientes,
                    COUNT(DISTINCT s.id_sitio) FILTER (WHERE s.biografia IS NULL OR s.titulo_seo IS NULL OR s.portada_url IS NULL) AS contenido_pendiente,
                    COUNT(DISTINCT s.id_sitio) FILTER (
                        WHERE s.estado IN ('PUBLICADO', 'BORRADOR')
                          AND (
                              NULLIF(TRIM(COALESCE(s.titulo_seo, '')), '') IS NULL
                              OR NULLIF(TRIM(COALESCE(s.descripcion_seo, '')), '') IS NULL
                              OR NULLIF(TRIM(COALESCE(s.especialidad_publica, d.especialidad, '')), '') IS NULL
                              OR NULLIF(TRIM(COALESCE(s.ciudad, '')), '') IS NULL
                          )
                    ) AS seo_incompleto,
                    COALESCE(SUM(m.visitas) FILTER (WHERE m.fecha >= CURRENT_DATE - INTERVAL '30 days'), 0) AS visitas_30,
                    COALESCE(SUM(m.clics_whatsapp) FILTER (WHERE m.fecha >= CURRENT_DATE - INTERVAL '30 days'), 0) AS clics_whatsapp_30,
                    COALESCE(SUM(m.clics_agendar) FILTER (WHERE m.fecha >= CURRENT_DATE - INTERVAL '30 days'), 0) AS clics_agenda_30
                FROM SITIOS_MEDICOS s
                JOIN DOCTORES d ON d.correo_doctor = s.correo_doctor
                LEFT JOIN SITIOS_MEDICOS_METRICAS_DIARIAS m ON m.id_sitio = s.id_sitio
                WHERE d.activo = TRUE
            """)
            presencia_metricas.update(cur.fetchone() or {})
            cur.execute("""
                SELECT COUNT(*) = 6 AS disponible
                FROM information_schema.columns
                WHERE table_name = 'radar_eventos_citas'
                  AND column_name IN (
                    'correo_doctor',
                    'tipo_evento',
                    'estado_operativo',
                    'fecha_cita',
                    'liberado_en',
                    'expiracion_apartado'
                  )
            """)
            radar_apartados = cur.fetchone() or {}
            if radar_apartados.get('disponible'):
                cur.execute("""
                    SELECT COUNT(*) AS horarios_recuperados_hoy
                    FROM RADAR_EVENTOS_CITAS r
                    JOIN DOCTORES d ON d.correo_doctor = r.correo_doctor
                    WHERE d.activo = TRUE
                      AND COALESCE(r.tipo_evento, '') = 'APARTADO_TEMPORAL'
                      AND COALESCE(r.estado_operativo, 'activo') IN ('liberado', 'cancelado')
                      AND r.fecha_cita >= NOW()
                      AND COALESCE(r.liberado_en, r.expiracion_apartado) >= CURRENT_DATE
                """)
                presencia_metricas.update(cur.fetchone() or {})

        alertas = []
        nivel_general = 'OK'

        if lotes_vencidos_stock:
            alertas.append({
                'nivel': 'Atención',
                'texto': f'Hay {lotes_vencidos_stock} lotes vencidos con stock disponible.',
                'accion': 'Revisar inventario',
                'url': '/bodega/inventario'
            })

        if pedidos_nuevos:
            alertas.append({
                'nivel': 'Atención',
                'texto': f'Hay {pedidos_nuevos} pedidos nuevos sin preparar.',
                'accion': 'Abrir pedidos',
                'url': '/admin/pedidos'
            })
        if productos_bajo_stock:
            alertas.append({
                'nivel': 'Atención',
                'texto': f'Hay {productos_bajo_stock} productos bajo stock.',
                'accion': 'Ver catálogo',
                'url': '/admin/catalogo'
            })
        if productos_sin_stock:
            alertas.append({
                'nivel': 'Atención',
                'texto': f'Hay {productos_sin_stock} productos activos sin stock.',
                'accion': 'Ver catálogo',
                'url': '/admin/catalogo'
            })
        if lotes_por_caducar:
            alertas.append({
                'nivel': 'Atención',
                'texto': f'Hay {lotes_por_caducar} lotes próximos a caducar.',
                'accion': 'Revisar lotes',
                'url': '/bodega/inventario'
            })
        if int(presencia_metricas.get('dominios_pendientes') or 0):
            alertas.append({
                'nivel': 'Atención',
                'texto': f"Hay {int(presencia_metricas.get('dominios_pendientes') or 0)} páginas médicas con dominio pendiente.",
                'accion': 'Gestionar sitios',
                'url': '/admin/presencia-digital'
            })
        if int(presencia_metricas.get('contenido_pendiente') or 0):
            alertas.append({
                'nivel': 'Atención',
                'texto': f"Hay {int(presencia_metricas.get('contenido_pendiente') or 0)} páginas médicas con contenido pendiente.",
                'accion': 'Completar sitios',
                'url': '/admin/presencia-digital'
            })
        errores_confirmacion_hoy = int(salud_operativa.get('errores_confirmacion_hoy') or 0)
        if fallas_oauth_24h:
            afectados = texto_afectados(fallas_oauth_detalle)
            cuentas = len(fallas_oauth_detalle)
            if cuentas == 1:
                texto_oauth = (
                    f'La cuenta de Google de {afectados} requiere reconexión. '
                    'Se detectó una falla de acceso reciente.'
                )
            else:
                texto_oauth = (
                    f'{cuentas} cuentas de Google requieren revisión: {afectados}.'
                )
            alertas.append({
                'nivel': 'Crítico',
                'texto': texto_oauth,
                'accion': 'Ver sistema',
                'url': '/admin/supervisor'
            })
            nivel_general = 'Crítico'
        if fallas_calendar_24h:
            alertas.append({
                'nivel': 'Crítico',
                'texto': (
                    'Google Calendar presentó fallas recientes para '
                    f'{texto_afectados(fallas_calendar_detalle)}.'
                ),
                'accion': 'Ver sistema',
                'url': '/admin/supervisor'
            })
            nivel_general = 'Crítico'
        if fallas_gmail_24h:
            alertas.append({
                'nivel': 'Crítico',
                'texto': (
                    'Gmail presentó fallas recientes para '
                    f'{texto_afectados(fallas_gmail_detalle)}.'
                ),
                'accion': 'Ver sistema',
                'url': '/admin/supervisor'
            })
            nivel_general = 'Crítico'
        if errores_confirmacion_hoy:
            alertas.append({
                'nivel': 'Atención',
                'texto': f'Hay {errores_confirmacion_hoy} envío(s) de correo no completado(s) por causa técnica.',
                'accion': 'Ver sistema',
                'url': '/admin/supervisor'
            })

        supervisor_no_reciente = (
            not ultimo_supervisor
            or float(ultimo_supervisor.get('horas_desde') or 999) > 18
        )
        if supervisor_no_reciente:
            alertas.append({
                'nivel': 'Atención',
                'texto': 'El supervisor IA no tiene ejecución reciente.',
                'accion': 'Ver supervisor',
                'url': '/admin/supervisor'
            })

        auditoria_job = ultimos_jobs.get('auditoria_calendar')
        if not auditoria_job or not bool(auditoria_job.get('ok') == 'true') or float(auditoria_job.get('horas_desde') or 999) > 2:
            alertas.append({
                'nivel': 'Crítico',
                'texto': 'La auditoría de Calendar no tiene una ejecución reciente y correcta.',
                'accion': 'Ver supervisor',
                'url': '/admin/supervisor'
            })
            nivel_general = 'Crítico'

        if nivel_general != 'Crítico' and alertas:
            nivel_general = 'Atención'

        if nivel_general == 'OK':
            resumen_operativo = 'Operación estable. No hay alertas críticas por ahora.'
        elif nivel_general == 'Crítico':
            resumen_operativo = 'Doko necesita revisión prioritaria. Hay riesgos operativos que conviene revisar primero.'
        else:
            resumen_operativo = 'Doko opera, pero hay pendientes de negocio o plataforma que conviene atender.'

        acciones_hoy = []
        if pedidos_nuevos:
            acciones_hoy.append({'texto': f'Revisar {pedidos_nuevos} pedido(s) nuevo(s)', 'url': '/admin/pedidos'})
        if productos_sin_stock or productos_bajo_stock or lotes_vencidos_stock or lotes_por_caducar:
            acciones_hoy.append({'texto': 'Revisar inventario y lotes', 'url': '/admin/catalogo'})
        if int(presencia_metricas.get('dominios_pendientes') or 0) or int(presencia_metricas.get('contenido_pendiente') or 0):
            acciones_hoy.append({'texto': 'Completar presencia digital', 'url': '/admin/presencia-digital'})
        if fallas_google_oauth_24h or errores_confirmacion_hoy or supervisor_no_reciente or not auditoria_job or not bool(auditoria_job.get('ok') == 'true'):
            acciones_hoy.append({'texto': 'Revisar sistema y agentes', 'url': '/admin/supervisor'})
        if not acciones_hoy:
            acciones_hoy.append({'texto': 'Ver rendimiento médico', 'url': '/admin/doctores'})

        alertas.sort(key=lambda a: 0 if a.get('nivel') == 'Crítico' else 1)
        alertas_total = len(alertas)
        alertas = alertas[:5]

        return render_template(
            'admin/dashboard.html',
            doctores_activos=doctores_activos,
            valor_pedidos_mes=valor_pedidos_mes,
            citas_mes_total=citas_mes_total,
            citas_proximas=citas_proximas,
            citas_pendientes=citas_pendientes,
            pedidos_abiertos=pedidos_abiertos,
            pedidos_nuevos=pedidos_nuevos,
            pedidos_preparando=pedidos_preparando,
            pedidos_en_camino=pedidos_en_camino,
            pedidos_entregados_mes=pedidos_entregados_mes,
            productos_bajo_stock=productos_bajo_stock,
            lotes_vencidos_stock=lotes_vencidos_stock,
            lotes_por_caducar=lotes_por_caducar,
            productos_sin_stock=productos_sin_stock,
            proveedores_activos=proveedores_activos,
            ultimo_supervisor=ultimo_supervisor,
            ultimos_jobs=ultimos_jobs,
            salud_operativa=salud_operativa,
            fallas_google_oauth_24h=fallas_google_oauth_24h,
            fallas_oauth_24h=fallas_oauth_24h,
            fallas_calendar_24h=fallas_calendar_24h,
            fallas_gmail_24h=fallas_gmail_24h,
            datos_paciente_incompletos_24h=datos_paciente_incompletos_24h,
            politicas_confirmacion=politicas_confirmacion,
            rendimiento_doctores_mes=rendimiento_doctores_mes,
            pedidos_nuevos_detalle=pedidos_nuevos_detalle,
            productos_riesgo_detalle=productos_riesgo_detalle,
            lotes_vencidos_detalle=lotes_vencidos_detalle,
            lotes_por_caducar_detalle=lotes_por_caducar_detalle,
            presencia_metricas=presencia_metricas,
            alertas=alertas,
            alertas_total=alertas_total,
            nivel_general=nivel_general,
            resumen_operativo=resumen_operativo,
            acciones_hoy=acciones_hoy[:3],
        )
    finally:
        conn.close()


@admin_bp.route('/admin/confirmacion/<path:correo_doctor>', methods=['POST'])
@requiere_rol('admin')
def actualizar_modo_confirmacion(correo_doctor):
    data = _datos_formulario()
    modo = (data.get('modo_confirmacion') or 'manual').strip()
    permitidos = {'manual', 'confirmar_24h', 'confirmar_48h_cancelar_24h'}
    if modo not in permitidos:
        return jsonify({'ok': False, 'error': 'Modo de confirmación no válido.'}), 400

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE DOCTORES SET modo_confirmacion = %s
            WHERE correo_doctor = %s AND activo = TRUE
        """, (modo, correo_doctor))
        if not cur.rowcount:
            conn.rollback()
            return jsonify({'ok': False, 'error': 'Doctora no encontrada o inactiva.'}), 404
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
            VALUES (%s, %s, %s, %s, %s)
        """, ('CONFIGURACION_CONFIRMACION_DOCTORA', session.get('correo', 'admin'), 'admin',
              json.dumps({'correo_doctor': correo_doctor, 'modo_confirmacion': modo}), request.remote_addr))
        conn.commit()
        return jsonify({'ok': True, 'modo_confirmacion': modo})
    except Exception as exc:
        conn.rollback()
        return jsonify({'ok': False, 'error': str(exc)}), 400
    finally:
        conn.close()

@admin_bp.route('/admin/doctores', methods=['GET', 'POST'])
@requiere_rol('admin')
def doctores():
    """CRUD de Doctores Fundadores."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if request.method == 'POST':
            d = _datos_formulario()
            correo = (d.get('correo') or d.get('correo_doctor') or '').strip()
            nombre = (d.get('nombre') or d.get('nombre_doctor') or '').strip()
            especialidad = (d.get('especialidad') or '').strip() or None
            telefono = (d.get('telefono') or d.get('telefono_consultorio') or '').strip() or None
            id_publico = (d.get('id_publico') or '').strip() or None
            foto_perfil_url = (d.get('foto_perfil_url') or '').strip() or None
            try:
                calendar_booking_url = extraer_calendar_src(d.get('calendar_booking_url')) or None
            except ValueError as e:
                return _respuesta_ajax_o_redirect(
                    ok=False,
                    error=str(e),
                    redirect_endpoint='admin_bp.doctores',
                )
            direccion_consultorio = (d.get('direccion_consultorio') or '').strip() or None
            maps_url = (d.get('maps_url') or '').strip() or None
            medico_fundador = _bool_form(d, 'medico_fundador', False)

            if not correo or not nombre:
                return _respuesta_ajax_o_redirect(
                    ok=False,
                    error='Correo y nombre son obligatorios',
                    redirect_endpoint='admin_bp.doctores',
                )

            try:
                cur.execute("""
                    INSERT INTO DOCTORES (
                        correo_doctor, nombre_doctor, especialidad, telefono_consultorio,
                        id_publico, calendar_booking_url, direccion_consultorio, maps_url, foto_perfil_url, activo
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                """, (
                    correo, nombre, especialidad, telefono, id_publico,
                    calendar_booking_url, direccion_consultorio, maps_url, foto_perfil_url,
                ))
                _actualizar_medico_fundador_sitio(cur, correo, medico_fundador, id_publico)
                cur.execute("""
                    INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle)
                    VALUES (%s, %s, %s, %s)
                """, (
                    'ALTA_DOCTOR',
                    session.get('correo', 'admin'),
                    'admin',
                    json.dumps({'correo_doctor': correo, 'nombre_doctor': nombre, 'id_publico': id_publico}),
                ))
                conn.commit()
            except Exception as e:
                conn.rollback()
                return _respuesta_ajax_o_redirect(
                    ok=False,
                    error=str(e),
                    redirect_endpoint='admin_bp.doctores',
                )

            return _respuesta_ajax_o_redirect(ok=True, redirect_endpoint='admin_bp.doctores')

        cur.execute("""
            SELECT to_regclass('public.sitios_medicos') IS NOT NULL AS tabla,
                   EXISTS (
                       SELECT 1
                       FROM information_schema.columns
                       WHERE table_name = 'sitios_medicos'
                         AND column_name = 'visual_config'
                   ) AS tiene_visual_config
        """)
        sitios_estado = cur.fetchone() or {}
        if sitios_estado.get('tabla') and sitios_estado.get('tiene_visual_config'):
            cur.execute("""
                SELECT d.correo_doctor, d.nombre_doctor, d.especialidad, d.telefono_consultorio,
                       d.id_publico, d.calendar_booking_url, d.direccion_consultorio, d.maps_url,
                       d.foto_perfil_url, d.aseguradoras_aceptadas, d.activo, d.fecha_registro,
                       COALESCE((s.visual_config->>'medico_fundador')::boolean, FALSE) AS medico_fundador
                FROM DOCTORES d
                LEFT JOIN SITIOS_MEDICOS s ON s.correo_doctor = d.correo_doctor
                ORDER BY d.fecha_registro DESC
            """)
        else:
            cur.execute("""
                SELECT correo_doctor, nombre_doctor, especialidad, telefono_consultorio,
                       id_publico, calendar_booking_url, direccion_consultorio, maps_url,
                       foto_perfil_url, aseguradoras_aceptadas, activo, fecha_registro,
                       FALSE AS medico_fundador
                FROM DOCTORES
                ORDER BY fecha_registro DESC
            """)
        doctores_lista = cur.fetchall()
        cur.execute("""
            SELECT d.correo_doctor, d.nombre_doctor, d.modo_confirmacion,
                   COUNT(r.id_radar) AS citas_mes,
                   COUNT(r.id_radar) FILTER (
                       WHERE UPPER(COALESCE(r.estatus_confirmacion, '')) LIKE 'CONFIRM%%'
                          OR UPPER(COALESCE(r.estatus_confirmacion, '')) LIKE 'VERIFIC%%'
                   ) AS confirmadas,
                   COUNT(r.id_radar) FILTER (
                       WHERE UPPER(COALESCE(r.estatus_confirmacion, 'Pendiente')) LIKE 'PEND%%'
                   ) AS pendientes,
                   COUNT(r.id_radar) FILTER (
                       WHERE UPPER(COALESCE(r.estatus_confirmacion, '')) LIKE 'CANCEL%%'
                          OR COALESCE(r.estado_operativo, 'activo') = 'cancelado'
                   ) AS canceladas
            FROM DOCTORES d
            LEFT JOIN RADAR_EVENTOS_CITAS r
              ON r.correo_doctor = d.correo_doctor
             AND r.fecha_cita >= DATE_TRUNC('month', NOW())
             AND r.fecha_cita < DATE_TRUNC('month', NOW()) + INTERVAL '1 month'
             AND COALESCE(r.tipo_evento, 'CITA_PACIENTE') = 'CITA_PACIENTE'
            WHERE d.activo = TRUE
            GROUP BY d.correo_doctor, d.nombre_doctor, d.modo_confirmacion
            ORDER BY citas_mes DESC, d.nombre_doctor
        """)
        rendimiento = []
        for row in cur.fetchall():
            total = int(row.get('citas_mes') or 0)
            row['tasa_confirmacion'] = round((int(row.get('confirmadas') or 0) / total) * 100) if total else 0
            rendimiento.append(row)
        return render_template('admin/doctores.html', doctores=doctores_lista, rendimiento=rendimiento)
    finally:
        conn.close()

@admin_bp.route('/admin/doctores/<path:correo_doctor>/editar', methods=['POST'])
@requiere_rol('admin')
def editar_doctor(correo_doctor):
    d = _datos_formulario()
    try:
        calendar_booking_url = extraer_calendar_src(d.get('calendar_booking_url')) or None
    except ValueError as e:
        return _respuesta_ajax_o_redirect(
            ok=False,
            error=str(e),
            redirect_endpoint='admin_bp.doctores',
        )

    nombre = (d.get('nombre_doctor') or d.get('nombre') or '').strip()
    especialidad = (d.get('especialidad') or '').strip() or None
    telefono = (d.get('telefono_consultorio') or d.get('telefono') or '').strip() or None
    id_publico = (d.get('id_publico') or '').strip() or None
    direccion = (d.get('direccion_consultorio') or '').strip() or None
    maps_url = (d.get('maps_url') or '').strip() or None
    foto = (d.get('foto_perfil_url') or '').strip() or None
    aseguradoras = (d.get('aseguradoras_aceptadas') or '').strip() or None
    medico_fundador = _bool_form(d, 'medico_fundador', False)
    activo_raw = str(d.get('activo', '')).lower()
    activo = activo_raw in ('true', '1', 'on', 'si', 'activo')

    if not nombre:
        return _respuesta_ajax_o_redirect(
            ok=False,
            error='Nombre del doctor es obligatorio',
            redirect_endpoint='admin_bp.doctores',
        )

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE DOCTORES
            SET nombre_doctor = %s,
                especialidad = %s,
                telefono_consultorio = %s,
                id_publico = %s,
                calendar_booking_url = %s,
                direccion_consultorio = %s,
                maps_url = %s,
                foto_perfil_url = %s,
                aseguradoras_aceptadas = %s,
                activo = %s
            WHERE correo_doctor = %s
        """, (
            nombre,
            especialidad,
            telefono,
            id_publico,
            calendar_booking_url,
            direccion,
            maps_url,
            foto,
            aseguradoras,
            activo,
            correo_doctor,
        ))
        if cur.rowcount == 0:
            conn.rollback()
            return _respuesta_ajax_o_redirect(
                ok=False,
                error='Doctor no encontrado',
                redirect_endpoint='admin_bp.doctores',
            )
        _actualizar_medico_fundador_sitio(cur, correo_doctor, medico_fundador, id_publico)

        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            'EDICION_DOCTOR_ADMIN',
            session.get('correo', 'admin'),
            'admin',
            json.dumps({'correo_doctor': correo_doctor, 'id_publico': id_publico}),
            request.remote_addr,
        ))
        conn.commit()
        return _respuesta_ajax_o_redirect(ok=True, redirect_endpoint='admin_bp.doctores')
    except Exception as e:
        conn.rollback()
        return _respuesta_ajax_o_redirect(
            ok=False,
            error=str(e),
            redirect_endpoint='admin_bp.doctores',
        )
    finally:
        conn.close()

@admin_bp.route('/admin/doctores/<correo>/toggle', methods=['POST'])
@requiere_rol('admin')
def toggle_doctor(correo):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE DOCTORES SET activo = NOT activo WHERE correo_doctor = %s", (correo,))
        conn.commit()
        return jsonify({'ok': True})
    finally:
        conn.close()

# UPLOADS BINDADOS (Solo 2 carpetas permitidas aquí. No PDFs. No Documentos)
@admin_bp.route('/admin/upload/doctor-foto', methods=['POST'])
@requiere_rol('admin')
def upload_doctor_foto():
    archivo = request.files.get('file')
    if not archivo: return jsonify({'error': 'No file'}), 400
    try:
        url = subir_archivo(archivo.read(), archivo.filename, 'doctores')
        return jsonify({'ok': True, 'url': url})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@admin_bp.route('/admin/upload/producto-foto', methods=['POST'])
@requiere_rol('admin')
def upload_producto_foto():
    archivo = request.files.get('file')
    if not archivo: return jsonify({'error': 'No file'}), 400
    try:
        url = subir_archivo(archivo.read(), archivo.filename, 'productos')
        return jsonify({'ok': True, 'url': url})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@admin_bp.route('/admin/catalogo/<id_producto>/foto', methods=['POST'])
@requiere_rol('admin')
def upload_catalogo_producto_foto(id_producto):
    archivo = request.files.get('foto') or request.files.get('file')
    if not archivo:
        return jsonify({'ok': False, 'error': 'Seleccione una imagen'}), 400
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT 1
            FROM CAT_PRODUCTOS_MAESTRO
            WHERE id_producto = %s AND estatus_producto = 'activo'
        """, (id_producto,))
        if not cur.fetchone():
            return jsonify({'ok': False, 'error': 'Producto no encontrado o inactivo'}), 404
        url = subir_archivo(archivo.read(), archivo.filename, 'productos')
        cur.execute("""
            UPDATE CAT_PRODUCTOS_MAESTRO
            SET galeria_fotos = COALESCE(galeria_fotos, '[]'::jsonb) || %s::jsonb
            WHERE id_producto = %s
        """, (json.dumps([url]), id_producto))
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            'FOTO_PRODUCTO_CATALOGO',
            session.get('correo', 'admin'),
            'admin',
            json.dumps({'id_producto': id_producto, 'url': url}),
            request.remote_addr,
        ))
        conn.commit()
        return jsonify({'ok': True, 'url': url})
    except Exception as e:
        conn.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 400
    finally:
        conn.close()


# ==============================================================================
# PRESENCIA DIGITAL MEDICA
# ==============================================================================

@admin_bp.route('/admin/presencia-digital', methods=['GET'])
@requiere_rol('admin')
def presencia_digital():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if not _tablas_presencia_disponibles(cur):
            return render_template('admin/presencia_digital.html', migracion_pendiente=True,
                                   sitios=[], doctores=[], sitio_actual=None, metricas={}, dominio=PRESENCIA_BASE_DOMAIN,
                                   checklist=[])

        cur.execute("""
            SELECT d.correo_doctor, d.nombre_doctor, d.especialidad, d.telefono_consultorio,
                   d.foto_perfil_url, d.direccion_consultorio, d.maps_url,
                   d.aseguradoras_aceptadas, d.metodos_pago_aceptados,
                   d.horarios_atencion, d.id_publico, d.color_tema,
                   d.aviso_consultorio, d.aviso_activo, d.aviso_expira_en,
                   d.aviso_visible_portal, d.aviso_visible_chatbot, d.aviso_visible_web
            FROM DOCTORES d
            WHERE d.activo = TRUE
            ORDER BY d.nombre_doctor
        """)
        doctores = cur.fetchall()
        cur.execute("""
            SELECT s.id_sitio, s.correo_doctor, s.subdominio, s.estado, s.estado_dominio, s.plantilla,
                   s.fecha_creacion, d.nombre_doctor, d.especialidad,
                   COALESCE(SUM(m.visitas) FILTER (WHERE m.fecha >= CURRENT_DATE - INTERVAL '30 days'), 0) AS visitas_30,
                   COALESCE(SUM(m.clics_whatsapp) FILTER (WHERE m.fecha >= CURRENT_DATE - INTERVAL '30 days'), 0) AS whatsapp_30,
                   COALESCE(SUM(m.clics_agendar) FILTER (WHERE m.fecha >= CURRENT_DATE - INTERVAL '30 days'), 0) AS agenda_30,
                   COALESCE(SUM(m.clics_maps) FILTER (WHERE m.fecha >= CURRENT_DATE - INTERVAL '30 days'), 0) AS maps_30,
                   COALESCE(SUM(m.clics_telefono) FILTER (WHERE m.fecha >= CURRENT_DATE - INTERVAL '30 days'), 0) AS telefono_30
            FROM SITIOS_MEDICOS s
            JOIN DOCTORES d ON d.correo_doctor = s.correo_doctor
            LEFT JOIN SITIOS_MEDICOS_METRICAS_DIARIAS m ON m.id_sitio = s.id_sitio
            GROUP BY s.id_sitio, d.nombre_doctor, d.especialidad
            ORDER BY s.fecha_creacion DESC
        """)
        sitios = cur.fetchall()
        sitio_actual = None
        sitio_id = (request.args.get('sitio') or '').strip()
        nuevo_sitio = (request.args.get('nuevo') or '').strip() == '1'
        if sitio_id:
            cur.execute("""
                SELECT s.*, d.nombre_doctor, d.especialidad, d.telefono_consultorio,
                       d.foto_perfil_url, d.direccion_consultorio, d.maps_url,
                       d.aseguradoras_aceptadas, d.metodos_pago_aceptados,
                       d.horarios_atencion, d.id_publico, d.aviso_consultorio, d.aviso_activo,
                       d.aviso_expira_en, d.aviso_visible_portal, d.aviso_visible_chatbot,
                       d.aviso_visible_web
                FROM SITIOS_MEDICOS s JOIN DOCTORES d ON d.correo_doctor = s.correo_doctor
                WHERE s.id_sitio = %s
            """, (sitio_id,))
            sitio_actual = cur.fetchone()
            if sitio_actual:
                cur.execute("SELECT * FROM SITIOS_MEDICOS_MEDIA WHERE id_sitio=%s ORDER BY orden, fecha_creacion", (sitio_id,))
                sitio_actual['media'] = cur.fetchall()
                cur.execute("SELECT * FROM SITIOS_MEDICOS_CREDENCIALES WHERE id_sitio=%s ORDER BY orden, fecha_creacion", (sitio_id,))
                sitio_actual['credenciales'] = cur.fetchall()
                cur.execute("SELECT * FROM SITIOS_MEDICOS_REDES WHERE id_sitio=%s ORDER BY orden", (sitio_id,))
                sitio_actual['redes'] = cur.fetchall()
                cur.execute("""
                    SELECT id_faq, palabras_clave, respuesta, orden, activo, categoria
                    FROM FAQ_CHATBOT
                    WHERE id_doctor_app = %s
                    ORDER BY orden ASC, id_faq ASC
                """, (sitio_actual['id_publico'],))
                sitio_actual['faqs'] = cur.fetchall()
                cur.execute("""
                    SELECT id_servicio, nombre_servicio, precio, tipo_precio, descripcion
                    FROM CAT_SERVICIOS_CONSULTORIO
                    WHERE correo_doctor = %s AND activo = TRUE
                    ORDER BY nombre_servicio
                """, (sitio_actual['correo_doctor'],))
                sitio_actual['servicios'] = cur.fetchall()
                cur.execute("""
                    SELECT COALESCE(SUM(visitas),0) AS visitas, COALESCE(SUM(clics_whatsapp),0) AS whatsapp,
                           COALESCE(SUM(clics_agendar),0) AS agenda,
                           COALESCE(SUM(clics_maps),0) AS maps,
                           COALESCE(SUM(clics_telefono),0) AS telefono
                    FROM SITIOS_MEDICOS_METRICAS_DIARIAS WHERE id_sitio=%s AND fecha >= CURRENT_DATE - INTERVAL '30 days'
                """, (sitio_id,))
                metricas = cur.fetchone()
            else:
                metricas = {}
        else:
            metricas = {}
        checklist = _checklist_presencia(sitio_actual)
        return render_template('admin/presencia_digital.html', migracion_pendiente=False,
                               sitios=sitios, doctores=doctores, sitio_actual=sitio_actual, metricas=metricas,
                               dominio=PRESENCIA_BASE_DOMAIN, checklist=checklist)
    finally:
        conn.close()


@admin_bp.route('/admin/presencia-digital/seo-local', methods=['GET'])
@requiere_rol('admin')
def seo_local():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT to_regclass('public.seo_local_rutas') AS tabla")
        tabla_disponible = bool(cur.fetchone()['tabla'])
        rutas = []
        ruta_actual = None
        if tabla_disponible:
            cur.execute("""
                SELECT * FROM SEO_LOCAL_RUTAS
                ORDER BY orden ASC, especialidad ASC, slug ASC
            """)
            rutas = cur.fetchall()
            editar_id = (request.args.get('editar') or '').strip()
            for ruta in rutas:
                ruta['terminos'] = _terminos_seo_local(ruta['especialidad'], ruta.get('terminos_busqueda'))
                from routes.presencia import _obtener_directorio_medico
                ruta['medicos_coincidentes'] = len(_obtener_directorio_medico(ruta['terminos']))
                if editar_id and str(ruta['id_ruta']) == editar_id:
                    ruta_actual = ruta
        rutas_fijas = [
            {'slug': 'medicos-en-tijuana', 'titulo': 'Médicos en Tijuana'},
            {'slug': 'doctores-en-tijuana', 'titulo': 'Doctores en Tijuana'},
            {'slug': 'especialistas-en-tijuana', 'titulo': 'Especialistas en Tijuana'},
            {'slug': 'ginecologia-tijuana', 'titulo': 'Ginecología en Tijuana'},
            {'slug': 'colposcopia-tijuana', 'titulo': 'Colposcopia en Tijuana'},
            {'slug': 'papanicolaou-tijuana', 'titulo': 'Papanicolaou en Tijuana'},
        ]
        return render_template(
            'admin/seo_local.html',
            tabla_disponible=tabla_disponible,
            rutas=rutas,
            ruta_actual=ruta_actual,
            rutas_fijas=rutas_fijas,
            dominio=PRESENCIA_BASE_DOMAIN,
        )
    finally:
        conn.close()


@admin_bp.route('/admin/presencia-digital/seo-local/guardar', methods=['POST'])
@requiere_rol('admin')
def guardar_seo_local():
    d = _datos_formulario()
    try:
        especialidad = _texto(d, 'especialidad')
        ciudad = _texto(d, 'ciudad') or 'Tijuana'
        if not especialidad:
            raise ValueError('Escribe la especialidad o categoría médica.')
        if ciudad.casefold() != 'tijuana':
            raise ValueError('En esta fase las páginas SEO solo pueden publicarse para Tijuana.')
        slug_base = _texto(d, 'slug') or f'{especialidad}-{ciudad}'
        slug = _slug_seo_local(slug_base)
        titulo = _texto(d, 'titulo')
        subtitulo = _texto(d, 'subtitulo')
        descripcion = _texto(d, 'descripcion')
        if not titulo or not subtitulo or not descripcion:
            raise ValueError('Completa título, subtítulo y descripción.')
        if len(slug) > 120 or len(titulo) > 140 or len(subtitulo) > 220 or len(descripcion) > 500:
            raise ValueError('Uno de los textos supera el tamaño permitido.')
        estado = (d.get('estado') or 'BORRADOR').strip().upper()
        if estado not in {'BORRADOR', 'PUBLICADO', 'PAUSADO'}:
            raise ValueError('Estado de publicación no válido.')
        orden = _int_opcional(d, 'orden')
        if orden is None:
            orden = 999
        terminos = _terminos_seo_local(especialidad, d.get('terminos_busqueda'))
        _validar_texto_publicidad_medica(titulo, subtitulo, descripcion, ' '.join(terminos))
        if estado == 'PUBLICADO':
            from routes.presencia import _obtener_directorio_medico
            if not _obtener_directorio_medico(terminos):
                raise ValueError('No se puede publicar: todavía no hay un médico activo y visible que coincida.')
    except (TypeError, ValueError) as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400

    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT to_regclass('public.seo_local_rutas') AS tabla")
        if not cur.fetchone()['tabla']:
            return jsonify({'ok': False, 'error': 'Aplica primero la migración de SEO local.'}), 503
        ruta_id = (d.get('id_ruta') or '').strip()
        valores = (
            slug, especialidad, 'Tijuana', titulo, subtitulo, descripcion,
            json.dumps(terminos, ensure_ascii=False), estado, orden,
        )
        if ruta_id:
            cur.execute("""
                UPDATE SEO_LOCAL_RUTAS
                SET slug=%s, especialidad=%s, ciudad=%s, titulo=%s, subtitulo=%s,
                    descripcion=%s, terminos_busqueda=%s::jsonb, estado=%s, orden=%s,
                    actualizado_en=NOW()
                WHERE id_ruta=%s
                RETURNING id_ruta
            """, valores + (ruta_id,))
        else:
            ruta_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO SEO_LOCAL_RUTAS
                    (id_ruta, slug, especialidad, ciudad, titulo, subtitulo, descripcion,
                     terminos_busqueda, estado, orden)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                RETURNING id_ruta
            """, (ruta_id,) + valores)
        guardada = cur.fetchone()
        if not guardada:
            return jsonify({'ok': False, 'error': 'No se encontró la ruta para editar.'}), 404
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            'SEO_LOCAL_CONFIGURADO', session.get('correo', 'admin'), 'admin',
            json.dumps({'id_ruta': str(guardada['id_ruta']), 'slug': slug, 'estado': estado}),
            request.remote_addr,
        ))
        conn.commit()
        return jsonify({'ok': True, 'id_ruta': str(guardada['id_ruta'])})
    except Exception as exc:
        conn.rollback()
        if getattr(exc, 'pgcode', None) == '23505':
            return jsonify({'ok': False, 'error': 'Ya existe una página con esa ruta.'}), 409
        return jsonify({'ok': False, 'error': str(exc)}), 400
    finally:
        conn.close()


@admin_bp.route('/admin/presencia-digital/seo-local/<id_ruta>/preview', methods=['GET'])
@requiere_rol('admin')
def preview_seo_local(id_ruta):
    from routes.presencia import render_seo_local_preview_admin
    return render_seo_local_preview_admin(id_ruta)


@admin_bp.route('/admin/presencia-digital/<id_sitio>/preview', methods=['GET'])
@requiere_rol('admin')
def preview_sitio_medico(id_sitio):
    from routes.presencia import render_sitio_preview_admin
    return render_sitio_preview_admin(id_sitio)


@admin_bp.route('/admin/presencia-digital/<id_sitio>/eliminar-borrador', methods=['POST'])
@requiere_rol('admin')
def eliminar_borrador_sitio_medico(id_sitio):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            DELETE FROM SITIOS_MEDICOS
            WHERE id_sitio = %s AND estado = 'BORRADOR'
            RETURNING id_sitio, correo_doctor, subdominio
        """, (id_sitio,))
        sitio = cur.fetchone()
        if not sitio:
            return jsonify({'ok': False, 'error': 'Solo se pueden eliminar sitios en borrador.'}), 400
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
            VALUES (%s, %s, %s, %s, %s)
        """, ('SITIO_MEDICO_BORRADOR_ELIMINADO', session.get('correo', 'admin'), 'admin',
              json.dumps({'id_sitio': str(sitio['id_sitio']), 'correo_doctor': sitio['correo_doctor'], 'subdominio': sitio['subdominio']}), request.remote_addr))
        conn.commit()
        return jsonify({'ok': True})
    except Exception as exc:
        conn.rollback()
        return jsonify({'ok': False, 'error': str(exc)}), 400
    finally:
        conn.close()


@admin_bp.route('/admin/presencia-digital/sitio', methods=['POST'])
@requiere_rol('admin')
def guardar_sitio_medico():
    d = _datos_formulario()
    try:
        subdominio = _subdominio_valido(d.get('subdominio'))
        portada = _url_publica_valida(d.get('portada_url'), 'La portada')
        logo = _url_publica_valida(d.get('logo_url'), 'El logo')
        og_image = _url_publica_valida(d.get('og_image'), 'La imagen Open Graph')
        destino_boton = _url_publica_valida(d.get('destino_boton_principal'), 'El destino del botón principal')
        estado = (d.get('estado') or 'BORRADOR').upper()
        estado_dominio = (d.get('estado_dominio') or 'PENDIENTE_DOMINIO').upper()
        plantilla = (d.get('plantilla') or 'clinica_clara').strip()
        if (estado not in {'BORRADOR', 'PUBLICADO', 'PAUSADO'}
                or estado_dominio not in {'PENDIENTE_DOMINIO', 'CONFIGURADO', 'VERIFICADO', 'ERROR'}
                or plantilla not in {'clinica_clara', 'especialista_editorial', 'consulta_moderna'}):
            raise ValueError('Configuración de publicación no válida.')
        _validar_texto_publicidad_medica(
            d.get('titulo_seo'), d.get('descripcion_seo'), d.get('biografia'),
            d.get('biografia_corta'), d.get('biografia_larga'), d.get('hero_titulo'),
            d.get('hero_subtitulo'), d.get('hero_texto_confianza'), d.get('frase_destacada'),
            d.get('aviso_consultorio')
        )
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400

    correo_doctor = (d.get('correo_doctor') or '').strip().lower()
    if not correo_doctor:
        return jsonify({'ok': False, 'error': 'Selecciona una doctora.'}), 400
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if not _tablas_presencia_disponibles(cur):
            return jsonify({'ok': False, 'error': 'Aplica primero la migración de Presencia Digital.'}), 503
        cur.execute("SELECT correo_doctor, direccion_consultorio, id_publico, nombre_doctor, especialidad FROM DOCTORES WHERE correo_doctor=%s AND activo=TRUE", (correo_doctor,))
        doctor_publicacion = cur.fetchone()
        if not doctor_publicacion:
            return jsonify({'ok': False, 'error': 'La doctora no está activa.'}), 404
        cedula_profesional = (d.get('cedula_profesional') or '').strip() or None
        cedula_especialidad = (d.get('cedula_especialidad') or '').strip() or None
        institucion_titulo = (d.get('institucion_titulo') or '').strip() or None
        aviso_publicidad = (d.get('aviso_publicidad_cofepris') or '').strip() or None
        if estado == 'PUBLICADO':
            faltantes = []
            if not doctor_publicacion.get('id_publico'):
                faltantes.append('Portal Doko / ID público')
            if not (_texto(d, 'nombre_clinica_publico') or doctor_publicacion.get('nombre_doctor')):
                faltantes.append('nombre público')
            if not (_texto(d, 'especialidad_publica') or doctor_publicacion.get('especialidad')):
                faltantes.append('especialidad')
            if not _texto(d, 'ciudad'):
                faltantes.append('ciudad')
            if not _texto(d, 'titulo_seo'):
                faltantes.append('título SEO')
            if not _texto(d, 'descripcion_seo'):
                faltantes.append('descripción SEO')
            if not portada:
                faltantes.append('sub portada')
            if not _bool_form(d, 'mostrar_agenda', True):
                faltantes.append('botón Agendar activo')
            if not cedula_profesional:
                faltantes.append('cédula profesional')
            if not cedula_especialidad:
                faltantes.append('cédula de especialidad')
            if not institucion_titulo:
                faltantes.append('institución que expidió el título')
            if not doctor_publicacion.get('direccion_consultorio'):
                faltantes.append('dirección del consultorio')
            if faltantes:
                return jsonify({'ok': False, 'error': 'Para publicar faltan datos COFEPRIS: ' + ', '.join(faltantes)}), 400
        estilos_validos = {'foto_completa', 'foto_contain', 'emblema_redondo', 'emblema_suave'}
        tamanos_validos = {'compacto', 'normal', 'grande'}
        decoraciones_validas = {'ninguna', 'lavanda', 'cerezos', 'flores'}
        temas_validos = {'marino', 'lila', 'sakura', 'verde', 'turquesa', 'vino'}
        hero_image_style = (d.get('hero_image_style') or 'foto_completa').strip()
        hero_image_size = (d.get('hero_image_size') or 'normal').strip()
        hero_decoration = (d.get('hero_decoration') or 'ninguna').strip()
        tema_visual = (d.get('tema_visual') or 'marino').strip()
        if hero_image_style not in estilos_validos:
            hero_image_style = 'foto_completa'
        if hero_image_size not in tamanos_validos:
            hero_image_size = 'normal'
        if hero_decoration not in decoraciones_validas:
            hero_decoration = 'ninguna'
        if tema_visual not in temas_validos:
            tema_visual = 'marino'
        visual_config = {
            'tema_visual': tema_visual,
            'hero_image_style': hero_image_style,
            'hero_image_size': hero_image_size,
            'hero_decoration': hero_decoration,
            'visible_en_directorio': _bool_form(d, 'visible_en_directorio', True),
            'destacado_directorio': _bool_form(d, 'destacado_directorio', False),
            'medico_fundador': _bool_form(d, 'medico_fundador', False),
            'orden_directorio': _int_opcional(d, 'orden_directorio'),
            'servicios_destacados_directorio': _texto(d, 'servicios_destacados_directorio') or '',
        }
        sitio_id = (d.get('id_sitio') or '').strip()
        fecha_publicacion_sql = ", fecha_publicacion = COALESCE(fecha_publicacion, NOW())" if estado == 'PUBLICADO' else ""
        valores = (
            subdominio, estado, estado_dominio, plantilla, _texto(d, 'titulo_seo'),
            _texto(d, 'descripcion_seo'), _texto(d, 'biografia'),
            portada, logo, _texto(d, 'whatsapp_numero'),
            cedula_profesional, cedula_especialidad, institucion_titulo, aviso_publicidad,
            _texto(d, 'nombre_clinica_publico'), _texto(d, 'especialidad_publica'), _texto(d, 'ciudad') or 'Tijuana',
            _texto(d, 'estado_region'), _texto(d, 'color_secundario'), _texto(d, 'hero_titulo'),
            _texto(d, 'hero_subtitulo'), _texto(d, 'hero_texto_confianza'),
            _texto(d, 'texto_boton_principal') or 'Agendar cita', destino_boton,
            _texto(d, 'texto_boton_whatsapp') or 'Enviar WhatsApp',
            _bool_form(d, 'mostrar_whatsapp', True), _bool_form(d, 'mostrar_agenda', True),
            _texto(d, 'biografia_corta'), _texto(d, 'biografia_larga'), _texto(d, 'enfoque_atencion'),
            _int_opcional(d, 'anios_experiencia'), _texto(d, 'formacion_resumida'), _texto(d, 'frase_destacada'),
            _texto(d, 'firma_visible'), _texto(d, 'og_title'), _texto(d, 'og_description'), og_image,
            _texto(d, 'canonical_url'), _texto(d, 'keywords_internas'), _bool_form(d, 'indexable', False),
            _bool_form(d, 'schema_medico_activo', True), _bool_form(d, 'faq_schema_activo', True),
            _bool_form(d, 'mostrar_pagos', True), _bool_form(d, 'mostrar_aseguradoras', True),
            _texto(d, 'texto_pagos'), _texto(d, 'texto_aseguradoras'), _texto(d, 'estacionamiento'),
            _texto(d, 'instrucciones_llegada'), json.dumps(visual_config),
            correo_doctor,
        )
        if sitio_id:
            cur.execute(f"""
                UPDATE SITIOS_MEDICOS SET subdominio=%s, estado=%s, estado_dominio=%s, plantilla=%s, titulo_seo=%s,
                    descripcion_seo=%s, biografia=%s, portada_url=%s, logo_url=%s, whatsapp_numero=%s,
                    cedula_profesional=%s, cedula_especialidad=%s, institucion_titulo=%s,
                    aviso_publicidad_cofepris=%s,
                    nombre_clinica_publico=%s, especialidad_publica=%s, ciudad=%s, estado_region=%s,
                    color_secundario=%s, hero_titulo=%s, hero_subtitulo=%s, hero_texto_confianza=%s,
                    texto_boton_principal=%s, destino_boton_principal=%s, texto_boton_whatsapp=%s,
                    mostrar_whatsapp=%s, mostrar_agenda=%s, biografia_corta=%s, biografia_larga=%s,
                    enfoque_atencion=%s, anios_experiencia=%s, formacion_resumida=%s,
                    frase_destacada=%s, firma_visible=%s, og_title=%s, og_description=%s, og_image=%s,
                    canonical_url=%s, keywords_internas=%s, indexable=%s, schema_medico_activo=%s,
                    faq_schema_activo=%s, mostrar_pagos=%s, mostrar_aseguradoras=%s, texto_pagos=%s,
                    texto_aseguradoras=%s, estacionamiento=%s, instrucciones_llegada=%s,
                    visual_config=%s,
                    actualizado_en=NOW()
                    {fecha_publicacion_sql}
                WHERE id_sitio=%s AND correo_doctor=%s
                RETURNING id_sitio
            """, valores[:-1] + (sitio_id, correo_doctor))
        else:
            nuevo_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO SITIOS_MEDICOS
                    (id_sitio, correo_doctor, subdominio, estado, estado_dominio, plantilla, titulo_seo,
                     descripcion_seo, biografia, portada_url, logo_url, whatsapp_numero,
                     cedula_profesional, cedula_especialidad, institucion_titulo, aviso_publicidad_cofepris,
                     nombre_clinica_publico, especialidad_publica, ciudad, estado_region, color_secundario,
                     hero_titulo, hero_subtitulo, hero_texto_confianza, texto_boton_principal,
                     destino_boton_principal, texto_boton_whatsapp, mostrar_whatsapp, mostrar_agenda,
                     biografia_corta, biografia_larga, enfoque_atencion, anios_experiencia,
                     formacion_resumida, frase_destacada, firma_visible, og_title, og_description,
                     og_image, canonical_url, keywords_internas, indexable, schema_medico_activo,
                     faq_schema_activo, mostrar_pagos, mostrar_aseguradoras, texto_pagos,
                     texto_aseguradoras, estacionamiento, instrucciones_llegada, visual_config,
                     fecha_publicacion)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, CASE WHEN %s = 'PUBLICADO' THEN NOW() ELSE NULL END)
                RETURNING id_sitio
            """, (nuevo_id, correo_doctor) + valores[:-1] + (estado,))
        sitio = cur.fetchone()
        if not sitio:
            conn.rollback()
            return jsonify({'ok': False, 'error': 'No se encontró el sitio para editar.'}), 404
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
            VALUES (%s, %s, %s, %s, %s)
        """, ('CONFIGURACION_SITIO_MEDICO', session.get('correo', 'admin'), 'admin',
              json.dumps({'id_sitio': str(sitio['id_sitio']), 'correo_doctor': correo_doctor, 'estado': estado}), request.remote_addr))
        conn.commit()
        return jsonify({'ok': True, 'id_sitio': str(sitio['id_sitio'])})
    except Exception as exc:
        conn.rollback()
        return jsonify({'ok': False, 'error': str(exc)}), 400
    finally:
        conn.close()


@admin_bp.route('/admin/presencia-digital/media', methods=['POST'])
@requiere_rol('admin')
def agregar_media_sitio():
    archivos = request.files.getlist('file')
    archivo = archivos[0] if archivos else None
    sitio_id = (request.form.get('id_sitio') or '').strip()
    tipo = (request.form.get('tipo') or 'GALERIA').upper()
    tipos_media = {
        'GALERIA', 'CONSULTORIO', 'RECEPCION', 'EQUIPO', 'FACHADA',
        'ESTACIONAMIENTO', 'RECONOCIMIENTO', 'CERTIFICACION',
        'DIPLOMA', 'CEDULA', 'ASOCIACION', 'OTRO'
    }
    if not archivo or not sitio_id or tipo not in tipos_media:
        return jsonify({'ok': False, 'error': 'Imagen, sitio y tipo son obligatorios.'}), 400
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM SITIOS_MEDICOS WHERE id_sitio=%s", (sitio_id,))
        if not cur.fetchone():
            return jsonify({'ok': False, 'error': 'Sitio no encontrado.'}), 404
        urls = []
        base_orden = int(request.form.get('orden') or 0)
        for indice, item in enumerate(archivos):
            url = subir_archivo(item.read(), item.filename, 'fotosweb')
            urls.append(url)
            cur.execute("""
                INSERT INTO SITIOS_MEDICOS_MEDIA (id_media, id_sitio, tipo, url, texto_alternativo, titulo, descripcion, orden)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (str(uuid.uuid4()), sitio_id, tipo, url,
                  (request.form.get('texto_alternativo') or '').strip() or None,
                  (request.form.get('titulo') or '').strip() or None,
                  (request.form.get('descripcion') or '').strip() or None,
                  base_orden + indice))
        conn.commit()
        return jsonify({'ok': True, 'url': urls[0], 'urls': urls, 'count': len(urls)})
    except Exception as exc:
        conn.rollback()
        return jsonify({'ok': False, 'error': str(exc)}), 400
    finally:
        conn.close()


@admin_bp.route('/admin/presencia-digital/media/<id_media>/quitar', methods=['POST'])
@requiere_rol('admin')
def quitar_media_sitio(id_media):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            UPDATE SITIOS_MEDICOS_MEDIA
            SET activo = FALSE
            WHERE id_media = %s
            RETURNING id_media, id_sitio
        """, (id_media,))
        media = cur.fetchone()
        if not media:
            conn.rollback()
            return jsonify({'ok': False, 'error': 'Foto no encontrada.'}), 404
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
            VALUES (%s, %s, %s, %s, %s)
        """, ('MEDIA_SITIO_MEDICO_QUITADA', session.get('correo', 'admin'), 'admin',
              json.dumps({'id_media': str(media['id_media']), 'id_sitio': str(media['id_sitio'])}), request.remote_addr))
        conn.commit()
        return jsonify({'ok': True})
    except Exception as exc:
        conn.rollback()
        return jsonify({'ok': False, 'error': str(exc)}), 400
    finally:
        conn.close()


@admin_bp.route('/admin/presencia-digital/asset', methods=['POST'])
@requiere_rol('admin')
def subir_asset_sitio_medico():
    archivo = request.files.get('file')
    tipo = (request.form.get('tipo') or '').strip().upper()
    if tipo == 'SUBPORTADA':
        tipo = 'PORTADA'
    if not archivo or tipo not in {'PORTADA', 'LOGO'}:
        return jsonify({'ok': False, 'error': 'Selecciona una imagen de sub portada o logo.'}), 400
    try:
        url = subir_archivo(archivo.read(), archivo.filename, 'fotosweb')
        return jsonify({'ok': True, 'url': url})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400


@admin_bp.route('/admin/presencia-digital/credencial', methods=['POST'])
@requiere_rol('admin')
def agregar_credencial_sitio():
    d = _datos_formulario()
    archivo = request.files.get('file') or request.files.get('imagen')
    tipo = (d.get('tipo') or '').upper()
    if tipo not in {'CERTIFICACION', 'RECONOCIMIENTO', 'DIPLOMA', 'ASOCIACION', 'CEDULA'} or not d.get('id_sitio'):
        return jsonify({'ok': False, 'error': 'Completa el tipo y sitio.'}), 400
    conn = get_connection()
    try:
        cur = conn.cursor()
        imagen_url = None
        if archivo and archivo.filename:
            imagen_url = subir_archivo(archivo.read(), archivo.filename, 'fotosweb')
        titulo = (d.get('titulo') or '').strip()
        if not titulo:
            titulo = {
                'CERTIFICACION': 'Certificación',
                'RECONOCIMIENTO': 'Reconocimiento',
                'DIPLOMA': 'Diploma',
                'ASOCIACION': 'Asociación',
                'CEDULA': 'Cédula profesional',
            }.get(tipo, 'Credencial profesional')
        cur.execute("""
            INSERT INTO SITIOS_MEDICOS_CREDENCIALES
                (id_credencial, id_sitio, tipo, titulo, institucion, descripcion, imagen_url, texto_alternativo, orden)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (str(uuid.uuid4()), d['id_sitio'], tipo, titulo,
              (d.get('institucion') or '').strip() or None, (d.get('descripcion') or '').strip() or None,
              imagen_url, (d.get('texto_alternativo') or '').strip() or None,
              int(d.get('orden') or 0)))
        conn.commit()
        return jsonify({'ok': True})
    except Exception as exc:
        conn.rollback()
        return jsonify({'ok': False, 'error': str(exc)}), 400
    finally:
        conn.close()


@admin_bp.route('/admin/presencia-digital/credencial/<id_credencial>/quitar', methods=['POST'])
@requiere_rol('admin')
def quitar_credencial_sitio(id_credencial):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            UPDATE SITIOS_MEDICOS_CREDENCIALES
            SET activo = FALSE
            WHERE id_credencial = %s
            RETURNING id_credencial, id_sitio
        """, (id_credencial,))
        credencial = cur.fetchone()
        if not credencial:
            conn.rollback()
            return jsonify({'ok': False, 'error': 'Credencial no encontrada.'}), 404
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
            VALUES (%s, %s, %s, %s, %s)
        """, ('CREDENCIAL_SITIO_MEDICO_QUITADA', session.get('correo', 'admin'), 'admin',
              json.dumps({
                  'id_credencial': str(credencial['id_credencial']),
                  'id_sitio': str(credencial['id_sitio']),
              }), request.remote_addr))
        conn.commit()
        return jsonify({'ok': True})
    except Exception as exc:
        conn.rollback()
        return jsonify({'ok': False, 'error': str(exc)}), 400
    finally:
        conn.close()


@admin_bp.route('/admin/presencia-digital/red', methods=['POST'])
@requiere_rol('admin')
def agregar_red_sitio():
    d = _datos_formulario()
    red = (d.get('red') or '').upper()
    try:
        url = _url_publica_valida(d.get('url'), 'La red social')
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    if red not in {'INSTAGRAM', 'FACEBOOK', 'TIKTOK', 'YOUTUBE', 'LINKEDIN', 'WEB'} or not d.get('id_sitio'):
        return jsonify({'ok': False, 'error': 'Completa la red y el sitio.'}), 400
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO SITIOS_MEDICOS_REDES (id_red, id_sitio, red, url, orden)
            VALUES (%s, %s, %s, %s, %s)
        """, (str(uuid.uuid4()), d['id_sitio'], red, url, int(d.get('orden') or 0)))
        conn.commit()
        return jsonify({'ok': True})
    except Exception as exc:
        conn.rollback()
        return jsonify({'ok': False, 'error': str(exc)}), 400
    finally:
        conn.close()


@admin_bp.route('/admin/presencia-digital/educacion', methods=['POST'])
@requiere_rol('admin')
def agregar_educacion_paciente():
    d = _datos_formulario()
    sitio_id = (d.get('id_sitio') or '').strip()
    pregunta = (d.get('palabras_clave') or d.get('pregunta') or '').strip()
    respuesta = (d.get('respuesta') or '').strip()
    categoria = (d.get('categoria') or 'EDUCACION').strip().upper()[:40]
    orden = int(d.get('orden') or 0)
    if not sitio_id or not pregunta or not respuesta:
        return jsonify({'ok': False, 'error': 'Completa tema, respuesta y sitio.'}), 400
    try:
        _validar_texto_publicidad_medica(pregunta, respuesta)
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT s.id_sitio, d.id_publico, s.correo_doctor
            FROM SITIOS_MEDICOS s
            JOIN DOCTORES d ON d.correo_doctor = s.correo_doctor
            WHERE s.id_sitio = %s AND d.activo = TRUE
        """, (sitio_id,))
        sitio = cur.fetchone()
        if not sitio or not sitio.get('id_publico'):
            return jsonify({'ok': False, 'error': 'El sitio necesita una doctora activa con ID público.'}), 404
        cur.execute("""
            INSERT INTO FAQ_CHATBOT
                (id_faq, id_doctor_app, palabras_clave, respuesta, orden, activo, categoria, visible_en_pagina, visible_en_chatbot)
            VALUES (%s, %s, %s, %s, %s, TRUE, %s, TRUE, TRUE)
        """, (str(uuid.uuid4()), sitio['id_publico'], pregunta, respuesta, orden, categoria))
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
            VALUES (%s, %s, %s, %s, %s)
        """, ('EDUCACION_PACIENTE_SITIO', session.get('correo', 'admin'), 'admin',
              json.dumps({'id_sitio': str(sitio['id_sitio']), 'correo_doctor': sitio['correo_doctor']}), request.remote_addr))
        conn.commit()
        return jsonify({'ok': True})
    except Exception as exc:
        conn.rollback()
        return jsonify({'ok': False, 'error': str(exc)}), 400
    finally:
        conn.close()


@admin_bp.route('/admin/presencia-digital/educacion/<id_faq>/quitar', methods=['POST'])
@requiere_rol('admin')
def quitar_educacion_paciente(id_faq):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE FAQ_CHATBOT SET activo = FALSE WHERE id_faq = %s", (id_faq,))
        if cur.rowcount == 0:
            conn.rollback()
            return jsonify({'ok': False, 'error': 'Tema educativo no encontrado.'}), 404
        conn.commit()
        return jsonify({'ok': True})
    except Exception as exc:
        conn.rollback()
        return jsonify({'ok': False, 'error': str(exc)}), 400
    finally:
        conn.close()


# Presencia digital no registra pagos ni suscripciones en Doko.
# ==============================================================================
# BLOQUE 9.2 — CATÁLOGO, PEDIDOS Y USUARIOS
# ==============================================================================

@admin_bp.route('/admin/catalogo', methods=['GET', 'POST'])
@requiere_rol('admin')
def catalogo():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if request.method == 'POST':
            d = _datos_formulario()
            nombre = (d.get('nombre') or d.get('nombre_comercial') or '').strip()
            descripcion = (d.get('descripcion') or d.get('descripcion_suffy') or '').strip() or None
            precio_raw = d.get('precio_venta') or ''

            if not nombre or not str(precio_raw).strip():
                return jsonify({'ok': False, 'error': 'Nombre y precio de venta son obligatorios'}), 400

            try:
                precio_venta = float(precio_raw)
            except (TypeError, ValueError):
                return jsonify({'ok': False, 'error': 'Precio de venta inválido'}), 400

            estatus_producto = (d.get('estatus_producto') or 'activo').strip() or 'activo'
            cur.execute("""
                INSERT INTO CAT_PRODUCTOS_MAESTRO (nombre_comercial, descripcion, precio_venta, estatus_producto)
                VALUES (%s, %s, %s, %s) RETURNING id_producto
            """, (nombre, descripcion, precio_venta, estatus_producto))
            id_producto = cur.fetchone()['id_producto']
            conn.commit()
            return jsonify({'ok': True, 'id_producto': str(id_producto)})

        cur.execute("SELECT * FROM CAT_PRODUCTOS_MAESTRO WHERE estatus_producto = 'activo' ORDER BY nombre_comercial")
        return render_template('admin/catalogo.html', productos=cur.fetchall())
    finally:
        conn.close()

@admin_bp.route('/admin/catalogo/<id_producto>', methods=['DELETE'])
@requiere_rol('admin')
def eliminar_producto(id_producto):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE CAT_PRODUCTOS_MAESTRO SET estatus_producto = 'inactivo' WHERE id_producto = %s", (id_producto,))
        conn.commit()
        return jsonify({'ok': True})
    finally:
        conn.close()

@admin_bp.route('/admin/pedidos', methods=['GET'])
@requiere_rol('admin')
def pedidos():
    """Kanban de pedidos."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT vpe.*, d.nombre_doctor, r.nombre AS nombre_repartidor
            FROM VENTAS_PEDIDOS_ELITE vpe
            JOIN DOCTORES d ON vpe.correo_doctor = d.correo_doctor
            LEFT JOIN USUARIOS_INTERNOS r ON vpe.id_repartidor = r.id_usuario::text
            ORDER BY vpe.fecha_pedido DESC
        """)
        pedidos_lista = cur.fetchall()
        cur.execute("""
            SELECT id_usuario, nombre, correo
            FROM USUARIOS_INTERNOS
            WHERE rol = 'repartidor' AND activo = TRUE
            ORDER BY nombre ASC
        """)
        repartidores = cur.fetchall()
        return render_template('admin/pedidos.html', pedidos=pedidos_lista, repartidores=repartidores)
    finally:
        conn.close()

@admin_bp.route('/admin/pedidos/<id_pedido>/mover', methods=['POST'])
@requiere_rol('admin')
def mover_pedido(id_pedido):
    """Mueve estatus y asigna repartidor cuando pasa a en_camino."""
    d = request.json or {}
    nuevo_estatus = d.get('estatus_entrega')
    id_repartidor = d.get('id_repartidor')
    if nuevo_estatus != 'en_camino':
        return jsonify({'ok': False, 'error': 'estatus_invalido'}), 400
    if not id_repartidor:
        return jsonify({'ok': False, 'error': 'repartidor_requerido'}), 400

    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id_pedido, estatus_entrega
            FROM VENTAS_PEDIDOS_ELITE
            WHERE id_pedido = %s
            FOR UPDATE
        """, (id_pedido,))
        pedido = cur.fetchone()
        if not pedido:
            return jsonify({'ok': False, 'error': 'pedido_no_encontrado'}), 404
        if pedido['estatus_entrega'] != 'preparando':
            return jsonify({'ok': False, 'error': 'pedido_debe_estar_preparando'}), 409

        cur.execute("""
            SELECT id_usuario
            FROM USUARIOS_INTERNOS
            WHERE id_usuario::text = %s AND rol = 'repartidor' AND activo = TRUE
        """, (id_repartidor,))
        if not cur.fetchone():
            return jsonify({'ok': False, 'error': 'repartidor_invalido'}), 400

        cur.execute("""
            UPDATE VENTAS_PEDIDOS_ELITE
            SET estatus_entrega = %s,
                id_repartidor = %s,
                hora_salida = NOW()
            WHERE id_pedido = %s
        """, (nuevo_estatus, id_repartidor, id_pedido))
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
            VALUES ('PEDIDO_MOVIDO', %s, 'admin', %s, %s)
        """, (
            session.get('correo', 'admin'),
            json.dumps({
                'id_pedido': str(id_pedido),
                'estatus_anterior': pedido['estatus_entrega'],
                'estatus_nuevo': nuevo_estatus,
                'id_repartidor': str(id_repartidor) if id_repartidor else None,
            }),
            request.remote_addr,
        ))
        conn.commit()

        if nuevo_estatus == 'en_camino':
            threading.Thread(
                target=AgenteReparto().ejecutar,
                args=(str(id_repartidor),),
                daemon=True,
            ).start()

        return jsonify({'ok': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 400
    finally:
        conn.close()


@admin_bp.route('/admin/pedidos/<id_pedido>/cancelar', methods=['POST'])
@requiere_rol('admin')
def cancelar_pedido(id_pedido):
    """Cancela pedidos nuevos sin tocar inventario ni reparto."""
    d = request.json or {}
    motivo = (d.get('motivo') or '').strip() or None
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id_pedido, estatus_entrega
            FROM VENTAS_PEDIDOS_ELITE
            WHERE id_pedido = %s
            FOR UPDATE
        """, (id_pedido,))
        pedido = cur.fetchone()
        if not pedido:
            return jsonify({'ok': False, 'error': 'pedido_no_encontrado'}), 404
        estado_actual = str(pedido['estatus_entrega'] or '').strip().lower()
        if estado_actual not in ('pendiente', 'nuevo'):
            return jsonify({
                'ok': False,
                'error': 'Solo se pueden cancelar pedidos nuevos. Los pedidos preparados o en ruta requieren revisión manual.'
            }), 409

        cur.execute("""
            UPDATE VENTAS_PEDIDOS_ELITE
            SET estatus_entrega = 'cancelado'
            WHERE id_pedido = %s
        """, (id_pedido,))
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
            VALUES ('PEDIDO_CANCELADO_ADMIN', %s, 'admin', %s, %s)
        """, (
            session.get('correo', 'admin'),
            json.dumps({
                'id_pedido': str(id_pedido),
                'estatus_anterior': pedido['estatus_entrega'],
                'estatus_nuevo': 'cancelado',
                'motivo': motivo,
            }),
            request.remote_addr,
        ))
        conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 400
    finally:
        conn.close()
@admin_bp.route('/admin/usuarios', methods=['GET', 'POST'])
@requiere_rol('admin')
def usuarios():
    from werkzeug.security import generate_password_hash
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if request.method == 'POST':
            d = _datos_formulario()
            nombre = (d.get('nombre') or '').strip()
            correo = (d.get('correo') or '').strip()
            password = d.get('password') or ''
            rol = (d.get('rol') or '').strip()
            doctoras_asignadas = d.get('doctoras') or []
            if isinstance(doctoras_asignadas, str):
                doctoras_asignadas = [doctoras_asignadas]

            if not nombre or not correo or not password or not rol:
                return jsonify({'ok': False, 'error': 'Todos los campos son obligatorios'}), 400
            if rol == 'asistente' and not doctoras_asignadas:
                return jsonify({'ok': False, 'error': 'Asigna al menos una doctora a la asistente'}), 400

            hash_pass = generate_password_hash(password)
            cur.execute("""
                INSERT INTO USUARIOS_INTERNOS (nombre, correo, password_hash, rol)
                VALUES (%s, %s, %s, %s)
                RETURNING id_usuario
            """, (nombre, correo, hash_pass, rol))
            usuario_nuevo = cur.fetchone()
            if rol == 'asistente':
                id_usuario_nuevo = str(usuario_nuevo['id_usuario'])
                for correo_doctor in doctoras_asignadas:
                    cur.execute("""
                        INSERT INTO ASISTENTES_DOCTORES (id_usuario, correo_doctor, asignado_por)
                        SELECT %s, correo_doctor, %s
                        FROM DOCTORES
                        WHERE correo_doctor = %s AND activo = TRUE
                        ON CONFLICT (id_usuario, correo_doctor) DO NOTHING
                    """, (id_usuario_nuevo, session.get('correo', 'admin'), correo_doctor))
            conn.commit()
            return jsonify({'ok': True})

        cur.execute("SELECT id_usuario, nombre, correo, rol, activo, fecha_alta FROM USUARIOS_INTERNOS ORDER BY fecha_alta DESC")
        usuarios_lista = cur.fetchall()
        cur.execute("""
            SELECT correo_doctor, nombre_doctor, especialidad
            FROM DOCTORES
            WHERE activo = TRUE
            ORDER BY nombre_doctor
        """)
        doctores = cur.fetchall()
        cur.execute("""
            SELECT ad.id_usuario, ad.correo_doctor, d.nombre_doctor
            FROM ASISTENTES_DOCTORES ad
            JOIN DOCTORES d ON d.correo_doctor = ad.correo_doctor
            ORDER BY d.nombre_doctor
        """)
        asignaciones = {}
        for row in cur.fetchall():
            asignaciones.setdefault(str(row['id_usuario']), []).append(row)
        return render_template('admin/usuarios.html', usuarios=usuarios_lista, doctores=doctores, asignaciones=asignaciones)
    except Exception as exc:
        conn.rollback()
        if request.method == 'POST' or request.is_json:
            return jsonify({'ok': False, 'error': str(exc)}), 400
        raise
    finally:
        conn.close()


@admin_bp.route('/admin/usuarios/<id_usuario>/doctoras', methods=['POST'])
@requiere_rol('admin')
def actualizar_doctoras_asistente(id_usuario):
    d = _datos_formulario()
    doctoras = d.get('doctoras') or []
    if isinstance(doctoras, str):
        doctoras = [doctoras]

    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT rol FROM USUARIOS_INTERNOS WHERE id_usuario = %s AND activo = TRUE", (id_usuario,))
        usuario = cur.fetchone()
        if not usuario or usuario['rol'] != 'asistente':
            return jsonify({'ok': False, 'error': 'Usuario asistente no encontrado'}), 404
        if not doctoras:
            return jsonify({'ok': False, 'error': 'Asigna al menos una doctora'}), 400

        cur.execute("DELETE FROM ASISTENTES_DOCTORES WHERE id_usuario = %s", (id_usuario,))
        for correo_doctor in doctoras:
            cur.execute("""
                INSERT INTO ASISTENTES_DOCTORES (id_usuario, correo_doctor, asignado_por)
                SELECT %s, correo_doctor, %s
                FROM DOCTORES
                WHERE correo_doctor = %s AND activo = TRUE
                ON CONFLICT (id_usuario, correo_doctor) DO NOTHING
            """, (id_usuario, session.get('correo', 'admin'), correo_doctor))
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
            VALUES (%s, %s, %s, %s, %s)
        """, ('ASIGNACION_ASISTENTE_DOCTORAS', session.get('correo', 'admin'), 'admin',
              json.dumps({'id_usuario': id_usuario, 'doctoras': doctoras}), request.remote_addr))
        conn.commit()
        return jsonify({'ok': True})
    except Exception as exc:
        conn.rollback()
        return jsonify({'ok': False, 'error': str(exc)}), 400
    finally:
        conn.close()

@admin_bp.route('/admin/usuarios/<id_usuario>/toggle', methods=['POST'])
@requiere_rol('admin')
def toggle_usuario(id_usuario):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE USUARIOS_INTERNOS SET activo = NOT activo WHERE id_usuario = %s", (id_usuario,))
        conn.commit()
        return jsonify({'ok': True})
    finally:
        conn.close()


# ==============================================================================
# PROVEEDORES Y FACTURAS
# ==============================================================================

@admin_bp.route('/admin/proveedores', methods=['GET', 'POST'])
@requiere_rol('admin')
def proveedores():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if request.method == 'POST':
            d = _datos_formulario()
            nombre_fiscal = (d.get('nombre_fiscal') or '').strip()
            if not nombre_fiscal:
                return jsonify({'ok': False, 'error': 'Razón social es obligatoria'}), 400
            cur.execute("""
                INSERT INTO PROVEEDORES (nombre_fiscal, rfc, correo_ejecutivo, telefono, contacto_nombre)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                nombre_fiscal,
                (d.get('rfc') or '').strip() or None,
                (d.get('correo_ejecutivo') or '').strip() or None,
                (d.get('telefono') or '').strip() or None,
                (d.get('contacto_nombre') or '').strip() or None,
            ))
            conn.commit()
            return jsonify({'ok': True})
            
        cur.execute("SELECT * FROM PROVEEDORES WHERE activo = TRUE ORDER BY nombre_fiscal")
        proveedores_lista = cur.fetchall()
        cur.execute("""
            SELECT id_producto, nombre_comercial
            FROM CAT_PRODUCTOS_MAESTRO
            WHERE estatus_producto = 'activo'
            ORDER BY nombre_comercial
        """)
        productos_lista = cur.fetchall()
        return render_template(
            'admin/proveedores.html',
            proveedores=proveedores_lista,
            productos=productos_lista,
        )
    finally:
        conn.close()

@admin_bp.route('/admin/proveedores/insumo-foto', methods=['POST'])
@requiere_rol('admin')
def upload_insumo_foto_proveedor():
    archivo = request.files.get('foto') or request.files.get('file')
    id_producto = (request.form.get('id_producto') or '').strip()

    if not id_producto:
        return jsonify({'ok': False, 'error': 'Seleccione un insumo del catálogo'}), 400
    if not archivo or not archivo.filename:
        return jsonify({'ok': False, 'error': 'Seleccione una imagen'}), 400

    conn = get_connection()
    try:
        url = subir_archivo(archivo.read(), archivo.filename, 'productos')
        cur = conn.cursor()
        cur.execute("""
            UPDATE CAT_PRODUCTOS_MAESTRO
            SET galeria_fotos = COALESCE(galeria_fotos, '[]'::jsonb) || %s::jsonb
            WHERE id_producto = %s
        """, (json.dumps([url]), id_producto))
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle)
            VALUES (%s, %s, %s, %s)
        """, (
            'FOTO_INSUMO_ADMIN',
            session.get('correo', 'admin'),
            'admin',
            json.dumps({'id_producto': id_producto, 'url': url}),
        ))
        conn.commit()
        return jsonify({'ok': True, 'url': url})
    except Exception as e:
        conn.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 400
    finally:
        conn.close()

@admin_bp.route('/admin/proveedores/<id_provider>/toggle', methods=['POST'])
@requiere_rol('admin')
def toggle_proveedor(id_provider):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE PROVEEDORES SET activo = NOT activo WHERE id_provider = %s", (id_provider,))
        conn.commit()
        return jsonify({'ok': True})
    finally:
        conn.close()

@admin_bp.route('/admin/facturas', methods=['GET', 'POST'])
@requiere_rol('admin')
def facturas():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        if request.method == 'POST':
            d = _datos_formulario()
            if not d.get('id_proveedor') or not d.get('folio_factura') or not d.get('fecha_factura'):
                return jsonify({'ok': False, 'error': 'Proveedor, folio y fecha son obligatorios'}), 400
            renglones = d.get('renglones') or []
            if isinstance(renglones, str):
                try:
                    renglones = json.loads(renglones)
                except json.JSONDecodeError:
                    return jsonify({'ok': False, 'error': 'Renglones de factura inválidos'}), 400
            if not isinstance(renglones, list) or not renglones:
                return jsonify({'ok': False, 'error': 'Agrega al menos un renglón de insumos'}), 400

            try:
                subtotal = float(d.get('subtotal') or 0)
                iva = float(d.get('iva') or 0)
                total = float(d.get('total') or 0)
            except (TypeError, ValueError):
                return jsonify({'ok': False, 'error': 'Montos inválidos'}), 400
            
            # Validación de integridad matemática (margen de $1 para redondeos)
            if abs(total - (subtotal + iva)) > 1.0:
                return jsonify({'error': 'El Total no coincide con la suma de Subtotal + IVA'}), 400

            try:
                cur.execute(
                    "SELECT id_provider FROM PROVEEDORES WHERE id_provider = %s AND activo = TRUE",
                    (d['id_proveedor'],),
                )
                if not cur.fetchone():
                    return jsonify({'ok': False, 'error': 'Proveedor no encontrado o inactivo'}), 400

                cur.execute("""
                    INSERT INTO FACTURAS_COMPRA (id_proveedor, folio_factura, fecha_factura, subtotal, iva, total, notas, capturada_por)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id_factura
                """, (d['id_proveedor'], d['folio_factura'], d['fecha_factura'], subtotal, iva, total, d.get('notas'), session['correo']))
                id_factura = cur.fetchone()['id_factura']

                for idx, renglon in enumerate(renglones, start=1):
                    id_producto = (renglon.get('id_producto') or '').strip() or None
                    lote_proveedor = (renglon.get('lote_proveedor') or '').strip()
                    fecha_caducidad = (renglon.get('fecha_caducidad') or '').strip()
                    tipo_presentacion = (renglon.get('tipo_presentacion') or '').strip()
                    tipos_presentacion = {'pieza', 'caja', 'paquete', 'bolsa', 'kit'}

                    try:
                        cantidad_presentaciones = int(renglon.get('cantidad_presentaciones') or 0)
                        piezas_por_presentacion = int(renglon.get('piezas_por_presentacion') or 0)
                        precio_compra_presentacion = float(renglon.get('precio_compra_presentacion') or 0)
                    except (TypeError, ValueError):
                        raise ValueError(f'Renglon {idx}: datos de presentacion o precio invalidos')

                    if cantidad_presentaciones <= 0:
                        raise ValueError(f'Renglon {idx}: la cantidad de presentaciones debe ser mayor a 0')
                    if not tipo_presentacion or tipo_presentacion not in tipos_presentacion:
                        raise ValueError(f'Renglon {idx}: tipo de presentacion invalido')
                    if piezas_por_presentacion <= 0:
                        raise ValueError(f'Renglon {idx}: piezas por presentacion debe ser mayor a 0')
                    if precio_compra_presentacion < 0:
                        raise ValueError(f'Renglon {idx}: el precio de compra por presentacion no puede ser negativo')
                    if not fecha_caducidad:
                        raise ValueError(f'Renglon {idx}: fecha de caducidad obligatoria')
                    if not lote_proveedor:
                        raise ValueError(f'Renglon {idx}: lote proveedor obligatorio')

                    cantidad = cantidad_presentaciones * piezas_por_presentacion
                    precio_compra = precio_compra_presentacion / piezas_por_presentacion

                    if id_producto:
                        cur.execute("""
                            SELECT id_producto
                            FROM CAT_PRODUCTOS_MAESTRO
                            WHERE id_producto = %s AND estatus_producto = 'activo'
                        """, (id_producto,))
                        if not cur.fetchone():
                            raise ValueError(f'Renglon {idx}: producto no encontrado o inactivo')
                    else:
                        nombre_comercial = (renglon.get('nombre_comercial') or '').strip()
                        descripcion = (renglon.get('descripcion') or '').strip() or None
                        precio_venta_raw = str(renglon.get('precio_venta') or '').strip()
                        if not precio_venta_raw:
                            raise ValueError(f'Renglon {idx}: precio de venta obligatorio para producto nuevo')
                        try:
                            precio_venta = float(precio_venta_raw)
                        except (TypeError, ValueError):
                            raise ValueError(f'Renglon {idx}: precio de venta invalido')
                        if not nombre_comercial:
                            raise ValueError(f'Renglon {idx}: nombre comercial obligatorio para producto nuevo')
                        if precio_venta < 0:
                            raise ValueError(f'Renglon {idx}: precio de venta no puede ser negativo')

                        cur.execute("""
                            INSERT INTO CAT_PRODUCTOS_MAESTRO
                                (nombre_comercial, descripcion, precio_venta, estatus_producto)
                            VALUES (%s, %s, %s, 'activo')
                            RETURNING id_producto
                        """, (nombre_comercial, descripcion, precio_venta))
                        id_producto = cur.fetchone()['id_producto']

                    id_lote = str(uuid.uuid4())
                    cur.execute("""
                        INSERT INTO INVENTARIO_LOTES
                            (id_lote, id_producto, lote_proveedor, cantidad_piezas_actual,
                             fecha_caducidad, precio_compra, activo)
                        VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                    """, (id_lote, id_producto, lote_proveedor, cantidad, fecha_caducidad, precio_compra))

                    cur.execute("""
                        INSERT INTO MOVIMIENTOS_INVENTARIO
                            (id_lote, tipo_movimiento, cantidad, referencia_doc, detalle, fecha_movimiento)
                        VALUES (%s, 'ENTRADA_COMPRA', %s, %s, %s, NOW())
                    """, (
                        id_lote,
                        cantidad,
                        d['folio_factura'],
                        f'Entrada por factura. Compra: {cantidad_presentaciones} {tipo_presentacion}(s) x {piezas_por_presentacion} piezas',
                    ))

                conn.commit()
                return jsonify({'ok': True, 'id_factura': str(id_factura)})
            except Exception as e:
                conn.rollback()
                return jsonify({'ok': False, 'error': str(e)}), 400

        # Filtro opcional
        id_prov = request.args.get('id_proveedor')
        query = """
            SELECT f.*, p.nombre_fiscal 
            FROM FACTURAS_COMPRA f
            JOIN PROVEEDORES p ON f.id_proveedor = p.id_provider
        """
        params = ()
        if id_prov:
            query += " WHERE f.id_proveedor = %s"
            params = (id_prov,)
            
        query += " ORDER BY f.fecha_factura DESC"
        
        cur.execute(query, params)
        facturas_lista = cur.fetchall()
        
        # Para el modal
        cur.execute("SELECT id_provider, nombre_fiscal FROM PROVEEDORES WHERE activo = TRUE")
        proveedores_lista = cur.fetchall()
        cur.execute("""
            SELECT id_producto, nombre_comercial, precio_venta
            FROM CAT_PRODUCTOS_MAESTRO
            WHERE estatus_producto = 'activo'
            ORDER BY nombre_comercial
        """)
        productos_lista = cur.fetchall()
        
        return render_template(
            'admin/facturas.html',
            facturas=facturas_lista,
            proveedores=proveedores_lista,
            productos=productos_lista,
        )
    finally:
        conn.close()

@admin_bp.route('/admin/facturas/<id_factura>', methods=['GET'])
@requiere_rol('admin')
def detalle_factura(id_factura):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Detalle de la factura y los movimientos de inventario que entraron con ella
        cur.execute("""
            SELECT m.id_movimiento, m.cantidad, m.referencia_doc, m.detalle,
                   m.fecha_movimiento, l.lote_proveedor, l.fecha_caducidad,
                   l.precio_compra, p.nombre_comercial
            FROM MOVIMIENTOS_INVENTARIO m
            JOIN INVENTARIO_LOTES l ON m.id_lote = l.id_lote
            JOIN CAT_PRODUCTOS_MAESTRO p ON l.id_producto = p.id_producto
            WHERE m.referencia_doc = (SELECT folio_factura FROM FACTURAS_COMPRA WHERE id_factura = %s)
            AND m.tipo_movimiento = 'ENTRADA_COMPRA'
        """, (id_factura,))
        return jsonify({'movimientos': cur.fetchall()})
    finally:
        conn.close()


# ==============================================================================
# BLOQUE 9.4 — CONTABILIDAD, FAQ, AGENTES Y SUPERVISIÓN
# ==============================================================================

@admin_bp.route('/admin/contabilidad', methods=['GET', 'POST'])
@requiere_rol('admin')
def contabilidad():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if request.method == 'POST':
            d = request.json
            cur.execute("""
                INSERT INTO CONTABILIDAD_ADMIN (tipo, concepto, monto, fecha_documento)
                VALUES (%s, %s, %s, %s)
            """, (d['tipo'], d['concepto'], d['monto'], d['fecha_documento']))
            conn.commit()
            return jsonify({'ok': True})

        cur.execute("SELECT * FROM CONTABILIDAD_ADMIN ORDER BY fecha_documento DESC LIMIT 100")
        return render_template('admin/contabilidad.html', registros=cur.fetchall())
    finally:
        conn.close()

@admin_bp.route('/admin/faq', methods=['GET', 'POST'])
@requiere_rol('admin')
def faq_global():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if request.method == 'POST':
            d = request.json
            cur.execute("""
                INSERT INTO FAQ_CHATBOT (palabras_clave, respuesta, orden)
                VALUES (%s, %s, %s)
            """, (d['palabras_clave'], d['respuesta'], d.get('orden', 0)))
            conn.commit()
            return jsonify({'ok': True})

        cur.execute("SELECT * FROM FAQ_CHATBOT WHERE id_doctor_app IS NULL ORDER BY orden ASC")
        return render_template('admin/faq.html', faqs=cur.fetchall())
    finally:
        conn.close()

@admin_bp.route('/admin/auditoria', methods=['GET'])
@requiere_rol('admin')
def auditoria():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM AUDITORIA_SEGURIDAD ORDER BY fecha_evento DESC LIMIT 200")
        return render_template('admin/auditoria.html', logs=cur.fetchall())
    finally:
        conn.close()

# ---- RUTAS DE AGENTES E INTELIGENCIA ARTIFICIAL ----

@admin_bp.route('/admin/asistente', methods=['POST'])
@requiere_rol('admin')
def asistente_admin():
    """El cerebro Gemini ayudando al admin."""
    pregunta = request.json.get('pregunta')
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Extraer micro-contexto para darle inteligencia a Gemini
        cur.execute("SELECT COUNT(*) as d FROM DOCTORES WHERE activo=TRUE")
        docs = cur.fetchone()['d']
        cur.execute("SELECT COUNT(*) as p FROM VENTAS_PEDIDOS_ELITE WHERE estatus_entrega='nuevo'")
        peds = cur.fetchone()['p']
        
        contexto_negocio = f"Tienes {docs} doctores activos y {peds} pedidos nuevos por surtir."
        
        cerebro = CerebroGemini()
        respuesta = cerebro.responder_admin(pregunta, contexto_negocio)
        return jsonify({'respuesta': respuesta})
    finally:
        conn.close()

@admin_bp.route('/admin/supervisor', methods=['GET'])
@requiere_rol('admin')
def supervisor():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM LOGS_SUPERVISOR ORDER BY fecha_ejecucion DESC LIMIT 50")
        return render_template('admin/supervisor.html', logs=cur.fetchall())
    finally:
        conn.close()


@admin_bp.route('/admin/uso-ia', methods=['GET'])
@requiere_rol('admin')
def uso_ia():
    """Telemetria agregada del asistente sin preguntas ni datos clinicos."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'ia_asistente_uso'
            ) AS disponible,
            EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'ia_evaluacion_uso'
            ) AS evaluacion_disponible
        """)
        tablas_ia = cur.fetchone() or {}
        disponible = bool(tablas_ia.get('disponible'))
        evaluacion_disponible = bool(tablas_ia.get('evaluacion_disponible'))
        if not disponible:
            return render_template(
                'admin/uso_ia.html',
                migracion_pendiente=True,
                resumen={},
                consultorios=[],
                limite_consultorio=PANEL_ASSISTANT_GEMINI_CLINIC_DAILY_LIMIT,
                limite_global=PANEL_ASSISTANT_GEMINI_GLOBAL_DAILY_LIMIT,
                evaluacion_disponible=evaluacion_disponible,
                evaluacion_resumen={},
                evaluacion_consultorios=[],
                limite_evaluacion_consultorio=IMPLEMENTATION_AI_CLINIC_DAILY_LIMIT,
                limite_evaluacion_global=IMPLEMENTATION_AI_GLOBAL_DAILY_LIMIT,
            )

        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE fecha_evento >= DATE_TRUNC('day', NOW())) AS preguntas_hoy,
                COUNT(*) FILTER (
                    WHERE fecha_evento >= DATE_TRUNC('day', NOW())
                      AND fuente = 'reglas' AND estado = 'resuelto'
                ) AS reglas_hoy,
                COUNT(*) FILTER (
                    WHERE fecha_evento >= DATE_TRUNC('day', NOW())
                      AND fuente = 'gemini_intent'
                      AND estado IN ('reservado', 'resuelto', 'error')
                ) AS gemini_hoy,
                COUNT(*) FILTER (
                    WHERE fecha_evento >= DATE_TRUNC('day', NOW())
                      AND estado = 'error'
                ) AS errores_hoy,
                COUNT(*) FILTER (
                    WHERE fecha_evento >= DATE_TRUNC('day', NOW())
                      AND estado = 'limitado'
                ) AS limitadas_hoy,
                COALESCE(SUM(tokens_entrada) FILTER (
                    WHERE fecha_evento >= DATE_TRUNC('day', NOW())
                ), 0) AS tokens_entrada_hoy,
                COALESCE(SUM(tokens_salida + tokens_razonamiento) FILTER (
                    WHERE fecha_evento >= DATE_TRUNC('day', NOW())
                ), 0) AS tokens_salida_hoy,
                COALESCE(SUM(costo_estimado_usd) FILTER (
                    WHERE fecha_evento >= DATE_TRUNC('day', NOW())
                ), 0) AS costo_hoy,
                COALESCE(SUM(costo_estimado_usd) FILTER (
                    WHERE fecha_evento >= CURRENT_DATE - INTERVAL '30 days'
                ), 0) AS costo_30d,
                MAX(fecha_evento) AS ultima_actividad
            FROM IA_ASISTENTE_USO
        """)
        resumen = cur.fetchone() or {}

        cur.execute("""
            SELECT
                d.correo_doctor,
                d.nombre_doctor,
                COUNT(u.id_uso) FILTER (
                    WHERE u.fecha_evento >= DATE_TRUNC('day', NOW())
                ) AS preguntas_hoy,
                COUNT(u.id_uso) FILTER (
                    WHERE u.fecha_evento >= DATE_TRUNC('day', NOW())
                      AND u.fuente = 'reglas' AND u.estado = 'resuelto'
                ) AS reglas_hoy,
                COUNT(u.id_uso) FILTER (
                    WHERE u.fecha_evento >= DATE_TRUNC('day', NOW())
                      AND u.fuente = 'gemini_intent'
                      AND u.estado IN ('reservado', 'resuelto', 'error')
                ) AS gemini_hoy,
                COUNT(u.id_uso) FILTER (
                    WHERE u.fecha_evento >= DATE_TRUNC('day', NOW())
                      AND u.estado = 'error'
                ) AS errores_hoy,
                COALESCE(SUM(u.tokens_total) FILTER (
                    WHERE u.fecha_evento >= DATE_TRUNC('day', NOW())
                ), 0) AS tokens_hoy,
                COALESCE(SUM(u.costo_estimado_usd) FILTER (
                    WHERE u.fecha_evento >= CURRENT_DATE - INTERVAL '30 days'
                ), 0) AS costo_30d,
                MAX(u.fecha_evento) AS ultima_actividad
            FROM DOCTORES d
            LEFT JOIN IA_ASISTENTE_USO u ON u.correo_doctor = d.correo_doctor
            WHERE d.activo = TRUE
            GROUP BY d.correo_doctor, d.nombre_doctor
            ORDER BY gemini_hoy DESC, preguntas_hoy DESC, d.nombre_doctor ASC
        """)
        consultorios = []
        for fila in cur.fetchall():
            fila['cuota_restante'] = max(
                0,
                PANEL_ASSISTANT_GEMINI_CLINIC_DAILY_LIMIT - int(fila.get('gemini_hoy') or 0),
            )
            consultorios.append(fila)
        resumen['cuota_global_restante'] = max(
            0,
            PANEL_ASSISTANT_GEMINI_GLOBAL_DAILY_LIMIT - int(resumen.get('gemini_hoy') or 0),
        )

        evaluacion_resumen = {}
        evaluacion_consultorios = []
        if evaluacion_disponible:
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (
                        WHERE fecha_evento >= DATE_TRUNC('day', NOW())
                          AND estado IN ('RESERVADO', 'RESUELTO', 'ERROR')
                    ) AS analisis_hoy,
                    COUNT(*) FILTER (
                        WHERE fecha_evento >= DATE_TRUNC('day', NOW())
                          AND estado = 'RESUELTO'
                    ) AS resueltos_hoy,
                    COUNT(*) FILTER (
                        WHERE fecha_evento >= DATE_TRUNC('day', NOW())
                          AND estado = 'ERROR'
                    ) AS errores_hoy,
                    COUNT(*) FILTER (
                        WHERE fecha_evento >= DATE_TRUNC('day', NOW())
                          AND estado = 'LIMITADO'
                    ) AS limitados_hoy,
                    COALESCE(SUM(tokens_total) FILTER (
                        WHERE fecha_evento >= DATE_TRUNC('day', NOW())
                    ), 0) AS tokens_hoy,
                    COALESCE(SUM(costo_estimado_usd) FILTER (
                        WHERE fecha_evento >= CURRENT_DATE - INTERVAL '30 days'
                    ), 0) AS costo_30d,
                    MAX(fecha_evento) AS ultima_actividad
                FROM IA_EVALUACION_USO
            """)
            evaluacion_resumen = cur.fetchone() or {}
            evaluacion_resumen['cuota_global_restante'] = max(
                0,
                IMPLEMENTATION_AI_GLOBAL_DAILY_LIMIT - int(evaluacion_resumen.get('analisis_hoy') or 0),
            )
            cur.execute("""
                SELECT d.nombre_doctor, d.correo_doctor,
                       COUNT(u.id_uso) FILTER (
                           WHERE u.fecha_evento >= DATE_TRUNC('day', NOW())
                             AND u.estado IN ('RESERVADO', 'RESUELTO', 'ERROR')
                       ) AS analisis_hoy,
                       COALESCE(SUM(u.tokens_total) FILTER (
                           WHERE u.fecha_evento >= DATE_TRUNC('day', NOW())
                       ), 0) AS tokens_hoy,
                       COALESCE(SUM(u.costo_estimado_usd) FILTER (
                           WHERE u.fecha_evento >= CURRENT_DATE - INTERVAL '30 days'
                       ), 0) AS costo_30d,
                       MAX(u.fecha_evento) AS ultima_actividad
                FROM DOCTORES d
                LEFT JOIN IA_EVALUACION_USO u ON u.correo_doctor = d.correo_doctor
                WHERE d.activo = TRUE
                GROUP BY d.nombre_doctor, d.correo_doctor
                ORDER BY analisis_hoy DESC, d.nombre_doctor
            """)
            for fila in cur.fetchall():
                fila['cuota_restante'] = max(
                    0,
                    IMPLEMENTATION_AI_CLINIC_DAILY_LIMIT - int(fila.get('analisis_hoy') or 0),
                )
                evaluacion_consultorios.append(fila)
        return render_template(
            'admin/uso_ia.html',
            migracion_pendiente=False,
            resumen=resumen,
            consultorios=consultorios,
            limite_consultorio=PANEL_ASSISTANT_GEMINI_CLINIC_DAILY_LIMIT,
            limite_global=PANEL_ASSISTANT_GEMINI_GLOBAL_DAILY_LIMIT,
            evaluacion_disponible=evaluacion_disponible,
            evaluacion_resumen=evaluacion_resumen,
            evaluacion_consultorios=evaluacion_consultorios,
            limite_evaluacion_consultorio=IMPLEMENTATION_AI_CLINIC_DAILY_LIMIT,
            limite_evaluacion_global=IMPLEMENTATION_AI_GLOBAL_DAILY_LIMIT,
        )
    finally:
        conn.close()

@admin_bp.route('/admin/supervisor/ejecutar', methods=['POST'])
@requiere_rol('admin')
def ejecutar_supervisor():
    resultado = AgenteSupervisor().ejecutar(origen='manual')
    return jsonify(resultado)

@admin_bp.route('/admin/agentes', methods=['GET'])
@requiere_rol('admin')
def dashboard_agentes():
    return render_template('admin/agentes.html')


def _historial_agente(tabla, columna_fecha):
    permitidos = {
        'LOGS_COMERCIAL': 'fecha_deteccion',
        'LOGS_COMPRAS': 'fecha_generacion',
        'LOGS_FINANCIERO': 'fecha_calculo',
    }
    if permitidos.get(tabla) != columna_fecha:
        return []
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute(f'SELECT * FROM {tabla} ORDER BY {columna_fecha} DESC LIMIT 10')
            return cur.fetchall()
        except Exception:
            conn.rollback()
            return []
    finally:
        conn.close()


@admin_bp.route('/admin/suffy/comercial', methods=['GET'])
@requiere_rol('admin')
def agente_comercial_area():
    return render_template(
        'admin/agente_area.html',
        area='Doko Suffy', titulo='Oportunidades comerciales',
        descripcion='Detecta consultorios activos que dejaron de comprar. Solo prepara borradores; no envía mensajes.',
        action_url='/admin/agentes/comercial/ejecutar',
        action_label='Analizar oportunidades',
        empty_message='No hay oportunidades de reactivación por ahora.',
        result_key='oportunidades_detectadas',
        historial=_historial_agente('LOGS_COMERCIAL', 'fecha_deteccion'),
    )


@admin_bp.route('/admin/inventario/compras', methods=['GET'])
@requiere_rol('admin')
def agente_compras_area():
    return render_template(
        'admin/agente_area.html',
        area='Bodega e inventario', titulo='Asistente de compras',
        descripcion='Revisa existencias y propone qué reabastecer. Nunca genera una compra automática.',
        action_url='/admin/agentes/compras/ejecutar',
        action_label='Revisar stock',
        empty_message='No hay productos con stock crítico.',
        result_key='productos',
        historial=_historial_agente('LOGS_COMPRAS', 'fecha_generacion'),
    )


@admin_bp.route('/admin/administracion/finanzas', methods=['GET'])
@requiere_rol('admin')
def agente_financiero_area():
    return render_template(
        'admin/agente_area.html',
        area='Administración', titulo='Lectura financiera',
        descripcion='Calcula margen con ventas y costos registrados. No mueve dinero ni modifica facturas.',
        action_url='/admin/agentes/financiero/ejecutar',
        action_label='Calcular mes actual',
        empty_message='No hay ventas del mes para calcular margen.',
        result_key='margen_promedio',
        historial=_historial_agente('LOGS_FINANCIERO', 'fecha_calculo'),
    )

@admin_bp.route('/admin/agentes/compras/ejecutar', methods=['POST'])
@requiere_rol('admin')
def ejecutar_compras():
    resultado = AgenteCompras().ejecutar()
    return jsonify({'ok': bool(resultado.get('ok')), 'resultado': resultado}), (200 if resultado.get('ok') else 500)

@admin_bp.route('/admin/agentes/comercial/ejecutar', methods=['POST'])
@requiere_rol('admin')
def ejecutar_comercial():
    resultado = AgenteComercial().ejecutar()
    return jsonify({'ok': bool(resultado.get('ok')), 'resultado': resultado}), (200 if resultado.get('ok') else 500)

@admin_bp.route('/admin/agentes/financiero/ejecutar', methods=['POST'])
@requiere_rol('admin')
def ejecutar_financiero():
    resultado = AgenteFinanciero().ejecutar()
    return jsonify({'ok': bool(resultado.get('ok')), 'resultado': resultado}), (200 if resultado.get('ok') else 500)


@admin_bp.route('/admin/agentes/trazabilidad/<id_lote>', methods=['POST'])
@requiere_rol('admin')
def ejecutar_trazabilidad(id_lote):
    from agentes.nivel2.agente_trazabilidad import AgenteTrazabilidad
    resultado = AgenteTrazabilidad().ejecutar(id_lote, session.get('correo', 'admin'))
    return jsonify(resultado)


