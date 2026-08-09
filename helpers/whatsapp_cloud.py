"""Cliente minimo para enviar mensajes por WhatsApp Cloud API.

El cliente no guarda destinatarios, textos, tokens ni respuestas completas de
Meta. Solo devuelve el resultado minimo que necesita el webhook.
"""

import re

import requests

import config_bunker


_DIGITOS_TELEFONO = re.compile(r"^\d{8,15}$")


def enviar_mensaje_texto(destinatario: str, texto: str) -> dict:
    """Envia un texto corto y devuelve un resultado sin contenido sensible."""
    destinatario = "".join(ch for ch in str(destinatario or "") if ch.isdigit())
    texto = str(texto or "").strip()
    phone_number_id = str(config_bunker.WHATSAPP_PHONE_NUMBER_ID or "").strip()
    access_token = str(config_bunker.WHATSAPP_ACCESS_TOKEN or "").strip()

    if not _DIGITOS_TELEFONO.fullmatch(destinatario):
        return {"ok": False, "categoria": "destinatario_invalido"}
    if not phone_number_id or not access_token:
        return {"ok": False, "categoria": "no_configurado"}
    if not texto:
        return {"ok": False, "categoria": "texto_vacio"}

    version = str(getattr(config_bunker, "WHATSAPP_GRAPH_API_VERSION", "v25.0"))
    url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
    try:
        respuesta = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": destinatario,
                "type": "text",
                "text": {"preview_url": False, "body": texto[:4096]},
            },
            timeout=10,
        )
    except requests.RequestException:
        return {"ok": False, "categoria": "red_no_disponible"}

    if not respuesta.ok:
        return {
            "ok": False,
            "categoria": "api_rechazo",
            "status": respuesta.status_code,
        }

    try:
        datos = respuesta.json()
    except ValueError:
        datos = {}
    mensajes = datos.get("messages") if isinstance(datos, dict) else None
    message_id = None
    if isinstance(mensajes, list) and mensajes and isinstance(mensajes[0], dict):
        message_id = mensajes[0].get("id")
    return {
        "ok": True,
        "categoria": "enviado",
        "status": respuesta.status_code,
        "message_id_present": bool(message_id),
    }
