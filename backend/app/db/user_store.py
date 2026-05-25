"""
PlaceUp Career — User & related data store.

In production, all user data lives in Firestore. This module re-exports
the Firestore implementations so every ``from app.db import user_store``
call site works unchanged.

The old SQLite helpers are no longer used and have been removed.
"""
from __future__ import annotations

# Re-export all functions from the Firestore user store.
# The call sites import ``user_store.create_user``, etc.
from app.db.firestore_user_store import (  # noqa: F401
    consume_email_verification,
    consume_password_reset,
    count_user_applications,
    create_auth_session,
    create_alert,
    create_resume,
    create_user,
    delete_alert,
    delete_resume,
    delete_user,
    get_alert_settings,
    get_auth_session,
    get_auth_session_by_refresh_hash,
    get_preferences,
    get_user_by_email,
    get_user_by_id,
    list_alerts,
    list_resumes,
    list_users,
    list_user_applications,
    mark_alert_read,
    mark_all_alerts_read,
    mark_email_verified,
    revoke_all_refresh_tokens,
    revoke_auth_session,
    revoke_user_sessions,
    rotate_auth_session,
    set_active_resume,
    set_user_password,
    upsert_email_verification,
    upsert_password_reset,
    upsert_user_application,
    update_resume_parsed_text,
    update_alert_settings,
    update_preferences,
    update_user_profile,
)
