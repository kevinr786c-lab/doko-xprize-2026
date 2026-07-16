-- Doko: índices de lectura para 10 -> 100 médicos.
-- Ejecutar una vez en Cloud SQL como usuario con permisos DDL.
-- No crea tablas ni columnas y es seguro volver a ejecutarlo.

CREATE INDEX IF NOT EXISTS idx_radar_doctor_fecha
    ON RADAR_EVENTOS_CITAS (correo_doctor, fecha_cita);

CREATE INDEX IF NOT EXISTS idx_radar_doctor_google_evento
    ON RADAR_EVENTOS_CITAS (correo_doctor, google_event_id);

CREATE INDEX IF NOT EXISTS idx_radar_estado_fecha
    ON RADAR_EVENTOS_CITAS (estatus_confirmacion, fecha_cita);

CREATE INDEX IF NOT EXISTS idx_pedidos_doctor_fecha
    ON VENTAS_PEDIDOS_ELITE (correo_doctor, fecha_pedido DESC);

CREATE INDEX IF NOT EXISTS idx_pedidos_estado_fecha
    ON VENTAS_PEDIDOS_ELITE (estatus_entrega, fecha_pedido);

CREATE INDEX IF NOT EXISTS idx_pedidos_repartidor_estado
    ON VENTAS_PEDIDOS_ELITE (id_repartidor, estatus_entrega);

CREATE INDEX IF NOT EXISTS idx_detalle_pedido
    ON DETALLE_VENTA_LOTES (id_pedido);

CREATE INDEX IF NOT EXISTS idx_inventario_producto_fefo
    ON INVENTARIO_LOTES (id_producto, fecha_caducidad)
    WHERE activo = TRUE AND cantidad_piezas_actual > 0;

CREATE INDEX IF NOT EXISTS idx_movimientos_lote_fecha
    ON MOVIMIENTOS_INVENTARIO (id_lote, fecha_movimiento DESC);

CREATE INDEX IF NOT EXISTS idx_auditoria_evento_actor_fecha
    ON AUDITORIA_SEGURIDAD (tipo_evento, actor, fecha_evento DESC);

-- Antes de convertirlo en UNIQUE, revisar y resolver cualquier duplicado
-- histórico con la misma pareja (correo_doctor, google_event_id). Mientras
-- tanto, AuditorCalendar usa bloqueo advisory por doctor para evitar nuevos.
