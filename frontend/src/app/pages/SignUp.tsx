import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Link, useNavigate } from "react-router";
import { Eye, EyeOff, X, Upload, Check } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import * as api from "../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  bg: "#011126", surface: "#401212",
  border: "rgba(242,238,179,0.1)", text: "#F2EEB3",
  t2: "rgba(242,238,179,0.65)", t3: "rgba(242,238,179,0.45)",
  grad: "linear-gradient(135deg, #8C3A27, #A6372D, #401212)",
  red: "#A6372D", input: "rgba(242,238,179,0.05)",
};

interface TaxonomyRole { name: string }
interface TaxonomyCategory { name: string; roles: TaxonomyRole[] }

function Field({ label, type = "text", value, onChange, placeholder, required, rightEl }:
  { label: string; type?: string; value: string; onChange: (v: string) => void; placeholder?: string; required?: boolean; rightEl?: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <label style={{ fontSize: 12, fontWeight: 500, color: T.t2, fontFamily: F.sans }}>
        {label} {required ? <span style={{ color: T.red }}>*</span> : null}
      </label>
      <div style={{ position: "relative" }}>
        <input type={type} value={value} placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          style={{ width: "100%", height: 42, padding: rightEl ? "0 40px 0 12px" : "0 12px",
            borderRadius: 10, border: `1px solid ${T.border}`, background: T.input,
            color: T.text, fontSize: 13, fontFamily: F.sans, outline: "none", boxSizing: "border-box" }}
          onFocus={(e) => { e.target.style.borderColor = T.red; }}
          onBlur={(e) => { e.target.style.borderColor = T.border; }} />
        {rightEl && (
          <div style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)" }}>{rightEl}</div>
        )}
      </div>
    </div>
  );
}

function Select({ label, value, onChange, options, required }:
  { label: string; value: string; onChange: (v: string) => void; options: readonly string[]; required?: boolean }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <label style={{ fontSize: 12, fontWeight: 500, color: T.t2, fontFamily: F.sans }}>
        {label} {required ? <span style={{ color: T.red }}>*</span> : null}
      </label>
      <select value={value} onChange={(e) => onChange(e.target.value)}
        style={{ height: 42, padding: "0 12px", borderRadius: 10, border: `1px solid ${T.border}`,
          background: T.input, color: T.text, fontSize: 13, fontFamily: F.sans, outline: "none" }}>
        <option value="">— select —</option>
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );
}

