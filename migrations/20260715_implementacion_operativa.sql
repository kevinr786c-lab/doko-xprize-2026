-- Implementacion operativa y protocolos versionados de Doko.
-- Migracion aditiva: no modifica citas, Google Workspace ni tablas medicas existentes.

BEGIN;

CREATE TABLE IF NOT EXISTS PROTOCOLOS_DOKO (
    id_protocolo UUID PRIMARY KEY,
    codigo TEXT NOT NULL,
    version INTEGER NOT NULL,
    titulo TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    contenido JSONB NOT NULL,
    origen TEXT NOT NULL DEFAULT 'FLUJO_REAL_VALIDADO',
    estado TEXT NOT NULL DEFAULT 'ACTIVO',
    creado_por TEXT NOT NULL DEFAULT 'Doko',
    fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT protocolos_doko_version_check CHECK (version > 0),
    CONSTRAINT protocolos_doko_origen_check
        CHECK (origen IN ('FLUJO_REAL_VALIDADO', 'REFERENCIA_OPERATIVA')),
    CONSTRAINT protocolos_doko_estado_check CHECK (estado IN ('ACTIVO', 'ARCHIVADO')),
    CONSTRAINT protocolos_doko_codigo_version_unique UNIQUE (codigo, version)
);

CREATE TABLE IF NOT EXISTS EVALUACIONES_IMPLEMENTACION (
    id_evaluacion UUID PRIMARY KEY,
    correo_doctor TEXT NOT NULL REFERENCES DOCTORES(correo_doctor) ON DELETE RESTRICT,
    id_usuario_asistente UUID NULL REFERENCES USUARIOS_INTERNOS(id_usuario) ON DELETE SET NULL,
    tipo TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'BORRADOR',
    seccion_actual TEXT NOT NULL DEFAULT 'datos',
    creado_por TEXT NOT NULL,
    actualizado_por TEXT NOT NULL,
    aprobacion_confirmada BOOLEAN NOT NULL DEFAULT FALSE,
    aprobado_por_nombre TEXT NULL,
    aprobado_en TIMESTAMPTZ NULL,
    fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cerrado_en TIMESTAMPTZ NULL,
    CONSTRAINT evaluaciones_implementacion_tipo_check
        CHECK (tipo IN ('DIAGNOSTICO_INICIAL', 'CAPACITACION', 'EVALUACION', 'SEGUIMIENTO')),
    CONSTRAINT evaluaciones_implementacion_estado_check
        CHECK (estado IN (
            'BORRADOR', 'ENTREVISTA_COMPLETA', 'PROTOCOLOS_APROBADOS',
            'ASISTENTE_EVALUADA', 'SEGUIMIENTO', 'CERRADA'
        ))
);

CREATE TABLE IF NOT EXISTS EVALUACION_RESPUESTAS (
    id_respuesta UUID PRIMARY KEY,
    id_evaluacion UUID NOT NULL REFERENCES EVALUACIONES_IMPLEMENTACION(id_evaluacion) ON DELETE CASCADE,
    etapa TEXT NOT NULL,
    seccion TEXT NOT NULL,
    codigo_pregunta TEXT NOT NULL,
    respondente TEXT NOT NULL,
    opcion TEXT NULL,
    respuesta_texto TEXT NULL,
    fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT evaluacion_respuestas_respondente_check
        CHECK (respondente IN ('DOCTORA', 'ASISTENTE', 'ADMIN')),
    CONSTRAINT evaluacion_respuestas_unique
        UNIQUE (id_evaluacion, etapa, codigo_pregunta, respondente)
);

CREATE TABLE IF NOT EXISTS EVALUACION_PROTOCOLOS (
    id_evaluacion_protocolo UUID PRIMARY KEY,
    id_evaluacion UUID NOT NULL REFERENCES EVALUACIONES_IMPLEMENTACION(id_evaluacion) ON DELETE CASCADE,
    id_protocolo UUID NOT NULL REFERENCES PROTOCOLOS_DOKO(id_protocolo) ON DELETE RESTRICT,
    codigo_protocolo TEXT NOT NULL,
    version_protocolo INTEGER NOT NULL,
    protocolo_snapshot JSONB NOT NULL,
    decision TEXT NOT NULL DEFAULT 'DEFINIR_DESPUES',
    adaptacion_texto TEXT NULL,
    estado_aprobacion TEXT NOT NULL DEFAULT 'BORRADOR',
    aprobado_por_nombre TEXT NULL,
    aprobado_en TIMESTAMPTZ NULL,
    fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT evaluacion_protocolos_decision_check
        CHECK (decision IN ('ADOPTAR', 'ADAPTAR', 'NO_APLICA', 'DEFINIR_DESPUES')),
    CONSTRAINT evaluacion_protocolos_aprobacion_check
        CHECK (estado_aprobacion IN ('BORRADOR', 'APROBADO')),
    CONSTRAINT evaluacion_protocolos_unique UNIQUE (id_evaluacion, codigo_protocolo)
);

