ALTER TABLE DOCTORES
    ADD COLUMN IF NOT EXISTS color_tema TEXT NOT NULL DEFAULT 'marino';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'doctores_color_tema_check') THEN
        ALTER TABLE DOCTORES ADD CONSTRAINT doctores_color_tema_check
            CHECK (color_tema IN ('marino', 'verde', 'turquesa', 'lila', 'sakura', 'vino'));
    END IF;
END $$;
