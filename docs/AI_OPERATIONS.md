# AI Operations

## Production AI

Doko uses Gemini 2.5 Flash in production, but the model is not the source of
truth for permissions, appointment state, incident severity, or financial and
inventory actions.

### Patient assistant

The patient assistant answers administrative questions using public or
clinic-configured information such as services, published prices, location,
payment methods, insurance, scheduling, and confirmation instructions.

It cannot diagnose, recommend treatment, prescribe, interpret symptoms,
change appointments, or access another clinic's information. Medical questions
are redirected to the clinic.

### Doko Assistant in the medical panel

Most questions are answered through local rules. Conversational appointment
search is also interpreted locally and never consumes Gemini quota.

When local rules cannot classify an operational question:

1. Doko extracts only allowed concepts.
2. Names, dates, email addresses, phone numbers, UUIDs, notes, and free text are
   removed.
3. Gemini may return one category from an allowlist.
4. Doko reads the real local state and produces the final explanation.

Gemini never receives appointment details and never writes to the agenda.

### Operational implementation review

An admin can manually request a review of a completed implementation section.
Doko sanitizes the text and asks Gemini for at most three structured findings:
what is defined, what remains unclear, and a recommended follow-up question or
related protocol. A human chooses whether to add, ask, adapt, or discard each
finding.

### Supervisor and controlled business agents

The supervisor consolidates deterministic audits and business signals. Gemini
can improve readability, while the alert level remains rule-based. Commercial,
purchasing, finance, inventory, traceability, and delivery agents are
human-triggered assistants. They do not autonomously contact customers,
purchase stock, move money, or change protected records.

## Limits and fallbacks

- Panel assistant default clinic limit: 50 Gemini classifications per day.
- Panel assistant default user limit: 20 classifications per hour.
- Panel assistant default global limit: 500 classifications per day.
- Operational implementation: 20 reviews per clinic and 100 globally per day.
- Deterministic responses remain available when a limit is reached.
- Token and cost estimates are recorded without prompts or patient content.

## Key decisions

AI is permitted to classify, summarize, and suggest. It is not permitted to:

- Grant access.
- Set incident severity.
- Create, edit, confirm, cancel, or release an appointment.
- Send an email outside the programmed workflow.
- Approve a clinic protocol or evaluate an employee by itself.
- Purchase inventory, assign money, or complete delivery.

This separation is intentional: Doko applies AI where language is useful and
deterministic rules where operational correctness is required.
