import json
import uuid
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, session
from psycopg2.extras import RealDictCursor

from helpers.db import get_connection
from helpers.decorators import requiere_rol
from helpers.storage import subir_archivo, extension_permitida

reparto_bp = Blueprint("reparto_bp", __name__)


def _sql_id(value):
    return str(value) if isinstance(value, uuid.UUID) else value


@reparto_bp.route("/reparto/mis_pedidos", methods=["GET"])
@requiere_rol("repartidor")
def mis_pedidos():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        user_id = session["id_usuario"]
        es_admin = session.get("rol") == "admin"

        orden_ids = None
        if not es_admin:
            cur.execute("""
                SELECT ruta_json FROM LOGS_REPARTO
                WHERE id_repartidor = %s AND aprobada_por_admin = TRUE
                ORDER BY fecha_calculo DESC LIMIT 1
            """, (user_id,))
            ruta = cur.fetchone()
            orden_ids = json.loads(ruta["ruta_json"]) if ruta and ruta.get("ruta_json") else None

        if es_admin:
            cur.execute("""
                SELECT p.*, d.nombre_doctor, d.maps_url, d.direccion_consultorio
                FROM VENTAS_PEDIDOS_ELITE p
                JOIN DOCTORES d ON p.correo_doctor = d.correo_doctor
                WHERE p.estatus_entrega = 'en_camino'
                ORDER BY p.fecha_pedido ASC
            """)
        else:
            cur.execute("""
                SELECT p.*, d.nombre_doctor, d.maps_url, d.direccion_consultorio
                FROM VENTAS_PEDIDOS_ELITE p
                JOIN DOCTORES d ON p.correo_doctor = d.correo_doctor
                WHERE p.id_repartidor = %s
                    AND p.estatus_entrega = 'en_camino'
                ORDER BY p.fecha_pedido ASC
            """, (user_id,))
        pedidos = cur.fetchall()

        for pedido in pedidos:
            cur.execute("""
                SELECT prod.nombre_comercial, dvl.cantidad
                FROM DETALLE_VENTA_LOTES dvl
                JOIN CAT_PRODUCTOS_MAESTRO prod ON dvl.id_producto = prod.id_producto
                WHERE dvl.id_pedido = %s
                ORDER BY prod.nombre_comercial ASC
            """, (_sql_id(pedido["id_pedido"]),))
            pedido["productos"] = cur.fetchall()

        if orden_ids:
            pedidos_dict = {str(p["id_pedido"]): p for p in pedidos}
            pedidos_ordenados = [pedidos_dict[pid] for pid in orden_ids if pid in pedidos_dict]
            pedidos_en_ruta = {str(p["id_pedido"]) for p in pedidos_ordenados}
            # Una ruta previa no puede ocultar pedidos que se asignaron después.
            pedidos_ordenados.extend(
                p for p in pedidos if str(p["id_pedido"]) not in pedidos_en_ruta
            )
        else:
            pedidos_ordenados = sorted(pedidos, key=lambda x: x["fecha_pedido"])

        return render_template("reparto/mis_pedidos.html", pedidos=pedidos_ordenados, es_admin=es_admin)
    finally:
        conn.close()
@reparto_bp.route("/reparto/pedido/<uuid:id_pedido>/foto", methods=["POST"])
@requiere_rol("repartidor")
def subir_foto_entrega(id_pedido):
    id_pedido_sql = _sql_id(id_pedido)
    es_admin = session.get("rol") == "admin"
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id_repartidor FROM VENTAS_PEDIDOS_ELITE WHERE id_pedido = %s", (id_pedido_sql,))
        pedido = cur.fetchone()
        if not pedido or (not es_admin and str(pedido["id_repartidor"]) != str(session["id_usuario"])):
            return jsonify({"error": "no_autorizado"}), 403

        if "foto" not in request.files or not extension_permitida(request.files["foto"].filename):
            return jsonify({"error": "archivo_invalido"}), 400

        file = request.files["foto"]
        url_gcs = subir_archivo(file.read(), file.filename, "documentos/entregas")
        cur.execute(
            "UPDATE VENTAS_PEDIDOS_ELITE SET evidencia_entrega_url = %s WHERE id_pedido = %s",
            (url_gcs, id_pedido_sql)
        )
        conn.commit()
        return jsonify({"ok": True, "url": url_gcs})
    finally:
        conn.close()


@reparto_bp.route("/reparto/pedido/<uuid:id_pedido>/entregado", methods=["POST"])
@requiere_rol("repartidor")
def confirmar_entrega(id_pedido):
    id_pedido_sql = _sql_id(id_pedido)
    es_admin = session.get("rol") == "admin"
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT id_repartidor, estatus_entrega FROM VENTAS_PEDIDOS_ELITE WHERE id_pedido = %s",
            (id_pedido_sql,)
        )
        pedido = cur.fetchone()

        if not pedido or (not es_admin and str(pedido["id_repartidor"]) != str(session["id_usuario"])):
            return jsonify({"error": "no_autorizado"}), 403
        if pedido["estatus_entrega"] != "en_camino":
            return jsonify({"error": "estatus_invalido"}), 400

        cur.execute("""
            UPDATE VENTAS_PEDIDOS_ELITE
            SET estatus_entrega = 'entregado', hora_entrega = NOW()
            WHERE id_pedido = %s
        """, (id_pedido_sql,))

        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle)
            VALUES (
                'ENTREGA_CONFIRMADA',
                %s,
                %s,
                %s
            )
        """, (
            session["id_usuario"],
            session.get("rol", "repartidor"),
            json.dumps({"id_pedido": id_pedido_sql, "hora": datetime.now().isoformat(), "operado_por_admin": es_admin}),
        ))

        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        conn.close()
