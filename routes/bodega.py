import json
import uuid
from flask import Blueprint, render_template, request, jsonify, session
from psycopg2.extras import RealDictCursor

from helpers.db import get_connection
from helpers.decorators import requiere_rol
from helpers.storage import subir_archivo, extension_permitida
bodega_bp = Blueprint("bodega_bp", __name__)


def _sql_id(value):
    return str(value) if isinstance(value, uuid.UUID) else value


@bodega_bp.route("/bodega/inventario", methods=["GET"])
@requiere_rol("bodeguero")
def inventario():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT l.*, p.nombre_comercial,
                   (l.fecha_caducidad <= CURRENT_DATE + INTERVAL '30 days') AS alerta_caducidad
            FROM INVENTARIO_LOTES l
            JOIN CAT_PRODUCTOS_MAESTRO p ON l.id_producto = p.id_producto
            WHERE l.activo = TRUE AND l.cantidad_piezas_actual > 0
            ORDER BY l.fecha_caducidad ASC NULLS LAST
        """)
        return render_template("bodega/inventario.html", lotes=cur.fetchall())
    finally:
        conn.close()


@bodega_bp.route("/bodega/movimientos", methods=["GET"])
@requiere_rol("bodeguero")
def movimientos():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT m.*, p.nombre_comercial, l.lote_proveedor
            FROM MOVIMIENTOS_INVENTARIO m
            LEFT JOIN INVENTARIO_LOTES l ON m.id_lote = l.id_lote
            LEFT JOIN CAT_PRODUCTOS_MAESTRO p ON l.id_producto = p.id_producto
            ORDER BY m.fecha_movimiento DESC NULLS LAST
            LIMIT 200
        """)
        return render_template("bodega/movimientos.html", movimientos=cur.fetchall())
    finally:
        conn.close()


