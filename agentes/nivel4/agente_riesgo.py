class AgenteRiesgo:
    """Evalua riesgos operativos sin modificar inventario ni pedidos."""

    def generar_micro_reporte(self, cur) -> str:
        alertas = []

        cur.execute("""
            SELECT COUNT(*) AS cantidad FROM (
                SELECT id_producto, SUM(cantidad_piezas_actual) AS total
                FROM INVENTARIO_LOTES
                WHERE activo = TRUE
                  AND cantidad_piezas_actual > 0
                  AND fecha_caducidad >= CURRENT_DATE
                GROUP BY id_producto
                HAVING SUM(cantidad_piezas_actual) <= 5
            ) AS criticos
        """)
        stock_bajo = cur.fetchone()['cantidad'] or 0
        if stock_bajo:
            alertas.append(f'{stock_bajo} productos con bajo stock')

        cur.execute("""
            SELECT COUNT(*) AS cantidad
            FROM VENTAS_PEDIDOS_ELITE
            WHERE estatus_entrega IN ('PENDIENTE', 'nuevo')
              AND fecha_pedido < NOW() - INTERVAL '2 hours'
        """)
        pedidos_pendientes = cur.fetchone()['cantidad'] or 0
        if pedidos_pendientes:
            alertas.append(f'{pedidos_pendientes} pedidos nuevos con mas de 2 horas')

        cur.execute("""
            SELECT COUNT(*) AS cantidad
            FROM INVENTARIO_LOTES
            WHERE fecha_caducidad < CURRENT_DATE
              AND cantidad_piezas_actual > 0
              AND activo = TRUE
        """)
        lotes_vencidos = cur.fetchone()['cantidad'] or 0
        if lotes_vencidos:
            alertas.append(f'{lotes_vencidos} lotes vencidos con stock')

        if alertas:
            return 'ATENCION: ' + ', '.join(alertas) + '.'
        return 'OK: sin alertas operativas de inventario o pedidos.'
