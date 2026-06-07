import { useState, useEffect, type ReactNode } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ArrowLeft, MapPin, DollarSign, ExternalLink, Bookmark, Share2, Check, X, ShieldCheck, Sparkles, Briefcase } from "lucide-react";
import * as api from "../../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  text: "#F2EEB3", t2: "rgba(242,238,179,0.65)", t3: "rgba(242,238,179,0.45)",
  border: "rgba(242,238,179,0.08)", glass: "rgba(64,18,18,0.55)",
  grad: "linear-gradient(135deg, #F2A341, #ED7D2B, #C75A12)",
  red: "#ED7D2B", burnt: "#F2A341", dark: "#C75A12",
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
  const color = !hasScore ? T.t3 : safeScore >= 80 ? "#22c55e" : safeScore >= 60 ? T.red : safeScore >= 40 ? T.burnt : "#F2EEB3";
  const textColor = safeScore >= 40 ? color : "#F2EEB3";
  return (
    <div style={{ position: "relative", width: 120, height: 120 }}>
      <svg viewBox="0 0 120 120" style={{ width: "100%", height: "100%", transform: "rotate(-90deg)" }}>
        <defs>
          <filter id="jd-glow"><feGaussianBlur stdDeviation="3" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
        </defs>
        <circle cx="60" cy="60" r={r} fill="none" stroke="rgba(242,238,179,0.12)" strokeWidth="9" />
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

function getScoreMeta(score: number | null | undefined) {
  if (typeof score !== "number" || !Number.isFinite(score)) {
    return {
      label: "Resume match unavailable",
      detail: "Upload or activate a resume to calculate a real score.",
      color: T.t3,
      bg: "rgba(242,238,179,0.05)",
      border: T.border,
    };
  }
  if (score >= 80) return { label: "Strong match", detail: "This role lines up well with your active resume.", color: "#22c55e", bg: "rgba(34,197,94,0.10)", border: "rgba(34,197,94,0.25)" };
  if (score >= 60) return { label: "Good match", detail: "A few resume keyword updates could improve your odds.", color: T.red, bg: "rgba(237,125,43,0.12)", border: "rgba(237,125,43,0.28)" };
  if (score >= 40) return { label: "Partial match", detail: "Review requirements before applying.", color: T.burnt, bg: "rgba(140,58,39,0.12)", border: "rgba(140,58,39,0.28)" };
  return { label: "Low match", detail: "This posting appears far from your active resume.", color: "#F2EEB3", bg: "rgba(242,238,179,0.06)", border: "rgba(242,238,179,0.12)" };
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
      parts.push(<code key={k++} style={{ fontSize: 12, background: "rgba(242,238,179,0.08)", padding: "1px 5px", borderRadius: 4, fontFamily: F.mono }}>{tok.slice(1, -1)}</code>);
    last = m.index + tok.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts.length === 1 && typeof parts[0] === "string" ? parts[0] : <>{parts}</>;
}

function renderJobDescription(raw: string): ReactNode {
  if (!raw?.trim()) return <span style={{ color: T.t3, fontFamily: F.sans, fontSize: 13 }}>Open the original posting for full details.</span>;

  // Decode HTML entities and convert block tags to newlines before stripping
  const ta = document.createElement("textarea");
  ta.innerHTML = raw;
  let text = ta.value;
  text = text.replace(/<br\s*\/?>/gi, "\n");
  text = text.replace(/<\/?(p|div|li|ul|ol|h[1-6]|section)\b[^>]*>/gi, "\n");
  text = text.replace(/<[^>]+>/g, "");

  // Normalize: collapse horizontal whitespace only; preserve line breaks
  const lines = text.split("\n").map((l) => l.replace(/[ \t]+/g, " ").trim());

  const blocks: ReactNode[] = [];
  let listItems: string[] = [];
  let listKey = 0;

  const flushList = () => {
    if (!listItems.length) return;
    blocks.push(
      <ul key={`ul-${listKey++}`} style={{ margin: "4px 0 10px", paddingLeft: 20, display: "flex", flexDirection: "column", gap: 3 }}>
        {listItems.map((item, j) => (
          <li key={j} style={{ fontSize: 13, color: T.t2, fontFamily: F.sans, lineHeight: 1.65 }}>{renderInline(item)}</li>
        ))}
      </ul>
    );
    listItems = [];
  };

  lines.forEach((line, i) => {
    if (!line) { flushList(); return; }

    // ## or # heading
    const h1m = line.match(/^#{1,2}\s+(.*)/);
    if (h1m) {
      flushList();
      blocks.push(<div key={`h1-${i}`} style={{ fontSize: 14, fontWeight: 700, color: T.text, fontFamily: F.sans, marginTop: 18, marginBottom: 6, paddingBottom: 4, borderBottom: `1px solid ${T.border}` }}>{h1m[1].replace(/\*\*/g, "")}</div>);
      return;
    }
    // ### sub-heading
    const h2m = line.match(/^#{3,6}\s+(.*)/);
    if (h2m) {
      flushList();
      blocks.push(<div key={`h2-${i}`} style={{ fontSize: 13, fontWeight: 600, color: T.t2, fontFamily: F.sans, marginTop: 14, marginBottom: 4 }}>{h2m[1].replace(/\*\*/g, "")}</div>);
      return;
    }
    // Standalone **Section Heading** or **Section Heading:**
    if (/^\*\*[^*]+\*\*:?\s*$/.test(line)) {
      flushList();
      blocks.push(<div key={`bh-${i}`} style={{ fontSize: 14, fontWeight: 700, color: T.text, fontFamily: F.sans, marginTop: 18, marginBottom: 6, paddingBottom: 4, borderBottom: `1px solid ${T.border}` }}>{line.replace(/\*\*/g, "").replace(/:$/, "").trim()}</div>);
      return;
    }
    // Bullet / numbered list item
    const bm = line.match(/^(?:[*\-•·]|\d+[.)]) +(.*)/);
    if (bm) { listItems.push(bm[1]); return; }

    // Regular paragraph
    flushList();
    blocks.push(<p key={`p-${i}`} style={{ fontSize: 13, color: T.t2, fontFamily: F.sans, lineHeight: 1.75, margin: "4px 0" }}>{renderInline(line)}</p>);
  });

  flushList();
  return <>{blocks}</>;
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

  // Look across every URL field the backend may expose so the Apply button
  // works regardless of which scraper sourced the job.
  const resolvedJobUrl = (() => {
    const j: any = job ?? {};
    const candidates = [
      j.job_url,
      j.source_url,
      j.job_url_direct,
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
    strongKeywords: job?.strongKeywords ?? [],
    missingKeywords: Array.isArray(job?.missingKeywords) ? (job?.missingKeywords as any) : [],
    benefits: job?.benefits ?? [],
    approvalRate: job?.approvalRate ?? 0,
    petitions: job?.petitions ?? 0,
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
    return <div style={{ color: "#F2EEB3", fontFamily: F.sans, fontSize: 14 }}>Loading job details...</div>;
  }

  if (error) {
    return <div style={{ color: "#ff7f7f", fontFamily: F.sans, fontSize: 14 }}>{error}</div>;
  }

  const visaBadge: Record<string, { bg: string; color: string; border: string }> = {
    "H-1B":    { bg: "rgba(140,58,39,0.15)", color: T.burnt,  border: "rgba(140,58,39,0.35)" },
    "F1-OPT":  { bg: "rgba(237,125,43,0.12)", color: T.red,    border: "rgba(237,125,43,0.3)" },
    "F1-STEM": { bg: "rgba(64,18,18,0.15)",  color: T.red,    border: "rgba(64,18,18,0.3)" },
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
  const scoreMeta = getScoreMeta(currentJob.match);
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
    { title: "What you'll do", items: responsibilityHighlights, tone: "rgba(237,125,43,0.10)" },
    { title: "What they need", items: requirementHighlights, tone: "rgba(242,238,179,0.06)" },
    { title: "Standout signals", items: niceHighlights.length ? niceHighlights : visibleMissing.slice(0, 3).map((item) => `${item.kw} (${item.impact})`), tone: "rgba(140,58,39,0.13)" },
  ].filter((card) => card.items.length);

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: isTablet ? "1fr" : "1.8fr 1fr",
        gap: isMobile ? 14 : 20,
      }}
    >
      {/* MAIN */}
      <div style={{ display: "flex", flexDirection: "column", gap: 16, minWidth: 0 }}>
        {/* Back */}
        <button onClick={onBack} style={{ display: "flex", alignItems: "center", gap: 6, background: "none", border: "none", cursor: "pointer", color: T.t2, fontSize: 13, fontFamily: F.sans, width: "fit-content" }}>
          <ArrowLeft size={14} /> All Jobs
        </button>

        {/* Header card */}
        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: isMobile ? 16 : 24 }}>
          <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "minmax(0, 1fr) 170px", gap: 18, alignItems: "start", marginBottom: 18 }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap", marginBottom: 7 }}>
                  <span style={{ fontSize: 10, fontWeight: 700, padding: "4px 8px", borderRadius: 999, background: "rgba(242,238,179,0.05)", color: T.t2, border: `1px solid ${T.border}`, fontFamily: F.sans }}>{role}</span>
                  <span style={{ fontSize: 10, fontWeight: 700, padding: "4px 8px", borderRadius: 999, background: scoreMeta.bg, color: scoreMeta.color, border: `1px solid ${scoreMeta.border}`, fontFamily: F.sans }}>{scoreMeta.label}</span>
                </div>
                <h2 style={{ fontFamily: F.sans, fontSize: 22, fontWeight: 700, color: T.text, marginBottom: 4, lineHeight: 1.2 }}>{currentJob.title}</h2>
                <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                  <span style={{ fontSize: 14, color: T.t2, fontFamily: F.sans, fontWeight: 500 }}>{currentJob.company}</span>
                  <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 13, color: T.t3, fontFamily: F.sans }}><MapPin size={12} />{currentJob.location}</span>
                  <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 13, color: T.t3, fontFamily: F.sans }}><DollarSign size={12} />{currentJob.salary}</span>
                  <span style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>{currentJob.posted}</span>
                </div>
              </div>
            </div>
            <div style={{ borderRadius: 16, border: `1px solid ${scoreMeta.border}`, background: scoreMeta.bg, padding: 12, display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
              <ATSRingLarge score={currentJob.match} />
              <div style={{ textAlign: "center", fontSize: 11, color: T.t3, fontFamily: F.sans, lineHeight: 1.4 }}>{scoreMeta.detail}</div>
            </div>
          </div>

          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 16 }}>
            {(currentJob.visa ?? []).map((v) => {
              const s = visaBadge[v] ?? { bg: "rgba(64,18,18,0.1)", color: T.t2, border: T.border };
              return <span key={v} style={{ fontSize: 10, fontWeight: 700, padding: "3px 9px", borderRadius: 4, background: s.bg, color: s.color, border: `1px solid ${s.border}`, fontFamily: F.sans, letterSpacing: "0.04em" }}>{v}</span>;
            })}
            {applied && <span style={{ fontSize: 10, fontWeight: 700, padding: "3px 9px", borderRadius: 4, background: "rgba(34,197,94,0.1)", color: "#22c55e", border: "1px solid rgba(34,197,94,0.25)", fontFamily: F.sans }}>✓ Applied</span>}
          </div>

          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button
              type="button"
              onClick={openCompanyApply}
              title={currentJob.jobUrl ? currentJob.jobUrl : "Open a Google search for this role"}
              style={{
                display: "flex", alignItems: "center", gap: 6, padding: "11px 20px",
                borderRadius: 10, border: "none", background: T.grad, color: "#fff",
                fontSize: 13, fontWeight: 600, fontFamily: F.sans, cursor: "pointer",
                boxShadow: "0 0 20px rgba(237,125,43,0.35)",
              }}
            >
              <ExternalLink size={14} /> Apply on Company Website
            </button>
            <button
              type="button"
              onClick={toggleSave}
              style={{
                display: "flex", alignItems: "center", gap: 6, padding: "11px 16px",
                borderRadius: 10,
                border: `1px solid ${saved ? "rgba(237,125,43,0.35)" : T.border}`,
                background: saved ? "rgba(237,125,43,0.10)" : "transparent",
                color: saved ? T.red : T.t2,
                fontSize: 13, fontFamily: F.sans, cursor: "pointer",
              }}
            >
              <Bookmark size={14} fill={saved ? T.red : "none"} /> {saved ? "Saved" : "Save"}
            </button>
            <button
              type="button"
              onClick={shareJob}
              style={{
                display: "flex", alignItems: "center", gap: 6, padding: "11px 16px",
                borderRadius: 10, border: `1px solid ${T.border}`, background: "transparent",
                color: copied ? T.red : T.t2, fontSize: 13, fontFamily: F.sans, cursor: "pointer",
              }}
            >
              <Share2 size={14} /> {copied ? "Copied!" : "Share"}
            </button>
          </div>
        </div>

        {/* ATS Breakdown */}
        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: 24 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 18 }}>
            <div>
              <h3 style={{ fontFamily: F.sans, fontSize: 15, fontWeight: 700, color: T.text, marginBottom: 4 }}>Resume Match Breakdown</h3>
              <div style={{ fontFamily: F.sans, fontSize: 12, color: T.t3 }}>{currentJob.match == null ? "A score appears after a resume is active." : "Based on overlap between your active resume and this posting."}</div>
            </div>
            <div style={{ fontFamily: F.mono, fontSize: 22, fontWeight: 700, color: scoreMeta.color }}>{typeof currentJob.match === "number" ? `${currentJob.match}%` : "--"}</div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: T.t3, fontFamily: F.sans, marginBottom: 10 }}>Strong Keywords ✓</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {visibleKeywords.map((kw) => (
                  <span key={kw} style={{ fontSize: 11, padding: "4px 9px", borderRadius: 4, background: "rgba(237,125,43,0.1)", color: T.red, border: "1px solid rgba(237,125,43,0.25)", fontFamily: F.sans, display: "flex", alignItems: "center", gap: 4 }}>
                    <Check size={9} /> {kw}
                  </span>
                ))}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: T.t3, fontFamily: F.sans, marginBottom: 10 }}>Missing Keywords ✗</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {visibleMissing.map(({ kw, impact }) => (
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
        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: isMobile ? 16 : 24, overflow: "hidden" }}>
          <div style={{ display: "flex", alignItems: isMobile ? "flex-start" : "center", justifyContent: "space-between", gap: 12, flexDirection: isMobile ? "column" : "row", marginBottom: 18 }}>
            <div>
              <div style={{ fontFamily: F.sans, fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase", color: T.t3, marginBottom: 6 }}>Full posting</div>
              <h3 style={{ fontFamily: F.sans, fontSize: 18, fontWeight: 800, color: T.text, margin: 0 }}>Job Description</h3>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {jdSignals.map((signal) => (
                <div key={signal.label} style={{ padding: "7px 10px", borderRadius: 999, border: `1px solid ${T.border}`, background: "rgba(242,238,179,0.04)", fontFamily: F.sans }}>
                  <span style={{ fontSize: 10, color: T.t3, marginRight: 6 }}>{signal.label}</span>
                  <span style={{ fontSize: 11, fontWeight: 800, color: T.text }}>{signal.value}</span>
                </div>
              ))}
            </div>
          </div>

          {highlightCards.length > 0 && (
            <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : `repeat(${Math.min(highlightCards.length, 3)}, minmax(0, 1fr))`, gap: 12, marginBottom: 18 }}>
              {highlightCards.map((card) => (
                <div key={card.title} style={{ border: `1px solid ${T.border}`, borderRadius: 16, background: card.tone, padding: 14 }}>
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

          <div style={{ border: `1px solid ${T.border}`, borderRadius: 18, background: "rgba(1,17,38,0.22)", padding: isMobile ? 14 : 20 }}>
            {renderJobDescription(descriptionText)}
          </div>
        </div>
      </div>

      {/* SIDEBAR */}
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: 20 }}>
          <h4 style={{ fontFamily: F.sans, fontSize: 13, fontWeight: 700, color: T.text, marginBottom: 14 }}>Posting Snapshot</h4>
          {[
            { label: "Role", value: role || "Active", icon: Briefcase },
            { label: "Location", value: currentJob.location, icon: MapPin },
            { label: "Visa signals", value: (currentJob.visa ?? []).length ? `${(currentJob.visa ?? []).length} found` : "Not verified", icon: ShieldCheck },
            { label: "Source", value: currentJob.jobUrl ? "Company link" : "Search fallback", icon: Sparkles },
          ].map((item) => {
            const Icon = item.icon;
            return (
              <div key={item.label} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 0", borderBottom: `1px solid ${T.border}` }}>
                <div style={{ width: 28, height: 28, borderRadius: 8, background: "rgba(237,125,43,0.10)", border: "1px solid rgba(237,125,43,0.20)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
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

        {/* Visa Info */}
        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: 20 }}>
          <h4 style={{ fontFamily: F.sans, fontSize: 13, fontWeight: 600, color: T.text, marginBottom: 14 }}>Visa Sponsorship Info</h4>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
            {(currentJob.visa ?? []).map((v) => {
              const s = { "H-1B": { bg: "rgba(140,58,39,0.15)", color: T.burnt, border: "rgba(140,58,39,0.35)" }, "F1-OPT": { bg: "rgba(237,125,43,0.12)", color: T.red, border: "rgba(237,125,43,0.3)" } }[v] ?? { bg: "rgba(64,18,18,0.1)", color: T.t2, border: T.border };
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
          </div>
        </div>

        {/* Benefits */}
        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: 20 }}>
          <h4 style={{ fontFamily: F.sans, fontSize: 13, fontWeight: 600, color: T.text, marginBottom: 12 }}>Benefits & Perks</h4>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {(currentJob.benefits ?? []).map((b) => (
              <div key={b} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ width: 20, height: 20, borderRadius: "50%", background: "rgba(237,125,43,0.12)", border: "1px solid rgba(237,125,43,0.25)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
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
              style={{
                width: "min(460px, calc(100vw - 24px))",
                maxHeight: "85vh",
                overflowY: "auto",
                background: "rgba(64,18,18,0.9)",
                backdropFilter: "blur(24px)",
                border: "1px solid rgba(242,238,179,0.1)",
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

              {/* Follow-up question */}
              <div style={{ fontSize: 13, fontWeight: 600, color: T.text, fontFamily: F.sans, marginBottom: 10 }}>Did you complete the application?</div>

              <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 20 }}>
                <button disabled={savingApplication} onClick={() => recordApplication("applied")} style={{ flex: "1 1 180px", padding: "13px", borderRadius: 12, border: "none", background: T.grad, color: "#fff", fontSize: 14, fontWeight: 600, fontFamily: F.sans, cursor: "pointer" }}>
                  Yes, I Applied! 🎉
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
                    style={{ height: 38, borderRadius: 10, border: `1px solid ${T.border}`, background: "rgba(242,238,179,0.04)", color: T.text, fontSize: 13, fontFamily: F.sans, padding: "0 10px", outline: "none" }}
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
                    style={{ height: 38, borderRadius: 10, border: `1px solid ${T.border}`, background: "rgba(242,238,179,0.04)", color: T.text, fontSize: 13, fontFamily: F.sans, padding: "0 10px", outline: "none" }}
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
                  border: `1px solid ${T.border}`, background: "rgba(242,238,179,0.04)",
                  color: T.text, fontSize: 13, fontFamily: F.sans, outline: "none",
                  boxSizing: "border-box", marginBottom: 16,
                }}
              />

              {/* Notes section */}
              <div style={{ fontSize: 12, fontWeight: 600, color: T.t3, fontFamily: F.sans, marginBottom: 8, letterSpacing: "0.04em", textTransform: "uppercase" }}>Notes (optional)</div>
              <textarea
                placeholder="Salary range mentioned, interview timeline, referral contact, or anything else..."
                value={applyNotes}
                onChange={(e) => setApplyNotes(e.target.value)}
                style={{
                  width: "100%", minHeight: 72, padding: "12px 14px", borderRadius: 12,
                  border: `1px solid ${T.border}`, background: "rgba(242,238,179,0.04)",
                  color: T.text, fontSize: 13, fontFamily: F.sans, resize: "vertical",
                  outline: "none", boxSizing: "border-box",
                }}
              />

              {/* Why not */}
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
