# PlaceUp OpenClaw Tailoring Service

This is a separate, private Cloud Run service. It is deliberately not bundled
into `placeup-api`, permits no unauthenticated invocation, has no browser or
channel tools, and has no ATS submission permissions. The API authenticates
with a Google-signed Cloud Run identity token plus an application service
token. Candidate prompts are passed only to the isolated one-shot child
process and are never written to logs.

It is disabled in PlaceUp unless all three settings are present:
`OPENCLAW_TAILOR_ENABLED=true`, `OPENCLAW_TAILOR_URL`, and the
`OPENCLAW_TAILOR_TOKEN` secret. A provider key must be configured on this
service before deployment. Until then the existing grounded tailoring pipeline
continues unchanged.

The production default is `ollama-cloud/glm-5.2`. This is the current hosted
catalog ID for the same GLM-5.2 Cloud model exposed as `glm-5.2:cloud` through
Ollama's local-launch route. It uses OpenClaw's
dedicated Ollama Cloud provider directly and does not run an Ollama daemon or
model weights inside Cloud Run. Store an Ollama Cloud key in Secret Manager as
`OLLAMA_API_KEY`; never put it in this repository or paste it into application
configuration.

Deploy the worker first without changing the API, run the private smoke job,
and only then pass `-EnableApiIntegration` to the deployment script. This
prevents an unavailable or unsubscribed hosted model from adding latency to
the production tailoring fallback.
