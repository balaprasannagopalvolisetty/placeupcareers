import { useState } from "react";
import { motion } from "motion/react";
import { Link, useNavigate } from "react-router";
import { Eye, EyeOff } from "lucide-react";
import { useAuth } from "../context/AuthContext";

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

function Field({ label, type = "text", value, onChange, rightEl }: { label: string; type?: string; value: string; onChange: (v: string) => void; rightEl?: React.ReactNode }) {
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
        {rightEl && <div style={{ position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)" }}>{rightEl}</div>}
      </div>
    </div>
  );
}

export default function SignUp() {
  const navigate = useNavigate();
  const { signUp } = useAuth();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    setError(null);
    if (!firstName || !lastName || !email || !password || !confirmPassword) {
      setError("Please complete all fields.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    try {
      await signUp({ first_name: firstName, last_name: lastName, email, password });
      navigate("/dashboard");
    } catch (err) {
      setError((err as Error).message || "Unable to create your account.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", justifyContent: "center", alignItems: "center", padding: 24, background: T.bg }}>
      <div style={{ width: "100%", maxWidth: 560, borderRadius: 28, background: "rgba(1,17,38,0.9)", border: `1px solid ${T.border}`, backdropFilter: "blur(30px)", padding: 36, boxShadow: "0 24px 64px rgba(1,17,38,0.4)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 32 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 34, height: 34, borderRadius: 10, background: T.grad, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontWeight: 700, fontFamily: F.sans }}>P</div>
            <div>
              <div style={{ fontFamily: F.sans, fontSize: 18, fontWeight: 700, color: T.text }}>Create your account</div>
              <div style={{ fontSize: 13, color: T.t2, fontFamily: F.sans }}>Build your job and visa dashboard.</div>
            </div>
          </div>
          <Link to="/signin" style={{ color: T.red, fontSize: 13, fontWeight: 600, fontFamily: F.sans, textDecoration: "none" }}>Already have an account?</Link>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <Field label="First Name" value={firstName} onChange={setFirstName} />
          <Field label="Last Name" value={lastName} onChange={setLastName} />
          <Field label="Email Address" type="email" value={email} onChange={setEmail} />
          <Field
            label="Password"
            type={showPass ? "text" : "password"}
            value={password}
            onChange={setPassword}
            rightEl={
              <button onClick={() => setShowPass(!showPass)} style={{ background: "none", border: "none", cursor: "pointer", color: T.t3 }}>
                {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            }
          />
          <div style={{ gridColumn: "1 / -1" }}>
            <Field label="Confirm Password" type="password" value={confirmPassword} onChange={setConfirmPassword} />
          </div>
        </div>

        {error && <div style={{ color: "#f87171", fontSize: 13, marginTop: 18, fontFamily: F.sans }}>{error}</div>}

        <motion.button
          whileTap={{ scale: 0.97 }}
          onClick={handleSubmit}
          disabled={loading}
          style={{
            width: "100%",
            marginTop: 24,
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
          {loading ? "Creating account..." : "Create Account"}
        </motion.button>

        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginTop: 20, fontSize: 12, color: T.t3, fontFamily: F.sans }}>
          <span>Secure onboarding</span>
          <span>PCI-DSS + SSL</span>
        </div>
      </div>
    </div>
  );
}
