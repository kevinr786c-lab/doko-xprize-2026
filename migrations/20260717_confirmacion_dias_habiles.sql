BEGIN;

ALTER TABLE DOCTORES
    ADD COLUMN IF NOT EXISTS confirmacion_dias_habiles BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN DOCTORES.confirmacion_dias_habiles IS
    'Si esta activo, el ciclo 48h/24h envia y libera solo en dias habiles de lunes a viernes.';

COMMIT;
