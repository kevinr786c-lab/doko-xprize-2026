import hashlib
import re
import uuid
from datetime import date, datetime, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, abort, jsonify, make_response, render_template, request
from psycopg2.extras import RealDictCursor

from config_bunker import PORTAL_BASE_URL, PRESENCIA_BASE_DOMAIN, WHATSAPP_NUMBER
from helpers.db import get_connection


presencia_bp = Blueprint('presencia_bp', __name__)
COOKIE_SESION = 'doko_presencia_sesion'
EVENTOS_VALIDOS = {'CLICK_WHATSAPP', 'CLICK_AGENDAR', 'CLICK_MAPS', 'CLICK_TELEFONO'}
SUBDOMINIO_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
TZ_TIJUANA = ZoneInfo('America/Tijuana')


def _host_normalizado(host: str) -> str:
    return (host or '').split(':', 1)[0].strip().lower().rstrip('.')


def _subdominio_desde_host(host: str) -> str | None:
    host = _host_normalizado(host)
    sufijo = f'.{PRESENCIA_BASE_DOMAIN}'
    if not host.endswith(sufijo):
        return None
    subdominio = host[:-len(sufijo)]
    if not subdominio or '.' in subdominio or subdominio == 'app':
        return None
    return subdominio if SUBDOMINIO_RE.fullmatch(subdominio) else None


def _es_url_publica(valor: str) -> bool:
    parsed = urlparse((valor or '').strip())
    return parsed.scheme in {'https', 'http'} and bool(parsed.netloc)


def _es_host_home_doko(host: str) -> bool:
    host = _host_normalizado(host)
    if host in {PRESENCIA_BASE_DOMAIN, f'www.{PRESENCIA_BASE_DOMAIN}', 'localhost', '127.0.0.1'}:
        return True
    return False


def _numero_whatsapp_medico(sitio: dict) -> str:
    """Devuelve WhatsApp de la doctora/sitio; nunca usa el WhatsApp comercial global."""
    valor = (sitio.get('whatsapp_numero') or sitio.get('telefono_consultorio') or '').strip()
    digitos = ''.join(ch for ch in valor if ch.isdigit())
    if not digitos:
        return ''
    if len(digitos) == 10:
        return f'52{digitos}'
    return digitos


def _formatear_horario_liberado(fecha_cita: datetime) -> str:
    if not isinstance(fecha_cita, datetime):
        return ''
    fecha_local = fecha_cita.replace(tzinfo=None)
    hoy = datetime.now(TZ_TIJUANA).date()
    fecha = fecha_local.date()
    hora = fecha_local.strftime('%I:%M %p').lstrip('0').replace('AM', 'a. m.').replace('PM', 'p. m.')
    if fecha == hoy:
        return f'Hoy {hora}'
    if fecha == hoy + timedelta(days=1):
        return f'Mañana {hora}'
    dias = ['lun.', 'mar.', 'mié.', 'jue.', 'vie.', 'sáb.', 'dom.']
    meses = ['ene.', 'feb.', 'mar.', 'abr.', 'may.', 'jun.', 'jul.', 'ago.', 'sep.', 'oct.', 'nov.', 'dic.']
    return f"{dias[fecha.weekday()]} {fecha.day} {meses[fecha.month - 1]} · {hora}"


def _parece_slug_publico(valor: str | None) -> bool:
    valor = (valor or '').strip()
    if not valor:
        return False
    return '-' in valor and ' ' not in valor and valor.lower() == valor


def _nombre_publico_directorio(doctor: dict) -> str:
    """Evita mostrar slugs técnicos en tarjetas públicas de doko.lat."""
    nombre_clinica = (doctor.get('nombre_clinica_publico') or '').strip()
    if nombre_clinica and not _parece_slug_publico(nombre_clinica):
        return nombre_clinica
    nombre_doctor = (doctor.get('nombre_doctor') or '').strip()
    if nombre_doctor:
        return nombre_doctor
    subdominio = (doctor.get('subdominio') or '').replace('-', ' ').strip()
    return subdominio.title() if subdominio else 'Médico Doko'


