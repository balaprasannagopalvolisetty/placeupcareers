import { useState, useEffect, type ReactNode } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ArrowLeft, MapPin, DollarSign, ExternalLink, Bookmark, Share2, Check, X, ShieldCheck, Sparkles, Briefcase } from "lucide-react";
import * as api from "../../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  text: "var(--pu-f1f5f9-t)", t2: "var(--pu-226-232-240-072)", t3: "var(--pu-148-163-184-075)",
  border: "var(--pu-148-163-184-008)", glass: "var(--pu-15-30-55-055)",
  grad: "linear-gradient(135deg, var(--pu-2563eb), var(--pu-0ea5e9))",
  red: "var(--pu-3b82f6-t)", burnt: "var(--pu-60a5fa-t)", dark: "var(--pu-1d4ed8)",
};

function normalizeVisa(visa: unknown): string[] {
  if (Array.isArray(visa)) {
    return visa.filter((item): item is string => typeof item === "string");
  }
  if (visa && typeof visa === "object") {
    const record = visa as Record<string, unknown>;
    const country = typeof record.visa_country === "string" ? record.visa_country : "";
    const programNames = Array.isArray(record.visa_program_names)
      ? record.visa_program_names.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
      : [];
    const badges = programNames.map((name) => country ? `${country}: ${name}` : name);
    if (country === "US") {
      if (record.visa_h1b) badges.push("H-1B");
      if (record.visa_opt) badges.push("F1-OPT");
      if (record.visa_stem_opt) badges.push("F1-STEM");
      if (record.h1b_verified) badges.push("H-1B Verified");
      if (record.green_card) badges.push("Green Card");
    }
    if (record.no_sponsorship) badges.push("No sponsorship");
    return Array.from(new Set(badges));
  }
  if (typeof visa === "string") {
    return visa.split(",").map((item) => item.trim()).filter(Boolean);
  }
  return [];
}

function formatSalary(salary: unknown): string {
  if (!salary) return "";
  if (typeof salary === "string") return salary;
  if (typeof salary === "object") {
    // A2: treat 0 / negative as "no data" — never render $0K–$0K.
    const rawMin = (salary as any).min_salary;
    const rawMax = (salary as any).max_salary;
    const min = typeof rawMin === "number" && rawMin > 0 ? rawMin : undefined;
    const max = typeof rawMax === "number" && rawMax > 0 ? rawMax : undefined;
    if (min !== undefined && max !== undefined) {
      return `$${Math.round(min / 1000)}K–$${Math.round(max / 1000)}K`;
    }
    if (min !== undefined) {
      return `$${Math.round(min / 1000)}K+`;
    }
    if (max !== undefined) {
      return `Up to $${Math.round(max / 1000)}K`;
    }
    if ((salary as any).display && !/\$0K/.test(String((salary as any).display))) {
      return String((salary as any).display);
    }
  }
  return "";
}

function formatPostDate(value: unknown): string {
  if (!value) return "Recently";
  const raw = String(value);
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) {
    return raw.split("T")[0] || raw;
  }
  return parsed.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function ATSRingLarge({ score }: { score: number | null | undefined }) {
  const hasScore = typeof score === "number" && Number.isFinite(score);
  const safeScore = hasScore ? Math.max(0, Math.min(100, score)) : 0;
  const r = 52, circ = 2 * Math.PI * r, offset = circ * (1 - safeScore / 100);
  // Keep the ring legible even at low scores by avoiding the near-background T.dark.
  const color = !hasScore ? T.t3 : safeScore >= 80 ? "var(--pu-22c55e-b)" : safeScore >= 60 ? T.red : safeScore >= 40 ? T.burnt : "var(--pu-f1f5f9-t)";
  const textColor = safeScore >= 40 ? color : "var(--pu-f1f5f9-t)";
  return (
    <div style={{ position: "relative", width: 120, height: 120 }}>
      <svg viewBox="0 0 120 120" style={{ width: "100%", height: "100%", transform: "rotate(-90deg)" }}>
        <defs>
          <filter id="jd-glow"><feGaussianBlur stdDeviation="3" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
        </defs>
        <circle cx="60" cy="60" r={r} fill="none" stroke="var(--pu-148-163-184-012)" strokeWidth="9" />
        <motion.circle cx="60" cy="60" r={r} fill="none" stroke={color} strokeWidth="9" strokeLinecap="round"
          strokeDasharray={circ} initial={{ strokeDashoffset: circ }} animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1.5, ease: "easeOut" }} filter="url(#jd-glow)" />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <span style={{ fontFamily: F.mono, fontSize: hasScore ? 28 : 22, fontWeight: 600, color: textColor, lineHeight: 1 }}>{hasScore ? safeScore : "--"}</span>
        <span style={{ fontSize: 8, letterSpacing: "0.08em", textTransform: "uppercase", color: T.t2, fontFamily: F.sans, marginTop: 2 }}>{hasScore ? "Match" : "Resume"}</span>
      </div>
    </div>
  );
}

function getScoreMeta(score: number | null | undefined, scoreType?: string) {
  if (typeof score !== "number" || !Number.isFinite(score)) {
    if (scoreType === "insufficient_jd") {
      return {
        label: "Job details incomplete",
        detail: "This role needs a complete job description before it can be scored.",
        color: T.t3,
        bg: "var(--pu-148-163-184-005)",
        border: T.border,
      };
    }
    return {
      label: "Resume match unavailable",
      detail: "Upload or activate a resume to calculate a real score.",
      color: T.t3,
      bg: "var(--pu-148-163-184-005)",
      border: T.border,
    };
  }
  if (scoreType === "baseline_ats") {
    return { label: "ATS estimate", detail: "Upload or activate a resume for an exact match score.", color: T.t2, bg: "var(--pu-148-163-184-006)", border: T.border };
  }
  if (scoreType === "insufficient_jd") {
    return { label: "ATS estimate", detail: "This posting needs more job description detail before exact scoring.", color: T.t2, bg: "var(--pu-148-163-184-006)", border: T.border };
  }
  if (score >= 80) return { label: "Strong match", detail: "This role lines up well with your active resume.", color: "var(--pu-22c55e-t)", bg: "var(--pu-34-197-94-01)", border: "var(--pu-34-197-94-025)" };
  if (score >= 60) return { label: "Good match", detail: "A few resume keyword updates could improve your odds.", color: T.red, bg: "var(--pu-59-130-246-012)", border: "var(--pu-59-130-246-028)" };
  if (score >= 40) return { label: "Partial match", detail: "Review requirements before applying.", color: T.burnt, bg: "var(--pu-37-99-235-012)", border: "var(--pu-37-99-235-028)" };
  return { label: "Low match", detail: "This posting appears far from your active resume.", color: "var(--pu-f1f5f9-t)", bg: "var(--pu-148-163-184-006)", border: "var(--pu-148-163-184-012)" };
}

