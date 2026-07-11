import { useEffect, useState, type CSSProperties } from "react";
import { motion } from "motion/react";
import { MapPin, Globe, Linkedin, Github, Briefcase, Award, ExternalLink, FileText, Target, Building2, ShieldCheck } from "lucide-react";
import * as api from "../../lib/api";
import { LoadingLogo } from "../LoadingLogo";
import { useIsMobile } from "../ui/use-mobile";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  text: "var(--pu-f1f5f9-t)", t2: "var(--pu-226-232-240-072)", t3: "var(--pu-148-163-184-075)",
  border: "var(--pu-148-163-184-008)", glass: "var(--pu-15-30-55-055)",
  grad: "linear-gradient(135deg, var(--pu-2563eb), var(--pu-0ea5e9))", red: "var(--pu-3b82f6-t)", burnt: "var(--pu-60a5fa-t)",
};

const card: CSSProperties = {
  background: T.glass, backdropFilter: "blur(20px)",
  border: `1px solid ${T.border}`, borderRadius: 20, padding: 24,
};

/* ── Document-style resume preview ─────────────────────────────────────
   Renders the parsed resume as a real paper document: centered name +
   contact header, ruled section headings, hanging-indent bullets, bolded
   role/date lines — the same alignment the user's actual resume has. */

const PAPER = {
  bg: "#FDFDFB", ink: "#0F172A", body: "#334155", muted: "#64748B",
  rule: "#CBD5E1", accent: "#1D4ED8",
  serif: "Georgia, 'Times New Roman', serif",
};

function PaperLine({ text }: { text: string }) {
  const isBullet = /^[•●▪‣◦∙·]\s*/.test(text);
  const clean = text.replace(/^[•●▪‣◦∙·]\s*/, "");
  // Role/company/date lines ("Security Analyst — Acme · Jan 2024 – Present")
  const isRoleLine = !isBullet && /\b(19|20)\d{2}\b|\bpresent\b|\bcurrent\b/i.test(text) && text.length < 120;
  if (isBullet) {
    return (
      <div style={{ display: "flex", gap: 8, margin: "3px 0", paddingLeft: 2 }}>
        <span style={{ color: PAPER.accent, lineHeight: 1.62, fontSize: 12.5, flexShrink: 0 }}>•</span>
        <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.62, color: PAPER.body, fontFamily: F.sans, textAlign: "justify" }}>{clean}</p>
      </div>
    );
  }
  return (
    <p style={{
      margin: isRoleLine ? "10px 0 2px" : "4px 0",
      fontSize: isRoleLine ? 12.8 : 12.5,
      lineHeight: 1.65,
      color: isRoleLine ? PAPER.ink : PAPER.body,
      fontWeight: isRoleLine ? 700 : 400,
      fontFamily: F.sans,
      textAlign: isRoleLine ? "left" : "justify",
    }}>{clean}</p>
  );
}

function PaperSection({ title, lines }: { title: string; lines?: string[] }) {
  if (!lines || lines.length === 0) return null;
  return (
    <section style={{ marginTop: 18, minWidth: 0 }}>
      <div style={{
        fontSize: 11, fontWeight: 800, letterSpacing: "0.18em", textTransform: "uppercase",
        color: PAPER.ink, borderBottom: `1.5px solid ${PAPER.rule}`, paddingBottom: 5,
        marginBottom: 8, fontFamily: F.sans,
      }}>{title}</div>
      {lines.map((ln, i) => <PaperLine key={i} text={ln} />)}
    </section>
  );
}

/* ── Keyword categorization for the extractor panel ──────────────────── */

