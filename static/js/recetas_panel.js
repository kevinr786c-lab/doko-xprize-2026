(() => {
    'use strict';

    const state = {
        token: '',
        enabled: false,
        dirty: false,
        config: null,
        profile: null,
        suggestions: null,
        profileConfirmed: false,
        selectedFiles: new Map(),
    };

    const byId = id => document.getElementById(id);
    const fields = () => [
        byId('recipe-patient'),
        byId('recipe-age'),
        byId('recipe-date'),
        byId('recipe-next-date'),
        byId('recipe-prescription'),
    ].filter(Boolean);
    const contentFields = () => [
        byId('recipe-patient'),
        byId('recipe-age'),
        byId('recipe-next-date'),
        byId('recipe-prescription'),
    ].filter(Boolean);

    function setStatus(message, type = '') {
        const status = byId('recipe-status');
        if (!status) return;
        status.textContent = message || '';
        status.className = `recipe-status${type ? ` is-${type}` : ''}`;
    }

    function setProfileStatus(message, type = '') {
        const status = byId('recipe-professional-status');
        if (!status) return;
        status.textContent = message || '';
        status.className = `recipe-professional-status${type ? ` is-${type}` : ''}`;
    }

    function setText(id, value, fallback = '') {
        const element = byId(id);
        if (element) element.textContent = value || fallback;
    }

    function setImage(id, url, alt) {
        const image = byId(id);
        if (!image) return;
        if (!url) {
            image.hidden = true;
            image.removeAttribute('src');
            return;
        }
        image.src = url;
        image.alt = alt || '';
        image.hidden = false;
    }

    function value(id) {
        return byId(id)?.value?.trim() || '';
    }

    function formatDate(iso) {
        if (!iso) return '';
        const parts = iso.split('-');
        return parts.length === 3 ? `${parts[2]}/${parts[1]}/${parts[0]}` : iso;
    }

    function professionalLines(config) {
        const lines = [];
        if (config.especialidad) lines.push(config.especialidad);
        if (config.institucion_titulo) lines.push(config.institucion_titulo);
        const licenses = [];
        if (config.cedula_profesional) licenses.push(`Céd. Prof. ${config.cedula_profesional}`);
        if (config.cedula_especialidad) licenses.push(`Céd. Esp. ${config.cedula_especialidad}`);
        if (licenses.length) lines.push(licenses.join(' | '));
        if (config.rfc) lines.push(`RFC ${config.rfc}`);
        return lines;
    }

    function contactLines(config) {
        return [
            config.direccion_publica,
            config.telefono_consultorio ? `Consultorio: ${config.telefono_consultorio}` : '',
            config.telefono_emergencias ? `Emergencias: ${config.telefono_emergencias}` : '',
            config.correo_publico,
            config.datos_publicos,
        ].filter(Boolean);
    }

    function updateProfileRequirement() {
        const warning = byId('recipe-profile-required');
        if (warning) warning.hidden = state.profileConfirmed;
    }

    function applyConfig(payload) {
        const config = payload.configuracion;
        state.config = config;
        state.enabled = true;
        state.profileConfirmed = !!payload.perfil_profesional_confirmado;

        const nav = byId('doctor-recipes-nav');
        if (nav) nav.hidden = false;
        const profileSection = byId('recipe-professional-profile');
        if (profileSection) profileSection.hidden = false;
        byId('recipe-module')?.style.setProperty('--recipe-accent', 'var(--color-primario)');
        setText('recipe-editor-doctor', config.nombre_doctor, 'Perfil profesional pendiente');
        setText('recipe-clinic-name', config.nombre_consultorio, config.nombre_doctor || 'Consultorio');
        setText('recipe-doctor-name', config.nombre_doctor, 'Nombre profesional pendiente');
        setText('recipe-professional-data', professionalLines(config).join(' · '));
        setText('recipe-public-data', contactLines(config).join(' | '));
        setImage('recipe-logo', config.logo_url, 'Logo profesional');

        const emblems = byId('recipe-emblems');
        if (emblems) {
            emblems.replaceChildren();
            (config.emblemas || []).forEach(item => {
                const image = document.createElement('img');
                image.src = item.url;
                image.alt = item.nombre || 'Emblema institucional';
                emblems.appendChild(image);
            });
            emblems.hidden = !emblems.children.length;
        }

        const watermark = byId('recipe-watermark');
        if (watermark) watermark.hidden = !config.modo_prueba;
        const badge = byId('recipe-mode-badge');
        if (badge) badge.textContent = config.modo_prueba ? 'Prototipo' : 'Formato activo';
        const dateInput = byId('recipe-date');
        if (dateInput && !dateInput.value) dateInput.value = payload.fecha_tijuana || '';
        updateProfileRequirement();
        updatePreview();
    }

    function hideModule() {
        state.enabled = false;
        state.config = null;
        state.profile = null;
        state.suggestions = null;
        state.profileConfirmed = false;
        state.selectedFiles.clear();
        const nav = byId('doctor-recipes-nav');
        if (nav) nav.hidden = true;
        const profileSection = byId('recipe-professional-profile');
        if (profileSection) profileSection.hidden = true;
        if (byId('recetas-section')?.classList.contains('active')) {
            window.mostrarVistaDoctor?.('agenda-section');
        }
        resetDraft(true);
    }

    function updatePreview() {
        setText('recipe-print-patient', value('recipe-patient'), ' ');
        setText('recipe-print-age', value('recipe-age'), 'No indicada');
        setText('recipe-print-date', formatDate(value('recipe-date')), ' ');
        setText('recipe-print-next-date', formatDate(value('recipe-next-date')), 'No indicada');
        setText('recipe-print-prescription', value('recipe-prescription'));
        validateOverflow(false);
    }

    function validateOverflow(showMessage = true) {
        const area = byId('recipe-print-prescription');
        const label = byId('recipe-page-state');
        if (!area || !label) return false;
        const overflow = area.scrollHeight > area.clientHeight + 2;
        label.textContent = overflow ? 'El contenido supera una página' : 'Carta vertical · una página';
        label.classList.toggle('is-error', overflow);
        if (overflow && showMessage) {
            setStatus('La receta supera una página. Reduce o reorganiza las indicaciones antes de imprimir.', 'error');
        }
        return overflow;
    }

    function markDirty() {
        state.dirty = contentFields().some(field => field.value.trim()) || !!byId('recipe-review')?.checked;
        updatePreview();
    }

    function todayInTijuana() {
        const parts = new Intl.DateTimeFormat('en-US', {
            timeZone: 'America/Tijuana', year: 'numeric', month: '2-digit', day: '2-digit'
        }).formatToParts(new Date()).reduce((result, part) => {
            result[part.type] = part.value;
            return result;
        }, {});
        return `${parts.year}-${parts.month}-${parts.day}`;
    }

    function resetDraft(silent = false) {
        fields().forEach(field => { field.value = ''; });
        const review = byId('recipe-review');
        if (review) review.checked = false;
        if (byId('recipe-date')) byId('recipe-date').value = todayInTijuana();
        state.dirty = false;
        if (!silent) setStatus('Borrador limpiado.');
        updatePreview();
    }

    function openProfessionalProfile() {
        window.mostrarVistaDoctor?.('perfil-section');
        window.setTimeout(() => {
            byId('recipe-professional-profile')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 80);
    }

    function printRecipe() {
        setStatus('');
        if (!state.profileConfirmed || !state.config?.nombre_doctor || !state.config?.cedula_profesional) {
            setStatus('Confirma en Perfil el nombre profesional y la cédula antes de imprimir.', 'error');
            openProfessionalProfile();
            return;
        }
        if (!value('recipe-patient') || !value('recipe-date') || !value('recipe-prescription')) {
            setStatus('Completa paciente, fecha e indicaciones antes de imprimir.', 'error');
            return;
        }
        if (!byId('recipe-review')?.checked) {
            setStatus('Confirma que revisaste y autorizas la receta.', 'error');
            return;
        }
        if (validateOverflow(true)) return;
        setStatus('Guarda el PDF y adjúntalo manualmente en WhatsApp para validarlo. Doko no lo envía automáticamente.', 'ok');
        // Aislar la vista de receta para que el informe mensual no entre en la impresion.
        window.mostrarVistaDoctor?.('recetas-section');
        document.body.classList.add('recipe-print-mode');
        const clearPrintMode = () => document.body.classList.remove('recipe-print-mode');
        window.addEventListener('afterprint', clearPrintMode, { once: true });
        window.setTimeout(clearPrintMode, 15000);
        window.print();
    }

    async function apiJson(url, options = {}) {
        const headers = new Headers(options.headers || {});
        headers.set('Authorization', `Bearer ${state.token}`);
        if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
        const response = await fetch(url, { ...options, headers });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || !payload.ok) throw new Error(payload.error || 'No fue posible completar la operación.');
        return payload;
    }

    function profileForm() {
        return byId('recipe-professional-form');
    }

    function setAssetPreview(field, url) {
        const form = profileForm();
        const hidden = form?.elements?.namedItem(field);
        if (hidden) hidden.value = url || '';
        setImage(`recipe-profile-${field}-preview`, url, 'Vista previa del recurso');
    }

    function fillProfileForm(profile) {
        const form = profileForm();
        if (!form || !profile) return;
        Object.entries(profile).forEach(([key, fieldValue]) => {
            const control = form.elements.namedItem(key);
            if (!control) return;
            if (control.type === 'checkbox') control.checked = !!fieldValue;
            else control.value = fieldValue || '';
        });
        ['logo_url', 'emblema_1_url', 'emblema_2_url'].forEach(field => {
            setAssetPreview(field, profile[field] || '');
        });
    }

    function collectProfileForm() {
        const form = profileForm();
        const result = {};
        if (!form) return result;
        new FormData(form).forEach((fieldValue, key) => {
            if (!(fieldValue instanceof File)) result[key] = String(fieldValue);
        });
        ['emblema_1_autorizado', 'emblema_2_autorizado'].forEach(key => {
            result[key] = !!form.elements.namedItem(key)?.checked;
        });
        return result;
    }

    async function loadProfessionalProfile() {
        const payload = await apiJson('/panel/recetas/perfil-profesional');
        state.profile = payload.perfil;
        state.suggestions = payload.sugerencias;
        state.profileConfirmed = !!payload.confirmado;
        fillProfileForm(payload.perfil);
        updateProfileRequirement();
        setProfileStatus(
            state.profileConfirmed
                ? 'Copia privada confirmada. Los cambios del perfil público no la modificarán.'
                : 'Revisa y guarda esta copia privada antes de imprimir la primera receta.'
        );
    }

    async function saveProfessionalProfile(event) {
        event.preventDefault();
        const form = profileForm();
        if (!form?.reportValidity()) return;
        setProfileStatus('Guardando datos privados...');
        try {
            const payload = await apiJson('/panel/recetas/perfil-profesional', {
                method: 'PATCH',
                body: JSON.stringify(collectProfileForm()),
            });
            state.profile = payload.perfil;
            state.profileConfirmed = !!payload.confirmado;
            setProfileStatus('Datos privados guardados. No se publicaron en Doko.', 'ok');
            const configPayload = await apiJson('/panel/recetas/configuracion');
            applyConfig(configPayload);
        } catch (error) {
            setProfileStatus(error.message, 'error');
        }
    }

    function usePublicSuggestions() {
        if (!state.suggestions) {
            setProfileStatus('No hay sugerencias disponibles todavía.', 'error');
            return;
        }
        const current = collectProfileForm();
        const suggestedFields = [
            'nombre_profesional',
            'especialidad_profesional',
            'institucion_titulo',
            'cedula_profesional',
            'cedula_especialidad',
            'nombre_consultorio',
            'telefono_consultorio',
            'correo_contacto',
            'direccion_impresa',
            'logo_url',
        ];
        const merged = { ...current };
        suggestedFields.forEach(field => {
            const suggestion = String(state.suggestions[field] || '').trim();
            if (suggestion && !String(current[field] || '').trim()) merged[field] = suggestion;
        });
        fillProfileForm(merged);
        setProfileStatus('Sugerencias colocadas. Revísalas y guarda para crear la copia privada.');
    }

    async function uploadProfileAsset(field) {
        const file = state.selectedFiles.get(field);
        if (!file) {
            setProfileStatus('Primero elige una imagen.', 'error');
            return;
        }
        const body = new FormData();
        body.append('tipo', field);
        body.append('file', file);
        setProfileStatus('Subiendo imagen...');
        try {
            const payload = await apiJson('/panel/recetas/recursos', { method: 'POST', body });
            setAssetPreview(field, payload.url);
            state.selectedFiles.delete(field);
            setProfileStatus('Imagen lista. Guarda el perfil para confirmar el cambio.', 'ok');
        } catch (error) {
            setProfileStatus(error.message, 'error');
        }
    }

    async function sync({ token, esAsistente }) {
        resetDraft(true);
        state.token = token || '';
        if (!state.token || esAsistente) {
            hideModule();
            return false;
        }
        try {
            const payload = await apiJson('/panel/recetas/configuracion');
            applyConfig(payload);
            await loadProfessionalProfile();
            return true;
        } catch (error) {
            hideModule();
            return false;
        }
    }

    function open() {
        if (!state.enabled) return;
        window.setTimeout(() => validateOverflow(false), 0);
    }

    document.addEventListener('DOMContentLoaded', () => {
        resetDraft(true);
        fields().forEach(field => field.addEventListener('input', markDirty));
        byId('recipe-review')?.addEventListener('change', markDirty);
        byId('recipe-print-button')?.addEventListener('click', printRecipe);
        byId('recipe-reset-button')?.addEventListener('click', () => resetDraft(false));
        byId('recipe-open-professional-profile')?.addEventListener('click', openProfessionalProfile);
        byId('recipe-use-public-suggestions')?.addEventListener('click', usePublicSuggestions);
        profileForm()?.addEventListener('submit', saveProfessionalProfile);

        document.querySelectorAll('[data-recipe-profile-file]').forEach(input => {
            input.addEventListener('change', () => {
                const field = input.dataset.recipeProfileFile;
                const file = input.files?.[0];
                if (field && file) {
                    state.selectedFiles.set(field, file);
                    setProfileStatus(`${file.name} seleccionado. Toca Subir para cargarlo.`);
                }
            });
        });
        document.querySelectorAll('[data-recipe-profile-upload]').forEach(button => {
            button.addEventListener('click', () => uploadProfileAsset(button.dataset.recipeProfileUpload));
        });
        document.querySelectorAll('[data-recipe-profile-clear]').forEach(button => {
            button.addEventListener('click', () => {
                const field = button.dataset.recipeProfileClear;
                state.selectedFiles.delete(field);
                setAssetPreview(field, '');
                setProfileStatus('Recurso retirado del borrador. Guarda el perfil para confirmar.');
            });
        });

        window.addEventListener('resize', () => validateOverflow(false));
        window.addEventListener('beforeunload', event => {
            if (!state.dirty) return;
            event.preventDefault();
            event.returnValue = '';
        });
        window.addEventListener('pageshow', event => {
            if (event.persisted) resetDraft(true);
        });
        window.addEventListener('pagehide', () => resetDraft(true));
    });

    window.DokoRecetasPanel = { sync, reset: () => resetDraft(true), open };
})();
