"""Repair glued words in scraped job descriptions (A3).

Scrapers that strip HTML without preserving whitespace produce artifacts like
``WhatYou'llDo`` or ``Responsibilities:Designand build`` — the line breaks and
inter-element spaces are gone, so adjacent words collapse into one token.

A naive ``re.sub(r'([a-z])([A-Z])', r'\\1 \\2', text)`` is too aggressive: it
shatters legitimate camelCase tech tokens (``JavaScript`` -> ``Java Script``,
``GitHub`` -> ``Git Hub``, ``PyTorch`` -> ``Py Torch``). So this module is
*gated*:

  1. It only inspects whitespace-delimited tokens that *look* glued
     (multiple internal humps, an apostrophe-joined word, or a sentence-
     punctuation join like ``build.You``).
  2. Tokens in :data:`PRESERVE` (known products/acronyms) are never split.
  3. Runs of capitals (``gRPC``, ``APIs``, ``IDs``) are kept intact.

The goal is to fix the obvious scrape damage while leaving real identifiers
alone. It is deliberately conservative — when in doubt, it leaves the token
untouched. Prefer keeping ATS-provided HTML over relying on this; this is the
fallback for the HTML-stripped path.
"""

from __future__ import annotations

import re

# Known tokens that contain legitimate internal capitals. Compared lowercased,
# so casing in the JD does not matter. Extend as new false-positives surface.
PRESERVE: frozenset[str] = frozenset(
    {
        "javascript", "typescript", "github", "gitlab", "gitops", "devops",
        "devsecops", "pytorch", "tensorflow", "nodejs", "node.js", "nextjs",
        "next.js", "nestjs", "reactjs", "vuejs", "graphql", "postgresql",
        "mongodb", "mysql", "dynamodb", "powerbi", "powershell", "bigquery",
        "openai", "openshift", "openssl", "oauth", "openid", "saml", "grpc",
        "restapi", "macos", "ios", "ipados", "macbook", "iphone", "ipad",
        "kubernetes", "dotnet", "asp.net", "vmware", "salesforce", "workday",
        "servicenow", "quickbooks", "linkedin", "youtube", "wordpress",
        "fastapi", "django", "flask", "numpy", "scipy", "pandas", "matplotlib",
        "scikit", "sklearn", "kafka", "rabbitmq", "elasticsearch", "redis",
        "datadog", "pagerduty", "snowflake", "databricks", "terraform",
        "ansible", "jenkins", "circleci", "dbeaver", "intellij", "vscode",
        "webpack", "babel", "eslint", "playwright", "cypress",
    }
)

# A "hump" is a lowercase letter immediately followed by an uppercase one.
_HUMP_RE = re.compile(r"[a-z][A-Z]")
# Split point: lowercase/digit -> uppercase that starts a new word. Keeps
# capital runs together by requiring the uppercase to be followed by a
# lowercase letter (so "gRPC" is untouched, "buildYou" splits at "You").
_SPLIT_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z][a-z])")
# Sentence-punctuation glue: "build.You", "duties:Design" -> add a space after.
_PUNCT_GLUE_RE = re.compile(r"([.,;:!?])(?=[A-Z])")
# Apostrophe-joined contraction glued to the next word: "You'llDo".
_CONTRACTION_GLUE_RE = re.compile(r"((?:'|’)(?:ll|re|ve|s|d|t|m))(?=[A-Z])", re.I)

_TOKEN_RE = re.compile(r"\S+")
# A token is a de-glue candidate when it has 2+ humps, or contains a
# contraction-followed-by-capital, or a punctuation-glue join.
_GLUED_SIGNATURE_RE = re.compile(
    r"[a-z][A-Z].*[a-z][A-Z]"          # >= 2 humps
    r"|(?:'|’)(?:ll|re|ve|s|d|t|m)[A-Z]"  # contraction + capital
    r"|[.,;:!?][A-Z]"                  # punctuation + capital
)


def _strip_outer_punct(token: str) -> tuple[str, str, str]:
    """Split a token into (leading_punct, core, trailing_punct)."""
    m = re.match(r"^([^\w]*)(.*?)([^\w]*)$", token, re.S)
    if not m:
        return "", token, ""
    return m.group(1), m.group(2), m.group(3)


def _is_protected(core: str) -> bool:
    low = core.lower().strip(".")
    if low in PRESERVE:
        return True
    # All-caps acronyms ("API", "AWS", "SQL") and single-cap words ("Design").
    if core.isupper():
        return True
    if _HUMP_RE.search(core) is None:
        return True
    return False


def _deglue_token(token: str) -> str:
    lead, core, trail = _strip_outer_punct(token)
    if not core or _is_protected(core):
        return token
    if not _GLUED_SIGNATURE_RE.search(core):
        return token
    fixed = _CONTRACTION_GLUE_RE.sub(r"\1 ", core)
    fixed = _PUNCT_GLUE_RE.sub(r"\1 ", fixed)
    fixed = _SPLIT_BOUNDARY_RE.sub(" ", fixed)
    # Re-protect any sub-token that turned out to be a known product.
    parts = []
    for part in fixed.split(" "):
        parts.append(part)
    return lead + " ".join(p for p in parts if p) + trail


def deglue_text(text: str) -> str:
    """Return *text* with scrape-glued words separated, tech tokens preserved."""
    if not text:
        return text
    # Always normalize punctuation-glue first at the string level so that
    # joins inside otherwise-clean tokens are caught.
    text = _PUNCT_GLUE_RE.sub(r"\1 ", text)
    return _TOKEN_RE.sub(lambda m: _deglue_token(m.group(0)), text)


def looks_glued(text: str, *, min_hits: int = 2) -> bool:
    """Heuristic: does *text* contain enough glued artifacts to warrant repair?"""
    if not text:
        return False
    hits = len(_GLUED_SIGNATURE_RE.findall(text))
    return hits >= min_hits