const KW_CATEGORIES: Array<[string, string[]]> = [
  ["Security", [
    "siem", "splunk", "soc", "incident response", "threat", "vulnerability", "penetration testing",
    "owasp", "nist", "mitre", "edr", "ioc", "burp", "security", "cyber", "iam", "mfa", "rbac",
    "active directory", "zero trust", "defender", "sentinelone", "forensics", "phishing", "grc",
    "compliance", "sc-900", "cissp", "cysa", "pentest", "triage", "nmap", "zap", "sqlmap",
  ]],
  ["Cloud & Infrastructure", [
    "aws", "azure", "gcp", "cloud", "kubernetes", "docker", "terraform", "linux", "windows",
    "macos", "network", "vpn", "dns", "servicenow", "microsoft 365", "entra", "vmware",
    "infrastructure", "server", "desktop support", "intune",
  ]],
  ["Development", [
    "python", "javascript", "typescript", "java", "sql", "bash", "powershell", "react",
    "next.js", "node", "fastapi", "api", "html", "css", "c++", "golang", ".net", "flask",
  ]],
  ["Data & Tooling", [
    "postgresql", "mysql", "mongodb", "redis", "celery", "ci/cd", "git", "jira", "llm",
    "etl", "pandas", "automation", "excel", "tableau", "power bi", "kafka", "airflow",
  ]],
];

function keywordCategory(kw: string): string {
  const k = kw.toLowerCase();
  for (const [cat, terms] of KW_CATEGORIES) {
    if (terms.some((t) => k === t || k.includes(t) || t.includes(k))) return cat;
  }
  return "Other";
}

function normalizeHref(value?: string) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  if (/^mailto:/i.test(raw) || /^https?:\/\//i.test(raw)) return raw;
  if (/^(www\.|linkedin\.com\/|github\.com\/)/i.test(raw)) return `https://${raw}`;
  return raw;
}

