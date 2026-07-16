-- Presencia Digital Medica: contenido comercial separado del Portal del Paciente.
CREATE TABLE IF NOT EXISTS SITIOS_MEDICOS (
    id_sitio UUID PRIMARY KEY,
    correo_doctor TEXT NOT NULL UNIQUE REFERENCES DOCTORES(correo_doctor),
    subdominio TEXT NOT NULL UNIQUE,
    estado TEXT NOT NULL DEFAULT 'BORRADOR',
    estado_dominio TEXT NOT NULL DEFAULT 'PENDIENTE_DOMINIO',
    plantilla TEXT NOT NULL DEFAULT 'clinica_clara',
    titulo_seo TEXT,
    descripcion_seo TEXT,
    biografia TEXT,
    portada_url TEXT,
    logo_url TEXT,
    whatsapp_numero TEXT,
    cedula_profesional TEXT,
    cedula_especialidad TEXT,
    institucion_titulo TEXT,
    aviso_publicidad_cofepris TEXT,
    orden_secciones JSONB NOT NULL DEFAULT '["servicios","credenciales","galeria","ubicacion"]'::jsonb,
    configuracion_visual JSONB NOT NULL DEFAULT '{}'::jsonb,
    fecha_creacion TIMESTAMP NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT sitios_medicos_subdominio_check CHECK (subdominio ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
    CONSTRAINT sitios_medicos_estado_check CHECK (estado IN ('BORRADOR', 'PUBLICADO', 'PAUSADO')),
    CONSTRAINT sitios_medicos_estado_dominio_check CHECK (estado_dominio IN ('PENDIENTE_DOMINIO', 'CONFIGURADO', 'VERIFICADO', 'ERROR')),
    CONSTRAINT sitios_medicos_plantilla_check CHECK (plantilla IN ('clinica_clara', 'especialista_editorial', 'consulta_moderna'))
);

CREATE TABLE IF NOT EXISTS SITIOS_MEDICOS_MEDIA (
    id_media UUID PRIMARY KEY,
    id_sitio UUID NOT NULL REFERENCES SITIOS_MEDICOS(id_sitio) ON DELETE CASCADE,
    tipo TEXT NOT NULL,
    url TEXT NOT NULL,
    texto_alternativo TEXT,
    titulo TEXT,
    orden INTEGER NOT NULL DEFAULT 0,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_creacion TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT sitios_medicos_media_tipo_check CHECK (tipo IN ('GALERIA', 'RECONOCIMIENTO'))
);

CREATE TABLE IF NOT EXISTS SITIOS_MEDICOS_CREDENCIALES (
    id_credencial UUID PRIMARY KEY,
    id_sitio UUID NOT NULL REFERENCES SITIOS_MEDICOS(id_sitio) ON DELETE CASCADE,
    tipo TEXT NOT NULL,
    titulo TEXT NOT NULL,
    institucion TEXT,
    descripcion TEXT,
    fecha_obtencion DATE,
    imagen_url TEXT,
    orden INTEGER NOT NULL DEFAULT 0,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_creacion TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT sitios_medicos_credenciales_tipo_check CHECK (tipo IN ('CERTIFICACION', 'RECONOCIMIENTO'))
);

CREATE TABLE IF NOT EXISTS SITIOS_MEDICOS_REDES (
    id_red UUID PRIMARY KEY,
    id_sitio UUID NOT NULL REFERENCES SITIOS_MEDICOS(id_sitio) ON DELETE CASCADE,
    red TEXT NOT NULL,
    url TEXT NOT NULL,
    orden INTEGER NOT NULL DEFAULT 0,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT sitios_medicos_redes_tipo_check CHECK (red IN ('INSTAGRAM', 'FACEBOOK', 'TIKTOK', 'YOUTUBE', 'LINKEDIN', 'WEB'))
);

CREATE TABLE IF NOT EXISTS SITIOS_MEDICOS_EVENTOS (
    id_evento UUID PRIMARY KEY,
    id_sitio UUID NOT NULL REFERENCES SITIOS_MEDICOS(id_sitio) ON DELETE CASCADE,
    tipo_evento TEXT NOT NULL,
    session_hash TEXT NOT NULL,
    fecha_evento TIMESTAMP NOT NULL DEFAULT NOW(),
    fecha_dia DATE NOT NULL DEFAULT CURRENT_DATE,
    origen TEXT,
    CONSTRAINT sitios_medicos_eventos_tipo_check CHECK (tipo_evento IN ('VISITA', 'CLICK_WHATSAPP', 'CLICK_AGENDAR', 'FORMULARIO_ENVIADO')),
    CONSTRAINT sitios_medicos_eventos_unico_por_dia UNIQUE (id_sitio, tipo_evento, session_hash, fecha_dia)
);

CREATE TABLE IF NOT EXISTS SITIOS_MEDICOS_METRICAS_DIARIAS (
    id_sitio UUID NOT NULL REFERENCES SITIOS_MEDICOS(id_sitio) ON DELETE CASCADE,
    fecha DATE NOT NULL,
    visitas INTEGER NOT NULL DEFAULT 0,
    clics_whatsapp INTEGER NOT NULL DEFAULT 0,
    clics_agendar INTEGER NOT NULL DEFAULT 0,
    formularios INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (id_sitio, fecha)
);

CREATE INDEX IF NOT EXISTS idx_sitios_medicos_estado ON SITIOS_MEDICOS(estado);
CREATE INDEX IF NOT EXISTS idx_sitios_medicos_media_sitio ON SITIOS_MEDICOS_MEDIA(id_sitio, activo, orden);
CREATE INDEX IF NOT EXISTS idx_sitios_medicos_credenciales_sitio ON SITIOS_MEDICOS_CREDENCIALES(id_sitio, activo, orden);
CREATE INDEX IF NOT EXISTS idx_sitios_medicos_eventos_sitio_fecha ON SITIOS_MEDICOS_EVENTOS(id_sitio, fecha_evento DESC);
