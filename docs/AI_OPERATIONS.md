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

### Contextual continuity - CONTROLLED TESTING

Doko has a first, structured contextual-continuity phase enabled only for Dr.
Demo through `PANEL_ASSISTANT_CONTEXT_DEMO_EMAIL`. The context is ephemeral,
session-scoped, and expires after 10 minutes, with a maximum of two follow-ups.
It does not store the question or answer as free text, operational facts,
patient data, appointment content, or Google Workspace payloads. It keeps only
minimal continuity metadata such as category, referent, origin, and
non-reversible HMAC fingerprints used to isolate the actor, doctor, and
appointment.

The context is invalidated when the actor, doctor, or appointment changes, or
when the appointment is no longer current. A self-contained question replaces
or discards the previous context. Agenda searches do not reuse this context.
It only helps resolve short references such as "why?" or "what could be the
causes?"; Doko re-reads the real facts from its deterministic state before
producing an explanation. This context grants no new action or authority to
the model. It remains CONTROLLED TESTING and is not a general capability for
all clinics.

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
- Make medical decisions.
- Send an email outside a programmed and authorized workflow.
- Approve a clinic protocol or evaluate an employee by itself.
- Purchase stock, move money, complete a delivery, or perform any other protected write.

This boundary is intentional: language models assist with language; explicit
rules, verified records, and people retain operational authority.

For an AI-assisted workflow, the operating sequence is deterministic rules,
bounded AI interpretation, deterministic validation, and human authorization
when the consequence requires it.

## WhatsApp controlled test

The WhatsApp Cloud API prototype is in controlled testing, not clinic
production. It verifies webhook connectivity, receives controlled events, and
uses a local deterministic responder limited by an allowlist. The current
responder does not query Gemini, Google Calendar, or Gmail and cannot change an
appointment. It is not used with live patients.

## Future direction

Future research will evaluate whether Doko AI can take a more operational role inside explicitly authorized capabilities. Deterministic rules will continue to protect core invariants, permissions, and protected writes. New AI-enabled actions must be introduced through controlled experiments, narrow permissions, auditable behavior, and human authorization where the consequence requires it. This is a research direction, not a claim of current autonomous operation.
