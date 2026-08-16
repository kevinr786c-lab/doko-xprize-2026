import json
import re
import unicodedata
from difflib import get_close_matches
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from agentes.gemini_client import generar_texto_medido
from config_bunker import PANEL_ASSISTANT_GEMINI_MAX_OUTPUT_TOKENS


TZ_TIJUANA = ZoneInfo("America/Tijuana")

CATEGORIAS = {
    "correo",
    "confirmacion",
    "tipos_evento",
    "acciones_cita",
    "cita",
    "bloqueo",
    "apartado",
    "editar",
    "liberar",
    "buscar",
    "perfil",
    "servicios",
    "tema",
    "google",
    "suffy",
    "contexto_actual",
    "capacidades",
    "limite_medico",
    "fuera_alcance",
    "correo_cuando",
    "correo_no_llego",
    "correo_diferencias",
    "confirmar_manual",
    "liberar_confirmada",
    "editar_flujo",
    "apartado_expiracion",
    "apartado_convertir",
    "evento_externo",
    "google_alcance",
    "perfil_sin_google",
    "liberacion_automatica",
    "origen_cita",
    "correo_hora",
    "sin_confirmar",
    "confirmacion_anticipada",
    "buscar_agenda",
    "estado_cita",
    "recrear_cancelada",
}

MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

DIAS_SEMANA_ES = {
    "lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3,
    "viernes": 4, "sabado": 5, "domingo": 6,
}

VOCABULARIO_OPERATIVO = {
    "agenda", "agendar", "apartado", "aseguradora", "bloqueo", "buscar",
    "calendar", "cancelar", "cita", "color", "confirmacion", "confirmar",
    "conectar", "correo", "costo", "editar", "email", "enviar", "evento",
    "expirar", "filtro", "google", "guardar", "hora", "liberar", "mensaje",
    "oauth", "ocupado", "paciente", "pedido", "pendiente", "perfil", "precio",
    "recibio", "servicio", "suffy", "telefono", "tema", "tienda", "token",
    "verificado", "contexto", "estado", "haciendo", "estaba", "ayuda", "puedes",
    "sirve", "funciona", "seleccionada", "abierta", "cuando", "porque",
    "diferencia", "inmediato", "informativo", "llego", "llegar", "recibir",
    "reinicia", "convertir", "externo", "fuera", "cercana", "lejana",
    "manual", "despues", "antes", "origen", "reserva", "automatico",
    "elimino", "elimina", "libero", "libera", "vencio", "plazo",
    "configuro", "cambio", "accidente", "error", "temprano",
}

ACCIONES_SEGURAS = {
    "agendar": {"agendar", "crear", "registrar", "guardar"},
    "editar": {"editar", "modificar", "cambiar", "cambio"},
    "confirmar": {"confirmar", "confirmada", "verificar"},
    "liberar": {"liberar", "borrar", "eliminar", "cancelar"},
    "convertir": {"convertir", "convierto", "convertirlo", "hacer"},
    "buscar": {"buscar", "encontrar", "filtrar", "consultar"},
    "conectar": {"conectar", "reconectar", "autorizar"},
    "enviar": {"enviar", "mandar", "recibir", "llegar"},
}

OBJETOS_SEGUROS = {
    "cita": {"cita", "paciente", "agenda"},
    "correo": {"correo", "email", "mail", "mensaje", "spam"},
    "bloqueo": {"bloqueo", "bloquear", "ocupado"},
    "apartado": {"apartado", "temporal", "expira", "vencimiento"},
    "google": {"google", "calendar", "oauth", "token", "calendario"},
    "perfil": {"perfil", "foto", "color", "tema", "servicio"},
    "suffy": {"suffy", "tienda", "pedido", "catalogo", "insumo"},
}

CONDICIONES_SEGURAS = {
    "no_llego": ("no llego", "no le llego", "no recibio", "no aparece", "no mando", "no envio"),
    "confirmada": ("confirmada", "confirmado", "verificada", "verificado"),
    "sin_correo": ("sin correo", "no tiene correo", "falta correo"),
    "fallo": ("fallo", "error", "no funciona", "no pudo"),
    "cercana": ("hoy", "manana", "cercana", "proxima"),
    "lejana": ("lejana", "despues", "futura", "otro mes"),
    "externa": ("fuera de doko", "externo", "desde google"),
}

TOKENS_CONTEXTO = {
    "actual", "abierta", "editando", "estado", "estaba", "estoy", "hacia",
    "haciendo", "paso", "seleccionada", "seleccione",
}

TOKENS_CONTEXTO_CANONICOS = TOKENS_CONTEXTO | {"cita", "evento"}