CREATE TABLE IF NOT EXISTS EVALUACION_REVISIONES (
    id_revision UUID PRIMARY KEY,
    id_evaluacion UUID NOT NULL REFERENCES EVALUACIONES_IMPLEMENTACION(id_evaluacion) ON DELETE CASCADE,
    seccion TEXT NOT NULL,
    fuente TEXT NOT NULL,
    hallazgos JSONB NOT NULL DEFAULT '[]'::jsonb,
    decision TEXT NOT NULL DEFAULT 'PENDIENTE',
    decidido_por TEXT NULL,
    fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decidido_en TIMESTAMPTZ NULL,
    CONSTRAINT evaluacion_revisiones_fuente_check CHECK (fuente IN ('REGLAS', 'GEMINI')),
    CONSTRAINT evaluacion_revisiones_decision_check
        CHECK (decision IN ('PENDIENTE', 'AGREGAR_BORRADOR', 'PREGUNTAR_DOCTORA', 'ADAPTAR', 'DESCARTAR'))
);

CREATE TABLE IF NOT EXISTS IA_EVALUACION_USO (
    id_uso UUID PRIMARY KEY,
    id_evaluacion UUID NULL REFERENCES EVALUACIONES_IMPLEMENTACION(id_evaluacion) ON DELETE SET NULL,
    correo_doctor TEXT NOT NULL,
    actor_hash TEXT NOT NULL,
    categoria TEXT NOT NULL,
    estado TEXT NOT NULL,
    motivo_limite TEXT NULL,
    modelo TEXT NULL,
    tokens_entrada INTEGER NOT NULL DEFAULT 0,
    tokens_salida INTEGER NOT NULL DEFAULT 0,
    tokens_razonamiento INTEGER NOT NULL DEFAULT 0,
    tokens_total INTEGER NOT NULL DEFAULT 0,
    costo_estimado_usd NUMERIC(14, 8) NOT NULL DEFAULT 0,
    duracion_ms INTEGER NULL,
    fecha_evento TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ia_evaluacion_uso_estado_check
        CHECK (estado IN ('RESERVADO', 'RESUELTO', 'ERROR', 'LIMITADO')),
    CONSTRAINT ia_evaluacion_uso_tokens_check CHECK (
        tokens_entrada >= 0 AND tokens_salida >= 0
        AND tokens_razonamiento >= 0 AND tokens_total >= 0
    )
);

CREATE INDEX IF NOT EXISTS idx_evaluaciones_implementacion_doctor
    ON EVALUACIONES_IMPLEMENTACION (correo_doctor, actualizado_en DESC);
CREATE INDEX IF NOT EXISTS idx_evaluaciones_implementacion_asistente
    ON EVALUACIONES_IMPLEMENTACION (id_usuario_asistente, actualizado_en DESC);
CREATE INDEX IF NOT EXISTS idx_evaluacion_respuestas_evaluacion
    ON EVALUACION_RESPUESTAS (id_evaluacion, etapa, seccion);
CREATE INDEX IF NOT EXISTS idx_evaluacion_protocolos_evaluacion
    ON EVALUACION_PROTOCOLOS (id_evaluacion, estado_aprobacion);
CREATE INDEX IF NOT EXISTS idx_evaluacion_revisiones_evaluacion
    ON EVALUACION_REVISIONES (id_evaluacion, seccion, fecha_creacion DESC);
CREATE INDEX IF NOT EXISTS idx_ia_evaluacion_uso_doctor_fecha
    ON IA_EVALUACION_USO (correo_doctor, fecha_evento DESC);
CREATE INDEX IF NOT EXISTS idx_ia_evaluacion_uso_actor_fecha
    ON IA_EVALUACION_USO (actor_hash, fecha_evento DESC);

