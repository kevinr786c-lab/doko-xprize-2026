-- Permite el rol asistente en usuarios internos.
-- Necesario para que una asistente pueda entrar desde /login/interno
-- y operar el panel de las doctoras asignadas.

ALTER TABLE USUARIOS_INTERNOS
    DROP CONSTRAINT IF EXISTS usuarios_internos_rol_check;

ALTER TABLE USUARIOS_INTERNOS
    ADD CONSTRAINT usuarios_internos_rol_check
    CHECK (rol = ANY (ARRAY['admin'::text, 'bodeguero'::text, 'repartidor'::text, 'asistente'::text]));
