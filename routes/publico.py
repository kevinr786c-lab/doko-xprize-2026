import time
from collections import defaultdict
from flask import Blueprint, render_template, request, jsonify
from psycopg2.extras import RealDictCursor

from helpers.db import get_connection

publico_bp = Blueprint('publico_bp', __name__)

# ==============================================================================
# Seguridad y optimizacion
# ==============================================================================

_rate_limit = defaultdict(list)
_cerebro = None


def check_rate_limit(ip: str, max_req: int = 10, window: int = 60) -> bool:
    ahora = time.time()
    _rate_limit[ip] = [t for t in _rate_limit[ip] if ahora - t < window]
    if len(_rate_limit[ip]) >= max_req:
        return False
    _rate_limit[ip].append(ahora)
    return True


def get_cerebro():
    global _cerebro
    if _cerebro is None:
        from agentes.cerebro_gemini import CerebroGemini
        _cerebro = CerebroGemini()
    return _cerebro


def generar_respuesta_controlada(prompt: str) -> str:
    # El FAQ local resuelve la mayoría de mensajes. Este camino sólo se usa
    # como respaldo/traducción y respeta el límite local de costo.
    from agentes.gemini_client import generar_texto
    return generar_texto(prompt)


def traducir_clinica_a_ingles(texto_fuente: str) -> str:
    prompt = f"""Translate the following clinic information into English. Do not add new information. Do not diagnose. Do not recommend treatment. Only translate or lightly reformulate the provided text. Use plain text without Markdown, asterisks, or headings.

Clinic information:
{texto_fuente[:2500]}"""
    return generar_respuesta_controlada(prompt)


def responder_respaldo_limitado(pregunta: str, doctor: dict, servicios: list, faqs: list, idioma: str) -> str:
    servicios_txt = "\n".join(
        f"- {s.get('nombre_servicio', 'Servicio')}: ${float(s['precio']):,.0f} MXN"
        if s.get('tipo_precio') == 'precio_fijo' and s.get('precio') is not None
        else f"- {s.get('nombre_servicio', 'Servicio')}: {'El costo puede variar según valoración médica.' if s.get('tipo_precio') == 'segun_valoracion' else 'El costo final se determina durante la consulta.'}"
        for s in servicios[:12]
    ) or "No hay servicios configurados."
    faqs_txt = "\n".join(
        f"- {faq.get('palabras_clave', '')}: {faq.get('respuesta', '')}"
        for faq in faqs[:10]
    ) or "No hay preguntas frecuentes configuradas."
    idioma_respuesta = "English" if idioma == "en" else "Spanish"
    telefono = doctor.get('telefono_consultorio') or 'el consultorio'

    prompt = f"""You are Doko's virtual assistant for a public clinic page.
Answer in {idioma_respuesta}.

You may only answer about:
- services
- pricing
- location
- office hours
- phone
- how to book
- telling the patient to use the calendar on this page
- telling the patient to call the clinic if information is missing

Reject or redirect:
- diagnosis
- medications
- treatments
- medical emergencies
- inventory
- store
- warehouse
- orders

Rules:
1. Do not invent services, prices, studies, instructions, or medical advice.
2. Do not diagnose.
3. Do not recommend treatment.
4. If the information is not present, say to call the clinic: {telefono}.
5. Keep the answer short and clear.
6. Use plain text without Markdown, asterisks, or headings.

Clinic context:
- Doctor: {doctor.get('nombre_doctor', 'Doko')}
- Specialty: {doctor.get('especialidad', 'No especificada')}
- Phone: {telefono}
- Address: {doctor.get('direccion_consultorio', 'No disponible')}
- Office hours: {doctor.get('horarios_atencion', 'No disponible')}
- Current office notice: {doctor.get('aviso_consultorio') if doctor.get('aviso_activo') else 'No active notice'}

Services:
{servicios_txt}

FAQs:
{faqs_txt}

Patient question:
{pregunta[:500]}"""
    return generar_respuesta_controlada(prompt)


# ==============================================================================
# Helpers de datos
# ==============================================================================

def construir_faq_data(id_publico: str) -> list:
    """Extrae las FAQs especificas del doctor por id_publico y las FAQs globales."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT palabras_clave, respuesta
            FROM FAQ_CHATBOT
            WHERE (id_doctor_app = %s OR id_doctor_app IS NULL)
              AND activo = TRUE
              AND visible_en_chatbot = TRUE
            ORDER BY orden ASC
        """, (id_publico,))
        return cur.fetchall()
    finally:
        conn.close()


