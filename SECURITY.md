# Security Policy

Do not open a public issue containing credentials, OAuth tokens, patient data,
clinic records, payment evidence, or exploitable production details.

Security reports should be sent through the private contact listed in Doko's
privacy policy: <https://doko.lat/privacidad>.

## Supported environment

Only the current production deployment is supported. Local development must use
separate test credentials and fictitious data.

## Secret handling

- Keep secrets in environment variables or the deployment secret store.
- Never commit `.env`, Google credential JSON, database dumps, or private keys.
- Rotate any credential that appears in source control, logs, screenshots, or
  shared messages.
