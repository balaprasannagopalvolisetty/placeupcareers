import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { MapPin, Globe, Linkedin, Github, Briefcase, GraduationCap, Award, ExternalLink } from "lucide-react";
import * as api from "../../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  text: "#F2EEB3", t2: "rgba(242,238,179,0.65)", t3: "rgba(242,238,179,0.45)",
  border: "rgba(242,238,179,0.08)", glass: "rgba(64,18,18,0.55)",
  grad: "linear-gradient(135deg, #8C3A27, #A6372D, #401212)", red: "#A6372D", burnt: "#8C3A27",
};

const FALLBACK_SKILLS = ["React", "TypeScript", "Node.js", "AWS", "System Design", "REST APIs", "Python", "Docker", "CI/CD"];

export function UserProfilePage() {
  const [profile, setProfile] = useState<api.UserProfile | null>(null);
  const [resumes, setResumes] = useState<api.ResumeMetadata[]>([]);

  useEffect(() => {
    let active = true;
    Promise.all([api.getProfile(), api.getResumeList().catch(() => [])])
      .then(([p, rs]) => { if (active) { setProfile(p); setResumes(rs); } })
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

  const activeResume = resumes.find((r) => r.active);
  const score = activeResume?.score ?? 0;
  const links: { icon: typeof Linkedin; href?: string; label: string }[] = [
    { icon: Linkedin, href: profile?.linkedin_url || undefined, label: "LinkedIn" },
    { icon: Github, href: profile?.github_url || undefined, label: "GitHub" },
    { icon: Globe, href: profile?.portfolio_url || undefined, label: "Portfolio" },
  ];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 20 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: 28, textAlign: "center" }}>
          <div style={{ width: 80, height: 80, borderRadius: "50%", background: T.grad, margin: "0 auto 16px", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 28, fontWeight: 800, color: "#fff", fontFamily: F.sans, boxShadow: "0 0 24px rgba(166,55,45,0.4)" }}>
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

        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: 20, textAlign: "center" }}>
          <div style={{ fontSize: 12, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: T.t3, fontFamily: F.sans, marginBottom: 12 }}>Current ATS Score</div>
          <div style={{ fontFamily: F.mono, fontSize: 48, fontWeight: 500, color: T.red, lineHeight: 1 }}>{score}</div>
          <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans, marginTop: 4 }}>/100 · {score >= 80 ? "Well Optimized" : score >= 60 ? "Improving" : "Needs work"}</div>
          <div style={{ height: 4, borderRadius: 2, background: "rgba(242,238,179,0.06)", marginTop: 12, overflow: "hidden" }}>
            <motion.div initial={{ width: 0 }} animate={{ width: `${score}%` }} transition={{ duration: 1.2, ease: "easeOut" }}
              style={{ height: "100%", borderRadius: 2, background: T.grad }} />
          </div>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {profile?.summary ? (
          <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: 24 }}>
            <div style={{ fontFamily: F.sans, fontSize: 14, fontWeight: 600, color: T.text, marginBottom: 14 }}>Summary</div>
            <p style={{ fontSize: 13, color: T.t2, fontFamily: F.sans, lineHeight: 1.7, margin: 0 }}>{profile.summary}</p>
          </div>
        ) : null}

        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: 24 }}>
          <div style={{ fontFamily: F.sans, fontSize: 14, fontWeight: 600, color: T.text, marginBottom: 14 }}>Skills</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {FALLBACK_SKILLS.map((s) => (
              <span key={s} style={{ fontSize: 12, padding: "5px 12px", borderRadius: 8, background: "rgba(166,55,45,0.1)", color: T.red, border: "1px solid rgba(166,55,45,0.2)", fontFamily: F.sans }}>{s}</span>
            ))}
          </div>
        </div>

        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: 24 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
            <Briefcase size={15} color={T.red} />
            <span style={{ fontFamily: F.sans, fontSize: 14, fontWeight: 600, color: T.text }}>Resumes</span>
          </div>
          {resumes.length === 0 ? (
            <div style={{ fontSize: 13, color: T.t3, fontFamily: F.sans }}>No resumes uploaded yet. Visit the Resumes tab to upload your first one.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {resumes.map((r) => (
                <div key={r.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 12px", borderRadius: 10, background: r.active ? "rgba(166,55,45,0.06)" : "rgba(242,238,179,0.03)", border: `1px solid ${r.active ? "rgba(166,55,45,0.3)" : T.border}` }}>
                  <div>
                    <div style={{ fontSize: 13, color: T.text, fontFamily: F.sans, fontWeight: 600 }}>{r.name}</div>
                    <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans }}>Score: {r.score}/100 · {Math.round((r.size_bytes || 0) / 1024)} KB {r.active ? "· Active" : ""}</div>
                  </div>
                  {r.active ? (
                    <span style={{ fontSize: 10, fontWeight: 700, padding: "3px 8px", borderRadius: 9999, background: "rgba(166,55,45,0.12)", color: T.red, border: "1px solid rgba(166,55,45,0.25)", fontFamily: F.sans }}>Active</span>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </div>

        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: 24 }}>
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
    </div>
  );
}