def _terminos_ruta_seo(ruta: dict) -> list[str]:
    valor = ruta.get('terminos_busqueda') or []
    if isinstance(valor, str):
        valor = [item.strip() for item in valor.split(',')]
    salida = []
    vistos = set()
    for termino in [ruta.get('especialidad'), *valor]:
        limpio = str(termino or '').strip()
        clave = limpio.casefold()
        if limpio and clave not in vistos:
            vistos.add(clave)
            salida.append(limpio)
    return salida


def _listar_rutas_seo_publicadas() -> list[dict]:
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT to_regclass('public.seo_local_rutas') AS tabla")
        if not cur.fetchone()['tabla']:
            return []
        cur.execute("""
            SELECT id_ruta, slug, especialidad, ciudad, titulo, subtitulo,
                   descripcion, terminos_busqueda, estado, orden
            FROM SEO_LOCAL_RUTAS
            WHERE estado = 'PUBLICADO'
            ORDER BY orden ASC, especialidad ASC
        """)
        rutas = cur.fetchall()
        return [ruta for ruta in rutas if _obtener_directorio_medico(_terminos_ruta_seo(ruta))]
    finally:
        conn.close()


def _obtener_ruta_seo_local(*, slug: str | None = None, id_ruta: str | None = None,
                            solo_publicada: bool = True) -> dict | None:
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT to_regclass('public.seo_local_rutas') AS tabla")
        if not cur.fetchone()['tabla']:
            return None
        filtro_estado = " AND estado = 'PUBLICADO'" if solo_publicada else ''
        if id_ruta:
            cur.execute(f"SELECT * FROM SEO_LOCAL_RUTAS WHERE id_ruta=%s{filtro_estado}", (id_ruta,))
        else:
            cur.execute(f"SELECT * FROM SEO_LOCAL_RUTAS WHERE slug=%s{filtro_estado}", (slug,))
        return cur.fetchone()
    finally:
        conn.close()


def _obtener_espacios_liberados(correos_doctor: list[str] | None = None) -> dict[str, dict]:
    """Lee oportunidades públicas desde apartados vencidos/liberados sin exponer datos del paciente."""
    conn = get_connection()
    if not conn:
        return {}
    correos = [correo for correo in (correos_doctor or []) if correo]
    ahora = datetime.now(TZ_TIJUANA).replace(tzinfo=None)
    hace_24h = ahora - timedelta(hours=24)
    limite = ahora + timedelta(days=7)
    filtro_correos = ""
    params = [ahora, limite, hace_24h]
    if correos:
        filtro_correos = "AND r.correo_doctor = ANY(%s)"
        params.append(correos)
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(f"""
            SELECT DISTINCT ON (r.correo_doctor)
                   r.correo_doctor,
                   r.fecha_cita,
                   d.id_publico
            FROM RADAR_EVENTOS_CITAS r
            JOIN DOCTORES d ON d.correo_doctor = r.correo_doctor
            LEFT JOIN SITIOS_MEDICOS s ON s.correo_doctor = d.correo_doctor
            WHERE d.activo = TRUE
              AND d.id_publico IS NOT NULL
              AND COALESCE(r.estado_operativo, 'activo') IN ('liberado', 'cancelado')
              AND (
                    COALESCE(r.tipo_evento, '') = 'APARTADO_TEMPORAL'
                    OR (
                        COALESCE(r.tipo_evento, '') = 'CITA_PACIENTE'
                        AND COALESCE(r.origen_evento, '') IN ('doko', 'doko_asistente')
                    )
              )
              AND r.fecha_cita >= %s
              AND r.fecha_cita < %s
              AND COALESCE(r.liberado_en, r.expiracion_apartado) >= %s
              AND (s.id_sitio IS NULL OR (s.visual_config->>'visible_en_directorio') IS DISTINCT FROM 'false')
              {filtro_correos}
            ORDER BY r.correo_doctor, r.fecha_cita ASC
        """, tuple(params))
        oportunidades = {}
        for row in cur.fetchall():
            fecha_cita = row.get('fecha_cita')
            oportunidades[row['correo_doctor']] = {
                'fecha_cita': fecha_cita.isoformat(timespec='seconds') if isinstance(fecha_cita, datetime) else None,
                'texto_fecha': _formatear_horario_liberado(fecha_cita),
                'portal_url': f"https://{PRESENCIA_BASE_DOMAIN}/p/{row['id_publico']}",
            }
        return oportunidades
    except Exception:
        return {}
    finally:
        conn.close()


