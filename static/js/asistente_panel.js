(function () {
  const assistantView = document.getElementById('asistente-section');
  const messages = document.getElementById('panel-assistant-messages');
  const suggestions = document.getElementById('panel-assistant-suggestions');
  const form = document.getElementById('panel-assistant-form');
  const input = document.getElementById('panel-assistant-input');
  const send = document.getElementById('panel-assistant-send');
  const contextBanner = document.getElementById('panel-assistant-context');
  if (!assistantView || !messages || !suggestions || !form || !input || !send || !contextBanner) return;

  const generalQuickQuestions = [
    ['¿Cuándo se envía el correo?', 'Correo'],
    ['¿Cuál es la diferencia entre cita, bloqueo y apartado?', 'Tipos de evento'],
    ['¿Quién viene mañana?', 'Buscar cita'],
    ['¿Qué necesita la conexión con Google?', 'Google'],
  ];
  const contextualQuickQuestions = [
    ['¿Está confirmada esta cita?', 'Estado'],
    ['¿Cuándo se envía el correo de esta cita?', 'Correo'],
    ['¿Qué puedo hacer con esta cita?', 'Acciones'],
    ['¿De dónde salió esta cita?', 'Origen'],
  ];

  let appointmentId = null;
  let pending = false;
  let idleTimer = null;
  let previousViewId = 'agenda-section';
  let suspendedAgendaModal = false;

  function config() {
    return window.DOKO_PANEL_ASSISTANT_CONFIG || {};
  }

  function showView(targetId) {
    if (typeof config().showView === 'function') {
      config().showView(targetId);
      return;
    }
    document.querySelectorAll('.panel-view').forEach((section) => {
      section.classList.toggle('active', section.id === targetId);
    });
  }

  function getActiveOperationalView() {
    const active = document.querySelector('.panel-view.active:not(#asistente-section)');
    return active?.id || previousViewId || 'agenda-section';
  }

  function addMessage(text, role) {
    const bubble = document.createElement('div');
    bubble.className = `panel-assistant-message ${role}`;
    bubble.textContent = String(text || '');
    messages.appendChild(bubble);
    messages.scrollTop = messages.scrollHeight;
    return bubble;
  }

  function renderExplanation(bubble, explanation, fallback) {
    bubble.textContent = fallback || explanation?.detectado || '';
  }

  function formatDateOption(value) {
    const parts = String(value || '').split('-').map(Number);
    if (parts.length !== 3 || parts.some((part) => !Number.isFinite(part))) return String(value || '');
    const date = new Date(parts[0], parts[1] - 1, parts[2]);
    return new Intl.DateTimeFormat('es-MX', {
      weekday: 'short',
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    }).format(date);
  }

  function renderDateOptions(bubble, options, originalAction) {
    bubble.textContent = '';
    const intro = document.createElement('span');
    intro.textContent = 'Encontré ese día en varios meses. Elige cuál quieres consultar:';
    const list = document.createElement('div');
    list.className = 'panel-assistant-date-options';
    options.forEach((option) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'panel-assistant-date-option';
      button.textContent = `${formatDateOption(option.fecha)} (${Number(option.total || 0)})`;
      button.addEventListener('click', async () => {
        if (pending) return;
        pending = true;
        button.disabled = true;
        try {
          await executeSearchAction({
            ...originalAction,
            fecha: option.fecha,
            dia_mes: null,
          }, bubble);
        } catch (error) {
          bubble.textContent = error.message || 'No pude abrir esa fecha en la agenda.';
        } finally {
          pending = false;
          button.disabled = false;
        }
      });
      list.appendChild(button);
    });
    bubble.append(intro, list);
  }

  async function executeSearchAction(action, bubble) {
    if (typeof config().searchAgenda !== 'function') {
      throw new Error('La búsqueda de agenda no está disponible en esta versión del panel.');
    }
    const result = await config().searchAgenda(action);
    if (result?.tipo === 'opciones_fecha') {
      renderDateOptions(bubble, result.opciones || [], action);
      return;
    }
    const total = Number(result?.total || 0);
    bubble.textContent = total
      ? `Encontré ${total} resultado${total === 1 ? '' : 's'}. Los abrí en la agenda y resalté el siguiente vigente.`
      : 'No encontré coincidencias en el periodo consultado. Puedes limpiar la búsqueda o probar otro dato.';
    navigateTo('agenda-section');
  }

  function greeting() {
    const doctorName = config().getDoctorName?.() || 'este consultorio';
    return `Puedo orientarte sobre el uso de Doko para ${doctorName}: citas, correos, confirmaciones, bloqueos, apartados, perfil y Suffy.`;
  }

  function resetMessages() {
    messages.innerHTML = '';
    addMessage(greeting(), 'bot');
  }

  function renderAppointmentContext() {
    contextBanner.classList.toggle('visible', Boolean(appointmentId || suspendedAgendaModal));
    contextBanner.replaceChildren();
    if (!appointmentId && !suspendedAgendaModal) return;

    const copy = document.createElement('div');
    copy.className = 'panel-assistant-context-copy';
    const title = document.createElement('strong');
    title.textContent = appointmentId ? 'Cita seleccionada' : 'Edición pausada';
    const detail = document.createElement('span');
    detail.textContent = appointmentId
      ? 'Solo se consulta su estado operativo. Los datos del paciente no se envían a Gemini.'
      : 'Tus cambios siguen en el formulario y todavía no se han guardado.';
    copy.append(title, detail);

    const actions = document.createElement('div');
    actions.className = 'panel-assistant-context-actions';
    if (appointmentId) {
      const clear = document.createElement('button');
      clear.type = 'button';
      clear.className = 'panel-assistant-context-clear';
      clear.textContent = 'Consulta general';
      clear.addEventListener('click', () => {
        setAppointmentContext(null);
        input.focus();
      });
      actions.appendChild(clear);
    }
    if (suspendedAgendaModal) {
      const returnButton = document.createElement('button');
      returnButton.type = 'button';
      returnButton.className = 'panel-assistant-context-return';
      returnButton.textContent = 'Volver a la cita';
      returnButton.addEventListener('click', close);
      actions.appendChild(returnButton);
    }
    contextBanner.append(copy, actions);
  }

  function setAppointmentContext(idRadar) {
    appointmentId = idRadar || null;
    renderAppointmentContext();
    renderSuggestions();
  }

  function getInterfaceContext() {
    if (suspendedAgendaModal) return appointmentId ? 'editar_cita' : 'crear_evento';
    return appointmentId ? 'cita_seleccionada' : 'modulo_asistente';
  }

  function suspendAgendaModal() {
    const modal = document.getElementById('agenda-event-modal');
    if (!modal?.classList.contains('open')) return false;
    modal.classList.add('assistant-paused');
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('agenda-modal-open');
    suspendedAgendaModal = true;
    renderAppointmentContext();
    return true;
  }

  function restoreAgendaModal() {
    const modal = document.getElementById('agenda-event-modal');
    if (!suspendedAgendaModal || !modal?.classList.contains('open')) return false;
    showView('agenda-section');
    previousViewId = 'agenda-section';
    modal.classList.remove('assistant-paused');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('agenda-modal-open');
    suspendedAgendaModal = false;
    renderAppointmentContext();
    window.setTimeout(() => document.getElementById('agenda-assistant-help')?.focus(), 40);
    return true;
  }

  function open(options = {}) {
    const currentView = getActiveOperationalView();
    if (currentView !== 'asistente-section') previousViewId = currentView;
    if (Object.prototype.hasOwnProperty.call(options, 'idRadar')) {
      setAppointmentContext(options.idRadar);
    }
    suspendAgendaModal();
    showView('asistente-section');
    document.body.classList.add('panel-assistant-open');
    document.body.classList.remove('panel-assistant-idle');
    assistantView.setAttribute('aria-hidden', 'false');
    window.setTimeout(() => input.focus(), 60);
    if (options.pregunta) ask(options.pregunta);
  }

  function close() {
    document.body.classList.remove('panel-assistant-open');
    assistantView.setAttribute('aria-hidden', 'true');
    if (!restoreAgendaModal()) {
      showView(previousViewId || 'agenda-section');
    }
    activateLauncher();
  }

  function navigateTo(targetId) {
    if (targetId === 'asistente-section') {
      open();
      return;
    }
    if (suspendedAgendaModal) {
      close();
      return;
    }
    previousViewId = targetId || 'agenda-section';
    document.body.classList.remove('panel-assistant-open');
    assistantView.setAttribute('aria-hidden', 'true');
    showView(previousViewId);
    activateLauncher();
  }

  function reset() {
    const modal = document.getElementById('agenda-event-modal');
    if (modal?.classList.contains('assistant-paused')) {
      modal.classList.remove('assistant-paused', 'open');
      modal.setAttribute('aria-hidden', 'true');
    }
    suspendedAgendaModal = false;
    appointmentId = null;
    previousViewId = 'agenda-section';
    document.body.classList.remove('panel-assistant-open', 'agenda-modal-open');
    assistantView.setAttribute('aria-hidden', 'true');
    renderAppointmentContext();
    showView('agenda-section');
    resetMessages();
    activateLauncher();
  }

  async function ask(question) {
    const text = String(question || '').trim();
    if (!text || pending) return;
    const token = config().getToken?.();
    if (!token) {
      addMessage('La sesión del panel no está disponible. Vuelve a entrar al consultorio.', 'bot');
      return;
    }

    addMessage(text, 'user');
    input.value = '';
    pending = true;
    input.disabled = true;
    send.disabled = true;
    const waiting = addMessage('Revisando el flujo de Doko...', 'bot');

    try {
      const response = await fetch(`${config().baseUrl || ''}/panel/asistente`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          pregunta: text,
          id_radar: appointmentId || null,
          contexto_interfaz: getInterfaceContext(),
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || 'No pude revisar esa pregunta.');
      renderExplanation(waiting, data.explicacion, data.respuesta);
      if (data.accion_ui?.tipo === 'buscar_agenda') {
        await executeSearchAction(data.accion_ui, waiting);
      }
    } catch (error) {
      waiting.textContent = error.message || 'No pude consultar la guía de Doko en este momento.';
    } finally {
      pending = false;
      input.disabled = false;
      send.disabled = false;
      input.focus();
      messages.scrollTop = messages.scrollHeight;
    }
  }

  function renderSuggestions() {
    suggestions.innerHTML = '';
    const questions = appointmentId ? contextualQuickQuestions : generalQuickQuestions;
    questions.forEach(([question, label]) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'panel-assistant-suggestion';
      button.textContent = label;
      button.addEventListener('click', () => ask(question));
      suggestions.appendChild(button);
    });
  }

  function activateLauncher() {
    document.body.classList.remove('panel-assistant-idle');
    window.clearTimeout(idleTimer);
    idleTimer = window.setTimeout(() => {
      if (!document.body.classList.contains('panel-assistant-open')) {
        document.body.classList.add('panel-assistant-idle');
      }
    }, 7500);
  }

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    ask(input.value);
  });
  ['scroll', 'mousemove', 'touchstart', 'keydown'].forEach((eventName) => {
    window.addEventListener(eventName, activateLauncher, { passive: true });
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && document.body.classList.contains('panel-assistant-open')) close();
  });
  document.addEventListener('doko:doctor-context', reset);

  renderSuggestions();
  resetMessages();
  activateLauncher();

  window.DokoPanelAssistant = {
    open,
    close,
    reset,
    ask,
    navigateTo,
    setAppointmentContext,
  };
})();