export default function SignUp() {
  const navigate = useNavigate();
  const { signUp } = useAuth();

  // Step 1 — credentials
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPass, setShowPass] = useState(false);

  // Step 2 — career
  const [linkedinUrl, setLinkedinUrl] = useState("");
  const [currentRole, setCurrentRole] = useState("");
  const [currentCompany, setCurrentCompany] = useState("");
  const [experienceLevel, setExperienceLevel] = useState("");
  const [visaStatus, setVisaStatus] = useState("");
  const [location, setLocation] = useState("");

  // Step 3 — preferences
  const [taxonomy, setTaxonomy] = useState<TaxonomyCategory[]>([]);
  const [targetRoles, setTargetRoles] = useState<string[]>([]);
  const [targetLocations, setTargetLocations] = useState<string[]>([]);
  const [locationInput, setLocationInput] = useState("");

  // Step 4 — resume
  const [resumeFile, setResumeFile] = useState<File | null>(null);

  const [step, setStep] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Load taxonomy once for the role picker.
  useEffect(() => {
    fetch("/api/jobs/taxonomy")
      .then((r) => r.json())
      .then((data) => Array.isArray(data?.categories) && setTaxonomy(data.categories))
      .catch(() => {});
  }, []);

  const allRoles = taxonomy.flatMap((c) => c.roles.map((r) => r.name));

  const toggleRole = (r: string) => {
    setTargetRoles((prev) => {
      if (prev.includes(r)) return prev.filter((x) => x !== r);
      if (prev.length >= 5) return prev;  // hard cap
      return [...prev, r];
    });
  };

  const addLocation = () => {
    const v = locationInput.trim();
    if (!v) return;
    if (targetLocations.includes(v)) return;
    setTargetLocations((prev) => [...prev, v]);
    setLocationInput("");
  };

  const validateStep = (): string | null => {
    if (step === 1) {
      if (!firstName || !lastName || !email || !password || !confirm) return "Please complete all fields.";
      if (password !== confirm) return "Passwords do not match.";
      if (password.length < 8) return "Password must be at least 8 characters.";
    }
    if (step === 2) {
      if (!visaStatus) return "Please select your visa status.";
    }
    if (step === 3) {
      if (targetRoles.length === 0) return "Pick at least one target role (max 5).";
    }
    if (step === 4) {
      if (!resumeFile) return "Please upload one resume to create your account.";
    }
    return null;
  };

  const next = () => {
    const err = validateStep();
    if (err) { setError(err); return; }
    setError(null);
    setStep((s) => s + 1);
  };
  const back = () => { setError(null); setStep((s) => Math.max(1, s - 1)); };

  const handleSubmit = async () => {
    const err = validateStep();
    if (err) { setError(err); return; }
    setError(null);
    setLoading(true);
    try {
      await signUp({
        first_name: firstName, last_name: lastName, email, password,
        visa_status: visaStatus || undefined,
        experience_level: experienceLevel || undefined,
        current_role: currentRole || undefined,
        current_company: currentCompany || undefined,
        location: location || undefined,
        linkedin_url: linkedinUrl || undefined,
        target_roles: targetRoles,
        target_locations: targetLocations,
      });
      // After auth, upload the resume (only if provided).
      if (resumeFile) {
        try { await api.uploadResume(resumeFile); } catch (e) { console.warn("resume upload skipped:", e); }
      }
      navigate("/dashboard");
    } catch (err) {
      setError((err as Error).message || "Unable to create your account.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", justifyContent: "center", alignItems: "center", padding: 24, background: T.bg }}>
      <div style={{ width: "100%", maxWidth: 640, borderRadius: 24, background: "rgba(1,17,38,0.92)", border: `1px solid ${T.border}`, backdropFilter: "blur(28px)", padding: 32, boxShadow: "0 24px 64px rgba(1,17,38,0.4)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 32, height: 32, borderRadius: 9, background: T.grad, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontWeight: 700, fontFamily: F.sans }}>P</div>
            <div>
              <div style={{ fontFamily: F.sans, fontSize: 17, fontWeight: 700, color: T.text }}>Create your account</div>
              <div style={{ fontSize: 12, color: T.t2, fontFamily: F.sans }}>Step {step} of 4</div>
            </div>
          </div>
          <Link to="/signin" style={{ color: T.red, fontSize: 12, fontWeight: 600, fontFamily: F.sans, textDecoration: "none" }}>Already have an account?</Link>
        </div>

        {/* Progress dots */}
        <div style={{ display: "flex", gap: 6, marginBottom: 24 }}>
          {[1, 2, 3, 4].map((s) => (
            <div key={s} style={{ flex: 1, height: 3, borderRadius: 2, background: s <= step ? T.grad : "rgba(242,238,179,0.08)" }} />
          ))}
        </div>

        {/* Step 1 — credentials */}
        {step === 1 && (
          <motion.div initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            <Field label="First Name" value={firstName} onChange={setFirstName} required />
            <Field label="Last Name" value={lastName} onChange={setLastName} required />
            <div style={{ gridColumn: "1 / -1" }}>
              <Field label="Gmail / Email" type="email" value={email} onChange={setEmail} placeholder="you@example.com" required />
            </div>
            <Field label="Password" type={showPass ? "text" : "password"} value={password} onChange={setPassword} required
              rightEl={<button onClick={() => setShowPass(!showPass)} style={{ background: "none", border: "none", cursor: "pointer", color: T.t3, padding: 0 }}>{showPass ? <EyeOff size={14} /> : <Eye size={14} />}</button>} />
            <Field label="Confirm Password" type="password" value={confirm} onChange={setConfirm} required />
          </motion.div>
        )}

        {/* Step 2 — career */}
        {step === 2 && (
          <motion.div initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            <div style={{ gridColumn: "1 / -1" }}>
              <Field label="LinkedIn Profile URL" value={linkedinUrl} onChange={setLinkedinUrl} placeholder="https://linkedin.com/in/..." />
            </div>
            <Field label="Current Role" value={currentRole} onChange={setCurrentRole} placeholder="Software Engineer" />
            <Field label="Current Company" value={currentCompany} onChange={setCurrentCompany} placeholder="Acme Corp" />
            <Select label="Years of Experience" value={experienceLevel} onChange={setExperienceLevel} options={api.YEARS_OPTIONS} />
            <Select label="Visa Status" value={visaStatus} onChange={setVisaStatus} options={api.VISA_STATUS_OPTIONS} required />
            <div style={{ gridColumn: "1 / -1" }}>
              <Field label="Current Location" value={location} onChange={setLocation} placeholder="San Francisco, CA" />
            </div>
          </motion.div>
        )}

        {/* Step 3 — preferences */}
        {step === 3 && (
          <motion.div initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }}>
            <div style={{ marginBottom: 18 }}>
              <div style={{ fontSize: 12, fontWeight: 500, color: T.t2, fontFamily: F.sans, marginBottom: 6 }}>
                Job Preferences <span style={{ color: T.red }}>*</span>
                <span style={{ marginLeft: 6, fontSize: 11, color: T.t3 }}>pick up to 5 ({targetRoles.length}/5)</span>
              </div>
              <div style={{ maxHeight: 220, overflowY: "auto", border: `1px solid ${T.border}`, borderRadius: 10, padding: 8, background: T.input }}>
                {taxonomy.map((cat) => (
                  <div key={cat.name} style={{ marginBottom: 8 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: T.t3, fontFamily: F.sans, padding: "4px 6px" }}>{cat.name}</div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                      {cat.roles.map((r) => {
                        const sel = targetRoles.includes(r.name);
                        const disabled = !sel && targetRoles.length >= 5;
                        return (
                          <button key={r.name} type="button" onClick={() => toggleRole(r.name)} disabled={disabled}
                            style={{ fontSize: 11, padding: "4px 9px", borderRadius: 4, fontFamily: F.sans, cursor: disabled ? "not-allowed" : "pointer",
                              background: sel ? T.grad : "rgba(242,238,179,0.05)", color: sel ? "#fff" : (disabled ? T.t3 : T.t2),
                              border: `1px solid ${sel ? "rgba(166,55,45,0.6)" : T.border}`, opacity: disabled ? 0.5 : 1 }}>
                            {r.name}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <div style={{ fontSize: 12, fontWeight: 500, color: T.t2, fontFamily: F.sans, marginBottom: 6 }}>Location Preferences</div>
              <div style={{ display: "flex", gap: 8 }}>
                <input value={locationInput} onChange={(e) => setLocationInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addLocation(); } }}
                  placeholder="e.g. Remote, San Francisco, NYC"
                  style={{ flex: 1, height: 38, padding: "0 12px", borderRadius: 10, border: `1px solid ${T.border}`, background: T.input, color: T.text, fontSize: 13, fontFamily: F.sans, outline: "none" }} />
                <button type="button" onClick={addLocation} style={{ padding: "0 16px", borderRadius: 10, border: "none", background: T.grad, color: "#fff", fontSize: 12, fontWeight: 600, fontFamily: F.sans, cursor: "pointer" }}>Add</button>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 8 }}>
                {targetLocations.map((l) => (
                  <span key={l} style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11, padding: "3px 8px", borderRadius: 4, background: "rgba(166,55,45,0.1)", color: T.red, border: "1px solid rgba(166,55,45,0.25)", fontFamily: F.sans }}>
                    {l}
                    <button type="button" onClick={() => setTargetLocations((prev) => prev.filter((x) => x !== l))} style={{ background: "none", border: "none", cursor: "pointer", color: T.red, padding: 0 }}><X size={10} /></button>
                  </span>
                ))}
              </div>
            </div>
          </motion.div>
        )}

        {/* Step 4 — resume */}
        {step === 4 && (
          <motion.div initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }}>
            <div style={{ fontSize: 12, fontWeight: 500, color: T.t2, fontFamily: F.sans, marginBottom: 8 }}>
              Upload Resume (required, 1 file)
            </div>
            <label style={{ display: "block", padding: 28, borderRadius: 12, border: `2px dashed ${resumeFile ? T.red : "rgba(166,55,45,0.3)"}`, background: T.input, textAlign: "center", cursor: "pointer", transition: "all 0.2s" }}>
              <Upload size={24} color={T.red} style={{ margin: "0 auto 10px" }} />
              {resumeFile ? (
                <div>
                  <div style={{ fontSize: 13, color: T.text, fontFamily: F.sans, fontWeight: 600, marginBottom: 4 }}>
                    <Check size={12} style={{ verticalAlign: "middle", marginRight: 6 }} color="#22c55e" />
                    {resumeFile.name}
                  </div>
                  <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans }}>{Math.round(resumeFile.size / 1024)} KB</div>
                </div>
              ) : (
                <div>
                  <div style={{ fontSize: 13, color: T.text, fontFamily: F.sans, marginBottom: 4 }}>Click or drop a resume</div>
                  <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans }}>PDF or DOCX, max 10MB</div>
                </div>
              )}
              <input type="file" accept=".pdf,.docx" style={{ display: "none" }}
                onChange={(e) => setResumeFile(e.target.files?.[0] ?? null)} />
            </label>
            <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans, marginTop: 12, lineHeight: 1.55 }}>
              Your resume is stored as the single active resume. You can replace it later from the Resumes tab.
            </div>
          </motion.div>
        )}

        {error && (
          <div style={{ marginTop: 16, padding: "10px 12px", borderRadius: 8, background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.25)", color: "#f87171", fontSize: 12, fontFamily: F.sans }}>
            {error}
          </div>
        )}

        <div style={{ display: "flex", gap: 10, marginTop: 24 }}>
          {step > 1 && (
            <button type="button" onClick={back} disabled={loading}
              style={{ flex: 1, padding: "12px", borderRadius: 12, border: `1px solid ${T.border}`, background: "transparent", color: T.t2, fontSize: 13, fontFamily: F.sans, cursor: "pointer", fontWeight: 600 }}>
              Back
            </button>
          )}
          {step < 4 ? (
            <button type="button" onClick={next} disabled={loading}
              style={{ flex: 2, padding: "12px", borderRadius: 12, border: "none", background: T.grad, color: "#fff", fontSize: 13, fontFamily: F.sans, cursor: "pointer", fontWeight: 600, boxShadow: "0 0 18px rgba(166,55,45,0.3)" }}>
              Next →
            </button>
          ) : (
            <button type="button" onClick={handleSubmit} disabled={loading}
              style={{ flex: 2, padding: "12px", borderRadius: 12, border: "none", background: T.grad, color: "#fff", fontSize: 13, fontFamily: F.sans, cursor: loading ? "wait" : "pointer", fontWeight: 600, boxShadow: "0 0 18px rgba(166,55,45,0.3)" }}>
              {loading ? "Creating account…" : "Create Account 🎉"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
