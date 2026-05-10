import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ArrowLeft, MapPin, DollarSign, Clock, ExternalLink, Bookmark, Share2, Check, X, Lock, Copy, Linkedin } from "lucide-react";
import * as api from "../../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  text: "#F2EEB3", t2: "rgba(242,238,179,0.65)", t3: "rgba(242,238,179,0.45)",
  border: "rgba(242,238,179,0.08)", glass: "rgba(64,18,18,0.55)",
  grad: "linear-gradient(135deg, #8C3A27, #A6372D, #401212)",
  red: "#A6372D", burnt: "#8C3A27", dark: "#401212",
};

function normalizeVisa(visa: unknown): string[] {
  if (Array.isArray(visa)) {
    return visa.filter((item): item is string => typeof item === "string");
  }
  if (visa && typeof visa === "object") {
    const map: Record<string, string> = {
      visa_h1b: "H-1B",
      visa_opt: "F1-OPT",
      visa_stem_opt: "F1-STEM",
      h1b_verified: "H-1B Verified",
      green_card: "Green Card",
    };
    return Object.entries(visa)
      .filter(([key, value]) => key !== "visa_score" && value)
      .map(([key]) => map[key] ?? key.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase()));
  }
  if (typeof visa === "string") {
    return visa.split(",").map((item) => item.trim()).filter(Boolean);
  }
  return [];
}

function formatSalary(salary: unknown): string {
  if (!salary) return "Not specified";
  if (typeof salary === "string") return salary;
  if (typeof salary === "object") {
    const min = (salary as any).min_salary;
    const max = (salary as any).max_salary;
    if (typeof min === "number" && typeof max === "number") {
      return `$${Math.round(min / 1000)}K–$${Math.round(max / 1000)}K`;
    }
    if (typeof min === "number") {
      return `$${Math.round(min / 1000)}K+`;
    }
    if (typeof max === "number") {
      return `Up to $${Math.round(max / 1000)}K`;
    }
    if ((salary as any).display) {
      return String((salary as any).display);
    }
  }
  return "Not specified";
}

const JOBS: Record<number, {
  id: number; title: string; company: string; location: string; salary: string;
  match: number; visa: string[]; posted: string; status: string;
  responsibilities: string[]; requirements: string[]; niceToHave: string[];
  strongKeywords: string[]; missingKeywords: { kw: string; impact: "High" | "Medium" }[];
  benefits: string[]; approvalRate: number; petitions: number;
  hiringManager: { name: string; title: string; email: string; linkedin: string } | null;
}> = {
  1: {
    id: 1, title: "Senior Frontend Engineer", company: "Stripe", location: "San Francisco, CA",
    salary: "$180K–$220K", match: 96, visa: ["H-1B", "F1-OPT"], posted: "2h ago", status: "New",
    responsibilities: ["Build and own core payment UI components used by millions daily", "Lead technical design for new product initiatives", "Mentor junior engineers and drive team processes", "Collaborate with design to implement pixel-perfect interfaces"],
    requirements: ["5+ years React/TypeScript experience", "Deep understanding of browser performance", "Experience with testing frameworks (Jest, Cypress)", "Track record of shipping production features"],
    niceToHave: ["Experience with financial products", "Knowledge of accessibility standards", "Open source contributions", "GraphQL experience"],
    strongKeywords: ["React", "TypeScript", "Node.js", "REST APIs", "Jest", "Performance optimization"],
    missingKeywords: [{ kw: "GraphQL", impact: "High" }, { kw: "Terraform", impact: "Medium" }, { kw: "Kubernetes", impact: "Medium" }],
    benefits: ["Health, Dental, Vision", "Equity package", "401(k) matching", "Remote flexibility", "Learning budget $5K/yr", "Home office stipend"],
    approvalRate: 98, petitions: 1283,
    hiringManager: { name: "Jordan Lee", title: "Engineering Manager, Payments", email: "jordan.lee@stripe.com", linkedin: "linkedin.com/in/jordanlee" },
  },
};

