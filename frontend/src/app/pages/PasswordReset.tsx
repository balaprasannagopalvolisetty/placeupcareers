/**
 * /forgot-password, /reset-password, /verify-email pages.
 *
 * Lean implementation that only renders the surface area needed for
 * the auth flow. The actual reset/verify endpoints live in
 * backend/app/api/password_reset.py — wire SendGrid (or your provider
 * of choice) into _send_email() there and these pages light up.
 */

import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

const F = { sans: "'Plus Jakarta Sans', sans-serif" };
const T = {
  bg: "var(--pu-0b1220)",
  text: "var(--pu-f1f5f9-t)",
  t2: "var(--pu-148-163-184-07)",
  t3: "var(--pu-148-163-184-075)",
  border: "var(--pu-148-163-184-012)",
  grad: "linear-gradient(135deg, var(--pu-2563eb), var(--pu-0ea5e9))",
  red: "var(--pu-3b82f6-t)",
  input: "var(--pu-148-163-184-005)",
};

const API_BASE = ((import.meta.env.VITE_API_BASE as string | undefined) || "").replace(/\/+$/, "");

function Shell({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <main
      role="main"
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "32px 20px",
        background: T.bg,
        color: T.text,
        fontFamily: F.sans,
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 420,
          background: "var(--pu-15-30-55-055)",
          border: `1px solid ${T.border}`,
          borderRadius: 18,
          padding: "32px 28px",
        }}
      >
        <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 6 }}>{title}</h1>
        <p style={{ fontSize: 13, color: T.t2, marginBottom: 22, lineHeight: 1.5 }}>{subtitle}</p>
        {children}
      </div>
    </main>
  );
}

function fieldStyle(): React.CSSProperties {
  return {
    width: "100%",
    height: 42,
    padding: "0 12px",
    borderRadius: 10,
    border: `1px solid ${T.border}`,
    background: T.input,
    color: T.text,
    fontSize: 13,
    fontFamily: F.sans,
    outline: "none",
    boxSizing: "border-box",
  };
}

function primaryButtonStyle(disabled?: boolean): React.CSSProperties {
  return {
    width: "100%",
    height: 44,
    marginTop: 16,
    borderRadius: 10,
    border: "none",
    background: T.grad,
    color: "var(--pu-ffffff-t)",
    fontSize: 14,
    fontWeight: 600,
    fontFamily: F.sans,
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.6 : 1,
  };
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [message, setMessage] = useState("");

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!email.trim()) return;
    setStatus("sending");
    try {
      const res = await fetch(`${API_BASE}/api/auth/forgot-password`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email: email.trim().toLowerCase() }),
      });
      const data = await res.json().catch(() => ({}));
      // The backend returns 200 in both cases (account enumeration
      // protection), so we always go to "sent" here.
      setMessage(data.message || "Check your inbox for next steps.");
      setStatus("sent");
    } catch {
      setStatus("error");
    }
  };

  return (
    <Shell
      title="Forgot your password?"
      subtitle="Enter the email on your account and we'll send a reset link if it matches one we have."
    >
      <form onSubmit={submit}>
        <label htmlFor="forgot-email" style={{ fontSize: 12, color: T.t2, fontWeight: 500 }}>
          Email
        </label>
        <input
          id="forgot-email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          style={{ ...fieldStyle(), marginTop: 6 }}
        />
        {status === "sent" && (
          <p style={{ color: "var(--pu-22c55e-t)", fontSize: 12, marginTop: 12 }}>{message}</p>
        )}
        {status === "error" && (
          <p style={{ color: T.red, fontSize: 12, marginTop: 12 }}>
            Couldn't reach the server. Check your connection and try again.
          </p>
        )}
        <button type="submit" disabled={status === "sending"} style={primaryButtonStyle(status === "sending")}>
          {status === "sending" ? "Sending…" : "Send reset link"}
        </button>
      </form>
      <div style={{ marginTop: 16, fontSize: 12, color: T.t3, textAlign: "center" }}>
        <Link to="/signin" style={{ color: T.t2 }}>Back to sign in</Link>
      </div>
    </Shell>
  );
}

