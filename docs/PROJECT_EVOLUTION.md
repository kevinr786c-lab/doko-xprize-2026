# From Experiments to Production

This document records the preserved milestones behind Doko. It does not claim
that every intermediate version was saved or that version numbers form a
complete source-control history.

## Founder context

I entered 2026 after losing my hospital job and going through a period of
personal and financial instability. My experience did not begin in technology.
It came from hands-on hospital supply operations, warehouse and inventory
control, supplier interaction, replenishment, invoice handling, medical-supply
sourcing, surgical-kit preparation, shipping, receiving, and direct exposure
to clinic operations.

I am not a traditionally trained software engineer. In February, I began using
AI tools, documentation, experiments, and drawings to learn how to turn that
operational experience into a working service. I did not want to present a
disposable demo or claim skills I did not have. I wanted to build a stable
business, recover a path forward, and create a better future for my family.

AI tools helped me understand unfamiliar concepts and implement the product. I
provided the operational problems, clinic observation, product decisions,
safety boundaries, testing, customer support, and accountability for the final
service.

## Before the program period

| Period | Preserved evidence | Classification | What it means |
| --- | --- | --- | --- |
| February-March 2026 | Earlier GitHub experiments and a March archive | Pre-existing learning | I attempted and abandoned broad agent and medical-software experiments. They are not the submitted Doko product. |
| April 2026 | Independent Google Calendar booking-flow configuration and private payment evidence | Pre-existing customer relationship and standalone operational support | Before the program period, I had an existing relationship with one clinic and independently helped configure its Google Calendar booking flow, including availability, appointment duration, scheduling windows, and booking rules. This was standalone operational support for the clinic, not the submitted Doko platform. It gave me direct exposure to a real scheduling workflow that later informed product decisions during the program. |

The payment for that prior Calendar work is excluded from hackathon revenue.
The abandoned March archive contains obsolete credentials and service-account
material; it is excluded from this repository and must never be used as public
evidence.

Before Doko, I also spoke with a friend who independently sells supplies under
the name Grupo Pangea. We discussed helping each other in the future, but the
conversation never became a partnership, customer relationship, supplier
integration, team, or source of Doko revenue. Doko did not use Grupo Pangea's
code, inventory, customer list, operations, or income.

## Preserved program milestones

The official program period began on May 19, 2026.

| Date | Preserved artifact | What it demonstrates |
| --- | --- | --- |
| May 21-22 | `Untitled-2026-05-21-1050.excalidraw` | The earliest preserved integrated scene connecting login, OAuth, doctors, appointment radar, catalog, and orders. |
| May 27 | `01_especificaciones_tecnicas.md`, `03_cursorrules.md`, and related v4 planning | Formal planning for Flask, PostgreSQL, Cloud Run, Calendar, Gmail, roles, a patient portal, and Suffy. |
| May 29 | Devpost welcome email | I registered for Devpost after design work began, still within the official program period. |
| May 31 | `KB-TECH_Arquitectura_7_0.docx` | A more structured technical architecture milestone. |
| June 3 | `doko v8.1.zip`, `planificacion_tecnica_v9_0.md`, and `prompts_construccion_v9.md` | Movement from broad planning toward a controlled, integrated build. |
| June 4 | `planificacion_tecnica_v9_1.md` and `prompts_construccion_v9_1.md` | Human approval, deterministic risk rules, safer persistence, and clearer service boundaries. |
| June 10 | `Rediseno Doko v9.2.pdf` | A mobile-first visual redesign before direct clinic use reshaped product priorities. |
| June 19 onward | Founder field notes, clinic feedback, the current repository, and production behavior | Direct observation converted abstract modules into appointment, confirmation, search, portal, training, and operating workflows used by real doctors and assistants. |
| July 15 | `docs/evidence/load-test-2026-07-15.md` | Read-only concurrency validation of the panel assistant with deterministic fallbacks. |

I saved three June Excalidraw files named `dibujo +`, `dibujo v1`, and `dibujo`
because I initially believed each preserved a different part of the design.
Later review confirmed that they are byte-identical copies of one scene, not
three separate versions. I therefore treat them as one preserved artifact.

