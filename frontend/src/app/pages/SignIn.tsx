import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Link, useNavigate } from "react-router";
import { Eye, EyeOff, Star } from "lucide-react";
import { OrbitalSphereSmall } from "../components/OrbitalSphereSmall";
import { useAuth } from "../context/AuthContext";
import { getAuthProviders, getDemoCredentials, startGoogleOidc, type DemoCredentials } from "../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  bg: "#011126",
  surface: "#401212",
  border: "rgba(242,238,179,0.1)",
  text: "#F2EEB3",
  t2: "rgba(242,238,179,0.65)",
  t3: "rgba(242,238,179,0.45)",
  grad: "linear-gradient(135deg, #8C3A27, #A6372D, #401212)",
  red: "#A6372D",
  input: "rgba(242,238,179,0.05)",
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
  label,
  type = "text",
  value,
  onChange,
  rightEl,
}: {
  label: string;
  type?: string;
  value: string;
  onChange: (v: string) => void;
  rightEl?: React.ReactNode;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <label style={{ fontSize: 13, fontWeight: 500, color: T.t2, fontFamily: F.sans }}>{label}</label>
      <div style={{ position: "relative" }}>
        <input
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          style={{
            width: "100%",
            height: 48,
            padding: "0 44px 0 14px",
            borderRadius: 12,
            border: `1px solid ${T.border}`,
            background: T.input,
            color: T.text,
            fontSize: 14,
            fontFamily: F.sans,
            outline: "none",
            boxSizing: "border-box",
          }}
          onFocus={(e) => {
            e.target.style.borderColor = T.red;
            e.target.style.boxShadow = `0 0 0 3px rgba(166,55,45,0.15)`;
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

export default function SignIn() {
  const navigate = useNavigate();
  const { signIn } = useAuth();
  const { isMobile } = useViewportFlags();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [demo, setDemo] = useState<DemoCredentials | null>(null);
  const [googleSsoEnabled, setGoogleSsoEnabled] = useState(false);

  useEffect(() => {
    let active = true;
    getDemoCredentials()
      .then((d) => { if (active) setDemo(d); })
      .catch(() => { /* prod or unavailable — hide the demo affordance */ });
    getAuthProviders()
      .then((providers) => { if (active) setGoogleSsoEnabled(providers.google); })
      .catch(() => { if (active) setGoogleSsoEnabled(false); });
    return () => { active = false; };
  }, []);

  const handleSubmit = async () => {
    setError(null);
    if (!email || !password) {
      setError("Please enter your email and password.");
      return;
    }
    setLoading(true);
    try {
      await signIn(email, password);
      navigate("/dashboard");
    } catch (err) {
      setError((err as Error).message || "Unable to sign in.");
    } finally {
      setLoading(false);
    }
  };

  const handleUseDemo = async () => {
    if (!demo) return;
    setEmail(demo.email);
    setPassword(demo.password);
    setError(null);
    setLoading(true);
    try {
      await signIn(demo.email, demo.password);
      navigate("/dashboard");
    } catch (err) {
      setError((err as Error).message || "Demo sign-in failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", background: T.bg }}>
      <div style={{ position: "relative", overflow: "hidden", background: "linear-gradient(135deg, #011126 0%, #1a0808 100%)", minHeight: isMobile ? 240 : "auto" }}>
        <div style={{ position: "absolute", top: "10%", left: "5%", width: 300, height: 300, borderRadius: "50%", filter: "blur(80px)", background: "rgba(140,58,39,0.2)" }} />
        <div style={{ position: "absolute", bottom: "20%", right: "10%", width: 250, height: 250, borderRadius: "50%", filter: "blur(80px)", background: "rgba(166,55,45,0.15)" }} />
        <div style={{ position: "relative", zIndex: 1, height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: isMobile ? 24 : 48 }}>
          {!isMobile && <OrbitalSphereSmall />}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.8 }} style={{ marginTop: isMobile ? 0 : 40, padding: isMobile ? "16px 18px" : "20px 24px", borderRadius: 16, background: "rgba(64,18,18,0.65)", backdropFilter: "blur(20px)", border: "1px solid rgba(242,238,179,0.08)", maxWidth: 380 }}>
            <div style={{ display: "flex", gap: 3, marginBottom: 10 }}>
              {[0, 1, 2, 3, 4].map((i) => (
                <Star key={i} size={12} fill={T.red} color={T.red} />
              ))}
            </div>
            <p style={{ fontSize: 15, fontWeight: 500, color: T.text, fontFamily: F.sans, lineHeight: 1.6, marginBottom: 12 }}>
              "87% of PlaceUp users land interviews within 6 weeks"
            </p>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ width: 36, height: 36, borderRadius: "50%", background: "linear-gradient(135deg, #8C3A27, #A6372D)", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: F.sans, fontSize: 13, fontWeight: 700, color: "#fff" }}>SL</div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: T.text, fontFamily: F.sans }}>Sarah L.</div>
                <div style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>Software Engineer · Google (H-1B)</div>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
      <div style={{ background: T.surface, display: "flex", alignItems: "center", justifyContent: "center", padding: isMobile ? "32px 18px" : 48 }}>
        <div style={{ width: "100%", maxWidth: 420 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, justifyContent: "center", marginBottom: 40 }}>
            <img src="/logo_white.png" alt="PlaceUp Career" style={{ width: 34, height: 34, objectFit: "contain" }} />
            <span style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 18, color: T.text, letterSpacing: "-0.02em" }}>
              PlaceUp <span style={{ color: T.red, fontSize: 14, fontWeight: 600 }}>Career</span>
            </span>
          </div>
          <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22 }}>
            <h2 style={{ fontFamily: F.sans, fontSize: 26, fontWeight: 700, color: T.text, marginBottom: 6, textAlign: "center" }}>Welcome Back</h2>
            <p style={{ fontSize: 13, color: T.t2, fontFamily: F.sans, textAlign: "center", marginBottom: 28 }}>
              Sign in to access your job matches, alerts, and analytics.
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 16, marginBottom: 16 }}>
              <StyledInput label="Email Address" type="email" value={email} onChange={setEmail} />
              <StyledInput
                label="Password"
                type={showPass ? "text" : "password"}
                value={password}
                onChange={setPassword}
                rightEl={
                  <button onClick={() => setShowPass(!showPass)} style={{ background: "none", border: "none", cursor: "pointer", color: T.t3 }}>
                    {showPass ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                }
              />
            </div>
            {error && <div style={{ color: "#f87171", fontSize: 13, marginBottom: 12, fontFamily: F.sans }}>{error}</div>}
            <motion.button
              whileTap={{ scale: 0.97 }}
              onClick={handleSubmit}
              disabled={loading}
              style={{
                width: "100%",
                padding: "14px",
                borderRadius: 12,
                border: "none",
                cursor: "pointer",
                background: T.grad,
                color: "#fff",
                fontSize: 15,
                fontWeight: 600,
                fontFamily: F.sans,
                boxShadow: "0 0 24px rgba(166,55,45,0.35)",
                opacity: loading ? 0.75 : 1,
              }}
            >
              {loading ? "Signing in..." : "Sign In →"}
            </motion.button>
            {demo && (
              <motion.button
                whileTap={{ scale: 0.97 }}
                onClick={handleUseDemo}
                disabled={loading}
                style={{
                  width: "100%",
                  padding: "12px",
                  marginTop: 10,
                  borderRadius: 12,
                  border: `1px solid ${T.border}`,
                  cursor: loading ? "wait" : "pointer",
                  background: "rgba(242,238,179,0.04)",
                  color: T.text,
                  fontSize: 13,
                  fontWeight: 600,
                  fontFamily: F.sans,
                }}
                title={`${demo.email} / ${demo.password}`}
              >
                Use demo account
                <span style={{ display: "block", fontSize: 11, fontWeight: 400, color: T.t3, marginTop: 2 }}>
                  {demo.email} · password: {demo.password}
                </span>
              </motion.button>
            )}
            {/* Social SSO buttons intentionally removed per product
                request. If/when Google or LinkedIn OAuth is re-enabled,
                the backend endpoints in app/api/auth.py (/oidc/google
                etc.) are still live — just re-add the buttons here. */}
            <p style={{ marginTop: 18, textAlign: "center", fontSize: 12, color: T.t3, fontFamily: F.sans }}>
              <Link to="/forgot-password" style={{ color: T.t2, textDecoration: "none" }}>
                Forgot password?
              </Link>
            </p>
            <p style={{ marginTop: 8, textAlign: "center", fontSize: 13, color: T.t2, fontFamily: F.sans }}>
              Don't have an account?{" "}
              <Link to="/signup" style={{ color: T.red, fontWeight: 600, textDecoration: "none" }}>
                Sign up
              </Link>
            </p>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
