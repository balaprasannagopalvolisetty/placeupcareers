import { Component, ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** Optional override for the fallback shown when a child throws. */
  fallback?: (error: Error, reset: () => void) => ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Top-level guard against React render errors. The previous behaviour
 * was a fully blank dashboard whenever the Jobs page threw — which is
 * exactly the "jobs page keeps breaking" symptom users were reporting.
 *
 * Catching here lets the rest of the app stay usable AND gives the user
 * an explicit retry path instead of a frozen tab.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: unknown) {
    // Forward to console so Sentry / Cloud Logging picks it up via
    // existing window.onerror hooks.
    console.error("[ErrorBoundary] Caught render error:", error, info);
  }

  reset = () => this.setState({ error: null });

  render() {
    if (this.state.error) {
      if (this.props.fallback) return this.props.fallback(this.state.error, this.reset);
      return (
        <div
          role="alert"
          style={{
            margin: "24px auto",
            maxWidth: 540,
            padding: "20px 22px",
            borderRadius: 16,
            background: "var(--pu-64-18-18-07)",
            border: "1px solid var(--pu-59-130-246-035)",
            color: "var(--pu-f1f5f9-t)",
            fontFamily: "'Plus Jakarta Sans', sans-serif",
          }}
        >
          <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 6 }}>
            Something went wrong on this screen
          </div>
          <div style={{ fontSize: 13, opacity: 0.8, marginBottom: 14, lineHeight: 1.5 }}>
            We caught the error so the rest of the app stays working. Try reloading this view,
            or jump back to your dashboard.
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button
              onClick={this.reset}
              style={{
                padding: "9px 14px",
                borderRadius: 10,
                border: "none",
                background: "linear-gradient(135deg, var(--pu-2563eb), var(--pu-0ea5e9))",
                color: "var(--pu-ffffff-t)",
                fontWeight: 600,
                fontSize: 13,
                cursor: "pointer",
              }}
            >
              Retry
            </button>
            <button
              onClick={() => { window.location.href = "/dashboard"; }}
              style={{
                padding: "9px 14px",
                borderRadius: 10,
                border: "1px solid var(--pu-148-163-184-018)",
                background: "transparent",
                color: "var(--pu-f1f5f9-t)",
                fontWeight: 500,
                fontSize: 13,
                cursor: "pointer",
              }}
            >
              Back to dashboard
            </button>
          </div>
          {import.meta.env.DEV && (
            <pre
              style={{
                marginTop: 14,
                padding: 10,
                background: "var(--pu-0-0-0-025)",
                borderRadius: 8,
                fontSize: 11,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                color: "var(--pu-148-163-184-065)",
                maxHeight: 200,
                overflowY: "auto",
              }}
            >
              {String(this.state.error?.stack || this.state.error?.message || this.state.error)}
            </pre>
          )}
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
