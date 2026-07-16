(() => {
    'use strict';

    const PWA_UPDATE_ID = 'doko-pwa-update';
    const PWA_OFFLINE_ID = 'doko-pwa-offline';
    const PWA_INSTALL_ID = 'doko-pwa-install';
    const INSTALL_DISMISSED_KEY = 'doko_pwa_install_dismissed_at';
    let deferredInstallPrompt = null;

    function isInstallAllowedPath() {
        const path = window.location.pathname || '/';
        return path === '/login/interno'
            || path.startsWith('/admin')
            || path.startsWith('/panel')
            || path.startsWith('/bodega')
            || path.startsWith('/reparto');
    }

    function ensureStyles() {
        if (document.getElementById('doko-pwa-experience-styles')) return;
        const style = document.createElement('style');
        style.id = 'doko-pwa-experience-styles';
        style.textContent = `
            .doko-pwa-notice { align-items: center; background: #fff; border: 1px solid #cfdaea; border-radius: 10px; box-shadow: 0 12px 30px rgba(15, 35, 66, .18); color: #111827; display: flex; gap: 12px; left: 50%; max-width: min(430px, calc(100vw - 32px)); padding: 12px 14px; position: fixed; top: max(14px, env(safe-area-inset-top)); transform: translateX(-50%); width: max-content; z-index: 10050; }
            .doko-pwa-notice span { font-size: 14px; line-height: 1.35; }
            .doko-pwa-notice button { background: #163661; border: 0; border-radius: 7px; color: #fff; cursor: pointer; font: inherit; font-weight: 700; padding: 8px 11px; white-space: nowrap; }
            .doko-pwa-notice .doko-pwa-secondary { background: transparent; color: #163661; border: 1px solid #cfdaea; }
            .doko-pwa-install { align-items: flex-start; max-width: min(520px, calc(100vw - 28px)); }
            .doko-pwa-install strong { display: block; font-size: 14px; margin-bottom: 2px; }
            .doko-pwa-install small { color: #526274; display: block; font-size: 12px; line-height: 1.35; margin-top: 2px; }
            .doko-pwa-offline { background: #fff8e6; border-color: #efd28a; box-shadow: 0 8px 22px rgba(99, 72, 8, .13); }
            .doko-pwa-offline strong { color: #6b4d00; font-size: 14px; }
            @media (max-width: 480px) { .doko-pwa-notice { align-items: stretch; flex-wrap: wrap; } .doko-pwa-notice button { margin-left: auto; } }
        `;
        document.head.appendChild(style);
    }

    function removeNotice(id) {
        document.getElementById(id)?.remove();
    }

    function showOffline() {
        ensureStyles();
        if (document.getElementById(PWA_OFFLINE_ID)) return;
        const notice = document.createElement('div');
        notice.id = PWA_OFFLINE_ID;
        notice.className = 'doko-pwa-notice doko-pwa-offline';
        notice.setAttribute('role', 'status');
        notice.innerHTML = '<strong>Sin conexi&oacute;n.</strong><span>Los datos se actualizar&aacute;n al recuperar internet.</span>';
        document.body.appendChild(notice);
    }

    function isStandalone() {
        return window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
    }

    function isIos() {
        return /iphone|ipad|ipod/i.test(window.navigator.userAgent || '');
    }

    function installDismissedRecently() {
        const dismissedAt = Number(localStorage.getItem(INSTALL_DISMISSED_KEY) || 0);
        return dismissedAt && Date.now() - dismissedAt < 1000 * 60 * 60 * 24 * 7;
    }

    function dismissInstallNotice() {
        localStorage.setItem(INSTALL_DISMISSED_KEY, String(Date.now()));
        removeNotice(PWA_INSTALL_ID);
    }

    function showInstallNotice(mode = 'android') {
        if (!isInstallAllowedPath()) return;
        ensureStyles();
        if (isStandalone() || document.getElementById(PWA_INSTALL_ID) || installDismissedRecently()) return;
        const notice = document.createElement('div');
        notice.id = PWA_INSTALL_ID;
        notice.className = 'doko-pwa-notice doko-pwa-install';
        notice.setAttribute('role', 'status');
        const text = document.createElement('span');
        if (mode === 'ios') {
            text.innerHTML = '<strong>Agrega Doko a tu pantalla de inicio.</strong><small>En iPhone toca Compartir y luego “Agregar a pantalla de inicio”.</small>';
        } else {
            text.innerHTML = '<strong>Instala Doko como app.</strong><small>Accede más rápido a citas, pedidos y confirmaciones.</small>';
        }
        const primary = document.createElement('button');
        primary.type = 'button';
        primary.textContent = mode === 'ios' ? 'Entendido' : 'Instalar Doko';
        primary.addEventListener('click', async () => {
            if (mode === 'ios' || !deferredInstallPrompt) {
                dismissInstallNotice();
                return;
            }
            const promptEvent = deferredInstallPrompt;
            deferredInstallPrompt = null;
            promptEvent.prompt();
            try { await promptEvent.userChoice; } catch (_) {}
            dismissInstallNotice();
        });
        const later = document.createElement('button');
        later.type = 'button';
        later.className = 'doko-pwa-secondary';
        later.textContent = 'Luego';
        later.addEventListener('click', dismissInstallNotice);
        notice.append(text, primary, later);
        document.body.appendChild(notice);
    }

    function showUpdate(waitingWorker) {
        ensureStyles();
        if (!waitingWorker || document.getElementById(PWA_UPDATE_ID)) return;
        const notice = document.createElement('div');
        notice.id = PWA_UPDATE_ID;
        notice.className = 'doko-pwa-notice';
        notice.setAttribute('role', 'status');
        notice.innerHTML = '<span>Hay una versi&oacute;n nueva de Doko disponible.</span><button type="button">Actualizar</button>';
        notice.querySelector('button').addEventListener('click', () => {
            waitingWorker.postMessage({ type: 'SKIP_WAITING' });
        });
        document.body.appendChild(notice);
    }

    function registerPwaExperience() {
        if (!('serviceWorker' in navigator)) return;
        navigator.serviceWorker.register('/sw.js').then((registration) => {
            if (registration.waiting) showUpdate(registration.waiting);
            registration.addEventListener('updatefound', () => {
                const installing = registration.installing;
                if (!installing) return;
                installing.addEventListener('statechange', () => {
                    if (installing.state === 'installed' && navigator.serviceWorker.controller) {
                        showUpdate(registration.waiting);
                    }
                });
            });
        }).catch(() => {
            // PWA is optional; the normal web application remains available.
        });

        let refreshing = false;
        navigator.serviceWorker.addEventListener('controllerchange', () => {
            if (refreshing) return;
            refreshing = true;
            window.location.reload();
        });
    }

    window.addEventListener('offline', showOffline);
    window.addEventListener('online', () => removeNotice(PWA_OFFLINE_ID));
    window.addEventListener('beforeinstallprompt', (event) => {
        if (!isInstallAllowedPath()) return;
        event.preventDefault();
        deferredInstallPrompt = event;
        showInstallNotice('android');
    });
    window.addEventListener('appinstalled', () => {
        deferredInstallPrompt = null;
        removeNotice(PWA_INSTALL_ID);
    });
    window.addEventListener('load', () => {
        if (!navigator.onLine) showOffline();
        registerPwaExperience();
        window.setTimeout(() => {
            if (!isInstallAllowedPath()) return;
            if (isIos()) showInstallNotice('ios');
            else if (deferredInstallPrompt) showInstallNotice('android');
        }, 1600);
    });
})();
