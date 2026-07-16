-- Presencia Digital Doko: campos editoriales, SEO, conversion y metricas.

ALTER TABLE SITIOS_MEDICOS
    ADD COLUMN IF NOT EXISTS nombre_clinica_publico TEXT,
    ADD COLUMN IF NOT EXISTS especialidad_publica TEXT,
    ADD COLUMN IF NOT EXISTS ciudad TEXT DEFAULT 'Tijuana',
    ADD COLUMN IF NOT EXISTS estado_region TEXT,
    ADD COLUMN IF NOT EXISTS color_secundario TEXT,
    ADD COLUMN IF NOT EXISTS hero_titulo TEXT,
    ADD COLUMN IF NOT EXISTS hero_subtitulo TEXT,
    ADD COLUMN IF NOT EXISTS hero_texto_confianza TEXT,
    ADD COLUMN IF NOT EXISTS texto_boton_principal TEXT DEFAULT 'Agendar cita',
    ADD COLUMN IF NOT EXISTS destino_boton_principal TEXT,
    ADD COLUMN IF NOT EXISTS texto_boton_whatsapp TEXT DEFAULT 'Enviar WhatsApp',
    ADD COLUMN IF NOT EXISTS mostrar_whatsapp BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS mostrar_agenda BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS biografia_corta TEXT,
    ADD COLUMN IF NOT EXISTS biografia_larga TEXT,
    ADD COLUMN IF NOT EXISTS enfoque_atencion TEXT,
    ADD COLUMN IF NOT EXISTS anios_experiencia INTEGER,
    ADD COLUMN IF NOT EXISTS formacion_resumida TEXT,
    ADD COLUMN IF NOT EXISTS frase_destacada TEXT,
    ADD COLUMN IF NOT EXISTS firma_visible TEXT,
    ADD COLUMN IF NOT EXISTS og_title TEXT,
    ADD COLUMN IF NOT EXISTS og_description TEXT,
    ADD COLUMN IF NOT EXISTS og_image TEXT,
    ADD COLUMN IF NOT EXISTS canonical_url TEXT,
    ADD COLUMN IF NOT EXISTS keywords_internas TEXT,
    ADD COLUMN IF NOT EXISTS indexable BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS schema_medico_activo BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS faq_schema_activo BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS mostrar_pagos BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS mostrar_aseguradoras BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS texto_pagos TEXT,
    ADD COLUMN IF NOT EXISTS texto_aseguradoras TEXT,
    ADD COLUMN IF NOT EXISTS estacionamiento TEXT,
    ADD COLUMN IF NOT EXISTS instrucciones_llegada TEXT,
    ADD COLUMN IF NOT EXISTS fecha_publicacion TIMESTAMP;

ALTER TABLE SITIOS_MEDICOS_MEDIA
    ADD COLUMN IF NOT EXISTS descripcion TEXT,
    ADD COLUMN IF NOT EXISTS aprobado_por_admin BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE SITIOS_MEDICOS_CREDENCIALES
    ADD COLUMN IF NOT EXISTS texto_alternativo TEXT;

ALTER TABLE SITIOS_MEDICOS_METRICAS_DIARIAS
    ADD COLUMN IF NOT EXISTS clics_maps INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS clics_telefono INTEGER NOT NULL DEFAULT 0;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'sitios_medicos_media_tipo_check'
    ) THEN
        ALTER TABLE SITIOS_MEDICOS_MEDIA DROP CONSTRAINT sitios_medicos_media_tipo_check;
    END IF;
    ALTER TABLE SITIOS_MEDICOS_MEDIA
        ADD CONSTRAINT sitios_medicos_media_tipo_check
        CHECK (tipo IN ('GALERIA', 'CONSULTORIO', 'RECEPCION', 'EQUIPO', 'FACHADA', 'RECONOCIMIENTO', 'OTRO'));
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'sitios_medicos_credenciales_tipo_check'
    ) THEN
        ALTER TABLE SITIOS_MEDICOS_CREDENCIALES DROP CONSTRAINT sitios_medicos_credenciales_tipo_check;
    END IF;
    ALTER TABLE SITIOS_MEDICOS_CREDENCIALES
        ADD CONSTRAINT sitios_medicos_credenciales_tipo_check
        CHECK (tipo IN ('CERTIFICACION', 'RECONOCIMIENTO', 'DIPLOMA', 'ASOCIACION', 'CEDULA'));
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'sitios_medicos_eventos_tipo_check'
    ) THEN
        ALTER TABLE SITIOS_MEDICOS_EVENTOS DROP CONSTRAINT sitios_medicos_eventos_tipo_check;
    END IF;
    ALTER TABLE SITIOS_MEDICOS_EVENTOS
        ADD CONSTRAINT sitios_medicos_eventos_tipo_check
        CHECK (tipo_evento IN ('VISITA', 'CLICK_WHATSAPP', 'CLICK_AGENDAR', 'CLICK_MAPS', 'CLICK_TELEFONO', 'FORMULARIO_ENVIADO'));
END $$;

CREATE INDEX IF NOT EXISTS idx_sitios_medicos_subdominio ON SITIOS_MEDICOS(subdominio);