@bodega_bp.route("/bodega/pedidos", methods=["GET"])
@requiere_rol("bodeguero")
def pedidos():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT v.*, d.nombre_doctor, d.direccion_consultorio
            FROM VENTAS_PEDIDOS_ELITE v
            JOIN DOCTORES d ON v.correo_doctor = d.correo_doctor
            WHERE v.estatus_entrega IN (
                'PENDIENTE',
                'nuevo',
                'preparando'
            )
            ORDER BY v.fecha_pedido ASC
        """)
        pedidos_lista = cur.fetchall()

        for p in pedidos_lista:
            cur.execute("""
                SELECT
                    dvl.id_detalle,
                    dvl.id_producto,
                    dvl.id_lote,
                    dvl.cantidad,
                    dvl.precio_unitario,
                    prod.nombre_comercial
                FROM DETALLE_VENTA_LOTES dvl
                JOIN CAT_PRODUCTOS_MAESTRO prod ON dvl.id_producto = prod.id_producto
                WHERE dvl.id_pedido = %s
                ORDER BY prod.nombre_comercial ASC
            """, (_sql_id(p["id_pedido"]),))
            detalles = cur.fetchall()

            for det in detalles:
                cur.execute("""
                    SELECT id_lote, lote_proveedor, fecha_caducidad, cantidad_piezas_actual
                    FROM INVENTARIO_LOTES
                    WHERE id_producto = %s
                        AND activo = TRUE
                        AND cantidad_piezas_actual > 0
                        AND fecha_caducidad >= CURRENT_DATE
                    ORDER BY fecha_caducidad ASC NULLS LAST
                """, (_sql_id(det["id_producto"]),))
                restante = int(det["cantidad"])
                lotes_sugeridos = []
                for lote in cur.fetchall():
                    cantidad_asignada = min(restante, int(lote["cantidad_piezas_actual"]))
                    if cantidad_asignada <= 0:
                        continue
                    lote["cantidad_asignada"] = cantidad_asignada
                    lotes_sugeridos.append(lote)
                    restante -= cantidad_asignada
                    if restante == 0:
                        break
                det["lotes_sugeridos"] = lotes_sugeridos
                det["stock_insuficiente"] = restante > 0

            p["detalles"] = detalles

        return render_template("bodega/pedidos.html", pedidos=pedidos_lista)
    finally:
        conn.close()
@bodega_bp.route("/bodega/pedidos/<uuid:id_pedido>/foto", methods=["POST"])
@requiere_rol("bodeguero")
def subir_foto_pedido(id_pedido):
    id_pedido_sql = _sql_id(id_pedido)
    if "foto" not in request.files:
        return jsonify({"error": "no_file"}), 400
    file = request.files["foto"]
    if not file.filename or not extension_permitida(file.filename):
        return jsonify({"error": "formato_invalido"}), 400

    conn = get_connection()
    try:
        url_gcs = subir_archivo(file.read(), file.filename, "documentos/surtido")
        cur = conn.cursor()
        cur.execute(
            "UPDATE VENTAS_PEDIDOS_ELITE SET evidencia_surtido_url = %s WHERE id_pedido = %s",
            (url_gcs, id_pedido_sql)
        )
        conn.commit()
        return jsonify({"ok": True, "url": url_gcs})
    finally:
        conn.close()


@bodega_bp.route("/bodega/pedidos/<uuid:id_pedido>/preparado", methods=["POST"])
@requiere_rol("bodeguero")
def marcar_preparado(id_pedido):
    id_pedido_sql = _sql_id(id_pedido)
    data = request.json or {}
    lotes_reportados = data.get("lotes_reportados") or {}
    id_lote_reportado_global = data.get("id_lote_reportado")

    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id_pedido, estatus_entrega, evidencia_surtido_url
            FROM VENTAS_PEDIDOS_ELITE
            WHERE id_pedido = %s
            FOR UPDATE
        """, (id_pedido_sql,))
        pedido = cur.fetchone()
        if not pedido:
            return jsonify({"ok": False, "error": "pedido_no_encontrado"}), 404

        if pedido["estatus_entrega"] not in ("PENDIENTE", "nuevo"):
            return jsonify({"ok": False, "error": "pedido_ya_preparado_o_en_ruta"}), 400

        cur.execute("""
            SELECT id_detalle, id_producto, cantidad, precio_unitario
            FROM DETALLE_VENTA_LOTES
            WHERE id_pedido = %s
            ORDER BY id_detalle ASC
        """, (id_pedido_sql,))
        detalles = cur.fetchall()
        if not detalles:
            return jsonify({"ok": False, "error": "pedido_sin_detalle"}), 400

        surtido = []
        discrepancias = []
        evidencia = pedido.get("evidencia_surtido_url")

        for det in detalles:
            cur.execute("""
                SELECT id_lote, lote_proveedor, cantidad_piezas_actual, fecha_caducidad
                FROM INVENTARIO_LOTES
                WHERE id_producto = %s
                    AND activo = TRUE
                    AND cantidad_piezas_actual > 0
                    AND fecha_caducidad >= CURRENT_DATE
                ORDER BY fecha_caducidad ASC NULLS LAST
                FOR UPDATE
            """, (_sql_id(det["id_producto"]),))
            lotes_disponibles = cur.fetchall()
            restante = int(det["cantidad"])
            if sum(int(lote["cantidad_piezas_actual"]) for lote in lotes_disponibles) < restante:
                raise Exception("Stock insuficiente para surtir uno de los productos")

            id_lote_reportado = lotes_reportados.get(str(det["id_detalle"])) or id_lote_reportado_global
            primera_asignacion = True
            for lote_correcto in lotes_disponibles:
                cantidad_surtida = min(restante, int(lote_correcto["cantidad_piezas_actual"]))
                if cantidad_surtida <= 0:
                    continue
                lote_reportado = id_lote_reportado if primera_asignacion else None
                discrepancia = bool(lote_reportado and str(lote_reportado) != str(lote_correcto["id_lote"]))
                detalle_log = "FEFO correcto" if not discrepancia else "Lote reportado no coincide con FEFO"

                cur.execute("""
                    INSERT INTO LOGS_FIFO
                        (id_pedido, id_lote_correcto, id_lote_reportado, discrepancia, detalle, evidencia_url)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    id_pedido_sql,
                    _sql_id(lote_correcto["id_lote"]),
                    lote_reportado or None,
                    discrepancia,
                    detalle_log,
                    evidencia,
                ))

                if discrepancia:
                    discrepancias.append(detalle_log)

                surtido.append({
                    "id_detalle": det["id_detalle"],
                    "id_producto": det["id_producto"],
                    "id_lote": _sql_id(lote_correcto["id_lote"]),
                    "cantidad": cantidad_surtida,
                    "precio_unitario": det["precio_unitario"],
                    "es_primer_lote": primera_asignacion,
                })
                restante -= cantidad_surtida
                primera_asignacion = False
                if restante == 0:
                    break

        if discrepancias:
            conn.commit()
            return jsonify({
                "ok": False,
                "discrepancia": True,
                "detalle": "Hay discrepancia FEFO. Revise el lote reportado antes de surtir.",
            }), 400

        for mov in surtido:
            if mov["es_primer_lote"]:
                cur.execute("""
                    UPDATE DETALLE_VENTA_LOTES
                    SET id_lote = %s, cantidad = %s
                    WHERE id_detalle = %s
                """, (mov["id_lote"], mov["cantidad"], _sql_id(mov["id_detalle"])))
            else:
                cur.execute("""
                    INSERT INTO DETALLE_VENTA_LOTES
                        (id_detalle, id_pedido, id_producto, id_lote, cantidad, precio_unitario)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    str(uuid.uuid4()),
                    id_pedido_sql,
                    _sql_id(mov["id_producto"]),
                    mov["id_lote"],
                    mov["cantidad"],
                    mov["precio_unitario"],
                ))

            cur.execute("""
            UPDATE INVENTARIO_LOTES
            SET cantidad_piezas_actual = cantidad_piezas_actual - %s
            WHERE id_lote = %s
              AND cantidad_piezas_actual >= %s
        """, (mov["cantidad"], mov["id_lote"], mov["cantidad"]))
            if cur.rowcount != 1:
                raise Exception("El inventario cambió durante el surtido. Intente de nuevo.")

            cur.execute("""
                INSERT INTO MOVIMIENTOS_INVENTARIO
                    (id_lote, tipo_movimiento, cantidad, referencia_doc, detalle, fecha_movimiento)
                VALUES (%s, 'VENTA', %s, %s, %s, NOW())
            """, (
                mov["id_lote"],
                mov["cantidad"],
                id_pedido_sql,
                "Surtido de pedido",
            ))

        cur.execute(
            "UPDATE VENTAS_PEDIDOS_ELITE SET estatus_entrega = 'preparando' WHERE id_pedido = %s",
            (id_pedido_sql,)
        )
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle, ip_origen)
            VALUES ('PEDIDO_PREPARADO', %s, %s, %s, %s)
        """, (
            session.get("correo"),
            session.get("rol", "bodeguero"),
            json.dumps({"id_pedido": id_pedido_sql}),
            request.remote_addr,
        ))
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        conn.close()
@bodega_bp.route("/bodega/entrada", methods=["POST"])
@requiere_rol("bodeguero")
def entrada_inventario():
    data = request.json or {}
    tipo = data.get("tipo", "ENTRADA_COMPRA")

    if tipo == "ENTRADA_COMPRA":
        if not data.get("id_factura") or data.get("precio_compra") is None:
            return jsonify({"error": "datos_requeridos_compra"}), 400

    cantidad = int(data.get("cantidad_piezas", 0))
    if cantidad <= 0:
        return jsonify({"error": "cantidad_invalida"}), 400

    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        id_lote = str(uuid.uuid4())
        precio_compra = data.get("precio_compra")

        cur.execute("""
            INSERT INTO INVENTARIO_LOTES
            (id_lote, id_producto, lote_proveedor, cantidad_piezas_actual,
             fecha_caducidad, precio_compra, activo)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
        """, (id_lote, data["id_producto"], data["lote_proveedor"], cantidad,
              data.get("fecha_caducidad"), precio_compra))

        referencia = None
        if tipo == "ENTRADA_COMPRA":
            cur.execute("SELECT folio_factura FROM FACTURAS_COMPRA WHERE id_factura = %s", (data["id_factura"],))
            factura = cur.fetchone()
            referencia = factura["folio_factura"] if factura else str(data["id_factura"])

        cur.execute("""
            INSERT INTO MOVIMIENTOS_INVENTARIO
            (id_lote, tipo_movimiento, cantidad, referencia_doc, fecha_movimiento)
            VALUES (%s, %s, %s, %s, NOW())
        """, (id_lote, tipo, cantidad, referencia))

        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle)
            VALUES ('ENTRADA_INVENTARIO', %s, 'bodeguero', %s)
        """, (session.get("correo"), json.dumps({"id_lote": str(id_lote), "tipo": tipo})))

        conn.commit()
        return jsonify({"ok": True, "id_lote": str(id_lote)})
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        conn.close()