INSERT INTO PROTOCOLOS_DOKO (
    id_protocolo, codigo, version, titulo, descripcion, contenido
) VALUES
(
    'd0000001-0000-4000-8000-000000000001',
    'ATENCION_ORIENTACION', 1,
    'Atencion y orientacion inicial',
    'Guia a la persona desde su primera solicitud hasta verificar que comprendio el siguiente paso.',
    $json${
      "objetivo":"Orientar, verificar y cerrar el proceso administrativo sin sustituir el criterio medico.",
      "pasos":[
        "Identificar si solicita informacion, ayuda para agendar o una respuesta medica.",
        "Compartir el enlace correcto y explicar como utilizarlo cuando sea necesario.",
        "Verificar en Doko que la cita aparecio cuando la persona ya se agendo.",
        "Explicar el correo inmediato de reserva y la confirmacion Doko de 24 o 48 horas, incluyendo Spam.",
        "Escalar a la doctora solo las preguntas que requieren criterio medico."
      ],
      "variantes":["La persona se agenda sola", "La asistente crea la cita", "La persona necesita guia paso a paso"],
      "limites":["No diagnosticar", "No inventar servicios, precios o disponibilidad", "Enviar un enlace no sustituye la orientacion"],
      "por_confirmar":["Canal preferido", "Tiempo esperado de respuesta", "Preguntas que siempre se escalan"],
      "escenario":"Una persona solicita informacion y no logra completar la reserva. Explica como la acompanarias hasta cerrar el proceso."
    }$json$::jsonb
),
(
    'd0000002-0000-4000-8000-000000000002',
    'RECUPERACION_CANCELADA', 1,
    'Recuperacion de cita cancelada',
    'Distingue entre un correo fallido y una confirmacion no respondida antes de recuperar un horario.',
    $json${
      "objetivo":"Investigar por que se libero una cita y recuperarla solo cuando el horario sigue disponible.",
      "pasos":[
        "Copiar desde Doko el correo registrado y revisar el envio correspondiente.",
        "Distinguir si el correo fallo o si fue enviado y no se confirmo.",
        "Si el envio fallo, tratarlo como error operativo y no como falta de respuesta de la persona.",
        "Si la persona confirma y el horario sigue libre, recuperar la cita como confirmada.",
        "Si aun no decide, crear un apartado temporal con vencimiento y liberarlo al concluir."
      ],
      "variantes":["Correo fallido", "Correo enviado sin respuesta", "Horario ya ocupado", "Persona indecisa"],
      "limites":["No prometer un horario ocupado", "No confirmar sin aceptacion expresa", "No mantener apartados indefinidos"],
      "por_confirmar":["Duracion autorizada del apartado", "Canal para avisar recuperacion"],
      "escenario":"Una persona llama porque su cita fue liberada. Describe que revisas antes de volver a asignarla."
    }$json$::jsonb
),
(
    'd0000003-0000-4000-8000-000000000003',
    'SEGUIMIENTO_CONSULTA', 1,
    'Seguimiento indicado despues de consulta',
    'La doctora define el intervalo clinico y recepcion organiza la fecha sin alterar esa indicacion.',
    $json${
      "objetivo":"Programar correctamente el seguimiento indicado por la doctora.",
      "pasos":[
        "Confirmar el intervalo indicado por la doctora.",
        "Revisar disponibilidad sin decidir por cuenta propia el tiempo clinico.",
        "Crear la cita o guiar a la persona para que se agende.",
        "Explicar que la cita futura entrara al ciclo de confirmacion configurado.",
        "Verificar que el evento aparezca en Doko."
      ],
      "variantes":["Recepcion agenda", "La persona se agenda", "No hay disponibilidad en la fecha aproximada"],
      "limites":["La asistente no cambia el intervalo clinico", "No marcar confirmada sin aceptacion expresa"],
      "por_confirmar":["Margen permitido alrededor de la fecha indicada", "Servicios que requieren seguimiento especial"],
      "escenario":"La doctora indica control en un mes. Explica que decisiones pertenecen a la doctora y cuales a recepcion."
    }$json$::jsonb
),
(
    'd0000004-0000-4000-8000-000000000004',
    'URGENCIA_DOCTORA', 1,
    'Cirugia o emergencia de la doctora',
    'Organiza las citas afectadas con autorizacion de la doctora y comunicacion individual.',
    $json${
      "objetivo":"Reducir el impacto de una ausencia o retraso imprevisto sin divulgar informacion privada.",
      "pasos":[
        "La doctora define el rango afectado y las opciones autorizadas.",
        "Identificar en agenda las citas del rango.",
        "Contactar individualmente y explicar solo que existe una situacion operativa o medica imprevista.",
        "Ofrecer esperar, acudir despues o reprogramar segun lo autorizado.",
        "Si se reprograma, conservar la cita actual hasta que la nueva opcion sea aceptada."
      ],
      "variantes":["Retraso corto", "Ausencia completa", "Persona acepta esperar", "Persona necesita reprogramar", "No responde"],
      "limites":["No revelar detalles privados", "No mover citas sin aceptacion", "No enviar mensajes masivos automaticamente"],
      "por_confirmar":["Tiempo de espera autorizado", "Que hacer si la urgencia se extiende", "Como registrar contacto completado"],
      "escenario":"La doctora informa que estara fuera de 9 a 11. Explica como atiendes las citas afectadas."
    }$json$::jsonb
),
(
    'd0000005-0000-4000-8000-000000000005',
    'HORARIOS_LIBERADOS', 1,
    'Cobertura de horarios liberados',
    'Ofrece un espacio disponible sin quitar la cita actual ni prometerlo a varias personas.',
    $json${
      "objetivo":"Aprovechar cancelaciones con orden y sin generar dobles compromisos.",
      "pasos":[
        "Identificar personas que solicitaron una fecha mas cercana.",
        "Conservar su cita actual mientras se ofrece el nuevo horario.",
        "Apartar temporalmente el horario liberado para una sola persona.",
        "Mover la cita solo despues de recibir aceptacion.",
        "Liberar la fecha anterior y cerrar el apartado."
      ],
      "variantes":["Acepta", "No responde", "Rechaza", "Varias personas interesadas"],
      "limites":["No prometer simultaneamente el mismo horario", "No cancelar la cita anterior antes de aceptar"],
      "por_confirmar":["Orden de contacto", "Tiempo de espera", "Registro manual de interesados"],
      "escenario":"Se libera un horario solicitado por varias personas. Explica como lo ofreces sin perder sus citas actuales."
    }$json$::jsonb
),
(
    'd0000006-0000-4000-8000-000000000006',
    'CANCELACION_REPROGRAMACION', 1,
    'Cancelacion y reprogramacion',
    'Distingue una cancelacion definitiva de un cambio de fecha y conserva el mismo evento cuando corresponde.',
    $json${
      "objetivo":"Cancelar o reprogramar sin perder el control del estado de la cita.",
      "pasos":[
        "Preguntar si desea cancelar definitivamente o elegir otra fecha.",
        "Para reprogramar, revisar primero la nueva disponibilidad sin cancelar la cita existente.",
        "Editar fecha y hora del mismo evento despues de que la persona acepte.",
        "Para cancelar, liberar el horario y registrar la cancelacion.",
        "Si aun no decide, conservar la cita y usar un apartado temporal para la alternativa."
      ],
      "variantes":["Pendiente que reprograma", "Confirmada que reprograma", "Cancelacion definitiva", "Nueva fecha no decidida"],
      "limites":["No liberar antes de conocer la intencion", "No crear duplicados cuando basta editar"],
      "por_confirmar":["Politica ante cambios repetidos", "Canal de confirmacion de la nueva fecha"],
      "escenario":"Una persona llama para cancelar, pero tambien quiere otra fecha. Explica el orden correcto."
    }$json$::jsonb
),
(
    'd0000007-0000-4000-8000-000000000007',
    'SERVICIOS_COSTOS', 1,
    'Servicios, costos y valoracion medica',
    'Comunica informacion aprobada por el consultorio y escala lo que requiere criterio medico.',
    $json${
      "objetivo":"Responder con claridad sin convertir la informacion administrativa en consejo medico.",
      "pasos":[
        "Identificar el servicio o la duda administrativa.",
        "Responder directamente cuando exista un precio fijo aprobado.",
        "Explicar que el costo final depende de valoracion cuando asi este configurado.",
        "Informar pagos y aseguradoras segun los datos aprobados del consultorio.",
        "Escalar preguntas clinicas a la doctora."
      ],
      "variantes":["Precio fijo", "Valoracion medica", "Aseguradora", "Pregunta clinica"],
      "limites":["No inventar precios", "No prometer cobertura", "No orientar tratamientos"],
      "por_confirmar":["Servicios con precio fijo", "Forma de explicar valoracion", "Aseguradoras verificadas"],
      "escenario":"Una persona pregunta cuanto costara un procedimiento cuyo precio depende de valoracion. Explica como respondes."
    }$json$::jsonb
)
ON CONFLICT (codigo, version) DO NOTHING;

COMMIT;
