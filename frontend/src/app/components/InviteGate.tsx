import { useEffect, useState, type ReactNode } from "react";
import { motion } from "motion/react";
import { Link } from "react-router";
import { KeyRound, Mail, PartyPopper, Ticket } from "lucide-react";
import { getInviteStatus, getInviteToken, joinWaitlist, validateInviteCode } from "../lib/api";
import { BrandLogo } from "./BrandLogo";

const F = { sans: "'Plus Jakarta Sans', sans-serif" };
const T = {
  bg: "#F8FAFC",
  surface: "#FFFFFF",
  border: "#E2E8F0",
  text: "#0F172A",
  t2: "#475569",
  t3: "#94A3B8",
  grad: "linear-gradient(135deg, #2563EB, #0EA5E9)",
  accent: "#2563EB",
  input: "#F8FAFC",
};

function GateInput({
  label, type = "text", value, onChange, onEnter, placeholder, autoComplete,
}: {
  label: string;
  type?: string;
  value: string;
  onChange: (v: string) => void;
  onEnter?: () => void;
  placeholder?: string;
  autoComplete?: string;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <label style={{ fontSize: 13, fontWeight: 600, color: T.t2, fontFamily: F.sans }}>{label}</label>
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        autoComplete={autoComplete}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && onEnter) {
            e.preventDefault();
            onEnter();
          }
        }}
        style={{
          width: "100%", height: 48, padding: "0 14px",
          borderRadius: 12, border: `1px solid ${T.border}`,
          background: T.input, color: T.text, fontSize: 14.5,
          fontFamily: F.sans, outline: "none", boxSizing: "border-box",
        }}
        onFocus={(e) => {
          e.target.style.borderColor = T.accent;
          e.target.style.boxShadow = "0 0 0 3px rgba(37,99,235,0.12)";
        }}
        onBlur={(e) => {
          e.target.style.borderColor = T.border;
          e.target.style.boxShadow = "none";
        }}
      />
    </div>
  );
}

/**
 * InviteGate — private-beta wall in front of SignIn / SignUp.
 *
 * The invite code is validated by the backend (never present in this
 * bundle). A correct code stores a short-lived signed token in
 * sessionStorage and reveals the wrapped page. A wrong code offers the
 * waitlist instead: we save the visitor's email and notify them at
 * public launch.
 */
