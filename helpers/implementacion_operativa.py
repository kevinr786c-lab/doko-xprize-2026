"""Banco versionado de preguntas para Implementacion Operativa Doko."""

TIPOS_IMPLEMENTACION = {
    "DIAGNOSTICO_INICIAL": "Diagnostico inicial",
    "CAPACITACION": "Capacitacion",
    "EVALUACION": "Evaluacion",
    "SEGUIMIENTO": "Seguimiento",
}

ESTADOS_IMPLEMENTACION = {
    "BORRADOR": "Borrador",
    "ENTREVISTA_COMPLETA": "Entrevista completa",
    "PROTOCOLOS_APROBADOS": "Protocolos aprobados",
    "ASISTENTE_EVALUADA": "Asistente evaluada",
    "SEGUIMIENTO": "Seguimiento",
    "CERRADA": "Cerrada",
}

SECCIONES_IMPLEMENTACION = (
    {"codigo": "datos", "titulo": "Datos", "descripcion": "Objetivo y contexto de la visita."},
    {"codigo": "entrevista", "titulo": "Entrevista", "descripcion": "Como desea operar la doctora."},
    {"codigo": "protocolos", "titulo": "Protocolos", "descripcion": "Adoptar o adaptar referencias Doko."},
    {"codigo": "asistente", "titulo": "Asistente", "descripcion": "Comprension de escenarios operativos."},
    {"codigo": "plan", "titulo": "Capacitacion", "descripcion": "Acciones concretas de acompanamiento."},
    {"codigo": "seguimiento", "titulo": "Seguimiento", "descripcion": "Cambios observados y ajustes pendientes."},
    {"codigo": "resumen", "titulo": "Resumen", "descripcion": "Aprobacion y cierre de la implementacion."},
)


PREGUNTAS_IMPLEMENTACION = {
    "datos": (
        {
            "codigo": "objetivo_visita",
            "etapa": "DATOS",
            "respondente": "ADMIN",
            "titulo": "Objetivo de esta implementacion",
            "ayuda": "Que necesitas comprender, capacitar o revisar durante esta visita.",
            "tipo": "texto",
        },
        {
            "codigo": "observaciones_iniciales",
            "etapa": "DATOS",
            "respondente": "ADMIN",
            "titulo": "Observaciones iniciales",
            "ayuda": "Registra hechos operativos, sin datos de pacientes ni juicios personales.",
            "tipo": "texto",
        },
    ),
    "entrevista": (
        {
            "codigo": "recepcion_resuelve",
            "etapa": "ENTREVISTA_DOCTORA",
            "respondente": "DOCTORA",
            "titulo": "Que debe resolver recepcion sin interrumpirla?",
            "ayuda": "Por ejemplo: agenda, ubicacion, costos publicados o formas de pago.",
            "tipo": "texto",
        },
        {
            "codigo": "escalar_doctora",
            "etapa": "ENTREVISTA_DOCTORA",
            "respondente": "DOCTORA",
            "titulo": "Que situaciones deben escalarse siempre con usted?",
            "ayuda": "Distingue decisiones medicas de dudas administrativas.",
            "tipo": "texto",
        },
        {
            "codigo": "datos_recopilar",
            "etapa": "ENTREVISTA_DOCTORA",
            "respondente": "DOCTORA",
            "titulo": "Que informacion puede solicitar la asistente?",
            "ayuda": "Define solo los datos autorizados para preparar la atencion.",
            "tipo": "texto",
        },
        {
            "codigo": "tareas_antes_consulta",
            "etapa": "ENTREVISTA_DOCTORA",
            "respondente": "DOCTORA",
            "titulo": "Que debe estar listo antes de cada consulta?",
            "ayuda": "Recepcion, documentos, consultorio, materiales u otras tareas aprobadas.",
            "tipo": "texto",
        },
        {
            "codigo": "tareas_administrativas",
            "etapa": "ENTREVISTA_DOCTORA",
            "respondente": "DOCTORA",
            "titulo": "Que tareas administrativas espera de la asistente?",
            "ayuda": "Incluye seguimiento de agenda, llamadas y apoyo no clinico.",
            "tipo": "texto",
        },
        {
            "codigo": "servicios_costos",
            "etapa": "ENTREVISTA_DOCTORA",
            "respondente": "DOCTORA",
            "titulo": "Como deben explicarse servicios y costos?",
            "ayuda": "Aclara precios fijos, valoracion medica, pagos y aseguradoras.",
            "tipo": "texto",
        },
        {
            "codigo": "tiempo_respuesta",
            "etapa": "ENTREVISTA_DOCTORA",
            "respondente": "DOCTORA",
            "titulo": "Cual es el tiempo esperado de respuesta?",
            "ayuda": "Define una expectativa realista para llamadas y mensajes.",
            "tipo": "texto",
        },
        {
            "codigo": "cancelaciones",
            "etapa": "ENTREVISTA_DOCTORA",
            "respondente": "DOCTORA",
            "titulo": "Como desea manejar cancelaciones y cambios?",
            "ayuda": "Incluye recuperacion de espacios y reprogramaciones.",
            "tipo": "texto",
        },
        {
            "codigo": "paciente_bien_atendido",
            "etapa": "ENTREVISTA_DOCTORA",
            "respondente": "DOCTORA",
            "titulo": "Que significa para usted una persona bien atendida?",
            "ayuda": "Describe el resultado esperado, no la personalidad de la asistente.",
            "tipo": "texto",
        },
        {
            "codigo": "apoyo_doko",
            "etapa": "ENTREVISTA_DOCTORA",
            "respondente": "DOCTORA",
            "titulo": "Que deberia ayudar a organizar Doko?",
            "ayuda": "Identifica trabajo repetitivo, confuso o dificil de verificar.",
            "tipo": "texto",
        },
    ),
    "plan": (
        {
            "codigo": "fortalezas_observadas",
            "etapa": "CAPACITACION",
            "respondente": "ADMIN",
            "titulo": "Fortalezas observadas",
            "ayuda": "Que procesos ya se realizan de forma clara y consistente.",
            "tipo": "texto",
        },
        {
            "codigo": "temas_capacitacion",
            "etapa": "CAPACITACION",
            "respondente": "ADMIN",
            "titulo": "Temas que requieren capacitacion",
            "ayuda": "Selecciona pocos cambios concretos y verificables.",
            "tipo": "texto",
        },
        {
            "codigo": "acciones_acordadas",
            "etapa": "CAPACITACION",
            "respondente": "ADMIN",
            "titulo": "Acciones acordadas",
            "ayuda": "Que se hara, quien lo hara y como se comprobara.",
            "tipo": "texto",
        },
        {
            "codigo": "fecha_revision",
            "etapa": "CAPACITACION",
            "respondente": "ADMIN",
            "titulo": "Momento de la siguiente revision",
            "ayuda": "Registra el acuerdo sin incluir citas de pacientes.",
            "tipo": "texto",
        },
    ),
    "seguimiento": (
        {
            "codigo": "cambios_observados",
            "etapa": "SEGUIMIENTO",
            "respondente": "ADMIN",
            "titulo": "Que cambio desde la implementacion?",
            "ayuda": "Usa hechos observables del flujo de trabajo.",
            "tipo": "texto",
        },
        {
            "codigo": "dificultades_persistentes",
            "etapa": "SEGUIMIENTO",
            "respondente": "ADMIN",
            "titulo": "Que dificultades siguen presentes?",
            "ayuda": "Distingue capacitacion, acceso, proceso indefinido o mejora de Doko.",
            "tipo": "texto",
        },
        {
            "codigo": "ajustes_requeridos",
            "etapa": "SEGUIMIENTO",
            "respondente": "ADMIN",
            "titulo": "Que debe ajustarse ahora?",
            "ayuda": "Puede ser protocolo, capacitacion o herramienta.",
            "tipo": "texto",
        },
    ),
    "resumen": (
        {
            "codigo": "conclusion_implementacion",
            "etapa": "RESUMEN",
            "respondente": "ADMIN",
            "titulo": "Conclusion de la implementacion",
            "ayuda": "Resume acuerdos, pendientes y proximo seguimiento.",
            "tipo": "texto",
        },
    ),
}


