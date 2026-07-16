ALTER TABLE CAT_SERVICIOS_CONSULTORIO
    ADD COLUMN IF NOT EXISTS tipo_precio TEXT NOT NULL DEFAULT 'precio_fijo';

ALTER TABLE CAT_SERVICIOS_CONSULTORIO
    ALTER COLUMN precio DROP NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'servicios_tipo_precio_check') THEN
        ALTER TABLE CAT_SERVICIOS_CONSULTORIO ADD CONSTRAINT servicios_tipo_precio_check
            CHECK (tipo_precio IN ('precio_fijo', 'segun_valoracion', 'costo_durante_consulta'));
    END IF;
END $$;

UPDATE CAT_SERVICIOS_CONSULTORIO SET tipo_precio = 'precio_fijo' WHERE tipo_precio IS NULL;