function ATSRingLarge({ score }: { score: number }) {
  const r = 52, circ = 2 * Math.PI * r, offset = circ * (1 - score / 100);
  const color = score >= 80 ? T.red : score >= 60 ? T.burnt : T.dark;
  return (
    <div style={{ position: "relative", width: 120, height: 120 }}>
      <svg viewBox="0 0 120 120" style={{ width: "100%", height: "100%", transform: "rotate(-90deg)" }}>
        <defs>
          <filter id="jd-glow"><feGaussianBlur stdDeviation="3" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
        </defs>
        <circle cx="60" cy="60" r={r} fill="none" stroke="rgba(242,238,179,0.07)" strokeWidth="9" />
        <motion.circle cx="60" cy="60" r={r} fill="none" stroke={color} strokeWidth="9" strokeLinecap="round"
          strokeDasharray={circ} initial={{ strokeDashoffset: circ }} animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1.5, ease: "easeOut" }} filter="url(#jd-glow)" />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <span style={{ fontFamily: F.mono, fontSize: 28, fontWeight: 500, color, lineHeight: 1 }}>{score}</span>
        <span style={{ fontSize: 8, letterSpacing: "0.08em", textTransform: "uppercase", color: T.t3, fontFamily: F.sans, marginTop: 2 }}>Match</span>
      </div>
    </div>
  );
}

