# Testing and Verification

Tests must avoid production writes unless the action is explicitly authorized
and uses a test clinic with fictitious data.

## Python compilation

```powershell
python -m compileall app_elite.py routes helpers agentes
```

## Application import and primary templates

```powershell
$env:APP_IMPORT_OK='1'
python -c "from app_elite import app; print('APP_IMPORT_OK')"
python -c "from app_elite import app; [app.jinja_env.get_template(t) for t in ['auth/login_interno.html','admin/dashboard.html','admin/implementacion_operativa.html','presencia/home.html','presencia/sitio.html']]; print('JINJA_OK')"
```

## Route inspection

```powershell
python -c "from app_elite import app; print('\n'.join(sorted(str(r) for r in app.url_map.iter_rules())))"
```

## Read-only assistant load test

The load test requires an explicitly authorized test doctor:

```powershell
$env:DOKO_LOAD_TEST_DOCTOR='test-doctor@example.invalid'
python load_test_panel_assistant.py --help
```

Do not enable production-read flags without reviewing the script and confirming
that the selected account is a permitted test clinic. The test must not create,
edit, confirm, cancel, release, or email an appointment.

## Required manual smoke tests

- Internal login and role navigation.
- Doctor/assistant panel read, create, block, hold, edit, confirm, and release
  using fictitious test events.
- Google reconnection and OAuth callback with a test doctor.
- Patient portal and public physician page.
- Doko Assistant rules, safe intent classification, and local appointment search.
- Mi Centro, supervisor, AI usage, and operational implementation.
- Catalog, order cancellation rules, warehouse preparation, and delivery roles.
- Mobile layouts at 360, 390, and 430 px; desktop at 1024 and 1440 px.

## Current performance evidence

See [the sanitized July 15 load test](evidence/load-test-2026-07-15.md).
