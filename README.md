# Doko

Doko is an operational platform for independent medical practices in Tijuana.
It combines appointment operations, patient communication, public presence,
controlled AI assistance, and an emerging B2B supply workflow in one system.

Doko is not presented as a replacement for medical judgment. Its purpose is to
help a clinic operate consistently: fewer missed handoffs, clearer appointment
follow-up, safer use of Google Workspace, and repeatable front-desk processes.

## Production status

As of July 16, 2026, Doko is used by:

- 2 paying doctors.
- 3 clinic assistants across the participating practices.
- Real patient traffic through Doko patient portals.
- A clinic workflow that contained 127 appointment records between July 1 and
  July 15. This is operational volume managed with Doko, not a claim that Doko
  generated 127 new patients.

The business is intentionally onboarding slowly while workflows, reliability,
and training are validated with real clinics.

## What Doko includes

- **Medical panel:** appointments, blocks, temporary holds, editing, manual
  confirmation, release, search, profile management, and clinic services.
- **Patient portal:** clinic identity, contact and location information,
  appointment access, confirmation guidance, and a constrained patient
  assistant.
- **Appointment communication:** informational email, configurable 24/48-hour
  confirmation flow, and auditable confirmation/cancellation links.
- **Doko Assistant:** operational guidance and private, read-only conversational
  appointment search for doctors and assistants.
- **Operational implementation:** versioned clinic protocols, assistant
  training, follow-up, and human-approved workflow adaptations.
- **Doko.lat:** local medical directory and reusable physician pages with local
  SEO controls.
- **Doko Suffy:** B2B catalog, orders, warehouse preparation, inventory,
  delivery, suppliers, and controlled operational agents.
- **Mi Centro:** owner dashboard for doctors, digital presence, Suffy,
  inventory, administration, system health, and AI usage.

## AI-native operations

Doko uses Gemini 2.5 Flash in production with deliberately bounded authority.
Deterministic application rules remain responsible for permissions, incident
severity, appointment state, email timing, and every operational write.

Gemini is used for constrained tasks such as:

- Answering administrative patient questions from clinic-configured content.
- Classifying an allowed operational intent after local redaction.
- Summarizing non-Workspace operational information.
- Reviewing sanitized implementation notes for missing definitions.
- Producing human-readable drafts for controlled business agents.

Gemini cannot diagnose, prescribe, change appointments, approve protocols,
purchase products, move money, or override application rules. Raw or derived
Google Workspace API data is not sent to Gemini.

See [AI operations](docs/AI_OPERATIONS.md) and
[privacy and safety](docs/PRIVACY_AND_SAFETY.md).

## Architecture

- Python 3 / Flask / Gunicorn.
- PostgreSQL on Cloud SQL.
- Cloud Run production service.
- Google Cloud Storage for managed media.
- Google Calendar API and Gmail API through per-doctor OAuth authorization.
- Gemini API / Vertex AI adapter with measured usage and deterministic fallback.
- Server-rendered Jinja, CSS, and JavaScript with responsive PWA support.

See [architecture](docs/ARCHITECTURE.md).

## Local setup

1. Create a Python virtual environment.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to a local `.env` and provide local credentials.
4. Start PostgreSQL or the Cloud SQL Auth Proxy for an authorized test database.
5. Apply the SQL migrations in chronological order.
6. Run the application:

   ```bash
   python app_elite.py
   ```

Never commit `.env`, OAuth credentials, service-account keys, payment evidence,
patient screenshots, or production database exports.

## Verification

The repository includes syntax, import, template, and read-only load-test
instructions in [TESTING.md](docs/TESTING.md). Sanitized production evidence is
indexed in [PRODUCTION_EVIDENCE.md](docs/PRODUCTION_EVIDENCE.md).

## Hackathon disclosure

Doko was started during the Build with Gemini XPRIZE period. Pre-existing
clinic relationships, prior Google Calendar work, and the founder's operations
experience are disclosed separately from the submitted project. See
[HACKATHON_DISCLOSURES.md](docs/HACKATHON_DISCLOSURES.md).

## Live product

- Product and medical directory: <https://doko.lat>
- Privacy policy: <https://doko.lat/privacidad>

This private repository is provided for hackathon testing and judging. No
license is granted for redistribution or commercial reuse.
