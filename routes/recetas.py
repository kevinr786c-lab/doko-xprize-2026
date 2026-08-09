import json
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, render_template, request, session
from psycopg2.extras import RealDictCursor

from config_bunker import GCS_BUCKET_NAME
from helpers.db import get_connection
from helpers.decorators import requiere_rol
from helpers.jwt_auth import requiere_jwt
from helpers.storage import subir_archivo


recetas_bp = Blueprint("recetas_bp", __name__)
TZ_TIJUANA = ZoneInfo("America/Tijuana")

PERFIL_PRIVADO_CAMPOS = {
    "nombre_profesional": 180,
    "especialidad_profesional": 180,
    "institucion_titulo": 220,
    "cedula_profesional": 80,
    "cedula_especialidad": 80,
    "rfc": 20,
    "nombre_consultorio": 180,
    "telefono_consultorio": 80,
    "telefono_emergencias": 80,
    "correo_contacto": 180,
    "direccion_impresa": 500,
    "informacion_adicional": 700,
    "logo_url": 1000,
    "emblema_1_url": 1000,
    "emblema_1_nombre": 180,
    "emblema_2_url": 1000,
    "emblema_2_nombre": 180,
}


def _bool_form(data, key, default=False):
    if key not in data:
        return default
    return str(data.get(key) or "").strip().lower() in {"1", "true", "on", "si", "sí"}


def _texto(data, key, limite):
    valor = str(data.get(key) or "").strip()
    return valor[:limite] or None


def _url_imagen_configurada(data, key):
    valor = _texto(data, key, 1000)
    if not valor:
        return None
    parsed = urlparse(valor)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Los recursos visuales deben usar una URL HTTPS válida.")
    ruta_permitida = f"/{GCS_BUCKET_NAME}/"
    if parsed.hostname != "storage.googleapis.com" or not parsed.path.startswith(ruta_permitida):
        raise ValueError("Usa únicamente imágenes cargadas de forma segura en Doko.")
    return valor


def _obtener_configuracion(cur, correo_doctor):
    cur.execute("""
        SELECT d.correo_doctor, d.nombre_doctor, d.especialidad, d.telefono_consultorio,
               d.direccion_consultorio, d.foto_perfil_url, d.color_tema, d.activo,
               s.nombre_clinica_publico, s.especialidad_publica, s.logo_url AS sitio_logo_url,
               s.cedula_profesional AS sugerencia_cedula_profesional,
               s.cedula_especialidad AS sugerencia_cedula_especialidad,
               s.institucion_titulo AS sugerencia_institucion_titulo,
               rc.habilitada, rc.modo_prueba,
               rc.nombre_profesional,
               rc.especialidad_profesional,
               rc.institucion_titulo_privada,
               rc.cedula_profesional_privada,
               rc.cedula_especialidad_privada,
               rc.rfc_privado,
               rc.nombre_consultorio,
               rc.telefono_consultorio AS receta_telefono_consultorio,
               rc.telefono_emergencias,
               rc.correo_publico,
               rc.direccion_publica,
               rc.datos_publicos,
               rc.logo_url AS receta_logo_url,
               rc.emblema_1_url, rc.emblema_1_nombre, rc.emblema_1_autorizado,
               rc.emblema_2_url, rc.emblema_2_nombre, rc.emblema_2_autorizado,
               rc.perfil_profesional_confirmado_en,
               rc.perfil_profesional_confirmado_por,
               rc.actualizado_en
        FROM DOCTORES d
        LEFT JOIN SITIOS_MEDICOS s ON s.correo_doctor = d.correo_doctor
        LEFT JOIN RECETA_CONFIGURACION rc ON rc.correo_doctor = d.correo_doctor
        WHERE LOWER(TRIM(d.correo_doctor)) = LOWER(TRIM(%s))
    """, (correo_doctor,))
    return cur.fetchone()


