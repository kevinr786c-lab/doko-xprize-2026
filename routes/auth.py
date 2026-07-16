import json
import json

import requests
from flask import Blueprint, redirect, request, session, url_for, render_template, jsonify
from google_auth_oauthlib.flow import Flow
from werkzeug.security import check_password_hash
from psycopg2.extras import RealDictCursor

import config_bunker
from helpers.db import get_connection
from helpers.jwt_auth import generar_jwt

auth_bp = Blueprint("auth_bp", __name__)

def _base_url_actual() -> str:
    """Usa el dominio por el que entró el usuario para no mezclar doko.lat con run.app."""
    host = request.headers.get("X-Forwarded-Host") or request.host
    proto = request.headers.get("X-Forwarded-Proto") or request.scheme or "https"
    if config_bunker.IS_CLOUD:
        proto = "https"
    return f"{proto}://{host}".rstrip("/")

def construir_flujo_oauth():
    if not config_bunker.GOOGLE_CLIENT_ID or not config_bunker.GOOGLE_CLIENT_SECRET:
        raise ValueError("GOOGLE_CLIENT_ID y GOOGLE_CLIENT_SECRET deben estar configurados")

    client_config = {
        "web": {
            "client_id": config_bunker.GOOGLE_CLIENT_ID,
            "client_secret": config_bunker.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    redirect_path = "/" + config_bunker.OAUTH_REDIRECT_PATH.strip("/")
    redirect_uri = f"{_base_url_actual()}{redirect_path}"
    if config_bunker.IS_CLOUD and redirect_uri.startswith("http://"):
        redirect_uri = redirect_uri.replace("http://", "https://")

    flow = Flow.from_client_config(
        client_config,
        scopes=config_bunker.OAUTH_SCOPES,
        redirect_uri=redirect_uri
    )
    return flow


def _limpiar_sesion_oauth():
    """Elimina artefactos PKCE/OAuth de la sesión Flask."""
    session.pop("oauth_state", None)
    session.pop("code_verifier", None)
    session.pop("state", None)


def _iniciar_oauth_google():
    """Inicia el flujo OAuth2 de Google. Sin decoradores de sesión previa."""
    try:
        flow = construir_flujo_oauth()
    except ValueError as e:
        base_url = _base_url_actual()
        return render_template(
            "auth/login_interno.html",
            error=str(e),
            base_url=base_url,
            oauth_url=f"{base_url}/login/doctor",
        ), 503

    authorization_kwargs = {
        "access_type": "offline",
        "include_granted_scopes": "true",
    }
    if request.args.get("force_consent") == "1" or request.args.get("reauthorize") == "1":
        authorization_kwargs["prompt"] = "consent"

    authorization_url, state = flow.authorization_url(**authorization_kwargs)

    session["oauth_state"] = state
    session["code_verifier"] = flow.code_verifier
    session.modified = True

    return redirect(authorization_url)


@auth_bp.route("/login/doctor", methods=["GET"])
def login_doctor():
    return _iniciar_oauth_google()


@auth_bp.route("/callback", methods=["GET"])
@auth_bp.route("/oauth2callback", methods=["GET"])
def oauth2callback():
    stored_state = session.get("oauth_state")
    code_verifier = session.get("code_verifier")

    if not stored_state or stored_state != request.args.get("state"):
        _limpiar_sesion_oauth()
        return redirect(url_for("auth_bp.acceso_denegado"))

    if not code_verifier:
        _limpiar_sesion_oauth()
        return redirect(url_for("auth_bp.acceso_denegado"))

    flow = construir_flujo_oauth()
    flow.code_verifier = code_verifier

    authorization_response = request.url
    if config_bunker.IS_CLOUD and authorization_response.startswith("http://"):
        authorization_response = authorization_response.replace("http://", "https://")

    try:
        flow.fetch_token(authorization_response=authorization_response)
    except Exception:
        print("Error OAuth fetch_token")
        _limpiar_sesion_oauth()
        return redirect(url_for("auth_bp.acceso_denegado"))

    _limpiar_sesion_oauth()
    creds = flow.credentials

    userinfo_response = requests.get(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {creds.token}"},
        timeout=10,
    )
    if userinfo_response.status_code != 200:
        return redirect(url_for("auth_bp.acceso_denegado"))
        
    correo_doctor = userinfo_response.json().get("email")
    if not correo_doctor:
        return redirect(url_for("auth_bp.acceso_denegado"))

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT activo, onboarding_completo FROM DOCTORES WHERE correo_doctor = %s", (correo_doctor,))
        doctor = cur.fetchone()

        if not doctor or not doctor["activo"]:
            return redirect(url_for("auth_bp.acceso_denegado"))

        cur.execute("SELECT token_data FROM TOKENS_OAUTH WHERE correo_doctor = %s", (correo_doctor,))
        token_existente = cur.fetchone()
        refresh_token_anterior = None
        if token_existente and token_existente.get("token_data"):
            token_data_anterior = token_existente["token_data"]
            if isinstance(token_data_anterior, str):
                token_data_anterior = json.loads(token_data_anterior)
            refresh_token_anterior = token_data_anterior.get("refresh_token")

        token_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token or refresh_token_anterior,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "scopes": creds.scopes
        }
        
        cur.execute("""
            INSERT INTO TOKENS_OAUTH (correo_doctor, token_data, updated_at) 
            VALUES (%s, %s, NOW())
            ON CONFLICT (correo_doctor) 
            DO UPDATE SET token_data = EXCLUDED.token_data, updated_at = NOW()
        """, (correo_doctor, json.dumps(token_data)))
        
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
            VALUES (%s, %s, %s, %s, %s)
        """, ("LOGIN_DOCTOR", correo_doctor, "doctor", json.dumps({"metodo": "oauth2"}), request.remote_addr))

        conn.commit()
        jwt_token = generar_jwt(correo_doctor)
        onboarding_required = not bool(doctor["onboarding_completo"])

        return render_template(
            "auth/oauth_callback.html",
            jwt=jwt_token,
            onboarding=onboarding_required,
            login_url=f"{_base_url_actual()}{url_for('auth_bp.login_interno')}",
        )

    except Exception:
        if conn: conn.rollback()
        print("Error en oauth2callback")
        return redirect(url_for("auth_bp.acceso_denegado"))
    finally:
        if conn: conn.close()

@auth_bp.route("/login/interno", methods=["GET", "POST"])
def login_interno():
    base_url = _base_url_actual()
    ctx = {
        "base_url": base_url,
        "oauth_url": url_for("auth_bp.login_doctor"),
        "session_tipo": session.get("tipo"),
        "session_rol": session.get("rol"),
        "session_nombre": session.get("nombre"),
        "assistant_mode": request.args.get("asistente") == "1",
    }

    if request.method == "GET":
        return render_template("auth/login_interno.html", **ctx)

    correo = request.form.get("correo")
    password = request.form.get("password")

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id_usuario, nombre, correo, password_hash, rol, activo FROM USUARIOS_INTERNOS WHERE correo = %s", (correo,))
        usuario = cur.fetchone()

        if usuario and usuario["activo"] and check_password_hash(usuario["password_hash"], password):
            session.clear()
            session["tipo"] = "interno"
            session["rol"] = usuario["rol"]
            session["id_usuario"] = str(usuario["id_usuario"])
            session["correo"] = usuario["correo"]
            session["nombre"] = usuario["nombre"]

            cur.execute("INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, ip_origen) VALUES (%s, %s, %s, %s)", ("LOGIN_INTERNO", correo, usuario["rol"], request.remote_addr))
            conn.commit()

            if usuario["rol"] == "admin":
                return redirect(url_for("admin_bp.dashboard"))
            elif usuario["rol"] == "bodeguero":
                return redirect(url_for("bodega_bp.inventario"))
            elif usuario["rol"] == "repartidor":
                return redirect(url_for("reparto_bp.mis_pedidos"))
            elif usuario["rol"] == "asistente":
                return redirect(url_for("auth_bp.login_interno", asistente="1"))
        
        return render_template(
            "auth/login_interno.html",
            error="Credenciales incorrectas o usuario inactivo",
            **ctx,
        )
    finally:
        if conn:
            conn.close()

@auth_bp.route("/logout", methods=["GET"])
def logout():
    es_interno = session.get("tipo") == "interno"
    session.clear()
    if request.headers.get("Accept") == "application/json" or not es_interno:
        return jsonify({"ok": True, "mensaje": "Sesión cerrada"}) 
    return redirect(url_for("auth_bp.login_interno"))

@auth_bp.route("/acceso-denegado")
def acceso_denegado():
    return render_template("auth/acceso_denegado.html")


@auth_bp.route("/asistente/doctoras", methods=["GET"])
def doctoras_asistente():
    if session.get("tipo") != "interno" or session.get("rol") != "asistente" or not session.get("id_usuario"):
        return jsonify({"ok": False, "error": "sesion_asistente_requerida"}), 401

    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT d.correo_doctor, d.nombre_doctor, d.especialidad, d.foto_perfil_url
            FROM ASISTENTES_DOCTORES ad
            JOIN DOCTORES d ON LOWER(TRIM(d.correo_doctor)) = LOWER(TRIM(ad.correo_doctor))
            WHERE ad.id_usuario = %s AND d.activo = TRUE
            ORDER BY d.nombre_doctor
        """, (session["id_usuario"],))
        return jsonify({"ok": True, "doctoras": cur.fetchall()})
    finally:
        conn.close()


