-- Métodos de pago configurables por consultorio.
-- Ejecutar una vez en Cloud SQL antes de desplegar la versión que lo usa.
ALTER TABLE DOCTORES
    ADD COLUMN IF NOT EXISTS metodos_pago_aceptados TEXT;