function linkLabel(value: string) {
  try {
    const url = new URL(normalizeHref(value));
    return url.hostname.replace(/^www\./, "") + url.pathname.replace(/\/$/, "");
  } catch {
    return value.replace(/^https?:\/\//, "");
  }
}

function answer(value?: boolean) {
  if (value === true) return "Yes";
  if (value === false) return "No";
  return "—";
}

export function UserProfilePage() {
  const isMobile = useIsMobile();
  const [profile, setProfile] = useState<api.UserProfile | null>(null);
  const [resumes, setResumes] = useState<api.ResumeMetadata[]>([]);
  const [parsed, setParsed] = useState<api.ParsedResume | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      api.getProfile(),
      api.getResumeList().catch(() => [] as api.ResumeMetadata[]),
      api.getParsedActiveResume().catch(() => ({ has_resume: false, skills: [], keywords: [] } as api.ParsedResume)),
    ])
      .then(([p, rs, pr]) => {
        if (active) {
          setProfile(p);
          setResumes(rs);
          setParsed(pr);
        }
      })
      .catch(() => {});
    return () => { active = false; };
  }, []);

  const initials = profile
    ? `${profile.first_name?.[0] ?? ""}${profile.last_name?.[0] ?? ""}`.toUpperCase()
    : "PU";
  const fullName = profile ? `${profile.first_name} ${profile.last_name}` : "Loading...";
  const role = profile?.current_role || "Software Engineer";
  const plan = profile?.plan || "Pro";
  const location = profile?.location || "—";
  const visa = profile?.visa_status || "—";
  const exp = profile?.experience_years || "—";

  if (!profile) return <LoadingLogo label="Loading profile" />;

  const activeResume = resumes.find((r) => r.active);
  const score = parsed?.score ?? activeResume?.score ?? 0;
  const resumeSkills = Array.from(new Set(
    [...(parsed?.skills || []), ...(parsed?.keywords || [])].map((t) => String(t).trim()).filter(Boolean)
  )).slice(0, 40);
  const targetRoles = parsed?.target_roles || [];
  const pastCompanies = parsed?.past_companies || [];
  const rj = parsed?.resume_json;
  const experienceDetails = (parsed?.experience_details || rj?.experience_details || []).filter((item) => item.company || item.title);
  const resumeLinks = (rj?.contact?.links || []).map((link) => String(link).trim()).filter(Boolean);
  const applicationRows = [
    ["Current country", profile.country || "—"],
    ["Authorized to work", answer(profile.authorized_to_work)],
    ["Needs sponsorship", answer(profile.requires_sponsorship)],
    ["Open to relocation", answer(profile.open_to_relocation)],
    ["Gender", profile.gender || "—"],
    ["Race / ethnicity", profile.race_ethnicity || "—"],
    ["Disability", profile.disability_status || "—"],
    ["Veteran status", profile.veteran_status || "—"],
  ];

  const linkMap = new Map<string, { icon: typeof Linkedin; href?: string; label: string }>();
  const addLink = (icon: typeof Linkedin, href: string | undefined, label: string) => {
    const clean = normalizeHref(href);
    if (!clean) return;
    linkMap.set(clean.toLowerCase(), { icon, href: clean, label });
  };
  addLink(Linkedin, profile?.linkedin_url || undefined, "LinkedIn");
  addLink(Github, profile?.github_url || undefined, "GitHub");
  addLink(Globe, profile?.portfolio_url || undefined, "Portfolio");
  resumeLinks.forEach((href) => {
    const clean = normalizeHref(href);
    const icon = /github/i.test(clean) ? Github : /linkedin/i.test(clean) ? Linkedin : Globe;
    addLink(icon, clean, linkLabel(clean));
  });
  const links = Array.from(linkMap.values());

  return (
    <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "minmax(280px, 1fr) 2fr", gap: 20 }}>
      {/* ── Left column ── */}
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{ ...card, padding: 28, textAlign: "center" }}>
          <div style={{ width: 80, height: 80, borderRadius: "50%", background: T.grad, margin: "0 auto 16px", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 28, fontWeight: 800, color: "var(--pu-ffffff-t)", fontFamily: F.sans, boxShadow: "0 0 24px var(--pu-59-130-246-04)" }}>
            {initials}
          </div>
          <div style={{ fontFamily: F.sans, fontSize: 18, fontWeight: 700, color: T.text, marginBottom: 4 }}>{fullName}</div>
          <div style={{ fontSize: 13, color: T.t2, fontFamily: F.sans, marginBottom: 8 }}>{role}</div>
          <span style={{ fontSize: 11, fontWeight: 700, padding: "4px 12px", borderRadius: 9999, background: T.grad, color: "var(--pu-ffffff-t)", fontFamily: F.sans }}>{plan} Plan</span>

          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 20, textAlign: "left" }}>
            {[
              { icon: MapPin, text: location },
              { icon: Globe, text: visa },
              { icon: Briefcase, text: exp },
            ].map((item, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <item.icon size={13} color={T.t3} />
                <span style={{ fontSize: 12, color: T.t2, fontFamily: F.sans }}>{item.text}</span>
              </div>
            ))}
          </div>

          <div style={{ display: "flex", gap: 10, justifyContent: "center", marginTop: 16 }}>
            {links.map(({ icon: Icon, href, label }) => (
              <a key={label} href={href || "#"} target={href ? "_blank" : undefined} rel="noreferrer"
                aria-label={label}
                style={{ width: 36, height: 36, borderRadius: 10, border: `1px solid ${T.border}`, background: "var(--pu-148-163-184-004)", display: "flex", alignItems: "center", justifyContent: "center", cursor: href ? "pointer" : "not-allowed", opacity: href ? 1 : 0.4, color: T.t3, textDecoration: "none" }}>
                <Icon size={15} />
              </a>
            ))}
          </div>
        </div>

        {/* ATS score of active resume */}
        <div style={{ ...card, padding: 20, textAlign: "center" }}>
          <div style={{ fontSize: 12, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: T.t3, fontFamily: F.sans, marginBottom: 12 }}>Active Resume ATS Score</div>
          <div style={{ fontFamily: F.mono, fontSize: 48, fontWeight: 500, color: T.red, lineHeight: 1 }}>{score}</div>
          <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans, marginTop: 4 }}>/100 · {score >= 80 ? "Well Optimized" : score >= 60 ? "Improving" : "Needs work"}</div>
          {activeResume && (
            <div style={{ fontSize: 11, color: T.t2, fontFamily: F.sans, marginTop: 8 }}>{activeResume.name}</div>
          )}
          <div style={{ height: 4, borderRadius: 2, background: "var(--pu-148-163-184-006)", marginTop: 12, overflow: "hidden" }}>
            <motion.div initial={{ width: 0 }} animate={{ width: `${score}%` }} transition={{ duration: 1.2, ease: "easeOut" }}
              style={{ height: "100%", borderRadius: 2, background: T.grad }} />
          </div>
        </div>

        {/* Career snapshot: target roles + past experience */}
        <div style={card}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
            <Target size={15} color={T.red} />
            <span style={{ fontFamily: F.sans, fontSize: 14, fontWeight: 600, color: T.text }}>Target Roles</span>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 18 }}>
            {targetRoles.length === 0 && <span style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>Set target roles in Settings to tune your job matches.</span>}
            {targetRoles.map((r) => (
              <span key={r} style={{ fontSize: 11, padding: "4px 10px", borderRadius: 8, background: "var(--pu-59-130-246-01)", color: T.red, border: "1px solid var(--pu-59-130-246-02)", fontFamily: F.sans }}>{r}</span>
            ))}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
            <Building2 size={15} color={T.red} />
            <span style={{ fontFamily: F.sans, fontSize: 14, fontWeight: 600, color: T.text }}>Past Experience</span>
          </div>
          {experienceDetails.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {experienceDetails.slice(0, 5).map((item, idx) => (
                <div key={`${item.company}-${item.title}-${idx}`} style={{ border: `1px solid ${T.border}`, borderRadius: 12, padding: 11, background: "var(--pu-148-163-184-004)" }}>
                  <div style={{ fontSize: 12.5, fontWeight: 800, color: T.text, fontFamily: F.sans, lineHeight: 1.35 }}>{item.title || "Role"}</div>
                  <div style={{ fontSize: 11.5, color: T.t2, fontFamily: F.sans, lineHeight: 1.45, marginTop: 2 }}>{item.company || "Company"}</div>
                  <div style={{ fontSize: 10.5, color: T.t3, fontFamily: F.sans, lineHeight: 1.45, marginTop: 2 }}>
                    {[item.duration, item.location].filter(Boolean).join(" · ")}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {pastCompanies.length === 0 && <span style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>Companies are detected from your active resume's experience section.</span>}
              {pastCompanies.map((c) => (
                <span key={c} style={{ fontSize: 11, padding: "4px 10px", borderRadius: 8, background: "var(--pu-148-163-184-005)", color: T.t2, border: `1px solid ${T.border}`, fontFamily: F.sans }}>{c}</span>
              ))}
            </div>
          )}
        </div>

        {/* Application profile */}
        <div style={card}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
            <ShieldCheck size={15} color={T.red} />
            <span style={{ fontFamily: F.sans, fontSize: 14, fontWeight: 600, color: T.text }}>Application Profile</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {applicationRows.map(([label, value]) => (
              <div key={label} style={{ display: "flex", justifyContent: "space-between", gap: 12, borderBottom: `1px solid ${T.border}`, paddingBottom: 7 }}>
                <span style={{ fontSize: 11.5, color: T.t3, fontFamily: F.sans }}>{label}</span>
                <span style={{ fontSize: 11.5, color: T.t2, fontFamily: F.sans, textAlign: "right" }}>{value}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Quick links */}
        <div style={card}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
            <Award size={15} color={T.red} />
            <span style={{ fontFamily: F.sans, fontSize: 14, fontWeight: 600, color: T.text }}>Quick Links</span>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {links.filter((l) => l.href).map(({ icon: Icon, href, label }) => (
              <a key={label} href={href} target="_blank" rel="noreferrer"
                style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, padding: "6px 12px", borderRadius: 8, background: "var(--pu-148-163-184-005)", color: T.t2, border: `1px solid ${T.border}`, fontFamily: F.sans, textDecoration: "none" }}>
                <Icon size={12} /> {label} <ExternalLink size={10} />
              </a>
            ))}
            {links.filter((l) => l.href).length === 0 && (
              <span style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>Add LinkedIn / GitHub / Portfolio links from Settings.</span>
            )}
          </div>
        </div>
      </div>

      {/* ── Right column ── */}
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {/* Active resume document view */}
        <div style={card}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <FileText size={15} color={T.red} />
              <span style={{ fontFamily: F.sans, fontSize: 14, fontWeight: 600, color: T.text }}>Active Resume</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              {activeResume && (
                <span style={{ fontSize: 10, fontWeight: 700, padding: "3px 10px", borderRadius: 9999, background: "var(--pu-59-130-246-012)", color: T.red, border: "1px solid var(--pu-59-130-246-025)", fontFamily: F.sans }}>
                  {activeResume.name}
                </span>
              )}
              <span style={{ fontSize: 10, fontWeight: 800, padding: "3px 10px", borderRadius: 9999, background: score >= 80 ? "var(--pu-34-197-94-012)" : "var(--pu-59-130-246-012)", color: score >= 80 ? "var(--pu-86efac-t)" : T.red, border: `1px solid ${score >= 80 ? "var(--pu-34-197-94-026)" : "var(--pu-59-130-246-025)"}`, fontFamily: F.sans }}>
                ATS {score}/100
              </span>
            </div>
          </div>
          {!parsed?.has_resume || !rj ? (
            <div style={{ fontSize: 13, color: T.t3, fontFamily: F.sans }}>
              {parsed?.error || "No active resume found. Upload one from the Resumes tab to see it here."}
            </div>
          ) : (
            <div style={{
              background: PAPER.bg,
              border: "1px solid rgba(148,163,184,0.28)",
              borderRadius: 12,
              padding: isMobile ? "22px 18px" : "34px 40px",
              boxShadow: "0 18px 48px rgba(0,0,0,0.5), 0 2px 8px rgba(0,0,0,0.3)",
              maxWidth: 820,
              margin: "0 auto",
            }}>
              {/* Document header — centered like the real resume */}
              <div style={{ textAlign: "center", paddingBottom: 14, marginBottom: 6, borderBottom: `2px solid ${PAPER.ink}` }}>
                <div style={{ fontFamily: PAPER.serif, fontSize: isMobile ? 19 : 23, fontWeight: 700, color: PAPER.ink, letterSpacing: "0.02em" }}>
                  {fullName}
                </div>
                <div style={{ fontSize: 11.5, color: PAPER.muted, fontFamily: F.sans, marginTop: 5, display: "flex", flexWrap: "wrap", gap: "3px 0", justifyContent: "center" }}>
                  {[rj.contact?.email, rj.contact?.phone, ...(rj.contact?.links || []).slice(0, 2)]
                    .filter(Boolean)
                    .map((item, i, arr) => (
                      <span key={String(item)}>
                        {item}{i < arr.length - 1 && <span style={{ margin: "0 7px", color: PAPER.rule }}>|</span>}
                      </span>
                    ))}
                </div>
              </div>
              {rj.summary && (
                <section style={{ marginTop: 14 }}>
                  <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.18em", textTransform: "uppercase", color: PAPER.ink, borderBottom: `1.5px solid ${PAPER.rule}`, paddingBottom: 5, marginBottom: 8, fontFamily: F.sans }}>
                    Summary
                  </div>
                  <p style={{ fontSize: 12.5, color: PAPER.body, fontFamily: F.sans, lineHeight: 1.65, margin: 0, textAlign: "justify" }}>{rj.summary}</p>
                </section>
              )}
              <PaperSection title="Skills" lines={rj.sections?.skills} />
              <PaperSection title="Experience" lines={rj.experience} />
              <PaperSection title="Projects" lines={rj.projects} />
              <PaperSection title="Education" lines={rj.education} />
              <PaperSection title="Certifications" lines={rj.certifications} />
            </div>
          )}
        </div>

        {/* Keywords extracted from active resume — grouped by domain */}
        <div style={card}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4, gap: 8, flexWrap: "wrap" }}>
            <div style={{ fontFamily: F.sans, fontSize: 14, fontWeight: 600, color: T.text }}>Extracted Keywords</div>
            {resumeSkills.length > 0 && (
              <span style={{ fontSize: 10, fontWeight: 800, padding: "3px 10px", borderRadius: 9999, background: "var(--pu-59-130-246-012)", color: T.red, border: "1px solid var(--pu-59-130-246-025)", fontFamily: F.sans }}>
                {resumeSkills.length} terms
              </span>
            )}
          </div>
          <div style={{ fontSize: 12, color: T.t3, fontFamily: F.sans, marginBottom: 14 }}>Pulled from your active resume — job match scoring uses these same terms.</div>
          {resumeSkills.length === 0 ? (
            <span style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>Upload a resume with a skills section to populate keywords.</span>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {[...KW_CATEGORIES.map(([cat]) => cat), "Other"]
                .map((cat) => [cat, resumeSkills.filter((s) => keywordCategory(s) === cat)] as [string, string[]])
                .filter(([, terms]) => terms.length > 0)
                .map(([cat, terms]) => (
                  <div key={cat}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                      <span style={{ fontSize: 10.5, fontWeight: 800, letterSpacing: "0.1em", textTransform: "uppercase", color: T.t3, fontFamily: F.sans }}>{cat}</span>
                      <span style={{ flex: 1, height: 1, background: T.border }} />
                      <span style={{ fontSize: 10, color: T.t3, fontFamily: F.mono }}>{terms.length}</span>
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
                      {terms.map((s) => (
                        <span key={s} style={{ fontSize: 11.5, padding: "4px 11px", borderRadius: 8, background: "var(--pu-59-130-246-009)", color: T.red, border: "1px solid var(--pu-59-130-246-018)", fontFamily: F.sans }}>{s}</span>
                      ))}
                    </div>
                  </div>
                ))}
            </div>
          )}
        </div>

        {/* All resumes */}
        <div style={card}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
            <Briefcase size={15} color={T.red} />
            <span style={{ fontFamily: F.sans, fontSize: 14, fontWeight: 600, color: T.text }}>Resumes</span>
          </div>
          {resumes.length === 0 ? (
            <div style={{ fontSize: 13, color: T.t3, fontFamily: F.sans }}>No resumes uploaded yet. Visit the Resumes tab to upload your first one.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {resumes.map((r) => (
                <div key={r.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 12px", borderRadius: 10, background: r.active ? "var(--pu-59-130-246-006)" : "var(--pu-148-163-184-003)", border: `1px solid ${r.active ? "var(--pu-59-130-246-03)" : T.border}` }}>
                  <div>
                    <div style={{ fontSize: 13, color: T.text, fontFamily: F.sans, fontWeight: 600 }}>{r.name}</div>
                    <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans }}>Score: {r.score}/100 · {Math.round((r.size_bytes || 0) / 1024)} KB {r.active ? "· Active" : ""}</div>
                  </div>
                  {r.active ? (
                    <span style={{ fontSize: 10, fontWeight: 700, padding: "3px 8px", borderRadius: 9999, background: "var(--pu-59-130-246-012)", color: T.red, border: "1px solid var(--pu-59-130-246-025)", fontFamily: F.sans }}>Active</span>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
