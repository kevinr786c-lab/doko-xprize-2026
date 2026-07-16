-- Asistentes de consultorio: un usuario interno puede operar una o mas doctoras.
CREATE TABLE IF NOT EXISTS ASISTENTES_DOCTORES (
    id_usuario UUID NOT NULL REFERENCES USUARIOS_INTERNOS(id_usuario) ON DELETE CASCADE,
    correo_doctor TEXT NOT NULL REFERENCES DOCTORES(correo_doctor) ON DELETE CASCADE,
    fecha_asignacion TIMESTAMP NOT NULL DEFAULT NOW(),
    asignado_por TEXT,
    PRIMARY KEY (id_usuario, correo_doctor)
);

CREATE INDEX IF NOT EXISTS idx_asistentes_doctores_doctor
    ON ASISTENTES_DOCTORES(correo_doctor);
