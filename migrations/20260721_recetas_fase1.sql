BEGIN;

CREATE TABLE IF NOT EXISTS RECETA_CONFIGURACION (
    correo_doctor TEXT PRIMARY KEY REFERENCES DOCTORES(correo_doctor) ON DELETE CASCADE,
    habilitada BOOLEAN NOT NULL DEFAULT FALSE,
    modo_prueba BOOLEAN NOT NULL DEFAULT TRUE,
    nombre_consultorio TEXT,
    telefono_consultorio TEXT,
    telefono_emergencias TEXT,
    correo_publico TEXT,
    direccion_publica TEXT,
    datos_publicos TEXT,
    logo_url TEXT,
    emblema_1_url TEXT,
    emblema_1_nombre TEXT,
    emblema_1_autorizado BOOLEAN NOT NULL DEFAULT FALSE,
    emblema_2_url TEXT,
    emblema_2_nombre TEXT,
    emblema_2_autorizado BOOLEAN NOT NULL DEFAULT FALSE,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_por TEXT,
    CONSTRAINT receta_emblema_1_autorizado_check CHECK (
        emblema_1_url IS NULL OR emblema_1_autorizado = TRUE
    ),
    CONSTRAINT receta_emblema_2_autorizado_check CHECK (
        emblema_2_url IS NULL OR emblema_2_autorizado = TRUE
    )
);

CREATE INDEX IF NOT EXISTS idx_receta_configuracion_habilitada
    ON RECETA_CONFIGURACION (habilitada)
    WHERE habilitada = TRUE;

COMMIT;