def _obtener_directorio_medico(terminos: list[str] | None = None) -> list[dict]:
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT to_regclass('public.sitios_medicos') AS tabla")
        if not cur.fetchone()['tabla']:
            return []
        filtro_sql = ""
        params = []
        if terminos:
            filtros = []
            for termino in terminos:
                like = f"%{termino.lower()}%"
                filtros.append("""
                    LOWER(COALESCE(s.especialidad_publica, d.especialidad, '')) LIKE %s
                    OR LOWER(COALESCE(s.nombre_clinica_publico, d.nombre_doctor, '')) LIKE %s
                    OR EXISTS (
                        SELECT 1 FROM CAT_SERVICIOS_CONSULTORIO csf
                        WHERE csf.correo_doctor = d.correo_doctor
                          AND csf.activo = TRUE
                          AND LOWER(csf.nombre_servicio || ' ' || COALESCE(csf.descripcion, '')) LIKE %s
                    )
                """)
                params.extend([like, like, like])
            filtro_sql = " AND (" + " OR ".join(f"({f})" for f in filtros) + ")"
        cur.execute(f"""
            WITH directorio AS (
            SELECT
                s.id_sitio, s.subdominio, s.estado, s.nombre_clinica_publico, s.especialidad_publica,
                s.ciudad, s.logo_url, s.portada_url, s.estado_dominio,
                s.cedula_profesional, s.cedula_especialidad,
                d.nombre_doctor, d.especialidad, d.foto_perfil_url, d.id_publico,
                d.correo_doctor, d.telefono_consultorio, d.direccion_consultorio, d.maps_url,
                d.aseguradoras_aceptadas, d.metodos_pago_aceptados, d.horarios_atencion,
                d.aviso_consultorio,
                (d.aviso_activo AND d.aviso_visible_web AND (d.aviso_expira_en IS NULL OR d.aviso_expira_en >= NOW())) AS aviso_visible,
                COALESCE(NULLIF(s.visual_config->>'servicios_destacados_directorio', ''), NULL) AS servicios_destacados_texto,
                svc.servicios_destacados, svc.servicios_detalle,
                COALESCE((s.visual_config->>'destacado_directorio')::boolean, FALSE) AS destacado_directorio,
                COALESCE((s.visual_config->>'medico_fundador')::boolean, FALSE) AS medico_fundador,
                COALESCE(NULLIF(s.visual_config->>'orden_directorio', '')::int, 999) AS orden_directorio,
                COALESCE(s.id_sitio::text, d.correo_doctor) AS rotacion_clave,
                (
                    CASE WHEN COALESCE(s.nombre_clinica_publico, d.nombre_doctor) IS NOT NULL THEN 12 ELSE 0 END +
                    CASE WHEN COALESCE(s.especialidad_publica, d.especialidad) IS NOT NULL THEN 12 ELSE 0 END +
                    CASE WHEN COALESCE(s.ciudad, '') <> '' THEN 10 ELSE 0 END +
                    CASE WHEN COALESCE(s.logo_url, d.foto_perfil_url, s.portada_url) IS NOT NULL THEN 12 ELSE 0 END +
                    CASE WHEN d.id_publico IS NOT NULL THEN 18 ELSE 0 END +
                    CASE WHEN d.telefono_consultorio IS NOT NULL THEN 8 ELSE 0 END +
                    CASE WHEN d.direccion_consultorio IS NOT NULL THEN 10 ELSE 0 END +
                    CASE WHEN svc.servicios_destacados IS NOT NULL AND array_length(svc.servicios_destacados, 1) > 0 THEN 18 ELSE 0 END
                ) AS perfil_score
            FROM DOCTORES d
            LEFT JOIN SITIOS_MEDICOS s ON s.correo_doctor = d.correo_doctor
            LEFT JOIN LATERAL (
                SELECT ARRAY(
                    SELECT nombre_servicio
                    FROM CAT_SERVICIOS_CONSULTORIO cs
                    WHERE cs.correo_doctor = d.correo_doctor AND cs.activo = TRUE
                    ORDER BY nombre_servicio ASC
                    LIMIT 3
                ) AS servicios_destacados,
                (
                    SELECT COALESCE(json_agg(servicio ORDER BY servicio->>'nombre_servicio'), '[]'::json)
                    FROM (
                        SELECT json_build_object(
                            'nombre_servicio', cs.nombre_servicio,
                            'precio', cs.precio,
                            'tipo_precio', COALESCE(cs.tipo_precio, 'precio_fijo'),
                            'descripcion', cs.descripcion
                        ) AS servicio
                        FROM CAT_SERVICIOS_CONSULTORIO cs
                        WHERE cs.correo_doctor = d.correo_doctor AND cs.activo = TRUE
                        ORDER BY cs.nombre_servicio ASC
                        LIMIT 3
                    ) servicios
                ) AS servicios_detalle
            ) svc ON TRUE
            WHERE d.activo = TRUE
              AND d.id_publico IS NOT NULL
              AND COALESCE(s.ciudad, 'Tijuana') ILIKE 'Tijuana'
              AND (s.visual_config->>'visible_en_directorio') IS DISTINCT FROM 'false'
              AND LOWER(COALESCE(d.id_publico, '')) NOT IN ('dr-kevenr-tijuana', 'dr-keven-reyes', 'keven-reyes')
              AND LOWER(COALESCE(d.nombre_doctor, '')) NOT LIKE '%%keven%%'
              {filtro_sql}
            )
            SELECT * FROM directorio
            ORDER BY destacado_directorio DESC,
                     CASE WHEN perfil_score >= 70 THEN 0 WHEN perfil_score >= 45 THEN 1 ELSE 2 END ASC,
                     md5(rotacion_clave || to_char(CURRENT_DATE, 'IYYY-IW')) ASC,
                     orden_directorio ASC
            LIMIT 24
        """, tuple(params))
        doctores = cur.fetchall()
        oportunidades = _obtener_espacios_liberados([d.get('correo_doctor') for d in doctores])
        for doctor in doctores:
            doctor['nombre_directorio'] = _nombre_publico_directorio(doctor)
            doctor['espacio_liberado'] = oportunidades.get(doctor.get('correo_doctor'))
        return doctores
    finally:
        conn.close()


