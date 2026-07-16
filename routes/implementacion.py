import json
import uuid

from flask import Blueprint, jsonify, render_template, request, session
from psycopg2.extras import Json, RealDictCursor

from agentes.asistente_evaluacion import analizar_seccion
from helpers.db import get_connection
from helpers.decorators import requiere_rol
from helpers.implementacion_operativa import (
    ESTADOS_IMPLEMENTACION,
    PREGUNTAS_IMPLEMENTACION,
    SECCIONES_IMPLEMENTACION,
    TIPOS_IMPLEMENTACION,
    mapa_preguntas,
    preguntas_asistente,
)


implementacion_bp = Blueprint("implementacion_bp", __name__)

SECCIONES_CODIGOS = {item["codigo"] for item in SECCIONES_IMPLEMENTACION}
DECISIONES_PROTOCOLO = {"ADOPTAR", "ADAPTAR", "NO_APLICA", "DEFINIR_DESPUES"}
DECISIONES_REVISION = {
    "AGREGAR_BORRADOR", "PREGUNTAR_DOCTORA", "ADAPTAR", "DESCARTAR",
}


def _datos():
    return request.get_json(silent=True) or request.form.to_dict()


def _auditar(cur, tipo_evento, detalle):
    cur.execute(
        """
        INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
        VALUES (%s, %s, 'admin', %s, %s)
        """,
        (
            tipo_evento,
            session.get("correo", "admin"),
            json.dumps(detalle, ensure_ascii=False),
            request.remote_addr,
        ),
    )


def _tablas_disponibles(cur):
    cur.execute(
        """
        SELECT (to_regclass('public.protocolos_doko') IS NOT NULL
           AND to_regclass('public.evaluaciones_implementacion') IS NOT NULL
           AND to_regclass('public.evaluacion_respuestas') IS NOT NULL
           AND to_regclass('public.evaluacion_protocolos') IS NOT NULL
           AND to_regclass('public.evaluacion_revisiones') IS NOT NULL
           AND to_regclass('public.ia_evaluacion_uso') IS NOT NULL) AS disponible
        """
    )
    return bool((cur.fetchone() or {}).get("disponible"))


def _buscar_evaluacion(cur, id_evaluacion, bloquear=False):
    sufijo = " FOR UPDATE OF e" if bloquear else ""
    cur.execute(
        """
        SELECT e.*, d.nombre_doctor, d.especialidad,
               u.nombre AS nombre_asistente, u.correo AS correo_asistente
        FROM EVALUACIONES_IMPLEMENTACION e
        JOIN DOCTORES d ON d.correo_doctor = e.correo_doctor
        LEFT JOIN USUARIOS_INTERNOS u ON u.id_usuario = e.id_usuario_asistente
        WHERE e.id_evaluacion = %s
        """ + sufijo,
        (id_evaluacion,),
    )
    return cur.fetchone()


def _protocolos_evaluacion(cur, id_evaluacion):
    cur.execute(
        """
        SELECT * FROM EVALUACION_PROTOCOLOS
        WHERE id_evaluacion = %s
        ORDER BY codigo_protocolo
        """,
        (id_evaluacion,),
    )
    return cur.fetchall()


def _asistente_asignada(cur, correo_doctor, id_usuario):
    if not id_usuario:
        return True
    cur.execute(
        """
        SELECT 1
        FROM ASISTENTES_DOCTORES ad
        JOIN USUARIOS_INTERNOS u ON u.id_usuario = ad.id_usuario
        WHERE ad.correo_doctor = %s AND ad.id_usuario = %s
          AND u.rol = 'asistente' AND u.activo = TRUE
        """,
        (correo_doctor, id_usuario),
    )
    return cur.fetchone() is not None


def _resumen_progreso(respuestas, protocolos, preguntas):
    contestadas = {fila["codigo_pregunta"] for fila in respuestas if fila.get("respuesta_texto") or fila.get("opcion")}
    totales = {}
    for seccion, lista in preguntas.items():
        codigos = {item["codigo"] for item in lista}
        totales[seccion] = {
            "total": len(codigos),
            "contestadas": len(codigos & contestadas),
        }
    totales["protocolos"] = {
        "total": len(protocolos),
        "contestadas": sum(1 for item in protocolos if item["decision"] != "DEFINIR_DESPUES"),
    }
    return totales


