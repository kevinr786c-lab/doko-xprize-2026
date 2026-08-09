# AI Operations

## Operating principle

Doko uses Gemini 2.5 Flash in production where language interpretation is
useful. Deterministic application state remains authoritative.

Gemini does not grant permissions, decide appointment state, set incident
severity, approve financial or inventory actions, or execute protected clinic
operations. Doko is not an autonomous general clinic agent.

## Production uses

### Patient assistant

The patient assistant answers administrative questions from the approved
profile of the selected clinic, including services, published prices, location,
payment methods, insurance, scheduling guidance, and confirmation instructions.

It cannot diagnose, recommend treatment, prescribe, interpret symptoms, change
appointments, or access another clinic's information. Medical questions are
redirected to the clinic.

### Doko Assistant in the medical panel

Local rules answer most operational questions. Conversational appointment
search is also interpreted locally and does not consume Gemini quota.

When local rules cannot classify an allowed operational question:

1. Doko extracts only the concepts required for classification.
2. It removes names, dates, email addresses, phone numbers, UUIDs, notes, and
   unrestricted free text.
3. Gemini may return one category from an allowlist.
4. Doko reads the real local state and produces the final explanation.

Gemini never receives appointment records and never writes to the agenda.

### Operational implementation review

An administrator can manually request a review after completing an
implementation section. Doko sanitizes the text and asks Gemini for no more
than three structured findings: what is defined, what remains unclear, and a
recommended follow-up question or related protocol.

A human decides whether to add the finding to the draft, ask the physician,
adapt a protocol, or discard it. Gemini cannot approve a protocol or grade an
assistant.

### Supervisor and controlled business agents

The supervisor consolidates deterministic audits and operating signals. Gemini
may improve the readability of a summary, while alert severity remains
rule-based.

Commercial, purchasing, finance, inventory, traceability, and delivery agents
are human-triggered assistants. They do not autonomously contact customers,
purchase stock, move money, or modify protected records.

## Limits and fallbacks

- Panel assistant default clinic limit: 50 Gemini classifications per day.
- Panel assistant default user limit: 20 classifications per hour.
- Panel assistant default global limit: 500 classifications per day.
- Operational implementation limit: 20 reviews per clinic and 100 globally per
  day.
- Deterministic responses remain available when a limit is reached or Gemini
  is unavailable.
- Token and cost estimates are recorded without prompts or patient content.

## Decision boundary

AI may classify, summarize, suggest, and improve readability. It may not:

- Grant access.
- Set incident severity.
- Create, edit, confirm, cancel, release, or reschedule an appointment.
- Send an email outside a programmed and authorized workflow.
- Approve a clinic protocol or evaluate an employee by itself.
- Purchase inventory, allocate money, or complete a delivery.

This boundary is intentional: language models assist with language; explicit
rules, verified records, and people retain operational authority.

## Future direction

Additional assistants may be evaluated for clinic communication and new
specialty workflows. They are not presented as current production capability
until the workflow, permissions, privacy boundaries, and human fallback have
been tested with an authorized clinic.