def _perfil_privado(configuracion):
    return {
        "nombre_profesional": configuracion.get("nombre_profesional") or "",
        "especialidad_profesional": configuracion.get("especialidad_profesional") or "",
        "institucion_titulo": configuracion.get("institucion_titulo_privada") or "",
        "cedula_profesional": configuracion.get("cedula_profesional_privada") or "",
        "cedula_especialidad": configuracion.get("cedula_especialidad_privada") or "",
        "rfc": configuracion.get("rfc_privado") or "",
        "nombre_consultorio": configuracion.get("nombre_consultorio") or "",
        "telefono_consultorio": configuracion.get("receta_telefono_consultorio") or "",
        "telefono_emergencias": configuracion.get("telefono_emergencias") or "",
        "correo_contacto": configuracion.get("correo_publico") or "",
        "direccion_impresa": configuracion.get("direccion_publica") or "",
        "informacion_adicional": configuracion.get("datos_publicos") or "",
        "logo_url": configuracion.get("receta_logo_url") or "",
        "emblema_1_url": configuracion.get("emblema_1_url") or "",
        "emblema_1_nombre": configuracion.get("emblema_1_nombre") or "",
        "emblema_1_autorizado": bool(configuracion.get("emblema_1_autorizado")),
        "emblema_2_url": configuracion.get("emblema_2_url") or "",
        "emblema_2_nombre": configuracion.get("emblema_2_nombre") or "",
        "emblema_2_autorizado": bool(configuracion.get("emblema_2_autorizado")),
    }


def _sugerencias_publicas(configuracion):
    return {
        "nombre_profesional": configuracion.get("nombre_doctor") or "",
        "especialidad_profesional": (
            configuracion.get("especialidad_publica") or configuracion.get("especialidad") or ""
        ),
        "institucion_titulo": configuracion.get("sugerencia_institucion_titulo") or "",
        "cedula_profesional": configuracion.get("sugerencia_cedula_profesional") or "",
        "cedula_especialidad": configuracion.get("sugerencia_cedula_especialidad") or "",
        "rfc": "",
        "nombre_consultorio": configuracion.get("nombre_clinica_publico") or "",
        "telefono_consultorio": configuracion.get("telefono_consultorio") or "",
        "telefono_emergencias": "",
        "correo_contacto": configuracion.get("correo_doctor") or "",
        "direccion_impresa": configuracion.get("direccion_consultorio") or "",
        "informacion_adicional": "",
        "logo_url": configuracion.get("sitio_logo_url") or configuracion.get("foto_perfil_url") or "",
        "emblema_1_url": "",
        "emblema_1_nombre": "",
        "emblema_1_autorizado": False,
        "emblema_2_url": "",
        "emblema_2_nombre": "",
        "emblema_2_autorizado": False,
    }


def _validar_perfil_payload(data):
    perfil = {campo: _texto(data, campo, limite) for campo, limite in PERFIL_PRIVADO_CAMPOS.items()}
    perfil["rfc"] = (perfil.get("rfc") or "").upper() or None
    perfil["logo_url"] = _url_imagen_configurada(data, "logo_url")
    perfil["emblema_1_url"] = _url_imagen_configurada(data, "emblema_1_url")
    perfil["emblema_2_url"] = _url_imagen_configurada(data, "emblema_2_url")
    perfil["emblema_1_autorizado"] = _bool_form(data, "emblema_1_autorizado")
    perfil["emblema_2_autorizado"] = _bool_form(data, "emblema_2_autorizado")
    if perfil["emblema_1_url"] and not perfil["emblema_1_autorizado"]:
        raise ValueError("Confirma que cuentas con autorización para usar el primer emblema.")
    if perfil["emblema_2_url"] and not perfil["emblema_2_autorizado"]:
        raise ValueError("Confirma que cuentas con autorización para usar el segundo emblema.")
    return perfil


def _campos_modificados(anterior, nuevo):
    return sorted(
        campo for campo in nuevo
        if str(anterior.get(campo) or "").strip() != str(nuevo.get(campo) or "").strip()
    )


def _perfil_minimo_completo(perfil):
    return bool(perfil.get("nombre_profesional") and perfil.get("cedula_profesional"))