def _actualizar_estado_por_respuesta(cur, evaluacion, codigo_pregunta, preguntas):
    estado = evaluacion["estado"]
    if estado == "CERRADA":
        return
    pregunta = preguntas[codigo_pregunta]
    if pregunta["seccion"] == "entrevista":
        requeridas = [p["codigo"] for p in PREGUNTAS_IMPLEMENTACION["entrevista"]]
        cur.execute(
            """
            SELECT COUNT(DISTINCT codigo_pregunta) AS total
            FROM EVALUACION_RESPUESTAS
            WHERE id_evaluacion = %s AND codigo_pregunta = ANY(%s)
              AND (NULLIF(TRIM(respuesta_texto), '') IS NOT NULL OR opcion IS NOT NULL)
            """,
            (evaluacion["id_evaluacion"], requeridas),
        )
        if int((cur.fetchone() or {}).get("total") or 0) == len(requeridas) and estado == "BORRADOR":
            estado = "ENTREVISTA_COMPLETA"
    elif pregunta["seccion"] == "asistente" and evaluacion.get("id_usuario_asistente"):
        requeridas = [p["codigo"] for p in preguntas.values() if p["seccion"] == "asistente"]
        cur.execute(
            """
            SELECT COUNT(DISTINCT codigo_pregunta) AS total
            FROM EVALUACION_RESPUESTAS
            WHERE id_evaluacion = %s AND codigo_pregunta = ANY(%s)
              AND opcion IS NOT NULL
            """,
            (evaluacion["id_evaluacion"], requeridas),
        )
        if requeridas and int((cur.fetchone() or {}).get("total") or 0) == len(requeridas):
            estado = "ASISTENTE_EVALUADA"
    elif pregunta["seccion"] == "seguimiento" and evaluacion.get("aprobacion_confirmada"):
        estado = "SEGUIMIENTO"
    cur.execute(
        """
        UPDATE EVALUACIONES_IMPLEMENTACION
        SET estado = %s, actualizado_en = NOW(), actualizado_por = %s
        WHERE id_evaluacion = %s
        """,
        (estado, session.get("correo", "admin"), evaluacion["id_evaluacion"]),
    )


