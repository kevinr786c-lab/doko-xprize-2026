-- Permite usar el tema rosa sakura en el perfil del doctor.
-- La aplicacion ya valida este valor; esta migracion actualiza el CHECK viejo.

ALTER TABLE DOCTORES
    DROP CONSTRAINT IF EXISTS doctores_color_tema_check;

ALTER TABLE DOCTORES
    ADD CONSTRAINT doctores_color_tema_check
    CHECK (color_tema IN ('marino', 'verde', 'turquesa', 'lila', 'sakura', 'vino'));