def _guardar_perfil_privado(cur, correo_doctor, perfil, actor, confirmar=False):
    cur.execute("""
        UPDATE RECETA_CONFIGURACION SET
            nombre_profesional = %s,
            especialidad_profesional = %s,
            institucion_titulo_privada = %s,
            cedula_profesional_privada = %s,
            cedula_especialidad_privada = %s,
            rfc_privado = %s,
            nombre_consultorio = %s,
            telefono_consultorio = %s,
            telefono_emergencias = %s,
            correo_publico = %s,
            direccion_publica = %s,
            datos_publicos = %s,
            logo_url = %s,
            emblema_1_url = %s,
            emblema_1_nombre = %s,
            emblema_1_autorizado = %s,
            emblema_2_url = %s,
            emblema_2_nombre = %s,
            emblema_2_autorizado = %s,
            perfil_profesional_confirmado_en = CASE WHEN %s THEN NOW() ELSE NULL END,
            perfil_profesional_confirmado_por = CASE WHEN %s THEN %s ELSE NULL END,
            actualizado_en = NOW(),
            actualizado_por = %s
        WHERE correo_doctor = %s
    """, (
        perfil["nombre_profesional"], perfil["especialidad_profesional"],
        perfil["institucion_titulo"], perfil["cedula_profesional"],
        perfil["cedula_especialidad"], perfil["rfc"], perfil["nombre_consultorio"],
        perfil["telefono_consultorio"], perfil["telefono_emergencias"],
        perfil["correo_contacto"], perfil["direccion_impresa"],
        perfil["informacion_adicional"], perfil["logo_url"],
        perfil["emblema_1_url"], perfil["emblema_1_nombre"],
        perfil["emblema_1_autorizado"] if perfil["emblema_1_url"] else False,
        perfil["emblema_2_url"], perfil["emblema_2_nombre"],
        perfil["emblema_2_autorizado"] if perfil["emblema_2_url"] else False,
        confirmar, confirmar, actor, actor, correo_doctor,
    ))


