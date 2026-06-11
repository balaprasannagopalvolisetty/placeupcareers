import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Link, useNavigate } from "react-router";
import { ChevronDown, Eye, EyeOff, Search, X, Upload, Check } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import * as api from "../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  bg: "#011126", surface: "#C75A12",
  border: "rgba(242,238,179,0.1)", text: "#F2EEB3",
  t2: "rgba(242,238,179,0.65)", t3: "rgba(242,238,179,0.45)",
  grad: "linear-gradient(135deg, #F2A341, #ED7D2B, #C75A12)",
  red: "#ED7D2B", input: "rgba(242,238,179,0.05)",
};

function useViewportFlags() {
  const getWidth = () => (typeof window === "undefined" ? 1280 : window.innerWidth);
  const [width, setWidth] = useState(getWidth);

  useEffect(() => {
    const onResize = () => setWidth(getWidth());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return { isMobile: width < 640 };
}

interface TaxonomyRole { name: string }
interface TaxonomyCategory { name: string; roles: TaxonomyRole[] }

const LOCATION_SUGGESTIONS = [
  "Remote",
  "New York, NY",
  "San Francisco, CA",
  "San Jose, CA",
  "Seattle, WA",
  "Austin, TX",
  "Dallas, TX",
  "Chicago, IL",
  "Boston, MA",
  "Los Angeles, CA",
  "Irvine, CA",
  "Atlanta, GA",
  "Denver, CO",
  "Raleigh, NC",
  "Charlotte, NC",
  "Washington, DC",
  "Jersey City, NJ",
  "Phoenix, AZ",
  "Miami, FL",
  "United States",
];

const FALLBACK_TARGET_ROLES = [
  "Software Engineer",
  "Frontend Engineer",
  "Backend Engineer",
  "Full Stack Engineer",
  "Data Engineer",
  "Machine Learning Engineer",
  "Data Scientist",
  "DevOps / Cloud Engineer",
  "Cybersecurity Analyst",
  "Product Manager",
  "Business Analyst",
  "UX Designer",
];

function passwordChecks(value: string) {
  return {
    length: value.length >= 8,
    upper: /[A-Z]/.test(value),
    lower: /[a-z]/.test(value),
    number: /\d/.test(value),
    symbol: /[^A-Za-z0-9]/.test(value),
  };
}

function passwordError(value: string) {
  const checks = passwordChecks(value);
  if (!checks.length) return "Password must be at least 8 characters.";
  if (!checks.upper) return "Password must include at least one capital letter.";
  if (!checks.lower) return "Password must include at least one lowercase letter.";
  if (!checks.number) return "Password must include at least one number.";
  if (!checks.symbol) return "Password must include at least one symbol.";
  return null;
}

function isValidLinkedInUrl(value: string) {
  if (!value.trim()) return true;
  try {
    const url = new URL(value.trim());
    const host = url.hostname.replace(/^www\./, "").toLowerCase();
    return (url.protocol === "https:" || url.protocol === "http:") && host === "linkedin.com" && url.pathname.startsWith("/in/");
  } catch {
    return false;
  }
}

function validateResumeFile(file: File | null): string | null {
  if (!file) return "Please upload one resume to create your account.";
  const ext = file.name.toLowerCase().split(".").pop() || "";
  const allowedExt = new Set(["pdf", "docx"]);
  const allowedTypes = new Set([
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "",
  ]);
  if (!allowedExt.has(ext)) return "Please upload a PDF or Word DOCX resume only.";
  if (!allowedTypes.has(file.type)) return "This file type is not accepted. Upload a PDF or Word DOCX resume.";
  if (file.size <= 0) return "The selected resume file is empty.";
  if (file.size > 10 * 1024 * 1024) return "Resume file is too large. Maximum size is 10MB.";
  return null;
}

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

function PasswordRules({ value }: { value: string }) {
  const checks = passwordChecks(value);
  const rules = [
    { label: "8+ characters", ok: checks.length },
    { label: "Capital letter", ok: checks.upper },
    { label: "Lowercase letter", ok: checks.lower },
    { label: "Number", ok: checks.number },
    { label: "Symbol", ok: checks.symbol },
  ];
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginTop: 8 }}>
      {rules.map((rule) => (
        <div key={rule.label} style={{ display: "flex", alignItems: "center", gap: 5, color: rule.ok ? "#22c55e" : T.t3, fontSize: 11, fontFamily: F.sans }}>
          <Check size={11} /> {rule.label}
        </div>
      ))}
    </div>
  );
}