# ==============================================================================
# Rutas publicas
# ==============================================================================

@publico_bp.route('/p/<id_publico>', methods=['GET'])
def ver_perfil(id_publico):
    """Renderiza el perfil publico del doctor para los pacientes."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT correo_doctor, nombre_doctor, especialidad, telefono_consultorio,
                   foto_perfil_url, calendar_booking_url, direccion_consultorio, maps_url,
                   aseguradoras_aceptadas, metodos_pago_aceptados, horarios_atencion,
                   modo_confirmacion, color_tema, aviso_consultorio,
                   (aviso_activo AND aviso_visible_portal AND (aviso_expira_en IS NULL OR aviso_expira_en >= NOW())) AS aviso_activo,
                   activo, id_publico
            FROM DOCTORES
            WHERE id_publico = %s
        """, (id_publico,))
        doctor = cur.fetchone()

        if not doctor or not doctor['activo']:
            return render_template('publico/no_disponible.html'), 200

        cur.execute("""
            SELECT nombre_servicio, precio, tipo_precio, descripcion
            FROM CAT_SERVICIOS_CONSULTORIO
            WHERE correo_doctor = %s AND activo = TRUE
        """, (doctor['correo_doctor'],))
        servicios = cur.fetchall()

        faq_data = construir_faq_data(doctor['id_publico'])

        return render_template(
            'publico/perfil.html',
            doctor=doctor,
            servicios=servicios,
            faq_data=faq_data,
        )
    finally:
        conn.close()


@publico_bp.route('/p/<id_publico>/chat', methods=['POST'])
def chat_paciente(id_publico):
    """Endpoint que procesa preguntas con modos controlados de IA."""
    ip_cliente = request.remote_addr
    if not check_rate_limit(ip_cliente):
        return jsonify({
            'respuesta': "Has enviado muchos mensajes seguidos. Por favor, espera un minuto o contacta directamente al consultorio."
        }), 200

    data = request.json or {}
    pregunta = data.get('pregunta', '').strip()[:500]
    idioma = data.get('idioma', 'es')
    idioma = 'en' if idioma == 'en' else 'es'
    modo = data.get('modo', 'respaldo')
    texto_fuente = data.get('texto_fuente', '').strip()[:2500]

    if not pregunta and modo != 'traducir':
        return jsonify({'respuesta': "No recibí tu mensaje. ¿En qué te puedo ayudar?"}), 200

    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT correo_doctor, nombre_doctor, especialidad, telefono_consultorio,
                   direccion_consultorio, aseguradoras_aceptadas, metodos_pago_aceptados, horarios_atencion,
                   modo_confirmacion, aviso_consultorio,
                   (aviso_activo AND aviso_visible_chatbot AND (aviso_expira_en IS NULL OR aviso_expira_en >= NOW())) AS aviso_activo,
                   id_publico
            FROM DOCTORES
            WHERE id_publico = %s AND activo = TRUE
        """, (id_publico,))
        doctor = cur.fetchone()

        if not doctor:
            return jsonify({'respuesta': "Este consultorio no se encuentra disponible en este momento."}), 200

        cur.execute("""
            SELECT nombre_servicio, precio, tipo_precio, descripcion
            FROM CAT_SERVICIOS_CONSULTORIO
            WHERE correo_doctor = %s AND activo = TRUE
        """, (doctor['correo_doctor'],))
        servicios = cur.fetchall()

        faqs = construir_faq_data(doctor['id_publico'])

        if modo == 'traducir' and idioma == 'en' and texto_fuente:
            respuesta_ia = traducir_clinica_a_ingles(texto_fuente)
        else:
            respuesta_ia = responder_respaldo_limitado(pregunta, doctor, servicios, faqs, idioma)

        return jsonify({'respuesta': respuesta_ia}), 200

    except Exception as e:
        print(f"Error en chat público: {e}")
        telefono_salvavidas = doctor['telefono_consultorio'] if 'doctor' in locals() and doctor else "el consultorio"
        return jsonify({
            'respuesta': f"Tengo un pequeño problema de conexión en este momento. Por favor, comunícate directamente al {telefono_salvavidas}."
        }), 200
    finally:
        if conn:
            conn.close()
