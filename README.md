# Doko

**An adaptable operating ecosystem for small medical practices in Tijuana.**

Doko combines clinic operations, patient-facing digital presence, implementation support, bounded AI assistance, and a progressively developed medical-supply capability in one operating ecosystem and business. It is built from direct observation of real clinic work, then improved in small, testable steps.

> Build only where Doko adds meaningful value; integrate what is already solved well.

> Observe first. Build small. Validate with real users. Expand only when the workflow proves useful.

## Status language

This repository uses five explicit labels:

- **PRODUCTION**: running in real clinic operations.
- **VALIDATED**: tested with real users or workflows, but not necessarily offered broadly.
- **CONTROLLED TESTING**: restricted to test accounts or a controlled environment.
- **IMPLEMENTED / NOT YET COMMERCIALLY VALIDATED**: present in the product or repository, but not yet proven as a commercial workflow.
- **FUTURE DIRECTION**: planned direction, not a current capability.

## Why Doko exists

Small practices often depend on a doctor, an assistant, several disconnected tools, and knowledge that lives only in people's routines. A generic platform can impose a fixed workflow that does not match the specialty or the clinic. Doko starts with the opposite question: how does this clinic actually work, and where can software remove friction without replacing medical judgment?

The first production use includes five active operational users: two paying gynecologists and three clinic assistants assigned to their practices. The gynecologists are the customers; the assistants are operational users. Doctors and assistants do not share an identical toolset: each role receives only the interfaces, permissions, and workflows needed for its responsibilities. The goal is not to make every clinic identical. It is to establish a reliable operating core, document specialty-specific workflows, and add optional tools only after they prove useful.

In Doko, *adaptable* means that capabilities can be configured, enabled, limited, or developed around workflows validated with each clinic. It does not mean that the software changes itself autonomously.

## Current product

| Capability | Status | What it does |
|---|---|---|
| Medical panel and appointment operations | **PRODUCTION** | Gives doctors and assistants a daily operational view for appointments, confirmation state, editing, cancellation, and clinic follow-up. |
| Google Calendar integration | **PRODUCTION** | Doko does not attempt to replace a mature calendar engine. It uses Google Calendar as the scheduling foundation and builds clinic-specific operational workflows around it. |
| Gmail confirmation workflows | **PRODUCTION** | Sends and tracks bounded appointment communications while keeping deterministic appointment state authoritative. |
| Patient portal and `doko.lat` directory | **PRODUCTION** | Publishes approved clinic information, services, location, and booking access without exposing private operational records. |
| Doko assistants | **PRODUCTION, BOUNDED** | Answer clinic-scoped questions and classify limited intent. They do not make medical decisions or override operational records. |
| Mi Centro | **PRODUCTION / OPERATOR USE** | Supports physician setup, digital presence, clinic implementation, protocol documentation, AI usage visibility, and operational administration. |
| Implementation protocols | **VALIDATED** | Turn observed clinic routines into reviewable reference workflows, clinic adaptations, training plans, and follow-up. |
| Doko Suffy | **IMPLEMENTED / NOT YET COMMERCIALLY VALIDATED** | Provides software and operational foundations for integrated medical-supply sourcing and fulfillment; commercial validation and expansion of physical logistics remain ahead. |

## How the system works

1. A clinic's approved identity, services, availability, and operating rules are configured.
2. Google Calendar remains the scheduling foundation and Doko synchronizes the operational view.
3. Deterministic rules establish appointment state, permissions, confirmation behavior, and write actions.
4. Bounded AI may classify an allowed intent, summarize sanitized implementation material, or improve readability.
5. A doctor, assistant, or operator remains responsible for protected actions and final decisions.
6. Observed friction is documented as a protocol or experiment before it becomes a reusable product capability.

## AI in Doko

Doko is AI-assisted, not AI-authoritative.

Gemini 2.5 Flash is used in bounded production and administrative paths. It can classify restricted question categories, help present approved clinic information, and review sanitized implementation sections. Deterministic application logic remains the source of truth for identity, permissions, appointment state, severity, financial actions, inventory actions, and protected writes.

