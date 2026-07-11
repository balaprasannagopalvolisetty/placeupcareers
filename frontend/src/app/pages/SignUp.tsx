import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "motion/react";
import { Link, useNavigate } from "react-router";
import { ChevronDown, CreditCard, Eye, EyeOff, Search, ShieldCheck, Upload, Check, X } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import * as api from "../lib/api";
import { BrandLogo } from "../components/BrandLogo";
import {
  COUNTRIES,
  COUNTRY_BY_CODE,
  DEFAULT_PHONE_COUNTRY,
  visaOptionsForCountry,
} from "../lib/countries";

const AGREEMENT_VERSION = "2026-06-21";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
// Clean, light SaaS palette (matches Home / SignIn).
const T = {
  bg: "var(--pu-f8fafc-b)", surface: "var(--pu-ffffff-b)",
  border: "var(--pu-e2e8f0-b)", text: "var(--pu-0f172a-t)",
  t2: "var(--pu-475569-t)", t3: "var(--pu-94a3b8-t)",
  grad: "linear-gradient(135deg, var(--pu-2563eb), var(--pu-0ea5e9))",
  red: "var(--pu-2563eb)", input: "var(--pu-f8fafc-b)",
  panel: "var(--pu-ffffff-b)",
};

const STEP_LABELS = ["Account", "Terms", "Profile", "Top 5 Positions", "Payment", "Verify", "Resume"];
const TOTAL_STEPS = STEP_LABELS.length;
// Users pick exactly this many positions — no more, no less.
const MAX_TARGET_ROLES = 5;
const GENDER_OPTIONS = ["Male", "Female", "Non-binary", "Prefer not to answer", "Self-describe"];
const RACE_OPTIONS = ["Asian", "Black or African American", "Hispanic or Latino", "Middle Eastern or North African", "Native American or Alaska Native", "Native Hawaiian or Pacific Islander", "White", "Two or more races", "Prefer not to answer", "Self-describe"];
const DISABILITY_OPTIONS = ["No", "Yes", "Prefer not to answer"];
const VETERAN_OPTIONS = ["Not a veteran", "Veteran", "Protected veteran", "Prefer not to answer"];
const YES_NO_OPTIONS = ["Yes", "No"];

// Fallback position list used only if the /api/jobs/taxonomy fetch fails or
// returns nothing (e.g. local dev with no API proxy, or a transient outage).
// Keeps the picker usable so signup never dead-ends. Mirrors the backend
// taxonomy role names — the live API list supersedes this whenever it loads.
const FALLBACK_ROLES: string[] = [
  "Software Engineer", "Frontend Engineer", "Backend Engineer", "Full Stack Engineer",
  "Data Engineer", "Machine Learning Engineer", "Data Scientist", "DevOps / Cloud Engineer",
  "Cybersecurity Analyst", "Security Engineer", "QA / Test Engineer", "Systems Engineer",
  "Network Engineer", "Database Administrator", "Solutions Architect", "CRM / ERP Developer",
  "IT Support / Analyst", "Product Manager (Tech)", "UI/UX Designer", "Blockchain Developer",
  "AI Research Scientist", "Business Analyst", "Data Analyst", "Business Intelligence Developer",
  "Analytics Engineer", "Quantitative Analyst", "Research Analyst", "Operations Research Analyst",
  "Statistician", "Financial Analyst", "Investment Banking Analyst", "Accountant / CPA",
  "Risk Analyst", "Financial Consultant", "Actuary", "Compliance Analyst", "Treasury Analyst",
  "Tax Analyst", "Clinical Research Associate", "Biomedical Engineer", "Pharmaceutical Scientist",
  "Healthcare Data Analyst", "Bioinformatics Scientist", "Regulatory Affairs Specialist",
  "Public Health Analyst", "Lab Technician / Research Assistant", "Medical Technologist",
  "Mechanical Engineer", "Civil Engineer", "Electrical Engineer", "Chemical Engineer",
  "Industrial Engineer", "Aerospace Engineer", "Environmental Engineer", "Structural Engineer",
  "Management Consultant", "Operations Manager", "Project Manager", "Supply Chain Analyst",
  "Human Resources Generalist", "Strategy Analyst", "Scrum Master / Agile Coach",
  "Technical Program Manager", "Digital Marketing Analyst", "Content Strategist",
  "Marketing Data Analyst", "Social Media Manager", "Brand Manager",
  "Marketing Operations Specialist", "Research Assistant / Associate", "Teaching Assistant",
  "Instructional Designer", "Education Program Coordinator", "Academic Advisor",
  "ESL / Language Instructor", "Policy Analyst", "Government IT Specialist", "Intelligence Analyst",
  "Urban / City Planner", "Environmental Policy Analyst", "Product / UX Designer",
  "Graphic Designer", "Video / Motion Designer", "Architect", "Paralegal", "Contract Analyst",
  "Immigration Paralegal", "IP / Patent Analyst", "Compliance Officer",
].sort((a, b) => a.localeCompare(b));
const HIDDEN_ROLE_PATTERN = /\b(volunteer|intern|open source contributor|community tech educator|growth hacker)\b/i;
const isVisibleRole = (role: string) => Boolean(role.trim()) && !HIDDEN_ROLE_PATTERN.test(role);

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
  const c = passwordChecks(value);
  if (!c.length) return "Password must be at least 8 characters.";
  if (!c.upper) return "Password must include at least one capital letter.";
  if (!c.lower) return "Password must include at least one lowercase letter.";
  if (!c.number) return "Password must include at least one number.";
  if (!c.symbol) return "Password must include at least one symbol.";
  return null;
}

