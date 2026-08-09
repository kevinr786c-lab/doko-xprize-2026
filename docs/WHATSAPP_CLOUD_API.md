# WhatsApp Cloud API validation

> **Status: CONTROLLED TESTING / EXPERIMENTAL / PRE-PRODUCTION.** This work is
> not presented as a live clinic capability in the hackathon submission.

This initial integration validates the connection between Meta's WhatsApp
Cloud API and Doko. The current endpoint can verify Meta's callback, receive
controlled test events, and run a bounded local responder for allowlisted test
recipients. It does not yet operate a clinic's WhatsApp account, replace email
confirmations, answer real patients, modify appointments, or store message
content.

The intended next step is to validate a bounded response flow with Meta's test
number and Dr. Demo before designing clinic onboarding. Production use would
also require business verification, clinic authorization, approved message
templates where applicable, operational safeguards, and a separate review of
privacy and consent.

## Separate configuration

Gemini and WhatsApp use separate credentials and controls:

```text
GEMINI_API_KEY
WHATSAPP_ACCESS_TOKEN
WHATSAPP_VERIFY_TOKEN
WHATSAPP_APP_SECRET
WHATSAPP_PHONE_NUMBER_ID
WHATSAPP_BUSINESS_ACCOUNT_ID
WHATSAPP_GRAPH_API_VERSION
WHATSAPP_RESPONDER_ACTIVO
WHATSAPP_TEST_RECIPIENTS
```

Secrets must be configured in the deployment environment. They must never be
committed to GitHub, pasted into public conversations, or included in public
screenshots. Phone Number IDs and WhatsApp Business Account IDs are identifiers
rather than access tokens, but Doko still keeps them in environment variables.

## Controlled Dr. Demo test

The optional automated test response is restricted to explicitly allowlisted
test recipients. It uses local rules and does not query Gemini, Google Calendar,
or Gmail. It does not modify appointments, replace the current email workflow,
or persist message bodies.

```text
WHATSAPP_GRAPH_API_VERSION=v25.0
WHATSAPP_RESPONDER_ACTIVO=true
WHATSAPP_TEST_RECIPIENTS=<ALLOWLISTED_TEST_NUMBER_IN_E164_FORMAT>
```

The recipient value contains digits only. This responder must remain disabled
for real clinics until the test flow and production requirements have been
validated.

## Meta callback

The deployed callback is:

```text
https://doko.lat/webhooks/whatsapp
```

Meta's **Verify token** field must contain the same value configured as
`WHATSAPP_VERIFY_TOKEN`. This is a private value selected by Doko; it is not the
Meta access token.

Before any production use, `WHATSAPP_APP_SECRET` must be configured so Doko can
validate the `X-Hub-Signature-256` signature on incoming POST requests. An
unsigned local test is not evidence of production readiness.

## Evidence boundary

A successful callback verification or test webhook proves transport-level
connectivity only. It does not prove that Doko operates WhatsApp for a clinic,
that the AI assistant answers patients through WhatsApp, or that Meta has
approved the production onboarding model. Those capabilities remain planned
work after formalization and provider requirements are completed.