Doko does not send Gmail message bodies, Google Calendar event payloads, or appointment records to Gemini. In the panel assistant, Gemini receives only a locally extracted concept package when bounded classification is needed. In implementation review, input is sanitized before analysis. Human approval remains the last control layer.

See [AI operations](docs/AI_OPERATIONS.md) and [privacy and safety](docs/PRIVACY_AND_SAFETY.md).

## Doko Suffy

Doko Suffy is an integrated medical-supply sourcing and fulfillment capability under progressive development. Software and operational foundations exist, while commercial validation and expansion of the physical logistics operation remain ahead.

It is not a separate startup and it does not represent inventory stored inside each clinic. Its intended progression is:

1. a controlled base catalog;
2. specialized sourcing when a clinic needs alternatives;
3. comparison of supplier information, product characteristics, documentation, availability, and price;
4. internal purchasing, warehouse, lot, and delivery operations;
5. organic expansion based on demonstrated demand.

Current subscription revenue is not presented as Suffy revenue, and future supply margins are not counted as current traction.

## Real-world validation

Doko is used in production by five active operational users: two paying gynecologists and three clinic assistants. A dated snapshot on July 27, 2026 showed:

- 330 appointment records visible for one gynecologist during the month;
- 87 appointment records visible for the second gynecologist;
- 417 appointment records visible across both clinic workflows in that snapshot.

These figures describe operational volume handled by the system. They do **not** mean Doko generated those patients. Their real use validates reliability, workflow fit, and the pressure the product must support.

The two founding physicians are real users and the first operational validation collaborators. Future founding physicians from additional specialties will help distinguish common workflows, specialty-specific workflows, optional capabilities, and problems that are genuinely worth solving in software. The term describes their validation role; they are not legal cofounders of Doko.

## Business model

Doko is bootstrapped and has received no outside investment.

- **Current Doko revenue:** recurring clinic subscriptions.
- **Excluded from Doko hackathon revenue:** standalone implementation, operational support, or digital-presence services contracted outside the subscription.
- **Future Doko revenue:** margin from Doko Suffy sourcing and fulfillment after that capability is commercially validated.

The operating strategy is to keep infrastructure efficient, reinvest subscription revenue into validated improvements, grow through trusted clinic relationships, and expand Suffy only as real demand supports it. This is a strategy, not a guaranteed forecast.

See [product and business](docs/PRODUCT_AND_BUSINESS.md) and [hackathon disclosures](docs/HACKATHON_DISCLOSURES.md).

## Evidence

The repository preserves dated design artifacts, handwritten notes, architecture decisions, production screenshots, load-test results, and disclosure boundaries.

- [Production evidence](docs/PRODUCTION_EVIDENCE.md)
- [Project evolution](docs/PROJECT_EVOLUTION.md)
- [Notebook evidence and translations](docs/NOTEBOOK_EVIDENCE_TRANSLATIONS.md)
- [Testing](docs/TESTING.md)
- [Load test report](docs/evidence/load-test-2026-07-15.md)

Private customer contact details, bank evidence, signed receipts, and confidential operational records are supplied through the official judging channel rather than committed to source control.

## What Doko is not

Doko is:

- not an electronic health record;
- not a replacement for medical judgment;
- not a clinic drawer-inventory system;
- not a pharmacy and not currently selling medication;
- not dependent on a single supplier;
- not only an appointment scheduler;
- not a collection of unrelated projects;
- not a one-prompt application;
- not designed to use AI merely because AI is available.

Doko is an intentionally engineered and iteratively validated product. AI tools have supported learning and implementation, but product decisions, scope, validation, and operational boundaries are established through direct observation, deterministic controls, testing, and human judgment.

## Repository and judging access

This repository is temporarily accessible for XPRIZE hackathon review and judging. After the judging and review period concludes, the repository will be private. It contains the reviewable application snapshot and supporting documentation, but no production credentials or confidential customer evidence.

For a technical entry point, see [architecture](docs/ARCHITECTURE.md). For the distinction between pre-program resources and work completed during the program period, see [hackathon disclosures](docs/HACKATHON_DISCLOSURES.md).