function isValidEmail(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
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
  if (!file) return "Please upload one resume to finish creating your account.";
  const ext = file.name.toLowerCase().split(".").pop() || "";
  const allowedExt = new Set(["pdf", "docx"]);
  if (!allowedExt.has(ext)) return "Please upload a PDF or DOCX resume only.";
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

function Dropdown({ label, value, onChange, options, required, placeholder = "Select", renderOption }:
  { label: string; value: string; onChange: (v: string) => void; options: readonly string[]; required?: boolean; placeholder?: string; renderOption?: (o: string) => React.ReactNode }) {
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
        <span>{value ? (renderOption ? renderOption(value) : value) : placeholder}</span>
        <ChevronDown size={14} color={T.t3} />
      </button>
      {open && (
        <div style={{ position: "absolute", top: 68, left: 0, right: 0, zIndex: 30, maxHeight: 240, overflowY: "auto",
          borderRadius: 10, border: `1px solid ${T.border}`, background: T.panel, boxShadow: "0 12px 32px var(--pu-15-23-42-012)", padding: 6 }}>
          {options.map((o) => (
            <button key={o} type="button" onClick={() => { onChange(o); setOpen(false); }}
              style={{ width: "100%", textAlign: "left", padding: "9px 10px", borderRadius: 8, border: "none",
                background: value === o ? "var(--pu-37-99-235-01)" : "transparent", color: T.text,
                fontSize: 13, fontFamily: F.sans, cursor: "pointer" }}>
              {renderOption ? renderOption(o) : o}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function CountryDropdown({ label, value, onChange, required }:
  { label: string; value: string; onChange: (code: string) => void; required?: boolean }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const selected = value ? COUNTRY_BY_CODE[value] : undefined;
  const list = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return COUNTRIES;
    return COUNTRIES.filter((c) => c.name.toLowerCase().includes(needle) || c.code.toLowerCase() === needle);
  }, [q]);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5, position: "relative" }}>
      <label style={{ fontSize: 12, fontWeight: 500, color: T.t2, fontFamily: F.sans }}>
        {label} {required ? <span style={{ color: T.red }}>*</span> : null}
      </label>
      <button type="button" onClick={() => setOpen((v) => !v)}
        style={{ height: 42, padding: "0 12px", borderRadius: 10, border: `1px solid ${open ? T.red : T.border}`,
          background: T.input, color: selected ? T.text : T.t3, fontSize: 13, fontFamily: F.sans, outline: "none",
          display: "flex", alignItems: "center", justifyContent: "space-between", cursor: "pointer" }}>
        <span>{selected ? `${selected.flag}  ${selected.name}` : "Select your country"}</span>
        <ChevronDown size={14} color={T.t3} />
      </button>
      {open && (
        <div style={{ position: "absolute", top: 68, left: 0, right: 0, zIndex: 40, borderRadius: 10,
          border: `1px solid ${T.border}`, background: T.panel, boxShadow: "0 12px 32px var(--pu-15-23-42-012)", padding: 6 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, height: 36, padding: "0 10px", borderRadius: 8, background: "var(--pu-f1f5f9-b)", border: `1px solid ${T.border}`, marginBottom: 6 }}>
            <Search size={14} color={T.t3} />
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search country"
              style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: T.text, fontSize: 13, fontFamily: F.sans }} />
          </div>
          <div style={{ maxHeight: 220, overflowY: "auto" }}>
            {list.map((c) => (
              <button key={c.code} type="button" onClick={() => { onChange(c.code); setOpen(false); setQ(""); }}
                style={{ width: "100%", textAlign: "left", padding: "8px 10px", borderRadius: 8, border: "none",
                  background: value === c.code ? "var(--pu-37-99-235-01)" : "transparent", color: T.text,
                  fontSize: 13, fontFamily: F.sans, cursor: "pointer", display: "flex", gap: 8 }}>
                <span>{c.flag}</span><span>{c.name}</span>
                <span style={{ marginLeft: "auto", color: T.t3 }}>{c.dial}</span>
              </button>
            ))}
            {list.length === 0 && <div style={{ padding: 10, color: T.t3, fontSize: 12 }}>No matches</div>}
          </div>
        </div>
      )}
    </div>
  );
}

