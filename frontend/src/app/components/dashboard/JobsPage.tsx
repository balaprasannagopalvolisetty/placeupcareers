import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import { Search, Filter, X, MapPin, DollarSign, Clock, Bookmark, ExternalLink, Flame, Briefcase, ShieldCheck, Sparkles, RefreshCw } from "lucide-react";
import * as api from "../../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  text: "#F2EEB3", t2: "rgba(242,238,179,0.65)", t3: "rgba(242,238,179,0.45)",
  border: "rgba(242,238,179,0.08)", glass: "rgba(64,18,18,0.55)",
  grad: "linear-gradient(135deg, #8C3A27, #A6372D, #401212)",
  red: "#A6372D", burnt: "#8C3A27", dark: "#401212",
};

const STATUS_CHIPS = ["All", "New", "Applied", "Interview", "Saved"];
const TIME_CHIPS = [
  { label: "Any time", value: "" },
  { label: "Today", value: "today" },
  { label: "Yesterday", value: "yesterday" },
  { label: "Week", value: "week" },
  { label: "Month", value: "month" },
];
const VISA_BADGES: Record<string, { bg: string; color: string; border: string }> = {
  "H-1B":   { bg: "rgba(140,58,39,0.15)", color: "#8C3A27", border: "rgba(140,58,39,0.35)" },
  "OPT":    { bg: "rgba(166,55,45,0.12)", color: "#A6372D", border: "rgba(166,55,45,0.3)" },
  "STEM":   { bg: "rgba(64,18,18,0.15)",  color: "#A6372D", border: "rgba(64,18,18,0.3)" },
  "Vol":    { bg: "rgba(34,197,94,0.10)", color: "#22c55e", border: "rgba(34,197,94,0.3)" },
  "No sponsorship": { bg: "rgba(242,238,179,0.06)", color: "rgba(242,238,179,0.65)", border: "rgba(242,238,179,0.14)" },
};

function normalizeVisa(visa: unknown): string[] {
  if (Array.isArray(visa)) return visa.filter((v): v is string => typeof v === "string");
  if (visa && typeof visa === "object") {
    const map: Record<string, string> = {
      visa_h1b: "H-1B", visa_opt: "OPT", visa_stem_opt: "STEM",
      h1b_verified: "H-1B Verified", green_card: "Green Card",
      no_sponsorship: "No sponsorship",
    };
    return Object.entries(visa as Record<string, unknown>)
      .filter(([key, value]) => key !== "visa_score" && Boolean(value))
      .map(([key]) => map[key] ?? key.replace(/_/g, " "));
  }
  if (typeof visa === "string") return visa.split(",").map((s) => s.trim()).filter(Boolean);
  return [];
}

function formatSalary(salary: unknown): string {
  if (!salary) return "—";
  if (typeof salary === "string") return salary;
  if (typeof salary === "object") {
    const min = (salary as any).min_salary, max = (salary as any).max_salary;
    if (typeof min === "number" && typeof max === "number") return `$${Math.round(min/1000)}K–$${Math.round(max/1000)}K`;
    if (typeof min === "number") return `$${Math.round(min/1000)}K+`;
    if (typeof max === "number") return `Up to $${Math.round(max/1000)}K`;
    if ((salary as any).display) return String((salary as any).display);
  }
  return "—";
}

interface TaxonomyRole { name: string; synonyms: string[]; visa: string[]; hot: boolean }
interface TaxonomyCategory { name: string; icon: string; roles: TaxonomyRole[] }

const JOB_FETCH_RETRY_MS = 700;
const JOB_FETCH_TIMEOUT_MS = 30000;