function AppSelect({ label, value, onChange, options, required, placeholder = "Select" }:
  { label: string; value: string; onChange: (v: string) => void; options: readonly string[]; required?: boolean; placeholder?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5, position: "relative" }}>
      <label style={{ fontSize: 12, fontWeight: 500, color: T.t2, fontFamily: F.sans }}>
        {label} {required ? <span style={{ color: T.red }}>*</span> : null}
      </label>
      <button type="button" onClick={() => setOpen((v) => !v)}
        style={{ height: 42, padding: "0 12px", borderRadius: 10, border: `1px solid ${open ? T.red : T.border}`,
          background: T.input, color: value ? T.text : T.t3, fontSize: 13, fontFamily: F.sans, outline: "none",
          display: "flex", alignItems: "center", justifyContent: "space-between", cursor: "pointer" }}>
        <span>{value || placeholder}</span>
        <ChevronDown size={14} color={T.t3} />
      </button>
      {open && (
        <div style={{ position: "absolute", top: 68, left: 0, right: 0, zIndex: 30, maxHeight: 220, overflowY: "auto",
          borderRadius: 10, border: `1px solid ${T.border}`, background: "#081426", boxShadow: "0 16px 40px rgba(1,17,38,0.5)", padding: 6 }}>
          {options.map((o) => (
            <button key={o} type="button" onClick={() => { onChange(o); setOpen(false); }}
              style={{ width: "100%", textAlign: "left", padding: "9px 10px", borderRadius: 8, border: "none",
                background: value === o ? "rgba(237,125,43,0.18)" : "transparent", color: T.text,
                fontSize: 13, fontFamily: F.sans, cursor: "pointer" }}>
              {o}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function LocationSuggestField({ label, value, onChange, placeholder }:
  { label: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  const matches = value.trim().length >= 4
    ? LOCATION_SUGGESTIONS.filter((item) => {
        const q = value.trim().toLowerCase();
        return item.toLowerCase() !== q && item.toLowerCase().includes(q);
      }).slice(0, 6)
    : [];
  return (
    <div style={{ position: "relative" }}>
      <Field label={label} value={value} onChange={onChange} placeholder={placeholder} />
      {matches.length > 0 && (
        <div style={{ position: "absolute", top: 66, left: 0, right: 0, zIndex: 25, borderRadius: 10,
          border: `1px solid ${T.border}`, background: "#081426", boxShadow: "0 16px 40px rgba(1,17,38,0.5)", padding: 6 }}>
          {matches.map((item) => (
            <button key={item} type="button" onClick={() => onChange(item)}
              style={{ width: "100%", textAlign: "left", padding: "8px 10px", borderRadius: 8, border: "none",
                background: "transparent", color: T.text, fontSize: 13, fontFamily: F.sans, cursor: "pointer" }}>
              {item}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function SignUp() {
  const navigate = useNavigate();
  const { signUp } = useAuth();
  const { isMobile } = useViewportFlags();

  // Step 1 — credentials
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
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
  const [roleSearch, setRoleSearch] = useState("");
  const [targetLocations, setTargetLocations] = useState<string[]>([]);
  const [locationInput, setLocationInput] = useState("");

  // Step 4 — resume
  const [resumeFile, setResumeFile] = useState<File | null>(null);

  const [step, setStep] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Load taxonomy once for the role picker.
  useEffect(() => {
    api.getJobTaxonomy()
      .then((data) => Array.isArray(data?.categories) && setTaxonomy(data.categories))
      .catch(() => {});
  }, []);

  const allRoles = Array.from(new Set([
    ...taxonomy.flatMap((c) => c.roles.map((r) => r.name).filter(Boolean)),
    ...FALLBACK_TARGET_ROLES,
  ]));
  const filteredRoles = allRoles
    .filter((role) => role.toLowerCase().includes(roleSearch.trim().toLowerCase()))
    .slice(0, 12);
  const visibleRoles = roleSearch.trim() ? filteredRoles : allRoles.slice(0, 12);
  const filteredLocationPrefs = locationInput.trim().length >= 4
    ? LOCATION_SUGGESTIONS.filter((item) => {
        const q = locationInput.trim().toLowerCase();
        return item.toLowerCase() !== q && item.toLowerCase().includes(q);
      }).slice(0, 6)
    : [];

  const toggleRole = (r: string) => {
    setTargetRoles((prev) => {
      if (prev.includes(r)) return prev.filter((x) => x !== r);
      if (prev.length >= 25) return prev;  // hard cap
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
      if (!firstName || !lastName || !email || !phone || !password || !confirm) return "Please complete all fields.";
      if (password !== confirm) return "Passwords do not match.";
      const passwordProblem = passwordError(password);
      if (passwordProblem) return passwordProblem;
    }
    if (step === 2) {
      if (!isValidLinkedInUrl(linkedinUrl)) return "Enter a valid LinkedIn profile URL like https://linkedin.com/in/your-name.";
      if (!visaStatus) return "Please select your visa status.";
    }
    if (step === 3) {
      if (targetRoles.length === 0) return "Pick at least one target role.";
    }
    if (step === 4) {
      const resumeProblem = validateResumeFile(resumeFile);
      if (resumeProblem) return resumeProblem;
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
        phone: phone || undefined,
        visa_status: visaStatus || undefined,
        experience_level: experienceLevel || undefined,
        current_role: currentRole || undefined,
        current_company: currentCompany || undefined,
        location: location || undefined,
        linkedin_url: linkedinUrl.trim() || undefined,
        target_roles: targetRoles,
        target_locations: targetLocations,
      });
      // After auth, upload the resume as the user's active resume before they
      // enter the dashboard so they are not asked to upload it again.
      if (resumeFile) {
        try {
          await api.uploadResume(resumeFile);
          window.dispatchEvent(new Event("placeup:resume-changed"));
        } catch (resumeError) {
          setError((resumeError as Error).message || "Account created, but resume upload failed. Please retry the secure resume upload before continuing.");
          return;
        }
      }
      navigate("/dashboard");
    } catch (err) {
      setError((err as Error).message || "Unable to create your account.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", justifyContent: "center", alignItems: "center", padding: isMobile ? 14 : 24, background: T.bg }}>
      <div style={{ width: "100%", maxWidth: 640, borderRadius: isMobile ? 18 : 24, background: "rgba(1,17,38,0.92)", border: `1px solid ${T.border}`, backdropFilter: "blur(28px)", padding: isMobile ? 18 : 32, boxShadow: "0 24px 64px rgba(1,17,38,0.4)" }}>
        <div style={{ display: "flex", flexDirection: isMobile ? "column" : "row", alignItems: isMobile ? "flex-start" : "center", justifyContent: "space-between", gap: isMobile ? 12 : 0, marginBottom: 24 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <img src="/logo_white.png" alt="PlaceUp Career" style={{ width: 34, height: 34, objectFit: "contain" }} />
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
          <motion.div initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 14 }}>
            <Field label="First Name" value={firstName} onChange={setFirstName} required />
            <Field label="Last Name" value={lastName} onChange={setLastName} required />
            <div style={{ gridColumn: "1 / -1" }}>
              <Field label="Gmail / Email" type="email" value={email} onChange={setEmail} placeholder="you@example.com" required />
            </div>
            <div style={{ gridColumn: "1 / -1" }}>
              <Field label="Phone Number" type="tel" value={phone} onChange={setPhone} placeholder="+1 555 012 3456" required />
            </div>
            <Field label="Password" type={showPass ? "text" : "password"} value={password} onChange={setPassword} required
              rightEl={<button onClick={() => setShowPass(!showPass)} style={{ background: "none", border: "none", cursor: "pointer", color: T.t3, padding: 0 }}>{showPass ? <EyeOff size={14} /> : <Eye size={14} />}</button>} />
            <Field label="Confirm Password" type="password" value={confirm} onChange={setConfirm} required />
            <div style={{ gridColumn: "1 / -1" }}>
              <PasswordRules value={password} />
            </div>
          </motion.div>
        )}

        {/* Step 2 — career */}
        {step === 2 && (
          <motion.div initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 14 }}>
            <div style={{ gridColumn: "1 / -1" }}>
              <Field label="LinkedIn Profile URL" value={linkedinUrl} onChange={setLinkedinUrl} placeholder="https://linkedin.com/in/..." />
            </div>
            <Field label="Current Role" value={currentRole} onChange={setCurrentRole} placeholder="Software Engineer" />
            <Field label="Current Company" value={currentCompany} onChange={setCurrentCompany} placeholder="Acme Corp" />
            <AppSelect label="Years of Experience" value={experienceLevel} onChange={setExperienceLevel} options={api.YEARS_OPTIONS} />
            <AppSelect label="Visa Status" value={visaStatus} onChange={setVisaStatus} options={api.VISA_STATUS_OPTIONS} required />
            <div style={{ gridColumn: "1 / -1" }}>
              <LocationSuggestField label="Current Location" value={location} onChange={setLocation} placeholder="Start typing, e.g. San F" />
            </div>
          </motion.div>
        )}

        {/* Step 3 — preferences */}
        {step === 3 && (
          <motion.div initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }}>
            <div style={{ marginBottom: 18 }}>
              <div style={{ fontSize: 12, fontWeight: 500, color: T.t2, fontFamily: F.sans, marginBottom: 6 }}>
                Job Preferences <span style={{ color: T.red }}>*</span>
                <span style={{ marginLeft: 6, fontSize: 11, color: T.t3 }}>pick up to 25 ({targetRoles.length}/25)</span>
              </div>
              <div style={{ position: "relative", border: `1px solid ${T.border}`, borderRadius: 10, padding: 8, background: T.input }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, height: 38, padding: "0 10px", borderRadius: 8, background: "rgba(1,17,38,0.35)", border: `1px solid ${T.border}` }}>
                  <Search size={14} color={T.t3} />
                  <input value={roleSearch} onChange={(e) => setRoleSearch(e.target.value)} placeholder="Search and select target roles"
                    style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: T.text, fontSize: 13, fontFamily: F.sans }} />
                  <ChevronDown size={14} color={T.t3} />
                </div>
                <div style={{ maxHeight: 180, overflowY: "auto", marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                  {visibleRoles.map((role) => {
                    const sel = targetRoles.includes(role);
                    const disabled = !sel && targetRoles.length >= 25;
                    return (
                      <button key={role} type="button" onClick={() => toggleRole(role)} disabled={disabled}
                        style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 10px", borderRadius: 8, border: "none",
                          background: sel ? "rgba(237,125,43,0.18)" : "transparent", color: disabled ? T.t3 : T.text,
                          fontSize: 13, fontFamily: F.sans, cursor: disabled ? "not-allowed" : "pointer", textAlign: "left" }}>
                        <span>{role}</span>
                        {sel && <Check size={13} color="#22c55e" />}
                      </button>
                    );
                  })}
                  {visibleRoles.length === 0 && (
                    <button type="button" onClick={() => roleSearch.trim() && toggleRole(roleSearch.trim())}
                      style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 10px", borderRadius: 8, border: "none",
                        background: "transparent", color: T.t2, fontSize: 13, fontFamily: F.sans, cursor: roleSearch.trim() ? "pointer" : "default", textAlign: "left" }}>
                      <span>{roleSearch.trim() ? `Use "${roleSearch.trim()}"` : "Start typing to search roles"}</span>
                    </button>
                  )}
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 8 }}>
                  {targetRoles.map((role) => (
                    <span key={role} style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11, padding: "3px 8px", borderRadius: 4, background: "rgba(237,125,43,0.1)", color: T.red, border: "1px solid rgba(237,125,43,0.25)", fontFamily: F.sans }}>
                      {role}
                      <button type="button" onClick={() => toggleRole(role)} style={{ background: "none", border: "none", cursor: "pointer", color: T.red, padding: 0 }}><X size={10} /></button>
                    </span>
                  ))}
                </div>
              </div>
            </div>

            <div>
              <div style={{ fontSize: 12, fontWeight: 500, color: T.t2, fontFamily: F.sans, marginBottom: 6 }}>Location Preferences</div>
              <div style={{ display: "flex", flexDirection: isMobile ? "column" : "row", gap: 8 }}>
                <input value={locationInput} onChange={(e) => setLocationInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addLocation(); } }}
                  placeholder="Type 4+ letters, e.g. San F"
                  style={{ flex: 1, height: 38, padding: "0 12px", borderRadius: 10, border: `1px solid ${T.border}`, background: T.input, color: T.text, fontSize: 13, fontFamily: F.sans, outline: "none" }} />
                <button type="button" onClick={addLocation} style={{ height: 38, padding: "0 16px", borderRadius: 10, border: "none", background: T.grad, color: "#fff", fontSize: 12, fontWeight: 600, fontFamily: F.sans, cursor: "pointer" }}>Add</button>
              </div>
              {filteredLocationPrefs.length > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 8 }}>
                  {filteredLocationPrefs.map((item) => (
                    <button key={item} type="button" onClick={() => { setLocationInput(item); if (!targetLocations.includes(item)) setTargetLocations((prev) => [...prev, item]); }}
                      style={{ fontSize: 11, padding: "4px 9px", borderRadius: 4, fontFamily: F.sans, cursor: "pointer",
                        background: "rgba(242,238,179,0.05)", color: T.t2, border: `1px solid ${T.border}` }}>
                      {item}
                    </button>
                  ))}
                </div>
              )}
              <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 8 }}>
                {targetLocations.map((l) => (
                  <span key={l} style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11, padding: "3px 8px", borderRadius: 4, background: "rgba(237,125,43,0.1)", color: T.red, border: "1px solid rgba(237,125,43,0.25)", fontFamily: F.sans }}>
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
            <label style={{ display: "block", padding: 28, borderRadius: 12, border: `2px dashed ${resumeFile ? T.red : "rgba(237,125,43,0.3)"}`, background: T.input, textAlign: "center", cursor: "pointer", transition: "all 0.2s" }}>
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
                  <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans }}>PDF or Word DOCX, max 10MB</div>
                </div>
              )}
              <input type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" style={{ display: "none" }}
                onChange={(e) => {
                  const file = e.target.files?.[0] ?? null;
                  const fileProblem = validateResumeFile(file);
                  setResumeFile(fileProblem ? null : file);
                  setError(fileProblem);
                }} />
            </label>
            <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans, marginTop: 12, lineHeight: 1.55 }}>
              Your resume is security-checked for active PDF/DOCX content, parsed into private JSON, and saved as your active resume. You can replace it later from the Resumes tab.
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
              style={{ flex: 2, padding: "12px", borderRadius: 12, border: "none", background: T.grad, color: "#fff", fontSize: 13, fontFamily: F.sans, cursor: "pointer", fontWeight: 600, boxShadow: "0 0 18px rgba(237,125,43,0.3)" }}>
              Next →
            </button>
          ) : (
            <button type="button" onClick={handleSubmit} disabled={loading}
              style={{ flex: 2, padding: "12px", borderRadius: 12, border: "none", background: T.grad, color: "#fff", fontSize: 13, fontFamily: F.sans, cursor: loading ? "wait" : "pointer", fontWeight: 600, boxShadow: "0 0 18px rgba(237,125,43,0.3)" }}>
              {loading ? "Creating account…" : "Create Account 🎉"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