def _obtener_sitio(subdominio: str, *, solo_publicado: bool = True, sitio_id: str | None = None) -> dict | None:
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT to_regclass('public.sitios_medicos') AS tabla")
        if not cur.fetchone()['tabla']:
            return None
        filtros = ["d.activo = TRUE"]
        params = []
        if sitio_id:
            filtros.append("s.id_sitio = %s")
            params.append(sitio_id)
        else:
            filtros.append("s.subdominio = %s")
            params.append(subdominio)
        if solo_publicado:
            filtros.append("s.estado = 'PUBLICADO'")

        cur.execute(f"""
            SELECT s.*, d.nombre_doctor, d.especialidad, d.telefono_consultorio,
                   d.foto_perfil_url, d.direccion_consultorio, d.maps_url,
                   d.aseguradoras_aceptadas, d.metodos_pago_aceptados,
                   d.horarios_atencion, d.color_tema, d.aviso_consultorio,
                   (d.aviso_activo AND d.aviso_visible_web AND (d.aviso_expira_en IS NULL OR d.aviso_expira_en >= NOW())) AS aviso_activo,
                   d.id_publico
            FROM SITIOS_MEDICOS s
            JOIN DOCTORES d ON d.correo_doctor = s.correo_doctor
            WHERE {' AND '.join(filtros)}
        """, tuple(params))
        sitio = cur.fetchone()
        if not sitio:
            return None
        cur.execute("""
            SELECT nombre_servicio, precio, tipo_precio, descripcion
            FROM CAT_SERVICIOS_CONSULTORIO
            WHERE correo_doctor = %s AND activo = TRUE
            ORDER BY nombre_servicio ASC
        """, (sitio['correo_doctor'],))
        sitio['servicios'] = cur.fetchall()
        cur.execute("""
            SELECT tipo, url, texto_alternativo, titulo, descripcion
            FROM SITIOS_MEDICOS_MEDIA
            WHERE id_sitio = %s AND activo = TRUE
            ORDER BY orden ASC, fecha_creacion ASC
        """, (sitio['id_sitio'],))
        sitio['media'] = cur.fetchall()
        cur.execute("""
            SELECT tipo, titulo, institucion, descripcion, fecha_obtencion, imagen_url
            FROM SITIOS_MEDICOS_CREDENCIALES
            WHERE id_sitio = %s AND activo = TRUE
            ORDER BY orden ASC, fecha_creacion ASC
        """, (sitio['id_sitio'],))
        sitio['credenciales'] = cur.fetchall()
        cur.execute("""
            SELECT red, url
            FROM SITIOS_MEDICOS_REDES
            WHERE id_sitio = %s AND activo = TRUE
            ORDER BY orden ASC
        """, (sitio['id_sitio'],))
        sitio['redes'] = cur.fetchall()
        cur.execute("""
            SELECT palabras_clave, respuesta
            FROM FAQ_CHATBOT
            WHERE (id_doctor_app = %s OR id_doctor_app IS NULL)
              AND activo = TRUE
              AND visible_en_pagina = TRUE
            ORDER BY orden ASC
            LIMIT 6
        """, (sitio['id_publico'],))
        sitio['faqs'] = cur.fetchall()
        sitio['espacio_liberado'] = _obtener_espacios_liberados([sitio['correo_doctor']]).get(sitio['correo_doctor'])
        return sitio
    finally:
        conn.close()