@implementacion_bp.route("/admin/doctores/implementacion", methods=["GET", "POST"])
@requiere_rol("admin")
def implementaciones():
    conn = get_connection()
    if not conn:
        return (jsonify({"ok": False, "error": "Base de datos no disponible"}), 503) if request.method == "POST" else ("Base de datos no disponible", 503)
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if not _tablas_disponibles(cur):
            if request.method == "POST":
                return jsonify({"ok": False, "error": "Aplica la migracion de Implementacion Operativa"}), 503
            return render_template(
                "admin/implementacion_operativa.html",
                migracion_pendiente=True,
                evaluacion=None,
                evaluaciones=[],
                doctores=[],
                asistentes=[],
                tipos=TIPOS_IMPLEMENTACION,
            )

        if request.method == "POST":
            datos = _datos()
            correo_doctor = str(datos.get("correo_doctor") or "").strip().lower()
            tipo = str(datos.get("tipo") or "DIAGNOSTICO_INICIAL").strip().upper()
            id_asistente = str(datos.get("id_usuario_asistente") or "").strip() or None
            if tipo not in TIPOS_IMPLEMENTACION:
                return jsonify({"ok": False, "error": "Tipo de implementacion no valido"}), 400
            cur.execute(
                "SELECT correo_doctor FROM DOCTORES WHERE correo_doctor = %s AND activo = TRUE",
                (correo_doctor,),
            )
            if not cur.fetchone():
                return jsonify({"ok": False, "error": "Doctora activa no encontrada"}), 404
            if not _asistente_asignada(cur, correo_doctor, id_asistente):
                return jsonify({"ok": False, "error": "La asistente no esta asignada a esta doctora"}), 400

            id_evaluacion = str(uuid.uuid4())
            actor = session.get("correo", "admin")
            cur.execute(
                """
                INSERT INTO EVALUACIONES_IMPLEMENTACION (
                    id_evaluacion, correo_doctor, id_usuario_asistente,
                    tipo, creado_por, actualizado_por
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (id_evaluacion, correo_doctor, id_asistente, tipo, actor, actor),
            )
            cur.execute(
                """
                SELECT id_protocolo, codigo, version, titulo, descripcion, contenido
                FROM PROTOCOLOS_DOKO WHERE estado = 'ACTIVO'
                ORDER BY codigo, version DESC
                """
            )
            vistos = set()
            for protocolo in cur.fetchall():
                if protocolo["codigo"] in vistos:
                    continue
                vistos.add(protocolo["codigo"])
                snapshot = {
                    "codigo": protocolo["codigo"],
                    "version": protocolo["version"],
                    "titulo": protocolo["titulo"],
                    "descripcion": protocolo["descripcion"],
                    "contenido": protocolo["contenido"],
                }
                cur.execute(
                    """
                    INSERT INTO EVALUACION_PROTOCOLOS (
                        id_evaluacion_protocolo, id_evaluacion, id_protocolo,
                        codigo_protocolo, version_protocolo, protocolo_snapshot
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid.uuid4()), id_evaluacion, protocolo["id_protocolo"],
                        protocolo["codigo"], protocolo["version"], Json(snapshot),
                    ),
                )
            _auditar(cur, "IMPLEMENTACION_CREADA", {
                "id_evaluacion": id_evaluacion,
                "correo_doctor": correo_doctor,
                "tipo": tipo,
                "asistente_vinculada": bool(id_asistente),
            })
            conn.commit()
            return jsonify({
                "ok": True,
                "id_evaluacion": id_evaluacion,
                "url": f"/admin/doctores/implementacion/{id_evaluacion}",
            })

        cur.execute(
            """
            SELECT correo_doctor, nombre_doctor, especialidad
            FROM DOCTORES WHERE activo = TRUE ORDER BY nombre_doctor
            """
        )
        doctores = cur.fetchall()
        cur.execute(
            """
            SELECT ad.correo_doctor, u.id_usuario, u.nombre, u.correo
            FROM ASISTENTES_DOCTORES ad
            JOIN USUARIOS_INTERNOS u ON u.id_usuario = ad.id_usuario
            WHERE u.activo = TRUE AND u.rol = 'asistente'
            ORDER BY u.nombre
            """
        )
        asistentes = cur.fetchall()
        cur.execute(
            """
            SELECT e.*, d.nombre_doctor, d.especialidad, u.nombre AS nombre_asistente,
                   COUNT(r.id_respuesta) AS respuestas
            FROM EVALUACIONES_IMPLEMENTACION e
            JOIN DOCTORES d ON d.correo_doctor = e.correo_doctor
            LEFT JOIN USUARIOS_INTERNOS u ON u.id_usuario = e.id_usuario_asistente
            LEFT JOIN EVALUACION_RESPUESTAS r ON r.id_evaluacion = e.id_evaluacion
            GROUP BY e.id_evaluacion, d.nombre_doctor, d.especialidad, u.nombre
            ORDER BY e.actualizado_en DESC
            """
        )
        return render_template(
            "admin/implementacion_operativa.html",
            migracion_pendiente=False,
            evaluacion=None,
            evaluaciones=cur.fetchall(),
            doctores=doctores,
            asistentes=asistentes,
            tipos=TIPOS_IMPLEMENTACION,
            estados=ESTADOS_IMPLEMENTACION,
        )
    except Exception as exc:
        conn.rollback()
        if request.method == "POST":
            return jsonify({"ok": False, "error": str(exc)}), 400
        raise
    finally:
        conn.close()


