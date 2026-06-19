/**
 * Frontend error reporting hook.
 *
 * Catches unhandled errors + promise rejections and, when VITE_SENTRY_DSN is
 * set, forwards them to Sentry (lazy-loaded). Without the DSN it just
 * console.errors, so dev tooling still works and the bundle stays lean.
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
    // Literal dynamic import so Vite code-splits @sentry/react into a lazy
    // chunk only fetched when a DSN is configured (guarded by the return above).
    const Sentry: any = await import("@sentry/react");
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
    console.warn("[observability] Sentry init skipped", err);
  }
}
