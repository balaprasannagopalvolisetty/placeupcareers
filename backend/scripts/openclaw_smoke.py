"""Private Cloud Run smoke test for the isolated OpenClaw tailoring worker.

Run with the placeup-api service account. It prints only structural validation
results and never logs credentials or the generated document text.
"""
from __future__ import annotations

import json
import os

import httpx
from google.auth.transport.requests import Request
from google.oauth2 import id_token


def main() -> int:
    base_url = os.environ["OPENCLAW_URL"].strip().rstrip("/")
    service_token = os.environ["PLACEUP_SERVICE_TOKEN"]
    identity = id_token.fetch_id_token(Request(), base_url)
    payload = {
        "resume_text": (
            "Test Candidate\nSecurity Engineer\nSkills: Python, AWS, incident response.\n"
            "Experience: Built documented cloud security controls and investigated alerts."
        ),
        "job": {
            "id": "openclaw-smoke",
            "title": "Cloud Security Engineer",
            "company": "PlaceUp Test",
            "description": (
                "Responsibilities include reviewing AWS security controls and incident response. "
                "Requirements include Python and cloud security experience."
            ),
        },
        "candidate": {"name": "Test Candidate", "work_authorization": ""},
        "rules": {"truth_only": True, "no_new_numeric_claims": True, "output": "json"},
    }
    response = httpx.post(
        f"{base_url}/v1/tailor",
        headers={"Authorization": f"Bearer {identity}", "X-Service-Token": service_token},
        json=payload,
        timeout=150,
    )
    response.raise_for_status()
    data = response.json()
    resume_spec = data.get("resume_spec")
    cover_letter = data.get("cover_letter")
    ok = isinstance(resume_spec, dict) and isinstance(cover_letter, str) and bool(cover_letter.strip())
    print(json.dumps({"ok": ok, "resume_spec": isinstance(resume_spec, dict), "cover_letter_chars": len(cover_letter or "")}))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