@implementacion_bp.route("/admin/doctores/implementacion/<id_evaluacion>", methods=["GET", "PATCH"])
@requiere_rol("admin")
def detalle_implementacion(id_evaluacion):
    conn = get_connection()
    if not conn:
        return jsonify({"ok": False, "error": "Base de datos no disponible"}), 503
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        evaluacion = _buscar_evaluacion(cur, id_evaluacion, bloquear=request.method == "PATCH")
        if not evaluacion:
            return jsonify({"ok": False, "error": "Implementacion no encontrada"}), 404

        if request.method == "PATCH":
            if evaluacion["estado"] == "CERRADA":
                return jsonify({"ok": False, "error": "La implementacion ya esta cerrada"}), 409
            datos = _datos()
            id_asistente = datos.get("id_usuario_asistente", evaluacion.get("id_usuario_asistente"))
            id_asistente = str(id_asistente or "").strip() or None
            tipo = str(datos.get("tipo") or evaluacion["tipo"]).strip().upper()
            seccion = str(datos.get("seccion_actual") or evaluacion["seccion_actual"]).strip().lower()
            if tipo not in TIPOS_IMPLEMENTACION or seccion not in SECCIONES_CODIGOS:
                return jsonify({"ok": False, "error": "Datos de implementacion no validos"}), 400
            if not _asistente_asignada(cur, evaluacion["correo_doctor"], id_asistente):
                return jsonify({"ok": False, "error": "La asistente no esta asignada a esta doctora"}), 400
            cur.execute(
                """
                UPDATE EVALUACIONES_IMPLEMENTACION
                SET id_usuario_asistente = %s, tipo = %s, seccion_actual = %s,
                    actualizado_en = NOW(), actualizado_por = %s
                WHERE id_evaluacion = %s
                """,
                (id_asistente, tipo, seccion, session.get("correo", "admin"), id_evaluacion),
            )
            conn.commit()
            return jsonify({"ok": True})

        protocolos = _protocolos_evaluacion(cur, id_evaluacion)
        cur.execute(
            "SELECT * FROM EVALUACION_RESPUESTAS WHERE id_evaluacion = %s ORDER BY fecha_creacion",
            (id_evaluacion,),
        )
        respuestas = cur.fetchall()
        cur.execute(
            """
            SELECT * FROM EVALUACION_REVISIONES
            WHERE id_evaluacion = %s ORDER BY fecha_creacion DESC
            """,
            (id_evaluacion,),
        )
        revisiones = cur.fetchall()
        cur.execute(
            """
            SELECT u.id_usuario, u.nombre, u.correo
            FROM ASISTENTES_DOCTORES ad
            JOIN USUARIOS_INTERNOS u ON u.id_usuario = ad.id_usuario
            WHERE ad.correo_doctor = %s AND u.activo = TRUE AND u.rol = 'asistente'
            ORDER BY u.nombre
            """,
            (evaluacion["correo_doctor"],),
        )
        asistentes = cur.fetchall()
        preguntas = {clave: list(valor) for clave, valor in PREGUNTAS_IMPLEMENTACION.items()}
        preguntas["asistente"] = list(preguntas_asistente(protocolos))
        respuesta_por_codigo = {fila["codigo_pregunta"]: fila for fila in respuestas}
        progreso = _resumen_progreso(respuestas, protocolos, preguntas)
        return render_template(
            "admin/implementacion_operativa.html",
            migracion_pendiente=False,
            evaluacion=evaluacion,
            evaluaciones=[],
            doctores=[],
            asistentes=asistentes,
            protocolos=protocolos,
            respuestas=respuesta_por_codigo,
            revisiones=revisiones,
            preguntas=preguntas,
            secciones=SECCIONES_IMPLEMENTACION,
            progreso=progreso,
            tipos=TIPOS_IMPLEMENTACION,
            estados=ESTADOS_IMPLEMENTACION,
        )
    finally:
        conn.close()


