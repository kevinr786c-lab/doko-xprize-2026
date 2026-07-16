-- Clasificacion operativa de agenda para citas manuales, bloqueos y apartados.
-- No separa tablas: conserva RADAR_EVENTOS_CITAS como la fuente operativa.

ALTER TABLE RADAR_EVENTOS_CITAS
    ADD COLUMN IF NOT EXISTS tipo_evento TEXT NOT NULL DEFAULT 'CITA_PACIENTE',
    ADD COLUMN IF NOT EXISTS origen_evento TEXT NOT NULL DEFAULT 'google_calendar',
    ADD COLUMN IF NOT EXISTS creado_por_usuario_id UUID NULL,
    ADD COLUMN IF NOT EXISTS notas_internas TEXT NULL,
    ADD COLUMN IF NOT EXISTS telefono_manual TEXT NULL,
    ADD COLUMN IF NOT EXISTS correo_manual TEXT NULL,
    ADD COLUMN IF NOT EXISTS servicio_id UUID NULL,
    ADD COLUMN IF NOT EXISTS expiracion_apartado TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS liberado_en TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS motivo_liberacion TEXT NULL,
    ADD COLUMN IF NOT EXISTS estado_operativo TEXT NOT NULL DEFAULT 'activo';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'radar_tipo_evento_check'
    ) THEN
        ALTER TABLE RADAR_EVENTOS_CITAS ADD CONSTRAINT radar_tipo_evento_check
            CHECK (tipo_evento IN ('CITA_PACIENTE', 'BLOQUEO_HORARIO', 'APARTADO_TEMPORAL', 'EVENTO_INTERNO'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'radar_origen_evento_check'
    ) THEN
        ALTER TABLE RADAR_EVENTOS_CITAS ADD CONSTRAINT radar_origen_evento_check
            CHECK (origen_evento IN ('google_calendar', 'doko', 'doko_asistente', 'google_externo'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'radar_estado_operativo_check'
    ) THEN
        ALTER TABLE RADAR_EVENTOS_CITAS ADD CONSTRAINT radar_estado_operativo_check
            CHECK (estado_operativo IN ('activo', 'liberado', 'convertido_a_cita', 'cancelado'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_radar_eventos_tipo_estado
    ON RADAR_EVENTOS_CITAS (correo_doctor, tipo_evento, estado_operativo, fecha_cita);

CREATE INDEX IF NOT EXISTS idx_radar_eventos_google_doko
    ON RADAR_EVENTOS_CITAS (correo_doctor, google_event_id);
