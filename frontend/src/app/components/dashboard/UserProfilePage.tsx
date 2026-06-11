import { useEffect, useState, type CSSProperties } from "react";
import { motion } from "motion/react";
import { MapPin, Globe, Linkedin, Github, Briefcase, Award, ExternalLink, FileText, Target, Building2 } from "lucide-react";
import * as api from "../../lib/api";
import { LoadingLogo } from "../LoadingLogo";
import { useIsMobile } from "../ui/use-mobile";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  text: "#F2EEB3", t2: "rgba(242,238,179,0.65)", t3: "rgba(242,238,179,0.45)",
  border: "rgba(242,238,179,0.08)", glass: "rgba(64,18,18,0.55)",
  grad: "linear-gradient(135deg, #F2A341, #ED7D2B, #C75A12)", red: "#ED7D2B", burnt: "#F2A341",
};

const card: CSSProperties = {
  background: T.glass, backdropFilter: "blur(20px)",
  border: `1px solid ${T.border}`, borderRadius: 20, padding: 24,
};

function ResumeSection({ title, lines }: { title: string; lines?: string[] }) {
  if (!lines || lines.length === 0) return null;
  return (
    <div style={{ marginBottom: 18 }}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: T.red, fontFamily: F.sans, marginBottom: 8, paddingBottom: 5, borderBottom: `1px solid ${T.border}` }}>
        {title}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
        {lines.map((ln, i) => (
          <p key={i} style={{ fontSize: 12.5, color: T.t2, fontFamily: F.sans, lineHeight: 1.6, margin: 0 }}>{ln}</p>
        ))}
      </div>
    </div>
  );
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

  const links: { icon: typeof Linkedin; href?: string; label: string }[] = [
    { icon: Linkedin, href: profile?.linkedin_url || undefined, label: "LinkedIn" },
    { icon: Github, href: profile?.github_url || undefined, label: "GitHub" },
    { icon: Globe, href: profile?.portfolio_url || undefined, label: "Portfolio" },
  ];

  return (
    <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "minmax(280px, 1fr) 2fr", gap: 20 }}>
      {/* ── Left column ── */}
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{ ...card, padding: 28, textAlign: "center" }}>
          <div style={{ width: 80, height: 80, borderRadius: "50%", background: T.grad, margin: "0 auto 16px", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 28, fontWeight: 800, color: "#fff", fontFamily: F.sans, boxShadow: "0 0 24px rgba(237,125,43,0.4)" }}>
            {initials}
          </div>
          <div style={{ fontFamily: F.sans, fontSize: 18, fontWeight: 700, color: T.text, marginBottom: 4 }}>{fullName}</div>
          <div style={{ fontSize: 13, color: T.t2, fontFamily: F.sans, marginBottom: 8 }}>{role}</div>
          <span style={{ fontSize: 11, fontWeight: 700, padding: "4px 12px", borderRadius: 9999, background: T.grad, color: "#fff", fontFamily: F.sans }}>{plan} Plan</span>

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
                style={{ width: 36, height: 36, borderRadius: 10, border: `1px solid ${T.border}`, background: "rgba(242,238,179,0.04)", display: "flex", alignItems: "center", justifyContent: "center", cursor: href ? "pointer" : "not-allowed", opacity: href ? 1 : 0.4, color: T.t3, textDecoration: "none" }}>
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
          <div style={{ height: 4, borderRadius: 2, background: "rgba(242,238,179,0.06)", marginTop: 12, overflow: "hidden" }}>
            <motion.div initial={{ width: 0 }} animate={{ width: `${score}%` }} transition={{ duration: 1.2, ease: "easeOut" }}
              style={{ height: "100%", borderRadius: 2, background: T.grad }} />
          </div>
        </div>

        {/* Career snapshot: target roles + past companies */}
        <div style={card}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
            <Target size={15} color={T.red} />
            <span style={{ fontFamily: F.sans, fontSize: 14, fontWeight: 600, color: T.text }}>Target Roles</span>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 18 }}>
            {targetRoles.length === 0 && <span style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>Set target roles in Settings to tune your job matches.</span>}
            {targetRoles.map((r) => (
              <span key={r} style={{ fontSize: 11, padding: "4px 10px", borderRadius: 8, background: "rgba(237,125,43,0.1)", color: T.red, border: "1px solid rgba(237,125,43,0.2)", fontFamily: F.sans }}>{r}</span>
            ))}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
            <Building2 size={15} color={T.red} />
            <span style={{ fontFamily: F.sans, fontSize: 14, fontWeight: 600, color: T.text }}>Past Companies</span>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {pastCompanies.length === 0 && <span style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>Companies are detected from your active resume's experience section.</span>}
            {pastCompanies.map((c) => (
              <span key={c} style={{ fontSize: 11, padding: "4px 10px", borderRadius: 8, background: "rgba(242,238,179,0.05)", color: T.t2, border: `1px solid ${T.border}`, fontFamily: F.sans }}>{c}</span>
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
                style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, padding: "6px 12px", borderRadius: 8, background: "rgba(242,238,179,0.05)", color: T.t2, border: `1px solid ${T.border}`, fontFamily: F.sans, textDecoration: "none" }}>
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
            {activeResume && (
              <span style={{ fontSize: 10, fontWeight: 700, padding: "3px 10px", borderRadius: 9999, background: "rgba(237,125,43,0.12)", color: T.red, border: "1px solid rgba(237,125,43,0.25)", fontFamily: F.sans }}>
                {activeResume.name}
              </span>
            )}
          </div>
          {!parsed?.has_resume || !rj ? (
            <div style={{ fontSize: 13, color: T.t3, fontFamily: F.sans }}>
              {parsed?.error || "No active resume found. Upload one from the Resumes tab to see it here."}
            </div>
          ) : (
            <div style={{ background: "rgba(1,14,34,0.45)", border: `1px solid ${T.border}`, borderRadius: 14, padding: "20px 22px", maxHeight: 520, overflowY: "auto" }}>
              {/* Resume header */}
              <div style={{ marginBottom: 16, paddingBottom: 12, borderBottom: `1px solid ${T.border}` }}>
                <div style={{ fontFamily: F.sans, fontSize: 17, fontWeight: 700, color: T.text }}>{fullName}</div>
                <div style={{ fontSize: 11.5, color: T.t3, fontFamily: F.sans, marginTop: 3, display: "flex", flexWrap: "wrap", gap: "4px 12px" }}>
                  {rj.contact?.email && <span>{rj.contact.email}</span>}
                  {rj.contact?.phone && <span>{rj.contact.phone}</span>}
                  {(rj.contact?.links || []).slice(0, 3).map((l) => <span key={l}>{l}</span>)}
                </div>
              </div>
              {rj.summary && (
                <div style={{ marginBottom: 18 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: T.red, fontFamily: F.sans, marginBottom: 8, paddingBottom: 5, borderBottom: `1px solid ${T.border}` }}>Summary</div>
                  <p style={{ fontSize: 12.5, color: T.t2, fontFamily: F.sans, lineHeight: 1.65, margin: 0 }}>{rj.summary}</p>
                </div>
              )}
              <ResumeSection title="Experience" lines={rj.experience} />
              <ResumeSection title="Skills" lines={rj.sections?.skills} />
              <ResumeSection title="Projects" lines={rj.projects} />
              <ResumeSection title="Education" lines={rj.education} />
              <ResumeSection title="Certifications" lines={rj.certifications} />
            </div>
          )}
        </div>

        {/* Keywords extracted from active resume */}
        <div style={card}>
          <div style={{ fontFamily: F.sans, fontSize: 14, fontWeight: 600, color: T.text, marginBottom: 4 }}>Extracted Keywords</div>
          <div style={{ fontSize: 12, color: T.t3, fontFamily: F.sans, marginBottom: 14 }}>Pulled from your active resume — job match scoring uses these same terms.</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {resumeSkills.length === 0 && (
              <span style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>Upload a resume with a skills section to populate keywords.</span>
            )}
            {resumeSkills.map((s) => (
              <span key={s} style={{ fontSize: 12, padding: "5px 12px", borderRadius: 8, background: "rgba(237,125,43,0.1)", color: T.red, border: "1px solid rgba(237,125,43,0.2)", fontFamily: F.sans }}>{s}</span>
            ))}
          </div>
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
                <div key={r.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 12px", borderRadius: 10, background: r.active ? "rgba(237,125,43,0.06)" : "rgba(242,238,179,0.03)", border: `1px solid ${r.active ? "rgba(237,125,43,0.3)" : T.border}` }}>
                  <div>
                    <div style={{ fontSize: 13, color: T.text, fontFamily: F.sans, fontWeight: 600 }}>{r.name}</div>
                    <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans }}>Score: {r.score}/100 · {Math.round((r.size_bytes || 0) / 1024)} KB {r.active ? "· Active" : ""}</div>
                  </div>
                  {r.active ? (
                    <span style={{ fontSize: 10, fontWeight: 700, padding: "3px 8px", borderRadius: 9999, background: "rgba(237,125,43,0.12)", color: T.red, border: "1px solid rgba(237,125,43,0.25)", fontFamily: F.sans }}>Active</span>
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
