import json
from datetime import timedelta
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config_bunker
from helpers.google_auth import get_valid_token


TZ_TIJUANA = ZoneInfo("America/Tijuana")
MARKER_PREFIX = "DOKO_EVENTO:"


def _error_scopes_insuficientes(exc: HttpError) -> bool:
    return exc.resp.status == 403 and "insufficient" in str(exc).lower()


def _mensaje_reautorizar_google(correo_doctor: str) -> str:
    url = f"{config_bunker.BASE_URL.rstrip('/')}/login/doctor?force_consent=1"
    return (
        "Google Calendar no autorizó crear o modificar eventos para esta doctora. "
        f"Vuelve a conectar Google con la cuenta {correo_doctor} desde: {url}"
    )


def _service(correo_doctor: str):
    return build("calendar", "v3", credentials=get_valid_token(correo_doctor), cache_discovery=False)


def construir_marcador_doko(id_radar: str, tipo_evento: str, origen: str = "doko") -> str:
    return f"{MARKER_PREFIX}{json.dumps({'id_radar': str(id_radar), 'tipo_evento': tipo_evento, 'origen': origen}, ensure_ascii=False)}"


def leer_marcador_doko(description: str) -> dict | None:
    texto = description or ""
    idx = texto.find(MARKER_PREFIX)
    if idx < 0:
        return None
    payload = texto[idx + len(MARKER_PREFIX):].splitlines()[0].strip()
    try:
        data = json.loads(payload)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def crear_evento_doko(
    *,
    correo_doctor: str,
    id_radar: str,
    tipo_evento: str,
    titulo: str,
    inicio,
    duracion_minutos: int,
    descripcion: str = "",
    paciente_correo: str | None = None,
):
    fin = inicio + timedelta(minutes=duracion_minutos)
    marcador = construir_marcador_doko(id_radar, tipo_evento)
    descripcion_final = "\n".join([parte for parte in [descripcion.strip(), marcador] if parte])
    body = {
        "summary": titulo,
        "description": descripcion_final,
        "start": {"dateTime": inicio.replace(tzinfo=TZ_TIJUANA).isoformat(), "timeZone": "America/Tijuana"},
        "end": {"dateTime": fin.replace(tzinfo=TZ_TIJUANA).isoformat(), "timeZone": "America/Tijuana"},
        "transparency": "opaque",
    }
    if paciente_correo:
        body["attendees"] = [{"email": paciente_correo}]
    try:
        return _service(correo_doctor).events().insert(
            calendarId=correo_doctor,
            body=body,
            sendUpdates="none",
        ).execute()
    except HttpError as exc:
        if _error_scopes_insuficientes(exc):
            raise PermissionError(_mensaje_reautorizar_google(correo_doctor)) from exc
        raise


def marcar_evento_confirmado_doko(correo_doctor: str, google_event_id: str) -> bool:
    if not google_event_id:
        return False
    try:
        service = _service(correo_doctor)
        evento = service.events().get(calendarId=correo_doctor, eventId=google_event_id).execute()
        titulo_actual = (evento.get("summary") or "Cita").strip()
        if titulo_actual.lower().startswith("confirmada"):
            return True
        service.events().patch(
            calendarId=correo_doctor,
            eventId=google_event_id,
            body={"summary": f"Confirmada - {titulo_actual}"},
            sendUpdates="none",
        ).execute()
        return True
    except HttpError as exc:
        if _error_scopes_insuficientes(exc):
            raise PermissionError(_mensaje_reautorizar_google(correo_doctor)) from exc
        if exc.resp.status in {404, 410}:
            return False
        raise


def actualizar_evento_doko(
    *,
    correo_doctor: str,
    google_event_id: str,
    id_radar: str,
    tipo_evento: str,
    titulo: str,
    inicio,
    duracion_minutos: int,
    descripcion: str = "",
    paciente_correo: str | None = None,
):
    if not google_event_id:
        return False
    fin = inicio + timedelta(minutes=duracion_minutos)
    marcador = construir_marcador_doko(id_radar, tipo_evento)
    descripcion_final = "\n".join([parte for parte in [descripcion.strip(), marcador] if parte])
    body = {
        "summary": titulo,
        "description": descripcion_final,
        "start": {"dateTime": inicio.replace(tzinfo=TZ_TIJUANA).isoformat(), "timeZone": "America/Tijuana"},
        "end": {"dateTime": fin.replace(tzinfo=TZ_TIJUANA).isoformat(), "timeZone": "America/Tijuana"},
        "transparency": "opaque",
    }
    body["attendees"] = [{"email": paciente_correo}] if paciente_correo else []
    try:
        _service(correo_doctor).events().patch(
            calendarId=correo_doctor,
            eventId=google_event_id,
            body=body,
            sendUpdates="none",
        ).execute()
        return True
    except HttpError as exc:
        if _error_scopes_insuficientes(exc):
            raise PermissionError(_mensaje_reautorizar_google(correo_doctor)) from exc
        if exc.resp.status in {404, 410}:
            return False
        raise


def borrar_evento_doko(correo_doctor: str, google_event_id: str) -> bool:
    if not google_event_id:
        return True
    try:
        _service(correo_doctor).events().delete(calendarId=correo_doctor, eventId=google_event_id).execute()
        return True
    except HttpError as exc:
        if _error_scopes_insuficientes(exc):
            raise PermissionError(_mensaje_reautorizar_google(correo_doctor)) from exc
        if exc.resp.status in {404, 410}:
            return True
        raise
