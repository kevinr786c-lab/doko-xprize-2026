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
| Printable prescription workflow | Application source and physician-reviewed demo | VALIDATED WITH AN AUTHORIZED PHYSICIAN — supporting evidence kept in the judge-facing submission | No prescription or patient content in the repository |
| WhatsApp Cloud API prototype | `docs/WHATSAPP_CLOUD_API.md` and application source | CONTROLLED TESTING / EXPERIMENTAL / PRE-PRODUCTION | Test allowlist; no persisted message bodies |
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
- Doko does not attempt to replace a mature calendar engine. It uses Google
  Calendar as the scheduling foundation and builds clinic-specific operational
  workflows around it.
- Doko Suffy is an integrated medical-supply sourcing and fulfillment
  capability under progressive development. Software and operational
  foundations exist, while commercial validation and expansion of the
  physical logistics operation remain ahead. Future Suffy margin must not be
  presented as current subscription revenue.
- Pre-program experiments and independent clinic operational support are
  disclosed inputs, not the submitted integrated product. See
  `docs/HACKATHON_DISCLOSURES.md` for the canonical disclosure.
- The printable prescription workflow is physician reviewed but is not an EHR,
  certified e-prescribing service, autonomous prescriber, or authorization for
  controlled medication.
- The WhatsApp prototype proves controlled webhook connectivity and local
  bounded response behavior. It is not a live clinic or patient communication
  claim.

## Evidence hierarchy

When memory, a narrative summary, and a dated artifact differ, the dated
artifact controls the claim. Historical counts must retain their original
capture date; they should not be silently updated to a later total.

## Prohibited repository evidence

Do not commit patient names, phone numbers, email addresses, appointment notes,
OAuth tokens, database exports, signed payment receipts, government IDs, or
unredacted clinic conversations.
