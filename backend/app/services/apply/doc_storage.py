"""
Storage for rendered tailored documents (resume + cover letter).

Uploads the bytes produced by `resume_renderer` to private Cloud Storage and
returns a durable `gs://` reference. A local directory exists only for
development/tests; production never writes ephemeral instance storage.

Object layout: `tailored/{uid}/{company_key}/{position_key}/{name}`.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

from app.config import settings

log = logging.getLogger("placeup.apply.storage")

_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _safe(part: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", (part or "").strip().lower()).strip("-") or "x"


def _content_type(name: str) -> str:
    for ext, ct in _CONTENT_TYPES.items():
        if name.endswith(ext):
            return ct
    return "application/octet-stream"


def store_document(
    uid: str,
    company: str,
    name: str,
    data: bytes,
    *,
    position_key: str = "",
) -> Optional[str]:
    """Persist one rendered document and return its private storage URI.

    Production is GCS-only. Development/tests may use the local fallback when
    no bucket is configured.
    """
    object_path = (
        f"tailored/{_safe(uid)}/{_safe(company)}/"
        f"{_safe(position_key or 'general')}/{_safe(name)}"
    )
    bucket = getattr(settings, "apply_docs_bucket", "") or ""
    if bucket:
        try:  # pragma: no cover - requires GCS
            from google.cloud import storage  # type: ignore

            client = storage.Client(project=settings.gcp_project_id or None)
            blob = client.bucket(bucket).blob(object_path)
            blob.upload_from_string(data, content_type=_content_type(name))
            # Prefer a durable gs:// reference; the app can mint a signed URL on
            # read. (Public URLs require the bucket to allow it.)
            return f"gs://{bucket}/{object_path}"
        except Exception as exc:
            log.warning("GCS upload failed (%s): %s", bucket, exc)
            if settings.is_production:
                return None

    if settings.is_production:
        log.error("APPLY_DOCS_BUCKET is required in production")
        return None

    # Development/test fallback only.
    try:
        base = getattr(settings, "apply_docs_local_dir", "") or "/tmp/placeup_tailored"
        full = os.path.join(base, object_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(data)
        return f"file://{full}"
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("local doc store failed: %s", exc)
        return None


def content_type_for(uri: str) -> str:
    return _content_type(uri or "")


def signed_url(uri: str, minutes: int = 30) -> Optional[str]:
    """Return a short-lived HTTPS URL for a `gs://` object so an external ATS
    (e.g. Recruitee's remote-CV field) can fetch it without the bucket being
    public. Requires the runtime SA to have token-signing (V4 signing via IAM
    `signBlob`, i.e. roles/iam.serviceAccountTokenCreator on itself). Returns
    None if signing isn't available — callers fall back to multipart upload."""
    if not uri or not uri.startswith("gs://"):
        return None
    try:  # pragma: no cover - requires GCS + signing
        from datetime import timedelta
        from google.cloud import storage  # type: ignore

        _, _, rest = uri.partition("gs://")
        bucket_name, _, blob_path = rest.partition("/")
        client = storage.Client(project=settings.gcp_project_id or None)
        blob = client.bucket(bucket_name).blob(blob_path)
        return blob.generate_signed_url(version="v4", expiration=timedelta(minutes=minutes), method="GET")
    except Exception as exc:
        log.info("signed_url unavailable for %s: %s", uri, exc)
        return None


def read_document(uri: str) -> Optional[bytes]:
    """Fetch a stored document's bytes from a `gs://` or `file://` URI.

    Used by the ownership-checked document-serving endpoint (so buckets stay
    private) and, later, by Tier A adapters that attach the resume on submit.
    Returns None if the URI can't be read.
    """
    if not uri:
        return None
    if uri.startswith("gs://"):
        try:  # pragma: no cover - requires GCS
            from google.cloud import storage  # type: ignore

            _, _, rest = uri.partition("gs://")
            bucket_name, _, blob_path = rest.partition("/")
            client = storage.Client(project=settings.gcp_project_id or None)
            return client.bucket(bucket_name).blob(blob_path).download_as_bytes()
        except Exception as exc:
            log.warning("GCS read failed for %s: %s", uri, exc)
            return None
    if uri.startswith("file://"):
        if settings.is_production:
            log.warning("Refusing local document URI in production")
            return None
        try:
            with open(uri[len("file://"):], "rb") as fh:
                return fh.read()
        except Exception as exc:
            log.warning("local read failed for %s: %s", uri, exc)
            return None
    return None
