"""
Structured JSON logging + per-request correlation IDs.

Why this exists
---------------
Cloud Logging works best when every log line is JSON. Plain-text logs
with `[INFO] message` are searchable but you can't pivot on user_id,
request_id, latency, status — and you can't build alert policies that
fire on, say, "5xx ratio > 5% in the last 5 minutes for path=/api/jobs".

What this adds
--------------
1. `configure_json_logging()` — installs a JSON formatter on the root
   logger. In production we emit one log record per line of JSON.
2. `RequestIdMiddleware` — generates (or trusts) an X-Request-Id
   header, stashes it in a contextvar, and tags every log line + the
   response with it. Lets you trace a single user request end-to-end
   across `/api/jobs` → DB query log → ATS worker → response.
3. `AccessLogMiddleware` — one structured line per request, with
   method, path, status, duration_ms, user_id (when known), and the
   request id. This replaces the noisy uvicorn default access logger
   and is what Cloud Run shows in the request log.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any, Dict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# ContextVar so any log call inside the request handler can attach the
# active request id without us threading it through every function arg.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
user_id_ctx: ContextVar[str] = ContextVar("user_id", default="")

log = logging.getLogger(__name__)


class JsonFormatter(logging.Formatter):
    """Render LogRecord as a single-line JSON document.

    Cloud Logging on Cloud Run auto-promotes recognised fields:
      - `severity` → log level (we map levelname)
      - `message`  → message body
      - `logging.googleapis.com/trace` → trace id (when running with
         the trace context env var; we leave it for later)
    """

    LEVEL_TO_SEVERITY = {
        "DEBUG": "DEBUG",
        "INFO": "INFO",
        "WARNING": "WARNING",
        "ERROR": "ERROR",
        "CRITICAL": "CRITICAL",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "severity": self.LEVEL_TO_SEVERITY.get(record.levelname, record.levelname),
            "message": record.getMessage(),
            "logger": record.name,
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        }
        request_id = request_id_ctx.get()
        if request_id:
            payload["request_id"] = request_id
        user_id = user_id_ctx.get()
        if user_id:
            payload["user_id"] = user_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Carry through `logger.info("...", extra={"foo": ...})` fields.
        for key, value in record.__dict__.items():
            if key in {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message", "asctime",
            }:
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = repr(value)
        return json.dumps(payload, ensure_ascii=False)


def configure_json_logging(level: str = "INFO") -> None:
    """Install JSON logging on the root logger. Safe to call twice."""
    root = logging.getLogger()
    root.setLevel(level.upper())
    # Wipe whatever logging.basicConfig set up earlier so we don't
    # double-emit each line (plain text + JSON).
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

    # Calm down noisy frameworks. uvicorn's access log is replaced by
    # AccessLogMiddleware below; SQLAlchemy debug logs flood Cloud Logging.
    for noisy in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel("WARNING")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach an X-Request-Id to every request/response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Trust an inbound id from the load balancer so traces survive
        # the hop from Firebase Hosting → Cloud Run → upstream service.
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_ctx.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers.setdefault("X-Request-Id", request_id)
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Emit one structured JSON line per request — replaces uvicorn.access."""

    async def dispatch(self, request: Request, call_next) -> Response:
        started = time.monotonic()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            duration_ms = round((time.monotonic() - started) * 1000, 2)
            # Skip the noise of health checks — Cloud Run pings these
            # constantly and they swamp the log.
            path = request.url.path
            if path not in {"/api/health", "/api/health/"}:
                log.info(
                    "request",
                    extra={
                        "http_method": request.method,
                        "http_path": path,
                        "http_status": status,
                        "duration_ms": duration_ms,
                        "client_ip": (request.client.host if request.client else None),
                        "user_agent": request.headers.get("user-agent", "")[:200],
                    },
                )
