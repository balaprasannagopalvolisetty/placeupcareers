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
            background: "rgba(64,18,18,0.7)",
            border: "1px solid rgba(59,130,246,0.35)",
            color: "#F1F5F9",
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
                background: "linear-gradient(135deg, #2563EB, #0EA5E9)",
                color: "#fff",
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
                border: "1px solid rgba(148,163,184,0.18)",
                background: "transparent",
                color: "#F1F5F9",
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
                background: "rgba(0,0,0,0.25)",
                borderRadius: 8,
                fontSize: 11,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                color: "rgba(148,163,184,0.65)",
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