def _registrar_evento(sitio: dict, tipo_evento: str, session_id: str) -> None:
    if tipo_evento not in {'VISITA', *EVENTOS_VALIDOS} or not session_id:
        return
    conn = get_connection()
    if not conn:
        return
    try:
        session_hash = hashlib.sha256(session_id.encode('utf-8')).hexdigest()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO SITIOS_MEDICOS_EVENTOS
                (id_evento, id_sitio, tipo_evento, session_hash, fecha_dia, origen)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id_sitio, tipo_evento, session_hash, fecha_dia) DO NOTHING
        """, (str(uuid.uuid4()), sitio['id_sitio'], tipo_evento, session_hash, date.today(),
              (request.referrer or '')[:500] or None))
        if cur.rowcount:
            consultas_metricas = {
                'VISITA': """
                    INSERT INTO SITIOS_MEDICOS_METRICAS_DIARIAS (id_sitio, fecha, visitas)
                    VALUES (%s, %s, 1)
                    ON CONFLICT (id_sitio, fecha)
                    DO UPDATE SET visitas = SITIOS_MEDICOS_METRICAS_DIARIAS.visitas + 1
                """,
                'CLICK_WHATSAPP': """
                    INSERT INTO SITIOS_MEDICOS_METRICAS_DIARIAS (id_sitio, fecha, clics_whatsapp)
                    VALUES (%s, %s, 1)
                    ON CONFLICT (id_sitio, fecha)
                    DO UPDATE SET clics_whatsapp = SITIOS_MEDICOS_METRICAS_DIARIAS.clics_whatsapp + 1
                """,
                'CLICK_AGENDAR': """
                    INSERT INTO SITIOS_MEDICOS_METRICAS_DIARIAS (id_sitio, fecha, clics_agendar)
                    VALUES (%s, %s, 1)
                    ON CONFLICT (id_sitio, fecha)
                    DO UPDATE SET clics_agendar = SITIOS_MEDICOS_METRICAS_DIARIAS.clics_agendar + 1
                """,
                'CLICK_MAPS': """
                    INSERT INTO SITIOS_MEDICOS_METRICAS_DIARIAS (id_sitio, fecha, clics_maps)
                    VALUES (%s, %s, 1)
                    ON CONFLICT (id_sitio, fecha)
                    DO UPDATE SET clics_maps = SITIOS_MEDICOS_METRICAS_DIARIAS.clics_maps + 1
                """,
                'CLICK_TELEFONO': """
                    INSERT INTO SITIOS_MEDICOS_METRICAS_DIARIAS (id_sitio, fecha, clics_telefono)
                    VALUES (%s, %s, 1)
                    ON CONFLICT (id_sitio, fecha)
                    DO UPDATE SET clics_telefono = SITIOS_MEDICOS_METRICAS_DIARIAS.clics_telefono + 1
                """,
            }
            cur.execute(consultas_metricas[tipo_evento], (sitio['id_sitio'], date.today()))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()


def render_sitio_por_host():
    """Returns a medical site only for a published first-level medical subdomain."""
    subdominio = _subdominio_desde_host(request.host)
    if not subdominio:
        return None
    sitio = _obtener_sitio(subdominio)
    if not sitio:
        return None

    session_id = request.cookies.get(COOKIE_SESION) or uuid.uuid4().hex
    _registrar_evento(sitio, 'VISITA', session_id)
    portal_url = f"https://{PRESENCIA_BASE_DOMAIN}/p/{sitio['id_publico']}"
    whatsapp = _numero_whatsapp_medico(sitio)
    response = make_response(render_template(
        'presencia/sitio.html', sitio=sitio, portal_url=portal_url, whatsapp_numero=whatsapp,
        dominio=PRESENCIA_BASE_DOMAIN,
    ))
    if not request.cookies.get(COOKIE_SESION):
        response.set_cookie(COOKIE_SESION, session_id, max_age=60 * 60 * 24 * 90,
                            secure=request.is_secure, httponly=True, samesite='Lax')
    return response


def _render_home_doko(doctores: list[dict], *, titulo: str, subtitulo: str, descripcion: str,
                      canonical_path: str = '/', etiqueta: str = 'Doko · Tijuana',
                      robots: str = 'index,follow', total_doctores: int | None = None):
    whatsapp_limpio = ''.join(ch for ch in (WHATSAPP_NUMBER or '') if ch.isdigit())
    demo_mensaje = (
        'Hola Doko, quiero solicitar una demostracion para mi consultorio. '
        'Me interesa conocer agenda inteligente, presencia digital y confirmaciones automaticas.'
    )
    return render_template(
        'presencia/home.html',
        doctores=doctores,
        dominio=PRESENCIA_BASE_DOMAIN,
        portal_base=f"https://{PRESENCIA_BASE_DOMAIN}",
        whatsapp_numero=whatsapp_limpio,
        demo_mensaje=demo_mensaje,
        home_title=titulo,
        home_subtitle=subtitulo,
        home_description=descripcion,
        home_canonical=f"https://{PRESENCIA_BASE_DOMAIN}{canonical_path}",
        home_eyebrow=etiqueta,
        home_robots=robots,
        total_doctores=total_doctores if total_doctores is not None else len(doctores),
        seo_local_routes=_listar_rutas_seo_publicadas(),
        show_ginecology_services=canonical_path in {
            '/ginecologia-tijuana', '/colposcopia-tijuana', '/papanicolaou-tijuana'
        },
    )


def _render_directorio_doko(doctores: list[dict], *, titulo: str, subtitulo: str,
                            descripcion: str, canonical_path: str,
                            etiqueta: str = 'Directorio médico local',
                            robots: str = 'index,follow', nombre_busqueda: str = '',
                            especialidad_busqueda: str = ''):
    return render_template(
        'presencia/directorio.html',
        doctores=doctores,
        dominio=PRESENCIA_BASE_DOMAIN,
        portal_base=f"https://{PRESENCIA_BASE_DOMAIN}",
        directory_title=titulo,
        directory_subtitle=subtitulo,
        directory_description=descripcion,
        directory_canonical=f"https://{PRESENCIA_BASE_DOMAIN}{canonical_path}",
        directory_path=canonical_path,
        directory_eyebrow=etiqueta,
        directory_robots=robots,
        search_name=nombre_busqueda,
        search_specialty=especialidad_busqueda,
        seo_local_routes=_listar_rutas_seo_publicadas(),
    )


def render_home_doko():
    """Renderiza la pagina principal de marca solo para el dominio raiz de Doko."""
    if not _es_host_home_doko(request.host):
        return None
    directorio = _obtener_directorio_medico()
    return _render_home_doko(
        directorio[:6],
        titulo='Encuentra especialistas y agenda tu cita en Tijuana',
        subtitulo='Servicios, ubicación y agenda desde un solo lugar',
        descripcion='Encuentra médicos y especialistas en Tijuana, consulta servicios, ubicación, formas de pago y agenda tu cita desde el Portal Doko.',
        total_doctores=len(directorio),
    )


@presencia_bp.route('/medicos-en-tijuana')
def directorio_medicos_tijuana():
    nombre = (request.args.get('nombre') or request.args.get('buscar') or '').strip()
    especialidad = (request.args.get('especialidad') or '').strip()
    terminos = [valor for valor in (nombre, especialidad) if valor] or None
    if especialidad and 'ginecolog' in especialidad.casefold():
        terminos.extend(['gineco', 'ginecóloga', 'ginecólogo'])
    return _render_directorio_doko(
        _obtener_directorio_medico(terminos),
        titulo='Médicos en Tijuana',
        subtitulo='Directorio local de consultorios con Portal Doko',
        descripcion='Encuentra médicos y doctoras en Tijuana con perfil digital, portal de agenda y confirmaciones desde Doko.',
        canonical_path='/medicos-en-tijuana',
        etiqueta='Directorio médico local',
        nombre_busqueda=nombre,
        especialidad_busqueda=especialidad,
    )


@presencia_bp.route('/doctores-en-tijuana')
def directorio_doctores_tijuana():
    return _render_directorio_doko(
        _obtener_directorio_medico(),
        titulo='Doctores en Tijuana',
        subtitulo='Perfiles médicos claros para agendar desde Doko',
        descripcion='Consulta doctores en Tijuana con servicios, ubicación, formas de pago y enlace de agenda desde Doko.',
        canonical_path='/doctores-en-tijuana',
        etiqueta='Doctores · Tijuana',
    )


@presencia_bp.route('/especialistas-en-tijuana')
def directorio_especialistas_tijuana():
    return _render_directorio_doko(
        _obtener_directorio_medico(),
        titulo='Especialistas en Tijuana',
        subtitulo='Encuentra perfiles médicos activos en Doko',
        descripcion='Encuentra especialistas en Tijuana con información del consultorio, servicios disponibles y acceso al Portal Doko para agendar.',
        canonical_path='/especialistas-en-tijuana',
        etiqueta='Especialistas · Tijuana',
    )


@presencia_bp.route('/ginecologia-tijuana')
def directorio_ginecologia_tijuana():
    return _render_directorio_doko(
        _obtener_directorio_medico(['ginecologia', 'gineco', 'ginecóloga', 'colposcopia', 'papanicolaou', 'vph']),
        titulo='Ginecología en Tijuana',
        subtitulo='Doctoras y consultorios ginecológicos en Doko',
        descripcion='Consulta perfiles de ginecología en Tijuana con servicios, educación para pacientes y agenda desde Portal Doko.',
        canonical_path='/ginecologia-tijuana',
        etiqueta='Ginecología · Tijuana',
    )


@presencia_bp.route('/colposcopia-tijuana')
def directorio_colposcopia_tijuana():
    return _render_directorio_doko(
        _obtener_directorio_medico(['colposcopia', 'colposcopista', 'vph', 'papanicolaou']),
        titulo='Colposcopia en Tijuana',
        subtitulo='Perfiles médicos con información educativa y agenda Doko',
        descripcion='Encuentra información y consultorios relacionados con colposcopia en Tijuana. Agenda desde el Portal del Paciente Doko.',
        canonical_path='/colposcopia-tijuana',
        etiqueta='Colposcopia · Tijuana',
    )


@presencia_bp.route('/papanicolaou-tijuana')
def directorio_papanicolaou_tijuana():
    return _render_directorio_doko(
        _obtener_directorio_medico(['papanicolaou', 'citologia', 'vph', 'ginecologia']),
        titulo='Papanicolaou en Tijuana',
        subtitulo='Consultorios con servicios ginecológicos y agenda Doko',
        descripcion='Encuentra consultorios en Tijuana con información sobre papanicolaou y agenda desde el Portal del Paciente Doko.',
        canonical_path='/papanicolaou-tijuana',
        etiqueta='Papanicolaou · Tijuana',
    )


@presencia_bp.route('/<slug>')
def directorio_seo_local(slug):
    if not _es_host_home_doko(request.host) or not SUBDOMINIO_RE.fullmatch(slug or ''):
        abort(404)
    ruta = _obtener_ruta_seo_local(slug=slug, solo_publicada=True)
    if not ruta:
        abort(404)
    doctores = _obtener_directorio_medico(_terminos_ruta_seo(ruta))
    if not doctores:
        abort(404)
    return _render_directorio_doko(
        doctores,
        titulo=ruta['titulo'],
        subtitulo=ruta['subtitulo'],
        descripcion=ruta['descripcion'],
        canonical_path=f"/{ruta['slug']}",
        etiqueta=f"{ruta['especialidad']} · {ruta['ciudad']}",
    )


@presencia_bp.route('/robots.txt')
def robots_txt():
    contenido = f"""User-agent: *