function PhoneInput({ countryCode, onCountry, number, onNumber }:
  { countryCode: string; onCountry: (code: string) => void; number: string; onNumber: (v: string) => void }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const wrapRef = useRef<HTMLDivElement>(null);
  const country = COUNTRY_BY_CODE[countryCode] || COUNTRIES[0];
  const list = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return COUNTRIES;
    return COUNTRIES.filter((c) => c.name.toLowerCase().includes(needle) || c.dial.includes(needle) || c.code.toLowerCase() === needle);
  }, [q]);
  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <label style={{ fontSize: 12, fontWeight: 500, color: T.t2, fontFamily: F.sans }}>
        Phone Number <span style={{ color: T.red }}>*</span>
      </label>
      <div ref={wrapRef} style={{ position: "relative", display: "flex", gap: 8 }}>
        <button type="button" onClick={() => setOpen((v) => !v)}
          style={{ height: 42, padding: "0 10px", borderRadius: 10, border: `1px solid ${open ? T.red : T.border}`,
            background: T.input, color: T.text, fontSize: 13, fontFamily: F.sans, cursor: "pointer",
            display: "flex", alignItems: "center", gap: 6, whiteSpace: "nowrap" }}>
          <span style={{ fontSize: 16 }}>{country.flag}</span>
          <span>{country.dial}</span>
          <ChevronDown size={13} color={T.t3} />
        </button>
        <input type="tel" inputMode="tel" value={number} placeholder="555 012 3456"
          onChange={(e) => onNumber(e.target.value.replace(/[^\d\s()-]/g, ""))}
          style={{ flex: 1, height: 42, padding: "0 12px", borderRadius: 10, border: `1px solid ${T.border}`,
            background: T.input, color: T.text, fontSize: 13, fontFamily: F.sans, outline: "none", boxSizing: "border-box" }} />
        {open && (
          <div style={{ position: "absolute", top: 48, left: 0, width: 300, zIndex: 40, borderRadius: 10,
            border: `1px solid ${T.border}`, background: T.panel, boxShadow: "0 12px 32px var(--pu-15-23-42-012)", padding: 6 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, height: 36, padding: "0 10px", borderRadius: 8, background: "var(--pu-f1f5f9-b)", border: `1px solid ${T.border}`, marginBottom: 6 }}>
              <Search size={14} color={T.t3} />
              <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search country or code"
                style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: T.text, fontSize: 13, fontFamily: F.sans }} />
            </div>
            <div style={{ maxHeight: 220, overflowY: "auto" }}>
              {list.map((c) => (
                <button key={c.code} type="button" onClick={() => { onCountry(c.code); setOpen(false); setQ(""); }}
                  style={{ width: "100%", textAlign: "left", padding: "8px 10px", borderRadius: 8, border: "none",
                    background: countryCode === c.code ? "var(--pu-37-99-235-01)" : "transparent", color: T.text,
                    fontSize: 13, fontFamily: F.sans, cursor: "pointer", display: "flex", gap: 8 }}>
                  <span>{c.flag}</span><span style={{ flex: 1 }}>{c.name}</span>
                  <span style={{ color: T.t3 }}>{c.dial}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function PasswordRules({ value }: { value: string }) {
  const c = passwordChecks(value);
  const rules = [
    { label: "8+ characters", ok: c.length },
    { label: "Capital letter", ok: c.upper },
    { label: "Lowercase letter", ok: c.lower },
    { label: "Number", ok: c.number },
    { label: "Symbol", ok: c.symbol },
  ];
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginTop: 8 }}>
      {rules.map((r) => (
        <div key={r.label} style={{ display: "flex", alignItems: "center", gap: 5, color: r.ok ? "var(--pu-16a34a)" : T.t3, fontSize: 11, fontFamily: F.sans }}>
          <Check size={11} /> {r.label}
        </div>
      ))}
    </div>
  );
}

