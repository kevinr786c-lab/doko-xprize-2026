"""Reglas locales y acotadas para la primera prueba de WhatsApp.

Este modulo no consulta Gemini, Calendar, Gmail ni datos de pacientes. Solo
clasifica mensajes generales y devuelve una orientacion segura.
"""

import re
import unicodedata


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(ch for ch in texto if not unicodedata.combining(ch)).lower().strip()


def clasificar_intencion(texto: str) -> str:
    """Clasifica una pregunta sin conservarla ni enviarla a un modelo."""
    normalizado = _normalizar(texto)
    if re.search(r"\b(hola|buenas|buenos dias|buenas tardes|buenas noches)\b", normalizado):
        return "saludo"
    if re.search(r"\b(cancel|cancelo|cancelar|cancelacion)\b", normalizado):
        return "cancelar"
    if re.search(r"\b(reagend|reprogram|cambiar.*cita|otra fecha)\b", normalizado):
        return "reagendar"
    if re.search(r"\b(confirm|confirmar|confirmacion)\b", normalizado):
        return "confirmacion"
    if re.search(r"\b(horario|atienden|abren|sabado|domingo)\b", normalizado):
        return "horarios"
    if re.search(r"\b(direccion|ubicacion|donde estan|como llego)\b", normalizado):
        return "ubicacion"
    if re.search(r"\b(servicio|servicios|colposcop|consulta|precio|costo)\b", normalizado):
        return "servicios"
    if re.search(r"\b(cita|agendar|agenda|reservar)\b", normalizado):
        return "cita"
    return "general"


def construir_respuesta(intencion: str, contexto: dict | None = None) -> str:
    """Construye una respuesta prudente usando solo contexto aprobado."""
    contexto = contexto if isinstance(contexto, dict) else {}
    nombre = str(contexto.get("nombre_doctora") or "el consultorio").strip()
    enlace = str(contexto.get("enlace_agenda") or "").strip()
    horarios = str(contexto.get("horarios") or "").strip()
    direccion = str(contexto.get("direccion") or "").strip()
    servicios = str(contexto.get("servicios") or "").strip()

    respuestas = {
        "saludo": f"Hola. Soy Doko y te ayudo con la informacion operativa de {nombre}. Que necesitas consultar?",
        "cancelar": "Puedo orientarte para cancelar una cita. Indica que deseas cancelarla y recepcion confirmara el cambio; Doko no cancela citas automaticamente en esta prueba.",
        "reagendar": "Puedo orientarte para cambiar una cita. Recepcion debe revisar primero la nueva disponibilidad y confirmar el cambio.",
        "confirmacion": "La confirmacion se realiza conforme al flujo configurado por el consultorio. Si no recibiste el mensaje, revisa WhatsApp y consulta con recepcion.",
        "horarios": f"Los horarios configurados para este consultorio son: {horarios}." if horarios else "Recepcion puede confirmarte los horarios actuales del consultorio.",
        "ubicacion": f"La ubicacion configurada es: {direccion}." if direccion else "Recepcion puede compartirte la ubicacion actual del consultorio.",
        "servicios": f"Los servicios configurados son: {servicios}." if servicios else "Recepcion puede informarte los servicios y costos vigentes.",
        "cita": f"Para solicitar una cita usa este enlace: {enlace}" if enlace else "Para agendar, solicita a recepcion el enlace de la agenda.",
        "general": "Puedo ayudarte con horarios, servicios, ubicacion, citas, confirmaciones, cancelaciones y cambios de fecha.",
    }
    return respuestas.get(intencion, respuestas["general"])
