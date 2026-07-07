"""
PlaceUp Career — User & related data store.

Backend is selected by USER_DATABASE_BACKEND:

  * ``firestore`` - Firebase/Google Cloud Firestore (production:
    users, sessions, resumes, preferences, alerts).

This module re-exports the Firestore implementation so every
``from app.db import user_store`` call site works unchanged.
"""
from __future__ import annotations

from app.db import firestore_user_store as _impl

consume_email_verification = _impl.consume_email_verification
consume_password_reset = _impl.consume_password_reset
count_role_requests = _impl.count_role_requests
count_user_applications = _impl.count_user_applications
count_tailor_requests_today = _impl.count_tailor_requests_today
create_auth_session = _impl.create_auth_session
create_alert = _impl.create_alert
create_resume = _impl.create_resume
create_role_request = _impl.create_role_request
create_user = _impl.create_user
delete_alert = _impl.delete_alert
delete_resume = _impl.delete_resume
delete_user = _impl.delete_user
get_agreement_for_user = _impl.get_agreement_for_user
get_alert_settings = _impl.get_alert_settings
get_auth_session = _impl.get_auth_session
get_auth_session_by_refresh_hash = _impl.get_auth_session_by_refresh_hash
get_preferences = _impl.get_preferences
get_role_request = _impl.get_role_request
get_user_by_email = _impl.get_user_by_email
get_user_by_id = _impl.get_user_by_id
get_user_by_phone = _impl.get_user_by_phone
list_agreements = _impl.list_agreements
list_alerts = _impl.list_alerts
list_events = _impl.list_events
list_resumes = _impl.list_resumes
list_role_requests = _impl.list_role_requests
list_tailor_queue = _impl.list_tailor_queue
list_users = _impl.list_users
list_user_applications = _impl.list_user_applications
get_tailor_queue_item = _impl.get_tailor_queue_item
mark_alert_read = _impl.mark_alert_read
mark_all_alerts_read = _impl.mark_all_alerts_read
mark_email_verified = _impl.mark_email_verified
record_agreement = _impl.record_agreement
record_event = _impl.record_event
revoke_all_refresh_tokens = _impl.revoke_all_refresh_tokens
revoke_auth_session = _impl.revoke_auth_session
revoke_user_sessions = _impl.revoke_user_sessions
rotate_auth_session = _impl.rotate_auth_session
set_active_resume = _impl.set_active_resume
set_user_password = _impl.set_user_password
update_role_request = _impl.update_role_request
upsert_email_verification = _impl.upsert_email_verification
upsert_password_reset = _impl.upsert_password_reset
upsert_tailor_queue_item = _impl.upsert_tailor_queue_item
upsert_user_application = _impl.upsert_user_application
update_tailor_queue_item = _impl.update_tailor_queue_item
update_resume_parsed_text = _impl.update_resume_parsed_text
update_alert_settings = _impl.update_alert_settings
update_preferences = _impl.update_preferences
update_user_profile = _impl.update_user_profile
