"""Notificaciones de correo relacionadas con citas, sin cambios de estado."""

import base64
import html
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build

from helpers.google_auth import TokenNoEncontrado, get_valid_token


TZ_TIJUANA = ZoneInfo("America/Tijuana")
LOGGER = logging.getLogger(__name__)


def enviar_correo_cita_confirmada(cita: dict, doctor: dict) -> bool:
    """Envía una confirmación informativa después de confirmar una cita.

    Esta función no modifica la base de datos ni Google Calendar. Un error de
    correo nunca debe revertir una confirmación ya guardada.
    """
    datos_paciente = cita.get("datos_paciente") or {}
    correo_paciente = datos_paciente.get("correo")
    correo_doctor = cita.get("correo_doctor")
    if not correo_paciente or not correo_doctor or not doctor:
        return False

    fecha_cita = cita.get("fecha_cita")
    if not isinstance(fecha_cita, datetime):
        return False
    if fecha_cita.tzinfo is None:
        fecha_cita = fecha_cita.replace(tzinfo=TZ_TIJUANA)
    fecha_local = fecha_cita.astimezone(TZ_TIJUANA)

    nombre_paciente_raw = str(datos_paciente.get("nombre") or "Paciente")
    nombre_doctor_raw = str(doctor.get("nombre_doctor") or "")
    especialidad_raw = str(doctor.get("especialidad") or "")
    telefono_raw = str(doctor.get("telefono_consultorio") or "")
    direccion_raw = str(doctor.get("direccion_consultorio") or "")
    nombre_paciente = html.escape(nombre_paciente_raw)
    nombre_doctor = html.escape(nombre_doctor_raw)
    especialidad = html.escape(especialidad_raw)
    telefono = html.escape(telefono_raw)
    direccion = html.escape(direccion_raw)
    fecha_texto = fecha_local.strftime("%d/%m/%Y")
    hora_texto = fecha_local.strftime("%I:%M %p").lstrip("0")

    cuerpo_texto = (
        f"Hola {nombre_paciente_raw}, tu cita fue confirmada correctamente.\n\n"
        f"Fecha: {fecha_texto}\n"
        f"Hora: {hora_texto}\n"
        f"Consultorio: {nombre_doctor_raw}\n"
        f"Especialidad: {especialidad_raw}\n"
        f"Dirección: {direccion_raw}\n"
        f"Teléfono: {telefono_raw}\n\n"
        "Te esperamos. Si necesitas realizar un cambio, comunícate directamente con el consultorio.\n\n"
        "Si no encuentras los correos del consultorio, revisa también spam o correo no deseado.\n\n"
        "Mensaje enviado por el consultorio mediante Doko."
    )

    cuerpo_html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;color:#1f2937;line-height:1.55;">
      <p>Hola {nombre_paciente}, tu cita fue confirmada correctamente.</p>
      <p><strong>Fecha:</strong> {fecha_texto}<br>
      <strong>Hora:</strong> {hora_texto}<br>
      <strong>Consultorio:</strong> {nombre_doctor}<br>
      <strong>Especialidad:</strong> {especialidad}<br>
      <strong>Direcci\u00f3n:</strong> {direccion}<br>
      <strong>Tel\u00e9fono:</strong> {telefono}</p>
      <p>Te esperamos. Si necesitas realizar un cambio, comun\u00edcate directamente con el consultorio.</p>
      <p style="color:#4b5563;font-size:13px;">Si no encuentras los correos del consultorio, revisa tambi&eacute;n spam o correo no deseado.</p>
      <p style="color:#4b5563;font-size:13px;">Mensaje enviado por el consultorio mediante Doko.</p>
    </div>
    """

    try:
        creds = get_valid_token(correo_doctor)
        service = build("gmail", "v1", credentials=creds)
        mensaje = MIMEMultipart("alternative")
        mensaje["to"] = correo_paciente
        mensaje["from"] = correo_doctor
        mensaje["subject"] = f"Cita confirmada con {nombre_doctor_raw} - {fecha_texto}"
        mensaje.attach(MIMEText(cuerpo_texto, "plain", "utf-8"))
        mensaje.attach(MIMEText(cuerpo_html, "html", "utf-8"))
        raw = base64.urlsafe_b64encode(mensaje.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return True
    except TokenNoEncontrado:
        LOGGER.warning("No se envi\u00f3 el correo de cita confirmada: falta autorizaci\u00f3n Gmail.")
    except Exception:
        LOGGER.exception("No se pudo enviar el correo de cita confirmada.")
    return False


def enviar_correo_cita_registrada(cita: dict, doctor: dict) -> dict:
    """Envía un comprobante sin enlaces ni cambios en el estado de la cita."""
    datos_paciente = cita.get("datos_paciente") or {}
    correo_paciente = str(datos_paciente.get("correo") or cita.get("correo_manual") or "").strip()
    correo_doctor = str(cita.get("correo_doctor") or "").strip()
    fecha_cita = cita.get("fecha_cita")
    if not correo_paciente or not correo_doctor or not doctor or not isinstance(fecha_cita, datetime):
        return {"ok": False, "categoria": "datos", "motivo": "No hay correo o fecha válida para el comprobante."}

    if fecha_cita.tzinfo is None:
        fecha_cita = fecha_cita.replace(tzinfo=TZ_TIJUANA)
    fecha_local = fecha_cita.astimezone(TZ_TIJUANA)

    nombre_paciente_raw = str(datos_paciente.get("nombre") or "Paciente")
    nombre_doctor_raw = str(doctor.get("nombre_doctor") or "")
    especialidad_raw = str(doctor.get("especialidad") or "")
    telefono_raw = str(doctor.get("telefono_consultorio") or "")
    direccion_raw = str(doctor.get("direccion_consultorio") or "")
    maps_url_raw = str(doctor.get("maps_url") or "").strip()
    servicio_raw = str(datos_paciente.get("motivo") or "").strip()

    nombre_paciente = html.escape(nombre_paciente_raw)
    nombre_doctor = html.escape(nombre_doctor_raw)
    especialidad = html.escape(especialidad_raw)
    telefono = html.escape(telefono_raw)
    direccion = html.escape(direccion_raw)
    maps_url = html.escape(maps_url_raw, quote=True)
    servicio = html.escape(servicio_raw)
    fecha_texto = fecha_local.strftime("%d/%m/%Y")
    hora_texto = fecha_local.strftime("%I:%M %p").lstrip("0")

    lineas_texto = [
        f"Hola {nombre_paciente_raw}, tu cita fue registrada por el consultorio.",
        "",
        f"Fecha: {fecha_texto}",
        f"Hora: {hora_texto}",
        f"Doctora: {nombre_doctor_raw}",
    ]
    if especialidad_raw:
        lineas_texto.append(f"Especialidad: {especialidad_raw}")
    if servicio_raw:
        lineas_texto.append(f"Servicio: {servicio_raw}")
    if direccion_raw:
        lineas_texto.append(f"Dirección: {direccion_raw}")
    if maps_url_raw:
        lineas_texto.append(f"Ubicación: {maps_url_raw}")
    if telefono_raw:
        lineas_texto.append(f"Teléfono: {telefono_raw}")
    lineas_texto.extend([
        "",
        "Esta cita fue acordada directamente con el consultorio y no requiere confirmación mediante enlace.",
        "Si necesitas realizar un cambio, comunícate directamente con el consultorio.",
        "",
        "Mensaje enviado por el consultorio mediante Doko.",
    ])
    cuerpo_texto = "\n".join(lineas_texto)

    filas_html = [
        f"<strong>Fecha:</strong> {fecha_texto}",
        f"<strong>Hora:</strong> {hora_texto}",
        f"<strong>Doctora:</strong> {nombre_doctor}",
    ]
    if especialidad_raw:
        filas_html.append(f"<strong>Especialidad:</strong> {especialidad}")
    if servicio_raw:
        filas_html.append(f"<strong>Servicio:</strong> {servicio}")
    if direccion_raw:
        filas_html.append(f"<strong>Direcci&oacute;n:</strong> {direccion}")
    if telefono_raw:
        filas_html.append(f"<strong>Tel&eacute;fono:</strong> {telefono}")
    enlace_maps = (
        f'<p><a href="{maps_url}" style="color:#173f73;font-weight:700;">Abrir ubicaci&oacute;n</a></p>'
        if maps_url_raw else ""
    )
    cuerpo_html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;color:#1f2937;line-height:1.55;">
      <p>Hola {nombre_paciente}, tu cita fue registrada por el consultorio.</p>
      <p>{'<br>'.join(filas_html)}</p>
      {enlace_maps}
      <p><strong>Esta cita no requiere confirmaci&oacute;n mediante enlace.</strong></p>
      <p>Si necesitas realizar un cambio, comun&iacute;cate directamente con el consultorio.</p>
      <p style="color:#4b5563;font-size:13px;">Mensaje enviado por el consultorio mediante Doko.</p>
    </div>
    """

    try:
        creds = get_valid_token(correo_doctor)
        service = build("gmail", "v1", credentials=creds)
        mensaje = MIMEMultipart("alternative")
        mensaje["to"] = correo_paciente
        mensaje["from"] = correo_doctor
        mensaje["subject"] = f"Tu cita fue registrada con {nombre_doctor_raw} - {fecha_texto}"
        mensaje.attach(MIMEText(cuerpo_texto, "plain", "utf-8"))
        mensaje.attach(MIMEText(cuerpo_html, "html", "utf-8"))
        raw = base64.urlsafe_b64encode(mensaje.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {"ok": True, "categoria": None, "motivo": None}
    except TokenNoEncontrado as exc:
        LOGGER.warning("No se envió el comprobante de cita: falta autorización Gmail.")
        return {"ok": False, "categoria": "oauth", "motivo": str(exc)[:220]}
    except Exception as exc:
        LOGGER.exception("No se pudo enviar el comprobante de cita registrada.")
        return {"ok": False, "categoria": "gmail", "motivo": str(exc)[:220]}