function RolePicker({
  roles,
  selected,
  search,
  onSearch,
  onToggle,
}: {
  roles: string[];
  selected: string[];
  search: string;
  onSearch: (value: string) => void;
  onToggle: (role: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const full = selected.length >= MAX_TARGET_ROLES;

  // Close the drop box when clicking outside it.
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return roles
      .filter((role) => !q || role.toLowerCase().includes(q))
      .slice(0, 90);
  }, [roles, search]);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center", marginBottom: 8 }}>
        <div>
          <div style={{ fontSize: 13, color: T.text, fontFamily: F.sans, fontWeight: 700 }}>Choose your {MAX_TARGET_ROLES} target positions</div>
          <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans, marginTop: 3 }}>Pick exactly {MAX_TARGET_ROLES} positions. These power your job matches and daily recommendations.</div>
        </div>
        <div style={{ fontSize: 12, color: full ? "var(--pu-16a34a)" : T.red, fontFamily: F.mono, fontWeight: 800 }}>
          {selected.length}/{MAX_TARGET_ROLES}
        </div>
      </div>

      {/* Drop box */}
      <div ref={wrapRef} style={{ position: "relative" }}>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          style={{
            width: "100%", minHeight: 48, padding: "8px 12px", borderRadius: 10,
            background: T.input, border: `1px solid ${open ? T.accent : T.border}`,
            boxShadow: open ? "0 0 0 3px var(--pu-37-99-235-012)" : "none",
            display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8,
            cursor: "pointer", textAlign: "left",
          }}
        >
          <span style={{ fontSize: 13.5, fontFamily: F.sans, color: selected.length ? T.text : T.t3 }}>
            {selected.length
              ? `${selected.length} of ${MAX_TARGET_ROLES} position${selected.length > 1 ? "s" : ""} selected`
              : "Select positions…"}
          </span>
          <ChevronDown size={16} color={T.t3} style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform 0.15s", flexShrink: 0 }} />
        </button>

        {open && (
          <div style={{
            position: "absolute", top: 54, left: 0, right: 0, zIndex: 40,
            borderRadius: 12, border: `1px solid ${T.border}`, background: T.surface,
            boxShadow: "0 12px 30px var(--pu-15-23-42-012)", padding: 8,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, height: 40, padding: "0 12px", borderRadius: 10, background: T.input, border: `1px solid ${T.border}`, marginBottom: 8 }}>
              <Search size={14} color={T.t3} />
              <input autoFocus value={search} onChange={(e) => onSearch(e.target.value)} placeholder="Search role, e.g. Security Analyst"
                style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: T.text, fontSize: 13, fontFamily: F.sans }} />
            </div>
            <div style={{ maxHeight: 240, overflowY: "auto", display: "grid", gridTemplateColumns: "1fr", gap: 6 }}>
              {visible.length === 0 && (
                <div style={{ padding: 12, fontSize: 12.5, color: T.t3, fontFamily: F.sans, textAlign: "center" }}>No roles match “{search}”.</div>
              )}
              {visible.map((role) => {
                const active = selected.includes(role);
                const disabled = !active && full;
                return (
                  <button key={role} type="button" disabled={disabled} onClick={() => onToggle(role)}
                    title={disabled ? `You can only pick ${MAX_TARGET_ROLES} positions. Remove one to change your selection.` : undefined}
                    style={{ minHeight: 38, padding: "8px 10px", borderRadius: 9, border: `1px solid ${active ? "var(--pu-22-163-74-035)" : "transparent"}`,
                      background: active ? "var(--pu-34-197-94-01)" : "transparent", color: disabled ? T.t3 : T.text,
                      fontSize: 13, fontFamily: F.sans, cursor: disabled ? "not-allowed" : "pointer", textAlign: "left",
                      display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                    <span>{role}</span>
                    {active && <Check size={13} color="var(--pu-16a34a)" />}
                  </button>
                );
              })}
            </div>
            {full && (
              <div style={{ padding: "8px 10px", marginTop: 6, fontSize: 11.5, color: "var(--pu-16a34a)", fontFamily: F.sans, background: "var(--pu-34-197-94-008)", borderRadius: 8 }}>
                All {MAX_TARGET_ROLES} positions selected. Remove one to swap.
              </div>
            )}
          </div>
        )}
      </div>

      {/* Selected chips */}
      {selected.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
          {selected.map((role) => (
            <span key={role} style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, fontWeight: 700, padding: "5px 8px", borderRadius: 999, background: "var(--pu-37-99-235-008)", color: T.red, border: "1px solid var(--pu-37-99-235-022)", fontFamily: F.sans }}>
              {role}
              <button type="button" onClick={() => onToggle(role)} style={{ background: "none", border: "none", color: T.red, cursor: "pointer", padding: 0, display: "flex" }}><X size={11} /></button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

const PRIMARY_BTN: React.CSSProperties = {
  flex: 2, padding: "12px", borderRadius: 12, border: "none", background: T.grad, color: "var(--pu-ffffff-t)",
  fontSize: 13.5, fontFamily: F.sans, cursor: "pointer", fontWeight: 700, boxShadow: "0 8px 20px var(--pu-37-99-235-025)",
};
const GHOST_BTN: React.CSSProperties = {
  flex: 1, padding: "12px", borderRadius: 12, border: `1px solid ${T.border}`, background: "transparent",
  color: T.t2, fontSize: 13, fontFamily: F.sans, cursor: "pointer", fontWeight: 600,
};

export default function SignUp() {
  const navigate = useNavigate();
  const { signUp, verifySignupOtp } = useAuth();
  const { isMobile } = useViewportFlags();

  const [step, setStep] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [phoneCountry, setPhoneCountry] = useState(DEFAULT_PHONE_COUNTRY);
  const [phoneNumber, setPhoneNumber] = useState("");

  const [agreed, setAgreed] = useState(false);
  const [disagreed, setDisagreed] = useState(false);

  const [linkedinUrl, setLinkedinUrl] = useState("");
  const [currentCompany, setCurrentCompany] = useState("");
  const [experienceLevel, setExperienceLevel] = useState("");
  const [country, setCountry] = useState("US");
  const [targetCountry, setTargetCountry] = useState("US");
  const [visaStatus, setVisaStatus] = useState("");
  const [visaOther, setVisaOther] = useState("");
  const [gender, setGender] = useState("");
  const [raceEthnicity, setRaceEthnicity] = useState("");
  const [disabilityStatus, setDisabilityStatus] = useState("");
  const [veteranStatus, setVeteranStatus] = useState("");
  const [openToRelocation, setOpenToRelocation] = useState("");
  const [authorizedToWork, setAuthorizedToWork] = useState("");
  const [requiresSponsorship, setRequiresSponsorship] = useState("");
  const [allRoles, setAllRoles] = useState<string[]>(FALLBACK_ROLES);
  const [roleSearch, setRoleSearch] = useState("");
  const [targetRoles, setTargetRoles] = useState<string[]>([]);

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [otpSent, setOtpSent] = useState(false);
  const [otpCode, setOtpCode] = useState("");

  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [plans, setPlans] = useState<api.PaymentPlan[]>([]);
  const [selectedPlan, setSelectedPlan] = useState("pro");
  const [paymentReference, setPaymentReference] = useState("");
  const [paymentMessage, setPaymentMessage] = useState("Choose the monthly plan that fits your job search.");

  const visaOptions = useMemo(() => visaOptionsForCountry(country), [country]);
  useEffect(() => {
    if (visaStatus && !visaOptions.includes(visaStatus)) {
      setVisaStatus("");
      setVisaOther("");
    }
  }, [country]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    let active = true;
    api.getJobTaxonomy()
      .then((taxonomy) => {
        if (!active) return;
        const roles = Array.from(new Set((taxonomy.categories || []).flatMap((cat) => cat.roles.map((role: any) => String(role.name || "")).filter(isVisibleRole))));
        // Only replace the fallback if the API actually returned roles; an
        // empty response shouldn't blank out the picker.
        if (roles.length) setAllRoles(roles.sort((a, b) => a.localeCompare(b)));
      })
      // Network/API failure: keep FALLBACK_ROLES so the picker stays usable.
      .catch(() => {});
    return () => { active = false; };
  }, []);
  useEffect(() => {
    let active = true;
    api.getPaymentPlans()
      .then((res) => {
        if (!active) return;
        const available = Array.isArray(res.plans) ? res.plans : [];
        setPlans(available);
        if (available.some((plan) => plan.id === "pro")) setSelectedPlan("pro");
        if (res.message) setPaymentMessage(res.message);
      })
      .catch(() => {
        if (!active) return;
        setPlans([
          { id: "basic", name: "Basic", price: 9.99, interval: "m", features: ["Job matching", "Resume ATS score", "Saved jobs"] },
          { id: "pro", name: "Pro", price: 24.99, interval: "m", features: ["Everything in Basic", "Recruiter contacts", "Application tracking", "Priority job matches"] },
          { id: "elite", name: "Elite", price: 149.99, interval: "m", features: ["Everything in Pro", "Premium enrichment", "Visa sponsor insights", "Concierge support", "Dedicated employee applies for you to 25-30 filtered positions daily"] },
        ]);
      });
    return () => { active = false; };
  }, []);

  const fullPhone = () => {
    const dial = (COUNTRY_BY_CODE[phoneCountry] || COUNTRIES[0]).dial;
    return `${dial} ${phoneNumber.trim()}`.trim();
  };
  const boolAnswer = (value: string) => value ? value === "Yes" : undefined;
  const countryName = (code: string) => COUNTRY_BY_CODE[code]?.name || code;

  const validateStep = (): string | null => {
    if (step === 1) {
      if (!firstName.trim() || !lastName.trim()) return "Please enter your first and last name.";
      if (!isValidEmail(email)) return "Please enter a valid email address.";
      if (phoneNumber.replace(/\D/g, "").length < 6) return "Please enter a valid phone number.";
    }
    if (step === 2) {
      if (!agreed) return "You must accept the Terms of Service and Privacy Policy to continue.";
    }
    if (step === 3) {
      if (!isValidLinkedInUrl(linkedinUrl)) return "Enter a valid LinkedIn profile URL like https://linkedin.com/in/your-name.";
      if (!country) return "Please select your country.";
      if (!targetCountry) return "Please select your target country.";
      if (!visaStatus) return "Please select your visa / work-authorization status.";
      if (visaStatus === "Other" && !visaOther.trim()) return "Please describe your visa / work-authorization status.";
      if (!authorizedToWork) return "Please answer whether you are currently authorized to work in your target country.";
      if (!requiresSponsorship) return "Please answer whether you need visa sponsorship.";
    }
    if (step === 4) {
      if (targetRoles.length !== MAX_TARGET_ROLES) return `Please select exactly ${MAX_TARGET_ROLES} target positions so your Jobs feed stays relevant.`;
    }
    if (step === 5) {
      if (!selectedPlan) return "Please choose a plan to continue.";
    }
    return null;
  };

  const next = () => {
    const err = validateStep();
    if (err) { setError(err); return; }
    setError(null);
    setStep((s) => Math.min(TOTAL_STEPS, s + 1));
  };
  const back = () => { setError(null); setStep((s) => Math.max(1, s - 1)); };

  const createAccountAndSendCode = async () => {
    const passProblem = passwordError(password);
    if (passProblem) { setError(passProblem); return; }
    if (password !== confirm) { setError("Passwords do not match."); return; }
    setError(null);
    setLoading(true);
    try {
      const payload: api.SignupPayload = {
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: email.trim(),
        password,
        phone: fullPhone(),
        country,
        visa_status: visaStatus,
        visa_status_other: visaStatus === "Other" ? visaOther.trim() : undefined,
        experience_level: experienceLevel || undefined,
        current_company: currentCompany.trim() || undefined,
        linkedin_url: linkedinUrl.trim() || undefined,
        gender: gender || undefined,
        race_ethnicity: raceEthnicity || undefined,
        disability_status: disabilityStatus || undefined,
        veteran_status: veteranStatus || undefined,
        open_to_relocation: boolAnswer(openToRelocation),
        authorized_to_work: boolAnswer(authorizedToWork),
        requires_sponsorship: boolAnswer(requiresSponsorship),
        target_roles: targetRoles.slice(0, MAX_TARGET_ROLES),
        target_locations: [countryName(targetCountry)],
        agreement_accepted: true,
        agreement_version: AGREEMENT_VERSION,
        payment_plan: selectedPlan || "pro",
        payment_reference: paymentReference || "free_preview",
      };
      const result = await signUp(payload);
      if ("otp_required" in result && result.otp_required) {
        setOtpSent(true);
      } else {
        setStep(7);
      }
    } catch (err) {
      setError((err as Error).message || "Unable to create your account.");
    } finally {
      setLoading(false);
    }
  };

  const verifyCode = async () => {
    if (otpCode.trim().length < 4) { setError("Enter the 6-digit code we emailed you."); return; }
    setError(null);
    setLoading(true);
    try {
      await verifySignupOtp(email.trim(), otpCode.trim());
      setStep(7);
    } catch (err) {
      setError((err as Error).message || "Invalid or expired code.");
    } finally {
      setLoading(false);
    }
  };

  const toggleTargetRole = (role: string) => {
    setTargetRoles((prev) => {
      if (prev.includes(role)) return prev.filter((item) => item !== role);
      if (prev.length >= MAX_TARGET_ROLES) return prev;
      return [...prev, role];
    });
  };

  const resendCode = async () => {
    setError(null);
    try {
      await api.requestOtp(email.trim(), "signup");
    } catch (err) {
      setError((err as Error).message || "Could not resend the code.");
    }
  };

  const handlePaymentContinue = async () => {
    const plan = plans.find((item) => item.id === selectedPlan);
    if (!plan) {
      setError("Please choose a plan to continue.");
      return;
    }
    setError(null);
    if (Number(plan.price || 0) <= 0) {
      setPaymentReference("free_preview");
      setStep(6);
      return;
    }
    setLoading(true);
    try {
      const checkout = await api.getPublicCheckoutLink(selectedPlan);
      if (checkout.checkout_url) {
        window.open(checkout.checkout_url, "_blank", "noopener,noreferrer");
        setPaymentReference(`hosted_checkout_started:${selectedPlan}`);
        setPaymentMessage("Checkout opened in a new tab. Return here after payment to finish account creation.");
      } else {
        setPaymentReference("checkout_not_configured");
        setPaymentMessage(checkout.message || "Checkout is not configured yet, so your plan selection is saved and you can continue.");
      }
      setStep(6);
    } catch (err) {
      setError((err as Error).message || "Could not start checkout. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const finishWithResume = async () => {
    const fileProblem = validateResumeFile(resumeFile);
    if (fileProblem) { setError(fileProblem); return; }
    setError(null);
    setLoading(true);
    try {
      await api.uploadResume(resumeFile as File);
      window.dispatchEvent(new Event("placeup:resume-changed"));
      navigate("/dashboard");
    } catch (err) {
      setError((err as Error).message || "Resume upload failed. Please retry.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", justifyContent: "center", alignItems: "center", padding: isMobile ? 14 : 24, background: `radial-gradient(900px 400px at 50% -5%, var(--pu-37-99-235-006), transparent 70%), ${T.bg}` }}>
      <div style={{ width: "100%", maxWidth: 640, borderRadius: isMobile ? 18 : 24, background: "var(--pu-ffffff-b)", border: `1px solid ${T.border}`, padding: isMobile ? 18 : 32, boxShadow: "0 4px 12px var(--pu-15-23-42-006), 0 24px 56px var(--pu-15-23-42-01)" }}>
        <div style={{ display: "flex", flexDirection: isMobile ? "column" : "row", alignItems: isMobile ? "flex-start" : "center", justifyContent: "space-between", gap: isMobile ? 12 : 0, marginBottom: 20 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <BrandLogo variant="dark" height={44} />
            <div>
              <div style={{ fontFamily: F.sans, fontSize: 17, fontWeight: 700, color: T.text }}>Create your account</div>
              <div style={{ fontSize: 12, color: T.t2, fontFamily: F.sans }}>Step {step} of {TOTAL_STEPS} · {STEP_LABELS[step - 1]}</div>
            </div>
          </div>
          <Link to="/signin" style={{ color: T.red, fontSize: 12, fontWeight: 600, fontFamily: F.sans, textDecoration: "none" }}>Already have an account?</Link>
        </div>

        <div style={{ display: "flex", gap: 6, marginBottom: 22 }}>
          {STEP_LABELS.map((_, i) => (
            <div key={i} style={{ flex: 1, height: 3, borderRadius: 2, background: i + 1 <= step ? T.grad : "var(--pu-e2e8f0-b)" }} />
          ))}
        </div>

        {step === 1 && (
          <motion.div initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 14 }}>
            <Field label="First Name" value={firstName} onChange={setFirstName} required />
            <Field label="Last Name" value={lastName} onChange={setLastName} required />
            <div style={{ gridColumn: "1 / -1" }}>
              <Field label="Email" type="email" value={email} onChange={setEmail} placeholder="you@example.com" required />
            </div>
            <div style={{ gridColumn: "1 / -1" }}>
              <PhoneInput countryCode={phoneCountry} onCountry={setPhoneCountry} number={phoneNumber} onNumber={setPhoneNumber} />
            </div>
          </motion.div>
        )}

        {step === 2 && (
          <motion.div initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }}>
            <div style={{ fontSize: 13, color: T.text, fontFamily: F.sans, fontWeight: 600, marginBottom: 10 }}>Before you continue</div>
            <div style={{ maxHeight: 220, overflowY: "auto", border: `1px solid ${T.border}`, borderRadius: 12, padding: 16, background: T.input, fontSize: 13, color: T.t2, lineHeight: 1.6, fontFamily: F.sans }}>
              <p style={{ marginTop: 0 }}>
                PlaceUp aggregates public job postings and provides resume analysis and visa sponsorship signals. We are a software tool, not an employer, staffing agency, or immigration adviser, and we do not guarantee interviews, offers, sponsorship, or employment. All match, ATS, and sponsorship indicators are informational estimates.
              </p>
              <p>
                By continuing you agree to our{" "}
                <Link to="/terms" target="_blank" style={{ color: T.red }}>Terms of Service</Link>,{" "}
                <Link to="/privacy" target="_blank" style={{ color: T.red }}>Privacy Policy</Link>,{" "}
                <Link to="/cookies" target="_blank" style={{ color: T.red }}>Cookies notice</Link>, and{" "}
          <Link to="/disclaimer" target="_blank" style={{ color: T.red }}>Disclaimer</Link>. Your selected plan is used for access limits and support routing during launch preview.
              </p>
              <p style={{ marginBottom: 0 }}>You must be 18+ and provide accurate information. We record your acceptance (date, version, and IP) for compliance.</p>
            </div>

            <label style={{ display: "flex", alignItems: "flex-start", gap: 10, marginTop: 16, cursor: "pointer" }}>
              <input type="checkbox" checked={agreed} onChange={(e) => { setAgreed(e.target.checked); if (e.target.checked) setDisagreed(false); }}
                style={{ width: 18, height: 18, marginTop: 1, accentColor: T.red, cursor: "pointer" }} />
              <span style={{ fontSize: 13, color: T.text, fontFamily: F.sans }}>
                I have read and <strong>agree</strong> to the Terms of Service, Privacy Policy, Disclaimer, and Refund Policy.
              </span>
            </label>
            <button type="button" onClick={() => { setDisagreed(true); setAgreed(false); }}
              style={{ marginTop: 10, background: "none", border: "none", color: T.t3, fontSize: 12, fontFamily: F.sans, cursor: "pointer", textDecoration: "underline" }}>
              I do not agree
            </button>
            {disagreed && (
              <div style={{ marginTop: 12, padding: "10px 12px", borderRadius: 8, background: "var(--pu-239-68-68-008)", border: "1px solid var(--pu-239-68-68-025)", color: "var(--pu-dc2626)", fontSize: 12, fontFamily: F.sans }}>
                You can't create an account without accepting the Terms and Privacy Policy. You're welcome to review them and come back.
              </div>
            )}
          </motion.div>
        )}

        {step === 3 && (
          <motion.div initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 14 }}>
            <div style={{ gridColumn: "1 / -1" }}>
              <Field label="LinkedIn Profile URL" value={linkedinUrl} onChange={setLinkedinUrl} placeholder="https://linkedin.com/in/..." />
            </div>
            <Field label="Current Company" value={currentCompany} onChange={setCurrentCompany} placeholder="Acme Corp" />
            <Dropdown label="Years of Experience" value={experienceLevel} onChange={setExperienceLevel} options={api.YEARS_OPTIONS} />
            <CountryDropdown label="Current Country" value={country} onChange={setCountry} required />
            <CountryDropdown label="Target Country" value={targetCountry} onChange={setTargetCountry} required />
            <Dropdown label="Visa / Work Authorization" value={visaStatus} onChange={(v) => { setVisaStatus(v); if (v !== "Other") setVisaOther(""); }} options={visaOptions} required placeholder="Select status" />
            <Dropdown label="Authorized to work in target country?" value={authorizedToWork} onChange={setAuthorizedToWork} options={YES_NO_OPTIONS} required placeholder="Select answer" />
            <Dropdown label="Need visa sponsorship?" value={requiresSponsorship} onChange={setRequiresSponsorship} options={YES_NO_OPTIONS} required placeholder="Select answer" />
            <Dropdown label="Open to relocation?" value={openToRelocation} onChange={setOpenToRelocation} options={YES_NO_OPTIONS} placeholder="Select answer" />
            <Dropdown label="Sex / Gender" value={gender} onChange={setGender} options={GENDER_OPTIONS} placeholder="Optional" />
            <Dropdown label="Race / Ethnicity" value={raceEthnicity} onChange={setRaceEthnicity} options={RACE_OPTIONS} placeholder="Optional" />
            <Dropdown label="Disability" value={disabilityStatus} onChange={setDisabilityStatus} options={DISABILITY_OPTIONS} placeholder="Optional" />
            <Dropdown label="Veteran Status" value={veteranStatus} onChange={setVeteranStatus} options={VETERAN_OPTIONS} placeholder="Optional" />
            {visaStatus === "Other" && (
              <div style={{ gridColumn: "1 / -1" }}>
                <Field label="Describe your status" value={visaOther} onChange={setVisaOther} placeholder="e.g. Dependent visa with work rights" required />
              </div>
            )}
            <div style={{ gridColumn: "1 / -1", fontSize: 11.5, color: T.t3, fontFamily: F.sans, lineHeight: 1.55 }}>
              Optional EEO-style answers are stored privately so application packets can be prefilled consistently across ATS forms. Choose "Prefer not to answer" where available.
            </div>
          </motion.div>
        )}

        {step === 4 && (
          <motion.div initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }}>
            <RolePicker roles={allRoles} selected={targetRoles} search={roleSearch} onSearch={setRoleSearch} onToggle={toggleTargetRole} />
          </motion.div>
        )}

        {step === 5 && (
          <motion.div initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <CreditCard size={16} color={T.red} />
              <div>
                <div style={{ fontSize: 13, fontWeight: 800, color: T.text, fontFamily: F.sans }}>Choose your access plan</div>
                <div style={{ fontSize: 11.5, color: T.t3, fontFamily: F.sans }}>{paymentMessage}</div>
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "repeat(3, minmax(0, 1fr))", gap: 10 }}>
              {(plans.length ? plans : [
                { id: "basic", name: "Basic", price: 9.99, interval: "m", features: ["Job matching", "Resume ATS score", "Saved jobs"] },
                { id: "pro", name: "Pro", price: 24.99, interval: "m", features: ["Everything in Basic", "Recruiter contacts", "Application tracking", "Priority job matches"] },
                { id: "elite", name: "Elite", price: 149.99, interval: "m", features: ["Everything in Pro", "Premium enrichment", "Visa sponsor insights", "Concierge support", "Dedicated employee applies for you to 25-30 filtered positions daily"] },
              ] as api.PaymentPlan[]).map((plan) => {
                const active = selectedPlan === plan.id;
                const price = Number(plan.price || 0);
                return (
                  <button
                    key={plan.id}
                    type="button"
                    onClick={() => setSelectedPlan(plan.id)}
                    style={{
                      minHeight: 190,
                      padding: 14,
                      borderRadius: 14,
                      border: `1px solid ${active ? "var(--pu-37-99-235-048)" : T.border}`,
                      background: active ? "var(--pu-37-99-235-008)" : T.input,
                      boxShadow: active ? "0 10px 26px var(--pu-37-99-235-016)" : "none",
                      textAlign: "left",
                      cursor: "pointer",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center", marginBottom: 8 }}>
                      <span style={{ fontSize: 14, fontWeight: 850, color: T.text, fontFamily: F.sans }}>{plan.name}</span>
                      {active && <Check size={15} color="var(--pu-16a34a)" />}
                    </div>
                    <div style={{ fontSize: 24, fontWeight: 900, color: T.text, fontFamily: F.sans, lineHeight: 1 }}>
                      {price <= 0 ? "$0" : `$${price.toFixed(2)}`}
                      <span style={{ fontSize: 11, color: T.t3, fontWeight: 700 }}> / {plan.interval}</span>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 12 }}>
                      {(plan.features || []).map((feature) => (
                        <span key={feature} style={{ display: "flex", gap: 6, fontSize: 11.5, color: T.t2, fontFamily: F.sans, lineHeight: 1.35 }}>
                          <ShieldCheck size={12} color="var(--pu-16a34a)" style={{ flexShrink: 0, marginTop: 1 }} />
                          {feature}
                        </span>
                      ))}
                    </div>
                  </button>
                );
              })}
            </div>
          </motion.div>
        )}

        {step === 6 && (
          <motion.div initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }}>
            {!otpSent ? (
              <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 14 }}>
                <div style={{ gridColumn: "1 / -1", fontSize: 12, color: T.t3, fontFamily: F.sans }}>
                  Set a password, then we'll email a 6-digit code to <strong style={{ color: T.text }}>{email}</strong> to verify it's you.
                </div>
                <Field label="Password" type={showPass ? "text" : "password"} value={password} onChange={setPassword} required
                  rightEl={<button onClick={() => setShowPass(!showPass)} style={{ background: "none", border: "none", cursor: "pointer", color: T.t3, padding: 0 }}>{showPass ? <EyeOff size={14} /> : <Eye size={14} />}</button>} />
                <Field label="Confirm Password" type="password" value={confirm} onChange={setConfirm} required />
                <div style={{ gridColumn: "1 / -1" }}><PasswordRules value={password} /></div>
              </div>
            ) : (
              <div>
                <div style={{ fontSize: 13, color: T.text, fontFamily: F.sans, fontWeight: 600, marginBottom: 6 }}>Verify your email</div>
                <div style={{ fontSize: 12, color: T.t3, fontFamily: F.sans, marginBottom: 14 }}>
                  Enter the 6-digit code we emailed to {email}.
                </div>
                <input value={otpCode} onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="••••••" inputMode="numeric"
                  style={{ width: "100%", height: 52, padding: "0 16px", borderRadius: 12, border: `1px solid ${T.border}`,
                    background: T.input, color: T.text, fontSize: 22, letterSpacing: 8, textAlign: "center",
                    fontFamily: F.mono, outline: "none", boxSizing: "border-box" }} />
                <button type="button" onClick={resendCode}
                  style={{ marginTop: 12, background: "none", border: "none", color: T.red, fontSize: 12, fontFamily: F.sans, cursor: "pointer" }}>
                  Resend code
                </button>
              </div>
            )}
          </motion.div>
        )}

        {step === 7 && (
          <motion.div initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }}>
            <div style={{ fontSize: 12, fontWeight: 500, color: T.t2, fontFamily: F.sans, marginBottom: 8 }}>
              Upload your resume (required, 1 file)
            </div>
            <label style={{ display: "block", padding: 28, borderRadius: 12, border: `2px dashed ${resumeFile ? T.red : "var(--pu-37-99-235-035)"}`, background: T.input, textAlign: "center", cursor: "pointer" }}>
              <Upload size={24} color={T.red} style={{ margin: "0 auto 10px" }} />
              {resumeFile ? (
                <div>
                  <div style={{ fontSize: 13, color: T.text, fontFamily: F.sans, fontWeight: 600, marginBottom: 4 }}>
                    <Check size={12} style={{ verticalAlign: "middle", marginRight: 6 }} color="var(--pu-16a34a)" />
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
              <input type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" style={{ display: "none" }}
                onChange={(e) => {
                  const file = e.target.files?.[0] ?? null;
                  const fileProblem = validateResumeFile(file);
                  setResumeFile(fileProblem ? null : file);
                  setError(fileProblem);
                }} />
            </label>
            <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans, marginTop: 12, lineHeight: 1.55 }}>
              Your resume is security-checked, parsed into private JSON, and saved as your active resume. You can replace it later from the Resumes tab.
            </div>
          </motion.div>
        )}

        {error && (
          <div style={{ marginTop: 16, padding: "10px 12px", borderRadius: 8, background: "var(--pu-239-68-68-008)", border: "1px solid var(--pu-239-68-68-025)", color: "var(--pu-dc2626)", fontSize: 12, fontFamily: F.sans }}>
            {error}
          </div>
        )}

        <div style={{ display: "flex", gap: 10, marginTop: 24 }}>
          {step > 1 && step !== 7 && !(step === 6 && otpSent) && (
            <button type="button" onClick={back} disabled={loading} style={GHOST_BTN}>Back</button>
          )}

          {step <= 4 && (
            <button type="button" onClick={next} disabled={loading} style={PRIMARY_BTN}>Continue</button>
          )}

          {step === 5 && (
            <button type="button" onClick={handlePaymentContinue} disabled={loading} style={PRIMARY_BTN}>
              {loading ? "Checking plan..." : "Continue to verification"}
            </button>
          )}

          {step === 6 && !otpSent && (
            <button type="button" onClick={createAccountAndSendCode} disabled={loading} style={PRIMARY_BTN}>
              {loading ? "Creating account…" : "Create account & send code"}
            </button>
          )}
          {step === 6 && otpSent && (
            <button type="button" onClick={verifyCode} disabled={loading} style={PRIMARY_BTN}>
              {loading ? "Verifying…" : "Verify & continue"}
            </button>
          )}

          {step === 7 && (
            <button type="button" onClick={finishWithResume} disabled={loading} style={PRIMARY_BTN}>
              {loading ? "Finishing…" : "Finish and go to dashboard"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
