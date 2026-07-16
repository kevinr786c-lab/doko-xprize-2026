-- Rutas editoriales para paginas locales de especialidad en doko.lat.
CREATE TABLE IF NOT EXISTS SEO_LOCAL_RUTAS (
    id_ruta UUID PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    especialidad TEXT NOT NULL,
    ciudad TEXT NOT NULL DEFAULT 'Tijuana',
    titulo TEXT NOT NULL,
    subtitulo TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    terminos_busqueda JSONB NOT NULL DEFAULT '[]'::jsonb,
    estado TEXT NOT NULL DEFAULT 'BORRADOR',
    orden INTEGER NOT NULL DEFAULT 999,
    fecha_creacion TIMESTAMP NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT seo_local_rutas_slug_check CHECK (slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
    CONSTRAINT seo_local_rutas_estado_check CHECK (estado IN ('BORRADOR', 'PUBLICADO', 'PAUSADO'))
);

CREATE INDEX IF NOT EXISTS idx_seo_local_rutas_estado_orden
    ON SEO_LOCAL_RUTAS (estado, orden, slug);
CREATE INDEX IF NOT EXISTS idx_seo_local_rutas_ciudad
    ON SEO_LOCAL_RUTAS (LOWER(ciudad));
CREATE INDEX IF NOT EXISTS idx_seo_local_rutas_especialidad
    ON SEO_LOCAL_RUTAS (LOWER(especialidad));
