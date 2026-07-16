"""Analisis controlado de implementacion operativa, sin datos de pacientes."""

import hashlib
import hmac
import json
import re
import time
import unicodedata
import uuid
from dataclasses import dataclass
from decimal import Decimal

from agentes.gemini_client import generar_texto_medido
from config_bunker import (
    GEMINI_INPUT_USD_PER_MILLION,
    GEMINI_OUTPUT_USD_PER_MILLION,
    IMPLEMENTATION_AI_CLINIC_DAILY_LIMIT,
    IMPLEMENTATION_AI_COOLDOWN_SECONDS,
    IMPLEMENTATION_AI_GLOBAL_DAILY_LIMIT,
    IMPLEMENTATION_AI_MAX_INPUT_CHARS,
    IMPLEMENTATION_AI_MAX_OUTPUT_TOKENS,
    JWT_SECRET,
)
from helpers.db import get_connection


@dataclass(frozen=True)
class ReservaEvaluacion:
    permitida: bool
    id_uso: str | None = None
    motivo: str | None = None
    restante_consultorio: int | None = None


def _normalizar(texto: str) -> str:
    valor = unicodedata.normalize("NFKC", str(texto or ""))
    return re.sub(r"\s+", " ", valor).strip()


def _reemplazar_literal(texto: str, valor: str) -> str:
    limpio = _normalizar(valor)
    if len(limpio) < 2:
        return texto
    return re.sub(re.escape(limpio), "[persona]", texto, flags=re.IGNORECASE)


