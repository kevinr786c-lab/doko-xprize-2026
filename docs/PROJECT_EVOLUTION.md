# From Experiments to Production

This document describes the preserved milestones behind Doko. It is not a
claim that every intermediate version was saved or that version numbers form a
complete source-control history.

## Founder context

The founder entered 2026 after losing a hospital job and going through a period
of personal and financial instability. He had practical experience in hospital
procurement, warehouse operations, suppliers, and clinic workflows, but no
formal software-engineering training.

In February, he began using AI tools to learn how software could turn that
experience into a working service. The goal was not to build a disposable
hackathon demonstration or to claim expertise he did not have. The goal was to
create a stable business, rebuild a path forward, and provide a better future
for his family.

AI tools explained unfamiliar concepts and helped implement the product. The
founder supplied the operational problems, field observation, product
decisions, safety boundaries, testing, customer support, and responsibility for
the resulting service.

## Before the program period

| Period | Preserved evidence | Classification | What it means |
| --- | --- | --- | --- |
| February-March 2026 | Earlier GitHub experiments and a March archive | Pre-existing learning | Broad agent and medical-software experiments were attempted and abandoned. They are not the submitted Doko product. |
| April 2026 | Standalone Google Calendar service and private payment evidence | Pre-existing customer relationship | The founder configured Calendar for one doctor and gained access to observe a real clinic workflow. The pre-program payment is outside the hackathon P&L. |

The abandoned March archive contains obsolete credentials and service-account
material. It must never be committed or used as public evidence.

An unimplemented proposal involving Grupo Pangea is also excluded. It did not
become a partnership, customer, supplier integration, or current Doko feature.

## Preserved hackathon milestones

The official program period began on May 19, 2026.

| Date | Preserved artifact | What it demonstrates |
| --- | --- | --- |
| May 21-22 | `Untitled-2026-05-21-1050.excalidraw` | Earliest preserved integrated scene connecting login, OAuth, doctors, appointment radar, catalog, and orders. |
| May 27 | `01_especificaciones_tecnicas.md`, `03_cursorrules.md`, and related v4 planning | A formal Flask, PostgreSQL, Cloud Run, Calendar, Gmail, role, portal, and Suffy architecture. |
| May 29 | Devpost welcome email | The founder joined Devpost after design work had begun, still within the official period. |
| May 31 | `KB-TECH_Arquitectura_7_0.docx` | A more structured technical architecture milestone. |
| June 3 | `doko v8.1.zip`, `planificacion_tecnica_v9_0.md`, and `prompts_construccion_v9.md` | Transition from broad planning toward a controlled integrated build. |
| June 4 | `planificacion_tecnica_v9_1.md` and `prompts_construccion_v9_1.md` | Human approval, deterministic risk rules, safer persistence, and clearer service boundaries. |
| June 10 | `Rediseno Doko v9.2.pdf` | A mobile-first visual redesign before direct clinic use reshaped the product priorities. |
| June 19 onward | Founder field notes, clinic feedback, current repository, and production behavior | Direct clinic observation converted abstract modules into appointment, confirmation, search, portal, training, and operating workflows used by real doctors and assistants. |
| July 15 | `docs/evidence/load-test-2026-07-15.md` | Read-only concurrency validation of the panel assistant with deterministic fallbacks. |

Three June Excalidraw files named `dibujo +`, `dibujo v1`, and `dibujo` are
byte-identical copies of one scene, not three separate versions. They are
treated as one preserved design artifact.

## Decisions that changed the product

### Reduce unnecessary clinical-data scope

Early experiments considered medical files, laboratory results, and broader
clinical agents. Doko removed those functions from the submitted product. The
current platform focuses on operations and does not present AI as medical
judgment.

### Keep deterministic rules in authority

Appointment state, permissions, confirmation timing, incident severity, and
operational writes are decided by application rules. Gemini may explain,
classify a redacted allowed intent, or draft a bounded analysis, but it cannot
override those rules.

### Use Google as an integrated scheduling layer

Google Calendar remains the reliable scheduling component. Doko adds the
clinic-specific panel, patient portal, appointment search, confirmation cycle,
audit trail, operational guidance, and failure visibility around it.

### Learn from the assistant's actual work

Direct observation showed that software alone was not enough. Doko added
temporary holds, blocks, manual confirmation, released-slot handling,
conversational read-only search, and versioned implementation protocols based
on real front-desk work.

### Narrow Suffy to a credible B2B operation

Early notes considered a broad range of services. The current Suffy scope is a
controlled B2B catalog, ordering, inventory, warehouse, supplier, and delivery
workflow. Potential partnerships and future procurement revenue are not
presented as current traction.

## What the evidence proves

- Dated digital artifacts establish preserved milestones inside the program
  period.
- The pocket notebook documents questions, learning, discarded ideas, and
  product reasoning; it is undated and is not used alone to establish dates.
- The current repository demonstrates the submitted implementation.
- The live service, sanitized logs, aggregate usage, payment evidence, and
  permissioned testimonials demonstrate operation and traction.

## What the evidence does not claim

- That every version between v1 and v9 was preserved.
- That Doko generated every appointment managed by the platform.
- That abandoned pre-program experiments are part of the submitted code.
- That Grupo Pangea is a current partner or supplier integration.
- That future Suffy, directory, or procurement revenue has already been earned.
- That AI replaces medical or operational accountability.

## How the submission evidence is organized

### Public repository and project page

- Current source code and technical documentation.
- This project-evolution record.
- Six selected notebook pages with Spanish transcription and English context.
- Sanitized architecture, testing, AI-operation, and production-evidence
  summaries.
- Public product links and a demonstration made with test data.

### Judges and organizers only

- Cash-basis P&L and supporting receipts.
- Payment evidence and customer classification.
- Permissioned testimonials or public testimonial links.
- Any private operational proof needed to validate aggregate traction.

### Excluded completely

- Credentials, tokens, service-account files, and patient information.
- The obsolete February-March source archive.
- The unimplemented Grupo Pangea proposal.
- Undated notebook pages that do not add clear evidence.
- Unverified future revenue, partnerships, or product capabilities.

## Core narrative

> Doko was built during the hackathon by one founder using AI-assisted learning
> and development. It grew from disclosed operational experience, an earlier
> standalone Calendar service, and direct clinic observation. Preserved designs
> became a production platform that helps doctors and assistants operate
> appointments, confirmations, public presence, supplies, and repeatable clinic
> workflows with deterministic safeguards and bounded AI.
