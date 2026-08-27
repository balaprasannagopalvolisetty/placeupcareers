You are extracting structured facts from a competitor page for PlaceUp Career's
competitive intelligence store. Be terse. This output is stored, not read aloud.

Entity: {{ENTITY}}
Source: {{URL}}

Return ONLY lines in `key: value` form. No preamble, no headings, no commentary.
Use these keys where the page supports them, and omit any you cannot support:

positioning: one sentence, their words
target_user: who they say it is for
pricing_tiers: name @ price / period, comma separated
free_tier: what the free plan actually includes
key_features: up to 6, comma separated
visa_or_sponsorship: what they claim about visa/sponsorship, or "none"
countries: coverage claimed, or "US only" / "unclear"
data_sources: where they say their jobs come from
proof: named customers, counts, or testimonials they lead with
new_since: anything flagged as new, beta, or recently launched
weakness_signal: any limitation they disclose themselves

Rules:
- Only what the page states. Never infer, never fill a gap with a plausible value.
- If the page is a paywall, error, or bot-block, return exactly: blocked: true
- Keep every value under 200 characters.

PAGE TEXT:
{{TEXT}}
