(function () {
    'use strict';

    const notify = (message, type = 'info') => {
        if (window.dokoNotificar) window.dokoNotificar(message, type);
    };

    async function requestJson(url, options = {}) {
        const response = await fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                ...(options.headers || {}),
            },
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || payload.ok === false) {
            throw new Error(payload.error || `No fue posible completar la accion (${response.status}).`);
        }
        return payload;
    }

    function initCreate() {
        const panel = document.getElementById('implementation-create');
        const open = document.getElementById('implementation-new-toggle');
        const close = document.getElementById('implementation-new-close');
        const cancel = document.getElementById('implementation-create-cancel');
        const submit = document.getElementById('implementation-create-submit');
        const doctor = document.getElementById('implementation-doctor');
        const assistant = document.getElementById('implementation-assistant');
        const type = document.getElementById('implementation-type');
        if (!panel || !open || !doctor || !assistant || !type || !submit) return;

        const hide = () => { panel.hidden = true; };
        const show = () => {
            panel.hidden = false;
            panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
            doctor.focus();
        };
        const filterAssistants = () => {
            const selectedDoctor = doctor.value;
            assistant.value = '';
            Array.from(assistant.options).forEach((option, index) => {
                if (index === 0) return;
                option.hidden = option.dataset.doctor !== selectedDoctor;
            });
        };

        open.addEventListener('click', show);
        close?.addEventListener('click', hide);
        cancel?.addEventListener('click', hide);
        doctor.addEventListener('change', filterAssistants);
        submit.addEventListener('click', async () => {
            if (!doctor.value) {
                notify('Selecciona una doctora.', 'error');
                doctor.focus();
                return;
            }
            submit.disabled = true;
            submit.textContent = 'Creando...';
            try {
                const data = await requestJson('/admin/doctores/implementacion', {
                    method: 'POST',
                    body: JSON.stringify({
                        correo_doctor: doctor.value,
                        id_usuario_asistente: assistant.value || null,
                        tipo: type.value,
                    }),
                });
                window.location.assign(data.url);
            } catch (error) {
                notify(error.message, 'error');
                submit.disabled = false;
                submit.textContent = 'Crear borrador';
            }
        });
    }

    function initEditor() {
        const editor = document.querySelector('.implementation-editor');
        if (!editor) return;
        const evaluationId = editor.dataset.evaluationId;
        const baseUrl = `/admin/doctores/implementacion/${evaluationId}`;
        const sectionSelect = document.getElementById('implementation-section-select');
        const sectionButtons = Array.from(document.querySelectorAll('[data-section-target]'));
        const sectionPanels = Array.from(document.querySelectorAll('[data-section-panel]'));

        async function saveMetadata(extra = {}) {
            return requestJson(baseUrl, {
                method: 'PATCH',
                body: JSON.stringify(extra),
            });
        }

        function showSection(section, persist = true) {
            if (!sectionPanels.some((panel) => panel.dataset.sectionPanel === section)) return;
            sectionPanels.forEach((panel) => { panel.hidden = panel.dataset.sectionPanel !== section; });
            sectionButtons.forEach((button) => button.classList.toggle('is-active', button.dataset.sectionTarget === section));
            if (sectionSelect) sectionSelect.value = section;
            editor.dataset.currentSection = section;
            window.scrollTo({ top: 0, behavior: 'smooth' });
            if (persist) saveMetadata({ seccion_actual: section }).catch((error) => notify(error.message, 'error'));
        }

        sectionButtons.forEach((button) => button.addEventListener('click', () => showSection(button.dataset.sectionTarget)));
        sectionSelect?.addEventListener('change', () => showSection(sectionSelect.value));

        const editType = document.getElementById('implementation-edit-type');
        const editAssistant = document.getElementById('implementation-edit-assistant');
        editType?.addEventListener('change', async () => {
            try {
                await saveMetadata({ tipo: editType.value });
                notify('Tipo de implementacion actualizado.', 'success');
            } catch (error) {
                notify(error.message, 'error');
                window.location.reload();
            }
        });
        editAssistant?.addEventListener('change', async () => {
            try {
                await saveMetadata({ id_usuario_asistente: editAssistant.value || null });
                notify('Asistente vinculada. Actualizando escenarios...', 'success');
                window.location.reload();
            } catch (error) {
                notify(error.message, 'error');
                window.location.reload();
            }
        });

        document.querySelectorAll('[data-question-deck]').forEach((deck) => {
            const cards = Array.from(deck.querySelectorAll('[data-question-card]'));
            let activeIndex = Math.max(0, cards.findIndex((card) => !card.hidden));

            const showQuestion = (index) => {
                if (!cards.length) return;
                activeIndex = Math.max(0, Math.min(index, cards.length - 1));
                cards.forEach((card, cardIndex) => { card.hidden = cardIndex !== activeIndex; });
                cards[activeIndex].querySelector('[data-answer-text]')?.focus();
            };

            cards.forEach((card, index) => {
                card.querySelector('[data-question-prev]')?.addEventListener('click', () => showQuestion(index - 1));
                card.querySelector('[data-question-save]')?.addEventListener('click', async (event) => {
                    const button = event.currentTarget;
                    const text = card.querySelector('[data-answer-text]')?.value.trim() || '';
                    const option = card.querySelector('[data-answer-option]')?.value || '';
                    if (!text && !option) {
                        notify('Escribe una respuesta antes de continuar.', 'error');
                        return;
                    }
                    button.disabled = true;
                    const original = button.textContent;
                    button.textContent = 'Guardando...';
                    try {
                        await requestJson(`${baseUrl}/respuesta`, {
                            method: 'PATCH',
                            body: JSON.stringify({
                                codigo_pregunta: card.dataset.questionCode,
                                opcion: option || null,
                                respuesta_texto: text || null,
                            }),
                        });
                        let saved = card.querySelector('.implementation-saved');
                        if (!saved) {
                            saved = document.createElement('span');
                            saved.className = 'implementation-saved';
                            saved.textContent = 'Guardada';
                            card.querySelector('.implementation-question-progress')?.appendChild(saved);
                        }
                        notify('Respuesta guardada.', 'success');
                        if (index < cards.length - 1) showQuestion(index + 1);
                    } catch (error) {
                        notify(error.message, 'error');
                    } finally {
                        button.disabled = false;
                        button.textContent = original;
                    }
                });
            });
        });

        document.querySelectorAll('[data-protocol-id]').forEach((card) => {
            const decision = card.querySelector('[data-protocol-decision]');
            const adaptationField = card.querySelector('[data-adaptation-field]');
            const adaptation = card.querySelector('[data-protocol-adaptation]');
            const save = card.querySelector('[data-protocol-save]');
            const syncVisibility = () => { adaptationField.hidden = decision.value !== 'ADAPTAR'; };
            decision.addEventListener('change', syncVisibility);
            save.addEventListener('click', async () => {
                if (decision.value === 'ADAPTAR' && !adaptation.value.trim()) {
                    notify('Describe la adaptacion del consultorio.', 'error');
                    adaptation.focus();
                    return;
                }
                save.disabled = true;
                try {
                    await requestJson(`${baseUrl}/protocolo/${card.dataset.protocolId}`, {
                        method: 'POST',
                        body: JSON.stringify({
                            decision: decision.value,
                            adaptacion_texto: adaptation.value.trim() || null,
                        }),
                    });
                    notify('Decision guardada. Requiere aprobacion de la doctora.', 'success');
                } catch (error) {
                    notify(error.message, 'error');
                } finally {
                    save.disabled = false;
                }
            });
        });

        function buildFinding(item) {
            const block = document.createElement('div');
            block.className = `implementation-finding implementation-finding--${item.tipo || 'aclarar'}`;
            const title = document.createElement('strong');
            title.textContent = item.titulo || 'Hallazgo';
            const detail = document.createElement('p');
            detail.textContent = item.detalle || '';
            block.append(title, detail);
            return block;
        }

        function appendSuggestionToCurrent(card) {
            const section = card.closest('[data-review-section]')?.dataset.reviewSection;
            const panel = document.querySelector(`[data-section-panel="${section}"]`);
            const visibleQuestion = Array.from(panel?.querySelectorAll('[data-question-card]') || []).find((item) => !item.hidden);
            const textarea = visibleQuestion?.querySelector('[data-answer-text]');
            if (!textarea) return false;
            const details = Array.from(card.querySelectorAll('.implementation-finding p')).map((item) => item.textContent.trim()).filter(Boolean);
            if (!details.length) return false;
            const prefix = textarea.value.trim() ? '\n\n' : '';
            textarea.value += `${prefix}Sugerencia Doko: ${details.join(' ')}`;
            textarea.focus();
            return true;
        }

        async function decideReview(card, decision) {
            try {
                await requestJson(`${baseUrl}/revision/${card.dataset.reviewId}`, {
                    method: 'POST',
                    body: JSON.stringify({ decision }),
                });
                if (decision === 'AGREGAR_BORRADOR') {
                    notify(appendSuggestionToCurrent(card) ? 'Sugerencia agregada. Guarda la respuesta para conservarla.' : 'Revision marcada para agregar.', 'success');
                } else if (decision === 'ADAPTAR') {
                    notify('Revision marcada para adaptar. Revisa los protocolos del consultorio.', 'success');
                    showSection('protocolos');
                } else {
                    notify('Decision registrada.', 'success');
                }
                card.querySelector('.implementation-review-actions')?.remove();
            } catch (error) {
                notify(error.message, 'error');
            }
        }

        function bindReviewButtons(scope = document) {
            scope.querySelectorAll('[data-review-decision]').forEach((button) => {
                if (button.dataset.bound === '1') return;
                button.dataset.bound = '1';
                button.addEventListener('click', () => decideReview(button.closest('[data-review-id]'), button.dataset.reviewDecision));
            });
        }
        bindReviewButtons();

        document.querySelectorAll('[data-analyze-section]').forEach((button) => {
            button.addEventListener('click', async () => {
                button.disabled = true;
                const original = button.textContent;
                button.textContent = 'Doko esta revisando...';
                try {
                    const result = await requestJson(`${baseUrl}/analizar-seccion`, {
                        method: 'POST',
                        body: JSON.stringify({ seccion: button.dataset.analyzeSection }),
                    });
                    const container = button.closest('[data-review-section]').querySelector('[data-review-results]');
                    const card = document.createElement('article');
                    card.className = 'implementation-review-card';
                    card.dataset.reviewId = result.id_revision;
                    const source = document.createElement('div');
                    source.className = 'implementation-review-source';
                    source.textContent = result.fuente === 'GEMINI' ? 'Gemini - pendiente' : 'Reglas Doko - pendiente';
                    card.appendChild(source);
                    result.hallazgos.forEach((item) => card.appendChild(buildFinding(item)));
                    const actions = document.createElement('div');
                    actions.className = 'implementation-review-actions';
                    [
                        ['AGREGAR_BORRADOR', 'Agregar'],
                        ['PREGUNTAR_DOCTORA', 'Preguntar'],
                        ['ADAPTAR', 'Adaptar'],
                        ['DESCARTAR', 'Descartar'],
                    ].forEach(([value, label]) => {
                        const action = document.createElement('button');
                        action.type = 'button';
                        action.dataset.reviewDecision = value;
                        action.textContent = label;
                        actions.appendChild(action);
                    });
                    card.appendChild(actions);
                    container.prepend(card);
                    bindReviewButtons(card);
                    notify(result.fuente === 'GEMINI' ? 'Doko termino la revision con Gemini.' : 'Doko uso sus reglas locales.', 'success');
                } catch (error) {
                    notify(error.message, 'error');
                } finally {
                    button.disabled = false;
                    button.textContent = original;
                }
            });
        });

        const approve = document.getElementById('implementation-approve');
        approve?.addEventListener('click', async () => {
            const name = document.getElementById('implementation-approved-by')?.value.trim() || '';
            const confirmed = Boolean(document.getElementById('implementation-approved-confirm')?.checked);
            if (!name || !confirmed) {
                notify('Registra quien reviso y confirma la aprobacion.', 'error');
                return;
            }
            approve.disabled = true;
            try {
                await requestJson(`${baseUrl}/aprobar`, {
                    method: 'POST',
                    body: JSON.stringify({ aprobado_por_nombre: name, confirmacion: confirmed }),
                });
                notify('Protocolos aprobados para este consultorio.', 'success');
                window.location.reload();
            } catch (error) {
                notify(error.message, 'error');
                approve.disabled = false;
            }
        });

        const close = document.getElementById('implementation-close');
        close?.addEventListener('click', async () => {
            const accepted = window.dokoConfirmar
                ? await window.dokoConfirmar('Al cerrar, las respuestas y protocolos quedaran como historial de esta implementacion.', {
                    titulo: 'Cerrar implementacion',
                    textoConfirmar: 'Cerrar',
                })
                : window.confirm('Cerrar implementacion?');
            if (!accepted) return;
            close.disabled = true;
            try {
                await requestJson(`${baseUrl}/cerrar`, { method: 'POST', body: '{}' });
                notify('Implementacion cerrada.', 'success');
                window.location.reload();
            } catch (error) {
                notify(error.message, 'error');
                close.disabled = false;
            }
        });

        if (editor.dataset.closed === '1') {
            editor.querySelectorAll('textarea, input, select, [data-question-save], [data-protocol-save], [data-analyze-section]').forEach((control) => {
                if (!control.closest('.implementation-mobile-nav')) control.disabled = true;
            });
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        initCreate();
        initEditor();
    });
})();
