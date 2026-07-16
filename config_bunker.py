import os
from pathlib import Path

from dotenv import load_dotenv

# Carga variables locales (.env estándar o Plaintext del búnker)
_raiz = Path(__file__).resolve().parent
load_dotenv(_raiz / '.env')
load_dotenv(_raiz / '.env' / 'Plaintext')

# Detección de entorno: Cloud Run vs Local
IS_CLOUD = os.environ.get('K_SERVICE') is not None

# Configuración Base de Datos
DB_HOST = os.environ.get('DB_HOST') or (
    '/cloudsql/kb-system-elite:us-central1:kb-elite-db-01'
    if IS_CLOUD else '127.0.0.1'
)

DB_CONFIG = {
    'dbname': os.environ.get('DB_NAME', 'postgres'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
    'host': DB_HOST,
    'port': os.environ.get('DB_PORT', '5432')
}

# Seguridad y Secretos Generales
SECRET_KEY = os.environ.get('SECRET_KEY', 'bunker_dev_secret_key')
JOB_SECRET = os.environ.get('JOB_SECRET', 'bunker_dev_job_secret')
JWT_SECRET = os.environ.get('JWT_SECRET', 'bunker_dev_jwt_secret')
JWT_EXPIRATION_HOURS = int(os.environ.get('JWT_EXPIRATION_HOURS', 24))
DB_POOL_MIN = int(os.environ.get('DB_POOL_MIN', '1'))
DB_POOL_MAX = int(os.environ.get('DB_POOL_MAX', '8'))
GEMINI_DAILY_REQUEST_LIMIT = int(os.environ.get('GEMINI_DAILY_REQUEST_LIMIT', '250'))
PANEL_ASSISTANT_GEMINI_CLINIC_DAILY_LIMIT = int(
    os.environ.get('PANEL_ASSISTANT_GEMINI_CLINIC_DAILY_LIMIT', '50')
)
PANEL_ASSISTANT_GEMINI_ACTOR_HOURLY_LIMIT = int(
    os.environ.get('PANEL_ASSISTANT_GEMINI_ACTOR_HOURLY_LIMIT', '20')
)
PANEL_ASSISTANT_GEMINI_GLOBAL_DAILY_LIMIT = int(
    os.environ.get('PANEL_ASSISTANT_GEMINI_GLOBAL_DAILY_LIMIT', '500')
)
PANEL_ASSISTANT_GEMINI_COOLDOWN_SECONDS = int(
    os.environ.get('PANEL_ASSISTANT_GEMINI_COOLDOWN_SECONDS', '2')
)
PANEL_ASSISTANT_GEMINI_MAX_OUTPUT_TOKENS = int(
    os.environ.get('PANEL_ASSISTANT_GEMINI_MAX_OUTPUT_TOKENS', '48')
)
IMPLEMENTATION_AI_CLINIC_DAILY_LIMIT = int(
    os.environ.get('IMPLEMENTATION_AI_CLINIC_DAILY_LIMIT', '20')
)
IMPLEMENTATION_AI_GLOBAL_DAILY_LIMIT = int(
    os.environ.get('IMPLEMENTATION_AI_GLOBAL_DAILY_LIMIT', '100')
)
IMPLEMENTATION_AI_COOLDOWN_SECONDS = int(
    os.environ.get('IMPLEMENTATION_AI_COOLDOWN_SECONDS', '2')
)
IMPLEMENTATION_AI_MAX_INPUT_CHARS = int(
    os.environ.get('IMPLEMENTATION_AI_MAX_INPUT_CHARS', '2500')
)
IMPLEMENTATION_AI_MAX_OUTPUT_TOKENS = int(
    os.environ.get('IMPLEMENTATION_AI_MAX_OUTPUT_TOKENS', '350')
)
PANEL_ASSISTANT_SEARCH_DOCTORS = {
    correo.strip().lower()
    for correo in os.environ.get(
        'PANEL_ASSISTANT_SEARCH_DOCTORS',
        '*',
    ).split(',')
    if correo.strip()
}
GEMINI_INPUT_USD_PER_MILLION = float(
    os.environ.get('GEMINI_INPUT_USD_PER_MILLION', '0.30')
)
GEMINI_OUTPUT_USD_PER_MILLION = float(
    os.environ.get('GEMINI_OUTPUT_USD_PER_MILLION', '2.50')
)

# Google y Gemini
GOOGLE_CLIENT_ID = os.environ.get('CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('CLIENT_SECRET', '')
GEMINI_PROJECT_ID = os.environ.get('GEMINI_PROJECT_ID', 'kb-system-elite')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')
AI_PROVIDER = os.environ.get('AI_PROVIDER', 'gemini_api' if GEMINI_API_KEY else 'vertex').lower()
GCS_BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME', 'mydoko-storage')
GOOGLE_KEY_PATH = 'google-key.json'
# SCOPES OPERATIVOS COMPATIBLES CON LA CONSOLA (SIN CALENDAR.EVENTS NI MODIFY)
# --- CONFIGURACIÓN DE SCOPES REQUERIDA POR ROUTES/AUTH v9.2 ---
OAUTH_SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid'
]
# Operación de Negocio
WHATSAPP_NUMBER = os.environ.get('WHATSAPP_NUMBER', '')
BASE_URL = os.environ.get('BASE_URL', 'http://localhost:8080')
OAUTH_REDIRECT_PATH = os.environ.get('OAUTH_REDIRECT_PATH', '/oauth2callback')
PRESENCIA_BASE_DOMAIN = os.environ.get('PRESENCIA_BASE_DOMAIN', 'doko.lat').strip().lower()
PORTAL_BASE_URL = os.environ.get('PORTAL_BASE_URL', BASE_URL).rstrip('/')


def validar_configuracion_produccion() -> None:
    """Detiene el arranque de Cloud Run si faltan secretos esenciales."""
    if not IS_CLOUD:
        return

    requeridos = {
        'SECRET_KEY': SECRET_KEY,
        'JOB_SECRET': JOB_SECRET,
        'JWT_SECRET': JWT_SECRET,
        'DB_PASSWORD': os.environ.get('DB_PASSWORD'),
        'CLIENT_ID': GOOGLE_CLIENT_ID,
        'CLIENT_SECRET': GOOGLE_CLIENT_SECRET,
    }
    valores_inseguros = {
        'bunker_dev_secret_key',
        'bunker_dev_job_secret',
        'bunker_dev_jwt_secret',
        'desarrollo123',
    }
    faltantes = [nombre for nombre, valor in requeridos.items() if not valor or valor in valores_inseguros]
    if faltantes:
        raise RuntimeError('Faltan secretos de producción: ' + ', '.join(faltantes))
    if not BASE_URL.startswith('https://'):
        raise RuntimeError('BASE_URL debe usar HTTPS en Cloud Run.')

def escanear_bunker():
    """Muestra el estado de la configuración sin exponer contraseñas."""
    print("\n" + "="*35)
    print("🚀 KB-TECH BUNKER STATUS v9.1")
    print("="*35)
    print(f"[*] Entorno Cloud:    {IS_CLOUD}")
    print(f"[*] Host DB:          {DB_HOST}")
    print(f"[*] GCS Bucket:       {GCS_BUCKET_NAME}")
    print(f"[*] WhatsApp PWA:     {WHATSAPP_NUMBER or 'NO CONFIGURADO (Botón Oculto)'}")
    print("="*35 + "\n")

if __name__ == '__main__':
    escanear_bunker()
