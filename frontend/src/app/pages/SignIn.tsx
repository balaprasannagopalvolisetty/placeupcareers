import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Link, useLocation, useNavigate } from "react-router";
import { Check, Eye, EyeOff, Globe, ShieldCheck, Target } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { getDemoCredentials, type DemoCredentials } from "../lib/api";
import { BrandLogo } from "../components/BrandLogo";

const F = { sans: "'Plus Jakarta Sans', sans-serif" };
// Clean, light SaaS palette (matches Home / SignUp).
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

function useViewportFlags() {
  const getWidth = () => (typeof window === "undefined" ? 1280 : window.innerWidth);
  const [width, setWidth] = useState(getWidth);
  useEffect(() => {
    const onResize = () => setWidth(getWidth());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return { isMobile: width < 760 };
}

function StyledInput({
  label, type = "text", value, onChange, rightEl, onEnter, autoComplete,
}: {
  label: string;
  type?: string;
  value: string;
  onChange: (v: string) => void;
  rightEl?: React.ReactNode;
  onEnter?: () => void;
  autoComplete?: string;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <label style={{ fontSize: 13, fontWeight: 600, color: T.t2, fontFamily: F.sans }}>{label}</label>
      <div style={{ position: "relative" }}>
        <input
          type={type}
          value={value}
          autoComplete={autoComplete}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && onEnter) {
              e.preventDefault();
              onEnter();
            }
          }}
          style={{
            width: "100%", height: 48, padding: "0 44px 0 14px",
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
        {rightEl && (
          <div style={{ position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)" }}>
            {rightEl}
          </div>
        )}
      </div>
    </div>
  );
}

const VALUE_POINTS = [
  { icon: Target, text: "Every job scored against your resume in real time" },
  { icon: ShieldCheck, text: "Visa sponsorship signals on every listing" },
  { icon: Globe, text: "Fresh roles from 30+ countries, refreshed every 6 hours" },
  { icon: Check, text: "Application tracking and smart daily alerts" },
];

export default function SignIn() {
  const navigate = useNavigate();
  const location = useLocation();
  const { signIn } = useAuth();
  const { isMobile } = useViewportFlags();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [demo, setDemo] = useState<DemoCredentials | null>(null);
  const redirectTo = typeof location.state === "object" && location.state && "from" in location.state
    ? String((location.state as { from?: unknown }).from || "/dashboard")
    : "/dashboard";

  useEffect(() => {
    let active = true;
    getDemoCredentials()
      .then((d) => { if (active) setDemo(d); })
      .catch(() => { /* prod or unavailable: hide the demo affordance */ });
    return () => { active = false; };
  }, []);

  const handleSubmit = async () => {
    setError(null);
    if (!identifier.trim() || !password) {
      setError("Please enter your email or phone and password.");
      return;
    }
    setLoading(true);
    try {
      await signIn(identifier.trim(), password);
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError((err as Error).message || "Unable to sign in.");
    } finally {
      setLoading(false);
    }
  };

  const handleUseDemo = async () => {
    if (!demo) return;
    setIdentifier(demo.email);
    setPassword(demo.password);
    setError(null);
    setLoading(true);
    try {
      await signIn(demo.email, demo.password);
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError((err as Error).message || "Demo sign-in failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", background: T.bg }}>
      {/* Left brand panel */}
      {!isMobile && (
        <div style={{
          position: "relative", overflow: "hidden",
          background: "linear-gradient(160deg, #1E3A8A 0%, #2563EB 55%, #0EA5E9 100%)",
          display: "flex", flexDirection: "column", justifyContent: "center", padding: 56,
        }}>
          <div style={{ position: "absolute", top: "-15%", right: "-10%", width: 420, height: 420, borderRadius: "50%", background: "rgba(255,255,255,0.07)", filter: "blur(10px)" }} />
          <div style={{ position: "absolute", bottom: "-20%", left: "-10%", width: 380, height: 380, borderRadius: "50%", background: "rgba(255,255,255,0.05)", filter: "blur(10px)" }} />
          <div style={{ position: "relative", zIndex: 1, maxWidth: 420 }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 10, marginBottom: 28 }}>
              <BrandLogo height={56} />
            </span>
            <h2 style={{ fontFamily: F.sans, fontSize: 32, fontWeight: 800, color: "#fff", lineHeight: 1.2, letterSpacing: "-0.02em", marginBottom: 14 }}>
              Your job search, focused on where you can actually get hired.
            </h2>
            <p style={{ fontSize: 15.5, color: "rgba(255,255,255,0.85)", fontFamily: F.sans, lineHeight: 1.7, marginBottom: 32 }}>
              Sign in to see your matches, ATS scores, and visa-friendly roles.
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {VALUE_POINTS.map((point) => (
                <div key={point.text} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <span style={{ width: 30, height: 30, borderRadius: 8, background: "rgba(255,255,255,0.14)", display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                    <point.icon size={15} color="#fff" />
                  </span>
                  <span style={{ fontSize: 14.5, color: "rgba(255,255,255,0.92)", fontFamily: F.sans, fontWeight: 500 }}>{point.text}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Right form panel */}
      <div style={{ background: T.surface, display: "flex", alignItems: "center", justifyContent: "center", padding: isMobile ? "40px 20px" : 48 }}>
        <div style={{ width: "100%", maxWidth: 420 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10, marginBottom: 36 }}>
            <BrandLogo variant="dark" height={58} />
          </div>
          <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22 }}>
            <h2 style={{ fontFamily: F.sans, fontSize: 26, fontWeight: 800, color: T.text, marginBottom: 6, textAlign: "center", letterSpacing: "-0.02em" }}>Welcome back</h2>
            <p style={{ fontSize: 14, color: T.t2, fontFamily: F.sans, textAlign: "center", marginBottom: 28 }}>
              Sign in to access your job matches, alerts, and analytics.
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 16, marginBottom: 16 }}>
              <StyledInput label="Email or phone" type="text" value={identifier} onChange={setIdentifier} onEnter={handleSubmit} autoComplete="username" />
              <StyledInput
                label="Password"
                type={showPass ? "text" : "password"}
                value={password}
                onChange={setPassword}
                onEnter={handleSubmit}
                autoComplete="current-password"
                rightEl={
                  <button onClick={() => setShowPass(!showPass)} style={{ background: "none", border: "none", cursor: "pointer", color: T.t3, padding: 0, display: "flex" }}>
                    {showPass ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                }
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
              onClick={handleSubmit}
              disabled={loading}
              style={{
                width: "100%", padding: "14px", borderRadius: 12, border: "none",
                cursor: loading ? "wait" : "pointer", background: T.grad, color: "#fff",
                fontSize: 15.5, fontWeight: 700, fontFamily: F.sans,
                boxShadow: "0 8px 20px rgba(37,99,235,0.25)",
                opacity: loading ? 0.75 : 1,
              }}
            >
              {loading ? "Signing in..." : "Sign in"}
            </motion.button>
            {demo && (
              <motion.button
                whileTap={{ scale: 0.97 }}
                onClick={handleUseDemo}
                disabled={loading}
                style={{
                  width: "100%", padding: "12px", marginTop: 10, borderRadius: 12,
                  border: `1px solid ${T.border}`, cursor: loading ? "wait" : "pointer",
                  background: "#fff", color: T.text, fontSize: 13.5, fontWeight: 600, fontFamily: F.sans,
                }}
                title={`${demo.email} / ${demo.password}`}
              >
                Use demo account
                <span style={{ display: "block", fontSize: 11.5, fontWeight: 400, color: T.t3, marginTop: 2 }}>
                  {demo.email} / password: {demo.password}
                </span>
              </motion.button>
            )}
            <p style={{ marginTop: 18, textAlign: "center", fontSize: 13, color: T.t3, fontFamily: F.sans }}>
              <Link to="/forgot-password" style={{ color: T.t2, textDecoration: "none", fontWeight: 500 }}>
                Forgot password?
              </Link>
            </p>
            <p style={{ marginTop: 8, textAlign: "center", fontSize: 13.5, color: T.t2, fontFamily: F.sans }}>
              Don't have an account?{" "}
              <Link to="/signup" style={{ color: T.accent, fontWeight: 700, textDecoration: "none" }}>
                Sign up
              </Link>
            </p>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
