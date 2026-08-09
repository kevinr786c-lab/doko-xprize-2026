# Production Evidence Index

This index lists the public, sanitized evidence included in the repository.
Confidential financial and customer evidence is submitted only through
Devpost's judge-facing channels.

| Evidence | Location | Status | Privacy rule |
| --- | --- | --- | --- |
| Live public product | <https://doko.lat> | Available | Public data only |
| Appointment volume snapshot | Medical-panel aggregate snapshot, July 27, 2026 | Point-in-time evidence | Counts only; no patient-level data |
| Current application source | Repository root | Included | No credentials or production data |
| Preserved project milestones | `docs/PROJECT_EVOLUTION.md` | Included | No credentials or patient data |
| Pocket notebook translations | `docs/NOTEBOOK_EVIDENCE_TRANSLATIONS.md` | Included | Selected pages contain no patient data |
| Selected notebook images | `docs/evidence/notebook/` | Six included | Reviewed pages contain no patient or Workspace data |
| Read-only assistant load test | `docs/evidence/load-test-2026-07-15.md` | Included | Aggregate metrics only |
| AI operating boundaries | `docs/AI_OPERATIONS.md` | Included | No prompts or patient data |
| Privacy and safety controls | `docs/PRIVACY_AND_SAFETY.md` | Included | No Workspace payloads |
| Automated repository validation | `.github/workflows/validate.yml` | Included | Compile, import, route, and Jinja checks |

Payment records, profit-and-loss evidence, customer contact details, and
permissioned testimonials are intentionally excluded from the source
repository. They belong in the confidential submission fields provided by
Devpost.

## Interpretation rules

- Doko manages a real appointment workflow; it did not generate every
  appointment represented in the system.
- The July 27 dashboard snapshot shows approximately 330 appointment records
  for one physician and 87 for another. These are operational counts captured
  on that date, not a patient-acquisition claim.
- Appointment confirmation and released-slot management improve operational
  control. Revenue, attendance, or patient-growth effects require separate
  measured evidence.
- Google Calendar is the integrated scheduling foundation. The Doko portal,
  panel, deterministic rules, audit, confirmation, implementation, and
  assistance layers are Doko's clinic-specific operating system around it.
- Doko Suffy is an integrated sourcing and fulfillment capability under
  progressive development. Future Suffy margin must not be presented as
  current subscription revenue.
- Pre-program experiments and the earlier standalone Google Calendar booking
  configuration are disclosed inputs, not the submitted integrated product.

## Evidence hierarchy

When memory, a narrative summary, and a dated artifact differ, the dated
artifact controls the claim. Historical counts must retain their original
capture date; they should not be silently updated to a later total.

## Prohibited repository evidence

Do not commit patient names, phone numbers, email addresses, appointment notes,
OAuth tokens, database exports, signed payment receipts, government IDs, or
unredacted clinic conversations.
