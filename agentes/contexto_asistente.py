"""Memoria estructurada y efimera para continuidad del asistente de panel."""

from __future__ import annotations

import hashlib
import hmac
import re
import time
import unicodedata
from typing import Any, Mapping

from agentes.asistente_panel import CATEGORIAS


CONTEXT_KEY = "asistente_panel_contexto_v1"
CONTEXT_VERSION = 1
CONTEXT_TTL_SECONDS = 10 * 60
CONTEXT_MAX_FOLLOWUPS = 2

_ORIGENES = {"reglas", "gemini_intent"}
_CATEGORIAS_NO_MEMORIZABLES = {"", "fuera_alcance", "buscar_agenda", "limite_medico"}
_REFERENTES = {"tema_operativo", "evento_seleccionado"}

_TEMAS_AUTOSUFICIENTES = (
    "agenda",
    "apartad",
    "bloque",
    "busca",
    "calendar",
    "cancel",
    "cita",
    "confirm",
    "correo",
    "costo",
    "direccion",
    "editar",
    "email",
    "evento",
    "fecha",
    "gmail",
    "google",
    "horario",
    "liberar",
    "paciente",
    "perfil",
    "precio",
    "reagend",
    "receta",
    "servicio",
    "suffy",
    "telefono",
    "tema",
    "tienda",
    "ubicacion",
)

_INICIOS_DEPENDIENTES = (
    "a que se debe",
    "a que te refieres",
    "cuales",
    "como asi",
    "como funciona eso",
    "entonces",
    "eso",
    "esa",
    "ese",
    "esto",
    "lo anterior",
    "lo mismo",
    "por que",
    "porque",
    "puede ser",
    "que causas",
    "que significa",
    "que pasa",
    "tambien",
    "y",
)


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", texto.lower())).strip()


def contexto_habilitado_para_doctor(correo_doctor: str, correo_demo: str) -> bool:
    """Activa la fase solo para el correo exacto de Dr. Demo."""
    demo = str(correo_demo or "").strip().lower()
    return bool(demo) and str(correo_doctor or "").strip().lower() == demo


def huella_contextual(valor: Any, secreto: str) -> str | None:
    """Crea una huella no reversible para aislar actores, doctoras y citas."""
    limpio = str(valor or "").strip().lower()
    if not limpio:
        return None
    clave = str(secreto or "").encode("utf-8")
    return hmac.new(clave, limpio.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def crear_contexto(
    *,
    actor_hash: str,
    doctor_hash: str,
    categoria: str,
    origen: str,
    id_radar_hash: str | None,
    ahora: int | None = None,
) -> dict[str, Any] | None:
    """Crea contexto compacto; nunca recibe ni almacena el texto de la consulta."""
    categoria = str(categoria or "").strip()
    if (
        not actor_hash
        or not doctor_hash
        or categoria not in CATEGORIAS
        or categoria in _CATEGORIAS_NO_MEMORIZABLES
        or origen not in _ORIGENES
    ):
        return None
    instante = int(time.time() if ahora is None else ahora)
    return {
        "version": CONTEXT_VERSION,
        "actor": actor_hash,
        "doctora": doctor_hash,
        "categoria": categoria,
        "referente": "evento_seleccionado" if id_radar_hash else "tema_operativo",
        "id_radar_hash": id_radar_hash,
        "origen": origen,
        "turnos_restantes": CONTEXT_MAX_FOLLOWUPS,
        "creado_en": instante,
        "expira_en": instante + CONTEXT_TTL_SECONDS,
    }


def validar_contexto(
    contexto: Any,
    *,
    actor_hash: str,
    doctor_hash: str,
    id_radar_hash: str | None,
    evento_vigente: bool,
    ahora: int | None = None,
) -> dict[str, Any] | None:
    """Valida aislamiento, vigencia, turnos y continuidad de la misma cita."""
    if not isinstance(contexto, Mapping):
        return None
    esperado = {
        "version", "actor", "doctora", "categoria", "referente",
        "id_radar_hash", "origen", "turnos_restantes", "creado_en", "expira_en",
    }
    if set(contexto.keys()) != esperado:
        return None
    try:
        copia = dict(contexto)
        if copia["version"] != CONTEXT_VERSION:
            return None
        if not hmac.compare_digest(str(copia["actor"]), str(actor_hash)):
            return None
        if not hmac.compare_digest(str(copia["doctora"]), str(doctor_hash)):
            return None
        if copia["referente"] not in _REFERENTES or copia["origen"] not in _ORIGENES:
            return None
        categoria = str(copia["categoria"] or "")
        if categoria not in CATEGORIAS or categoria in _CATEGORIAS_NO_MEMORIZABLES:
            return None
        instante = int(time.time() if ahora is None else ahora)
        if int(copia["expira_en"]) <= instante or int(copia["turnos_restantes"]) <= 0:
            return None
        if copia["id_radar_hash"] != id_radar_hash:
            return None
        if copia["id_radar_hash"] and not evento_vigente:
            return None
        return copia
    except (KeyError, TypeError, ValueError):
        return None


def es_follow_up(
    pregunta: str,
    *,
    contexto_valido: Mapping[str, Any] | None,
    accion_detectada: bool = False,
) -> bool:
    """Detecta referencias breves; no decide categorias ni habilita acciones."""
    if not contexto_valido or accion_detectada:
        return False
    normalizada = _normalizar(pregunta)
    if not normalizada or len(normalizada.split()) > 16:
        return False
    palabras = normalizada.split()
    if any(
        palabra.startswith(tema)
        for palabra in palabras
        for tema in _TEMAS_AUTOSUFICIENTES
    ):
        return False
    return any(
        normalizada == inicio or normalizada.startswith(f"{inicio} ")
        for inicio in _INICIOS_DEPENDIENTES
    )


def consumir_contexto(contexto: Mapping[str, Any]) -> dict[str, Any] | None:
    """Consume un follow-up sin extender la caducidad original."""
    actualizado = dict(contexto)
    actualizado["turnos_restantes"] = int(actualizado["turnos_restantes"]) - 1
    return actualizado if actualizado["turnos_restantes"] > 0 else None


def resolver_continuidad(
    *,
    habilitado: bool,
    pregunta: str,
    categoria_actual: str | None,
    contexto_valido: Mapping[str, Any] | None,
    accion_detectada: bool = False,
) -> tuple[str | None, bool, dict[str, Any] | None]:
    """Resuelve un referente sin cambiar hechos ni conceder autoridad."""
    if not habilitado:
        contexto_sin_cambios = dict(contexto_valido) if contexto_valido else None
        return categoria_actual, False, contexto_sin_cambios
    if not es_follow_up(
        pregunta,
        contexto_valido=contexto_valido,
        accion_detectada=accion_detectada,
    ):
        return categoria_actual, False, None
    return (
        str(contexto_valido["categoria"]),
        True,
        consumir_contexto(contexto_valido),
    )