def _auditar_cambios(cur, tipo, actor, rol, correo_doctor, campos):
    cur.execute("""
        INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        tipo, actor, rol,
        json.dumps({"correo_doctor": correo_doctor, "campos_modificados": campos}),
        request.remote_addr,
    ))


def _acceso_doctor_recetas(cur):
    if getattr(request, "jwt_actor_rol", None) != "doctor":
        return None, (jsonify({"ok": False, "error": "Las recetas son exclusivas de la doctora."}), 403)
    configuracion = _obtener_configuracion(cur, getattr(request, "correo_doctor", None))
    if not configuracion or not configuracion.get("activo") or not configuracion.get("habilitada"):
        return None, (jsonify({"ok": False, "error": "El módulo de recetas no está habilitado."}), 403)
    return configuracion, None


@recetas_bp.route("/admin/doctores/<path:correo_doctor>/recetas", methods=["GET"])
@requiere_rol("admin")
def configurar_receta(correo_doctor):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        configuracion = _obtener_configuracion(cur, correo_doctor)
        if not configuracion:
            return "Doctora no encontrada.", 404
        return render_template("admin/receta_configuracion.html", receta=configuracion)
    finally:
        conn.close()


@recetas_bp.route("/admin/doctores/<path:correo_doctor>/recetas", methods=["POST"])
@requiere_rol("admin")
def guardar_configuracion_receta(correo_doctor):
    data = request.get_json(silent=True) if request.is_json else request.form.to_dict()
    data = data or {}
    try:
        perfil = _validar_perfil_payload(data)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        configuracion = _obtener_configuracion(cur, correo_doctor)
        if not configuracion:
            return jsonify({"ok": False, "error": "Doctora no encontrada."}), 404
        habilitada = _bool_form(data, "habilitada")
        if habilitada and not configuracion.get("activo"):
            return jsonify({"ok": False, "error": "Activa primero la cuenta médica."}), 400

        anterior = _perfil_privado(configuracion)
        cur.execute("""
            INSERT INTO RECETA_CONFIGURACION (correo_doctor, habilitada, modo_prueba, actualizado_por)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (correo_doctor) DO UPDATE SET
                habilitada = EXCLUDED.habilitada,
                modo_prueba = EXCLUDED.modo_prueba,
                actualizado_en = NOW(),
                actualizado_por = EXCLUDED.actualizado_por
        """, (correo_doctor, habilitada, _bool_form(data, "modo_prueba"), session.get("correo", "admin")))
        perfil_confirmado = _perfil_minimo_completo(perfil)
        _guardar_perfil_privado(
            cur, correo_doctor, perfil, session.get("correo", "admin"),
            confirmar=perfil_confirmado,
        )
        campos = _campos_modificados(anterior, perfil)
        if bool(configuracion.get("habilitada")) != habilitada:
            campos.append("habilitada")
        _auditar_cambios(
            cur,
            "RECETA_MODULO_ACTIVADO" if habilitada and not configuracion.get("habilitada")
            else "RECETA_MODULO_DESACTIVADO" if not habilitada and configuracion.get("habilitada")
            else "RECETA_CONFIGURACION_ACTUALIZADA",
            session.get("correo", "admin"), "admin", correo_doctor, sorted(set(campos)),
        )
        conn.commit()
        return jsonify({
            "ok": True,
            "habilitada": habilitada,
            "perfil_profesional_confirmado": perfil_confirmado,
        })
    except Exception as exc:
        conn.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    finally:
        conn.close()


def _subir_recurso():
    archivo = request.files.get("file")
    if not archivo:
        return jsonify({"ok": False, "error": "Selecciona una imagen."}), 400
    try:
        url = subir_archivo(archivo.read(), archivo.filename, "doctores")
        return jsonify({"ok": True, "url": url})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@recetas_bp.route("/admin/doctores/recetas/upload", methods=["POST"])
@requiere_rol("admin")
def subir_recurso_receta():
    return _subir_recurso()


@recetas_bp.route("/panel/recetas/perfil-profesional", methods=["GET"])
@requiere_jwt
def perfil_profesional_receta():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        configuracion, error = _acceso_doctor_recetas(cur)
        if error:
            return error
        return jsonify({
            "ok": True,
            "confirmado": bool(configuracion.get("perfil_profesional_confirmado_en")),
            "perfil": _perfil_privado(configuracion),
            "sugerencias": _sugerencias_publicas(configuracion),
        })
    finally:
        conn.close()


@recetas_bp.route("/panel/recetas/perfil-profesional", methods=["PATCH"])
@requiere_jwt
def guardar_perfil_profesional_receta():
    data = request.get_json(silent=True) or {}
    try:
        perfil = _validar_perfil_payload(data)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if not _perfil_minimo_completo(perfil):
        return jsonify({
            "ok": False,
            "error": "Completa al menos el nombre profesional y la cédula profesional.",
        }), 400

    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        configuracion, error = _acceso_doctor_recetas(cur)
        if error:
            return error
        anterior = _perfil_privado(configuracion)
        actor = getattr(request, "correo_doctor", "doctor")
        _guardar_perfil_privado(
            cur, configuracion["correo_doctor"], perfil, actor, confirmar=True,
        )
        _auditar_cambios(
            cur, "RECETA_PERFIL_PROFESIONAL_ACTUALIZADO", actor, "doctor",
            configuracion["correo_doctor"], _campos_modificados(anterior, perfil),
        )
        conn.commit()
        return jsonify({"ok": True, "perfil": perfil, "confirmado": True})
    except Exception as exc:
        conn.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    finally:
        conn.close()


@recetas_bp.route("/panel/recetas/recursos", methods=["POST"])
@requiere_jwt
def subir_recurso_receta_panel():
    tipo = str(request.form.get("tipo") or "").strip()
    if tipo not in {"logo_url", "emblema_1_url", "emblema_2_url"}:
        return jsonify({"ok": False, "error": "Tipo de recurso no permitido."}), 400
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        _, error = _acceso_doctor_recetas(cur)
        if error:
            return error
    finally:
        conn.close()
    return _subir_recurso()


@recetas_bp.route("/panel/recetas/configuracion", methods=["GET"])
@requiere_jwt
def configuracion_receta_panel():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        configuracion, error = _acceso_doctor_recetas(cur)
        if error:
            return error
        perfil = _perfil_privado(configuracion)
        emblemas = []
        for numero in (1, 2):
            if perfil[f"emblema_{numero}_url"] and perfil[f"emblema_{numero}_autorizado"]:
                emblemas.append({
                    "url": perfil[f"emblema_{numero}_url"],
                    "nombre": perfil[f"emblema_{numero}_nombre"] or "Emblema institucional",
                })
        return jsonify({
            "ok": True,
            "fecha_tijuana": datetime.now(TZ_TIJUANA).date().isoformat(),
            "perfil_profesional_confirmado": bool(configuracion.get("perfil_profesional_confirmado_en")),
            "configuracion": {
                "nombre_doctor": perfil["nombre_profesional"],
                "especialidad": perfil["especialidad_profesional"],
                "cedula_profesional": perfil["cedula_profesional"],
                "cedula_especialidad": perfil["cedula_especialidad"],
                "institucion_titulo": perfil["institucion_titulo"],
                "rfc": perfil["rfc"],
                "nombre_consultorio": perfil["nombre_consultorio"],
                "telefono_consultorio": perfil["telefono_consultorio"],
                "telefono_emergencias": perfil["telefono_emergencias"],
                "correo_publico": perfil["correo_contacto"],
                "direccion_publica": perfil["direccion_impresa"],
                "datos_publicos": perfil["informacion_adicional"],
                "logo_url": perfil["logo_url"],
                "emblemas": emblemas,
                "color_tema": configuracion.get("color_tema") or "marino",
                "modo_prueba": bool(configuracion.get("modo_prueba")),
            },
        })
    finally:
        conn.close()
