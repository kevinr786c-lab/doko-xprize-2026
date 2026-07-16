ALTER TABLE DOCTORES
    ADD COLUMN IF NOT EXISTS modo_confirmacion TEXT NOT NULL DEFAULT 'manual';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'doctores_modo_confirmacion_check'
    ) THEN
        ALTER TABLE DOCTORES ADD CONSTRAINT doctores_modo_confirmacion_check
            CHECK (modo_confirmacion IN ('manual', 'confirmar_24h', 'confirmar_48h_cancelar_24h'));
    END IF;
END $$;

ALTER TABLE RADAR_EVENTOS_CITAS
    ADD COLUMN IF NOT EXISTS confirmacion_enviada_en TIMESTAMP,
    ADD COLUMN IF NOT EXISTS confirmacion_error_en TIMESTAMP,
    ADD COLUMN IF NOT EXISTS confirmacion_error_motivo TEXT,
    ADD COLUMN IF NOT EXISTS recordatorio_manana_enviado_en TIMESTAMP,
    ADD COLUMN IF NOT EXISTS recordatorio_tarde_enviado_en TIMESTAMP,
    ADD COLUMN IF NOT EXISTS cancelacion_automatica_en TIMESTAMP,
    ADD COLUMN IF NOT EXISTS motivo_cancelacion TEXT;