@auth_bp.route("/asistente/doctoras/token", methods=["POST"])
def token_doctora_asistente():
    if session.get("tipo") != "interno" or session.get("rol") != "asistente" or not session.get("id_usuario"):
        return jsonify({"ok": False, "error": "sesion_asistente_requerida"}), 401

    data = request.get_json(silent=True) or {}
    correo_doctor = (data.get("correo_doctor") or "").strip().lower()
    if not correo_doctor:
        return jsonify({"ok": False, "error": "selecciona_doctora"}), 400

    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT d.correo_doctor, d.onboarding_completo
            FROM ASISTENTES_DOCTORES ad
            JOIN DOCTORES d ON LOWER(TRIM(d.correo_doctor)) = LOWER(TRIM(ad.correo_doctor))
            WHERE ad.id_usuario = %s
              AND LOWER(TRIM(d.correo_doctor)) = LOWER(TRIM(%s))
              AND d.activo = TRUE
        """, (session["id_usuario"], correo_doctor))
        doctora = cur.fetchone()
        if not doctora:
            return jsonify({"ok": False, "error": "doctora_no_asignada"}), 403

        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            "LOGIN_ASISTENTE_PANEL_DOCTOR",
            session.get("correo"),
            "asistente",
            json.dumps({"correo_doctor": correo_doctor}),
            request.remote_addr,
        ))
        conn.commit()
        return jsonify({
            "ok": True,
            "jwt": generar_jwt(doctora["correo_doctor"], actor_rol="asistente", id_usuario=session["id_usuario"]),
            "onboarding": not bool(doctora["onboarding_completo"]),
        })
    except Exception as exc:
        conn.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    finally:
        conn.close()