Allow: /
Sitemap: https://{PRESENCIA_BASE_DOMAIN}/sitemap.xml
"""
    return Response(contenido, mimetype='text/plain')


@presencia_bp.route('/sitemap.xml')
def sitemap_xml():
    urls = [
        f"https://{PRESENCIA_BASE_DOMAIN}/",
        f"https://{PRESENCIA_BASE_DOMAIN}/medicos-en-tijuana",
        f"https://{PRESENCIA_BASE_DOMAIN}/doctores-en-tijuana",
        f"https://{PRESENCIA_BASE_DOMAIN}/especialistas-en-tijuana",
        f"https://{PRESENCIA_BASE_DOMAIN}/ginecologia-tijuana",
        f"https://{PRESENCIA_BASE_DOMAIN}/colposcopia-tijuana",
        f"https://{PRESENCIA_BASE_DOMAIN}/papanicolaou-tijuana",
    ]
    for ruta in _listar_rutas_seo_publicadas():
        urls.append(f"https://{PRESENCIA_BASE_DOMAIN}/{ruta['slug']}")
    for doctor in _obtener_directorio_medico():
        if doctor.get('subdominio'):
            urls.append(f"https://{doctor['subdominio']}.{PRESENCIA_BASE_DOMAIN}/")
    items = "\n".join(
        f"  <url><loc>{url}</loc><changefreq>weekly</changefreq><priority>{'1.0' if url.endswith(PRESENCIA_BASE_DOMAIN + '/') else '0.7'}</priority></url>"
        for url in urls
    )
    contenido = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{items}
</urlset>"""
    return Response(contenido, mimetype='application/xml')


