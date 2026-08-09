"""Entrada segura para WhatsApp Cloud API.

La primera etapa verifica el webhook y responde solo al numero de prueba
autorizado. No guarda mensajes, telefonos, nombres ni texto de pacientes.
"""

import hashlib
import hmac
import logging

from flask import Blueprint, Response, jsonify, request

import config_bunker
from agentes.asistente_whatsapp import clasificar_intencion, construir_respuesta
from helpers.whatsapp_cloud import enviar_mensaje_texto


whatsapp_bp = Blueprint("whatsapp_bp", __name__)
logger = logging.getLogger(__name__)


def _telefono_normalizado(valor: str) -> str:
    return "".join(ch for ch in str(valor or "") if ch.isdigit())


def _extraer_mensaje(payload: dict):
    """Extrae solo el primer texto necesario para la prueba y lo trunca."""
    try:
        cambio = payload["entry"][0]["changes"][0]
        valor = cambio["value"]
        mensajes = valor.get("messages") or []
        mensaje = mensajes[0] if mensajes else {}
        texto = mensaje.get("text", {}).get("body")
        remitente = mensaje.get("from")
        phone_number_id = valor.get("metadata", {}).get("phone_number_id")
    except (AttributeError, IndexError, KeyError, TypeError):
        return None
    if mensaje.get("type") != "text" or not texto or not remitente or not phone_number_id:
        return None
    return str(phone_number_id), str(remitente), str(texto)[:500]


def _firma_valida(cuerpo: bytes) -> bool:
    secreto = str(config_bunker.WHATSAPP_APP_SECRET or "")
    if not secreto:
        return False

    recibida = request.headers.get("X-Hub-Signature-256", "")
    if not recibida.startswith("sha256="):
        return False

    esperada = hmac.new(secreto.encode("utf-8"), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(recibida[7:], esperada)


@whatsapp_bp.route("/webhooks/whatsapp", methods=["GET"])
def verificar_webhook_whatsapp():
    """Responde al reto de verificación que envía Meta."""
    modo = request.args.get("hub.mode", "")
    token = request.args.get("hub.verify_token", "")
    reto = request.args.get("hub.challenge", "")
    esperado = str(config_bunker.WHATSAPP_VERIFY_TOKEN or "")

    if modo == "subscribe" and reto and esperado and hmac.compare_digest(token, esperado):
        return Response(reto, status=200, mimetype="text/plain")

    return jsonify(ok=False, error="verificacion_webhook_fallida"), 403


@whatsapp_bp.route("/webhooks/whatsapp", methods=["POST"])
def recibir_webhook_whatsapp():
    """Acepta un evento sin conservar su contenido sensible."""
    cuerpo = request.get_data(cache=True)
    if not _firma_valida(cuerpo):
        return jsonify(ok=False, error="firma_webhook_invalida"), 403

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(ok=False, error="cuerpo_json_invalido"), 400
    if payload.get("object") != "whatsapp_business_account":
        return jsonify(ok=False, error="objeto_webhook_no_soportado"), 400

    # No registrar payload, texto, teléfonos, nombres ni identificadores.
    mensaje = _extraer_mensaje(payload)
    if mensaje and config_bunker.WHATSAPP_RESPONDER_ACTIVO:
        phone_number_id, destinatario, texto = mensaje
        phone_id_configurado = str(config_bunker.WHATSAPP_PHONE_NUMBER_ID or "")
        cuenta_correcta = not phone_id_configurado or phone_number_id == phone_id_configurado
        destinatarios_permitidos = {
            _telefono_normalizado(item)
            for item in config_bunker.WHATSAPP_TEST_RECIPIENTS
        }
        destinatario_permitido = (
            _telefono_normalizado(destinatario) in destinatarios_permitidos
        )
        logger.info(
            "WhatsApp entrada de texto: responder_activo=%s cuenta_correcta=%s destinatario_permitido=%s",
            bool(config_bunker.WHATSAPP_RESPONDER_ACTIVO),
            cuenta_correcta,
            destinatario_permitido,
        )
        if cuenta_correcta and destinatario_permitido:
            intencion = clasificar_intencion(texto)
            respuesta = construir_respuesta(intencion, {"nombre_doctora": "Dr. Demo"})
            resultado = enviar_mensaje_texto(destinatario, respuesta)
            logger.info(
                "WhatsApp salida de prueba: categoria=%s ok=%s status=%s message_id_present=%s",
                resultado.get("categoria", intencion),
                resultado.get("ok"),
                resultado.get("status"),
                resultado.get("message_id_present"),
            )
        else:
            logger.info("WhatsApp mensaje no respondido por filtros de prueba")
    else:
        logger.info("Evento WhatsApp recibido sin respuesta automatica")
    return jsonify(ok=True), 200
