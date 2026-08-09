# Privacy and Safety

## Data minimization

Doko requests only the Google scopes required for its production scheduling and
transactional email functions:

- `openid`
- `userinfo.email`
- `calendar`
- `gmail.send`

Google Workspace data is used for the authorized clinic workflow and is not
used to train or improve generalized AI models.

## AI isolation

Doko does not send Gmail message bodies, Google Calendar event payloads, or
appointment records to Gemini. For the medical-panel assistant, Gemini receives
only a locally extracted concept package when bounded classification is
invoked; deterministic operational records remain authoritative.

Conversational appointment search is fully local. The implementation assistant
removes names, email addresses, phone numbers, dates, UUIDs, patient
information, and Workspace content before a manual review call.

The patient assistant uses only the public or clinic-approved context of the
selected physician. Clinic context is isolated and may not be reused to answer
for another clinic.

## WhatsApp controlled testing

The current WhatsApp Cloud API integration is restricted to controlled testing. The test responder uses local deterministic rules and does not query Gemini, Google Calendar, or Gmail. Message bodies are not persisted by the prototype. Production clinic use will require a separate review of authorization, consent, provider requirements, templates, privacy, retention, and operational safeguards.

## Repository safety

The repository excludes:

- Environment files and local secret folders.
- OAuth client credentials and service-account keys.
- Cloud SQL proxy binaries.
- Private receipts and revenue evidence.
- Patient screenshots and database exports.
- Temporary recordings, generated previews, and local tool caches.

No production secret should ever be added to source control. If a secret is
accidentally committed, removing the file is not sufficient; the credential
must be revoked or rotated.

## Evidence safety

Screenshots and videos must use a test physician and fictitious patient data or
be redacted before publication. Aggregate appointment counts are preferred over
row-level records. Testimonials require the participant's explicit permission.

Appointment volume demonstrates that Doko operates under real clinic load. It
does not mean that Doko generated those patients or appointments.

The public privacy policy is hosted at <https://doko.lat/privacidad>.
