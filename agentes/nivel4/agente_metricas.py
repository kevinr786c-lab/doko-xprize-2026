class AgenteMetricas:
    """Resumen cuantitativo; sólo lee datos reales de la operación."""

    def generar_contexto_ia(self, cur) -> str:
        """Contexto propio de Doko que puede resumirse con IA.

        No incluye datos brutos, agregados ni derivados de Google Workspace.
        """
        cur.execute("""
            SELECT
                COALESCE(SUM(total_pedido) FILTER (WHERE DATE(fecha_pedido) = CURRENT_DATE), 0) AS valor_hoy,
                COUNT(*) FILTER (WHERE estatus_entrega IN ('PENDIENTE', 'nuevo')) AS pedidos_nuevos,
                COUNT(*) FILTER (WHERE estatus_entrega = 'preparando') AS pedidos_preparando,
                COUNT(*) FILTER (WHERE estatus_entrega = 'en_camino') AS pedidos_en_camino
            FROM VENTAS_PEDIDOS_ELITE
        """)
        pedidos = cur.fetchone()

        cur.execute('SELECT COUNT(*) AS total FROM DOCTORES WHERE activo = TRUE')
        doctores = cur.fetchone()['total']

        return (
            f"Doctores activos en Doko: {doctores}. "
            f"Pedidos nuevos: {pedidos['pedidos_nuevos'] or 0}; "
            f"preparando: {pedidos['pedidos_preparando'] or 0}; "
            f"en camino: {pedidos['pedidos_en_camino'] or 0}. "
            f"Valor de pedidos hoy: ${float(pedidos['valor_hoy'] or 0):,.2f}."
        )

    def generar_micro_reporte(self, cur) -> str:
        cur.execute("""
            SELECT
                COALESCE(SUM(total_pedido) FILTER (WHERE DATE(fecha_pedido) = CURRENT_DATE), 0) AS valor_hoy,
                COUNT(*) FILTER (WHERE estatus_entrega IN ('PENDIENTE', 'nuevo')) AS pedidos_nuevos,
                COUNT(*) FILTER (WHERE estatus_entrega = 'preparando') AS pedidos_preparando,
                COUNT(*) FILTER (WHERE estatus_entrega = 'en_camino') AS pedidos_en_camino
            FROM VENTAS_PEDIDOS_ELITE
        """)
        pedidos = cur.fetchone()

        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE fecha_cita >= NOW() AND fecha_cita < NOW() + INTERVAL '7 days') AS proximas,
                COUNT(*) FILTER (
                    WHERE fecha_cita >= NOW() AND fecha_cita < NOW() + INTERVAL '7 days'
                      AND UPPER(COALESCE(estatus_confirmacion, '')) = 'PENDIENTE'
                ) AS pendientes,
                COUNT(*) FILTER (
                    WHERE fecha_cita >= NOW() AND fecha_cita < NOW() + INTERVAL '7 days'
                      AND UPPER(COALESCE(estatus_confirmacion, '')) LIKE 'CONFIRM%%'
                ) AS confirmadas
            FROM RADAR_EVENTOS_CITAS
        """)
        citas = cur.fetchone()

        cur.execute('SELECT COUNT(*) AS total FROM DOCTORES WHERE activo = TRUE')
        doctores = cur.fetchone()['total']

        return (
            f"Doctores activos: {doctores}. "
            f"Citas próximas 7 días: {citas['proximas'] or 0}; "
            f"pendientes: {citas['pendientes'] or 0}; confirmadas: {citas['confirmadas'] or 0}. "
            f"Pedidos nuevos: {pedidos['pedidos_nuevos'] or 0}; preparando: {pedidos['pedidos_preparando'] or 0}; "
            f"en camino: {pedidos['pedidos_en_camino'] or 0}. "
            f"Valor de pedidos hoy: ${float(pedidos['valor_hoy'] or 0):,.2f}."
        )
