"""
Optional Sentry / OpenTelemetry initialization.

This is the one place that talks to the error-tracking SDK. Calling
`init_observability()` from main.py is a no-op unless SENTRY_DSN is set
in the environment — so dev and CI don't accidentally ship errors to a
production project, and we don't add a hard runtime dependency on the
SDK just to deploy.

To turn it on:

    pip install sentry-sdk==2.* fastapi
    export SENTRY_DSN=https://<key>@oXXXX.ingest.sentry.io/<project>
    export SENTRY_ENVIRONMENT=production
    export SENTRY_TRACES_SAMPLE_RATE=0.1   # 10% performance sampling

Once enabled, every unhandled exception, every 5xx, and every slow
request becomes a Sentry issue — replacing the "tail the logs and hope"
debugging loop.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


def init_observability() -> bool:
    """Try to bring Sentry online. Returns True on success."""
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        log.info("Sentry DSN not set; skipping error tracking init.")
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    except ImportError:
        log.warning(
            "SENTRY_DSN is set but sentry-sdk is not installed. "
            "Run `pip install 'sentry-sdk[fastapi]'` to enable error tracking."
        )
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
        release=os.getenv("SENTRY_RELEASE") or os.getenv("GIT_SHA"),
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
        profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.0")),
        # Don't ship request bodies — they can contain resumes / PII.
        send_default_pii=False,
        max_breadcrumbs=50,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
    )
    log.info("Sentry initialised.")
    return True
