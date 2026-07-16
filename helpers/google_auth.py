import json
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from config_bunker import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from helpers.db import get_connection

class TokenNoEncontrado(Exception):
    pass

def get_valid_token(correo_doctor: str) -> Credentials:
    """
    Recupera el token OAuth2 del doctor, lo renueva si es necesario,
    lo actualiza en la BD y devuelve el objeto Credentials listo para usar.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT correo_doctor, token_data
            FROM TOKENS_OAUTH
            WHERE LOWER(TRIM(correo_doctor)) = LOWER(TRIM(%s))
            """,
            (correo_doctor,),
        )
        row = cur.fetchone()
        
        if not row:
            raise TokenNoEncontrado(f"No hay registros de token OAuth para: {correo_doctor}")

        correo_token = row[0]
        token_data = row[1]
        if isinstance(token_data, str):
            token_data = json.loads(token_data)

        creds = Credentials(
            token=token_data.get('token'),
            refresh_token=token_data.get('refresh_token'),
            token_uri=token_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=token_data.get('scopes')
        )

        # Si expiró o expira en menos de 5 min (Google Auth maneja ese umbral internamente al hacer refresh)
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as exc:
                raise TokenNoEncontrado(
                    "La cuenta de Google debe reconectarse. El permiso anterior expiró o fue revocado."
                ) from exc
            
            # Guardamos el token fresco en PostgreSQL
            nuevo_token_data = {
                'token': creds.token,
                'refresh_token': creds.refresh_token,
                'token_uri': creds.token_uri,
                'client_id': creds.client_id,
                'scopes': creds.scopes
            }
            cur.execute(
                "UPDATE TOKENS_OAUTH SET token_data = %s, updated_at = NOW() WHERE correo_doctor = %s",
                (json.dumps(nuevo_token_data), correo_token)
            )
            conn.commit()

        return creds

    finally:
        conn.close()
