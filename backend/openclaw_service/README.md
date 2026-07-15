# PlaceUp OpenClaw Tailoring Service

This is a separate, private Cloud Run service. It is deliberately not bundled
into `placeup-api`, has no public ingress, no browser/channel tools, and no ATS
submission permissions. The API authenticates with Cloud Run IAM plus an
application service token. Candidate prompts are written to an ephemeral 0600
file and removed after each request.

It is disabled in PlaceUp unless all three settings are present:
`OPENCLAW_TAILOR_ENABLED=true`, `OPENCLAW_TAILOR_URL`, and the
`OPENCLAW_TAILOR_TOKEN` secret. A provider key must be configured on this
service before deployment. Until then the existing grounded tailoring pipeline
continues unchanged.