def sanear_texto(texto: str, nombres_conocidos=()) -> str:
    """Elimina identificadores antes de construir el prompt de Gemini."""
    valor = _normalizar(texto)[:5000]
    for nombre in nombres_conocidos:
        valor = _reemplazar_literal(valor, nombre)

    patrones = (
        (r"https?://\S+|www\.\S+", "[url]"),
        (r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[correo]"),
        (r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", "[identificador]"),
        (r"\b(?:paciente|doctora|doctor|dra\.?|dr\.?|asistente|sra\.?|sr\.?)\s+(?:de\s+)?[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+(?:\s+[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+){0,2}", "[persona]"),
        (r"\b(?:\+?\d[\s().-]*){4,}\b", "[numero]"),
        (r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", "[fecha]"),
        (r"\b(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+\d{1,2}\b", "[fecha]"),
        (r"\b\d+\b", "[numero]"),
    )
    for patron, reemplazo in patrones:
        valor = re.sub(patron, reemplazo, valor, flags=re.IGNORECASE)
    return _normalizar(valor).lower()


def _hash_actor(id_actor: str) -> str:
    secreto = str(JWT_SECRET or "doko").encode("utf-8")
    mensaje = f"implementacion-operativa:{id_actor or 'admin'}".encode("utf-8")
    return hmac.new(secreto, mensaje, hashlib.sha256).hexdigest()


def _insertar_uso(cur, *, id_evaluacion, correo_doctor, actor_hash, estado, motivo=None):
    id_uso = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO IA_EVALUACION_USO (
            id_uso, id_evaluacion, correo_doctor, actor_hash,
            categoria, estado, motivo_limite
        ) VALUES (%s, %s, %s, %s, 'REVISION_SECCION', %s, %s)
        """,
        (id_uso, id_evaluacion, correo_doctor, actor_hash, estado, motivo),
    )
    return id_uso


def _reservar(id_evaluacion: str, correo_doctor: str, actor_hash: str) -> ReservaEvaluacion:
    conn = get_connection()
    if not conn:
        return ReservaEvaluacion(False, motivo="telemetria_no_disponible")
    try:
        cur = conn.cursor()
        for clave in sorted({
            "ia-evaluacion:global",
            f"ia-evaluacion:consultorio:{correo_doctor.lower()}",
            f"ia-evaluacion:actor:{actor_hash}",
        }):
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (clave,))

        cur.execute(
            """
            SELECT COUNT(*) FROM IA_EVALUACION_USO
            WHERE estado IN ('RESERVADO', 'RESUELTO', 'ERROR')
              AND fecha_evento >= DATE_TRUNC('day', NOW())
            """
        )
        global_hoy = int(cur.fetchone()[0] or 0)
        cur.execute(
            """
            SELECT COUNT(*) FROM IA_EVALUACION_USO
            WHERE estado IN ('RESERVADO', 'RESUELTO', 'ERROR')
              AND correo_doctor = %s
              AND fecha_evento >= DATE_TRUNC('day', NOW())
            """,
            (correo_doctor,),
        )
        consultorio_hoy = int(cur.fetchone()[0] or 0)
        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE estado = 'RESERVADO'
                      AND fecha_evento >= NOW() - INTERVAL '2 minutes'
                ),
                MAX(fecha_evento) FILTER (
                    WHERE estado IN ('RESERVADO', 'RESUELTO', 'ERROR')
                )
            FROM IA_EVALUACION_USO
            WHERE actor_hash = %s
            """,
            (actor_hash,),
        )
        activas, ultima = cur.fetchone()

        motivo = None
        if global_hoy >= IMPLEMENTATION_AI_GLOBAL_DAILY_LIMIT:
            motivo = "limite_global_diario"
        elif consultorio_hoy >= IMPLEMENTATION_AI_CLINIC_DAILY_LIMIT:
            motivo = "limite_consultorio_diario"
        elif int(activas or 0) > 0:
            motivo = "llamada_en_curso"
        elif ultima:
            cur.execute("SELECT EXTRACT(EPOCH FROM (NOW() - %s))", (ultima,))
            if float(cur.fetchone()[0] or 0) < IMPLEMENTATION_AI_COOLDOWN_SECONDS:
                motivo = "espera_breve"

        if motivo:
            _insertar_uso(
                cur,
                id_evaluacion=id_evaluacion,
                correo_doctor=correo_doctor,
                actor_hash=actor_hash,
                estado="LIMITADO",
                motivo=motivo,
            )
            conn.commit()
            return ReservaEvaluacion(
                False,
                motivo=motivo,
                restante_consultorio=max(0, IMPLEMENTATION_AI_CLINIC_DAILY_LIMIT - consultorio_hoy),
            )

        id_uso = _insertar_uso(
            cur,
            id_evaluacion=id_evaluacion,
            correo_doctor=correo_doctor,
            actor_hash=actor_hash,
            estado="RESERVADO",
        )
        conn.commit()
        return ReservaEvaluacion(
            True,
            id_uso=id_uso,
            restante_consultorio=max(0, IMPLEMENTATION_AI_CLINIC_DAILY_LIMIT - consultorio_hoy - 1),
        )
    except Exception:
        conn.rollback()
        return ReservaEvaluacion(False, motivo="telemetria_no_disponible")
    finally:
        conn.close()


def _finalizar(id_uso: str, resultado, duracion_ms: int, error=False):
    conn = get_connection()
    if not conn:
        return
    try:
        entrada = int(getattr(resultado, "tokens_entrada", 0) or 0)
        salida = int(getattr(resultado, "tokens_salida", 0) or 0)
        razonamiento = int(getattr(resultado, "tokens_razonamiento", 0) or 0)
        total = int(getattr(resultado, "tokens_total", 0) or 0)
        costo = (
            Decimal(entrada) * Decimal(str(GEMINI_INPUT_USD_PER_MILLION))
            + Decimal(salida + razonamiento) * Decimal(str(GEMINI_OUTPUT_USD_PER_MILLION))
        ) / Decimal(1_000_000)
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE IA_EVALUACION_USO
            SET estado = %s, actualizado_en = NOW(), modelo = %s,
                tokens_entrada = %s, tokens_salida = %s,
                tokens_razonamiento = %s, tokens_total = %s,
                costo_estimado_usd = %s, duracion_ms = %s
            WHERE id_uso = %s AND estado = 'RESERVADO'
            """,
            (
                "ERROR" if error else "RESUELTO",
                str(getattr(resultado, "modelo", "") or "") or None,
                entrada, salida, razonamiento, total, costo,
                max(0, int(duracion_ms)), id_uso,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()


def _hallazgos_locales(respuestas):
    total = len(respuestas)
    pendientes = sum(
        1 for item in respuestas
        if any(frase in item.get("respuesta", "") for frase in ("no se", "pendiente", "por definir"))
    )
    hallazgos = [{
        "tipo": "definido",
        "titulo": "Seccion documentada",
        "detalle": f"Doko encontro {total} respuesta(s) operativas para revisar.",
    }]
    if pendientes:
        hallazgos.append({
            "tipo": "aclarar",
            "titulo": "Hay decisiones pendientes",
            "detalle": "Conviene confirmar responsables y limites antes de aprobar el protocolo.",
        })
    hallazgos.append({
        "tipo": "pregunta",
        "titulo": "Siguiente comprobacion",
        "detalle": "Pregunta como se verificara que el acuerdo se cumple en la operacion diaria.",
    })
    return hallazgos[:3]


def _extraer_json(texto: str):
    valor = str(texto or "").strip()
    valor = re.sub(r"^```(?:json)?\s*|\s*```$", "", valor, flags=re.IGNORECASE)
    inicio, fin = valor.find("{"), valor.rfind("}")
    if inicio < 0 or fin <= inicio:
        raise ValueError("Gemini no devolvio JSON")
    return json.loads(valor[inicio:fin + 1])


def _validar_hallazgos(datos):
    permitidos = {"definido", "aclarar", "pregunta", "protocolo"}
    resultado = []
    for item in (datos.get("hallazgos") or [])[:3]:
        tipo = str(item.get("tipo") or "").strip().lower()
        titulo = _normalizar(item.get("titulo"))[:90]
        detalle = _normalizar(item.get("detalle"))[:420]
        if tipo in permitidos and titulo and detalle:
            resultado.append({"tipo": tipo, "titulo": titulo, "detalle": detalle})
    if not resultado:
        raise ValueError("Gemini no devolvio hallazgos validos")
    return resultado


def analizar_seccion(
    *,
    id_evaluacion: str,
    correo_doctor: str,
    id_actor: str,
    seccion: str,
    respuestas,
    nombres_conocidos=(),
):
    seguras = []
    for item in respuestas:
        respuesta = sanear_texto(item.get("respuesta"), nombres_conocidos)
        if respuesta:
            seguras.append({
                "pregunta": sanear_texto(item.get("pregunta"), nombres_conocidos)[:180],
                "respuesta": respuesta[:700],
            })
    if not seguras:
        return {
            "fuente": "REGLAS",
            "hallazgos": [{
                "tipo": "aclarar",
                "titulo": "Falta informacion",
                "detalle": "Completa al menos una respuesta de esta seccion antes de pedir la revision.",
            }],
            "motivo": "sin_respuestas",
        }

    serializado = json.dumps(seguras, ensure_ascii=True)
    if len(serializado) > IMPLEMENTATION_AI_MAX_INPUT_CHARS:
        serializado = serializado[:IMPLEMENTATION_AI_MAX_INPUT_CHARS]
    locales = _hallazgos_locales(seguras)
    actor_hash = _hash_actor(id_actor)
    reserva = _reservar(id_evaluacion, correo_doctor, actor_hash)
    if not reserva.permitida:
        return {
            "fuente": "REGLAS",
            "hallazgos": locales,
            "motivo": reserva.motivo,
            "cuota_restante": reserva.restante_consultorio,
        }

    prompt = (
        "Eres un analista de procesos administrativos de consultorios. "
        "No calificas personas, no decides acciones medicas y no apruebas protocolos. "
        "Analiza solamente si el proceso esta definido, que falta aclarar y cual seria "
        "la siguiente pregunta operativa. Devuelve JSON estricto con esta forma: "
        '{"hallazgos":[{"tipo":"definido|aclarar|pregunta|protocolo",'
        '"titulo":"...","detalle":"..."}]}. Maximo tres hallazgos. '
        f"Seccion: {sanear_texto(seccion)}. Respuestas saneadas: {serializado}"
    )
    inicio = time.perf_counter()
    try:
        resultado = generar_texto_medido(
            prompt,
            max_output_tokens=IMPLEMENTATION_AI_MAX_OUTPUT_TOKENS,
            temperature=0,
        )
        hallazgos = _validar_hallazgos(_extraer_json(resultado.texto))
        duracion = int((time.perf_counter() - inicio) * 1000)
        _finalizar(reserva.id_uso, resultado, duracion)
        return {
            "fuente": "GEMINI",
            "hallazgos": hallazgos,
            "cuota_restante": reserva.restante_consultorio,
        }
    except Exception:
        duracion = int((time.perf_counter() - inicio) * 1000)
        _finalizar(reserva.id_uso, None, duracion, error=True)
        return {
            "fuente": "REGLAS",
            "hallazgos": locales,
            "motivo": "gemini_no_disponible",
            "cuota_restante": reserva.restante_consultorio,
        }
