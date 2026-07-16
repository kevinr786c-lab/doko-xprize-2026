(function () {
  'use strict';

  const chatWindow = document.getElementById('chat-window');
  const chatInput = document.getElementById('chat-input');
  const chatForm = document.getElementById('chat-form');
  const chatToggle = document.getElementById('chat-toggle');
  const chatClose = document.getElementById('chat-close');
  const chatContainer = document.getElementById('chat-container');
  const chatShow = document.getElementById('chat-show');
  const chatPreview = document.getElementById('chat-preview');
  const chatSuggestions = document.getElementById('chat-suggestions');
  const idPublico = chatContainer ? chatContainer.dataset.id : null;
  const data = window.FAQ_DATA || {};
  const doctor = data.doctor || {};

  if (!chatWindow || !chatInput || !chatForm || !chatContainer) return;

  let idioma = localStorage.getItem('doko_chat_lang') || 'es';
  let chatHidden = localStorage.getItem('doko_chat_hidden') === '1';
  let idleTimer = null;

  const textos = {
    es: {
      saludo: 'Hola, soy el asistente virtual de Doko. Puedo ayudarte con servicios, costos, ubicacion, formas de pago y como agendar tu cita.',
      agenda: 'Para reservar, selecciona un horario disponible en el calendario de esta pagina. Despues de agendar, revisa tu correo para confirmar tu asistencia cuando aplique.',
      sinServicios: 'Aun no tengo una lista publica de servicios configurada para este consultorio. Puedes preguntar directamente al consultorio o revisar disponibilidad en el calendario.',
      serviciosIntro: 'Claro. Estos son los servicios configurados para este consultorio:\n\n',
      consultarPrecio: 'Consultar precio',
      descripcionServicio: 'En que consiste',
      servicioDetalleAyuda: 'Si deseas conocer en que consiste alguno, escribe el nombre del servicio.',
      seguridadMedica: 'El asistente virtual de Doko no puede dar diagnosticos, tratamientos ni recomendaciones medicas. Si presentas sintomas importantes o una urgencia, contacta directamente al consultorio o acude a servicios de emergencia.',
      confirmacion: 'La confirmacion se realiza por correo segun la politica del consultorio. Revisa tu bandeja de entrada, Spam o Correo no deseado y sigue las instrucciones para confirmar tu asistencia.',
      reagendar: 'Para cancelar o reagendar, sigue las instrucciones del correo de confirmacion. Tambien puedes volver a reservar en el calendario segun la disponibilidad del consultorio.',
      direccionVacia: 'La direccion aun no esta registrada.',
      maps: '\nTambien puedes tocar el boton "Ver ubicacion en Maps" en esta pagina.',
      ubicacion: 'La direccion del consultorio es:',
      telefono: 'El telefono del consultorio es',
      telefonoVacio: 'El telefono del consultorio aun no esta registrado en esta pagina.',
      segurosVacio: 'Las aseguradoras aceptadas no estan registradas en esta pagina. Contacta directamente al consultorio para confirmar cobertura.',
      seguros: 'Aseguradoras aceptadas:',
      segurosNoAceptados: 'Este consultorio no acepta aseguradoras por el momento. Para conocer opciones de pago, contacta directamente al consultorio.',
      pagos: 'Formas de pago aceptadas:',
      horarios: 'Horario de atenci\u00f3n del consultorio:',
      horariosVacio: 'El horario de atenci\u00f3n a\u00fan no est\u00e1 registrado. Puedes revisar disponibilidad en el calendario o contactar al consultorio.',
      aviso: 'Aviso del consultorio:',
      avisoVacio: 'No hay avisos especiales activos del consultorio por ahora.',
      pagosVacio: 'Las formas de pago aun no estan registradas. Contacta directamente al consultorio para confirmarlas.',
      tienda: 'Esta pagina es solo para pacientes y agenda de citas. No maneja tienda, insumos ni pedidos de productos.',
      fueraAlcance: 'Puedo ayudarte con servicios, costos, ubicacion, telefono y como agendar tu cita. Para otra informacion, contacta directamente al consultorio.',
      espera: 'Un momento, reviso la informacion del consultorio...',
      noEncontrado: 'No encontre esa informacion especifica.',
      placeholder: 'Escribe tu pregunta...',
      enviar: 'Enviar',
      idiomaLabel: 'Idioma del chat',
      sugerencias: [
        ['servicios', 'Servicios y costos'],
        ['agenda', 'Como agendar'],
        ['ubicacion', 'Ubicacion'],
        ['pagos', 'Formas de pago']
      ],
      labels: {
        servicios: 'Sobre servicios y costos',
        ubicacion: 'Ubicacion',
        agenda: 'Para agendar',
        telefono: 'Telefono',
        seguros: 'Seguros',
        pagos: 'Formas de pago',
        horarios: 'Horarios',
        aviso: 'Aviso del consultorio',
        faq: 'Informacion del consultorio',
        confirmacion: 'Confirmacion',
        reagendar: 'Cambios de cita',
        tienda: 'Nota'
      }
    },
    en: {
      saludo: "Hello, I am Doko's virtual assistant. I can help you with services, pricing, location, and how to book your appointment.",
      agenda: 'To book, select an available time in the calendar on this page. 24 hours before your appointment, you will receive an email to confirm your attendance.',
      sinServicios: 'I do not have a public service list configured for this office yet. You can contact the office directly or check availability in the calendar.',
      serviciosIntro: 'Of course. These are the services configured for this office:\n\n',
      consultarPrecio: 'Ask for price',
      descripcionServicio: 'What this service includes',
      servicioDetalleAyuda: 'If you would like to know what a service includes, ask me by its name.',
      seguridadMedica: "Doko's virtual assistant cannot provide diagnoses, treatments, or medical recommendations. If you have important symptoms or an emergency, contact the clinic directly or go to emergency services.",
      confirmacion: 'Confirmation is handled by email 24 hours before your appointment. Check your inbox and follow the instructions to confirm your attendance.',
      reagendar: 'To cancel or reschedule, follow the instructions in the confirmation email. You can also book again in the calendar depending on office availability.',
      direccionVacia: 'The address is not registered yet.',
      maps: '\nYou can also tap the "View location on Maps" button on this page.',
      ubicacion: 'The office address is:',
      telefono: 'The office phone number is',
      telefonoVacio: 'The office phone number is not registered on this page yet.',
      segurosVacio: 'Accepted insurance providers are not registered on this page. Please contact the clinic directly to confirm coverage.',
      seguros: 'Accepted insurance providers:',
      segurosNoAceptados: 'This office does not accept insurance providers at this time. Please contact the clinic directly for payment options.',
      pagos: 'Accepted payment methods:',
      horarios: 'Office hours:',
      horariosVacio: 'Office hours are not registered yet. You can check availability in the calendar or contact the clinic directly.',
      aviso: 'Office notice:',
      avisoVacio: 'There are no active special office notices right now.',
      pagosVacio: 'Payment methods are not registered yet. Please contact the clinic directly to confirm them.',
      tienda: 'This page is only for patients and appointment scheduling. It does not handle store, supplies, or product orders.',
      fueraAlcance: 'I can help with services, pricing, location, phone number, and how to book your appointment. For other information, please contact the clinic directly.',
      espera: 'One moment, I am checking the office information...',
      noEncontrado: 'I could not find that specific information.',
      placeholder: 'Type your question...',
      enviar: 'Send',
      idiomaLabel: 'Chat language',
      sugerencias: [
        ['services', 'Services and pricing'],
        ['book', 'How to book'],
        ['location', 'Location'],
        ['payments', 'Payment methods']
      ],
      labels: {
        servicios: 'About services and pricing',
        ubicacion: 'Location',
        agenda: 'How to book',
        telefono: 'Phone',
        seguros: 'Insurance',
        pagos: 'Payment methods',
        horarios: 'Office hours',
        aviso: 'Office notice',
        faq: 'Clinic information',
        confirmacion: 'Confirmation',
        reagendar: 'Appointment changes',
        tienda: 'Note'
      }
    }
  };

  const palabras = {
    sensible: [
      'emergencia', 'urgencia', 'urgente', 'urgent', 'emergency', 'dolor fuerte',
      'me duele', 'duele mucho', 'no puedo respirar', 'sangrado', 'sangrando',
      'bleeding', 'desmayo', 'embarazada', 'pregnant', 'fiebre', 'fever',
      'diagnostico', 'diagnose', 'diagnosis', 'diagnosticar', 'que tengo',
      'medicamento', 'medicine', 'medication', 'tratamiento', 'treatment',
      'receta', 'prescription', 'recomiendame', 'recommend'
    ],
    agenda: ['agendar', 'agendo', 'agenda', 'cita', 'appointment', 'book', 'booking', 'reservar', 'calendar', 'calendario', 'horario disponible', 'horarios disponibles', 'available', 'disponible'],
    confirmacion: ['confirmacion', 'confirmation', 'confirmar', 'confirm', 'correo', 'email', '24 horas', '24 hours', 'asistencia', 'attendance'],
    reagendar: ['cancelar', 'cancel', 'cancelo', 'reagendar', 'reschedule', 'cambiar cita', 'mover cita'],
    ubicacion: ['ubicacion', 'location', 'direccion', 'address', 'maps', 'mapa', 'llegar', 'where', 'donde', 'estan'],
    telefono: ['telefono', 'phone', 'llamar', 'call', 'contacto', 'contact', 'numero', 'number'],
    seguros: ['seguro', 'seguros', 'aseguradora', 'aseguradoras', 'insurance', 'coverage', 'cobertura'],
    pagos: ['pago', 'pagos', 'pagar', 'tarjeta', 'efectivo', 'transferencia', 'payment', 'pay', 'cash', 'card', 'credit', 'debit'],
    horarios: ['horario de atencion', 'horarios de atencion', 'horario', 'horarios', 'atencion', 'hours', 'opening hours', 'open hours'],
    aviso: ['aviso', 'avisos', 'vacaciones', 'vacation', 'cerrado', 'closed', 'cierre', 'ausente', 'descanso', 'holiday', 'notice'],
    tienda: ['tienda', 'store', 'insumo', 'supplies', 'insumos', 'producto', 'product', 'pedido', 'order', 'catalogo', 'catalog', 'whatsapp', 'warehouse', 'bodega'],
    servicios: ['servicio', 'servicios', 'service', 'services', 'precio', 'precios', 'price', 'pricing', 'cost', 'costo', 'cuesta', 'cuanto', 'ofrecen', 'offer', 'included', 'include', 'how much', 'consulta'],
    fueraAlcance: ['redes neuronales', 'neural networks', 'programacion', 'programming', 'politica', 'politics', 'crypto', 'bitcoin']
  };

  const ordenIntenciones = ['aviso', 'servicios', 'pagos', 'ubicacion', 'horarios', 'agenda', 'telefono', 'seguros', 'confirmacion', 'reagendar', 'tienda'];

  function t(clave, lang) {
    const langActivo = lang || idioma;
    return (textos[langActivo] && textos[langActivo][clave]) || textos.es[clave] || '';
  }

  function respuestaConfirmacion(lang) {
    const modo = doctor.modo_confirmacion || 'manual';
    if (modo === 'confirmar_48h_cancelar_24h') {
      return lang === 'en'
        ? 'You will receive a confirmation email 48 hours before your appointment. You have until 24 hours before the appointment to confirm; unconfirmed time slots may be released.'
        : 'Recibiras un correo de confirmacion 48 horas antes de tu cita. Tendras hasta 24 horas antes para confirmar; los horarios sin confirmar pueden liberarse.';
    }
    if (modo === 'confirmar_24h') {
      return lang === 'en'
        ? 'You will receive a confirmation email 24 hours before your appointment. The appointment is not cancelled automatically if you do not respond.'
        : 'Recibiras un correo de confirmacion 24 horas antes de tu cita. La cita no se cancela automaticamente si no respondes.';
    }
    return lang === 'en'
      ? 'You may receive a confirmation email before your appointment. Please follow the instructions in the message or contact the clinic directly.'
      : 'Podras recibir un correo de confirmacion antes de tu cita. Sigue sus instrucciones o contacta directamente al consultorio.';
  }

  function respuestaAgenda(lang) {
    const inicio = lang === 'en'
      ? 'To book, select an available time in the calendar on this page.'
      : 'Para reservar, selecciona un horario disponible en el calendario de esta pagina.';
    return `${inicio} ${respuestaConfirmacion(lang)}`;
  }

  const correccionesComunes = {
    ola: 'hola', presio: 'precio', presios: 'precios', prezio: 'precio',
    servisio: 'servicio', servisios: 'servicios', servicioz: 'servicios',
    ubicasion: 'ubicacion', direcion: 'direccion', direcsion: 'direccion',
    agendarr: 'agendar', reserbar: 'reservar', horaro: 'horario', horaio: 'horario',
    aseguranza: 'aseguradora', aseguransa: 'aseguradora',
    servise: 'service', servces: 'services', prce: 'price', whre: 'where',
    wher: 'where', adress: 'address', apointment: 'appointment',
    appointmet: 'appointment', schedual: 'schedule', calender: 'calendar',
    insurence: 'insurance', paymant: 'payment', pament: 'payment',
    confermation: 'confirmation', cancell: 'cancel'
  };

  function normalizar(texto) {
    const limpio = String(texto || '').toLowerCase().normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
    return limpio.split(' ').map(palabra => correccionesComunes[palabra] || palabra).join(' ');
  }

  function tiene(texto, lista) {
    return lista.some(p => texto.includes(normalizar(p)));
  }

  function clavesFaq(faq) {
    if (Array.isArray(faq.palabras_clave)) return faq.palabras_clave;
    return String(faq.palabras_clave || '').split(',').map(s => s.trim()).filter(Boolean);
  }

  function precioServicio(servicio, lang) {
    if (servicio.tipo_precio === 'segun_valoracion') {
      return lang === 'en' ? 'Price depends on medical evaluation.' : 'Precio segun valoracion medica.';
    }
    if (servicio.tipo_precio === 'costo_durante_consulta') {
      return lang === 'en' ? 'Final cost is determined during the consultation.' : 'Costo final determinado durante la consulta.';
    }
    return servicio.precio
      ? `$${Number(servicio.precio).toLocaleString(lang === 'en' ? 'en-US' : 'es-MX')}`
      : t('consultarPrecio', lang);
  }

  function limpiarFormatoRespuesta(texto) {
    // FAQs y Gemini pueden usar Markdown. El chat es texto plano y no debe
    // Evita mostrar asteriscos ni encabezados tecnicos al paciente.
    return String(texto || '')
      .replace(/^\s{0,3}#{1,6}\s*/gm, '')
      .replace(/\*\*([^*]+)\*\*/g, '$1')
      .replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, '$1')
      .replace(/^\s*[-*]\s+/gm, '- ')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }

  function textoServicio(servicio) {
    return normalizar(`${servicio.nombre_servicio || ''} ${servicio.descripcion || ''}`);
  }

  function tokensServicio(servicio) {
    return normalizar(servicio.nombre_servicio || '').split(' ').filter(token => token.length >= 4);
  }

  function buscarServicioEspecifico(texto) {
    const servicios = data.servicios || [];
    let mejor = null;
    let mejorScore = 0;

    servicios.forEach((servicio, idx) => {
      const nombre = normalizar(servicio.nombre_servicio || '');
      const textoCompleto = textoServicio(servicio);
      const tokensNombre = tokensServicio(servicio);
      const tokensUsuario = texto.split(' ').filter(token => token.length >= 4);
      let score = 0;

      if (nombre && texto.includes(nombre)) score += 100;

      tokensNombre.forEach(token => {
        if (texto.includes(token)) score += 20;
      });

      tokensUsuario.forEach(token => {
        if (textoCompleto.includes(token)) score += 4;
      });

      if (score > mejorScore) {
        mejor = { servicio, idx };
        mejorScore = score;
      }
    });

    return mejorScore >= 24 ? mejor : null;
  }

  function construirServicioDetalle(servicio, lang) {
    const nombre = servicio.nombre_servicio || (lang === 'en' ? 'Service' : 'Servicio');
    const precio = precioServicio(servicio, lang);
    const etiquetaPrecio = lang === 'en' ? 'Price' : 'Precio';
    const partes = [
      nombre,
      `${etiquetaPrecio}\n${precio}`
    ];
    if (servicio.descripcion) {
      partes.push(`${t('descripcionServicio', lang)}\n${servicio.descripcion}`);
    }
    return partes.join('\n\n');
  }

  function construirServicios(lang) {
    const servicios = data.servicios || [];
    if (!servicios.length) return t('sinServicios', lang);

    let respuesta = t('serviciosIntro', lang);
    servicios.forEach(servicio => {
      respuesta += `${servicio.nombre_servicio || 'Servicio'}\n`;
      respuesta += `${lang === 'en' ? 'Price' : 'Precio'}: ${precioServicio(servicio, lang)}\n\n`;
    });
    respuesta += t('servicioDetalleAyuda', lang);
    return respuesta;
  }

  function respuestaUbicacion(lang) {
    const direccion = doctor.direccion_consultorio || t('direccionVacia', lang);
    const maps = doctor.maps_url ? t('maps', lang) : '';
    return `\u{1F4CD} ${t('ubicacion', lang)} ${direccion}.${maps}`;
  }

  function respuestaTelefono(lang) {
    return doctor.telefono_consultorio ? `${t('telefono', lang)} ${doctor.telefono_consultorio}.` : t('telefonoVacio', lang);
  }

  function respuestaSeguros(lang) {
    const seguros = doctor.aseguradoras_aceptadas;
    const segurosNormalizados = normalizar(seguros);
    if (segurosNormalizados === 'no acepta aseguradoras' || segurosNormalizados === 'no acepto aseguradoras') {
      return t('segurosNoAceptados', lang);
    }
    return seguros ? `${t('seguros', lang)} ${seguros}.` : t('segurosVacio', lang);
  }

  function respuestaPagos(lang) {
    const metodos = doctor.metodos_pago_aceptados;
    return metodos ? `\u{1F4B3} ${t('pagos', lang)} ${metodos}.` : `\u{1F4B3} ${t('pagosVacio', lang)}`;
  }

  function respuestaHorarios(lang) {
    const horarios = doctor.horarios_atencion;
    return horarios ? `\u{1F4C5} ${t('horarios', lang)} ${horarios}.` : `\u{1F4C5} ${t('horariosVacio', lang)}`;
  }

  function respuestaAviso(lang) {
    const aviso = doctor.aviso_activo ? doctor.aviso_consultorio : '';
    return aviso ? `${t('aviso', lang)} ${aviso}` : t('avisoVacio', lang);
  }

  function agregarIntencion(mapa, id, textoEs, textoActual, requiereTraduccion) {
    if (mapa.has(id)) return;
    mapa.set(id, {
      id,
      textoEs,
      texto: textoActual,
      requiereTraduccion: !!requiereTraduccion
    });
  }

  function temaFaq(claves) {
    const textoClaves = normalizar(claves.join(' '));
    for (const id of ordenIntenciones) {
      if (palabras[id] && tiene(textoClaves, palabras[id])) return id;
    }
    return null;
  }

  function detectarIntenciones(mensajeUsuario) {
    const texto = normalizar(mensajeUsuario);
    const mapa = new Map();

    if (tiene(texto, palabras.sensible)) {
      return {
        sensible: true,
        intenciones: [{
          id: 'seguridad_medica',
          texto: t('seguridadMedica'),
          textoEs: t('seguridadMedica', 'es'),
          requiereTraduccion: false
        }]
      };
    }

    const servicioEspecifico = buscarServicioEspecifico(texto);
    if (servicioEspecifico) {
      agregarIntencion(
        mapa,
        `servicio_${servicioEspecifico.idx}`,
        construirServicioDetalle(servicioEspecifico.servicio, 'es'),
        construirServicioDetalle(servicioEspecifico.servicio, idioma),
        idioma === 'en'
      );
    } else if (tiene(texto, palabras.servicios)) {
      agregarIntencion(mapa, 'servicios', construirServicios('es'), construirServicios(idioma), idioma === 'en');
    }

    if (tiene(texto, palabras.ubicacion)) {
      agregarIntencion(mapa, 'ubicacion', respuestaUbicacion('es'), respuestaUbicacion(idioma), false);
    }
    if (tiene(texto, palabras.agenda)) {
      agregarIntencion(mapa, 'agenda', respuestaAgenda('es'), respuestaAgenda(idioma), false);
    }
    if (tiene(texto, palabras.telefono)) {
      agregarIntencion(mapa, 'telefono', respuestaTelefono('es'), respuestaTelefono(idioma), false);
    }
    if (tiene(texto, palabras.seguros)) {
      agregarIntencion(mapa, 'seguros', respuestaSeguros('es'), respuestaSeguros(idioma), false);
    }
    if (tiene(texto, palabras.pagos)) {
      agregarIntencion(mapa, 'pagos', respuestaPagos('es'), respuestaPagos(idioma), false);
    }
    if (tiene(texto, palabras.horarios)) {
      agregarIntencion(mapa, 'horarios', respuestaHorarios('es'), respuestaHorarios(idioma), false);
    }
    if (tiene(texto, palabras.aviso)) {
      agregarIntencion(mapa, 'aviso', respuestaAviso('es'), respuestaAviso(idioma), idioma === 'en');
    }
    if (tiene(texto, palabras.confirmacion)) {
      agregarIntencion(mapa, 'confirmacion', respuestaConfirmacion('es'), respuestaConfirmacion(idioma), false);
    }
    if (tiene(texto, palabras.reagendar)) {
      agregarIntencion(mapa, 'reagendar', t('reagendar', 'es'), t('reagendar'), false);
    }
    if (tiene(texto, palabras.tienda)) {
      agregarIntencion(mapa, 'tienda', t('tienda', 'es'), t('tienda'), false);
    }

    (data.faqs || []).forEach((faq, idx) => {
      const claves = clavesFaq(faq);
      const coincide = claves.some(clave => {
        const claveNorm = normalizar(clave);
        return claveNorm && texto.includes(claveNorm);
      });
      if (!coincide) return;

      const tema = temaFaq(claves);
      if (tema && mapa.has(tema)) return;
      agregarIntencion(mapa, `faq_${idx}`, faq.respuesta, faq.respuesta, idioma === 'en');
    });

    if (!mapa.size && tiene(texto, palabras.fueraAlcance)) {
      agregarIntencion(mapa, 'fuera_alcance', t('fueraAlcance', 'es'), t('fueraAlcance'), false);
    }

    return { sensible: false, intenciones: Array.from(mapa.values()) };
  }

  function ordenarIntenciones(intenciones) {
    return intenciones.slice().sort((a, b) => {
      const idA = a.id.startsWith('servicio_') ? 'servicios' : a.id;
      const idB = b.id.startsWith('servicio_') ? 'servicios' : b.id;
      const ia = ordenIntenciones.includes(idA) ? ordenIntenciones.indexOf(idA) : 99;
      const ib = ordenIntenciones.includes(idB) ? ordenIntenciones.indexOf(idB) : 99;
      return ia - ib;
    });
  }

  function etiquetaIntento(id, lang) {
    const base = id.startsWith('faq_') ? 'faq' : id.startsWith('servicio_') ? 'servicios' : id;
    return (textos[lang] && textos[lang].labels && textos[lang].labels[base]) || textos.es.labels[base] || 'Info';
  }

  function combinarIntenciones(intenciones, lang, usarTextoEs) {
    const ordenadas = ordenarIntenciones(intenciones);
    if (ordenadas.length === 1) return usarTextoEs ? ordenadas[0].textoEs : ordenadas[0].texto;

    return ordenadas.map(item => {
      const texto = usarTextoEs ? item.textoEs : item.texto;
      return `${etiquetaIntento(item.id, lang)}: ${texto}`;
    }).join('\n\n');
  }

  function respuestaControlada(mensajeUsuario) {
    const resultado = detectarIntenciones(mensajeUsuario);
    const intenciones = resultado.intenciones;

    if (resultado.sensible) {
      return { tipo: 'local', texto: intenciones[0].texto };
    }

    if (!intenciones.length) {
      return { tipo: 'respaldo' };
    }

    const requiereTraduccion = idioma === 'en' && intenciones.some(item => item.requiereTraduccion);
    if (requiereTraduccion) {
      return {
        tipo: 'traducir',
        textoFuente: combinarIntenciones(intenciones, 'es', true)
      };
    }

    return {
      tipo: 'local',
      texto: combinarIntenciones(intenciones, idioma, false)
    };
  }

  async function consultarServidor(pregunta, modo, textoFuente) {
    if (!idPublico) return null;
    try {
      const res = await fetch(`/p/${idPublico}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pregunta,
          idioma,
          modo,
          texto_fuente: textoFuente || ''
        })
      });
      const payload = await res.json();
      return payload.respuesta || null;
    } catch {
      return null;
    }
  }

  function agregarMensaje(texto, origen) {
    const burbuja = document.createElement('div');
    burbuja.className = `chat-burbuja chat-${origen}`;
    burbuja.textContent = limpiarFormatoRespuesta(texto);
    chatWindow.appendChild(burbuja);
    chatWindow.scrollTop = chatWindow.scrollHeight;
    return burbuja;
  }

  function abrirChat() {
    chatContainer.classList.add('chat-abierto');
    if (chatPreview) chatPreview.style.display = 'none';
    setTimeout(() => chatInput.focus(), 80);
  }

  function cerrarChat() {
    chatContainer.classList.remove('chat-abierto');
    if (chatPreview) chatPreview.style.display = 'none';
  }

  function aplicarPreferenciasLauncher() {
    document.body.classList.toggle('chat-hidden', chatHidden);
  }

  function activarLauncher() {
    document.body.classList.remove('chat-idle');
    window.clearTimeout(idleTimer);
    if (chatContainer.classList.contains('chat-abierto')) return;
    idleTimer = window.setTimeout(() => {
      if (!chatContainer.classList.contains('chat-abierto') && !chatHidden) {
        document.body.classList.add('chat-idle');
      }
    }, 7000);
  }

  function mostrarLauncher() {
    chatHidden = false;
    localStorage.removeItem('doko_chat_hidden');
    aplicarPreferenciasLauncher();
    activarLauncher();
  }

  function aplicarIdioma(nuevoIdioma, agregarAviso) {
    idioma = nuevoIdioma === 'en' ? 'en' : 'es';
    localStorage.setItem('doko_chat_lang', idioma);
    chatInput.placeholder = t('placeholder');
    const submitBtn = chatForm.querySelector('button[type="submit"]');
    if (submitBtn) submitBtn.textContent = t('enviar');
    if (chatPreview) chatPreview.textContent = t('saludo');
    renderSugerencias();
    if (agregarAviso) agregarMensaje(t('saludo'), 'bot');
  }

  async function preguntarRapido(texto) {
    abrirChat();
    chatInput.value = texto;
    chatForm.requestSubmit();
  }

  function renderSugerencias() {
    if (!chatSuggestions) return;
    const opciones = (textos[idioma] && textos[idioma].sugerencias) || textos.es.sugerencias;
    chatSuggestions.innerHTML = '';
    opciones.forEach(([pregunta, etiqueta]) => {
      const boton = document.createElement('button');
      boton.type = 'button';
      boton.className = 'chat-suggestion';
      boton.textContent = etiqueta;
      boton.addEventListener('click', () => preguntarRapido(pregunta));
      chatSuggestions.appendChild(boton);
    });
  }

  function crearSelectorIdioma() {
    const header = document.querySelector('.chat-header');
    if (!header || document.getElementById('chat-language')) return;

    const selector = document.createElement('select');
    selector.id = 'chat-language';
    selector.setAttribute('aria-label', t('idiomaLabel'));
    selector.innerHTML = '<option value="es">Espanol</option><option value="en">English</option>';
    selector.value = idioma;
    selector.addEventListener('change', () => aplicarIdioma(selector.value, true));
    header.insertBefore(selector, chatClose || null);
  }

  chatForm.addEventListener('submit', async function (e) {
    e.preventDefault();
    const mensaje = chatInput.value.trim();
    if (!mensaje) return;
    agregarMensaje(mensaje, 'usuario');
    chatInput.value = '';
    chatInput.disabled = true;

    const decision = respuestaControlada(mensaje);
    if (decision.tipo === 'local') {
      setTimeout(() => {
        agregarMensaje(decision.texto, 'bot');
        chatInput.disabled = false;
        chatInput.focus();
      }, 220);
      return;
    }

    const espera = agregarMensaje(t('espera'), 'bot');
    const servidor = await consultarServidor(mensaje, decision.tipo, decision.textoFuente);
    espera.remove();
    agregarMensaje(servidor || `${t('noEncontrado')} ${respuestaAgenda()}`, 'bot');
    chatInput.disabled = false;
    chatInput.focus();
  });

  if (chatToggle) chatToggle.addEventListener('click', abrirChat);
  if (chatClose) chatClose.addEventListener('click', cerrarChat);
  if (chatShow) chatShow.addEventListener('click', mostrarLauncher);
  ['scroll', 'mousemove', 'touchstart', 'keydown'].forEach((eventName) => {
    window.addEventListener(eventName, activarLauncher, {passive: true});
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && chatContainer.classList.contains('chat-abierto')) {
      cerrarChat();
    }
  });

  crearSelectorIdioma();
  aplicarPreferenciasLauncher();
  activarLauncher();
  aplicarIdioma(idioma, false);
  agregarMensaje(t('saludo'), 'bot');

  setTimeout(() => {
    if (chatPreview && !chatContainer.classList.contains('chat-abierto')) {
      chatPreview.style.display = 'none';
    }
  }, 6500);
})();