def render_seo_local_preview_admin(id_ruta: str):
    ruta = _obtener_ruta_seo_local(id_ruta=id_ruta, solo_publicada=False)
    if not ruta:
        abort(404)
    doctores = _obtener_directorio_medico(_terminos_ruta_seo(ruta))
    return _render_directorio_doko(
        doctores,
        titulo=ruta['titulo'],
        subtitulo=ruta['subtitulo'],
        descripcion=ruta['descripcion'],
        canonical_path=f"/{ruta['slug']}",
        etiqueta=f"Vista previa · {ruta['especialidad']} · {ruta['ciudad']}",
        robots='noindex,nofollow',
    )


def render_sitio_preview_admin(sitio_id: str):
    """Renderiza la misma página médica desde admin, aunque esté en borrador."""
    sitio = _obtener_sitio('', solo_publicado=False, sitio_id=sitio_id)
    if not sitio:
        abort(404)
    portal_url = f"https://{PRESENCIA_BASE_DOMAIN}/p/{sitio['id_publico']}"
    whatsapp = _numero_whatsapp_medico(sitio)
    response = make_response(render_template(
        'presencia/sitio.html', sitio=sitio, portal_url=portal_url, whatsapp_numero=whatsapp,
        dominio=PRESENCIA_BASE_DOMAIN, preview_admin=True,
    ))
    response.headers['Cache-Control'] = 'no-store'
    return response


@presencia_bp.route('/preview/sitio/<sitio_id>')
def render_sitio_preview_publico(sitio_id: str):
    """Vista previa pública por enlace, sin métricas y sin indexación."""
    return render_sitio_preview_admin(sitio_id)


@presencia_bp.route('/privacidad')
def privacidad_doko():
    return render_template('legal/privacidad.html')


@presencia_bp.route('/terminos')
def terminos_doko():
    return render_template('legal/terminos.html')


@presencia_bp.route('/presencia/evento', methods=['POST'])
def registrar_evento_publico():
    subdominio = _subdominio_desde_host(request.host)
    if not subdominio:
        abort(404)
    data = request.get_json(silent=True) or {}
    tipo_evento = (data.get('tipo_evento') or '').strip().upper()
    if tipo_evento not in EVENTOS_VALIDOS:
        return jsonify({'ok': False}), 400
    sitio = _obtener_sitio(subdominio)
    if not sitio:
        abort(404)
    session_id = request.cookies.get(COOKIE_SESION)
    if session_id:
        _registrar_evento(sitio, tipo_evento, session_id)
    return jsonify({'ok': True})

