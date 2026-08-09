BEGIN;

ALTER TABLE RECETA_CONFIGURACION
    ADD COLUMN IF NOT EXISTS nombre_profesional TEXT,
    ADD COLUMN IF NOT EXISTS especialidad_profesional TEXT,
    ADD COLUMN IF NOT EXISTS institucion_titulo_privada TEXT,
    ADD COLUMN IF NOT EXISTS cedula_profesional_privada TEXT,
    ADD COLUMN IF NOT EXISTS cedula_especialidad_privada TEXT,
    ADD COLUMN IF NOT EXISTS rfc_privado TEXT,
    ADD COLUMN IF NOT EXISTS perfil_profesional_confirmado_en TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS perfil_profesional_confirmado_por TEXT;

COMMIT;
