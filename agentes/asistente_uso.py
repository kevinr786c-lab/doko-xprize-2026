import hashlib
import hmac
import uuid
from dataclasses import dataclass
from decimal import Decimal

from config_bunker import (
    GEMINI_INPUT_USD_PER_MILLION,
    GEMINI_OUTPUT_USD_PER_MILLION,
    JWT_SECRET,
    PANEL_ASSISTANT_GEMINI_ACTOR_HOURLY_LIMIT,
    PANEL_ASSISTANT_GEMINI_CLINIC_DAILY_LIMIT,
    PANEL_ASSISTANT_GEMINI_COOLDOWN_SECONDS,
    PANEL_ASSISTANT_GEMINI_GLOBAL_DAILY_LIMIT,
)
from helpers.db import get_connection


ESTADOS_LLAMADA = ("reservado", "resuelto", "error")


@dataclass(frozen=True)
class ReservaGemini:
    permitida: bool
    id_uso: str | None = None
    motivo: str | None = None
    restante_consultorio: int | None = None


def hash_actor(correo_doctor: str, actor_rol: str, id_usuario: str | None) -> str:
    identidad = str(id_usuario or correo_doctor or "actor").strip().lower()
    mensaje = f"asistente-panel:{actor_rol}:{identidad}".encode("utf-8")
    secreto = str(JWT_SECRET or "doko").encode("utf-8")
    return hmac.new(secreto, mensaje, hashlib.sha256).hexdigest()


def _insertar_uso(
    cur,
    *,
    correo_doctor: str,
    actor_hash: str,
    actor_rol: str,
    fuente: str,
    categoria: str,
    estado: str,
    motivo_limite: str | None = None,
) -> str:
    id_uso = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO IA_ASISTENTE_USO (
            id_uso, correo_doctor, actor_hash, actor_rol,
            fuente, categoria, estado, motivo_limite
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            id_uso,
            correo_doctor,
            actor_hash,
            actor_rol,
            fuente,
            categoria,
            estado,
            motivo_limite,
        ),
    )
    return id_uso


def registrar_regla(
    correo_doctor: str,
    actor_hash: str,
    actor_rol: str,
    categoria: str,
    duracion_ms: int,
) -> None:
    conn = get_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        id_uso = _insertar_uso(
            cur,
            correo_doctor=correo_doctor,
            actor_hash=actor_hash,
            actor_rol=actor_rol,
            fuente="reglas",
            categoria=categoria,
            estado="resuelto",
        )
        cur.execute(
            "UPDATE IA_ASISTENTE_USO SET duracion_ms = %s WHERE id_uso = %s",
            (max(0, int(duracion_ms)), id_uso),
        )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()