export default function InviteGate({ children }: { children: ReactNode }) {
  // undefined = still asking the backend whether the gate is on.
  const [required, setRequired] = useState<boolean | undefined>(
    getInviteToken() ? false : undefined,
  );
  const [code, setCode] = useState("");
  const [checking, setChecking] = useState(false);
  const [rejected, setRejected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [waitEmail, setWaitEmail] = useState("");
  const [waitSubmitting, setWaitSubmitting] = useState(false);
  const [waitDone, setWaitDone] = useState<string | null>(null);
  const [waitError, setWaitError] = useState<string | null>(null);

  useEffect(() => {
    if (required !== undefined) return;
    let active = true;
    getInviteStatus()
      .then((s) => { if (active) setRequired(s.invite_required); })
      // If the status check fails, keep the gate up — fail closed.
      .catch(() => { if (active) setRequired(true); });
    return () => { active = false; };
  }, [required]);

  const handleValidate = async () => {
    const trimmed = code.trim();
    if (!trimmed) {
      setError("Please enter your invite code.");
      return;
    }
    setChecking(true);
    setError(null);
    try {
      await validateInviteCode(trimmed);
      setRequired(false);
    } catch (err) {
      const message = (err as Error).message || "";
      if (/too many/i.test(message)) {
        setError("Too many attempts. Please wait a minute and try again.");
      } else {
        setRejected(true);
      }
    } finally {
      setChecking(false);
    }
  };

  const handleWaitlist = async () => {
    const email = waitEmail.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setWaitError("Please enter a valid email address.");
      return;
    }
    setWaitSubmitting(true);
    setWaitError(null);
    try {
      const res = await joinWaitlist(email);
      setWaitDone(res.message || "You're on the list! We'll email you when PlaceUp opens up.");
    } catch (err) {
      setWaitError((err as Error).message || "Couldn't save your email. Please try again.");
    } finally {
      setWaitSubmitting(false);
    }
  };

  // Gate passed (or disabled server-side): render the real page.
  if (required === false) return <>{children}</>;

  return (
    <div style={{ minHeight: "100vh", background: T.bg, display: "flex", alignItems: "center", justifyContent: "center", padding: "40px 20px" }}>
      <div style={{ width: "100%", maxWidth: 440 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 32 }}>
          <BrandLogo variant="dark" height={64} />
        </div>

        {required === undefined ? (
          <p style={{ textAlign: "center", color: T.t3, fontFamily: F.sans, fontSize: 14 }}>Checking access…</p>
        ) : (
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.22 }}
            style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 18, padding: "32px 28px", boxShadow: "0 10px 30px rgba(15,23,42,0.06)" }}
          >
            {!rejected ? (
              <>
                <div style={{ display: "flex", justifyContent: "center", marginBottom: 16 }}>
                  <span style={{ width: 48, height: 48, borderRadius: 14, background: "rgba(37,99,235,0.08)", display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
                    <Ticket size={22} color={T.accent} />
                  </span>
                </div>
                <h2 style={{ fontFamily: F.sans, fontSize: 22, fontWeight: 800, color: T.text, textAlign: "center", marginBottom: 6, letterSpacing: "-0.02em" }}>
                  PlaceUp is invite-only right now
                </h2>
                <p style={{ fontSize: 14, color: T.t2, fontFamily: F.sans, textAlign: "center", marginBottom: 24, lineHeight: 1.6 }}>
                  We're in private beta. If you received an invite, enter your code below to continue.
                </p>
                <div style={{ marginBottom: 14 }}>
                  <GateInput
                    label="Enter Invite Code"
                    value={code}
                    onChange={(v) => { setCode(v); setError(null); }}
                    onEnter={handleValidate}
                    placeholder="Your invite code"
                    autoComplete="off"
                  />
                </div>
                {error && (
                  <div style={{
                    color: "#DC2626", fontSize: 13, marginBottom: 14, fontFamily: F.sans,
                    padding: "10px 12px", borderRadius: 8, background: "rgba(220,38,38,0.06)",
                    border: "1px solid rgba(220,38,38,0.2)",
                  }}>{error}</div>
                )}
                <motion.button
                  whileTap={{ scale: 0.97 }}
                  onClick={handleValidate}
                  disabled={checking}
                  style={{
                    width: "100%", padding: "14px", borderRadius: 12, border: "none",
                    cursor: checking ? "wait" : "pointer", background: T.grad, color: "#fff",
                    fontSize: 15.5, fontWeight: 700, fontFamily: F.sans,
                    boxShadow: "0 8px 20px rgba(37,99,235,0.25)",
                    opacity: checking ? 0.75 : 1,
                    display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8,
                  }}
                >
                  <KeyRound size={16} />
                  {checking ? "Checking…" : "Unlock access"}
                </motion.button>
                <p style={{ marginTop: 16, textAlign: "center", fontSize: 13, color: T.t3, fontFamily: F.sans }}>
                  No code?{" "}
                  <button
                    onClick={() => setRejected(true)}
                    style={{ background: "none", border: "none", padding: 0, cursor: "pointer", color: T.accent, fontWeight: 700, fontSize: 13, fontFamily: F.sans }}
                  >
                    Join the waitlist
                  </button>
                </p>
              </>
            ) : waitDone ? (
              <>
                <div style={{ display: "flex", justifyContent: "center", marginBottom: 16 }}>
                  <span style={{ width: 48, height: 48, borderRadius: 14, background: "rgba(22,163,74,0.1)", display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
                    <PartyPopper size={22} color="#16A34A" />
                  </span>
                </div>
                <h2 style={{ fontFamily: F.sans, fontSize: 22, fontWeight: 800, color: T.text, textAlign: "center", marginBottom: 6, letterSpacing: "-0.02em" }}>
                  You're on the list!
                </h2>
                <p style={{ fontSize: 14, color: T.t2, fontFamily: F.sans, textAlign: "center", lineHeight: 1.6, marginBottom: 20 }}>
                  {waitDone}
                </p>
                <p style={{ textAlign: "center", fontSize: 13, fontFamily: F.sans }}>
                  <Link to="/" style={{ color: T.accent, fontWeight: 700, textDecoration: "none" }}>Back to home</Link>
                </p>
              </>
            ) : (
              <>
                <div style={{ display: "flex", justifyContent: "center", marginBottom: 16 }}>
                  <span style={{ width: 48, height: 48, borderRadius: 14, background: "rgba(37,99,235,0.08)", display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
                    <Mail size={22} color={T.accent} />
                  </span>
                </div>
                <h2 style={{ fontFamily: F.sans, fontSize: 22, fontWeight: 800, color: T.text, textAlign: "center", marginBottom: 6, letterSpacing: "-0.02em" }}>
                  Hang tight — we're almost public
                </h2>
                <p style={{ fontSize: 14, color: T.t2, fontFamily: F.sans, textAlign: "center", marginBottom: 22, lineHeight: 1.6 }}>
                  That code didn't match, or you don't have one yet. PlaceUp is opening to everyone soon —
                  leave your email and we'll notify you the moment access goes public.
                </p>
                <div style={{ marginBottom: 14 }}>
                  <GateInput
                    label="Your email"
                    type="email"
                    value={waitEmail}
                    onChange={(v) => { setWaitEmail(v); setWaitError(null); }}
                    onEnter={handleWaitlist}
                    placeholder="you@example.com"
                    autoComplete="email"
                  />
                </div>
                {waitError && (
                  <div style={{
                    color: "#DC2626", fontSize: 13, marginBottom: 14, fontFamily: F.sans,
                    padding: "10px 12px", borderRadius: 8, background: "rgba(220,38,38,0.06)",
                    border: "1px solid rgba(220,38,38,0.2)",
                  }}>{waitError}</div>
                )}
                <motion.button
                  whileTap={{ scale: 0.97 }}
                  onClick={handleWaitlist}
                  disabled={waitSubmitting}
                  style={{
                    width: "100%", padding: "14px", borderRadius: 12, border: "none",
                    cursor: waitSubmitting ? "wait" : "pointer", background: T.grad, color: "#fff",
                    fontSize: 15.5, fontWeight: 700, fontFamily: F.sans,
                    boxShadow: "0 8px 20px rgba(37,99,235,0.25)",
                    opacity: waitSubmitting ? 0.75 : 1,
                  }}
                >
                  {waitSubmitting ? "Saving…" : "Notify me at launch"}
                </motion.button>
                <p style={{ marginTop: 16, textAlign: "center", fontSize: 13, color: T.t3, fontFamily: F.sans }}>
                  Got a code after all?{" "}
                  <button
                    onClick={() => { setRejected(false); setCode(""); setError(null); }}
                    style={{ background: "none", border: "none", padding: 0, cursor: "pointer", color: T.accent, fontWeight: 700, fontSize: 13, fontFamily: F.sans }}
                  >
                    Try again
                  </button>
                </p>
              </>
            )}
          </motion.div>
        )}
      </div>
    </div>
  );
}
