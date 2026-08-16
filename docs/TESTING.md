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

The load test requires an explicitly authorized test physician:

```powershell
$env:DOKO_LOAD_TEST_DOCTOR='test-doctor@example.invalid'
python load_test_panel_assistant.py --help
```

Do not enable production-read flags without reviewing the script and confirming
that the selected account is an authorized test clinic. The test must not
create, edit, confirm, cancel, release, or email an appointment.

## Required manual smoke tests

- Internal login and role navigation.
- Doctor and assistant panel read, create, block, hold, edit, confirm, cancel,
  and release flows using fictitious test events.
- Google reconnection and OAuth callback with a test physician.
- Patient portal, public physician page, and doko.lat directory.
- Doko Assistant deterministic rules, bounded intent classification, and local
  appointment search.
- Mi Centro, supervisor, aggregate AI usage, and operational implementation.
- Doko Suffy catalog, order-cancellation rules, warehouse preparation, and
  delivery-role isolation.
- Failure behavior when Gemini or a Google integration is unavailable.
- Role rejection for protected routes.
- Mobile layouts at 360, 390, and 430 px; desktop at 1024 and 1440 px.

### Printable prescription workflow

These checks are manual and use fictitious patient information:

- Confirm that only an authorized doctor with the module enabled can open it.
- Confirm clinic-scoped professional data and role rejection for assistants,
  disabled doctors, and users from another clinic.
- Exercise the permitted create, edit, clear, and delete interactions in the
  browser without sending prescription content to the server.
- Check rendering, page overflow protection, print preview, and browser
  print-or-PDF output.
- Confirm that reloading the page removes the draft and that no clinical text
  appears in local storage, network requests, application logs, or telemetry.

### WhatsApp Cloud API prototype

These checks are manual and remain limited to Meta test resources and
allowlisted recipients:

- Verify the callback with the correct token and reject an invalid token.
- Validate `X-Hub-Signature-256` when an app secret is configured.
- Confirm that the responder is disabled by default and rejects recipients
  outside the explicit test allowlist.
- Confirm that the bounded test response uses local deterministic rules only.
- Confirm that the prototype does not query Gemini, Google Calendar, or Gmail;
  modify appointments; or persist message bodies.

Experimental integrations and features still being validated are not counted
as completed production test coverage in this document.

## Current performance evidence

See [the sanitized July 15 load test](evidence/load-test-2026-07-15.md). Its
published measurements represent the dated July 15 test and should be
interpreted only within that original scope.