def reservar_gemini(
    correo_doctor: str,
    actor_hash: str,
    actor_rol: str,
    categoria: str = "pendiente_clasificacion",
) -> ReservaGemini:
    """Reserva una llamada con bloqueos PostgreSQL validos entre instancias."""
    conn = get_connection()
    if not conn:
        return ReservaGemini(False, motivo="telemetria_no_disponible")
    try:
        cur = conn.cursor()
        claves = sorted({
            "ia-asistente:global",
            f"ia-asistente:consultorio:{correo_doctor.strip().lower()}",
            f"ia-asistente:actor:{actor_hash}",
        })
        for clave in claves:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (clave,))

        estados = ESTADOS_LLAMADA
        cur.execute(
            """
            SELECT COUNT(*)
            FROM IA_ASISTENTE_USO
            WHERE fuente = 'gemini_intent'
              AND estado = ANY(%s)
              AND fecha_evento >= DATE_TRUNC('day', NOW())
            """,
            (list(estados),),
        )
        total_global = int(cur.fetchone()[0] or 0)
        cur.execute(
            """
            SELECT COUNT(*)
            FROM IA_ASISTENTE_USO
            WHERE fuente = 'gemini_intent'
              AND estado = ANY(%s)
              AND correo_doctor = %s
              AND fecha_evento >= DATE_TRUNC('day', NOW())
            """,
            (list(estados), correo_doctor),
        )
        total_consultorio = int(cur.fetchone()[0] or 0)
        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE fecha_evento >= NOW() - INTERVAL '1 hour') AS ultima_hora,
                COUNT(*) FILTER (
                    WHERE estado = 'reservado'
                      AND fecha_evento >= NOW() - INTERVAL '2 minutes'
                ) AS activas,
                MAX(fecha_evento) AS ultima_llamada
            FROM IA_ASISTENTE_USO
            WHERE fuente = 'gemini_intent'
              AND actor_hash = %s
              AND estado = ANY(%s)
            """,
            (actor_hash, list(estados)),
        )
        actor = cur.fetchone()
        total_actor_hora = int(actor[0] or 0)
        llamadas_activas = int(actor[1] or 0)
        ultima_llamada = actor[2]

        motivo = None
        if total_global >= PANEL_ASSISTANT_GEMINI_GLOBAL_DAILY_LIMIT:
            motivo = "limite_global_diario"
        elif total_consultorio >= PANEL_ASSISTANT_GEMINI_CLINIC_DAILY_LIMIT:
            motivo = "limite_consultorio_diario"
        elif total_actor_hora >= PANEL_ASSISTANT_GEMINI_ACTOR_HOURLY_LIMIT:
            motivo = "limite_actor_hora"
        elif llamadas_activas:
            motivo = "llamada_en_curso"
        elif ultima_llamada:
            cur.execute(
                "SELECT EXTRACT(EPOCH FROM (NOW() - %s))",
                (ultima_llamada,),
            )
            segundos = float(cur.fetchone()[0] or 0)
            if segundos < PANEL_ASSISTANT_GEMINI_COOLDOWN_SECONDS:
                motivo = "espera_breve"

        if motivo:
            _insertar_uso(
                cur,
                correo_doctor=correo_doctor,
                actor_hash=actor_hash,
                actor_rol=actor_rol,
                fuente="gemini_intent",
                categoria=categoria,
                estado="limitado",
                motivo_limite=motivo,
            )
            conn.commit()
            return ReservaGemini(
                False,
                motivo=motivo,
                restante_consultorio=max(
                    0,
                    PANEL_ASSISTANT_GEMINI_CLINIC_DAILY_LIMIT - total_consultorio,
                ),
            )

        id_uso = _insertar_uso(
            cur,
            correo_doctor=correo_doctor,
            actor_hash=actor_hash,
            actor_rol=actor_rol,
            fuente="gemini_intent",
            categoria=categoria,
            estado="reservado",
        )
        conn.commit()
        return ReservaGemini(
            True,
            id_uso=id_uso,
            restante_consultorio=max(
                0,
                PANEL_ASSISTANT_GEMINI_CLINIC_DAILY_LIMIT - total_consultorio - 1,
            ),
        )
    except Exception:
        conn.rollback()
        return ReservaGemini(False, motivo="telemetria_no_disponible")
    finally:
        conn.close()


def finalizar_gemini(
    id_uso: str,
    *,
    categoria: str,
    resultado=None,
    duracion_ms: int,
    error: bool = False,
) -> None:
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
            UPDATE IA_ASISTENTE_USO
            SET actualizado_en = NOW(), categoria = %s, estado = %s,
                modelo = %s, tokens_entrada = %s, tokens_salida = %s,
                tokens_razonamiento = %s, tokens_total = %s,
                costo_estimado_usd = %s, duracion_ms = %s
            WHERE id_uso = %s AND estado = 'reservado'
            """,
            (
                categoria,
                "error" if error else "resuelto",
                str(getattr(resultado, "modelo", "") or "") or None,
                entrada,
                salida,
                razonamiento,
                total,
                costo,
                max(0, int(duracion_ms)),
                id_uso,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()
