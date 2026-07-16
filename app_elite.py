import os
import hmac
import secrets

# CONFIGURACIÓN DE SEGURIDAD DOKO
if os.environ.get('K_SERVICE') is None:
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

from flask import Flask, redirect, send_from_directory, url_for, session, request, jsonify
from flask_cors import CORS

# Importamos IS_CLOUD para flexibilizar la cookie en el entorno local
from config_bunker import SECRET_KEY, IS_CLOUD, BASE_URL, validar_configuracion_produccion

# ==============================================================================
# IMPORTACIÓN DE MÓDULOS (Blueprints)
# ==============================================================================
from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.bodega import bodega_bp
from routes.reparto import reparto_bp
from routes.panel import panel_bp
from routes.publico import publico_bp
from routes.confirmacion import confirmacion_bp
from routes.jobs import jobs_bp
from routes.presencia import presencia_bp, render_home_doko, render_sitio_por_host
from routes.implementacion import implementacion_bp

# Inicialización de la aplicación
validar_configuracion_produccion()
app = Flask(__name__)
app.secret_key = SECRET_KEY

def _crear_csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
        session.modified = True
    return token


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": _crear_csrf_token}


@app.before_request
def proteger_csrf_interno():
    """Protege acciones internas con sesion sin tocar APIs publicas ni JWT medico."""
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None

    path = request.path or ""
    rutas_exentas = {
        "/login/interno",
    }
    prefijos_exentos = (
        "/jobs/",
        "/panel/",
        "/p/",
        "/c/",
        "/presencia/evento",
    )
    if path in rutas_exentas or any(path.startswith(prefijo) for prefijo in prefijos_exentos):
        return None

    if session.get("tipo") != "interno":
        return None

    esperado = session.get("_csrf_token")
    recibido = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
    if esperado and recibido and hmac.compare_digest(str(esperado), str(recibido)):
        return None

    if request.accept_mimetypes.best == "application/json" or request.headers.get("X-Requested-With"):
        return jsonify({"ok": False, "error": "csrf_invalido"}), 403
    return "Acceso denegado.", 403
#  SOLUCIÓN DE SEGURIDAD PARA EL CROSS-ORIGIN
@app.after_request
def add_security_headers(response):
    # Esto permite que su página principal y el popup se comuniquen sin bloqueos
    response.headers['Cross-Origin-Opener-Policy'] = 'same-origin-allow-popups'
    response.headers['Cross-Origin-Embedder-Policy'] = 'unsafe-none'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    return response
# ==============================================================================
# CONFIGURACIÓN DE SEGURIDAD (Reglas v9.2)
# ==============================================================================
# Si estamos en Cloud pide HTTPS obligatorio, en local permite HTTP
app.config['SESSION_COOKIE_SECURE'] = IS_CLOUD
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

allowed_origins = [
    BASE_URL.rstrip("/"),
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]

# CORS estricto: dominio activo de Doko y entorno de desarrollo local permitidos
CORS(app, resources={
    r"/panel/*": {"origins": allowed_origins},
    r"/login/doctor": {"origins": allowed_origins},
})

# ==============================================================================
# REGISTRO DE BLUEPRINTS (Rutas del sistema)
# ==============================================================================
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(bodega_bp)
app.register_blueprint(reparto_bp)
app.register_blueprint(panel_bp)
app.register_blueprint(publico_bp)
app.register_blueprint(confirmacion_bp)
app.register_blueprint(jobs_bp)
app.register_blueprint(presencia_bp)
app.register_blueprint(implementacion_bp)

# ==============================================================================
# ENRUTAMIENTO BASE
# ==============================================================================
@app.route('/')
def index():
    sitio = render_sitio_por_host()
    if sitio is not None:
        return sitio
    home = render_home_doko()
    if home is not None:
        return home
    """Redirección por defecto al búnker operativo interno."""
    return redirect(url_for('auth_bp.login_interno'))


@app.route('/sw.js')
def service_worker():
    """Entrega el worker desde la ra\u00edz para que cubra toda la aplicaci\u00f3n PWA."""
    response = app.make_response(send_from_directory(app.static_folder, 'sw.js'))
    response.headers['Cache-Control'] = 'no-cache'
    response.mimetype = 'application/javascript'
    return response

# ==============================================================================
# EJECUCIÓN DEL SERVIDOR
# ==============================================================================
if __name__ == '__main__':
    # Puerto 8080 estándar para despliegues en Google Cloud Run
    puerto = int(os.environ.get('PORT', 8080))
    # Host 0.0.0.0 es necesario para que Docker exponga el puerto correctamente
    app.run(debug=True, host='0.0.0.0', port=puerto)

