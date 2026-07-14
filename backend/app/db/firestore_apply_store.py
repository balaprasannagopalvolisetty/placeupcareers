"""
Firestore store for the automated application system.

Collections (schemas illustrated in the architecture doc, section G):

    applications/{appId}
    application_profiles/{uid}
    tailored_docs/{uid}__{company}
    inbox_messages/{msgId}
    ats_adapters/{atsType}

Reuses the same Firestore client + retry helpers as `firestore_user_store` so
apply data lives beside user data in the `placeup-firebase-*` project. This
module also implements the `ApplyStore` protocol the orchestrator expects
(get_application / save_application / get_job / get_profile) plus the tailoring
pipeline's storage hooks.

Sensitive fields (EEO, any credentials) should be encrypted at the application
layer with Cloud KMS before they reach here — see the doc's Security section.
The class stays storage-only; encryption is layered by callers.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from app.db.firestore_user_store import _client, _now_iso, _with_retries

log = logging.getLogger("placeup.apply.store")

_APPLICATIONS = "applications"
_PROFILES = "application_profiles"
_TAILORED = "tailored_docs"
_INBOX = "inbox_messages"
_ADAPTERS = "ats_adapters"


def _company_key(uid: str, company: str, position_key: str = "") -> str:
    company_part = (company or "").strip().lower().replace("/", "_")
    position_part = (position_key or "general").strip().lower().replace("/", "_")
    return f"{uid}__{company_part}__{position_part}"


class FirestoreApplyStore:
    """Concrete ApplyStore. Instantiated per request in the API layer."""

    # --- applications ---
    def get_application(self, app_id: str) -> Optional[dict]:
        snap = _with_retries(lambda: _client().collection(_APPLICATIONS).document(app_id).get())
        if not snap.exists:
            return None
        return (snap.to_dict() or {}) | {"id": snap.id}

    def save_application(self, app: dict) -> dict:
        app_id = app.get("id") or uuid.uuid4().hex
        app["id"] = app_id
        app.setdefault("created_at", _now_iso())
        app["updated_at"] = _now_iso()
        _client().collection(_APPLICATIONS).document(app_id).set(app, merge=True)
        return app

    def list_applications(self, uid: str, limit: int = 500) -> list[dict]:
        rows = _with_retries(
            lambda: list(
                _client().collection(_APPLICATIONS).where("uid", "==", uid).limit(limit).stream()
            )
        )
        items = [(s.to_dict() or {}) | {"id": s.id} for s in rows]
        items.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
        return items

    def update_status(self, uid: str, app_id: str, status: str) -> Optional[dict]:
        app = self.get_application(app_id)
        if not app or app.get("uid") != uid:
            return None
        app["status"] = status
        app["updated_at"] = _now_iso()
        app.setdefault("history", []).append(
            {"at": _now_iso(), "kind": "user_status", "status": status, "detail": "set on tracker"}
        )
        return self.save_application(app)

    # --- jobs + profile (the orchestrator's read side) ---
    def get_job(self, job_id: str) -> Optional[dict]:
        """Resolve a full job from the production jobs database."""
        try:  # pragma: no cover - requires jobs DB
            from app.db.postgres import PostgresClient

            return PostgresClient().get_job_sync(job_id)
        except Exception as exc:
            log.debug("get_job(%s) unavailable: %s", job_id, exc)
            return None

    def get_profile(self, uid: str) -> dict:
        try:
            from app.db import user_store

            base = user_store.get_user_by_id(uid) or {}
        except Exception:
            base = {}
        prof = self.get_application_profile(uid) or {}
        return {**base, **{k: v for k, v in prof.items() if v not in (None, "", [], {})}}

    # --- application profiles (reusable ATS answers) ---
    def get_application_profile(self, uid: str) -> Optional[dict]:
        snap = _with_retries(lambda: _client().collection(_PROFILES).document(uid).get())
        return (snap.to_dict() or {}) if snap.exists else None

    def save_application_profile(self, uid: str, data: dict) -> dict:
        data["uid"] = uid
        data["updated_at"] = _now_iso()
        _client().collection(_PROFILES).document(uid).set(data, merge=True)
        return data

    # --- tailored docs cache ---
    def get_tailored_docs(self, uid: str, company: str, position_key: str = "") -> Optional[dict]:
        key = _company_key(uid, company, position_key)
        snap = _with_retries(lambda: _client().collection(_TAILORED).document(key).get())
        return (snap.to_dict() or {}) if snap.exists else None

    def save_tailored_docs(
        self,
        uid: str,
        company: str,
        data: dict,
        position_key: str = "",
    ) -> dict:
        key = _company_key(uid, company, position_key)
        data["created_at"] = data.get("created_at") or _now_iso()
        _client().collection(_TAILORED).document(key).set(data, merge=True)
        return data

    def render_and_store_tailored(
        self,
        uid: str,
        company: str,
        spec: dict,
        cover_letter: Optional[str] = None,
        position_key: str = "",
    ) -> dict:
        """Render the tailored spec (+ optional cover letter) to ATS-safe
        DOCX/PDF and upload to Cloud Storage. Returns the stored URLs. The
        resume DOCX is treated as the canonical resume_url (ATS-preferred);
        the PDF is also stored and returned for the UI/preview."""
        from app.services.apply import doc_storage
        from app.services.apply.resume_renderer import render_all

        resume = (spec or {}).get("resume") or spec or {}
        try:
            files = render_all(resume, cover_letter)
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("render_all failed for %s/%s: %s", uid, company, exc)
            return {"resume_url": None, "cover_letter_url": None}

        urls: dict[str, Optional[str]] = {}
        for name, data in files.items():
            urls[name] = doc_storage.store_document(
                uid,
                company,
                name,
                data,
                position_key=position_key,
            )

        return {
            "resume_url": urls.get("resume.pdf") or urls.get("resume.docx"),
            "resume_docx_url": urls.get("resume.docx"),
            "resume_pdf_url": urls.get("resume.pdf"),
            "cover_letter_url": urls.get("cover_letter.pdf") or urls.get("cover_letter.docx"),
            "cover_letter_docx_url": urls.get("cover_letter.docx"),
            "cover_letter_pdf_url": urls.get("cover_letter.pdf"),
        }

    def get_resume_text(self, uid: str, resume_id: Optional[str]) -> str:
        try:
            from app.db import user_store
            resumes = user_store.list_resumes(uid) or []
            selected = next((row for row in resumes if resume_id and row.get("id") == resume_id), None)
            selected = selected or next((row for row in resumes if row.get("active")), None)
            selected = selected or (resumes[0] if resumes else None)
            return str((selected or {}).get("parsed_text") or "")
        except Exception as exc:
            log.debug("get_resume_text unavailable: %s", exc)
            return ""

    # --- inbox ---
    def save_inbox_message(self, msg: dict) -> dict:
        msg_id = msg.get("id") or uuid.uuid4().hex
        msg["id"] = msg_id
        msg.setdefault("received_at", _now_iso())
        _client().collection(_INBOX).document(msg_id).set(msg, merge=True)
        return msg

    def list_inbox(self, uid: str, limit: int = 200) -> list[dict]:
        rows = _with_retries(
            lambda: list(
                _client().collection(_INBOX).where("uid", "==", uid).limit(limit).stream()
            )
        )
        items = [(s.to_dict() or {}) | {"id": s.id} for s in rows]
        items.sort(key=lambda r: r.get("received_at") or "", reverse=True)
        return items

    def resolve_uid_from_local(self, local_part: str) -> Optional[str]:
        """Map an inbox local-part (first.last) to a uid via the user store."""
        try:
            from app.db import user_store

            return user_store.get_uid_by_inbox_local(local_part)  # type: ignore
        except Exception:
            return None
