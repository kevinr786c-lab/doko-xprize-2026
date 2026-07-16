-- Comprobante informativo para citas cercanas creadas directamente en Doko.
-- Se mantiene separado del token y del flujo de confirmacion 24/48 horas.

ALTER TABLE RADAR_EVENTOS_CITAS
    ADD COLUMN IF NOT EXISTS requiere_confirmacion_enlace BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS correo_registro_enviado_en TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS correo_registro_error_en TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS correo_registro_error_motivo TEXT NULL;

COMMENT ON COLUMN RADAR_EVENTOS_CITAS.requiere_confirmacion_enlace IS
    'FALSE para citas acordadas directamente que solo reciben comprobante informativo.';
COMMENT ON COLUMN RADAR_EVENTOS_CITAS.correo_registro_enviado_en IS
    'Fecha del comprobante informativo; no equivale a confirmacion_enviada_en.';
