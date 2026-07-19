# Production Evidence Index

This index lists the public, sanitized evidence currently included in the
repository. Confidential financial and customer evidence is submitted only
through Devpost's judge-facing fields.

| Evidence | Location | Status | Privacy rule |
| --- | --- | --- | --- |
| Live product | <https://doko.lat> | Available | Public data only |
| Current application source | Repository root | Included | No credentials or production data |
| Preserved project milestones | `docs/PROJECT_EVOLUTION.md` | Included | No credentials or patient data |
| Pocket notebook translations | `docs/NOTEBOOK_EVIDENCE_TRANSLATIONS.md` | Included | Selected pages contain no patient data |
| Selected notebook images | `docs/evidence/notebook/` | Six included | Reviewed pages contain no patient or Workspace data |
| Read-only assistant load test | `docs/evidence/load-test-2026-07-15.md` | Included | Aggregate metrics only |
| AI operation boundaries | `docs/AI_OPERATIONS.md` | Included | No prompts or patient data |
| Privacy and safety controls | `docs/PRIVACY_AND_SAFETY.md` | Included | No Workspace payloads |
| Automated repository validation | `.github/workflows/validate.yml` | Included | Compile, import, route and Jinja checks |

Payment records, profit-and-loss evidence, customer contact details and
permissioned testimonials are intentionally excluded from the source repository.
They belong in the confidential submission channels provided by Devpost.

## Claims that require careful wording

- Doko helped manage an existing appointment workflow; it did not generate every
  appointment shown in the system.
- Appointment confirmation and released-slot management improve operational
  control, but causal revenue or attendance claims require measured evidence.
- Google Calendar is an integrated scheduling component; the Doko portal, panel,
  rules, audit, confirmation, and assistance layers are Doko.
- Future Suffy or local-directory revenue is not current revenue.
- Pre-program experiments and the earlier standalone Calendar service are
  disclosed inputs, not the submitted integrated product.

## Prohibited repository evidence

Do not commit patient names, phone numbers, email addresses, appointment notes,
OAuth tokens, database exports, signed payment receipts, IDs, or unredacted
clinic conversations.