function useResponsiveFlags() {
  const getWidth = () => (typeof window === "undefined" ? 1280 : window.innerWidth);
  const [width, setWidth] = useState(getWidth);

  useEffect(() => {
    const onResize = () => setWidth(getWidth());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return { width, isMobile: width < 640, isTablet: width < 1024 };
}

function friendlyJobError(err: unknown): string {
  const message = (err as Error)?.message || "Could not load jobs";
  if (message.toLowerCase().includes("failed to fetch")) {
    return "Network hiccup while loading jobs. Please retry, or refresh if this keeps happening.";
  }
  return message;
}

async function getJobsWithRetry(params: Record<string, string | number | boolean>, attempts = 2) {
  let lastError: unknown;
  for (let i = 0; i < attempts; i += 1) {
    try {
      const controller = new AbortController();
      const timeoutId = window.setTimeout(() => controller.abort(), JOB_FETCH_TIMEOUT_MS);
      try {
        const result = await api.getJobs(params, { signal: controller.signal });
        return result;
      } finally {
        window.clearTimeout(timeoutId);
      }
    } catch (err) {
      lastError = err;
      if (i < attempts - 1) {
        await new Promise((resolve) => window.setTimeout(resolve, JOB_FETCH_RETRY_MS * Math.pow(2, i)));
      }
    }
  }
  throw lastError;
}

function decodeHtml(value: string): string {
  const el = document.createElement("textarea");
  el.innerHTML = value;
  return el.value;
}

function cleanPreview(value: unknown): string {
  if (typeof value !== "string") return "";
  return decodeHtml(value).replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

function formatPosted(value: unknown): string {
  if (!value) return "Recently";
  const raw = String(value);
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw.length > 18 ? raw.slice(0, 18) : raw;
  const days = Math.max(0, Math.floor((Date.now() - date.getTime()) / 86400000));
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 30) return `${days} days ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function resolveJobUrl(job: api.JobPost): string {
  const j: any = job;
  const candidates = [j.job_url, j.source_url, j.job_url_direct, j.apply_url, j.url, j.company_url, j.external_url];
  const first = candidates.find((url) => typeof url === "string" && url.trim().length > 0);
  if (!first) return "";
  const trimmed = String(first).trim();
  return /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
}

// ─── localStorage tracking helpers ───────────────────────────────────────────

function getSavedIds(): Set<string> {
  try {
    const s = JSON.parse(localStorage.getItem("placeup_saved_jobs") || "[]");
    return new Set<string>(Array.isArray(s) ? s.map(String) : []);
  } catch { return new Set<string>(); }
}

function getTrackedJobs(): Record<string, "applied" | "interview"> {
  try {
    return JSON.parse(localStorage.getItem("placeup_job_tracking") || "{}") as Record<string, "applied" | "interview">;
  } catch { return {}; }
}

function ATSRing({ score, size = 60 }: { score: number | null | undefined; size?: number }) {
  const hasScore = typeof score === "number" && Number.isFinite(score);
  const safeScore = hasScore ? Math.max(0, Math.min(100, score)) : 0;
  const r = (size/2) - 5, circ = 2*Math.PI*r;
  const offset = circ * (1 - safeScore/100);
  // Avoid T.dark (#401212) for the ring — it blends into the card background.
  const color = !hasScore ? T.t3 : safeScore >= 80 ? "#22c55e" : safeScore >= 60 ? T.red : safeScore >= 40 ? T.burnt : "#F2EEB3";
  const textColor = safeScore >= 40 ? color : "#F2EEB3";
  return (
    <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
      <svg viewBox={`0 0 ${size} ${size}`} style={{ width: "100%", height: "100%", transform: "rotate(-90deg)" }}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="rgba(242,238,179,0.14)" strokeWidth="5" />
        <motion.circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth="5" strokeLinecap="round"
          strokeDasharray={circ} initial={{ strokeDashoffset: circ }} animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1.2, ease: "easeOut" }} />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <span style={{ fontFamily: F.mono, fontSize: hasScore ? 13 : 11, fontWeight: 600, color: textColor }}>{hasScore ? safeScore : "--"}</span>
        <span style={{ fontSize: 7, color: T.t2, fontFamily: F.sans, letterSpacing: "0.05em" }}>{hasScore ? "ATS" : "Resume"}</span>
      </div>
    </div>
  );
}

function getScoreMeta(score: number | null | undefined) {
  if (typeof score !== "number" || !Number.isFinite(score)) {
    return {
      label: "Resume needed",
      detail: "Upload resume for score",
      color: T.t3,
      bg: "rgba(242,238,179,0.05)",
      border: T.border,
    };
  }
  if (score >= 80) return { label: "Strong match", detail: "High keyword overlap", color: "#22c55e", bg: "rgba(34,197,94,0.10)", border: "rgba(34,197,94,0.25)" };
  if (score >= 60) return { label: "Good match", detail: "Review missing keywords", color: T.red, bg: "rgba(166,55,45,0.12)", border: "rgba(166,55,45,0.28)" };
  if (score >= 40) return { label: "Partial match", detail: "Resume may need tailoring", color: T.burnt, bg: "rgba(140,58,39,0.12)", border: "rgba(140,58,39,0.28)" };
  return { label: "Low match", detail: "Large skill gap detected", color: "#F2EEB3", bg: "rgba(242,238,179,0.06)", border: "rgba(242,238,179,0.12)" };
}

export function JobsPage({ onJobClick }: { onJobClick: (id: string) => void }) {
  const { isMobile, isTablet } = useResponsiveFlags();
  const [taxonomy, setTaxonomy] = useState<TaxonomyCategory[]>([]);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [activeRole, setActiveRole] = useState<string | null>(null);
  // Raw state for inputs; debounced into search/location used for API calls.
  const [searchRaw, setSearchRaw] = useState("");
  const [search, setSearch] = useState("");
  const [locationRaw, setLocationRaw] = useState("");
  const [location, setLocation] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");
  const [timeFilter, setTimeFilter] = useState("");
  const [visaOnly, setVisaOnly] = useState(false);

  const [savedVersion, setSavedVersion] = useState(0);
  const [appliedVersion, setAppliedVersion] = useState(0);

  const [jobs, setJobs] = useState<api.JobPost[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 40;
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [resumeVersion, setResumeVersion] = useState(
    () => typeof window !== "undefined" ? localStorage.getItem("placeup_resume_version") || "" : ""
  );
  const [resumeLink, setResumeLink] = useState<{ checked: boolean; hasResume: boolean; score?: number; name?: string; error?: string }>({
    checked: false,
    hasResume: false,
  });
  const [pipelineStatus, setPipelineStatus] = useState<{ total_jobs?: number; active_jobs?: number; last_scraped_at?: string | null } | null>(null);
  const isLocalStatusFilter = statusFilter === "Saved" || statusFilter === "Applied" || statusFilter === "Interview";
  const hasServerFilters = Boolean(activeCategory || activeRole || search || location || visaOnly || timeFilter || statusFilter === "New");

  // Load taxonomy once.
  useEffect(() => {
    api.getJobTaxonomy()
      .then((data) => {
        if (Array.isArray(data?.categories)) setTaxonomy(data.categories);
      })
      .catch(() => {});
    api.getJobPipelineStatus()
      .then((status) => setPipelineStatus(status))
      .catch(() => {});
  }, []);

  useEffect(() => {
    const refresh = () => {
      setPage(1);
      setResumeVersion(typeof window !== "undefined" ? localStorage.getItem("placeup_resume_version") || String(Date.now()) : String(Date.now()));
      // Re-read saved/tracked state from localStorage whenever the window regains
      // focus — e.g. user saved a job from the detail view and navigated back.
      setSavedVersion((v) => v + 1);
      setAppliedVersion((v) => v + 1);
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
    // Treat the user as having a resume if either:
    //  (a) the parsed-resume endpoint says so, OR
    //  (b) the dashboard summary lists at least one resume on file.
    // This avoids the "asking twice for resume" bug where the Jobs page
    // would re-prompt for upload just because the older record was
    // missing parsed_text — even though the user already uploaded at signup.
    Promise.allSettled([
      api.getParsedActiveResume(),
      api.getDashboardSummary(),
    ])
      .then(([parsedRes, summaryRes]) => {
        if (!active) return;
        const parsed = parsedRes.status === "fulfilled" ? parsedRes.value : null;
        const summary = summaryRes.status === "fulfilled" ? summaryRes.value : null;
        const hasResume = Boolean(
          (parsed?.has_resume) ||
          (summary?.has_resume) ||
          (summary?.active_resume_name) ||
          (summary?.total_resumes && summary.total_resumes > 0)
        );
        setResumeLink({
          checked: true,
          hasResume,
          score: typeof parsed?.score === "number" ? parsed.score : summary?.resume_score,
          name: parsed?.name || summary?.active_resume_name,
          // Only surface the "re-upload" error when we are SURE no resume exists
          // anywhere — otherwise the banner is just noise.
          error: hasResume ? undefined : parsed?.error,
        });
      });
    return () => { active = false; };
  }, [resumeVersion]);

  // Reload jobs whenever filters or the active resume change.
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    if (page === 1) {
      setJobs([]);
      setTotal(0);
    }

    const params: Record<string, string | number | boolean> = { page, page_size: pageSize, max_years: 10, sort: "recent" };
    if (search) params.search = search;
    if (location) params.location = location;
    if (visaOnly) params.visa_only = true;
    if (statusFilter === "New") params.status = "active";
    if (activeCategory && !activeRole) params.category = activeCategory;
    if (activeRole) params.role = activeRole;
    if (timeFilter) {
      params.time_filter = timeFilter;
      // Pass timezone offset so backend calculates "today"/"yesterday" in the user's local time
      params.tz_offset = new Date().getTimezoneOffset();
    }

    getJobsWithRetry(params)
      .then((response: any) => {
        if (!active) return;
        // Be defensive: backends have historically returned either
        //   { jobs: [...], total }    (current) or
        //   [...]                     (legacy)
        // Both shapes should render the same All-Jobs grid.
        const incoming: any[] = Array.isArray(response)
          ? response
          : Array.isArray(response?.jobs)
            ? response.jobs
            : Array.isArray(response?.results)
              ? response.results
              : [];
        setJobs((prev) => page === 1 ? incoming : [...prev, ...incoming]);
        const reportedTotal = Array.isArray(response)
          ? response.length
          : (response?.total ?? response?.count ?? incoming.length);
        setTotal(typeof reportedTotal === "number" ? reportedTotal : incoming.length);
      })
      .catch((err) => {
        if (active) {
          setError(friendlyJobError(err));
          if (page === 1) {
            setJobs([]);
            setTotal(0);
          }
          // Keep failed first-page filters from showing stale All Jobs results.
        }
      })
      .finally(() => { if (active) setLoading(false); });

    return () => { active = false; };
  }, [activeCategory, activeRole, search, location, visaOnly, timeFilter, statusFilter, page, resumeVersion, reloadKey]);

  // Debounce search/location so API is only called after typing stops.
  useEffect(() => {
    const t = setTimeout(() => {
      setPage(1);
      setSearch(searchRaw);
    }, 400);
    return () => clearTimeout(t);
  }, [searchRaw]);

  useEffect(() => {
    const t = setTimeout(() => {
      setPage(1);
      setLocation(locationRaw);
    }, 400);
    return () => clearTimeout(t);
  }, [locationRaw]);

  useEffect(() => {
    setPage(1);
  }, [activeCategory, activeRole, search, location, visaOnly, timeFilter, statusFilter]);

  const savedIds = useMemo(() => getSavedIds(), [savedVersion]);
  const trackedJobs = useMemo(() => getTrackedJobs(), [appliedVersion]);

  const filtered = useMemo(() => {
    if (statusFilter === "All") return jobs;
    if (statusFilter === "Saved") return jobs.filter((j) => savedIds.has(String(j.id)));
    if (statusFilter === "New") return jobs;
    if (statusFilter === "Applied") return jobs.filter((j) => trackedJobs[String(j.id)] === "applied");
    if (statusFilter === "Interview") return jobs.filter((j) => trackedJobs[String(j.id)] === "interview");
    return jobs;
  }, [jobs, statusFilter, savedIds, trackedJobs]);

  const currentCategory = taxonomy.find((c) => c.name === activeCategory);
  const allJobsCount = Number(pipelineStatus?.total_jobs || pipelineStatus?.active_jobs || total || 0);
  const openPositionsCount = hasServerFilters ? total : allJobsCount;

  return (
    <div style={{ display: "grid", gridTemplateColumns: isTablet ? "1fr" : "280px minmax(0, 1fr)", gap: isMobile ? 12 : 20, alignItems: "start", width: "100%", minWidth: 0 }}>
      {/* CATEGORY SIDEBAR */}
      <aside style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 16, padding: isMobile ? 10 : 12, height: "fit-content", position: isTablet ? "relative" : "sticky", top: isTablet ? 0 : 20, minWidth: 0 }}>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: T.t3, fontFamily: F.sans, padding: "8px 10px 12px" }}>Categories</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 2, maxHeight: isTablet ? 320 : "70vh", overflowY: "auto" }}>
          <button
            onClick={() => { setActiveCategory(null); setActiveRole(null); setPage(1); }}
            style={{
              width: "100%", textAlign: "left", padding: "9px 10px", borderRadius: 8,
              border: "none", background: !activeCategory ? "rgba(166,55,45,0.10)" : "transparent",
              color: !activeCategory ? T.red : T.t2, fontSize: 13, fontFamily: F.sans, cursor: "pointer",
              fontWeight: !activeCategory ? 600 : 400, display: "flex", justifyContent: "space-between", alignItems: "center",
            }}
          >
            All Jobs
            <span style={{ fontSize: 11, color: T.t3 }}>{allJobsCount ? allJobsCount.toLocaleString() : loading ? "..." : "0"}</span>
          </button>
          {taxonomy.map((cat) => {
            const isActive = cat.name === activeCategory;
            return (
              <div key={cat.name}>
                <button
                  onClick={() => { setActiveCategory(cat.name); setActiveRole(null); setPage(1); }}
                  style={{
                    width: "100%", textAlign: "left", padding: "9px 10px", borderRadius: 8,
                    border: "none", background: isActive ? "rgba(166,55,45,0.10)" : "transparent",
                    color: isActive ? T.red : T.t2, fontSize: 13, fontFamily: F.sans, cursor: "pointer",
                    fontWeight: isActive ? 600 : 400, display: "flex", justifyContent: "space-between", alignItems: "center",
                  }}
                >
                  {cat.name}
                  <span style={{ fontSize: 11, color: T.t3 }}>{cat.roles.length} roles</span>
                </button>
                {isActive && (
                  <div style={{ marginLeft: 8, paddingLeft: 8, borderLeft: `1px solid ${T.border}`, marginTop: 4, marginBottom: 4 }}>
                    {cat.roles.map((role) => (
                      <button
                        key={role.name}
                        onClick={() => { setActiveRole(activeRole === role.name ? null : role.name); setPage(1); }}
                        style={{
                          width: "100%", textAlign: "left", padding: "6px 8px", borderRadius: 6,
                          border: "none", background: activeRole === role.name ? "rgba(166,55,45,0.06)" : "transparent",
                          color: activeRole === role.name ? T.red : T.t3, fontSize: 12, fontFamily: F.sans, cursor: "pointer",
                          display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6,
                        }}
                      >
                        <span>{role.name}</span>
                        <span style={{ display: "flex", gap: 3, alignItems: "center", flexShrink: 0 }}>
                          {role.hot && <Flame size={9} color={T.red} />}
                          {role.visa.slice(0, 2).map((v) => {
                            const s = VISA_BADGES[v] ?? VISA_BADGES["OPT"];
                            return <span key={v} style={{ fontSize: 8, fontWeight: 700, padding: "1px 4px", borderRadius: 3, background: s.bg, color: s.color, border: `1px solid ${s.border}` }}>{v}</span>;
                          })}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </aside>

      {/* JOBS LIST */}
      <div style={{ display: "flex", flexDirection: "column", gap: 14, minWidth: 0 }}>
        <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "repeat(3, minmax(0, 1fr))", gap: 10 }}>
          {[
            { label: "Open positions", value: openPositionsCount ? openPositionsCount.toLocaleString() : loading ? "..." : "0", icon: Briefcase },
            { label: "Visible now", value: loading && jobs.length === 0 ? "..." : filtered.length.toLocaleString(), icon: Sparkles },
            { label: "Visa filter", value: visaOnly ? "On" : "Off", icon: ShieldCheck },
          ].map((item) => {
            const Icon = item.icon;
            return (
              <div key={item.label} style={{ background: "rgba(64,18,18,0.42)", backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 14, padding: "13px 14px", display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ width: 32, height: 32, borderRadius: 9, background: "rgba(166,55,45,0.12)", border: "1px solid rgba(166,55,45,0.22)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <Icon size={15} color={T.red} />
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 16, fontWeight: 700, color: T.text, fontFamily: F.mono, lineHeight: 1.1 }}>{item.value}</div>
                  <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans, marginTop: 2 }}>{item.label}</div>
                </div>
              </div>
            );
          })}
        </div>
        {pipelineStatus && (
          <div style={{ padding: "10px 12px", borderRadius: 12, background: "rgba(242,238,179,0.04)", border: `1px solid ${T.border}`, color: T.t3, fontSize: 11, fontFamily: F.sans }}>
            Pipeline: {Number(pipelineStatus.active_jobs ?? total).toLocaleString()} active jobs
            {pipelineStatus.last_scraped_at ? ` - last scraped ${formatPosted(pipelineStatus.last_scraped_at)}` : ""}
          </div>
        )}

        {/* Search + filter bar */}
        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 14, padding: isMobile ? "10px" : "12px 16px", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flex: "1 1 240px", minWidth: isMobile ? "100%" : 200, height: 36, padding: "0 12px", borderRadius: 8, border: `1px solid ${T.border}`, background: "rgba(242,238,179,0.04)" }}>
            <Search size={13} color={T.t3} />
            <input value={searchRaw} onChange={(e) => setSearchRaw(e.target.value)} placeholder="Search title, company, JD..."
              style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: T.text, fontSize: 13, fontFamily: F.sans }} />
          </div>
          <input value={locationRaw} onChange={(e) => setLocationRaw(e.target.value)} placeholder="Location"
            style={{ width: isMobile ? "100%" : 140, flex: isMobile ? "1 1 100%" : "0 0 auto", height: 36, padding: "0 12px", borderRadius: 8, border: `1px solid ${T.border}`, background: "rgba(242,238,179,0.04)", color: T.text, fontSize: 13, outline: "none" }} />
          <button onClick={() => { setVisaOnly(!visaOnly); setPage(1); }}
            style={{ height: 36, padding: "0 12px", borderRadius: 8, border: `1px solid ${visaOnly ? "rgba(166,55,45,0.4)" : T.border}`, background: visaOnly ? "rgba(166,55,45,0.10)" : "transparent", color: visaOnly ? T.red : T.t2, fontSize: 12, fontFamily: F.sans, cursor: "pointer", display: "flex", alignItems: "center", gap: 5 }}>
            <Filter size={12} /> Visa-friendly
          </button>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {STATUS_CHIPS.map((s) => (
                <button key={s} onClick={() => { setStatusFilter(s); setPage(1); }}
                style={{ height: 32, padding: "0 12px", borderRadius: 9999, border: `1px solid ${statusFilter === s ? "transparent" : T.border}`, background: statusFilter === s ? T.grad : "transparent", color: statusFilter === s ? "#fff" : T.t2, fontSize: 12, cursor: "pointer", fontFamily: F.sans, fontWeight: statusFilter === s ? 600 : 400 }}>
                {s}
              </button>
            ))}
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", width: "100%" }}>
            {TIME_CHIPS.map((chip) => (
              <button key={chip.label} onClick={() => { setTimeFilter(chip.value); setPage(1); }}
                style={{ height: 30, padding: "0 10px", borderRadius: 9999, border: `1px solid ${timeFilter === chip.value ? "transparent" : T.border}`, background: timeFilter === chip.value ? T.grad : "transparent", color: timeFilter === chip.value ? "#fff" : T.t2, fontSize: 11, cursor: "pointer", fontFamily: F.sans, fontWeight: timeFilter === chip.value ? 700 : 400 }}>
                {chip.label}
              </button>
            ))}
          </div>
        </div>

        {resumeLink.checked && (
          <div style={{
            display: "flex", flexDirection: isMobile ? "column" : "row", alignItems: isMobile ? "stretch" : "center", justifyContent: "space-between", gap: 12,
            padding: "12px 14px", borderRadius: 14,
            border: `1px solid ${resumeLink.hasResume ? "rgba(34,197,94,0.22)" : "rgba(166,55,45,0.28)"}`,
            background: resumeLink.hasResume ? "rgba(34,197,94,0.07)" : "rgba(166,55,45,0.08)",
            color: T.t2, fontFamily: F.sans,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
              <div style={{
                width: 30, height: 30, borderRadius: 9, flexShrink: 0,
                display: "flex", alignItems: "center", justifyContent: "center",
                background: resumeLink.hasResume ? "rgba(34,197,94,0.10)" : "rgba(166,55,45,0.12)",
                border: `1px solid ${resumeLink.hasResume ? "rgba(34,197,94,0.24)" : "rgba(166,55,45,0.24)"}`,
              }}>
                <ShieldCheck size={14} color={resumeLink.hasResume ? "#22c55e" : T.red} />
              </div>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: T.text, lineHeight: 1.25 }}>
                  {resumeLink.hasResume ? "Active resume linked to job matching" : "Resume is not linked to job matching"}
                </div>
                <div style={{ fontSize: 11, color: T.t3, lineHeight: 1.4, marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {resumeLink.hasResume
                    ? `${resumeLink.name || "Resume"}${resumeLink.score ? ` - Resume score ${resumeLink.score}` : ""}`
                    : resumeLink.error || "Upload or re-upload a resume from the Resumes tab."}
                </div>
              </div>
            </div>
            {!resumeLink.hasResume && (
              <button
                onClick={() => { window.location.href = "/dashboard/resumes"; }}
                style={{ height: 32, padding: "0 12px", borderRadius: 8, border: "none", background: T.grad, color: "#fff", fontSize: 12, fontWeight: 700, fontFamily: F.sans, cursor: "pointer", flexShrink: 0, width: isMobile ? "100%" : "auto" }}
              >
                Upload Resume
              </button>
            )}
          </div>
        )}

        {/* Active filters strip */}
        {(activeRole || activeCategory || search || location || visaOnly || timeFilter || statusFilter !== "All") && (
          <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
            <span style={{ fontSize: 11, color: T.t3, fontFamily: F.sans }}>{filtered.length} of {total} positions</span>
            {activeCategory && (
              <span style={{ display: "inline-flex", gap: 4, alignItems: "center", fontSize: 11, padding: "3px 8px", borderRadius: 4, background: "rgba(166,55,45,0.08)", color: T.red, border: "1px solid rgba(166,55,45,0.25)", fontFamily: F.sans }}>
                Category: {activeCategory}
              </span>
            )}
            {activeRole && (
              <span style={{ display: "inline-flex", gap: 4, alignItems: "center", fontSize: 11, padding: "3px 8px", borderRadius: 4, background: "rgba(166,55,45,0.08)", color: T.red, border: "1px solid rgba(166,55,45,0.25)", fontFamily: F.sans }}>
                Role: {activeRole}
                <button onClick={() => { setActiveRole(null); setPage(1); }} style={{ background: "none", border: "none", cursor: "pointer", color: T.red, padding: 0 }}><X size={10} /></button>
              </span>
            )}
            {search && (
              <span style={{ display: "inline-flex", gap: 4, alignItems: "center", fontSize: 11, padding: "3px 8px", borderRadius: 4, background: "rgba(166,55,45,0.08)", color: T.red, border: "1px solid rgba(166,55,45,0.25)", fontFamily: F.sans }}>
                Search: {search}
                <button onClick={() => { setSearchRaw(""); setSearch(""); setPage(1); }} style={{ background: "none", border: "none", cursor: "pointer", color: T.red, padding: 0 }}><X size={10} /></button>
              </span>
            )}
            {location && (
              <span style={{ display: "inline-flex", gap: 4, alignItems: "center", fontSize: 11, padding: "3px 8px", borderRadius: 4, background: "rgba(166,55,45,0.08)", color: T.red, border: "1px solid rgba(166,55,45,0.25)", fontFamily: F.sans }}>
                Location: {location}
                <button onClick={() => { setLocationRaw(""); setLocation(""); setPage(1); }} style={{ background: "none", border: "none", cursor: "pointer", color: T.red, padding: 0 }}><X size={10} /></button>
              </span>
            )}
            {visaOnly && (
              <span style={{ display: "inline-flex", gap: 4, alignItems: "center", fontSize: 11, padding: "3px 8px", borderRadius: 4, background: "rgba(166,55,45,0.08)", color: T.red, border: "1px solid rgba(166,55,45,0.25)", fontFamily: F.sans }}>
                Visa-friendly
                <button onClick={() => { setVisaOnly(false); setPage(1); }} style={{ background: "none", border: "none", cursor: "pointer", color: T.red, padding: 0 }}><X size={10} /></button>
              </span>
            )}
            {timeFilter && (
              <span style={{ display: "inline-flex", gap: 4, alignItems: "center", fontSize: 11, padding: "3px 8px", borderRadius: 4, background: "rgba(166,55,45,0.08)", color: T.red, border: "1px solid rgba(166,55,45,0.25)", fontFamily: F.sans }}>
                Time: {TIME_CHIPS.find((chip) => chip.value === timeFilter)?.label || timeFilter}
                <button onClick={() => { setTimeFilter(""); setPage(1); }} style={{ background: "none", border: "none", cursor: "pointer", color: T.red, padding: 0 }}><X size={10} /></button>
              </span>
            )}
            {statusFilter !== "All" && (
              <span style={{ display: "inline-flex", gap: 4, alignItems: "center", fontSize: 11, padding: "3px 8px", borderRadius: 4, background: "rgba(166,55,45,0.08)", color: T.red, border: "1px solid rgba(166,55,45,0.25)", fontFamily: F.sans }}>
                Status: {statusFilter}{isLocalStatusFilter ? " (current page)" : ""}
                <button onClick={() => { setStatusFilter("All"); setPage(1); }} style={{ background: "none", border: "none", cursor: "pointer", color: T.red, padding: 0 }}><X size={10} /></button>
              </span>
            )}
          </div>
        )}

        {error && (
          <div style={{ padding: "14px 16px", borderRadius: 12, background: "rgba(166,55,45,0.08)", border: "1px solid rgba(166,55,45,0.25)", color: T.text, fontFamily: F.sans, fontSize: 13 }}>
            <div style={{ fontWeight: 700, marginBottom: 4, color: T.red }}>Couldn't load jobs</div>
            <div style={{ color: T.t2, marginBottom: 10 }}>{error}</div>
            <button
              onClick={() => setReloadKey((value) => value + 1)}
              style={{ height: 32, padding: "0 12px", borderRadius: 8, border: `1px solid ${T.border}`, background: "rgba(242,238,179,0.05)", color: T.text, fontSize: 12, fontFamily: F.sans, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 6 }}
            >
              <RefreshCw size={12} />
              Retry
            </button>
          </div>
        )}

        {/* Job cards */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 10 }}>
          {loading && jobs.length === 0 && (
            <div style={{ gridColumn: "1 / -1", textAlign: "center", padding: 40, color: T.t2, fontFamily: F.sans, background: T.glass, border: `1px solid ${T.border}`, borderRadius: 16 }}>
              Loading jobs…
            </div>
          )}
          {!loading && filtered.length === 0 && !error && (
            <div style={{ gridColumn: "1 / -1", textAlign: "center", padding: 40, background: T.glass, border: `1px solid ${T.border}`, borderRadius: 16, color: T.t2, fontFamily: F.sans }}>
              <div style={{ fontSize: 14, marginBottom: 6 }}>No jobs match the current filters.</div>
              <div style={{ fontSize: 12, color: T.t3, marginBottom: 12 }}>Try clearing the search, location, or status filter.</div>
              <button
                onClick={() => { setSearchRaw(""); setSearch(""); setLocationRaw(""); setLocation(""); setVisaOnly(false); setTimeFilter(""); setStatusFilter("All"); setActiveCategory(null); setActiveRole(null); setPage(1); }}
                style={{ padding: "8px 14px", borderRadius: 8, border: `1px solid ${T.border}`, background: "transparent", color: T.t2, fontSize: 12, fontFamily: F.sans, cursor: "pointer" }}
              >Reset filters</button>
            </div>
          )}
          {filtered.map((job, i) => {
            const visaBadges = normalizeVisa(job.visa);
            const match = job.match_score ?? job.match ?? null;
            const scoreMeta = getScoreMeta(match);
            const id = String(job.id || "");
            const preview = cleanPreview(job.description).slice(0, 260);
            const role = (job as any).role || (job as any).taxonomy_category || job.status || "Active";
            const jobUrl = resolveJobUrl(job);
            return (
              <motion.div
                key={id}
                initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}
                whileHover={{ y: -4, boxShadow: "0 16px 36px rgba(1,17,38,0.35)" }}
                onClick={() => onJobClick(id)}
                style={{
                  background: "linear-gradient(135deg, rgba(64,18,18,0.62), rgba(25,18,32,0.72))", backdropFilter: "blur(20px)", border: `1px solid ${T.border}`,
                  borderLeft: `4px solid ${scoreMeta.color}`,
                  borderRadius: 16, padding: 16, cursor: "pointer", display: "grid",
                  gridTemplateColumns: isMobile ? "1fr" : "minmax(0, 1fr) 138px", gap: 14, alignItems: "stretch",
                }}
              >
                <div style={{ minWidth: 0, display: "flex", flexDirection: "column", gap: 9 }}>
                  <div style={{ display: "flex", flexDirection: isMobile ? "column" : "row", justifyContent: "space-between", gap: 10, alignItems: isMobile ? "stretch" : "flex-start" }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 16, fontWeight: 700, color: T.text, fontFamily: F.sans, lineHeight: 1.25, marginBottom: 4 }}>{job.title || "Untitled role"}</div>
                      <div style={{ fontSize: 13, color: T.t2, fontFamily: F.sans, fontWeight: 600 }}>{job.company || "Unknown"}</div>
                    </div>
                    <span style={{ fontSize: 10, fontWeight: 700, padding: "4px 8px", borderRadius: 999, background: "rgba(242,238,179,0.05)", color: T.t2, border: `1px solid ${T.border}`, fontFamily: F.sans, whiteSpace: "nowrap", alignSelf: isMobile ? "flex-start" : "auto" }}>{role}</span>
                  </div>
                  <div style={{ display: "flex", gap: 12, fontSize: 11, color: T.t3, fontFamily: F.sans, flexWrap: "wrap" }}>
                    <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}><MapPin size={11} />{job.location || "Remote"}</span>
                    <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}><DollarSign size={11} />{formatSalary(job.salary)}</span>
                    <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}><Clock size={11} />{formatPosted(job.posted_at || (job as any).posted)}</span>
                  </div>
                  {preview && (
                    <div style={{ fontSize: 12, color: T.t3, fontFamily: F.sans, lineHeight: 1.55, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                      {preview}
                    </div>
                  )}
                  <div style={{ display: "flex", flexDirection: isMobile ? "column" : "row", justifyContent: "space-between", gap: 10, alignItems: isMobile ? "stretch" : "center", borderTop: `1px solid ${T.border}`, paddingTop: 10 }}>
                    <div style={{ display: "flex", gap: 5, flexWrap: "wrap", minWidth: 0 }}>
                      {visaBadges.slice(0, 4).map((v) => {
                        const s = VISA_BADGES[v] ?? { bg: "rgba(64,18,18,0.1)", color: T.t2, border: T.border };
                        return <span key={v} style={{ fontSize: 9, fontWeight: 700, padding: "2px 7px", borderRadius: 4, background: s.bg, color: s.color, border: `1px solid ${s.border}`, fontFamily: F.sans }}>{v}</span>;
                      })}
                      {visaBadges.length === 0 && <span style={{ fontSize: 10, color: T.t3, fontFamily: F.sans }}>Visa not verified</span>}
                    </div>
                    <div style={{ display: "flex", gap: 6, flexShrink: 0, flexWrap: "wrap", justifyContent: isMobile ? "flex-start" : "flex-end" }}>
                      <button onClick={(e) => {
                        e.stopPropagation();
                        const saved = Array.from(savedIds);
                        const next = savedIds.has(id) ? saved.filter((item) => item !== id) : [...saved, id];
                        localStorage.setItem("placeup_saved_jobs", JSON.stringify(next));
                        setSavedVersion((v) => v + 1);
                      }} style={{ width: 32, height: 30, borderRadius: 8, border: `1px solid ${savedIds.has(id) ? "rgba(166,55,45,0.4)" : T.border}`, background: savedIds.has(id) ? "rgba(166,55,45,0.08)" : "transparent", color: savedIds.has(id) ? T.red : T.t2, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }} title={savedIds.has(id) ? "Unsave" : "Save job"}><Bookmark size={13} fill={savedIds.has(id) ? T.red : "none"}/></button>
                      <button onClick={(e) => {
                        e.stopPropagation();
                        const cur = trackedJobs[id];
                        const updated = { ...trackedJobs };
                        if (!cur) { updated[id] = "applied"; }
                        else if (cur === "applied") { updated[id] = "interview"; }
                        else { delete updated[id]; }
                        localStorage.setItem("placeup_job_tracking", JSON.stringify(updated));
                        setAppliedVersion((v) => v + 1);
                      }} style={{ height: 30, padding: "0 10px", borderRadius: 8, border: `1px solid ${trackedJobs[id] === "interview" ? "rgba(59,130,246,0.4)" : trackedJobs[id] === "applied" ? "rgba(34,197,94,0.4)" : T.border}`, background: trackedJobs[id] === "interview" ? "rgba(59,130,246,0.08)" : trackedJobs[id] === "applied" ? "rgba(34,197,94,0.08)" : "transparent", color: trackedJobs[id] === "interview" ? "#3b82f6" : trackedJobs[id] === "applied" ? "#22c55e" : T.t3, fontSize: 10, fontWeight: 700, cursor: "pointer", fontFamily: F.sans, whiteSpace: "nowrap" }} title={trackedJobs[id] === "interview" ? "Interview stage — click to clear" : trackedJobs[id] === "applied" ? "Applied — click to move to Interview" : "Track application status"}>
                        {trackedJobs[id] === "interview" ? "Interview" : trackedJobs[id] === "applied" ? "Applied" : "Track"}
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          const url = jobUrl || `https://www.google.com/search?q=${encodeURIComponent(`${job.company || ""} ${job.title || ""} apply`)}`;
                          window.open(url, "_blank", "noopener,noreferrer");
                        }}
                        style={{ height: 30, padding: "0 12px", borderRadius: 8, border: `1px solid ${T.border}`, background: "rgba(242,238,179,0.05)", color: T.t2, fontSize: 11, cursor: "pointer", fontFamily: F.sans, fontWeight: 700, display: "flex", alignItems: "center", gap: 4 }}
                      ><ExternalLink size={11}/> Apply</button>
                      <button onClick={(e) => { e.stopPropagation(); onJobClick(id); }} style={{ height: 30, padding: "0 12px", borderRadius: 8, border: "none", background: T.grad, color: "#fff", fontSize: 11, cursor: "pointer", fontFamily: F.sans, fontWeight: 700, display: "flex", alignItems: "center", gap: 4 }}><ExternalLink size={11}/> View</button>
                    </div>
                  </div>
                </div>
                <div style={{ borderRadius: 14, border: `1px solid ${scoreMeta.border}`, background: scoreMeta.bg, padding: 12, display: "flex", flexDirection: isMobile ? "row" : "column", alignItems: "center", justifyContent: "center", gap: 10 }}>
                  <ATSRing score={match} size={70} />
                  <div style={{ textAlign: "center" }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: scoreMeta.color, fontFamily: F.sans, lineHeight: 1.2 }}>{scoreMeta.label}</div>
                    <div style={{ fontSize: 10, color: T.t3, fontFamily: F.sans, lineHeight: 1.35, marginTop: 3 }}>{scoreMeta.detail}</div>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
        {!loading && jobs.length < total && (
          <button
            onClick={() => setPage((p) => p + 1)}
            style={{ alignSelf: "center", marginTop: 6, padding: "10px 18px", borderRadius: 10, border: `1px solid ${T.border}`, background: "rgba(242,238,179,0.04)", color: T.t2, fontSize: 13, fontFamily: F.sans, cursor: "pointer" }}
          >
            Load more jobs ({jobs.length.toLocaleString()} of {total.toLocaleString()})
          </button>
        )}
      </div>
    </div>
  );
}