@bodega_bp.route("/bodega/ajuste", methods=["POST"])
@requiere_rol("bodeguero")
def ajuste_inventario():
    data = request.json or {}
    if not data.get("detalle_ajuste"):
        return jsonify({"error": "detalle_requerido"}), 400

    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT cantidad_piezas_actual FROM INVENTARIO_LOTES WHERE id_lote = %s FOR UPDATE", (data["id_lote"],))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "lote_no_encontrado"}), 404

        actual = int(row["cantidad_piezas_actual"])
        nueva = int(data["cantidad_nueva"])
        if nueva < 0:
            return jsonify({"error": "cantidad_invalida"}), 400
        diferencia = nueva - actual

        cur.execute("UPDATE INVENTARIO_LOTES SET cantidad_piezas_actual = %s WHERE id_lote = %s", (nueva, data["id_lote"]))
        cur.execute("""
            INSERT INTO MOVIMIENTOS_INVENTARIO
            (id_lote, tipo_movimiento, cantidad, detalle, fecha_movimiento)
            VALUES (%s, 'AJUSTE', %s, %s, NOW())
        """, (data["id_lote"], diferencia, data["detalle_ajuste"]))
        cur.execute("""
            INSERT INTO AUDITORIA_SEGURIDAD (tipo_evento, actor, rol_actor, detalle)
            VALUES ('AJUSTE_INVENTARIO', %s, 'bodeguero', %s)
        """, (session.get("correo"), json.dumps({"id_lote": str(data["id_lote"])})))
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()