function useViewportWidth() {
  // Track viewport width so the JobDetail layout can collapse its
  // 1.8fr / 1fr two-column split into a single stacked column on
  // phones — without this the right sidebar overflowed off-screen.
  const get = () => (typeof window === "undefined" ? 1280 : window.innerWidth);
  const [w, setW] = useState<number>(get);
  useEffect(() => {
    const onResize = () => setW(get());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return { width: w, isMobile: w < 640, isTablet: w < 1024 };
}

// ─── Job Description Renderer ────────────────────────────────────────────────

function renderInline(text: string): ReactNode {
  const regex = /(\*\*[^*\n]+\*\*|\*[^*\n]+\*|`[^`\n]+`)/g;
  const parts: ReactNode[] = [];
  let last = 0;
  let k = 0;
  let m: RegExpExecArray | null;
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**"))
      parts.push(<strong key={k++} style={{ color: T.text, fontWeight: 700 }}>{tok.slice(2, -2)}</strong>);
    else if (tok.startsWith("*"))
      parts.push(<em key={k++} style={{ fontStyle: "italic" }}>{tok.slice(1, -1)}</em>);
    else
      parts.push(<code key={k++} style={{ fontSize: 12, background: "var(--pu-148-163-184-008)", padding: "1px 5px", borderRadius: 4, fontFamily: F.mono }}>{tok.slice(1, -1)}</code>);
    last = m.index + tok.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts.length === 1 && typeof parts[0] === "string" ? parts[0] : <>{parts}</>;
}

// Common job-description section titles. A line that IS one of these (case-
// insensitive, optional trailing colon) becomes a major section header even
// when the scraped source flattened everything into same-size text.
const KNOWN_HEADINGS = /^(a family of companies( and experiences)?|about( the (role|company|team|position))?|company (overview|description)|who we are|job summary|summary|overview|position (summary|overview)|role (summary|overview)|job description|core responsibilities|key responsibilities|responsibilities|what you'?ll do|what you will do|duties|essential (duties|functions)|day[- ]to[- ]day|requirements|basic qualifications|minimum qualifications|preferred qualifications|qualifications|required (skills|qualifications|experience)|skills( (&|and) (experience|qualifications))?|experience|education|nice to have|what we'?re looking for|benefits|perks( (&|and) benefits)?|what we offer|compensation( (&|and) benefits)?|salary( range)?|pay( range)?|why (join|work) (us|here|with us)|our (culture|values|story)|equal (employment )?opportunity( (employer|statement))?|eeo( statement)?|diversity( (&|and) inclusion)?|location|work (location|environment)|schedule|about us|the (role|opportunity)|associates at corporate are offered many fantastic benefits)\s*:?\s*$/i;

type JDBlock =
  | { t: "h1"; s: string }
  | { t: "h2"; s: string }
  | { t: "bullet"; s: string }
  | { t: "p"; s: string };

/** A short, title-like line with no sentence punctuation (e.g. "Medical",
 * "Paid Parental Leave", "Systems Strategy & Administration"). */
function isShortLabel(s: string): boolean {
  const t = s.trim();
  if (!t || t.length > 52) return false;
  if (/[.!?,;]$/.test(t)) return false;      // reads like a sentence / clause
  if (t.split(/\s+/).length > 7) return false;
  return /^[A-Z0-9("']/.test(t);             // starts like a title
}

function renderJobDescription(raw: string): ReactNode {
  if (!raw?.trim()) return <span style={{ color: T.t3, fontFamily: F.sans, fontSize: 13 }}>Open the original posting for full details.</span>;

  // 1) Normalise the source to line-structured text. Real HTML tags are turned
  //    into explicit markers (### headings, • bullets) so genuine structure is
  //    preserved; the heuristics below recover structure the scraper flattened.
  const ta = document.createElement("textarea");
  ta.innerHTML = raw;
  let text = ta.value;
  text = text.replace(/<h[1-4]\b[^>]*>/gi, "\n## ").replace(/<\/h[1-4]>/gi, "\n");
  text = text.replace(/<li\b[^>]*>/gi, "\n• ").replace(/<\/li>/gi, "\n");
  text = text.replace(/<br\s*\/?>/gi, "\n");
  text = text.replace(/<\/?(p|div|ul|ol|section|tr)\b[^>]*>/gi, "\n");
  text = text.replace(/<[^>]+>/g, "");
  text = text.replace(/\*\*+|__+|~~+/g, "");
  text = text.replace(/^#+\s*/gm, "## ");    // normalise any md heading depth
  text = text.replace(/\\([^\w\s])/g, "$1"); // unescape "\&" -> "&" etc.
  text = text.replace(/^[ \t]*([^\n]{1,60})\n[ \t]*[-=]{3,}[ \t]*$/gm, "## $1"); // setext
  text = text.replace(/^[ \t]*[-=_*]{3,}[ \t]*$/gm, "");                          // rules

  const lines = text.split("\n").map((l) => l.replace(/[ \t]+/g, " ").trim());

  // 2) Classify each non-blank line into a tentative block type.
  const raws: (JDBlock | null)[] = lines.map((line): JDBlock | null => {
    if (!line) return null;
    let m = line.match(/^#{1,6}\s+(.*)/);
    if (m) return { t: "h1", s: m[1].replace(/:$/, "").trim() };
    m = line.match(/^(?:[*\-•·+▪◦‣●○]|\d+[.)])\s+(.*)/);
    if (m) return { t: "bullet", s: m[1].trim() };
    if (KNOWN_HEADINGS.test(line)) return { t: "h1", s: line.replace(/:$/, "").trim() };
    // "Something:" on its own short line → sub-heading.
    if (/:$/.test(line) && line.length <= 60 && line.split(/\s+/).length <= 8) {
      return { t: "h2", s: line.replace(/:$/, "").trim() };
    }
    return { t: "p", s: line };
  });

  // 3) Second pass: turn runs of short labels into bullets (e.g. the flat
  //    "Medical / Dental / Vision" benefits list) and promote a lone short
  //    label that introduces a paragraph into a sub-heading.
  const blocksData: JDBlock[] = [];
  for (let i = 0; i < raws.length; i++) {
    const b = raws[i];
    if (!b) continue;
    if (b.t === "p" && isShortLabel(b.s)) {
      const prev = [...raws.slice(0, i)].reverse().find((x) => x);
      const next = raws.slice(i + 1).find((x) => x);
      const prevIsLabel = !!prev && (prev.t === "bullet" || (prev.t === "p" && isShortLabel(prev.s)));
      const nextIsLabel = !!next && next.t === "p" && isShortLabel(next.s);
      const nextIsBody = !!next && next.t === "p" && !isShortLabel(next.s) && next.s.length > 60;
      if (prevIsLabel || nextIsLabel) { blocksData.push({ t: "bullet", s: b.s }); continue; }
      if (nextIsBody) { blocksData.push({ t: "h2", s: b.s }); continue; }
    }
    blocksData.push(b);
  }

  // 4) Render, grouping consecutive bullets into a single list.
  const out: ReactNode[] = [];
  let bucket: string[] = [];
  let key = 0;
  const flush = () => {
    if (!bucket.length) return;
    out.push(
      <ul key={`ul-${key++}`} style={{ margin: "6px 0 14px", paddingLeft: 22, display: "flex", flexDirection: "column", gap: 6 }}>
        {bucket.map((item, j) => (
          <li key={j} style={{ fontSize: 13.5, color: T.t2, fontFamily: F.sans, lineHeight: 1.6 }}>{renderInline(item)}</li>
        ))}
      </ul>
    );
    bucket = [];
  };
  blocksData.forEach((b, i) => {
    if (b.t === "bullet") { bucket.push(b.s); return; }
    flush();
    if (b.t === "h1") {
      out.push(
        <div key={`h1-${i}`} style={{ fontSize: 15.5, fontWeight: 800, color: T.text, fontFamily: F.sans, marginTop: i === 0 ? 0 : 24, marginBottom: 10, paddingBottom: 7, borderBottom: `1px solid ${T.border}`, letterSpacing: "-0.01em" }}>
          {b.s}
        </div>
      );
    } else if (b.t === "h2") {
      out.push(
        <div key={`h2-${i}`} style={{ fontSize: 13.5, fontWeight: 700, color: T.text, fontFamily: F.sans, marginTop: 16, marginBottom: 6 }}>
          {b.s}
        </div>
      );
    } else {
      out.push(
        <p key={`p-${i}`} style={{ fontSize: 13.5, color: T.t2, fontFamily: F.sans, lineHeight: 1.75, margin: "0 0 10px" }}>
          {renderInline(b.s)}
        </p>
      );
    }
  });
  flush();
  return <div style={{ display: "flex", flexDirection: "column" }}>{out}</div>;
}

export function JobDetailPage({ jobId, onBack }: { jobId: string; onBack: () => void }) {
  const { isMobile, isTablet } = useViewportWidth();
  const [job, setJob] = useState<api.JobPost | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"responsibilities" | "requirements" | "niceToHave">("responsibilities");
  const [showApplyModal, setShowApplyModal] = useState(false);
  const [applied, setApplied] = useState(false);
  const [savingApplication, setSavingApplication] = useState(false);
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);
  const [atsAnalysis, setAtsAnalysis] = useState<api.AtsAnalysis | null>(null);
  const [applyNotes, setApplyNotes] = useState("");
  const [heardBack, setHeardBack] = useState<"unknown" | "yes" | "no">("unknown");
  const [positionOpen, setPositionOpen] = useState<"unknown" | "yes" | "no">("unknown");
  const [salaryOffered, setSalaryOffered] = useState("");
  const [resumeVersion, setResumeVersion] = useState(
    () => typeof window !== "undefined" ? localStorage.getItem("placeup_resume_version") || "" : ""
  );
  useEffect(() => {
    const refresh = () => {
      setResumeVersion(typeof window !== "undefined" ? localStorage.getItem("placeup_resume_version") || String(Date.now()) : String(Date.now()));
    };
    window.addEventListener("placeup:resume-changed", refresh as EventListener);
    window.addEventListener("focus", refresh);
    return () => {
      window.removeEventListener("placeup:resume-changed", refresh as EventListener);
      window.removeEventListener("focus", refresh);
    };
  }, []);

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
  }, [jobId, resumeVersion]);

  // Advanced ATS analysis of the user's active resume vs this job (no upload).
  useEffect(() => {
    let active = true;
    setAtsAnalysis(null);
    api.getActiveAtsAnalysis(String(jobId))
      .then((res) => { if (active) setAtsAnalysis(res); })
      .catch(() => { if (active) setAtsAnalysis(null); });
    return () => { active = false; };
  }, [jobId, resumeVersion]);

  // Look across every URL field the backend may expose so the Apply button
  // works regardless of which scraper sourced the job.
  const resolvedJobUrl = (() => {
    const j: any = job ?? {};
    // Only a job-SPECIFIC resolved posting may outrank the original link.
    // Generic "/careers" landing pages are never used for Apply.
    const resolvedPosting = j.extra_metadata?.company_link?.link_type === "ats_posting"
      ? j.extra_metadata?.company_link?.url
      : undefined;
    const candidates = [
      j.job_url_direct,          // official company posting (backend already gates by link_type)
      resolvedPosting,
      j.job_url,
      j.source_url,
      j.apply_url,
      j.url,
      j.company_url,
      j.external_url,
    ];
    const first = candidates.find((u) => typeof u === "string" && u.trim().length > 0);
    if (!first) return "";
    const trimmed = String(first).trim();
    // Make sure we always pass an absolute URL to window.open()
    return /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
  })();

  // HONEST apply button: only claim "Company Website" when the link actually
  // leaves the third-party boards. While the company-link pipeline works
  // through the backlog, unresolved jobs say "Apply on LinkedIn" etc. instead
  // of pretending.
  const applyLabel = (() => {
    if (!resolvedJobUrl) return "Search this role";
    let host = "";
    try { host = new URL(resolvedJobUrl).hostname.toLowerCase(); } catch { return "Apply to this Position"; }
    const boards: Array<[string, string]> = [
      ["linkedin.com", "LinkedIn"], ["indeed.com", "Indeed"], ["glassdoor.", "Glassdoor"],
      ["dice.com", "Dice"], ["joinhandshake.com", "Handshake"], ["handshake.com", "Handshake"],
      ["ziprecruiter.com", "ZipRecruiter"], ["monster.com", "Monster"],
      ["simplyhired.com", "SimplyHired"], ["jooble.org", "Jooble"], ["jobbank.gc.ca", "Job Bank"],
      ["findajob.dwp.gov.uk", "Find a Job"], ["jobs.nhs.uk", "NHS Jobs"], ["arbeitnow.com", "Arbeitnow"],
      ["remoteok.com", "RemoteOK"], ["remotive.com", "Remotive"], ["weworkremotely.com", "WWR"],
      ["mycareersfuture.gov.sg", "MyCareersFuture"], ["jobicy.com", "Jobicy"],
    ];
    const board = boards.find(([needle]) => host.includes(needle));
    return board ? `Apply on ${board[1]}` : "Apply on Company";
  })();

  const currentJob = {
    ...(job || {}),
    title: job?.title ?? "Untitled role",
    company: job?.company ?? "Unknown",
    location: job?.location ?? "Remote",
    salary: formatSalary(job?.salary),
    match: job?.match_score ?? job?.match ?? null,
    visa: normalizeVisa(job?.visa),
    posted: formatPostDate(job?.posted_at ?? job?.posted),
    status: job?.status ?? "active",
    description: job?.description ?? "",
    responsibilities: job?.responsibilities ?? [],
    requirements: job?.requirements ?? [],
    niceToHave: job?.niceToHave ?? [],
    strongKeywords: atsAnalysis?.matched_keywords
      ? Object.values(atsAnalysis.matched_keywords).flat()
      : (job?.strongKeywords ?? []),
    missingKeywords: atsAnalysis?.missing_with_impact
      ? atsAnalysis.missing_with_impact.map((m) => ({ kw: m.keyword, impact: m.impact }))
      : (Array.isArray(job?.missingKeywords) ? (job?.missingKeywords as any) : []),
    benefits: job?.benefits ?? [],
    approvalRate: typeof job?.approvalRate === "number" ? job.approvalRate : null,
    petitions: typeof job?.petitions === "number" ? job.petitions : null,
    jobUrl: resolvedJobUrl,
  };

  useEffect(() => {
    if (!jobId || typeof window === "undefined") return;
    const savedJobs = JSON.parse(localStorage.getItem("placeup_saved_jobs") || "[]");
    setSaved(Array.isArray(savedJobs) && savedJobs.includes(String(jobId)));
  }, [jobId]);

  const openCompanyApply = () => {
    // ALWAYS show the application tracker modal regardless of whether
    // window.open succeeded (popup blockers / mobile Safari often return
    // null even when the tab opened). This is what the user wants:
    // the post-apply questions must always appear.
    const targetUrl = currentJob.jobUrl
      ? currentJob.jobUrl
      : `https://www.google.com/search?q=${encodeURIComponent(
          `${currentJob.company} ${currentJob.title} apply`
        )}`;
    try {
      window.open(targetUrl, "_blank", "noopener,noreferrer");
    } catch {
      // Some embedded webviews block window.open entirely — proceed anyway.
    }
    setShowApplyModal(true);
  };

  const recordApplication = async (status: "applied" | "not_applied", reason = "") => {
    setSavingApplication(true);
    try {
      await api.saveUserApplication({
        job_id: String(jobId),
        title: currentJob.title,
        company: currentJob.company,
        location: currentJob.location,
        job_url: currentJob.jobUrl,
        description: currentJob.description,
        match_score: typeof currentJob.match === "number" ? currentJob.match : 0,
        status,
        not_applied_reason: reason,
        heard_back: heardBack === "unknown" ? undefined : heardBack === "yes",
        position_open: positionOpen === "unknown" ? undefined : positionOpen === "yes",
        salary_offered: salaryOffered.trim() || undefined,
        notes: applyNotes.trim() || undefined,
      });
      setApplied(status === "applied");
      setShowApplyModal(false);
      setApplyNotes("");
      setHeardBack("unknown");
      setPositionOpen("unknown");
      setSalaryOffered("");
    } finally {
      setSavingApplication(false);
    }
  };

  const toggleSave = () => {
    const id = String(jobId);
    try {
      const raw = localStorage.getItem("placeup_saved_jobs") || "[]";
      const parsed = JSON.parse(raw);
      const list = Array.isArray(parsed) ? parsed.map(String) : [];
      const next = list.includes(id) ? list.filter((item) => item !== id) : [...list, id];
      localStorage.setItem("placeup_saved_jobs", JSON.stringify(next));
      setSaved(next.includes(id));
    } catch {
      // Storage may be disabled (private mode / quota) — still flip the local UI flag
      setSaved((prev) => !prev);
    }
  };

  const copyToClipboardFallback = (text: string) => {
    try {
      const el = document.createElement("textarea");
      el.value = text;
      el.style.position = "fixed";
      el.style.opacity = "0";
      document.body.appendChild(el);
      el.focus();
      el.select();
      document.execCommand("copy");
      document.body.removeChild(el);
      return true;
    } catch {
      return false;
    }
  };

  const shareJob = async () => {
    const url = currentJob.jobUrl || (typeof window !== "undefined" ? window.location.href : "");
    const text = `${currentJob.title} at ${currentJob.company}`;
    const flashCopied = () => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    };
    // navigator.share only works on HTTPS + supported browsers; gracefully degrade everywhere else.
    if (typeof navigator !== "undefined" && (navigator as any).share) {
      try {
        await (navigator as any).share({ title: text, text, url });
        return;
      } catch {
        // user cancelled / share failed — fall through to clipboard
      }
    }
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(url);
        flashCopied();
        return;
      }
    } catch {
      // fall through
    }
    if (copyToClipboardFallback(url)) flashCopied();
  };

  if (loading) {
    return <div style={{ color: "var(--pu-f1f5f9-t)", fontFamily: F.sans, fontSize: 14 }}>Loading job details...</div>;
  }

  if (error) {
    return <div style={{ color: "var(--pu-ff7f7f-t)", fontFamily: F.sans, fontSize: 14 }}>{error}</div>;
  }

  const visaBadge: Record<string, { bg: string; color: string; border: string }> = {
    "H-1B":    { bg: "var(--pu-37-99-235-015)", color: T.burnt,  border: "var(--pu-37-99-235-035)" },
    "F1-OPT":  { bg: "var(--pu-59-130-246-012)", color: T.red,    border: "var(--pu-59-130-246-03)" },
    "F1-STEM": { bg: "var(--pu-15-30-55-015)",  color: T.red,    border: "var(--pu-15-30-55-03)" },
  };

  // Scrapers occasionally leak HTTP errors, "nan"/"null" tokens, or full HTML
  // blobs into description sections. Filter aggressively on the client so the
  // tab bodies always show useful content (or a clean fallback below).
  const decodeHtml = (value: string) => {
    const el = document.createElement("textarea");
    el.innerHTML = value;
    return el.value;
  };
  const BAD_PATTERN = /(traceback|stack trace|exception|http\/\d|too many requests|undefined|null\b|^nan$|client error|server error|<\/?(div|script|style|html|body|p|li|ul)\b|apply now|privacy policy|salary range|annual salary|base pay|compensation range|\$\d)/i;
  const sanitizeBullet = (raw: unknown): string | null => {
    if (typeof raw !== "string") return null;
    let line = decodeHtml(raw).replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
    line = line.replace(/^[•·\-\*–—\s]+/, "").trim();
    if (line.length < 8 || line.length > 320) return null;
    if (BAD_PATTERN.test(line)) return null;
    if (/^(responsibilities|requirements|nice to have|preferred|qualifications)$/i.test(line)) return null;
    return line;
  };
  const cleanList = (input: unknown): string[] => {
    if (!Array.isArray(input)) return [];
    const seen = new Set<string>();
    const out: string[] = [];
    for (const v of input) {
      const c = sanitizeBullet(v);
      if (!c) continue;
      const key = c.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(c);
    }
    return out;
  };
  const scoreMeta = getScoreMeta(currentJob.match, job?.score_type);
  const visibleKeywords = (currentJob.strongKeywords ?? []).slice(0, 10);
  const visibleMissing = (currentJob.missingKeywords ?? []).slice(0, 10);
  const role = (job as any)?.role || (job as any)?.taxonomy_category || currentJob.status;
  const responsibilityHighlights = cleanList(currentJob.responsibilities).slice(0, 4);
  const requirementHighlights = cleanList(currentJob.requirements).slice(0, 4);
  const niceHighlights = cleanList(currentJob.niceToHave).slice(0, 3);
  const descriptionText = currentJob.description || "";
  const jdWordCount = descriptionText ? descriptionText.replace(/<[^>]+>/g, " ").trim().split(/\s+/).filter(Boolean).length : 0;
  const jdSignals = [
    { label: "Keywords", value: String((currentJob.strongKeywords ?? []).length + (currentJob.missingKeywords ?? []).length) },
    { label: "JD depth", value: jdWordCount > 450 ? "Full" : jdWordCount > 140 ? "Medium" : "Short" },
    { label: "Sections", value: String([responsibilityHighlights, requirementHighlights, niceHighlights].filter((items) => items.length).length || 1) },
  ];
  const highlightCards = [
    { title: "What you'll do", items: responsibilityHighlights, tone: "var(--pu-59-130-246-01)" },
    { title: "What they need", items: requirementHighlights, tone: "var(--pu-148-163-184-006)" },
    { title: "Standout signals", items: niceHighlights.length ? niceHighlights : visibleMissing.slice(0, 3).map((item) => `${item.kw} (${item.impact})`), tone: "var(--pu-37-99-235-013)" },
  ].filter((card) => card.items.length);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: isMobile ? 14 : 20, width: "100%", minWidth: 0, maxWidth: 1180, margin: "0 auto" }}>
      {/* MAIN */}
      <div style={{ display: "flex", flexDirection: "column", gap: 16, minWidth: 0 }}>
        <button onClick={onBack} style={{ display: "flex", alignItems: "center", gap: 6, background: "none", border: "none", cursor: "pointer", color: T.t2, fontSize: 13, fontFamily: F.sans, width: "fit-content" }}>
          <ArrowLeft size={14} /> All jobs
        </button>

        {/* Header card */}
        <div style={{ background: "var(--pu-8-18-38-055)", backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 18, padding: isMobile ? 18 : 24 }}>
          {/* minmax(320px,...) keeps the title/actions column from crushing to a
              sliver at intermediate viewport widths (single-word-per-line bug). */}
          <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "minmax(320px, 1fr) 230px", gap: 20, alignItems: "start" }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
                <div style={{ width: 38, height: 38, borderRadius: 10, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, color: "var(--pu-ffffff-t)", fontSize: 16, fontFamily: F.sans, background: `linear-gradient(135deg, ${T.red}, var(--pu-0b1220))` }}>
                  {(currentJob.company || "?").charAt(0).toUpperCase()}
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13.5, fontWeight: 700, color: T.text, fontFamily: F.sans, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{currentJob.company}</div>
                  <div style={{ fontSize: 11.5, color: T.t3, fontFamily: F.sans }}>{currentJob.posted}</div>
                </div>
              </div>

              <h2 style={{ fontFamily: F.sans, fontSize: isMobile ? 22 : 26, fontWeight: 800, color: T.text, margin: "0 0 14px", lineHeight: 1.18, letterSpacing: "-0.01em" }}>{currentJob.title}</h2>

              <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: "9px 18px", fontSize: 12.5, color: T.t2, fontFamily: F.sans, marginBottom: 16 }}>
                <span style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}><MapPin size={13} color={T.red} style={{ flexShrink: 0 }} /> <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{currentJob.location}</span></span>
                {currentJob.salary ? <span style={{ display: "flex", alignItems: "center", gap: 6 }}><DollarSign size={13} color={T.red} style={{ flexShrink: 0 }} /> {currentJob.salary}</span> : null}
                <span style={{ display: "flex", alignItems: "center", gap: 6, textTransform: "capitalize", minWidth: 0 }}><Briefcase size={13} color={T.red} style={{ flexShrink: 0 }} /> <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{role}</span></span>
                {(currentJob.visa ?? []).length ? <span style={{ display: "flex", alignItems: "center", gap: 6 }}><ShieldCheck size={13} color={T.red} style={{ flexShrink: 0 }} /> {(currentJob.visa ?? []).length} visa signal{(currentJob.visa ?? []).length > 1 ? "s" : ""}</span> : null}
              </div>

              <div style={{ display: "flex", gap: 7, flexWrap: "wrap", marginBottom: 18 }}>
                {(currentJob.visa ?? []).map((v) => (
                  <span key={v} style={{ fontSize: 11, fontWeight: 700, padding: "5px 11px", borderRadius: 999, background: "var(--pu-52-211-153-012)", color: "var(--pu-6ee7b7-t)", border: "1px solid var(--pu-52-211-153-03)", fontFamily: F.sans, display: "inline-flex", alignItems: "center", gap: 5 }}><Check size={11} /> {v}</span>
                ))}
                {applied && <span style={{ fontSize: 11, fontWeight: 700, padding: "5px 11px", borderRadius: 999, background: "var(--pu-52-211-153-012)", color: "var(--pu-6ee7b7-t)", border: "1px solid var(--pu-52-211-153-03)", fontFamily: F.sans }}>Applied</span>}
              </div>

              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <button type="button" onClick={openCompanyApply} title={currentJob.jobUrl ? currentJob.jobUrl : "Open a Google search for this role"}
                  style={{ display: "flex", alignItems: "center", gap: 6, padding: "11px 22px", borderRadius: 10, border: "none", background: T.grad, color: "var(--pu-ffffff-t)", fontSize: 13, fontWeight: 800, fontFamily: F.sans, cursor: "pointer" }}>
                  <ExternalLink size={14} /> {applyLabel}
                </button>
                <button type="button" onClick={toggleSave}
                  style={{ display: "flex", alignItems: "center", gap: 6, padding: "11px 16px", borderRadius: 10, border: `1px solid ${saved ? "var(--pu-59-130-246-035)" : T.border}`, background: saved ? "var(--pu-59-130-246-01)" : "var(--pu-148-163-184-003)", color: saved ? T.red : T.t2, fontSize: 13, fontWeight: 700, fontFamily: F.sans, cursor: "pointer" }}>
                  <Bookmark size={14} fill={saved ? T.red : "none"} /> {saved ? "Saved" : "Save"}
                </button>
                <button type="button" onClick={shareJob}
                  style={{ display: "flex", alignItems: "center", gap: 6, padding: "11px 16px", borderRadius: 10, border: `1px solid ${T.border}`, background: "var(--pu-148-163-184-003)", color: copied ? T.red : T.t2, fontSize: 13, fontWeight: 700, fontFamily: F.sans, cursor: "pointer" }}>
                  <Share2 size={14} /> {copied ? "Copied!" : "Share"}
                </button>
              </div>
            </div>

            {/* Match panel */}
            <div style={{ background: "var(--pu-59-130-246-008)", border: "1px solid var(--pu-59-130-246-025)", borderRadius: 14, overflow: "hidden" }}>
              <div style={{ padding: "14px 16px", display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8, borderBottom: "1px solid var(--pu-59-130-246-018)" }}>
                <span style={{ fontSize: 30, fontWeight: 800, color: T.text, fontFamily: F.sans, lineHeight: 1 }}>{typeof currentJob.match === "number" ? currentJob.match : "--"}<span style={{ fontSize: 15, color: T.t3 }}>{typeof currentJob.match === "number" ? "%" : ""}</span></span>
                <span style={{ fontSize: 10.5, fontWeight: 800, letterSpacing: "0.05em", textTransform: "uppercase", color: scoreMeta.color, fontFamily: F.sans, textAlign: "right" }}>{scoreMeta.label}</span>
              </div>
              <div style={{ padding: "13px 16px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, fontFamily: F.sans, marginBottom: 6 }}>
                  <span style={{ color: T.t2 }}>Keywords matched</span>
                  <span style={{ color: T.text, fontWeight: 700 }}>{visibleKeywords.length}/{visibleKeywords.length + visibleMissing.length}</span>
                </div>
                <div style={{ height: 5, borderRadius: 999, background: "var(--pu-148-163-184-01)", marginBottom: 12 }}>
                  <div style={{ height: 5, borderRadius: 999, background: T.red, width: `${(visibleKeywords.length + visibleMissing.length) ? Math.round((visibleKeywords.length / (visibleKeywords.length + visibleMissing.length)) * 100) : 0}%` }} />
                </div>
                <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans, lineHeight: 1.5 }}>{scoreMeta.detail}</div>
              </div>
            </div>
          </div>
        </div>

        {/* ATS keyword analysis */}
        {(visibleKeywords.length > 0 || visibleMissing.length > 0) && (
          <div style={{ background: "var(--pu-8-18-38-055)", backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 18, padding: isMobile ? 18 : 24 }}>
            <h3 style={{ fontFamily: F.sans, fontSize: 15, fontWeight: 800, color: T.text, margin: "0 0 4px" }}>ATS keyword analysis</h3>
            <div style={{ fontFamily: F.sans, fontSize: 12, color: T.t3, marginBottom: 16 }}>How your active resume lines up with this posting.</div>
            <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 16 }}>
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--pu-6ee7b7-t)", fontFamily: F.sans, marginBottom: 10 }}>You have</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
                  {visibleKeywords.length ? visibleKeywords.map((kw) => (
                    <span key={kw} style={{ fontSize: 11.5, padding: "5px 10px", borderRadius: 8, background: "var(--pu-52-211-153-012)", color: "var(--pu-6ee7b7-t)", border: "1px solid var(--pu-52-211-153-028)", fontFamily: F.sans, display: "inline-flex", alignItems: "center", gap: 5 }}><Check size={11} /> {kw}</span>
                  )) : <span style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>{atsAnalysis?.has_resume ? "No keyword matches for this role." : "Activate a resume to see matches."}</span>}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: T.t3, fontFamily: F.sans, marginBottom: 10 }}>Missing</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
                  {visibleMissing.length ? visibleMissing.map(({ kw, impact }) => (
                    <span key={kw} style={{ fontSize: 11.5, padding: "5px 10px", borderRadius: 8, background: "var(--pu-148-163-184-005)", color: T.t2, border: `1px solid ${T.border}`, fontFamily: F.sans }}>{kw}<span style={{ marginLeft: 5, fontSize: 9.5, color: impact === "High" ? "var(--pu-ef4444-t)" : T.t3 }}>{impact}</span></span>
                  )) : <span style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>No gaps detected.</span>}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Advanced ATS breakdown + red flags */}
        {atsAnalysis?.breakdown && atsAnalysis.breakdown.length > 0 && (() => {
          const cmap: Record<string, string> = { success: "var(--pu-6ee7b7-b)", warning: "var(--pu-60a5fa-b)", danger: "var(--pu-ef4444-b)" };
          const scoreLabels: Record<string, string> = {
            technical_fit: "Technical fit",
            experience_fit: "Experience fit",
            ats_match: "ATS match",
            recruiter_interest: "Recruiter interest",
            interview_probability: "Interview probability",
          };
          const recruiterScores = Object.entries(atsAnalysis.recruiter_scores || {}).filter(([, value]) => typeof value === "number");
          return (
            <div style={{ background: "var(--pu-8-18-38-055)", backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 18, padding: isMobile ? 18 : 24 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
                <div>
                  <h3 style={{ fontFamily: F.sans, fontSize: 15, fontWeight: 800, color: T.text, margin: "0 0 4px" }}>ATS score breakdown</h3>
                  <div style={{ fontFamily: F.sans, fontSize: 12, color: T.t3 }}>{atsAnalysis.recommendation} · {atsAnalysis.coverage_pct ?? 0}% keyword coverage · {atsAnalysis.semantic_similarity ?? 0}% semantic</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontFamily: F.mono, fontSize: 26, fontWeight: 800, color: T.red, lineHeight: 1 }}>{atsAnalysis.score ?? 0}<span style={{ fontSize: 14, color: T.t3 }}>/100</span></div>
                  <div style={{ fontSize: 10, color: T.t3, fontFamily: F.sans }}>ATS score</div>
                </div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {atsAnalysis.breakdown.map((b) => (
                  <div key={b.label}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, fontFamily: F.sans, marginBottom: 5 }}>
                      <span style={{ color: T.t2 }}>{b.label}</span>
                      <span style={{ fontWeight: 700, color: cmap[b.color] || T.text }}>{b.score}/{b.max}</span>
                    </div>
                    <div style={{ height: 5, borderRadius: 999, background: "var(--pu-148-163-184-01)" }}>
                      <div style={{ height: 5, borderRadius: 999, width: `${Math.round((b.score / b.max) * 100)}%`, background: cmap[b.color] || T.red }} />
                    </div>
                  </div>
                ))}
              </div>
              {atsAnalysis.red_flags && atsAnalysis.red_flags.length > 0 && (
                <div style={{ marginTop: 18, paddingTop: 16, borderTop: `1px solid ${T.border}` }}>
                  <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--pu-60a5fa-t)", fontFamily: F.sans, marginBottom: 10 }}>Bullets to strengthen</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {atsAnalysis.red_flags.slice(0, 5).map((f, idx) => (
                      <div key={idx} style={{ border: `1px solid ${T.border}`, borderRadius: 12, background: "var(--pu-1-17-38-03)", padding: 12 }}>
                        <div style={{ fontSize: 9.5, fontWeight: 800, letterSpacing: "0.04em", textTransform: "uppercase", color: f.impact === "High" ? "var(--pu-ef4444-t)" : T.t3, fontFamily: F.sans, marginBottom: 6 }}>{f.category}{f.impact ? ` · ${f.impact}` : ""}</div>
                        <div style={{ fontSize: 12, color: T.t3, fontFamily: F.sans, lineHeight: 1.5, marginBottom: 6, textDecoration: "line-through", textDecorationColor: "var(--pu-239-68-68-05)" }}>{f.original}</div>
                        <div style={{ fontSize: 12, color: T.text, fontFamily: F.sans, lineHeight: 1.5, display: "flex", gap: 6 }}><span style={{ color: "var(--pu-6ee7b7-t)", flexShrink: 0 }}>→</span>{f.suggestion}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {(recruiterScores.length > 0 || (atsAnalysis.knockout_risks || []).length > 0 || (atsAnalysis.resume_improvements || []).length > 0) && (
                <div style={{ marginTop: 18, paddingTop: 16, borderTop: `1px solid ${T.border}`, display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 14 }}>
                  {recruiterScores.length > 0 && (
                    <div style={{ border: `1px solid ${T.border}`, borderRadius: 14, background: "var(--pu-1-17-38-028)", padding: 14 }}>
                      <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.06em", textTransform: "uppercase", color: T.text, fontFamily: F.sans, marginBottom: 10 }}>Recruiter review</div>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 9 }}>
                        {recruiterScores.map(([key, value]) => (
                          <div key={key} style={{ borderRadius: 10, background: "var(--pu-148-163-184-004)", border: `1px solid ${T.border}`, padding: 10 }}>
                            <div style={{ fontSize: 10.5, color: T.t3, fontFamily: F.sans, marginBottom: 4 }}>{scoreLabels[key] || key}</div>
                            <div style={{ fontSize: 18, fontWeight: 850, color: value >= 75 ? "var(--pu-6ee7b7-t)" : value >= 55 ? "var(--pu-60a5fa-t)" : "var(--pu-ef4444-t)", fontFamily: F.mono }}>{value}/100</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {(atsAnalysis.knockout_risks || []).length > 0 && (
                    <div style={{ border: `1px solid ${T.border}`, borderRadius: 14, background: "var(--pu-1-17-38-028)", padding: 14 }}>
                      <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.06em", textTransform: "uppercase", color: T.text, fontFamily: F.sans, marginBottom: 10 }}>Knockout risks</div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        {(atsAnalysis.knockout_risks || []).slice(0, 5).map((risk) => (
                          <div key={`${risk.label}-${risk.jd_signal}`} style={{ fontSize: 11.5, color: T.t2, fontFamily: F.sans, lineHeight: 1.45 }}>
                            <span style={{ color: risk.resume_evidence ? "var(--pu-6ee7b7-t)" : risk.impact === "High" ? "var(--pu-ef4444-t)" : "var(--pu-60a5fa-t)", fontWeight: 800 }}>{risk.label}</span>
                            <span style={{ color: T.t3 }}> · {risk.resume_evidence ? "evidence found" : "needs review"}</span>
                            <div style={{ color: T.t3 }}>{risk.guidance}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {(atsAnalysis.resume_improvements || []).length > 0 && (
                    <div style={{ gridColumn: "1 / -1", border: `1px solid ${T.border}`, borderRadius: 14, background: "var(--pu-1-17-38-028)", padding: 14 }}>
                      <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.06em", textTransform: "uppercase", color: T.text, fontFamily: F.sans, marginBottom: 10 }}>Resume improvements</div>
                      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 8 }}>
                        {(atsAnalysis.resume_improvements || []).slice(0, 6).map((item) => (
                          <div key={item} style={{ fontSize: 11.5, color: T.t2, fontFamily: F.sans, lineHeight: 1.45, display: "flex", gap: 7 }}>
                            <span style={{ color: "var(--pu-6ee7b7-t)", flexShrink: 0 }}>✓</span><span>{item}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })()}

        {/* Job description */}
        <div style={{ background: "var(--pu-8-18-38-055)", backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 18, padding: isMobile ? 18 : 24, overflow: "hidden" }}>
          <div style={{ display: "flex", alignItems: isMobile ? "flex-start" : "center", justifyContent: "space-between", gap: 12, flexDirection: isMobile ? "column" : "row", marginBottom: 16 }}>
            <h3 style={{ fontFamily: F.sans, fontSize: 16, fontWeight: 800, color: T.text, margin: 0 }}>Job description</h3>
            <div style={{ display: "flex", gap: 7, flexWrap: "wrap" }}>
              {jdSignals.map((signal) => (
                <span key={signal.label} style={{ padding: "6px 10px", borderRadius: 999, border: `1px solid ${T.border}`, background: "var(--pu-148-163-184-004)", fontFamily: F.sans }}>
                  <span style={{ fontSize: 10, color: T.t3, marginRight: 6 }}>{signal.label}</span>
                  <span style={{ fontSize: 11, fontWeight: 800, color: T.text }}>{signal.value}</span>
                </span>
              ))}
            </div>
          </div>
          {highlightCards.length > 0 && (
            <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : `repeat(${Math.min(highlightCards.length, 3)}, minmax(0, 1fr))`, gap: 12, marginBottom: 18 }}>
              {highlightCards.map((card) => (
                <div key={card.title} style={{ border: `1px solid ${T.border}`, borderRadius: 14, background: card.tone, padding: 14 }}>
                  <div style={{ fontFamily: F.sans, fontSize: 12, fontWeight: 800, color: T.text, marginBottom: 10 }}>{card.title}</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {card.items.slice(0, 4).map((item) => (
                      <div key={item} style={{ display: "grid", gridTemplateColumns: "16px minmax(0, 1fr)", gap: 8, alignItems: "start" }}>
                        <Check size={12} color={T.red} style={{ marginTop: 3 }} />
                        <span style={{ fontFamily: F.sans, fontSize: 12, lineHeight: 1.55, color: T.t2 }}>{item}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
          <div style={{ border: `1px solid ${T.border}`, borderRadius: 14, background: "var(--pu-1-17-38-022)", padding: isMobile ? 16 : 24 }}>
            {/* Both the sanitized-HTML and plain-text sources are routed through
                the same structured renderer so every JD reads as clean,
                titled sections instead of a wall of text — and we avoid
                dangerouslySetInnerHTML entirely (smaller XSS surface). */}
            {renderJobDescription(job?.description_html || descriptionText)}
          </div>
        </div>
      </div>

      {/* Context panels */}
      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "repeat(auto-fit, minmax(280px, 1fr))", gap: 14, alignItems: "stretch" }}>
        <div style={{ background: "var(--pu-8-18-38-055)", backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 18, padding: 20 }}>
          <h4 style={{ fontFamily: F.sans, fontSize: 13, fontWeight: 800, color: T.text, marginBottom: 14 }}>Posting snapshot</h4>
          {[
            { label: "Role", value: role || "Active", icon: Briefcase },
            { label: "Location", value: currentJob.location, icon: MapPin },
            { label: "Visa signals", value: (currentJob.visa ?? []).length ? `${(currentJob.visa ?? []).length} found` : "Not verified", icon: ShieldCheck },
            { label: "Source", value: currentJob.jobUrl ? "Company link" : "Search fallback", icon: Sparkles },
          ].map((item) => {
            const Icon = item.icon;
            return (
              <div key={item.label} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 0", borderBottom: `1px solid ${T.border}` }}>
                <div style={{ width: 28, height: 28, borderRadius: 8, background: "var(--pu-59-130-246-01)", border: "1px solid var(--pu-59-130-246-02)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <Icon size={13} color={T.red} />
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 10, color: T.t3, fontFamily: F.sans, textTransform: "uppercase", letterSpacing: "0.06em" }}>{item.label}</div>
                  <div style={{ fontSize: 12, color: T.t2, fontFamily: F.sans, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{item.value}</div>
                </div>
              </div>
            );
          })}
        </div>

        {(currentJob.visa.length > 0 || (currentJob.approvalRate != null && currentJob.petitions != null)) && <div style={{ background: "var(--pu-8-18-38-055)", backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 18, padding: 20 }}>
          <h4 style={{ fontFamily: F.sans, fontSize: 13, fontWeight: 700, color: T.text, marginBottom: 14 }}>Visa sponsorship info</h4>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
            {(currentJob.visa ?? []).map((v) => (
              <span key={v} style={{ fontSize: 11, fontWeight: 700, padding: "4px 10px", borderRadius: 999, background: "var(--pu-52-211-153-012)", color: "var(--pu-6ee7b7-t)", border: "1px solid var(--pu-52-211-153-03)", fontFamily: F.sans }}>{v}</span>
            ))}
          </div>
          {currentJob.approvalRate != null && currentJob.petitions != null && <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ position: "relative", width: 60, height: 60 }}>
              <svg viewBox="0 0 60 60" style={{ transform: "rotate(-90deg)", width: "100%", height: "100%" }}>
                <circle cx="30" cy="30" r="24" fill="none" stroke="var(--pu-148-163-184-007)" strokeWidth="6" />
                <motion.circle cx="30" cy="30" r="24" fill="none" stroke={T.red} strokeWidth="6" strokeLinecap="round"
                  strokeDasharray={2 * Math.PI * 24}
                  initial={{ strokeDashoffset: 2 * Math.PI * 24 }}
                  animate={{ strokeDashoffset: 2 * Math.PI * 24 * (1 - currentJob.approvalRate / 100) }}
                  transition={{ duration: 1.4, ease: "easeOut" }}
                />
              </svg>
              <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <span style={{ fontFamily: F.mono, fontSize: 11, fontWeight: 500, color: T.red }}>{currentJob.approvalRate}%</span>
              </div>
            </div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: T.text, fontFamily: F.sans }}>{currentJob.approvalRate}% approval rate</div>
              <div style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>Last year: {currentJob.petitions.toLocaleString()} petitions</div>
            </div>
          </div>}
        </div>}

        {(currentJob.benefits ?? []).length > 0 && <div style={{ background: "var(--pu-8-18-38-055)", backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 18, padding: 20 }}>
          <h4 style={{ fontFamily: F.sans, fontSize: 13, fontWeight: 700, color: T.text, marginBottom: 12 }}>Benefits & perks</h4>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {(currentJob.benefits ?? []).map((b) => (
              <div key={b} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ width: 20, height: 20, borderRadius: "50%", background: "var(--pu-59-130-246-012)", border: "1px solid var(--pu-59-130-246-025)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <Check size={10} color={T.red} />
                </div>
                <span style={{ fontSize: 13, color: T.t2, fontFamily: F.sans }}>{b}</span>
              </div>
            ))}
          </div>
        </div>}
      </div>

      {/* Apply Modal */}
      <AnimatePresence>
        {showApplyModal && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            style={{ position: "fixed", inset: 0, background: "var(--pu-1-17-38-085)", backdropFilter: "blur(8px)", zIndex: 200, display: "flex", alignItems: "center", justifyContent: "center" }}
            onClick={() => setShowApplyModal(false)}
          >
            <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.9, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              style={{
                width: "min(460px, calc(100vw - 24px))",
                maxHeight: "85vh",
                overflowY: "auto",
                background: "var(--pu-15-30-55-09)",
                backdropFilter: "blur(24px)",
                border: "1px solid var(--pu-148-163-184-01)",
                borderRadius: 24,
                padding: isMobile ? "24px 20px" : "36px 32px",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
                <h3 style={{ fontFamily: F.sans, fontSize: 18, fontWeight: 600, color: T.text }}>Application Tracker</h3>
                <button onClick={() => setShowApplyModal(false)} style={{ background: "none", border: "none", cursor: "pointer", color: T.t3 }}><X size={18} /></button>
              </div>
              <div style={{ fontSize: 14, color: T.t2, fontFamily: F.sans, marginBottom: 20 }}>
                <strong style={{ color: T.text }}>{currentJob.title}</strong> at <strong style={{ color: T.text }}>{currentJob.company}</strong> opened in a new tab.
              </div>

              <div style={{ fontSize: 13, fontWeight: 600, color: T.text, fontFamily: F.sans, marginBottom: 10 }}>Did you complete the application?</div>

              <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 20 }}>
                <button disabled={savingApplication} onClick={() => recordApplication("applied")} style={{ flex: "1 1 180px", padding: "13px", borderRadius: 12, border: "none", background: T.grad, color: "var(--pu-ffffff-t)", fontSize: 14, fontWeight: 600, fontFamily: F.sans, cursor: "pointer" }}>
                  Yes, I applied
                </button>
                <button disabled={savingApplication} onClick={() => recordApplication("not_applied", "will_apply_later")} style={{ flex: "1 1 180px", padding: "13px", borderRadius: 12, border: `1px solid ${T.border}`, background: "transparent", color: T.t2, fontSize: 14, fontFamily: F.sans, cursor: "pointer" }}>
                  Will apply later
                </button>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
                <label style={{ display: "flex", flexDirection: "column", gap: 6, fontFamily: F.sans }}>
                  <span style={{ fontSize: 12, fontWeight: 600, color: T.t3 }}>Did you hear back?</span>
                  <select
                    value={heardBack}
                    onChange={(e) => setHeardBack(e.target.value as "unknown" | "yes" | "no")}
                    style={{ height: 38, borderRadius: 10, border: `1px solid ${T.border}`, background: "var(--pu-148-163-184-004)", color: T.text, fontSize: 13, fontFamily: F.sans, padding: "0 10px", outline: "none" }}
                  >
                    <option value="unknown">Not yet</option>
                    <option value="yes">Yes</option>
                    <option value="no">No</option>
                  </select>
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: 6, fontFamily: F.sans }}>
                  <span style={{ fontSize: 12, fontWeight: 600, color: T.t3 }}>Was it still open?</span>
                  <select
                    value={positionOpen}
                    onChange={(e) => setPositionOpen(e.target.value as "unknown" | "yes" | "no")}
                    style={{ height: 38, borderRadius: 10, border: `1px solid ${T.border}`, background: "var(--pu-148-163-184-004)", color: T.text, fontSize: 13, fontFamily: F.sans, padding: "0 10px", outline: "none" }}
                  >
                    <option value="unknown">Unknown</option>
                    <option value="yes">Yes</option>
                    <option value="no">No</option>
                  </select>
                </label>
              </div>

              <div style={{ fontSize: 12, fontWeight: 600, color: T.t3, fontFamily: F.sans, marginBottom: 8, letterSpacing: "0.04em", textTransform: "uppercase" }}>Salary info (optional)</div>
              <input
                value={salaryOffered}
                onChange={(e) => setSalaryOffered(e.target.value)}
                placeholder="Example: $140K-$165K base, bonus, equity..."
                style={{
                  width: "100%", height: 40, padding: "0 12px", borderRadius: 12,
                  border: `1px solid ${T.border}`, background: "var(--pu-148-163-184-004)",
                  color: T.text, fontSize: 13, fontFamily: F.sans, outline: "none",
                  boxSizing: "border-box", marginBottom: 16,
                }}
              />

              <div style={{ fontSize: 12, fontWeight: 600, color: T.t3, fontFamily: F.sans, marginBottom: 8, letterSpacing: "0.04em", textTransform: "uppercase" }}>Notes (optional)</div>
              <textarea
                placeholder="Salary range mentioned, interview timeline, referral contact, or anything else..."
                value={applyNotes}
                onChange={(e) => setApplyNotes(e.target.value)}
                style={{
                  width: "100%", minHeight: 72, padding: "12px 14px", borderRadius: 12,
                  border: `1px solid ${T.border}`, background: "var(--pu-148-163-184-004)",
                  color: T.text, fontSize: 13, fontFamily: F.sans, resize: "vertical",
                  outline: "none", boxSizing: "border-box",
                }}
              />

              <div style={{ marginTop: 18, paddingTop: 16, borderTop: `1px solid ${T.border}` }}>
                <div style={{ fontSize: 12, color: T.t3, fontFamily: F.sans, marginBottom: 10 }}>Or mark as skipped:</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button disabled={savingApplication} onClick={() => recordApplication("not_applied", "not_interested")} style={{ padding: "9px 14px", borderRadius: 10, border: `1px solid ${T.border}`, background: "transparent", color: T.t3, fontSize: 12, fontFamily: F.sans, cursor: "pointer" }}>
                    Not interested
                  </button>
                  <button disabled={savingApplication} onClick={() => recordApplication("not_applied", "position_closed")} style={{ padding: "9px 14px", borderRadius: 10, border: `1px solid ${T.border}`, background: "transparent", color: T.t3, fontSize: 12, fontFamily: F.sans, cursor: "pointer" }}>
                    Position closed
                  </button>
                  <button disabled={savingApplication} onClick={() => recordApplication("not_applied", "requirements_mismatch")} style={{ padding: "9px 14px", borderRadius: 10, border: `1px solid ${T.border}`, background: "transparent", color: T.t3, fontSize: 12, fontFamily: F.sans, cursor: "pointer" }}>
                    Requirements mismatch
                  </button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