@implementacion_bp.route("/admin/doctores/implementacion/<id_evaluacion>/respuesta", methods=["PATCH"])
@requiere_rol("admin")
def guardar_respuesta(id_evaluacion):
    datos = _datos()
    codigo = str(datos.get("codigo_pregunta") or "").strip()
    opcion = str(datos.get("opcion") or "").strip().upper() or None
    texto = str(datos.get("respuesta_texto") or "").strip()[:6000] or None
    conn = get_connection()
    if not conn:
        return jsonify({"ok": False, "error": "Base de datos no disponible"}), 503
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        evaluacion = _buscar_evaluacion(cur, id_evaluacion, bloquear=True)
        if not evaluacion:
            return jsonify({"ok": False, "error": "Implementacion no encontrada"}), 404
        if evaluacion["estado"] == "CERRADA":
            return jsonify({"ok": False, "error": "La implementacion ya esta cerrada"}), 409
        protocolos = _protocolos_evaluacion(cur, id_evaluacion)
        preguntas = mapa_preguntas(protocolos)
        pregunta = preguntas.get(codigo)
        if not pregunta:
            return jsonify({"ok": False, "error": "Pregunta no valida"}), 400
        opciones_validas = {item[0] for item in pregunta.get("opciones", ())}
        if pregunta["tipo"] == "evaluacion" and opcion not in opciones_validas:
            return jsonify({"ok": False, "error": "Selecciona un resultado operativo"}), 400
        if not texto and not opcion:
            return jsonify({"ok": False, "error": "Escribe una respuesta antes de continuar"}), 400

        cur.execute(
            """
            INSERT INTO EVALUACION_RESPUESTAS (
                id_respuesta, id_evaluacion, etapa, seccion,
                codigo_pregunta, respondente, opcion, respuesta_texto
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id_evaluacion, etapa, codigo_pregunta, respondente)
            DO UPDATE SET opcion = EXCLUDED.opcion,
                          respuesta_texto = EXCLUDED.respuesta_texto,
                          actualizado_en = NOW()
            """,
            (
                str(uuid.uuid4()), id_evaluacion, pregunta["etapa"], pregunta["seccion"],
                codigo, pregunta["respondente"], opcion, texto,
            ),
        )
        _actualizar_estado_por_respuesta(cur, evaluacion, codigo, preguntas)
        conn.commit()
        return jsonify({"ok": True})
    except Exception as exc:
        conn.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    finally:
        conn.close()


@implementacion_bp.route("/admin/doctores/implementacion/<id_evaluacion>/protocolo/<id_protocolo>", methods=["POST"])
@requiere_rol("admin")
def decidir_protocolo(id_evaluacion, id_protocolo):
    datos = _datos()
    decision = str(datos.get("decision") or "").strip().upper()
    adaptacion = str(datos.get("adaptacion_texto") or "").strip()[:8000] or None
    if decision not in DECISIONES_PROTOCOLO:
        return jsonify({"ok": False, "error": "Decision no valida"}), 400
    if decision == "ADAPTAR" and not adaptacion:
        return jsonify({"ok": False, "error": "Describe la adaptacion del consultorio"}), 400
    conn = get_connection()
    if not conn:
        return jsonify({"ok": False, "error": "Base de datos no disponible"}), 503
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        evaluacion = _buscar_evaluacion(cur, id_evaluacion, bloquear=True)
        if not evaluacion:
            return jsonify({"ok": False, "error": "Implementacion no encontrada"}), 404
        if evaluacion["estado"] == "CERRADA":
            return jsonify({"ok": False, "error": "La implementacion ya esta cerrada"}), 409
        cur.execute(
            """
            UPDATE EVALUACION_PROTOCOLOS
            SET decision = %s, adaptacion_texto = %s,
                estado_aprobacion = 'BORRADOR', aprobado_por_nombre = NULL,
                aprobado_en = NULL, actualizado_en = NOW()
            WHERE id_evaluacion_protocolo = %s AND id_evaluacion = %s
            """,
            (decision, adaptacion if decision == "ADAPTAR" else None, id_protocolo, id_evaluacion),
        )
        if cur.rowcount != 1:
            return jsonify({"ok": False, "error": "Protocolo no encontrado"}), 404
        cur.execute(
            """
            UPDATE EVALUACIONES_IMPLEMENTACION
            SET aprobacion_confirmada = FALSE, aprobado_por_nombre = NULL,
                aprobado_en = NULL,
                estado = CASE WHEN estado = 'BORRADOR' THEN estado ELSE 'ENTREVISTA_COMPLETA' END,
                actualizado_en = NOW(), actualizado_por = %s
            WHERE id_evaluacion = %s
            """,
            (session.get("correo", "admin"), id_evaluacion),
        )
        conn.commit()
        return jsonify({"ok": True})
    except Exception as exc:
        conn.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    finally:
        conn.close()


