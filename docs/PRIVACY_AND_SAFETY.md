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

Raw, aggregated, anonymized, or derived Gmail and Google Calendar API data is
not sent to Gemini. The panel assistant strips identifiers before an optional
intent classification, and conversational appointment search is fully local.

The implementation assistant removes names, emails, phone numbers, dates,
UUIDs, patient information, and Workspace content before a manual review call.

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

Screenshots and videos must use a test doctor and fictitious patient data, or be
redacted before publication. Aggregate appointment counts are preferred over
row-level records. Testimonials require the participant's explicit permission.

The public privacy policy is hosted at <https://doko.lat/privacidad>.