export function JobDetailPage({ jobId, onBack }: { jobId: string; onBack: () => void }) {
  const [job, setJob] = useState<api.JobPost | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"responsibilities" | "requirements" | "niceToHave">("responsibilities");
  const [showApplyModal, setShowApplyModal] = useState(false);
  const [applied, setApplied] = useState(false);
  const isPro = true; // simulate pro plan

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    api.getJobDetail(String(jobId))
      .then((response) => {
        if (!active) return;
        setJob(response);
      })
      .catch((err) => {
        if (!active) return;
        setError(err?.message ?? "Unable to load job details.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => { active = false; };
  }, [jobId]);

  const fallbackJob = JOBS[Number(jobId)] ?? JOBS[1];
  const currentJob = {
    ...fallbackJob,
    ...job,
    salary: formatSalary(job?.salary ?? fallbackJob.salary),
    match: job?.match_score ?? job?.match ?? fallbackJob.match,
    visa: normalizeVisa(job?.visa ?? fallbackJob.visa),
    posted: job?.posted_at ?? job?.posted ?? fallbackJob.posted,
    status: job?.status ?? fallbackJob.status,
    responsibilities: job?.responsibilities ?? fallbackJob.responsibilities,
    requirements: job?.requirements ?? fallbackJob.requirements,
    niceToHave: job?.niceToHave ?? fallbackJob.niceToHave,
    strongKeywords: job?.strongKeywords ?? fallbackJob.strongKeywords,
    missingKeywords: Array.isArray(job?.missingKeywords) ? (job?.missingKeywords as any) : fallbackJob.missingKeywords,
    benefits: job?.benefits ?? fallbackJob.benefits,
    approvalRate: job?.approvalRate ?? fallbackJob.approvalRate,
    petitions: job?.petitions ?? fallbackJob.petitions,
    hiringManager: fallbackJob.hiringManager,
  };

  if (loading) {
    return <div style={{ color: "#F2EEB3", fontFamily: F.sans, fontSize: 14 }}>Loading job details...</div>;
  }

  if (error) {
    return <div style={{ color: "#ff7f7f", fontFamily: F.sans, fontSize: 14 }}>{error}</div>;
  }

  const visaBadge: Record<string, { bg: string; color: string; border: string }> = {
    "H-1B":    { bg: "rgba(140,58,39,0.15)", color: T.burnt,  border: "rgba(140,58,39,0.35)" },
    "F1-OPT":  { bg: "rgba(166,55,45,0.12)", color: T.red,    border: "rgba(166,55,45,0.3)" },
    "F1-STEM": { bg: "rgba(64,18,18,0.15)",  color: T.red,    border: "rgba(64,18,18,0.3)" },
  };

  const tabContent = { responsibilities: currentJob.responsibilities, requirements: currentJob.requirements, niceToHave: currentJob.niceToHave };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1.8fr 1fr", gap: 20 }}>
      {/* MAIN */}
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {/* Back */}
        <button onClick={onBack} style={{ display: "flex", alignItems: "center", gap: 6, background: "none", border: "none", cursor: "pointer", color: T.t2, fontSize: 13, fontFamily: F.sans, width: "fit-content" }}>
          <ArrowLeft size={14} /> All Jobs
        </button>

        {/* Header card */}
        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: 24 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
            <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
              <div style={{ width: 60, height: 60, borderRadius: "50%", background: T.grad, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20, fontWeight: 700, color: "#fff", fontFamily: F.sans, boxShadow: "0 0 16px rgba(166,55,45,0.35)" }}>{currentJob.company[0]}</div>
              <div>
                <h2 style={{ fontFamily: F.sans, fontSize: 22, fontWeight: 700, color: T.text, marginBottom: 4, lineHeight: 1.2 }}>{currentJob.title}</h2>
                <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                  <span style={{ fontSize: 14, color: T.t2, fontFamily: F.sans, fontWeight: 500 }}>{currentJob.company}</span>
                  <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 13, color: T.t3, fontFamily: F.sans }}><MapPin size={12} />{currentJob.location}</span>
                  <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 13, color: T.t3, fontFamily: F.sans }}><DollarSign size={12} />{currentJob.salary}</span>
                  <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, color: T.t3, fontFamily: F.sans }}><Clock size={12} />{currentJob.posted}</span>
                </div>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 16, flexShrink: 0 }}>
              <ATSRingLarge score={currentJob.match} />
            </div>
          </div>

          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 16 }}>
            {(currentJob.visa ?? []).map((v) => {
              const s = visaBadge[v] ?? { bg: "rgba(64,18,18,0.1)", color: T.t2, border: T.border };
              return <span key={v} style={{ fontSize: 10, fontWeight: 700, padding: "3px 9px", borderRadius: 4, background: s.bg, color: s.color, border: `1px solid ${s.border}`, fontFamily: F.sans, letterSpacing: "0.04em" }}>{v}</span>;
            })}
            {applied && <span style={{ fontSize: 10, fontWeight: 700, padding: "3px 9px", borderRadius: 4, background: "rgba(34,197,94,0.1)", color: "#22c55e", border: "1px solid rgba(34,197,94,0.25)", fontFamily: F.sans }}>✓ Applied</span>}
          </div>

          <div style={{ display: "flex", gap: 10 }}>
            <button onClick={() => setShowApplyModal(true)} style={{ display: "flex", alignItems: "center", gap: 6, padding: "11px 20px", borderRadius: 10, border: "none", background: T.grad, color: "#fff", fontSize: 13, fontWeight: 600, fontFamily: F.sans, cursor: "pointer", boxShadow: "0 0 20px rgba(166,55,45,0.35)" }}>
              <ExternalLink size={14} /> Apply on Company Website
            </button>
            <button style={{ display: "flex", alignItems: "center", gap: 6, padding: "11px 16px", borderRadius: 10, border: `1px solid ${T.border}`, background: "transparent", color: T.t2, fontSize: 13, fontFamily: F.sans, cursor: "pointer" }}>
              <Bookmark size={14} /> Save
            </button>
            <button style={{ display: "flex", alignItems: "center", gap: 6, padding: "11px 16px", borderRadius: 10, border: `1px solid ${T.border}`, background: "transparent", color: T.t2, fontSize: 13, fontFamily: F.sans, cursor: "pointer" }}>
              <Share2 size={14} /> Share
            </button>
          </div>
        </div>

        {/* ATS Breakdown */}
        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: 24 }}>
          <h3 style={{ fontFamily: F.sans, fontSize: 15, fontWeight: 600, color: T.text, marginBottom: 20 }}>ATS Score for This Position</h3>
          <div style={{ display: "flex", justifyContent: "center", marginBottom: 20 }}>
            <ATSRingLarge score={job.match} />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: T.t3, fontFamily: F.sans, marginBottom: 10 }}>Strong Keywords ✓</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {(currentJob.strongKeywords ?? []).map((kw) => (
                  <span key={kw} style={{ fontSize: 11, padding: "4px 9px", borderRadius: 4, background: "rgba(166,55,45,0.1)", color: T.red, border: "1px solid rgba(166,55,45,0.25)", fontFamily: F.sans, display: "flex", alignItems: "center", gap: 4 }}>
                    <Check size={9} /> {kw}
                  </span>
                ))}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: T.t3, fontFamily: F.sans, marginBottom: 10 }}>Missing Keywords ✗</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {(currentJob.missingKeywords ?? []).map(({ kw, impact }) => (
                  <span key={kw} style={{ fontSize: 11, padding: "4px 9px", borderRadius: 4, background: "rgba(64,18,18,0.12)", color: "rgba(242,238,179,0.5)", border: "1px solid rgba(64,18,18,0.25)", fontFamily: F.sans }}>
                    {kw}
                    <span style={{ marginLeft: 4, fontSize: 9, color: impact === "High" ? "#ef4444" : T.t3 }}>{impact}</span>
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Job Description */}
        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: 24 }}>
          <div style={{ display: "flex", gap: 4, marginBottom: 20, background: "rgba(1,17,38,0.4)", borderRadius: 10, padding: 4 }}>
            {(["responsibilities", "requirements", "niceToHave"] as const).map((t) => (
              <button key={t} onClick={() => setTab(t)}
                style={{ flex: 1, padding: "8px", borderRadius: 8, border: "none", cursor: "pointer", background: tab === t ? T.grad : "transparent", color: tab === t ? "#fff" : T.t2, fontSize: 12, fontWeight: tab === t ? 600 : 400, fontFamily: F.sans, transition: "all 0.2s" }}>
                {t === "responsibilities" ? "Responsibilities" : t === "requirements" ? "Requirements" : "Nice to Have"}
              </button>
            ))}
          </div>
          <AnimatePresence mode="wait">
            <motion.ul key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} style={{ display: "flex", flexDirection: "column", gap: 10, paddingLeft: 0, listStyle: "none" }}>
              {(tabContent[tab] ?? []).map((item) => (
                <li key={item} style={{ display: "flex", alignItems: "flex-start", gap: 10, fontSize: 14, color: T.t2, fontFamily: F.sans, lineHeight: 1.65 }}>
                  <div style={{ width: 6, height: 6, borderRadius: "50%", background: T.red, flexShrink: 0, marginTop: 7 }} />
                  {item}
                </li>
              ))}
            </motion.ul>
          </AnimatePresence>
        </div>
      </div>

      {/* SIDEBAR */}
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {/* Hiring Manager */}
        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: 20 }}>
          <h4 style={{ fontFamily: F.sans, fontSize: 13, fontWeight: 600, color: T.text, marginBottom: 14 }}>Hiring Manager</h4>
          {isPro && job.hiringManager ? (
            <div>
              <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 14 }}>
                <div style={{ width: 48, height: 48, borderRadius: "50%", background: T.grad, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 15, fontWeight: 700, color: "#fff", fontFamily: F.sans }}>{job.hiringManager.name[0]}</div>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: T.text, fontFamily: F.sans }}>{job.hiringManager.name}</div>
                  <div style={{ fontSize: 12, color: T.t2, fontFamily: F.sans }}>{job.hiringManager.title}</div>
                </div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>{job.hiringManager.email}</span>
                  <button style={{ background: "none", border: "none", cursor: "pointer", color: T.t3 }}><Copy size={13} /></button>
                </div>
                <a href={`https://${job.hiringManager.linkedin}`} target="_blank" rel="noreferrer" style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: T.red, fontFamily: F.sans, textDecoration: "none" }}>
                  <Linkedin size={13} /> {job.hiringManager.linkedin}
                </a>
              </div>
            </div>
          ) : (
            <div style={{ textAlign: "center", padding: "16px 0" }}>
              <div style={{ width: 48, height: 48, borderRadius: "50%", background: "rgba(242,238,179,0.05)", margin: "0 auto 10px", display: "flex", alignItems: "center", justifyContent: "center", backdropFilter: "blur(4px)" }}>
                <Lock size={18} color={T.t3} />
              </div>
              <div style={{ fontSize: 13, color: T.t3, fontFamily: F.sans, marginBottom: 10 }}>Upgrade to Pro to unlock hiring manager contacts</div>
              <button style={{ padding: "9px 16px", borderRadius: 10, border: "none", background: T.grad, color: "#fff", fontSize: 12, fontWeight: 600, fontFamily: F.sans, cursor: "pointer" }}>Upgrade to Pro</button>
            </div>
          )}
        </div>

        {/* Visa Info */}
        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: 20 }}>
          <h4 style={{ fontFamily: F.sans, fontSize: 13, fontWeight: 600, color: T.text, marginBottom: 14 }}>Visa Sponsorship Info</h4>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
            {(currentJob.visa ?? []).map((v) => {
              const s = { "H-1B": { bg: "rgba(140,58,39,0.15)", color: T.burnt, border: "rgba(140,58,39,0.35)" }, "F1-OPT": { bg: "rgba(166,55,45,0.12)", color: T.red, border: "rgba(166,55,45,0.3)" } }[v] ?? { bg: "rgba(64,18,18,0.1)", color: T.t2, border: T.border };
              return <span key={v} style={{ fontSize: 10, fontWeight: 700, padding: "3px 8px", borderRadius: 4, background: s.bg, color: s.color, border: `1px solid ${s.border}`, fontFamily: F.sans }}>{v}</span>;
            })}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ position: "relative", width: 60, height: 60 }}>
              <svg viewBox="0 0 60 60" style={{ transform: "rotate(-90deg)", width: "100%", height: "100%" }}>
                <circle cx="30" cy="30" r="24" fill="none" stroke="rgba(242,238,179,0.07)" strokeWidth="6" />
                <motion.circle cx="30" cy="30" r="24" fill="none" stroke={T.red} strokeWidth="6" strokeLinecap="round"
                  strokeDasharray={2 * Math.PI * 24}
                  initial={{ strokeDashoffset: 2 * Math.PI * 24 }}
                  animate={{ strokeDashoffset: 2 * Math.PI * 24 * (1 - job.approvalRate / 100) }}
                  transition={{ duration: 1.4, ease: "easeOut" }}
                />
              </svg>
              <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <span style={{ fontFamily: F.mono, fontSize: 11, fontWeight: 500, color: T.red }}>{job.approvalRate}%</span>
              </div>
            </div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: T.text, fontFamily: F.sans }}>{job.approvalRate}% approval rate</div>
              <div style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>Last year: {job.petitions.toLocaleString()} petitions</div>
            </div>
          </div>
        </div>

        {/* Benefits */}
        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: 20 }}>
          <h4 style={{ fontFamily: F.sans, fontSize: 13, fontWeight: 600, color: T.text, marginBottom: 12 }}>Benefits & Perks</h4>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {(currentJob.benefits ?? []).map((b) => (
              <div key={b} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ width: 20, height: 20, borderRadius: "50%", background: "rgba(166,55,45,0.12)", border: "1px solid rgba(166,55,45,0.25)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <Check size={10} color={T.red} />
                </div>
                <span style={{ fontSize: 13, color: T.t2, fontFamily: F.sans }}>{b}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Apply Modal */}
      <AnimatePresence>
        {showApplyModal && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            style={{ position: "fixed", inset: 0, background: "rgba(1,17,38,0.85)", backdropFilter: "blur(8px)", zIndex: 200, display: "flex", alignItems: "center", justifyContent: "center" }}
            onClick={() => setShowApplyModal(false)}
          >
            <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.9, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              style={{ width: 420, background: "rgba(64,18,18,0.9)", backdropFilter: "blur(24px)", border: "1px solid rgba(242,238,179,0.1)", borderRadius: 24, padding: "36px 32px" }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
                <h3 style={{ fontFamily: F.sans, fontSize: 18, fontWeight: 600, color: T.text }}>Did you apply for this position?</h3>
                <button onClick={() => setShowApplyModal(false)} style={{ background: "none", border: "none", cursor: "pointer", color: T.t3 }}><X size={18} /></button>
              </div>
              <div style={{ fontSize: 14, color: T.t2, fontFamily: F.sans, marginBottom: 24 }}>
                <strong style={{ color: T.text }}>{job.title}</strong> at <strong style={{ color: T.text }}>{job.company}</strong>
              </div>
              <div style={{ display: "flex", gap: 12 }}>
                <button onClick={() => { setApplied(true); setShowApplyModal(false); }} style={{ flex: 1, padding: "13px", borderRadius: 12, border: "none", background: T.grad, color: "#fff", fontSize: 14, fontWeight: 600, fontFamily: F.sans, cursor: "pointer" }}>
                  Yes, I Applied! 🎉
                </button>
                <button onClick={() => setShowApplyModal(false)} style={{ flex: 1, padding: "13px", borderRadius: 12, border: `1px solid ${T.border}`, background: "transparent", color: T.t2, fontSize: 14, fontFamily: F.sans, cursor: "pointer" }}>
                  No
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
   </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
