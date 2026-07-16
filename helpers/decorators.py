from functools import wraps
from flask import session, redirect, url_for


def requiere_rol(*roles_permitidos):
    """Protege rutas internas validando sesión Flask y rol autorizado."""
    def decorador(f):
        @wraps(f)
        def funcion_decorada(*args, **kwargs):
            if not session.get('id_usuario') or session.get('tipo') != 'interno':
                return redirect(url_for('auth_bp.login_interno'))
            # El administrador supervisa y puede operar los módulos internos.
            if session.get('rol') != 'admin' and session.get('rol') not in roles_permitidos:
                return redirect(url_for('auth_bp.acceso_denegado'))
            return f(*args, **kwargs)
        return funcion_decorada
    return decorador


def requiere_doctor(f):
    """Solo para rutas HTML de OAuth2. La PWA usa @requiere_jwt."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('tipo') != 'doctor':
            return redirect(url_for('auth_bp.login_doctor'))
        return f(*args, **kwargs)
    return decorated_function