function passwordError(value: string): string | null {
  if (value.length < 8) return "Password must be at least 8 characters.";
  if (!/[A-Z]/.test(value)) return "Add an uppercase letter.";
  if (!/[a-z]/.test(value)) return "Add a lowercase letter.";
  if (!/\d/.test(value)) return "Add a number.";
  if (!/[^A-Za-z0-9]/.test(value)) return "Add a symbol.";
  return null;
}

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = useMemo(() => params.get("token") || "", [params]);
  const navigate = useNavigate();
  const [pwd, setPwd] = useState("");
  const [pwd2, setPwd2] = useState("");
  const [status, setStatus] = useState<"idle" | "submitting" | "done" | "error">("idle");
  const [err, setErr] = useState<string | null>(null);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setErr(null);
    if (pwd !== pwd2) { setErr("Passwords don't match."); return; }
    const pwErr = passwordError(pwd);
    if (pwErr) { setErr(pwErr); return; }
    setStatus("submitting");
    try {
      const res = await fetch(`${API_BASE}/api/auth/reset-password`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ token, new_password: pwd }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setErr(data.detail || "That link is no longer valid. Request a new one.");
        setStatus("error");
        return;
      }
      setStatus("done");
      setTimeout(() => navigate("/signin"), 1500);
    } catch {
      setErr("Network error. Try again.");
      setStatus("error");
    }
  };

  if (!token) {
    return (
      <Shell title="Reset link missing" subtitle="The reset URL is incomplete. Request a new one from the forgot-password page.">
        <Link to="/forgot-password" style={{ color: T.text }}>Request a new reset link →</Link>
      </Shell>
    );
  }

  return (
    <Shell title="Set a new password" subtitle="Pick something at least 8 characters with a mix of letters, numbers, and a symbol.">
      <form onSubmit={submit}>
        <label htmlFor="new-password" style={{ fontSize: 12, color: T.t2, fontWeight: 500 }}>
          New password
        </label>
        <input
          id="new-password" type="password" autoComplete="new-password" required
          value={pwd} onChange={(e) => setPwd(e.target.value)}
          style={{ ...fieldStyle(), marginTop: 6 }}
        />
        <label htmlFor="confirm-password" style={{ fontSize: 12, color: T.t2, fontWeight: 500, display: "block", marginTop: 12 }}>
          Confirm password
        </label>
        <input
          id="confirm-password" type="password" autoComplete="new-password" required
          value={pwd2} onChange={(e) => setPwd2(e.target.value)}
          style={{ ...fieldStyle(), marginTop: 6 }}
        />
        {err && <p style={{ color: T.red, fontSize: 12, marginTop: 12 }}>{err}</p>}
        {status === "done" && (
          <p style={{ color: "var(--pu-22c55e-t)", fontSize: 12, marginTop: 12 }}>
            Password updated. Redirecting you to sign in…
          </p>
        )}
        <button type="submit" disabled={status === "submitting"} style={primaryButtonStyle(status === "submitting")}>
          {status === "submitting" ? "Saving…" : "Update password"}
        </button>
      </form>
    </Shell>
  );
}

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [status, setStatus] = useState<"idle" | "verifying" | "done" | "error">("idle");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage("Missing verification token in the link.");
      return;
    }
    let cancelled = false;
    (async () => {
      setStatus("verifying");
      try {
        const res = await fetch(`${API_BASE}/api/auth/verify-email`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ token }),
        });
        if (cancelled) return;
        if (res.ok) {
          setStatus("done");
          setMessage("Your email is confirmed. You can close this tab or head to the dashboard.");
        } else {
          const data = await res.json().catch(() => ({}));
          setStatus("error");
          setMessage(data.detail || "This verification link is invalid or has expired.");
        }
      } catch {
        if (!cancelled) {
          setStatus("error");
          setMessage("Couldn't reach the server. Try again in a moment.");
        }
      }
    })();
    return () => { cancelled = true; };
  }, [token]);

  return (
    <Shell
      title={status === "done" ? "Email verified" : status === "error" ? "Verification problem" : "Verifying your email"}
      subtitle={message || "Hold on while we confirm your email address."}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <Link to="/dashboard" style={{ color: T.text, fontWeight: 600, textAlign: "center" }}>
          Go to dashboard →
        </Link>
        {status === "error" && (
          <Link to="/signin" style={{ color: T.t2, fontSize: 12, textAlign: "center" }}>
            Back to sign in
          </Link>
        )}
      </div>
    </Shell>
  );
}
