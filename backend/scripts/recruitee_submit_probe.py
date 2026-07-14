#!/usr/bin/env python3
"""
One-off probe to confirm Recruitee's candidate-apply field names against a REAL
offer BEFORE relying on the production adapter.

Recruitee's public Careers Site API (`POST /offers/{slug}/candidates`, no auth)
documents the multipart candidate fields. This script builds
the same request the RecruiteeAdapter sends and lets you (a) print it (dry run,
default) to eyeball the field names, and (b) actually POST it to a real offer
with --live to confirm a 201 and see the response body.

It is intentionally self-contained (only needs `httpx`) so it runs without the
full app/config import chain. Whatever field names you confirm here, lock into
`app/services/apply/adapters_tier_a.py::RecruiteeAdapter.submit`.

Examples
--------
Dry run (see exactly what would be sent):
    python -m scripts.recruitee_submit_probe --company hello --offer-slug engineer \
        --name "Bala V" --email you@example.com --phone 555-1234 --resume ./resume.pdf

Real submission to a live offer (creates a real candidate!):
    python -m scripts.recruitee_submit_probe --company hello --offer-slug engineer \
        --name "Bala V" --email you@example.com --resume ./resume.pdf --live

"""
from __future__ import annotations

import argparse
import json
import sys


def build_request(company: str, slug: str, name: str, email: str, phone: str,
                  cover_letter: str) -> tuple[str, dict]:
    """Mirror RecruiteeAdapter's documented multipart candidate fields."""
    endpoint = f"https://{company}.recruitee.com/api/offers/{slug}/candidates"
    candidate: dict = {"name": name, "email": email}
    if phone:
        candidate["phone"] = phone
    if cover_letter:
        candidate["cover_letter"] = cover_letter
    return endpoint, {"candidate": candidate}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Probe Recruitee candidate-apply field names.")
    ap.add_argument("--company", required=True, help="Recruitee subdomain, e.g. 'hello' in hello.recruitee.com")
    ap.add_argument("--offer-slug", required=True, help="Offer slug from the careers URL")
    ap.add_argument("--name", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--phone", required=True)
    ap.add_argument("--cover-letter", default="", help="Cover-letter text, or @path to read from a file")
    ap.add_argument("--resume", required=True, help="Local resume file -> multipart candidate[cv] upload")
    ap.add_argument("--live", action="store_true", help="Actually POST (default: dry-run print only)")
    a = ap.parse_args(argv)

    cover = a.cover_letter
    if cover.startswith("@"):
        with open(cover[1:], encoding="utf-8") as fh:
            cover = fh.read()

    endpoint, body = build_request(a.company, a.offer_slug, a.name, a.email, a.phone, cover)

    with open(a.resume, "rb") as fh:
        resume_bytes = fh.read()

    print("== Recruitee submit probe ==")
    print("POST", endpoint)
    print("mode: multipart/form-data")
    print("fields:", json.dumps({f"candidate[{k}]": v for k, v in body["candidate"].items()}, indent=2))
    print(f"file:   candidate[cv] = <{len(resume_bytes)} bytes from {a.resume}>")

    if not a.live:
        print("\n(dry-run — pass --live to actually submit to the real offer)")
        return 0

    try:
        import httpx
    except ImportError:
        print("ERROR: httpx is required for --live (pip install httpx)", file=sys.stderr)
        return 2

    print("\nSubmitting for real ...")
    with httpx.Client(timeout=30) as client:
        data = {f"candidate[{k}]": v for k, v in body["candidate"].items()}
        files = {"candidate[cv]": ("resume.pdf", resume_bytes, "application/pdf")}
        resp = client.post(endpoint, params={"async": "true"}, data=data, files=files)

    print("== response ==")
    print("status:", resp.status_code)
    print("body:", resp.text[:2000])
    if resp.status_code == 201:
        print("\nSUCCESS (201). These field names are correct — lock them into RecruiteeAdapter.submit.")
    elif resp.status_code == 422:
        print("\n422 VALIDATION: read the body above — it names the fields Recruitee expected/rejected.")
    else:
        print(f"\nUnexpected {resp.status_code} — inspect the body to adjust field names.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
