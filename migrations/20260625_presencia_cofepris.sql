-- Campos de cumplimiento editorial COFEPRIS para paginas medicas de presencia digital.
ALTER TABLE SITIOS_MEDICOS
    ADD COLUMN IF NOT EXISTS cedula_profesional TEXT,
    ADD COLUMN IF NOT EXISTS cedula_especialidad TEXT,
    ADD COLUMN IF NOT EXISTS institucion_titulo TEXT,
    ADD COLUMN IF NOT EXISTS aviso_publicidad_cofepris TEXT;
