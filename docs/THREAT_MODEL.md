# Luviio threat model

## Assets

User sessions, Supabase records, payment intents, webhook signatures, seller data, uploaded images, invoices, and operational logs are protected assets.

## Trust boundaries

The browser is untrusted. Requests cross the ASGI boundary, authorization boundary, Supabase/RLS boundary, and payment-provider webhook boundary. Background jobs and admin services are trusted only for their explicitly scoped credentials.

## Primary abuse cases

- Broken object authorization: every user-owned query must be scoped to the authenticated subject.
- Payment replay or forged webhook: verify signatures, use idempotency, and persist provider event IDs.
- Credential leakage: service-role, Stripe, Resend, VAPID, and Sentry secrets stay server-side and are redacted from logs.
- Upload abuse: enforce size/type limits, sanitize filenames, and never execute uploaded content.
- Brute force and resource exhaustion: apply rate limits, body limits, bounded pagination, and queue backpressure.
- Log injection/PII exposure: sanitize correlation IDs and redact headers, cookies, tokens, payment data, and sensitive payloads.

## Controls

Pydantic validation, explicit RBAC policies, Supabase RLS, signed webhooks, request/correlation IDs, structured redacted logs, security headers, dependency auditing, coverage gates, and CI lint/type checks are required controls.

## Incident response

Use `request_id` and `correlation_id` to find a request across logs. Revoke affected credentials, disable compromised feature flags, inspect audit/security logs, replay only verified webhook events, and document the incident without storing secrets or raw PII.
