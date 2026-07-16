from agentes.gemini_client import crear_modelo_gemini

MODELO_GEMINI = "gemini-2.5-flash"


class CerebroGemini:
    """Wrapper Gemini 2.5 Flash — chatbot paciente y asistente admin."""

    def __init__(self):
        self.model = crear_modelo_gemini(MODELO_GEMINI)

    def responder_paciente(self, pregunta: str, faq_data, info_doctor: dict) -> str:
        if isinstance(faq_data, list):
            faqs = faq_data
            servicios = []
        elif isinstance(faq_data, dict):
            faqs = faq_data.get("faqs", [])
            servicios = faq_data.get("servicios", [])
        else:
            faqs, servicios = [], []

        contexto_servicios = self._formatear_servicios(servicios)
        contexto_faqs = self._formatear_faqs(faqs)
        nombre = info_doctor.get('nombre_doctor', 'doctor')

        prompt = f"""Eres el asistente virtual del consultorio del Dr(a). {nombre}.
Responde SOLO con la información de abajo.

INFORMACIÓN DEL CONSULTORIO:
- Especialidad: {info_doctor.get('especialidad', 'No especificada')}
- Teléfono: {info_doctor.get('telefono_consultorio', 'No disponible')}
- Dirección: {info_doctor.get('direccion_consultorio', 'No disponible')}
- Aseguradoras: {info_doctor.get('aseguradoras_aceptadas', 'Consultar')}

SERVICIOS Y PRECIOS:
{contexto_servicios}

PREGUNTAS FRECUENTES:
{contexto_faqs}

REGLAS ESTRICTAS:
1. NO diagnostiques. NO agendes citas directamente. NO inventes datos.
2. NO hables de otros doctores.
3. Para agendar, indica usar el calendario en esta página.
4. Si no sabes algo: "Para esa información, llama al {info_doctor.get('telefono_consultorio', 'consultorio')}."
5. Español, máximo 3 párrafos cortos, tono amable.

PREGUNTA DEL PACIENTE: {pregunta}"""

        try:
            return self.model.generate_content(prompt).text.strip()
        except Exception:
            return (
                f"En este momento no puedo procesar tu pregunta. "
                f"Llama al consultorio: {info_doctor.get('telefono_consultorio', '')}."
            )

    def responder_admin(self, pregunta: str, contexto_negocio) -> str:
        if isinstance(contexto_negocio, str):
            contexto_str = contexto_negocio
        else:
            contexto_str = self._formatear_contexto_negocio(contexto_negocio or {})

        prompt = f"""Eres el asistente de operaciones de Doko Hub Logistics, SaaS médico en México.
Responde directo y accionable en máximo 5 líneas.

ESTADO DEL NEGOCIO:
{contexto_str}

PREGUNTA: {pregunta}"""

        try:
            return self.model.generate_content(prompt).text.strip()
        except Exception as e:
            return f"Error al consultar Gemini: {e}"

    def _formatear_servicios(self, servicios: list) -> str:
        if not servicios:
            return "No hay servicios registrados."
        lineas = []
        for s in servicios:
            precio = f"${float(s['precio']):,.0f}" if s.get('precio') else "Consultar precio"
            lineas.append(f"- {s.get('nombre_servicio', 'Servicio')}: {precio}")
        return "\n".join(lineas)

    def _formatear_faqs(self, faqs: list) -> str:
        if not faqs:
            return "No hay preguntas frecuentes registradas."
        lineas = []
        for faq in faqs[:10]:
            claves = faq.get("palabras_clave", "")
            lineas.append(f"- [{claves}]: {faq.get('respuesta', '')}")
        return "\n".join(lineas)

    def _formatear_contexto_negocio(self, ctx: dict) -> str:
        lineas = []
        for key, label in [
            ("doctores_activos", "Doctores activos"),
            ("citas_hoy", "Citas hoy"),
            ("pedidos_nuevos", "Pedidos nuevos"),
            ("pedidos_en_camino", "Pedidos en camino"),
            ("lotes_por_vencer", "Lotes por vencer"),
            ("ingresos_mes", "Ingresos del mes"),
        ]:
            if key in ctx:
                val = ctx[key]
                if key == "ingresos_mes":
                    val = f"${float(val):,.0f} MXN"
                lineas.append(f"{label}: {val}")
        return "\n".join(lineas) if lineas else "Sin datos disponibles."