@implementacion_bp.route("/admin/doctores/implementacion/<id_evaluacion>/analizar-seccion", methods=["POST"])
@requiere_rol("admin")
def analizar_implementacion(id_evaluacion):
    seccion = str(_datos().get("seccion") or "").strip().lower()
    if seccion not in {"datos", "entrevista", "asistente", "plan", "seguimiento", "resumen"}:
        return jsonify({"ok": False, "error": "Seccion no valida"}), 400
    conn = get_connection()
    if not conn:
        return jsonify({"ok": False, "error": "Base de datos no disponible"}), 503
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        evaluacion = _buscar_evaluacion(cur, id_evaluacion)
        if not evaluacion:
            return jsonify({"ok": False, "error": "Implementacion no encontrada"}), 404
        protocolos = _protocolos_evaluacion(cur, id_evaluacion)
        preguntas = mapa_preguntas(protocolos)
        cur.execute(
            """
            SELECT codigo_pregunta, respuesta_texto, opcion
            FROM EVALUACION_RESPUESTAS
            WHERE id_evaluacion = %s AND seccion = %s
            ORDER BY fecha_creacion
            """,
            (id_evaluacion, seccion),
        )
        respuestas = []
        for fila in cur.fetchall():
            pregunta = preguntas.get(fila["codigo_pregunta"], {})
            valor = " ".join(filter(None, (fila.get("opcion"), fila.get("respuesta_texto"))))
            respuestas.append({"pregunta": pregunta.get("titulo", "Pregunta operativa"), "respuesta": valor})
        resultado = analizar_seccion(
            id_evaluacion=id_evaluacion,
            correo_doctor=evaluacion["correo_doctor"],
            id_actor=str(session.get("id_usuario") or session.get("correo") or "admin"),
            seccion=seccion,
            respuestas=respuestas,
            nombres_conocidos=(
                evaluacion.get("nombre_doctor") or "",
                evaluacion.get("nombre_asistente") or "",
            ),
        )
        id_revision = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO EVALUACION_REVISIONES (
                id_revision, id_evaluacion, seccion, fuente, hallazgos
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (id_revision, id_evaluacion, seccion, resultado["fuente"], Json(resultado["hallazgos"])),
        )
        conn.commit()
        return jsonify({"ok": True, "id_revision": id_revision, **resultado})
    except Exception as exc:
        conn.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    finally:
        conn.close()


