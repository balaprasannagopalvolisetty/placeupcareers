/**
 * Frontend error reporting hook.
 *
 * Goals:
 *   1. Catch unhandled errors (window.onerror) and unhandled promise
 *      rejections so silent failures become visible.
 *   2. Forward them to a remote tracker IF one is configured via
 *      VITE_SENTRY_DSN. Without the env var, we just console.error
 *      so dev tooling still works.
 *
 * Why not "import * as Sentry from @sentry/react"? Adding the SDK to
 * the bundle even when it is not configured ships ~80 KB to every
 * user. Instead we lazy-import on first init, which keeps the default
 * bundle lean.
 */

const DSN_KEY = "VITE_SENTRY_DSN";
const ENV_KEY = "VITE_SENTRY_ENVIRONMENT";

type ErrorReporter = (error: Error | unknown, context?: Record<string, unknown>) => void;

let reporter: ErrorReporter = (err, ctx) => {
  console.error("[observability]", err, ctx || {});
};

export const captureError: ErrorReporter = (err, ctx) => reporter(err, ctx);

let initialised = false;

export async function initObservability(): Promise<void> {
  if (initialised) return;
  initialised = true;

  window.addEventListener("error", (event) => {
    captureError(event.error || event.message, {
      source: "window.onerror",
      filename: event.filename,
      lineno: event.lineno,
      colno: event.colno,
    });
  });
  window.addEventListener("unhandledrejection", (event) => {
    captureError(event.reason, { source: "unhandledrejection" });
  });

  const env = import.meta.env as Record<string, string | undefined>;
  const dsn = env[DSN_KEY];
  if (!dsn) return;

  try {
    const sentryModuleName = "@sentry/react";
    const Sentry: any = await import(/* @vite-ignore */ sentryModuleName);
    Sentry.init({
      dsn,
      environment: env[ENV_KEY] || (import.meta.env.PROD ? "production" : "development"),
      release: env.VITE_GIT_SHA,
      tracesSampleRate: 0.1,
      sendDefaultPii: false,
    });
    reporter = (err, ctx) => {
      if (ctx) {
        Sentry.withScope((scope: any) => {
          scope.setExtras(ctx);
          Sentry.captureException(err);
        });
      } else {
        Sentry.captureException(err);
      }
    };
    console.info("[observability] Sentry initialised");
  } catch (err) {
    console.warn("[observability] Sentry init skipped (package not installed)", err);
  }
}
