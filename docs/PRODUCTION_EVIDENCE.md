# Production Evidence Index

This index separates public technical evidence from confidential financial and
customer evidence.

| Evidence | Location | Status | Privacy rule |
| --- | --- | --- | --- |
| Live product | <https://doko.lat> | Available | Public data only |
| Preserved project milestones | `docs/PROJECT_EVOLUTION.md` | Included | No credentials or patient data |
| Pocket notebook translations | `docs/NOTEBOOK_EVIDENCE_TRANSLATIONS.md` | Draft included | Selected pages contain no patient data |
| Selected notebook images | `docs/evidence/notebook/` | Six included | Reviewed pages contain no patient or Workspace data |
| OAuth verification video | YouTube unlisted | Available separately | Fictitious patient data |
| Contest demo under 3 minutes | Devpost / YouTube | Pending final edit | English captions, test data |
| Read-only assistant load test | `docs/evidence/load-test-2026-07-15.md` | Included | Aggregate metrics only |
| Cloud Run revision and request logs | Devpost or sanitized repository image | Pending | No tokens or request payloads |
| AI usage dashboard | Sanitized repository image | Pending | No prompts or patient data |
| Appointment workflow volume | Sanitized aggregate image | Pending | Counts only, no patient rows |
| Revenue and expense evidence | Devpost judge-only upload | Pending | Never commit receipts |
| Assistant testimonial | Public permissioned post | Pending | No patient stories or data |
| Doctor impact testimonial | Public permissioned post | Pending | Describe workflow impact accurately |

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