@implementacion_bp.route("/admin/doctores/implementacion/<id_evaluacion>/revision/<id_revision>", methods=["POST"])
@requiere_rol("admin")
def decidir_revision(id_evaluacion, id_revision):
    decision = str(_datos().get("decision") or "").strip().upper()
    if decision not in DECISIONES_REVISION:
        return jsonify({"ok": False, "error": "Decision no valida"}), 400
    conn = get_connection()
    if not conn:
        return jsonify({"ok": False, "error": "Base de datos no disponible"}), 503
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE EVALUACION_REVISIONES
            SET decision = %s, decidido_por = %s, decidido_en = NOW()
            WHERE id_revision = %s AND id_evaluacion = %s AND decision = 'PENDIENTE'
            """,
            (decision, session.get("correo", "admin"), id_revision, id_evaluacion),
        )
        if cur.rowcount != 1:
            return jsonify({"ok": False, "error": "Revision no encontrada o ya decidida"}), 409
        conn.commit()
        return jsonify({"ok": True})
    except Exception as exc:
        conn.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    finally:
        conn.close()


@implementacion_bp.route("/admin/doctores/implementacion/<id_evaluacion>/aprobar", methods=["POST"])
@requiere_rol("admin")
def aprobar_implementacion(id_evaluacion):
    datos = _datos()
    nombre = str(datos.get("aprobado_por_nombre") or "").strip()[:180]
    confirmado = datos.get("confirmacion") is True or str(datos.get("confirmacion") or "").lower() in {"1", "true", "on", "si"}
    if not nombre or not confirmado:
        return jsonify({"ok": False, "error": "Registra quien reviso y confirma su aprobacion"}), 400
    conn = get_connection()
    if not conn:
        return jsonify({"ok": False, "error": "Base de datos no disponible"}), 503
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        evaluacion = _buscar_evaluacion(cur, id_evaluacion, bloquear=True)
        if not evaluacion:
            return jsonify({"ok": False, "error": "Implementacion no encontrada"}), 404
        if evaluacion["estado"] == "CERRADA":
            return jsonify({"ok": False, "error": "La implementacion ya esta cerrada"}), 409
        cur.execute(
            """
            SELECT COUNT(*) FILTER (WHERE decision = 'ADAPTAR' AND NULLIF(TRIM(adaptacion_texto), '') IS NULL) AS adaptaciones_vacias,
                   COUNT(*) AS total
            FROM EVALUACION_PROTOCOLOS WHERE id_evaluacion = %s
            """,
            (id_evaluacion,),
        )
        validacion = cur.fetchone()
        if not validacion or not validacion["total"] or validacion["adaptaciones_vacias"]:
            return jsonify({"ok": False, "error": "Completa las adaptaciones antes de aprobar"}), 400
        cur.execute(
            """
            UPDATE EVALUACION_PROTOCOLOS
            SET estado_aprobacion = 'APROBADO', aprobado_por_nombre = %s,
                aprobado_en = NOW(), actualizado_en = NOW()
            WHERE id_evaluacion = %s
            """,
            (nombre, id_evaluacion),
        )
        cur.execute(
            """
            UPDATE EVALUACIONES_IMPLEMENTACION
            SET aprobacion_confirmada = TRUE, aprobado_por_nombre = %s,
                aprobado_en = NOW(), estado = 'PROTOCOLOS_APROBADOS',
                actualizado_en = NOW(), actualizado_por = %s
            WHERE id_evaluacion = %s
            """,
            (nombre, session.get("correo", "admin"), id_evaluacion),
        )
        _auditar(cur, "PROTOCOLOS_IMPLEMENTACION_APROBADOS", {
            "id_evaluacion": id_evaluacion,
            "correo_doctor": evaluacion["correo_doctor"],
            "aprobado_por_nombre": nombre,
        })
        conn.commit()
        return jsonify({"ok": True})
    except Exception as exc:
        conn.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    finally:
        conn.close()


@implementacion_bp.route("/admin/doctores/implementacion/<id_evaluacion>/cerrar", methods=["POST"])
@requiere_rol("admin")
def cerrar_implementacion(id_evaluacion):
    conn = get_connection()
    if not conn:
        return jsonify({"ok": False, "error": "Base de datos no disponible"}), 503
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        evaluacion = _buscar_evaluacion(cur, id_evaluacion, bloquear=True)
        if not evaluacion:
            return jsonify({"ok": False, "error": "Implementacion no encontrada"}), 404
        if evaluacion["estado"] == "CERRADA":
            return jsonify({"ok": True})
        if not evaluacion["aprobacion_confirmada"]:
            return jsonify({"ok": False, "error": "Los protocolos deben aprobarse antes de cerrar"}), 400
        cur.execute(
            """
            SELECT 1 FROM EVALUACION_RESPUESTAS
            WHERE id_evaluacion = %s AND codigo_pregunta = 'conclusion_implementacion'
              AND NULLIF(TRIM(respuesta_texto), '') IS NOT NULL
            """,
            (id_evaluacion,),
        )
        if not cur.fetchone():
            return jsonify({"ok": False, "error": "Completa la conclusion antes de cerrar"}), 400
        cur.execute(
            """
            UPDATE EVALUACIONES_IMPLEMENTACION
            SET estado = 'CERRADA', cerrado_en = NOW(), actualizado_en = NOW(),
                actualizado_por = %s
            WHERE id_evaluacion = %s
            """,
            (session.get("correo", "admin"), id_evaluacion),
        )
        _auditar(cur, "IMPLEMENTACION_CERRADA", {
            "id_evaluacion": id_evaluacion,
            "correo_doctor": evaluacion["correo_doctor"],
        })
        conn.commit()
        return jsonify({"ok": True})
    except Exception as exc:
        conn.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    finally:
        conn.close()