The scene is available in
[Excalidraw](https://excalidraw.com/#json=VgyefdhM4jCxfErc5ah_W,bPdTnMoIvqJagbSV4OOdww).
Drawing was part of my learning method: when I could see a problem but could
not yet explain it, a diagram helped me organize the flow and gave the AI
enough context to teach me the concepts more clearly.

## Decisions that changed Doko

### Reduce unnecessary clinical-data scope

Early experiments considered medical files, laboratory results, and broader
clinical agents. I removed those functions from the submitted product. Doko
focuses on operations and does not present AI as medical judgment.

### Keep deterministic rules authoritative

Application rules govern appointment state, permissions, confirmation timing,
incident severity, and operational writes. Gemini may classify an allowed
intent, explain a result, summarize sanitized material, or suggest a bounded
next question. It cannot override those rules.

### Integrate a mature scheduling foundation

Doko does not attempt to replace a mature calendar engine. It uses Google
Calendar as an integrated scheduling foundation and builds clinic-specific
operational workflows around it. These workflows include a clinic-adapted
panel, patient portal, appointment search, confirmation cycles, auditing,
operational guidance, and visible failure states.

### Learn from the assistant's actual work

Direct observation showed that software alone was not enough. Doko added
temporary holds, blocks, manual confirmation, released-slot handling,
read-only conversational search, cancellation from the medical panel, and
versioned implementation protocols based on real front-desk work.

### Build an adaptable ecosystem, not a fixed specialty template

Every specialty and clinic operates differently. Doko keeps a common
operational core, then activates a capability only when a real clinic needs and
validates it. A useful gynecology workflow should not be forced on cardiology,
and an unnecessary tool should remain disabled.

## Current product direction

Doko is more than an appointment interface. It is an adaptable operating
ecosystem intended to help small medical practices gain daily control over
appointments, confirmations, cancellations, communication, digital presence,
staff implementation, and repeatable processes.

The next validation step is to learn from physicians in additional
specialties. In this context, a "founding physician" means a real early user
who helps validate a specialty workflow. It does not mean a legal cofounder or
member of the Doko team.

Approved clinic practices can become versioned protocols and training
references. Doko does not replace medical responsibility or guarantee
regulatory compliance. It helps organize work and orient the process so that
the clinic can operate with greater clarity.

### Doko Suffy within the same ecosystem

Doko Suffy is Doko's integrated medical-supply sourcing and fulfillment
capability, designed to grow progressively as the software operation builds
recurring revenue, clinic relationships, operational knowledge, and trust.

Its intended progression is a base catalog, specialized sourcing, trusted
supplier relationships, internal logistics, and organic expansion based on
validated demand. References to Suffy inventory mean Doko's future sourcing,
warehouse, and fulfillment inventory, not inventory inside a clinic's drawers.
Potential procurement margin, supplier relationships, and employment are
future direction, not current traction or earned revenue.

Doko.lat supports digital presence and discoverability, but Doko does not
claim that a page automatically generates patients. The broader goal is to
earn trust: a physician may associate Doko with control, time, sourcing, and
continuous improvement, while a patient may associate Doko with clinics that
work to provide organized and attentive service.

## Future direction

If recurring subscriptions and clinic relationships continue to grow, I plan
to reinvest part of that revenue into implementation capacity, support,
sourcing, and logistics. This is a bootstrapped growth strategy, not a
guarantee. Longer-term capabilities will be added only after operational need,
safety, cost, and maintainability are validated.

## What the evidence proves

- Dated digital artifacts establish preserved milestones within the program
  period.
- The pocket notebook records questions, learning, discarded ideas, and
  product reasoning. It is undated and is not used by itself to establish
  dates.
- The current repository demonstrates the submitted implementation.
- The live service, sanitized logs, aggregate usage, payment evidence, and
  permissioned testimonials support operation and traction.

## What the evidence does not claim

- That every version between v1 and v9 was preserved.
- That Doko generated every appointment managed by the platform.
- That dashboard appointment counts equal new patients acquired through Doko.
- That abandoned pre-program experiments are part of the submitted code.
- That Grupo Pangea is a Doko partner, team member, customer, supplier
  integration, or source of revenue.
- That future Suffy procurement revenue, logistics, partnerships, or jobs
  already exist.
- That AI replaces medical or operational accountability.

## Submission evidence boundaries

### Public repository and project page

- Current source code and technical documentation.
- This project-evolution record.
- Selected notebook pages with original Spanish transcription and immediate
  English translation.
- Sanitized architecture, testing, AI-operation, and production-evidence
  summaries.
- Public product links and a demonstration using test data.

### Judges and organizers only

- Cash-basis P&L and supporting receipts.
- Payment evidence and customer classification.
- Permissioned testimonials or public testimonial links.
- Private operational proof needed to validate aggregate traction.

### Excluded completely

- Credentials, tokens, service-account files, and patient information.
- The obsolete February-March source archive.
- The unimplemented Grupo Pangea proposal and its independent resources.
- Undated notebook pages that do not add clear evidence.
- Unverified future revenue, partnerships, or capabilities.

## Core narrative

> I developed, deployed, and validated Doko during the program with AI-assisted
> learning and implementation. It grew from my operational experience,
> standalone pre-program Calendar support, and direct clinic observation into
> a production platform that helps doctors and assistants manage appointments,
> confirmations, digital presence, implementation, and repeatable processes.
> Deterministic controls remain authoritative, AI operates within bounded
> roles, and future capabilities are introduced only after real workflows prove
> that they are useful.