def _texto_normalizado(texto: str) -> str:
    valor = unicodedata.normalize("NFKD", str(texto or ""))
    valor = "".join(ch for ch in valor if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", valor.lower()).strip()


def _fecha_valida_busqueda(dia: int, mes: int, anio: int) -> datetime | None:
    try:
        return datetime(anio, mes, dia, tzinfo=TZ_TIJUANA)
    except ValueError:
        return None


def _siguiente_fecha_anual(dia: int, mes: int, ahora: datetime) -> datetime | None:
    candidata = _fecha_valida_busqueda(dia, mes, ahora.year)
    if candidata and candidata.date() >= ahora.date():
        return candidata
    return _fecha_valida_busqueda(dia, mes, ahora.year + 1)


def _extraer_fecha_busqueda(texto: str, ahora: datetime) -> tuple[str | None, int | None, str | None]:
    """Devuelve fecha exacta, dia sin mes y un error claro si la fecha es invalida."""
    if re.search(r"\bhoy\b", texto):
        return ahora.date().isoformat(), None, None
    if re.search(r"\bmanana\b", texto):
        return (ahora + timedelta(days=1)).date().isoformat(), None, None

    numerica = re.search(r"\b([0-3]?\d)[/-]([01]?\d)(?:[/-](\d{2,4}))?\b", texto)
    if numerica:
        dia, mes = int(numerica.group(1)), int(numerica.group(2))
        anio_texto = numerica.group(3)
        if anio_texto:
            anio = int(anio_texto)
            if anio < 100:
                anio += 2000
            candidata = _fecha_valida_busqueda(dia, mes, anio)
        else:
            candidata = _siguiente_fecha_anual(dia, mes, ahora)
        if not candidata:
            return None, None, "Esa fecha no es valida. Escribe dia, mes y ano nuevamente."
        return candidata.date().isoformat(), None, None

    meses = "|".join(MESES_ES)
    escrita = re.search(
        rf"\b(?:el\s+)?([0-3]?\d)\s+de\s+({meses})(?:\s+de\s+(\d{{4}}))?\b",
        texto,
    )
    if escrita:
        dia = int(escrita.group(1))
        mes = MESES_ES[escrita.group(2)]
        if escrita.group(3):
            candidata = _fecha_valida_busqueda(dia, mes, int(escrita.group(3)))
        else:
            candidata = _siguiente_fecha_anual(dia, mes, ahora)
        if not candidata:
            return None, None, "Esa fecha no existe. Revisa el dia y el mes."
        return candidata.date().isoformat(), None, None

    for nombre_dia, indice in DIAS_SEMANA_ES.items():
        if re.search(rf"\b(?:proximo\s+)?{nombre_dia}\b", texto):
            diferencia = (indice - ahora.weekday()) % 7
            if "proximo" in texto and diferencia == 0:
                diferencia = 7
            return (ahora + timedelta(days=diferencia)).date().isoformat(), None, None

    dia_solo = re.search(r"\b(?:del\s+dia|el\s+dia|dia|del)\s+([0-3]?\d)\b", texto)
    if dia_solo:
        dia = int(dia_solo.group(1))
        if not 1 <= dia <= 31:
            return None, None, "El dia debe estar entre 1 y 31."
        return None, dia, None
    return None, None, None


def _extraer_telefono_busqueda(texto_original: str, texto_normalizado: str) -> str | None:
    sin_fechas = re.sub(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", " ", texto_normalizado)
    sin_fechas = re.sub(r"\b\d{1,2}\s+de\s+[a-z]+(?:\s+de\s+\d{4})?\b", " ", sin_fechas)
    candidatos = re.findall(r"(?:\d[\s().+-]*){4,10}", sin_fechas)
    for candidato in candidatos:
        digitos = re.sub(r"\D", "", candidato)
        if 4 <= len(digitos) <= 10:
            return digitos
    return None


def _extraer_nombre_busqueda(texto_original: str) -> str | None:
    texto = re.sub(r"\s+", " ", str(texto_original or "")).strip().strip("?.!,")
    patrones = (
        r"\b(?:busca(?:me)?|encuentra|localiza)(?:\s+la)?(?:\s+cita)?(?:\s+de|\s+a)?\s+(.+)$",
        r"\bcita\s+de\s+(.+)$",
    )
    candidato = None
    for patron in patrones:
        coincidencia = re.search(patron, texto, flags=re.IGNORECASE)
        if coincidencia:
            candidato = coincidencia.group(1)
            break
    if not candidato:
        return None
    candidato = re.sub(r"\b(?:el\s+)?d[ií]a\s+\d{1,2}\b.*$", "", candidato, flags=re.IGNORECASE)
    candidato = re.sub(r"\bel\s+\d{1,2}\s+de\s+[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+(?:\s+de\s+\d{4})?\b.*$", "", candidato, flags=re.IGNORECASE)
    candidato = re.sub(r"\b(?:hoy|mañana|manana|lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)\b.*$", "", candidato, flags=re.IGNORECASE)
    candidato = re.sub(r"\b(?:tel[eé]fono|tel|numero)\b.*$", "", candidato, flags=re.IGNORECASE)
    candidato = candidato.strip(" ,.-")
    letras = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", candidato)
    return candidato if len(letras) >= 3 else None


def interpretar_busqueda_agenda(pregunta: str, ahora: datetime | None = None) -> dict | None:
    """Interpreta comandos de lectura. El resultado nunca se envia a Gemini."""
    original = str(pregunta or "")[:300].strip()
    texto = _texto_normalizado(original)
    if not original or texto.startswith("como "):
        return None
    es_comando = bool(re.search(
        r"\b(?:busca(?:r|me)?|encuentra|localiza)\b"
        r"|\bquien(?:es)?\s+viene(?:n)?\b"
        r"|\bcitas?\s+(?:de(?:l)?|para)\b"
        r"|\bagenda\s+(?:de(?:l)?|para)\b",
        texto,
    ))
    if not es_comando:
        return None

    ahora_local = ahora or datetime.now(TZ_TIJUANA)
    if ahora_local.tzinfo is None:
        ahora_local = ahora_local.replace(tzinfo=TZ_TIJUANA)
    fecha, dia_mes, error = _extraer_fecha_busqueda(texto, ahora_local)
    telefono = _extraer_telefono_busqueda(original, texto)
    nombre = None if telefono else _extraer_nombre_busqueda(original)
    buscar = telefono or nombre

    if error:
        return {"tipo": "aclarar_busqueda", "mensaje": error}
    if not fecha and not dia_mes and not buscar:
        return {
            "tipo": "aclarar_busqueda",
            "mensaje": "Indica una fecha, el nombre del paciente o al menos cuatro digitos del telefono.",
        }
    return {
        "tipo": "buscar_agenda",
        "fecha": fecha,
        "dia_mes": dia_mes,
        "buscar": buscar,
        "alcance_meses": 12,
        "incluir_historial": False,
    }


def sanitizar_pregunta_para_ia(pregunta: str) -> str:
    """Devuelve solo señales operativas; nombres e identificadores quedan fuera."""
    texto = _texto_normalizado(str(pregunta or "")[:500])
    senales = []
    for token in re.findall(r"[a-z]+", texto):
        if len(token) < 4:
            continue
        if token in VOCABULARIO_OPERATIVO:
            senales.append(token)
            continue
        aproximacion = get_close_matches(token, VOCABULARIO_OPERATIVO, n=1, cutoff=0.72)
        if aproximacion:
            senales.append(aproximacion[0])
    return " ".join(dict.fromkeys(senales))


def _coincidencias_enumeradas(texto: str, grupos: dict[str, set[str]]) -> list[str]:
    encontradas = []
    tokens = set(re.findall(r"[a-z]+", texto))
    for etiqueta, alias in grupos.items():
        if tokens & alias or any(valor in texto for valor in alias if " " in valor):
            encontradas.append(etiqueta)
            continue
        for token in tokens:
            if len(token) >= 4 and get_close_matches(token, alias, n=1, cutoff=0.78):
                encontradas.append(etiqueta)
                break
    return encontradas


def construir_paquete_intencion(pregunta: str, contexto_interfaz: str) -> dict:
    """Extrae conceptos enumerados sin conservar texto libre ni identificadores."""
    texto = _texto_normalizado(str(pregunta or "")[:300])
    condiciones = [
        etiqueta
        for etiqueta, frases in CONDICIONES_SEGURAS.items()
        if any(frase in texto for frase in frases)
    ]
    if re.search(r"\bno(?:\s+[a-z]+){0,2}\s+(?:llego|recibio|mando|envio)\b", texto):
        condiciones.append("no_llego")
    condiciones = list(dict.fromkeys(condiciones))
    tipo_pregunta = []
    if "cuando" in texto:
        tipo_pregunta.append("cuando")
    if "porque" in texto or "por que" in texto:
        tipo_pregunta.append("por_que")
    if "como" in texto:
        tipo_pregunta.append("como")
    if "diferencia" in texto:
        tipo_pregunta.append("diferencia")
    if any(frase in texto for frase in ("que pasa si", "que pasaria", "si libero", "si cambio")):
        tipo_pregunta.append("consecuencia")
    if not tipo_pregunta:
        tipo_pregunta.append("orientacion")

    contexto = contexto_interfaz if contexto_interfaz in {
        "modulo_asistente", "editar_cita", "crear_evento", "cita_seleccionada"
    } else "modulo_asistente"
    return {
        "acciones": _coincidencias_enumeradas(texto, ACCIONES_SEGURAS),
        "objetos": _coincidencias_enumeradas(texto, OBJETOS_SEGUROS),
        "condiciones": condiciones,
        "tipo_pregunta": tipo_pregunta,
        "contexto_interfaz": contexto,
    }


def paquete_tiene_contexto(paquete: dict) -> bool:
    return bool(paquete.get("acciones") or paquete.get("objetos") or paquete.get("condiciones"))


def _tokens_contextuales(texto: str) -> set[str]:
    """Normaliza errores comunes sin conservar nombres ni otros datos libres."""
    tokens = set()
    for token in re.findall(r"[a-z]+", _texto_normalizado(texto)):
        if token in TOKENS_CONTEXTO_CANONICOS:
            tokens.add(token)
            continue
        aproximacion = get_close_matches(token, TOKENS_CONTEXTO_CANONICOS, n=1, cutoff=0.74)
        if aproximacion:
            tokens.add(aproximacion[0])
    return tokens


def clasificar_local(
    pregunta: str,
    *,
    continuidad_edicion: bool = False,
) -> str | None:
    texto = _texto_normalizado(pregunta)
    if continuidad_edicion:
        menciona_edicion = any(raiz in texto for raiz in ("edit", "modific", "cambi"))
        menciona_cita = any(
            termino in texto
            for termino in ("cita", "evento", "fecha", "hora", "correo", "confirmacion")
        )
        if menciona_edicion and menciona_cita:
            return "editar_flujo"
    reutiliza_cancelada = (
        any(frase in texto for frase in (
            "mismos datos", "datos de contacto", "reutiliz", "reusar",
            "recuperar los datos", "reagendar esta cita cancelada",
        ))
        and any(frase in texto for frase in (
            "otra cita", "crear otra", "nueva cita", "cancelad", "reagend",
        ))
    )
    if reutiliza_cancelada or any(frase in texto for frase in (
        "crear otra cita con los mismos datos", "crear una cita con los mismos datos",
        "nueva cita con los mismos datos", "reutilizar los datos",
        "reusar los datos", "reagendar esta cita cancelada",
    )):
        return "recrear_cancelada"
    if any(frase in texto for frase in (
        "esta cita esta confirmada", "esta confirmada esta cita", "ya esta confirmada",
        "sigue pendiente", "esta cita sigue pendiente", "estado de esta cita",
        "esta cita esta cancelada", "esta cita sigue activa", "esta cita esta activa",
    )):
        return "estado_cita"
    if any(frase in texto for frase in (
        "de donde salio", "de donde viene", "quien creo", "origen de la cita",
        "doko o google", "reserva de google", "reservada en google",
    )):
        return "origen_cita"
    if (
        any(frase in texto for frase in (
            "no se libero", "no libero", "no se elimina", "no elimino",
            "sigue ocupada", "sigue activa", "porque sigue", "por que sigue",
        ))
        and any(palabra in texto for palabra in (
            "cita", "confirm", "24 hora", "plazo", "ayer", "correo",
        ))
    ):
        return "liberacion_automatica"
    if (
        any(frase in texto for frase in ("a que hora", "que hora", "hora manda", "hora envia"))
        and any(palabra in texto for palabra in ("correo", "email", "mensaje", "confirmacion"))
    ):
        return "correo_hora"
    if any(frase in texto for frase in (
        "que pasa si no confirma", "si no confirma", "no confirmo", "no confirma la cita",
    )):
        return "sin_confirmar"
    if (
        any(palabra in texto for palabra in ("confirmo", "confirme", "confirmar", "confirmada"))
        and any(frase in texto for frase in (
            "antes de tiempo", "por accidente", "por error", "sin querer", "muy temprano",
        ))
    ):
        return "confirmacion_anticipada"
    if (
        any(frase in texto for frase in ("confirmo manual", "confirmar manual", "la confirmo", "puedo confirmar"))
        and any(palabra in texto for palabra in ("correo", "email", "manual", "panel", "cita"))
    ):
        return "confirmar_manual"
    if "diferencia" in texto and any(palabra in texto for palabra in ("cita", "bloque", "apart")):
        return "tipos_evento"
    if "liber" in texto and "confirm" in texto:
        return "acciones_cita"
    if "liber" in texto and ("confirm" in texto or "verific" in texto):
        return "liberar_confirmada"
    if "confirmar manual" in texto or "como confirm" in texto:
        return "confirmar_manual"
    if (any(frase in texto for frase in (
        "no llego", "no le llego", "no recibio", "no mando", "no envio",
        "no se envio", "no se envia", "no ha llegado", "no aparece",
    ))
        or re.search(r"\bno(?:\s+[a-z]+){0,3}\s+(?:llego|llega|recibio|recibe|mando|manda|envio|envia)\b", texto)
    ) and any(
        palabra in texto for palabra in ("correo", "email", "mensaje")
    ):
        return "correo_no_llego"
    if "diferencia" in texto and any(palabra in texto for palabra in ("correo", "confirmacion", "informativo")):
        return "correo_diferencias"
    if "cuando" in texto and any(palabra in texto for palabra in ("correo", "email", "mensaje", "confirmacion")):
        return "correo_cuando"
    if any(palabra in texto for palabra in ("editar", "cambiar", "cambio", "modificar")) and any(
        palabra in texto for palabra in ("fecha", "hora", "flujo", "correo", "confirmacion")
    ):
        return "editar_flujo"
    if "apart" in texto and any(palabra in texto for palabra in ("convert", "convi", "hacer cita")):
        return "apartado_convertir"
    if "apart" in texto and any(palabra in texto for palabra in ("expira", "vence", "vencimiento")):
        return "apartado_expiracion"
    if "apart" in texto:
        return "apartado"
    if any(valor in texto for valor in ("bloqueo", "bloquear", "como bloqueo", "ocupar horario")):
        return "bloqueo"
    if any(frase in texto for frase in ("fuera de doko", "evento externo", "desde google")):
        return "evento_externo"
    if any(palabra in texto for palabra in ("perfil", "color", "tema", "servicio")) and any(
        palabra in texto for palabra in ("google", "token", "conectar")
    ):
        return "perfil_sin_google"
    if any(frase in texto for frase in ("que afecta google", "para que sirve google", "que necesita google")):
        return "google_alcance"
    tokens_contextuales = _tokens_contextuales(texto)
    pregunta_sobre_contexto = bool(tokens_contextuales & {"cita", "evento"}) and bool(
        tokens_contextuales & TOKENS_CONTEXTO
    )
    if pregunta_sobre_contexto or any(frase in texto for frase in (
        "que estaba haciendo", "que estoy haciendo", "en que estaba",
        "que tiene esta cita", "que paso con esta cita", "cita que abri",
    )):
        return "contexto_actual"
    if any(frase in texto for frase in (
        "que puedes hacer", "como me ayudas", "en que me ayudas", "para que sirves",
        "que hace el asistente", "como funciona el asistente",
    )):
        return "capacidades"
    grupos = (
        ("limite_medico", ("diagnost", "tratamiento", "medicamento", "sintoma", "receta")),
        ("correo", ("correo", "email", "mail", "bandeja", "spam", "no llego", "no recibio", "enviar mensaje")),
        ("confirmacion", ("confirm", "24 hora", "48 hora", "pendiente", "verificad")),
        ("bloqueo", ("bloque", "ocupado", "no agendar")),
        ("apartado", ("apartado", "temporal", "vencimiento", "expira")),
        ("liberar", ("liberar", "borrar evento", "eliminar evento", "cancelar horario")),
        ("editar", ("editar", "modificar", "cambiar fecha", "cambiar hora", "guardar cambios")),
        ("buscar", ("buscar", "filtro", "consultar agenda", "encontrar paciente")),
        ("servicios", ("servicio", "precio", "costo", "consulta")),
        ("tema", ("color", "tema", "sakura", "lila", "marino", "turquesa", "vino")),
        ("perfil", ("perfil", "foto", "telefono consultorio", "aseguradora", "horario atencion")),
        ("google", ("google", "calendar", "calendario", "oauth", "token", "conectar")),
        ("suffy", ("suffy", "tienda", "pedido", "catalogo", "insumo")),
        ("cita", ("cita", "agendar", "paciente", "nueva cita", "hacer cita")),
    )
    for categoria, palabras in grupos:
        if any(palabra in texto for palabra in palabras):
            return categoria
    return None


def clasificar_con_gemini(paquete: dict):
    if not paquete_tiene_contexto(paquete):
        return "fuera_alcance", None
    permitidas = ", ".join(sorted(CATEGORIAS))
    prompt = f"""Clasifica una pregunta interna sobre el uso de un panel de agenda.
Devuelve exclusivamente una etiqueta de esta lista, sin explicación:
{permitidas}

No resuelvas la pregunta, no diagnostiques y no infieras datos personales.
Solo recibes conceptos enumerados extraidos localmente; no recibes la pregunta original.
Conceptos seguros: {json.dumps(paquete, ensure_ascii=True, sort_keys=True)}"""
    resultado = generar_texto_medido(
        prompt,
        max_output_tokens=PANEL_ASSISTANT_GEMINI_MAX_OUTPUT_TOKENS,
        temperature=0,
        aplicar_limite_local=False,
    )
    categoria = _texto_normalizado(resultado.texto).replace(" ", "_")
    return (categoria if categoria in CATEGORIAS else "fuera_alcance"), resultado


def clasificar_pregunta(pregunta: str) -> tuple[str, str]:
    categoria = clasificar_local(pregunta)
    if categoria:
        return categoria, "reglas"
    return "fuera_alcance", "reglas"


def _fecha_local(fecha) -> datetime | None:
    if not isinstance(fecha, datetime):
        return None
    if fecha.tzinfo is None:
        return fecha.replace(tzinfo=TZ_TIJUANA)
    return fecha.astimezone(TZ_TIJUANA)


def _restar_dias_habiles(valor: datetime, cantidad: int) -> datetime:
    resultado = valor
    restantes = max(0, int(cantidad))
    while restantes:
        resultado -= timedelta(days=1)
        if resultado.weekday() < 5:
            restantes -= 1
    return resultado


def describir_flujo_correo(evento: dict, modo_confirmacion: str, ahora: datetime | None = None) -> dict:
    tipo = str(evento.get("tipo_evento") or "CITA_PACIENTE").upper()
    if tipo == "BLOQUEO_HORARIO":
        return {"estado": "no_aplica", "mensaje": "Es un bloqueo interno. No genera correos para pacientes."}
    if tipo in {"APARTADO_TEMPORAL", "EVENTO_INTERNO"}:
        return {"estado": "no_aplica", "mensaje": "Este evento es interno. Solo enviará correos si se convierte en una cita con correo."}

    estado_operativo = str(evento.get("estado_operativo") or "activo").lower()
    estatus = str(evento.get("estatus_confirmacion") or "Pendiente").upper()
    if estado_operativo != "activo":
        return {"estado": "no_aplica", "mensaje": "Esta cita ya fue liberada y no espera nuevos correos de confirmación."}
    if estatus.startswith("CANCEL"):
        return {"estado": "no_aplica", "mensaje": "Esta cita está cancelada y ya no espera correos de confirmación."}

    if not bool(evento.get("tiene_correo")):
        return {"estado": "sin_correo", "mensaje": "La cita no tiene correo. Doko la conserva en agenda, pero no puede enviar mensajes al paciente."}
    if evento.get("correo_registro_enviado_en") or evento.get("correo_registro_enviado"):
        return {"estado": "enviado_ahora", "mensaje": "Doko ya envió el correo informativo de esta cita."}
    if evento.get("confirmacion_enviada_en"):
        return {"estado": "enviado_ahora", "mensaje": "Doko ya envió el correo de confirmación de esta cita."}
    if evento.get("correo_registro_error_en") or evento.get("intento_inmediato_fallido"):
        return {"estado": "error_envio", "mensaje": "Doko intentó enviar el correo informativo, pero el envío falló. La cita sí quedó guardada."}
    if "CONFIRM" in estatus or "VERIFIC" in estatus:
        return {"estado": "no_aplica", "mensaje": "La cita ya está confirmada y no espera un enlace de confirmación."}
    if evento.get("requiere_confirmacion_enlace") is False:
        return {"estado": "no_aplica", "mensaje": "Esta cita no requiere un enlace de confirmación adicional."}

    fecha = _fecha_local(evento.get("fecha_cita"))
    ahora_local = ahora or datetime.now(TZ_TIJUANA)
    if ahora_local.tzinfo is None:
        ahora_local = ahora_local.replace(tzinfo=TZ_TIJUANA)

    if modo_confirmacion == "confirmar_48h_cancelar_24h" and evento.get("confirmacion_dias_habiles"):
        mensaje = (
            "Doko intentará enviar la confirmación dos días hábiles antes de la cita. "
            "Si sigue pendiente, podrá liberar el horario el siguiente día hábil. "
            "Este consultorio no procesa este ciclo automático en sábado ni domingo."
        )
    elif modo_confirmacion == "confirmar_48h_cancelar_24h":
        mensaje = "Doko intentará enviar la confirmación alrededor de 48 horas antes de la cita, según la ejecución programada. No debe llegar al crear una cita lejana."
    elif modo_confirmacion == "confirmar_24h":
        mensaje = "Doko intentará enviar la confirmación cuando la cita entre en la ventana de 24 horas. No debe llegar al crear una cita lejana."
    else:
        mensaje = "La cita seguirá el flujo manual de confirmación configurado para este consultorio. Guardarla no garantiza un correo inmediato."

    if fecha and fecha <= ahora_local + timedelta(days=1):
        mensaje += " Como la cita es próxima, revisa el estado del envío y la conexión con Google si esperabas un correo informativo."
    return {"estado": "programado_confirmacion", "mensaje": mensaje}


def metadatos_flujo_guardado(
    *, tipo_evento: str, fecha_cita: datetime, correo: str, confirmado: bool,
    modo_confirmacion: str, confirmacion_dias_habiles: bool = False,
    intento_inmediato: bool, enviado: bool,
) -> dict:
    evento = {
        "tipo_evento": tipo_evento,
        "fecha_cita": fecha_cita,
        "tiene_correo": bool(str(correo or "").strip()),
        "estatus_confirmacion": "CONFIRMADO" if confirmado else "Pendiente",
        "correo_registro_enviado": bool(enviado),
        "intento_inmediato_fallido": bool(intento_inmediato and not enviado),
        "requiere_confirmacion_enlace": not intento_inmediato,
        "confirmacion_dias_habiles": bool(confirmacion_dias_habiles),
    }
    return describir_flujo_correo(evento, modo_confirmacion)


def _descripcion_fecha_operativa(fecha) -> str:
    fecha_local = _fecha_local(fecha)
    if not fecha_local:
        return ""
    meses = (
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    )
    hora = fecha_local.strftime("%I:%M").lstrip("0")
    periodo = "a. m." if fecha_local.hour < 12 else "p. m."
    return f"el {fecha_local.day} de {meses[fecha_local.month - 1]} a las {hora} {periodo}"


def _descripcion_envio_programado(evento: dict | None, modo_confirmacion: str) -> str:
    fecha = _fecha_local((evento or {}).get("fecha_cita"))
    if not fecha:
        return ""
    if modo_confirmacion == "confirmar_48h_cancelar_24h":
        hora = 8 if fecha.hour < 14 else 9
        if (evento or {}).get("confirmacion_dias_habiles"):
            momento = _restar_dias_habiles(fecha, 2)
        else:
            momento = fecha - timedelta(days=2)
        momento = momento.replace(hour=hora, minute=0, second=0, microsecond=0)
        return _descripcion_fecha_operativa(momento)
    if modo_confirmacion == "confirmar_24h":
        return _descripcion_fecha_operativa(fecha - timedelta(hours=24))
    return ""


def describir_contexto_actual(evento: dict | None, contexto_interfaz: str = "modulo_asistente") -> str:
    partes = []
    if contexto_interfaz == "editar_cita":
        partes.append("Estabas editando esta cita. Doko pausó el formulario para que pudieras preguntar sin perder tus cambios.")
    elif contexto_interfaz == "crear_evento":
        partes.append("Estabas creando un evento. Doko pausó el formulario y todavía no ha guardado esos cambios.")
    elif evento:
        partes.append("Tienes una cita seleccionada como contexto de esta conversación.")
    else:
        return "Estás en el módulo Asistente. No hay una cita seleccionada; abre una cita y usa ‘Preguntar a Doko’ para recibir una explicación de su estado operativo."

    if evento:
        tipo = str(evento.get("tipo_evento") or "CITA_PACIENTE").upper()
        tipos = {
            "CITA_PACIENTE": "Es una cita de paciente",
            "BLOQUEO_HORARIO": "Es un bloqueo de horario",
            "APARTADO_TEMPORAL": "Es un apartado temporal",
            "EVENTO_INTERNO": "Es un evento interno",
        }
        descripcion = tipos.get(tipo, "Es un evento de agenda")
        fecha = _descripcion_fecha_operativa(evento.get("fecha_cita"))
        if fecha:
            descripcion += f" programado {fecha}"
        estado_operativo = str(evento.get("estado_operativo") or "activo").lower()
        estatus = str(evento.get("estatus_confirmacion") or "Pendiente").strip().lower()
        descripcion += f". Su estado operativo es {estado_operativo}"
        if tipo == "CITA_PACIENTE":
            descripcion += f" y su confirmación está {estatus}"
        partes.append(descripcion + ".")

    if contexto_interfaz in {"editar_cita", "crear_evento"}:
        partes.append("Usa ‘Volver a la cita’ para continuar donde estabas.")
    return " ".join(partes)


def respuesta_operativa(
    categoria: str,
    modo_confirmacion: str,
    evento: dict | None = None,
    contexto_interfaz: str = "modulo_asistente",
) -> str:
    if categoria == "contexto_actual":
        return describir_contexto_actual(evento, contexto_interfaz)
    if categoria == "capacidades":
        return (
            "Puedo explicar citas, bloqueos, apartados, correos, confirmaciones, búsquedas, "
            "perfil, servicios, Google y Doko Suffy. Si abres una cita, también puedo describir "
            "su estado operativo sin usar los datos personales del paciente. No modifico ni confirmo eventos por mi cuenta."
        )
    if categoria in {"acciones_cita", "liberar"}:
        if evento:
            tipo = str(evento.get("tipo_evento") or "CITA_PACIENTE").upper()
            estatus = str(evento.get("estatus_confirmacion") or "Pendiente").upper()
            estado_operativo = str(evento.get("estado_operativo") or "activo").lower()
            if estado_operativo != "activo":
                return "Este evento ya está liberado; no hay otra acción de liberación pendiente."
            if tipo == "CITA_PACIENTE" and ("CONFIRM" in estatus or "VERIFIC" in estatus):
                return (
                    "Esta cita ya está confirmada y no puede liberarse desde Doko. "
                    "Por eso la acción ‘Liberar’ no aparece. Si la cita necesita cancelarse, "
                    "debe seguirse el flujo de cancelación del consultorio, no liberar el horario como si fuera un apartado."
                )
            if tipo == "CITA_PACIENTE":
                return (
                    "Esta es una cita de paciente. Confirmar cambia su estado a confirmada; "
                    "una vez confirmada, Doko ya no permite liberarla."
                )
            return (
                "Este evento interno sí puede liberarse. Al hacerlo, Doko retira el evento operativo "
                "de Google Calendar y deja disponible el horario."
            )
        if categoria == "liberar":
            return (
                "Doko permite liberar bloqueos, apartados y eventos internos. Una cita de paciente "
                "que ya está confirmada no puede liberarse; debe seguir el flujo de cancelación del consultorio."
            )
        return (
            "Confirmar marca una cita pendiente como confirmada. Una vez confirmada, Doko no permite liberarla. "
            "Liberar se utiliza principalmente para bloqueos, apartados y eventos internos."
        )
    if categoria in {"correo", "confirmacion"}:
        if evento:
            return describir_flujo_correo(evento, modo_confirmacion)["mensaje"]
        if modo_confirmacion == "confirmar_48h_cancelar_24h":
            return "Las citas lejanas no reciben correo al crearlas. Doko envía la confirmación alrededor de 48 horas antes y puede liberar a las 24 horas si no se confirma, según el flujo configurado."
        if modo_confirmacion == "confirmar_24h":
            return "Las citas lejanas no reciben correo al crearlas. Doko envía la confirmación cuando entran en la ventana de 24 horas, según el flujo configurado."
        return "Este consultorio usa confirmación manual. Una cita guardada no implica que Doko envíe un correo inmediatamente."

    respuestas = {
        "cita": "Nueva cita crea un evento de paciente en Doko y Google. Completa fecha y hora; agrega correo si necesitas que Doko pueda enviar mensajes.",
        "tipos_evento": "Bloqueo ocupa el horario de forma interna hasta que lo liberes y no genera correos. Apartado temporal reserva el espacio con vencimiento y después puede convertirse en cita o liberarse.",
        "acciones_cita": "Confirmar marca una cita pendiente como confirmada. Una cita confirmada no se libera desde Doko.",
        "bloqueo": "Bloquear horario marca un espacio como ocupado para que no se agende. Es interno y no envía correos a pacientes.",
        "apartado": "Apartado temporal reserva un horario por un tiempo limitado. Después puedes convertirlo en cita o liberarlo.",
        "editar": "Editar permite cambiar los datos del evento. Si modificas una cita, Doko conserva su tipo y actualiza Google cuando corresponde.",
        "liberar": "Liberar retira bloqueos, apartados o eventos internos. Una cita confirmada no se libera desde Doko.",
        "buscar": "Usa Buscar o consultar agenda para filtrar por fecha, nombre o teléfono. Limpiar filtros vuelve a la vista semanal.",
        "perfil": "Abre Perfil en el menú izquierdo, actualiza los datos del consultorio y toca Guardar perfil. Dirección y Maps se administran desde Mi Centro.",
        "servicios": "Los servicios se administran en Perfil. Puedes agregar, editar o desactivar; esos cambios no modifican la disponibilidad de Calendar.",
        "tema": "Abre Perfil, busca Color del tema, elige la paleta y toca Guardar perfil. El cambio es visual y no modifica citas, correos ni Google.",
        "google": "La conexión con Google se necesita para leer, crear, editar o liberar eventos de agenda y para enviar correos autorizados. Perfil, servicios y colores son independientes.",
        "suffy": "Doko Suffy permite consultar el catálogo, preparar un pedido y revisar su estado. No modifica la agenda médica.",
        "limite_medico": "Puedo explicar cómo usar Doko, pero no puedo diagnosticar, recomendar tratamientos ni tomar decisiones médicas.",
        "fuera_alcance": (
            "No entendí qué parte de Doko quieres revisar. Puedes preguntarme, por ejemplo: "
            "‘¿qué estaba haciendo en esta cita?’, ‘¿cuándo se envía el correo?’ o ‘¿cómo libero un horario?’."
        ),
    }
    return respuestas.get(categoria, respuestas["fuera_alcance"])


def _categoria_error_local(evento: dict | None) -> str | None:
    if not evento:
        return None
    motivo = _texto_normalizado(
        evento.get("correo_registro_error_motivo")
        or evento.get("confirmacion_error_motivo")
        or ""
    )
    if not motivo:
        return None
    if any(valor in motivo for valor in ("invalid_grant", "revoked", "oauth", "reconect", "autoriz")):
        return "oauth"
    if "calendar" in motivo or "calendario" in motivo:
        return "calendar"
    if any(valor in motivo for valor in ("gmail", "correo", "mensaje")):
        return "gmail"
    return "sistema"


def construir_contexto_operativo(
    evento: dict | None,
    modo_confirmacion: str,
    ahora: datetime | None = None,
    confirmacion_dias_habiles: bool = False,
) -> dict:
    """Resume hechos locales. Este objeto nunca se transfiere a Gemini."""
    if not evento:
        return {
            "hay_evento": False,
            "modo_confirmacion": modo_confirmacion,
            "confirmacion_dias_habiles": bool(confirmacion_dias_habiles),
        }
    ahora_local = ahora or datetime.now(TZ_TIJUANA)
    if ahora_local.tzinfo is None:
        ahora_local = ahora_local.replace(tzinfo=TZ_TIJUANA)
    fecha = _fecha_local(evento.get("fecha_cita"))
    ventana = "sin_fecha"
    if fecha:
        dias = (fecha.date() - ahora_local.date()).days
        if dias < 0:
            ventana = "pasada"
        elif dias == 0:
            ventana = "hoy"
        elif dias == 1:
            ventana = "manana"
        elif dias <= 7:
            ventana = "proximos_7_dias"
        else:
            ventana = "lejana"

    tipo = str(evento.get("tipo_evento") or "CITA_PACIENTE").upper()
    estatus = str(evento.get("estatus_confirmacion") or "Pendiente").upper()
    origen = str(evento.get("origen_evento") or "externo").lower()
    if origen.startswith("doko"):
        origen_operativo = "doko"
    elif evento.get("es_reserva_google"):
        origen_operativo = "google_reserva"
    elif origen in {"google_calendar", "google"}:
        origen_operativo = "google_calendar"
    else:
        origen_operativo = "google_externo"
    flujo = describir_flujo_correo(evento, modo_confirmacion, ahora=ahora_local)
    expiracion = _fecha_local(evento.get("expiracion_apartado"))
    token_expiracion = _fecha_local(evento.get("token_expiracion"))
    confirmacion_enviada = _fecha_local(evento.get("confirmacion_enviada_en"))
    return {
        "hay_evento": True,
        "tipo": tipo,
        "estado_operativo": str(evento.get("estado_operativo") or "activo").lower(),
        "confirmada": "CONFIRM" in estatus or "VERIFIC" in estatus,
        "cancelada": "CANCEL" in estatus,
        "origen": origen_operativo,
        "tiene_correo": bool(evento.get("tiene_correo")),
        "tiene_telefono": bool(evento.get("tiene_telefono")),
        "ventana": ventana,
        "modo_confirmacion": modo_confirmacion,
        "confirmacion_dias_habiles": bool(
            evento.get("confirmacion_dias_habiles", confirmacion_dias_habiles)
        ),
        "flujo_correo": flujo.get("estado"),
        "requiere_confirmacion": evento.get("requiere_confirmacion_enlace") is not False,
        "confirmacion_enviada": bool(confirmacion_enviada),
        "plazo_confirmacion_vencido": bool(token_expiracion and token_expiracion <= ahora_local),
        "cancelacion_automatica": bool(evento.get("cancelacion_automatica_en")),
        "categoria_error": _categoria_error_local(evento),
        "apartado_vencido": bool(expiracion and expiracion <= ahora_local),
    }


def _explicacion_correo(categoria: str, contexto: dict, evento: dict | None, modo: str) -> dict:
    if not contexto.get("hay_evento"):
        if modo == "confirmar_48h_cancelar_24h" and contexto.get("confirmacion_dias_habiles"):
            siguiente = "La confirmación se intenta dos días hábiles antes y el ciclo no se procesa en fin de semana."
        elif modo == "confirmar_48h_cancelar_24h":
            siguiente = "La confirmacion se intenta alrededor de 48 horas antes de cada cita pendiente."
        elif modo == "confirmar_24h":
            siguiente = "La confirmacion se intenta cuando la cita entra en la ventana de 24 horas."
        else:
            siguiente = "El consultorio usa confirmacion manual."
        return {
            "respuesta": f"No hay una cita seleccionada. {siguiente} Abre la cita y usa Preguntar a Doko para revisar su caso exacto.",
            "detectado": "No hay una cita seleccionada para revisar.",
            "causa": "Sin contexto solo puedo explicar la regla general del consultorio.",
            "siguiente": siguiente,
            "accion": "Abre una cita y usa Preguntar a Doko para revisar su caso exacto.",
        }

    estado = contexto.get("flujo_correo")
    detectado = describir_flujo_correo(evento or {}, modo)["mensaje"]
    if estado == "sin_correo":
        causa = "Doko no tiene una direccion a la cual enviar el mensaje."
        siguiente = "La cita permanecera guardada, pero no entrara al envio por correo."
        accion = "Agrega el correo y guarda los cambios si el paciente desea recibir mensajes."
    elif estado == "enviado_ahora":
        causa = "El registro local indica que Doko ya completo un envio para esta cita."
        siguiente = "El paciente puede recibirlo en bandeja principal, Spam o Correo no deseado."
        accion = "Pide revisar esas carpetas; no vuelvas a crear la cita."
    elif estado == "error_envio":
        error = contexto.get("categoria_error")
        causa = {
            "oauth": "La autorizacion de Google necesita revision.",
            "gmail": "Gmail no pudo completar el envio.",
            "calendar": "Google Calendar presento una falla relacionada.",
        }.get(error, "El ultimo intento tecnico no se completo.")
        siguiente = "La cita sigue guardada aunque el correo haya fallado."
        accion = "Revisa la conexion con Google y vuelve a consultar el estado; no dupliques el evento."
    elif estado == "programado_confirmacion":
        causa = "Todavia no corresponde enviar la confirmacion; guardar una cita lejana no la envia de inmediato."
        if modo == "confirmar_48h_cancelar_24h" and contexto.get("confirmacion_dias_habiles"):
            siguiente = "Doko la revisará dos días hábiles antes y no procesará el ciclo en sábado ni domingo."
        elif modo == "confirmar_48h_cancelar_24h":
            siguiente = "Doko la revisara alrededor de 48 horas antes de la cita."
        elif modo == "confirmar_24h":
            siguiente = "Doko la revisara cuando entre en la ventana de 24 horas."
        else:
            siguiente = "Este consultorio revisa la confirmacion de forma manual."
        accion = "No necesitas crearla otra vez; conserva el correo y deja que siga su ciclo."
    else:
        causa = "Por su tipo o estado, esta cita no espera otro correo automatico."
        siguiente = "Doko conservara el estado operativo actual."
        accion = "Revisa si esta confirmada, cancelada o configurada sin enlace adicional."

    if categoria == "correo_diferencias":
        detectado = "Doko maneja dos mensajes distintos: comprobante informativo y confirmacion."
        causa = "El comprobante informa una cita cercana creada directamente; la confirmacion aplica la politica 24/48 horas."
        siguiente = "Cada mensaje conserva su propio registro y no deben confundirse."
        accion = "Consulta el estado de esta cita para saber cual de los dos aplica."
        respuesta = (
            "Doko maneja dos correos distintos: uno informa una cita cercana creada directamente "
            "y otro solicita confirmacion segun la politica de 24/48 horas."
        )
    elif estado == "no_aplica":
        respuesta = detectado
    elif estado == "sin_correo":
        respuesta = "Esta cita no tiene correo, por eso Doko no puede enviar mensajes. Agrega el correo y guarda los cambios."
    elif estado == "enviado_ahora":
        respuesta = "Doko ya registro un envio para esta cita. Pide revisar la bandeja principal, Spam o Correo no deseado; no vuelvas a crearla."
    elif estado == "error_envio":
        respuesta = f"El correo no se completo: {causa} La cita sigue guardada. {accion}"
    elif estado == "programado_confirmacion":
        respuesta = f"{detectado} No necesitas crearla otra vez; conserva el correo y deja que siga su ciclo."
    else:
        respuesta = f"{detectado} {accion}"
    return {
        "respuesta": respuesta,
        "detectado": detectado,
        "causa": causa,
        "siguiente": siguiente,
        "accion": accion,
    }


def explicacion_operativa(
    categoria: str,
    modo_confirmacion: str,
    evento: dict | None = None,
    contexto_interfaz: str = "modulo_asistente",
    confirmacion_dias_habiles: bool = False,
    continuidad_edicion: bool = False,
) -> dict:
    contexto = construir_contexto_operativo(
        evento,
        modo_confirmacion,
        confirmacion_dias_habiles=confirmacion_dias_habiles,
    )
    if categoria == "estado_cita":
        if not contexto.get("hay_evento"):
            respuesta = "Abre una cita y usa Preguntar a Doko para revisar su estado real."
        elif contexto.get("tipo") != "CITA_PACIENTE":
            respuesta = (
                "Este registro es un evento interno, no una cita de paciente. "
                "No usa el estado de confirmacion del paciente."
            )
        elif contexto.get("cancelada") or contexto.get("estado_operativo") != "activo":
            respuesta = (
                "Esta cita esta cancelada o liberada. El registro queda disponible en el historial; "
                "si el paciente necesita otra fecha, crea una cita nueva con sus datos de contacto."
            )
        elif contexto.get("confirmada"):
            respuesta = (
                "Si, esta cita esta confirmada. Puedes editarla, pero Doko no permite liberarla; "
                "si debe cancelarse, sigue el flujo de cancelacion del consultorio."
            )
        else:
            respuesta = (
                "No, esta cita sigue pendiente. Puedes confirmarla manualmente o dejar que continúe "
                "el flujo de confirmacion configurado para el consultorio."
            )
        return {"respuesta": respuesta, "detectado": respuesta, "causa": "", "siguiente": "", "accion": ""}

    if categoria == "recrear_cancelada":
        if not contexto.get("hay_evento"):
            respuesta = "Abre una cita cancelada desde el historial para reutilizar sus datos de contacto."
        elif contexto.get("cancelada") or contexto.get("estado_operativo") != "activo":
            respuesta = (
                "El registro cancelado no se modifica. En Historial de cancelaciones usa Crear nueva cita: "
                "Doko copiara solamente nombre, telefono y correo; tu eliges la nueva fecha y hora."
            )
        else:
            respuesta = (
                "Esta cita sigue activa. Si solo necesita otra fecha u hora, editala; "
                "no hace falta crear un duplicado."
            )
        return {"respuesta": respuesta, "detectado": respuesta, "causa": "", "siguiente": "", "accion": ""}

    if categoria == "correo_hora":
        if contexto.get("confirmacion_enviada"):
            respuesta = "La confirmacion de esta cita ya fue enviada; no espera otro primer correo."
        elif modo_confirmacion == "confirmar_24h":
            respuesta = (
                "No tiene una hora fija para todas las citas. Doko la envia cuando entra en la ventana de "
                "24 horas, normalmente cerca de la misma hora del dia anterior; el job revisa cada 15 minutos."
            )
        elif modo_confirmacion == "confirmar_48h_cancelar_24h":
            fecha = _fecha_local((evento or {}).get("fecha_cita"))
            if fecha and fecha.hour < 14:
                respuesta = "Doko intentara enviarla alrededor de las 8:00 a. m., dos dias antes de esta cita."
            else:
                respuesta = "Doko intentara enviarla alrededor de las 9:00 a. m., dos dias antes de esta cita."
            if contexto.get("confirmacion_dias_habiles"):
                respuesta = respuesta.replace("dos dias antes", "dos días hábiles antes")
                respuesta += " No se envía en sábado ni domingo."
            respuesta += " El job revisa cada 15 minutos, por lo que puede completarse en el siguiente ciclo."
        else:
            respuesta = "Este consultorio usa confirmacion manual, por lo que Doko no tiene una hora automatica de envio."
        return {"respuesta": respuesta, "detectado": respuesta, "causa": "", "siguiente": "", "accion": ""}

    if categoria == "sin_confirmar":
        if contexto.get("confirmada"):
            respuesta = "Esta cita ya esta confirmada; no entrara al flujo de no confirmadas."
        elif modo_confirmacion == "confirmar_48h_cancelar_24h":
            if contexto.get("confirmacion_dias_habiles"):
                respuesta = (
                    "Si el paciente no confirma, Doko espera hasta el siguiente día hábil para intentar "
                    "cancelar la cita y liberar el horario en Google Calendar. No ejecuta esta liberación "
                    "en sábado ni domingo. Si Google falla, conserva la cita activa y registra el error."
                )
            else:
                respuesta = (
                    "Si el paciente no confirma dentro de las 24 horas posteriores al correo, Doko intenta "
                    "cancelar la cita y liberar el horario en Google Calendar. Si Google falla, conserva la cita "
                    "activa y registra el error para volver a revisarla."
                )
        elif modo_confirmacion == "confirmar_24h":
            respuesta = (
                "Si el paciente no confirma, la cita permanece pendiente; esta politica no la libera "
                "automaticamente. La asistente puede revisarla o confirmarla manualmente."
            )
        else:
            respuesta = "Este consultorio usa revision manual; una cita sin confirmar permanece pendiente hasta que la asistente actue."
        return {"respuesta": respuesta, "detectado": respuesta, "causa": "", "siguiente": "", "accion": ""}

    if categoria == "confirmacion_anticipada":
        fecha_cita = _descripcion_fecha_operativa((evento or {}).get("fecha_cita"))
        envio_programado = _descripcion_envio_programado(evento, modo_confirmacion)
        referencia_cita = f" programada {fecha_cita}" if fecha_cita else ""
        if contexto.get("confirmada"):
            respuesta = (
                f"Esta cita{referencia_cita} ya quedo confirmada. Doko no enviara el enlace de confirmacion ni la liberara "
                "automaticamente; si tiene correo, puede recibir el aviso de confirmada y sus recordatorios. "
                "Verifica la asistencia directamente con el paciente. Si la cita sigue vigente, dejala confirmada; "
                "si el paciente la rechaza, cancelala desde Google Calendar y Doko reflejara la cancelacion al sincronizar. "
                "No dupliques la cita ni intentes liberarla."
            )
        else:
            referencia_envio = (
                f" La confirmacion automatica estaba prevista {envio_programado.rstrip('.')}."
                if envio_programado
                else ""
            )
            respuesta = (
                f"Esta cita{referencia_cita} sigue pendiente.{referencia_envio} "
                "Si la confirmas manualmente ahora, Doko la marcara como confirmada de inmediato. "
                "Ya no enviara el enlace 24/48 horas ni la liberara por falta de confirmacion; si tiene correo, "
                "puede enviar el aviso de confirmada. Si ocurre por accidente, verifica directamente con el paciente: "
                "dejala confirmada si asistira o cancelala desde Google Calendar si la rechaza. Doko reflejara esa "
                "cancelacion al sincronizar; no dupliques la cita."
            )
        return {"respuesta": respuesta, "detectado": respuesta, "causa": "", "siguiente": "", "accion": ""}

    if categoria in {"correo", "confirmacion", "correo_cuando", "correo_no_llego", "correo_diferencias"}:
        return _explicacion_correo(categoria, contexto, evento, modo_confirmacion)

    if categoria == "origen_cita":
        origen = contexto.get("origen")
        respuestas = {
            "doko": (
                "Esta cita fue creada desde Doko. Doko la identifica por su marcador interno y puede "
                "explicar su flujo de correo y confirmacion."
            ),
            "google_reserva": (
                "Esta cita entro desde Google Calendar y Doko encontro señales de una reserva de Google. "
                "No fue creada desde el formulario interno de Doko."
            ),
            "google_calendar": (
                "Esta cita entro desde Google Calendar con datos de paciente. Doko no puede asegurar que "
                "provenga de la pagina de reservas; tambien pudo haberse creado directamente en Calendar."
            ),
            "google_externo": (
                "Este evento entro desde Google Calendar sin el marcador de Doko ni datos suficientes para "
                "tratarlo automaticamente como cita de paciente."
            ),
        }
        respuesta = respuestas.get(origen, respuestas["google_externo"])
        return {"respuesta": respuesta, "detectado": respuesta, "causa": "", "siguiente": "", "accion": ""}

    if categoria == "liberacion_automatica":
        if not contexto.get("hay_evento"):
            respuesta = "Abre la cita y usa Preguntar a Doko para revisar por que no se libero."
        elif contexto.get("confirmada"):
            respuesta = "La cita ya esta confirmada, por eso Doko no la libera automaticamente."
        elif contexto.get("cancelada") or contexto.get("estado_operativo") != "activo":
            respuesta = "La cita ya esta cancelada o liberada; puede requerir actualizar la agenda para reflejarlo."
        elif modo_confirmacion != "confirmar_48h_cancelar_24h":
            respuesta = "Este consultorio no tiene activa la liberacion automatica despues de 24 horas."
        elif not contexto.get("requiere_confirmacion"):
            respuesta = (
                "Esta cita no usa enlace de confirmacion, por eso no entra en la liberacion automatica. "
                "Esto puede ocurrir con una cita cercana creada desde Doko que recibio solo un correo informativo."
            )
        elif not contexto.get("tiene_correo"):
            respuesta = (
                "La cita no tiene correo. Doko no pudo enviar la confirmacion y, sin un envio registrado, "
                "no inicia el plazo de 24 horas ni la libera automaticamente."
            )
        elif not contexto.get("confirmacion_enviada"):
            if contexto.get("categoria_error"):
                respuesta = (
                    "La confirmacion no se envio correctamente, por eso no inicio el plazo de 24 horas. "
                    "La cita se conserva para evitar liberar un horario sin haber avisado al paciente."
                )
            else:
                respuesta = (
                    "Doko aun no registra el envio de confirmacion. El plazo de 24 horas empieza despues "
                    "de ese envio, no desde que se creo la cita."
                )
        elif not contexto.get("plazo_confirmacion_vencido"):
            respuesta = "Doko ya envio la confirmacion, pero el plazo de 24 horas todavia no ha vencido."
        elif contexto.get("categoria_error"):
            respuesta = (
                "El plazo ya vencio, pero Doko no pudo completar la liberacion en Google Calendar. "
                "La cita se mantuvo activa para no perderla y volvera a revisarse."
            )
        else:
            respuesta = (
                "La cita ya cumple las condiciones para liberarse. Si sigue activa, el job programado aun "
                "no ha completado el ciclo o fue interrumpido; actualiza la agenda y revisa Sistema."
            )
        return {"respuesta": respuesta, "detectado": respuesta, "causa": "", "siguiente": "", "accion": ""}

    if categoria == "acciones_cita":
        tipo = contexto.get("tipo")
        if not contexto.get("hay_evento"):
            respuesta = "Abre una cita o evento y usa Preguntar a Doko para ver las acciones que le corresponden."
        elif contexto.get("estado_operativo") != "activo" or contexto.get("cancelada"):
            respuesta = "Este evento ya esta cancelado o liberado y no tiene acciones operativas pendientes."
        elif tipo == "CITA_PACIENTE" and contexto.get("confirmada"):
            respuesta = "Esta cita ya esta confirmada. Puedes editarla, pero Doko no permite liberarla; si debe cancelarse, hazlo en Google Calendar para que Doko lo sincronice."
        elif tipo == "CITA_PACIENTE":
            respuesta = "Esta cita esta pendiente. Usa Confirmar para validarla o Editar para corregir sus datos; una vez confirmada ya no podras liberarla desde Doko."
        elif tipo == "APARTADO_TEMPORAL":
            respuesta = "En este apartado puedes usar Hacer cita para convertirlo, Editar para ajustarlo o Liberar si ya no necesitas el horario."
        elif tipo in {"BLOQUEO_HORARIO", "EVENTO_INTERNO"}:
            respuesta = "Este evento es interno. Puedes editarlo o usar Liberar para retirar el evento de Google Calendar y recuperar el horario."
        else:
            respuesta = "Puedes editar este evento; las demas acciones dependen de su tipo y estado."
        return {"respuesta": respuesta, "detectado": respuesta, "causa": "", "siguiente": "", "accion": ""}

    if categoria in {"liberar_confirmada", "confirmar_manual", "liberar"}:
        if categoria == "confirmar_manual" and contexto.get("hay_evento") and not contexto.get("confirmada"):
            respuesta = (
                "Si el paciente no puede entrar a su correo, puedes confirmar la cita manualmente. "
                "Vuelve a la cita y toca Confirmar; no necesitas abrir el enlace del paciente."
            )
            return {"respuesta": respuesta, "detectado": respuesta, "causa": "", "siguiente": "", "accion": ""}
        if contexto.get("hay_evento") and contexto.get("confirmada"):
            return {
                "detectado": "La cita seleccionada ya esta confirmada.",
                "causa": "Doko protege una cita confirmada y no permite liberarla como un bloqueo o apartado.",
                "siguiente": "El horario permanecera ocupado mientras conserve ese estado.",
                "accion": "Si debe cancelarse, sigue el flujo de cancelacion del consultorio; no uses Liberar.",
            }
        return {
            "detectado": "La confirmacion y la liberacion son acciones diferentes.",
            "causa": "Confirmar valida una cita pendiente; Liberar se reserva para eventos internos o citas aun liberables.",
            "siguiente": "Una cita confirmada deja de mostrar la accion Liberar.",
            "accion": "Confirma solo cuando corresponda o libera el evento antes de confirmarlo.",
        }

    if categoria == "editar_flujo":
        if continuidad_edicion and evento:
            return {
                "detectado": "La pregunta se refiere a la cita que tienes abierta; Doko no la trata como una cita nueva.",
                "causa": (
                    "Todavia no hay informacion suficiente para afirmar la causa. "
                    "Se puede revisar fecha, hora, estado de confirmacion, correo u origen del evento."
                ),
                "siguiente": "Indica cual de esos datos se ve diferente para contrastarlo con el estado actual de esta cita.",
                "accion": "No crees otra cita ni repitas el cambio hasta identificar el dato diferente.",
            }
        return {
            "detectado": "Estas consultando el efecto de editar una cita.",
            "causa": "Cambiar fecha, hora o correo actualiza el evento, pero Doko conserva los envios ya registrados.",
            "siguiente": "La cita se evaluara con su nueva fecha en los siguientes ciclos programados.",
            "accion": "Guarda una sola vez y revisa el resultado de correo que muestra Doko.",
        }

    if categoria == "apartado" and contexto.get("tipo") != "APARTADO_TEMPORAL":
        return {
            "respuesta": (
                "Para apartar un horario, toca Apartado temporal, elige fecha, hora y vencimiento, y guarda. "
                "Despues podras convertirlo en cita o liberarlo."
            ),
            "detectado": "Quieres reservar un horario sin crear todavia una cita de paciente.",
            "causa": "Apartado temporal guarda el espacio mientras completas o confirmas los datos.",
            "siguiente": "El horario quedara reservado hasta convertirlo en cita, liberarlo o llegar a su vencimiento.",
            "accion": "Toca Apartado temporal, elige fecha, hora y vencimiento, y guarda.",
        }

    if categoria in {"apartado_expiracion", "apartado_convertir", "apartado"}:
        vencido = contexto.get("apartado_vencido")
        return {
            "respuesta": (
                "Este espacio es un apartado temporal. Usa Hacer cita si ya tienes los datos necesarios, "
                "o Liberar si ya no necesitas reservarlo."
            ),
            "detectado": "Es un apartado temporal" + (" vencido." if vencido else "."),
            "causa": "El apartado reserva el espacio sin tratarlo todavia como cita de paciente.",
            "siguiente": "Puede convertirse en cita o liberarse; al vencer, Doko puede recuperar el horario segun su estado.",
            "accion": "Usa Hacer cita si ya tienes los datos necesarios, o Liberar si el espacio ya no se necesita.",
        }

    if categoria == "evento_externo":
        return {
            "detectado": "El evento fue creado fuera de Doko y todavia no tiene clasificacion operativa completa.",
            "causa": "Google Calendar no siempre incluye correo, telefono o tipo de evento de Doko.",
            "siguiente": "Doko lo conserva visible para no perder el horario ocupado.",
            "accion": "Editalo y completa los datos solo si debe tratarse como cita; si es personal, dejalo como interno.",
        }

    if categoria in {"google", "google_alcance", "perfil_sin_google"}:
        error = contexto.get("categoria_error")
        if error == "oauth":
            respuesta = "La autorizacion de Google necesita reconexion. Las acciones de agenda y correo pueden fallar hasta restablecerla; Perfil, servicios y colores siguen funcionando."
        elif error == "gmail":
            respuesta = "Gmail no completo el ultimo envio. La cita sigue guardada; revisa la conexion con Google antes de intentar otro correo."
        elif error == "calendar":
            respuesta = "Google Calendar no completo la ultima accion de agenda. No dupliques el evento; actualiza la agenda y revisa la conexion."
        else:
            respuesta = "Google se usa para leer, crear, editar o liberar eventos y para enviar correos. Perfil, servicios, horarios informativos y colores son independientes; reconecta solo si falla agenda o correo."
        return {"respuesta": respuesta, "detectado": respuesta, "causa": "", "siguiente": "", "accion": ""}

    base = respuesta_operativa(categoria, modo_confirmacion, evento, contexto_interfaz)
    return {
        "detectado": base,
        "causa": "",
        "siguiente": "",
        "accion": "",
    }


def respuesta_desde_explicacion(explicacion: dict) -> str:
    respuesta = str(explicacion.get("respuesta") or "").strip()
    if respuesta:
        return respuesta
    partes = []
    for clave in ("detectado", "causa", "siguiente", "accion"):
        texto = str(explicacion.get(clave) or "").strip()
        if texto and texto not in partes:
            partes.append(texto)
    return " ".join(partes)