RESULTADOS_ASISTENTE = (
    ("COMPRENDIDO", "Comprendido"),
    ("REQUIERE_CAPACITACION", "Requiere capacitacion"),
    ("PROCESO_NO_DEFINIDO", "Proceso todavia no definido"),
    ("FALTA_ACCESO", "Falta acceso o herramienta"),
    ("ALTERNATIVA_REVISAR", "Alternativa para revisar"),
    ("MEJORA_DOKO", "Oportunidad de mejora en Doko"),
)


def preguntas_asistente(protocolos):
    """Convierte el escenario congelado de cada protocolo en una pregunta."""
    preguntas = []
    for protocolo in protocolos:
        snapshot = protocolo.get("protocolo_snapshot") or {}
        contenido = snapshot.get("contenido") or {}
        preguntas.append({
            "codigo": f"escenario_{protocolo['codigo_protocolo'].lower()}",
            "etapa": "EVALUACION_ASISTENTE",
            "respondente": "ASISTENTE",
            "titulo": snapshot.get("titulo") or protocolo["codigo_protocolo"],
            "ayuda": contenido.get("escenario") or "Explica como resolverias este escenario.",
            "tipo": "evaluacion",
            "opciones": RESULTADOS_ASISTENTE,
            "codigo_protocolo": protocolo["codigo_protocolo"],
        })
    return tuple(preguntas)


def mapa_preguntas(protocolos=()):
    resultado = {}
    for seccion, preguntas in PREGUNTAS_IMPLEMENTACION.items():
        for pregunta in preguntas:
            resultado[pregunta["codigo"]] = {**pregunta, "seccion": seccion}
    for pregunta in preguntas_asistente(protocolos):
        resultado[pregunta["codigo"]] = {**pregunta, "seccion": "asistente"}
    return resultado
