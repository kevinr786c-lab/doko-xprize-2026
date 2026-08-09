# Doko

**An adaptable operating ecosystem for small medical practices in Tijuana.**

Doko combines clinic operations, patient-facing digital presence, implementation support, bounded AI assistance, and a progressively developed medical-supply capability in one product. It is built from direct observation of real clinic work, then improved in small, testable steps.

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

The first production use is with gynecology practices. The goal is not to make every clinic identical. It is to establish a reliable operating core, document specialty-specific workflows, and add optional tools only after they prove useful.

## Current product

| Capability | Status | What it does |
|---|---|---|
| Medical panel and appointment operations | **PRODUCTION** | Gives doctors and assistants a daily operational view for appointments, confirmation state, editing, cancellation, and clinic follow-up. |
| Google Calendar integration | **PRODUCTION** | Uses a mature calendar engine as the scheduling foundation instead of rebuilding one. Doko adds clinic-specific controls and operational visibility around it. |
| Gmail confirmation workflows | **PRODUCTION** | Sends and tracks bounded appointment communications while keeping deterministic appointment state authoritative. |
| Patient portal and `doko.lat` directory | **PRODUCTION** | Publishes approved clinic information, services, location, and booking access without exposing private operational records. |
| Doko assistants | **PRODUCTION, BOUNDED** | Answer clinic-scoped questions and classify limited intent. They do not make medical decisions or override operational records. |
| Mi Centro | **PRODUCTION / OPERATOR USE** | Supports physician setup, digital presence, clinic implementation, protocol documentation, AI usage visibility, and operational administration. |
| Implementation protocols | **VALIDATED** | Turn observed clinic routines into reviewable reference workflows, clinic adaptations, training plans, and follow-up. |
| Doko Suffy | **IMPLEMENTED / NOT YET COMMERCIALLY VALIDATED** | Provides the foundation for integrated medical-supply sourcing, catalog, warehouse, purchasing, and delivery operations. |

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

Doko Suffy is Doko's integrated medical-supply sourcing and fulfillment capability, designed to grow progressively as the software operation builds recurring revenue, clinic relationships, operational knowledge, and trust.

It is not a separate startup and it does not represent inventory stored inside each clinic. Its intended progression is:

1. a controlled base catalog;
2. specialized sourcing when a clinic needs alternatives;
3. trusted supplier relationships and quality review;
4. internal purchasing, warehouse, lot, and delivery operations;
5. organic expansion based on demonstrated demand.

Current subscription revenue is not presented as Suffy revenue, and future supply margins are not counted as current traction.

## Real-world validation

Doko is operated with two paying gynecology practices. A dated snapshot on July 27, 2026 showed:

- 330 appointments visible for one practice during the month;
- 87 appointments visible for the second practice;
- 417 appointments visible across both practices in that snapshot.

These figures describe operational volume handled by the system. They do **not** mean Doko generated those patients. The practices' real use validates reliability, workflow fit, and the pressure the product must support.

Founding physicians are real users and early operational validation collaborators. They are not legal cofounders of Doko.

## Business model

Doko is bootstrapped and has received no outside investment.

- **Current revenue:** recurring clinic subscriptions.
- **Separate service revenue:** implementation or digital-presence work when clearly contracted outside the subscription.
- **Future revenue:** margin from Doko Suffy sourcing and fulfillment after that capability is commercially validated.

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

This repository is temporarily public for hackathon review. It is intended to return to private access after the review period. It contains the reviewable application snapshot and supporting documentation, but no production credentials or confidential customer evidence.

For a technical entry point, see [architecture](docs/ARCHITECTURE.md). For the distinction between pre-program resources and work completed during the program period, see [hackathon disclosures](docs/HACKATHON_DISCLOSURES.md).
