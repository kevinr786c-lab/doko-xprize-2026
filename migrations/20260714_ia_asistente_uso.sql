-- Telemetria y cuotas del asistente operativo del panel.
-- No almacena preguntas, respuestas, pacientes, citas ni datos de Workspace.

CREATE TABLE IF NOT EXISTS IA_ASISTENTE_USO (
    id_uso UUID PRIMARY KEY,
    fecha_evento TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    correo_doctor TEXT NOT NULL,
    actor_hash TEXT NOT NULL,
    actor_rol TEXT NOT NULL,
    fuente TEXT NOT NULL,
    categoria TEXT NULL,
    estado TEXT NOT NULL,
    motivo_limite TEXT NULL,
    modelo TEXT NULL,
    tokens_entrada INTEGER NOT NULL DEFAULT 0,
    tokens_salida INTEGER NOT NULL DEFAULT 0,
    tokens_razonamiento INTEGER NOT NULL DEFAULT 0,
    tokens_total INTEGER NOT NULL DEFAULT 0,
    costo_estimado_usd NUMERIC(14, 8) NOT NULL DEFAULT 0,
    duracion_ms INTEGER NULL,
    CONSTRAINT ia_asistente_uso_actor_rol_check
        CHECK (actor_rol IN ('doctor', 'asistente')),
    CONSTRAINT ia_asistente_uso_fuente_check
        CHECK (fuente IN ('reglas', 'gemini_intent')),
    CONSTRAINT ia_asistente_uso_estado_check
        CHECK (estado IN ('reservado', 'resuelto', 'error', 'limitado')),
    CONSTRAINT ia_asistente_uso_tokens_check
        CHECK (
            tokens_entrada >= 0 AND tokens_salida >= 0
            AND tokens_razonamiento >= 0 AND tokens_total >= 0
        )
);

CREATE INDEX IF NOT EXISTS idx_ia_asistente_uso_consultorio_fecha
    ON IA_ASISTENTE_USO (correo_doctor, fecha_evento DESC);

CREATE INDEX IF NOT EXISTS idx_ia_asistente_uso_actor_fecha
    ON IA_ASISTENTE_USO (actor_hash, fecha_evento DESC);

CREATE INDEX IF NOT EXISTS idx_ia_asistente_uso_gemini_fecha
    ON IA_ASISTENTE_USO (fecha_evento DESC, fuente, estado);
