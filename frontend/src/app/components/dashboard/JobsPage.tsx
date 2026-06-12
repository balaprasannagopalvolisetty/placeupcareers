import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { useSearchParams } from "react-router";
import { motion } from "motion/react";
import { Search, Filter, X, Bookmark, ExternalLink, ShieldCheck, RefreshCw, Globe2, Route, Languages, Building2, Sparkles, Clock, Wand2 } from "lucide-react";
import * as api from "../../lib/api";
import { LoadingLogo } from "../LoadingLogo";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
// Aligned to the main-page cream + orange theme (navy surfaces, cream text,
// orange accent). Legacy accent keys (violet/blue/fuchsia) are kept but mapped
// to orange so every existing usage recolors automatically.
const T = {
  text: "#F5EAC8", t2: "rgba(245,234,200,0.66)", t3: "rgba(245,234,200,0.45)",
  border: "rgba(245,234,200,0.10)", glass: "rgba(64,18,18,0.55)",
  grad: "linear-gradient(135deg, #F2A341, #ED7D2B, #C75A12)",
  panel: "linear-gradient(135deg, rgba(1,17,38,0.92), rgba(64,18,18,0.5), rgba(122,52,8,0.28))",
  violet: "#ED7D2B", blue: "#F2A341", fuchsia: "#ED7D2B", red: "#ED7D2B", burnt: "#C75A12", dark: "#011126",
};

const J = {
  page: "transparent",
  card: "rgba(64,18,18,0.45)",
  line: "rgba(245,234,200,0.10)",
  text: "#F5EAC8",
  t2: "rgba(245,234,200,0.66)",
  t3: "rgba(245,234,200,0.45)",
  blue: "#ED7D2B",
  blueBg: "rgba(237,125,43,0.12)",
  green: "#3FB477",
  greenBg: "rgba(63,180,119,0.12)",
  shadow: "0 18px 44px rgba(1,17,38,0.28)",
};

const TIME_OPTIONS = [
  { label: "All active", value: "" },
  { label: "Last 8h", value: "8h" },
  { label: "Today", value: "today" },
  { label: "Yesterday", value: "yesterday" },
  { label: "Week", value: "week" },
  { label: "Month", value: "month" },
];
const SELECT_DARK_STYLE: CSSProperties = { background: "#011126", color: "#F5EAC8" };
const VISA_BADGES: Record<string, { bg: string; color: string; border: string }> = {
  "H-1B":   { bg: "rgba(237,125,43,0.15)", color: "#F5EAC8", border: "rgba(237,125,43,0.35)" },
  "OPT":    { bg: "rgba(37,99,235,0.12)", color: "#93C5FD", border: "rgba(237,125,43,0.3)" },
  "STEM":   { bg: "rgba(199,90,18,0.12)",  color: "#F9A8D4", border: "rgba(240,171,252,0.3)" },
  "Vol":    { bg: "rgba(34,197,94,0.10)", color: "#22c55e", border: "rgba(34,197,94,0.3)" },
  "No sponsorship": { bg: "rgba(245,234,200,0.08)", color: "rgba(245,234,200,0.62)", border: "rgba(245,234,200,0.18)" },
  "English-friendly": { bg: "rgba(34,197,94,0.10)", color: "#86EFAC", border: "rgba(34,197,94,0.26)" },
};

function normalizeVisa(visa: unknown): string[] {
  if (Array.isArray(visa)) return visa.filter((v): v is string => typeof v === "string");
  if (visa && typeof visa === "object") {
    const record = visa as Record<string, unknown>;
    const programNames = Array.isArray(record.visa_program_names)
      ? record.visa_program_names.filter((v): v is string => typeof v === "string" && v.trim().length > 0)
      : [];
    const country = typeof record.visa_country === "string" ? record.visa_country : "";
    const badges = programNames.map((name) => country ? `${country}: ${name}` : name);
    if (country === "US") {
      if (record.visa_h1b) badges.push("H-1B");
      if (record.visa_opt) badges.push("OPT");
      if (record.visa_stem_opt) badges.push("STEM OPT");
      if (record.h1b_verified) badges.push("H-1B Verified");
      if (record.green_card) badges.push("Green Card");
    }
    if (record.no_sponsorship) badges.push("No sponsorship");
    return Array.from(new Set(badges));
  }
  if (typeof visa === "string") return visa.split(",").map((s) => s.trim()).filter(Boolean);
  return [];
}

function normalizeTaxonomyVisa(visa: unknown): string[] {
  if (Array.isArray(visa)) return visa.filter((v): v is string => typeof v === "string" && v.trim().length > 0);
  if (typeof visa === "string") {
    return visa
      .split(/[\s,]+/)
      .map((v) => v.trim())
      .filter(Boolean);
  }
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

interface TaxonomyRole { name: string; synonyms: string[] | string; visa: string[]; hot: boolean }
interface TaxonomyCategory { name: string; icon: string; roles: TaxonomyRole[] }
interface TaxonomyMeta {
  category_count?: number;
  role_count?: number;
  backfill_term_count?: number;
  scrape_term_count?: number;
}
interface CountryOption { code: string; name: string }
interface VisaProgramOption { country_code: string; code: string; name: string }

const JOB_FETCH_RETRY_MS = 700;

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
  const name = (err as Error)?.name || "";
  if (name === "AbortError" || message.toLowerCase().includes("aborted")) {
    return "Jobs are taking longer than expected to load. Please retry in a moment.";
  }
  if (message.toLowerCase().includes("failed to fetch")) {
    return "Network hiccup while loading jobs. Please retry, or refresh if this keeps happening.";
  }
  return message;
}

async function getJobsWithRetry(params: Record<string, string | number | boolean>, attempts = 1) {
  let lastError: unknown;
  for (let i = 0; i < attempts; i += 1) {
    try {
      return await api.getJobs(params);
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
  return decodeHtml(value)
    .replace(/<[^>]+>/g, " ")
    // Strip markdown artifacts so every card preview reads as clean prose:
    // **bold**, __underline__, ### headers, list bullets, escape backslashes.
    .replace(/\*\*+|__+|~~+/g, "")
    .replace(/^#+\s*/gm, "")
    .replace(/^\s*[*\-\u2022]\s+/gm, "")
    .replace(/\\([\\`*_{}[\]()#+\-.!|>~])/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

function formatPosted(value: unknown): string {
  if (!value) return "Recently";
  const raw = String(value);
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw.length > 18 ? raw.slice(0, 18) : raw;
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const then = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const days = Math.max(0, Math.floor((today - then) / 86400000));
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 30) return `${days} days ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function jobPostedRaw(job: api.JobPost): unknown {
  // posted_at is preferred; fall back to scraped_at / last_seen_at so a date
  // always renders instead of "unavailable" for rows missing posted_at.
  return job.posted_at || job.posted || (job as any).scraped_at || (job as any).last_seen_at;
}

function jobDateLabel(job: api.JobPost): string {
  const raw = jobPostedRaw(job);
  return raw ? `Posted ${formatPosted(raw)}` : "Posted recently";
}

function compactNumber(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "0";
  if (value >= 1000000) return `${(value / 1000000).toFixed(value >= 10000000 ? 0 : 1)}M`;
  if (value >= 1000) return `${(value / 1000).toFixed(value >= 10000 ? 0 : 1)}K`;
  return value.toLocaleString();
}

function countryName(code: string, countries: CountryOption[]): string {
  return countries.find((country) => country.code === code)?.name || code;
}

const COUNTRY_FLAGS: Record<string, string> = {
  AE: "🇦🇪", AT: "🇦🇹", AU: "🇦🇺", BE: "🇧🇪", CA: "🇨🇦", CH: "🇨🇭", CZ: "🇨🇿", DE: "🇩🇪",
  DK: "🇩🇰", EE: "🇪🇪", ES: "🇪🇸", FI: "🇫🇮", FR: "🇫🇷", GB: "🇬🇧", HK: "🇭🇰", IE: "🇮🇪",
  IT: "🇮🇹", JP: "🇯🇵", KR: "🇰🇷", LU: "🇱🇺", NL: "🇳🇱", NO: "🇳🇴", NZ: "🇳🇿", PL: "🇵🇱",
  PT: "🇵🇹", QA: "🇶🇦", SA: "🇸🇦", SE: "🇸🇪", SG: "🇸🇬", TW: "🇹🇼", US: "🇺🇸",
};

function countryFlag(code: string): string {
  return COUNTRY_FLAGS[code] || "🌐";
}

// Windows does NOT render country-flag emoji (users see plain "US" letters),
// so anywhere we control the markup we render a real flag image with the
// emoji as alt/fallback. <option> elements can't contain images, so the
// dropdowns keep emoji.
function FlagIcon({ code, size = 16 }: { code: string; size?: number }) {
  const cc = (code || "").trim().toLowerCase();
  if (!cc || cc.length !== 2) return <span style={{ fontSize: size }}>🌐</span>;
  return (
    <img
      src={`https://flagcdn.com/${Math.round(size * 1.5)}x${size}/${cc}.png`}
      srcSet={`https://flagcdn.com/${Math.round(size * 3)}x${size * 2}/${cc}.png 2x`}
      width={Math.round(size * 1.5)}
      height={size}
      alt={countryFlag(code)}
      loading="lazy"
      onError={(e) => { e.currentTarget.outerHTML = countryFlag(code); }}
      style={{ borderRadius: 2, display: "inline-block", verticalAlign: "-2px", boxShadow: "0 0 0 1px rgba(245,234,200,0.15)" }}
    />
  );
}

function publishDateLabel(job: api.JobPost): string {
  const raw = jobPostedRaw(job);
  if (!raw) return "Publish date —";
  const date = new Date(String(raw));
  if (Number.isNaN(date.getTime())) return `Publish date ${String(raw).slice(0, 18)}`;
  const dd = String(date.getDate()).padStart(2, "0");
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  return `Publish date ${dd}-${mm}-${date.getFullYear()}`;
}

function getVisaRecord(job: api.JobPost): Record<string, unknown> {
  return job.visa && typeof job.visa === "object" && !Array.isArray(job.visa) ? job.visa as Record<string, unknown> : {};
}

function routeLabel(program: VisaProgramOption): string {
  const shortName = program.name.replace(/\s+Visa$/i, "").replace(/\s+Permit$/i, "");
  return `${countryFlag(program.country_code)} ${program.country_code} ${shortName}`;
}

function sourceLabel(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) return "Source pending";
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function controlStyle(extra: CSSProperties = {}): CSSProperties {
  return {
    height: 38,
    padding: "0 12px",
    borderRadius: 7,
    border: `1px solid ${J.line}`,
    background: J.card,
    color: J.text,
    fontSize: 12,
    fontFamily: F.sans,
    outline: "none",
    boxShadow: "0 1px 2px rgba(1,17,38,0.18)",
    backdropFilter: "blur(16px)",
    ...extra,
  };
}

function filterPillStyle(active = false): CSSProperties {
  return {
    height: 30,
    padding: "0 10px",
    borderRadius: 999,
    border: `1px solid ${active ? "rgba(34,197,94,0.30)" : J.line}`,
    background: active ? J.greenBg : J.card,
    color: active ? J.green : J.t2,
    fontSize: 11,
    fontWeight: 750,
    fontFamily: F.sans,
    cursor: "pointer",
  };
}

function activeFilterChipStyle(): CSSProperties {
  return {
    display: "inline-flex",
    gap: 5,
    alignItems: "center",
    fontSize: 11,
    padding: "4px 9px",
    borderRadius: 999,
    background: J.blueBg,
    color: J.blue,
    border: "1px solid rgba(237,125,43,0.28)",
    fontFamily: F.sans,
    fontWeight: 750,
  };
}

function paginationButtonStyle(active = false, disabled = false): CSSProperties {
  return {
    minWidth: 36,
    height: 36,
    padding: "0 11px",
    borderRadius: 8,
    border: `1px solid ${active ? "rgba(237,125,43,0.46)" : J.line}`,
    background: active ? "rgba(237,125,43,0.18)" : "rgba(245,234,200,0.05)",
    color: disabled ? J.t3 : active ? "#F5EAC8" : J.t2,
    fontSize: 12,
    fontWeight: 850,
    fontFamily: F.sans,
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.52 : 1,
    boxShadow: active ? "0 12px 30px rgba(237,125,43,0.20)" : "none",
  };
}

function paginationPages(current: number, totalPages: number, maxButtons: number) {
  const safeTotal = Math.max(1, totalPages);
  const safeCurrent = Math.min(Math.max(1, current), safeTotal);
  const count = Math.min(Math.max(3, maxButtons), safeTotal);
  let start = Math.max(1, safeCurrent - Math.floor(count / 2));
  const endOverflow = start + count - 1 - safeTotal;
  if (endOverflow > 0) start = Math.max(1, start - endOverflow);
  return Array.from({ length: Math.min(count, safeTotal) }, (_, index) => start + index);
}

function clearChipButtonStyle(): CSSProperties {
  return {
    background: "none",
    border: "none",
    cursor: "pointer",
    color: J.blue,
    padding: 0,
    display: "inline-flex",
    alignItems: "center",
  };
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

function getTrackedJobs(): Record<string, "applied" | "interview" | "not_applied"> {
  try {
    return JSON.parse(localStorage.getItem("placeup_job_tracking") || "{}") as Record<string, "applied" | "interview" | "not_applied">;
  } catch { return {}; }
}

function companyLogoUrl(job: api.JobPost): string {
  const url = resolveJobUrl(job);
  try {
    const host = new URL(url).hostname.replace(/^www\./, "");
    if (host) return `https://logo.clearbit.com/${host}`;
  } catch {
    // Fall back to Clearbit's domain guess below.
  }
  const slug = (job.company || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
  return slug ? `https://logo.clearbit.com/${slug}.com` : "";
}

function ATSRing({ score, size = 60 }: { score: number | null | undefined; size?: number }) {
  const hasScore = typeof score === "number" && Number.isFinite(score);
  const safeScore = hasScore ? Math.max(0, Math.min(100, score)) : 0;
  const r = (size/2) - 5, circ = 2*Math.PI*r;
  const offset = circ * (1 - safeScore/100);
  const color = !hasScore ? J.t3 : safeScore >= 80 ? "#22c55e" : safeScore >= 60 ? J.blue : safeScore >= 40 ? "#F59E0B" : "#F87171";
  const textColor = hasScore ? color : J.t3;
  return (
    <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
      <svg viewBox={`0 0 ${size} ${size}`} style={{ width: "100%", height: "100%", transform: "rotate(-90deg)" }}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="rgba(245,234,200,0.20)" strokeWidth="5" />
        <motion.circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth="5" strokeLinecap="round"
          strokeDasharray={circ} initial={{ strokeDashoffset: circ }} animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1.2, ease: "easeOut" }} />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <span style={{ fontFamily: F.mono, fontSize: hasScore ? 13 : 11, fontWeight: 600, color: textColor }}>{hasScore ? safeScore : "--"}</span>
        <span style={{ fontSize: 7, color: J.t2, fontFamily: F.sans, letterSpacing: "0.05em" }}>{hasScore ? "ATS" : "Resume"}</span>
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
      bg: "rgba(245,234,200,0.05)",
      border: T.border,
    };
  }
  if (score >= 80) return { label: "Strong match", detail: "High keyword overlap", color: "#22c55e", bg: "rgba(34,197,94,0.10)", border: "rgba(34,197,94,0.25)" };
  if (score >= 60) return { label: "Good match", detail: "Review missing keywords", color: T.violet, bg: "rgba(237,125,43,0.12)", border: "rgba(237,125,43,0.28)" };
  if (score >= 40) return { label: "Partial match", detail: "Resume may need tailoring", color: T.burnt, bg: "rgba(245,158,11,0.12)", border: "rgba(245,158,11,0.28)" };
  return { label: "Low match", detail: "Large skill gap detected", color: "#F5EAC8", bg: "rgba(245,234,200,0.06)", border: "rgba(245,234,200,0.12)" };
}

export function JobsPage({ onJobClick }: { onJobClick: (id: string) => void }) {
  const { isMobile, isTablet } = useResponsiveFlags();
  const [taxonomy, setTaxonomy] = useState<TaxonomyCategory[]>([]);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [activeRole, setActiveRole] = useState<string | null>(null);
  const pageChangedRef = useRef(false);

  // Deep links from the Alerts digest ("/dashboard/jobs?role=Security Engineer")
  // pre-apply the role/category filter on arrival.
  const [searchParams] = useSearchParams();
  useEffect(() => {
    const roleParam = searchParams.get("role");
    const categoryParam = searchParams.get("category");
    if (roleParam) setActiveRole(roleParam);
    if (categoryParam) setActiveCategory(categoryParam);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // Pulled from user_preferences once at mount. When present, the API
  // uses every saved target role/location to personalize results.
  // The user can still override any of these inline.
  const [userPrefs, setUserPrefs] = useState<{ target_roles: string[]; target_locations: string[] } | null>(null);
  const [prefsApplied, setPrefsApplied] = useState(false);
  // Raw state for inputs; debounced into search/location used for API calls.
  const [searchRaw, setSearchRaw] = useState("");
  const [search, setSearch] = useState("");
  const [locationRaw, setLocationRaw] = useState("");
  const [location, setLocation] = useState("");
  const [targetCountries, setTargetCountries] = useState<CountryOption[]>([]);
  const [visaPrograms, setVisaPrograms] = useState<VisaProgramOption[]>([]);
  const [countryFilter, setCountryFilter] = useState("");
  const [visaProgramFilter, setVisaProgramFilter] = useState("");
  const [timeFilter, setTimeFilter] = useState("");
  const [visaOnly, setVisaOnly] = useState(false);
  const [personalized, setPersonalized] = useState(true);
  const [sortBy, setSortBy] = useState<"match" | "recent">("match");

  const [savedVersion, setSavedVersion] = useState(0);
  const [appliedVersion, setAppliedVersion] = useState(0);
  const [serverTrackedJobs, setServerTrackedJobs] = useState<Record<string, "applied" | "interview" | "not_applied">>({});
  const [tailorQueueIds, setTailorQueueIds] = useState<Set<string>>(() => new Set());
  const [tailorUsage, setTailorUsage] = useState<{ used: number; limit: number }>({ used: 0, limit: 25 });
  const [tailorBusyId, setTailorBusyId] = useState("");

  const [jobs, setJobs] = useState<api.JobPost[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  // Pagination lives below the grid — jump back to the top of the list when
  // the page changes so the new positions are immediately visible. (This
  // effect MUST come after the `page` declaration: the dependency array is
  // evaluated during render, and referencing `page` earlier crashes with a
  // temporal-dead-zone ReferenceError.)
  useEffect(() => {
    if (page > 1 || pageChangedRef.current) {
      pageChangedRef.current = true;
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);
  const pageSize = 40;
  const [totalPages, setTotalPages] = useState(1);
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
  const [taxonomyMeta, setTaxonomyMeta] = useState<TaxonomyMeta | null>(null);
  const jobsRequestId = useRef(0);
  const hasServerFilters = Boolean(
    activeCategory || activeRole || search || location || countryFilter || visaProgramFilter || visaOnly || timeFilter ||
    (personalized && (userPrefs?.target_roles?.length || 0) > 0)
  );

  // Load taxonomy once.
  useEffect(() => {
    api.getJobTaxonomy()
      .then((data) => {
        setTaxonomyMeta(data?.meta || null);
        setTargetCountries(Array.isArray(data?.target_countries) ? data.target_countries : []);
        setVisaPrograms(Array.isArray(data?.visa_programs) ? data.visa_programs : []);
        if (Array.isArray(data?.categories)) {
          setTaxonomy(data.categories.map((cat: any) => ({
            ...cat,
            roles: Array.isArray(cat?.roles)
              ? cat.roles.map((role: any) => ({
                  ...role,
                  visa: normalizeTaxonomyVisa(role?.visa),
                }))
              : [],
          })));
        }
      })
      .catch(() => {});
    api.getJobPipelineStatus()
      .then((status) => setPipelineStatus(status))
      .catch(() => {});

    // Pull the user's saved preferences ONCE on mount. We use them to
    // pre-fill the location filter + bias the first role pick. We do
    // not auto-apply on every preference change because the user might
    // want to manually broaden their search inside this session.
    api.getPreferences()
      .then((prefs) => {
        if (!prefs) return;
        const roles = (prefs.target_roles || []).filter(Boolean) as string[];
        const locations = (prefs.target_locations || []).filter(Boolean) as string[];
        setUserPrefs({ target_roles: roles, target_locations: locations });
        if (!prefsApplied && (roles.length || locations.length)) {
          setPersonalized(true);
          setPrefsApplied(true);
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    let active = true;
    api.getUserApplications()
      .then((rows) => {
        if (!active) return;
        const next: Record<string, "applied" | "interview" | "not_applied"> = {};
        for (const row of rows || []) {
          if (row.job_id && ["applied", "interview", "not_applied"].includes(row.status)) {
            next[String(row.job_id)] = row.status as "applied" | "interview" | "not_applied";
          }
        }
        setServerTrackedJobs(next);
      })
      .catch(() => {});
    return () => { active = false; };
  }, [appliedVersion]);

  useEffect(() => {
    let active = true;
    const refresh = () => {
      api.getTailorQueue()
        .then((response) => {
          if (!active) return;
          setTailorQueueIds(new Set((response.items || []).map((item) => String(item.job_id || ""))));
          setTailorUsage({ used: Number(response.used_today || 0), limit: Number(response.daily_limit || 25) });
        })
        .catch(() => {});
    };
    refresh();
    window.addEventListener("placeup:tailor-queue-changed", refresh as EventListener);
    return () => {
      active = false;
      window.removeEventListener("placeup:tailor-queue-changed", refresh as EventListener);
    };
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
    const requestId = jobsRequestId.current + 1;
    jobsRequestId.current = requestId;
    setLoading(true);
    setError(null);
    if (page === 1) {
      setJobs([]);
      setTotal(0);
      setTotalPages(1);
    }

    const params: Record<string, string | number | boolean> = { page, page_size: pageSize, max_years: 10, sort: sortBy, personalized, tz_offset: new Date().getTimezoneOffset() };
    if (resumeLink.hasResume) params.include_scores = true;
    if (search) params.search = search;
    if (location) params.location = location;
    if (visaOnly) params.visa_only = true;
    if (activeCategory && !activeRole) params.category = activeCategory;
    if (activeRole) params.role = activeRole;
    if (countryFilter) params.country = countryFilter;
    if (visaProgramFilter) params.visa_program = visaProgramFilter;
    if (timeFilter) {
      params.time_filter = timeFilter;
    }

    getJobsWithRetry(params, 2)
      .then((response: any) => {
        if (!active || jobsRequestId.current !== requestId) return;
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
              : Array.isArray(response?.items)
                ? response.items
                : Array.isArray(response?.data)
                  ? response.data
                  : [];
        setJobs(incoming);
        const reportedTotal = Array.isArray(response)
          ? response.length
          : (response?.total ?? response?.count ?? incoming.length);
        setTotal(typeof reportedTotal === "number" ? reportedTotal : incoming.length);
        const reportedPages = !Array.isArray(response) && typeof response?.total_pages === "number"
          ? response.total_pages
          : Math.max(1, Math.ceil((typeof reportedTotal === "number" ? reportedTotal : incoming.length) / pageSize));
        setTotalPages(Math.max(1, reportedPages));
      })
      .catch((err) => {
        if (active && jobsRequestId.current === requestId) {
          setError(friendlyJobError(err));
          if (page === 1) {
            setJobs([]);
            setTotal(0);
            setTotalPages(1);
          }
          // Keep failed first-page filters from showing stale All Jobs results.
        }
      })
      .finally(() => { if (active && jobsRequestId.current === requestId) setLoading(false); });

    return () => { active = false; };
  }, [activeCategory, activeRole, search, location, countryFilter, visaProgramFilter, visaOnly, timeFilter, personalized, sortBy, page, resumeVersion, resumeLink.hasResume, reloadKey]);

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
  }, [activeCategory, activeRole, search, location, countryFilter, visaProgramFilter, visaOnly, timeFilter, personalized]);

  const savedIds = useMemo(() => getSavedIds(), [savedVersion]);
  const trackedJobs = useMemo(() => ({ ...getTrackedJobs(), ...serverTrackedJobs }), [appliedVersion, serverTrackedJobs]);

  const filtered = jobs.filter((job) => {
    const id = String(job.id || "");
    const status = id ? trackedJobs[id] : "";
    return status !== "applied" && status !== "interview";
  });

  const allRoles = useMemo(
    () => Array.from(new Set(taxonomy.flatMap((cat) => cat.roles.map((role) => role.name)).filter(Boolean)))
      .sort((a, b) => a.localeCompare(b)),
    [taxonomy],
  );
  const visibleVisaPrograms = useMemo(
    () => visaPrograms.filter((program) => !countryFilter || program.country_code === countryFilter),
    [visaPrograms, countryFilter],
  );
  const priorityCountries = useMemo(
    () => ["US", "CA", "GB", "DE", "NL", "AU", "SG", "AE"]
      .map((code) => targetCountries.find((country) => country.code === code))
      .filter((country): country is CountryOption => Boolean(country)),
    [targetCountries],
  );
  const priorityRoutes = useMemo(
    () => {
      const preferred = [
        "US:h1b", "US:stem_opt", "US:opt", "CA:lmia_work_permit", "CA:global_talent_stream",
        "GB:skilled_worker", "IE:critical_skills", "DE:eu_blue_card", "NL:highly_skilled_migrant",
        "AU:skills_in_demand_482", "NZ:aewv", "SG:employment_pass", "AE:standard_work_permit",
        "JP:engineer_specialist", "FR:eu_blue_card", "ES:eu_blue_card", "SE:eu_blue_card",
      ];
      const ranked = [...visibleVisaPrograms].sort((a, b) => {
        const ak = `${a.country_code}:${a.code}`;
        const bk = `${b.country_code}:${b.code}`;
        const ai = preferred.indexOf(ak);
        const bi = preferred.indexOf(bk);
        return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
      });
      return ranked.slice(0, isMobile ? 5 : 12);
    },
    [visibleVisaPrograms, isMobile],
  );
  const allJobsCount = Number(pipelineStatus?.total_jobs || pipelineStatus?.active_jobs || total || 0);
  const openPositionsCount = hasServerFilters ? total : allJobsCount;
  const safeTotalPages = Math.max(1, totalPages);
  const pageNumbers = useMemo(
    () => paginationPages(page, safeTotalPages, isMobile ? 5 : 7),
    [page, safeTotalPages, isMobile],
  );
  const currentPageStart = total > 0 ? ((page - 1) * pageSize) + 1 : 0;
  const currentPageEnd = total > 0 ? Math.min(page * pageSize, total) : 0;
  const canGoPrevious = page > 1 && !loading;
  const canGoNext = page < safeTotalPages && !loading;
  const taxonomyRoleCount = Number(taxonomyMeta?.role_count || allRoles.length || 0);
  const scrapeTermCount = Number(taxonomyMeta?.scrape_term_count || 0);
  const targetRoleCount = userPrefs?.target_roles?.length || 0;

  const persistApplication = async (job: api.JobPost, status: "applied" | "interview" | "not_applied") => {
    const id = String(job.id || "");
    if (!id) return;
    const updated = { ...trackedJobs, [id]: status };
    localStorage.setItem("placeup_job_tracking", JSON.stringify(updated));
    setServerTrackedJobs((prev) => ({ ...prev, [id]: status }));
    setAppliedVersion((v) => v + 1);
    await api.saveUserApplication({
      job_id: id,
      title: job.title || "",
      company: job.company || "",
      location: job.location || "",
      job_url: resolveJobUrl(job),
      description: cleanPreview(job.description).slice(0, 12000),
      match_score: typeof job.match_score === "number" ? job.match_score : 0,
      status,
      position_open: true,
    });
  };

  const addToTailorQueue = async (job: api.JobPost) => {
    const id = String(job.id || "");
    if (!id || tailorQueueIds.has(id) || tailorUsage.used >= tailorUsage.limit) return;
    setTailorBusyId(id);
    try {
      const result = await api.addTailorQueueItem({
        job_id: id,
        title: job.title || "",
        company: job.company || "",
        location: job.location || "",
        job_url: resolveJobUrl(job),
        description: cleanPreview(job.description).slice(0, 50000),
        match_score: typeof job.match_score === "number" ? job.match_score : Number(job.match || 0),
      });
      setTailorQueueIds((prev) => new Set([...Array.from(prev), id]));
      setTailorUsage({ used: Number(result.used_today || 0), limit: Number(result.daily_limit || 25) });
    } catch (err) {
      setError((err as Error)?.message || "Could not add this job to the tailor queue.");
    } finally {
      setTailorBusyId("");
    }
  };

  const paginationControls = total > pageSize ? (
    <div
      style={{
        marginTop: 8,
        marginBottom: 8,
        padding: isMobile ? "12px 10px" : "14px 16px",
        borderRadius: 12,
        border: `1px solid ${J.line}`,
        background: "rgba(1,17,38,0.68)",
        boxShadow: J.shadow,
        display: "flex",
        flexDirection: isMobile ? "column" : "row",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 12,
        position: "relative",
        zIndex: 2,
      }}
    >
      <div style={{ color: J.t2, fontSize: 12, fontWeight: 750, fontFamily: F.sans }}>
        Showing {currentPageStart.toLocaleString()}-{currentPageEnd.toLocaleString()} of {total.toLocaleString()} positions
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6, flexWrap: "wrap" }}>
        <button
          disabled={!canGoPrevious}
          onClick={() => canGoPrevious && setPage((p) => Math.max(1, p - 1))}
          style={paginationButtonStyle(false, !canGoPrevious)}
        >
          Prev
        </button>
        {pageNumbers[0] > 1 && (
          <>
            <button onClick={() => setPage(1)} style={paginationButtonStyle(page === 1)}>1</button>
            {pageNumbers[0] > 2 && <span style={{ color: J.t3, fontSize: 12, fontWeight: 850 }}>...</span>}
          </>
        )}
        {pageNumbers.map((pageNumber) => (
          <button
            key={`jobs-page-${pageNumber}`}
            onClick={() => setPage(pageNumber)}
            style={paginationButtonStyle(pageNumber === page)}
          >
            {pageNumber}
          </button>
        ))}
        {pageNumbers[pageNumbers.length - 1] < safeTotalPages && (
          <>
            {pageNumbers[pageNumbers.length - 1] < safeTotalPages - 1 && <span style={{ color: J.t3, fontSize: 12, fontWeight: 850 }}>...</span>}
            <button onClick={() => setPage(safeTotalPages)} style={paginationButtonStyle(page === safeTotalPages)}>
              {safeTotalPages}
            </button>
          </>
        )}
        <button
          disabled={!canGoNext}
          onClick={() => canGoNext && setPage((p) => Math.min(safeTotalPages, p + 1))}
          style={paginationButtonStyle(false, !canGoNext)}
        >
          Next
        </button>
      </div>
    </div>
  ) : null;

  return (
    <div style={{ width: "100%", minWidth: 0, background: J.page, color: J.text, margin: "-28px", padding: isMobile ? "14px 12px 32px" : "24px 28px 48px", minHeight: "calc(100vh - 64px)" }}>
      {/* JOBS LIST */}
      <div style={{ display: "flex", flexDirection: "column", gap: 14, minWidth: 0, maxWidth: 1240, margin: "0 auto" }}>
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          style={{
            position: "relative",
            overflow: "hidden",
            borderRadius: 8,
            padding: isMobile ? 14 : 18,
            background: T.panel,
            border: `1px solid ${J.line}`,
            boxShadow: J.shadow,
            backdropFilter: "blur(24px)",
          }}
        >
          <div style={{ position: "absolute", inset: 0, background: "radial-gradient(circle at 12% 0%, rgba(237,125,43,0.20), transparent 36%), radial-gradient(circle at 88% 8%, rgba(199,90,18,0.16), transparent 32%)", pointerEvents: "none" }} />
          <div style={{ position: "relative", display: "grid", gridTemplateColumns: isTablet ? "1fr" : "minmax(0, 1.3fr) minmax(310px, 0.7fr)", gap: 18, alignItems: "stretch" }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ display: "inline-flex", alignItems: "center", gap: 8, height: 28, padding: "0 10px", borderRadius: 999, border: "1px solid rgba(237,125,43,0.30)", background: J.blueBg, color: J.blue, fontSize: 11, fontWeight: 800, fontFamily: F.sans }}>
                <Sparkles size={13} />
                Global visa search
              </div>
              <div style={{ marginTop: 10, color: J.text, fontSize: isMobile ? 22 : 30, fontWeight: 850, lineHeight: 1.08, letterSpacing: 0, fontFamily: F.sans }}>
                English-friendly roles by country and visa route
              </div>
              <div style={{ marginTop: 9, color: J.t2, fontSize: 13, lineHeight: 1.55, maxWidth: 680, fontFamily: F.sans }}>
                Search current roles across the 25-country target map, then narrow by local visa names like H-1B, LMIA, Skilled Worker, EU Blue Card, Employment Pass, and more.
              </div>
              <div style={{ marginTop: 14, display: "flex", flexWrap: "wrap", gap: 8 }}>
                {(targetCountries.length ? targetCountries : priorityCountries).map((country) => (
                  <button
                    key={country.code}
                    title={country.name || country.code}
                    onClick={() => { setCountryFilter(country.code === countryFilter ? "" : country.code); setVisaProgramFilter(""); setPage(1); }}
                    style={{ ...filterPillStyle(countryFilter === country.code), display: "inline-flex", alignItems: "center", gap: 6 }}
                  >
                    <FlagIcon code={country.code} size={13} /> {country.code}
                  </button>
                ))}
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              {[
                { icon: Globe2, label: "Countries", value: targetCountries.length || 25, color: T.blue },
                { icon: Route, label: "Visa routes", value: visaPrograms.length || 58, color: T.violet },
                { icon: Building2, label: "Open roles", value: openPositionsCount, color: "#86EFAC" },
                { icon: Languages, label: "English signals", value: "Active", color: T.fuchsia },
              ].map((item) => {
                const Icon = item.icon;
                return (
                  <div key={item.label} style={{ minHeight: 82, borderRadius: 12, border: `1px solid ${J.line}`, background: "rgba(1,17,38,0.54)", padding: 12, display: "flex", flexDirection: "column", justifyContent: "space-between", backdropFilter: "blur(18px)" }}>
                    <div style={{ width: 30, height: 30, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(245,234,200,0.06)", border: `1px solid ${J.line}` }}>
                      <Icon size={15} color={item.color} />
                    </div>
                    <div>
                      <div style={{ color: J.text, fontSize: 20, fontWeight: 850, lineHeight: 1, fontFamily: F.sans }}>{typeof item.value === "number" ? compactNumber(item.value) : item.value}</div>
                      <div style={{ color: J.t2, fontSize: 11, marginTop: 5, fontFamily: F.sans }}>{item.label}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          style={{ background: J.card, border: `1px solid ${J.line}`, borderRadius: 16, padding: isMobile ? "10px" : "12px 14px", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", boxShadow: J.shadow, backdropFilter: "blur(24px)" }}
        >
          <select
            value={activeRole || ""}
            onChange={(e) => { setActiveRole(e.target.value || null); setActiveCategory(null); setPage(1); }}
            style={controlStyle({ minWidth: isMobile ? "100%" : 220, fontSize: 13 })}
          >
            <option style={SELECT_DARK_STYLE} value="">All saved roles</option>
            {[...allRoles].sort((a, b) => a.localeCompare(b)).map((role) => <option style={SELECT_DARK_STYLE} key={role} value={role}>{role}</option>)}
          </select>
          <div style={controlStyle({ display: "flex", alignItems: "center", gap: 8, flex: "1 1 240px", minWidth: isMobile ? "100%" : 200 })}>
            <Search size={13} color={J.t3} />
            <input value={searchRaw} onChange={(e) => setSearchRaw(e.target.value)} placeholder="Search title, company, JD..."
              style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: J.text, fontSize: 13, fontFamily: F.sans }} />
          </div>
          <input value={locationRaw} onChange={(e) => setLocationRaw(e.target.value)} placeholder="Location"
            style={controlStyle({ width: isMobile ? "100%" : 140, flex: isMobile ? "1 1 100%" : "0 0 auto", fontSize: 13 })} />
          <select
            value={countryFilter}
            onChange={(e) => { setCountryFilter(e.target.value); setVisaProgramFilter(""); setPage(1); }}
            style={controlStyle({ width: isMobile ? "100%" : 180 })}
          >
            <option style={SELECT_DARK_STYLE} value="">Country: All countries</option>
            {[...targetCountries].sort((a, b) => a.name.localeCompare(b.name)).map((country) => <option style={SELECT_DARK_STYLE} key={country.code} value={country.code}>{countryFlag(country.code)} {country.code} - {country.name}</option>)}
          </select>
          <select
            value={visaProgramFilter}
            onChange={(e) => { setVisaProgramFilter(e.target.value); setPage(1); }}
            style={controlStyle({ width: isMobile ? "100%" : 230 })}
          >
            <option style={SELECT_DARK_STYLE} value="">Visa-friendly: All routes</option>
            {[...visibleVisaPrograms].sort((a, b) => routeLabel(a).localeCompare(routeLabel(b))).map((program) => <option style={SELECT_DARK_STYLE} key={`${program.country_code}-${program.code}`} value={program.code}>{countryFlag(program.country_code)} {program.country_code} - {program.name}</option>)}
          </select>
          <button onClick={() => { setVisaOnly(!visaOnly); setPage(1); }}
            style={{ ...controlStyle(), border: `1px solid ${visaOnly ? "rgba(34,197,94,0.32)" : J.line}`, background: visaOnly ? J.greenBg : J.card, color: visaOnly ? "#86EFAC" : J.t2, cursor: "pointer", display: "flex", alignItems: "center", gap: 5 }}>
            <Filter size={12} /> Visa-friendly
          </button>
          <select
            value={timeFilter}
            onChange={(e) => { setTimeFilter(e.target.value); setPage(1); }}
            style={controlStyle({ width: isMobile ? "100%" : 136 })}
          >
            {TIME_OPTIONS.map((chip) => <option style={SELECT_DARK_STYLE} key={chip.label} value={chip.value}>{chip.label}</option>)}
          </select>
          <select
            value={sortBy}
            onChange={(e) => { setSortBy(e.target.value as "match" | "recent"); setPage(1); }}
            style={controlStyle({ width: isMobile ? "100%" : 168 })}
            title="Sort results"
          >
            <option style={SELECT_DARK_STYLE} value="match">Sort: Best match</option>
            <option style={SELECT_DARK_STYLE} value="recent">Sort: Recently posted</option>
          </select>
          <button
            onClick={() => {
              setReloadKey((value) => value + 1);
              api.getJobPipelineStatus().then((status) => setPipelineStatus(status)).catch(() => {});
            }}
            style={{ ...controlStyle(), cursor: "pointer", fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center", gap: 7 }}
          >
            <RefreshCw size={13} />
            Refresh
          </button>
          <div style={{ flexBasis: "100%", color: J.t2, fontSize: 11, fontFamily: F.sans }}>
            {filtered.length.toLocaleString()} visible
            {openPositionsCount ? ` / ${openPositionsCount.toLocaleString()} open` : ""}
            {taxonomyRoleCount ? ` - ${taxonomyRoleCount.toLocaleString()} current roles` : ""}
            {scrapeTermCount ? ` / ${scrapeTermCount.toLocaleString()} scrape terms` : ""}
            {personalized && targetRoleCount ? ` - personalized from ${targetRoleCount} saved roles` : ""}
            {pipelineStatus?.last_scraped_at ? ` - refreshed ${formatPosted(pipelineStatus.last_scraped_at)}` : ""}
          </div>
          {priorityRoutes.length > 0 && (
            <div style={{ flexBasis: "100%", display: "flex", gap: 7, flexWrap: "wrap", alignItems: "center" }}>
              <span style={{ color: J.t2, fontSize: 11, fontFamily: F.sans, marginRight: 2 }}>Popular routes</span>
              {priorityRoutes.map((program) => (
                <button
                  key={`route-${program.country_code}-${program.code}`}
                  onClick={() => { setCountryFilter(program.country_code); setVisaProgramFilter(program.code === visaProgramFilter ? "" : program.code); setPage(1); }}
                  style={{
                    height: 28,
                    padding: "0 9px",
                    borderRadius: 999,
                    border: `1px solid ${visaProgramFilter === program.code ? "rgba(237,125,43,0.32)" : J.line}`,
                    background: visaProgramFilter === program.code ? J.blueBg : J.card,
                    color: visaProgramFilter === program.code ? J.blue : J.t2,
                    fontSize: 11,
                    fontWeight: 750,
                    fontFamily: F.sans,
                    cursor: "pointer",
                  }}
                >
                  {routeLabel(program)}
                </button>
              ))}
            </div>
          )}
        </motion.div>

        {resumeLink.checked && (
          <div style={{
            display: "flex", flexDirection: isMobile ? "column" : "row", alignItems: isMobile ? "stretch" : "center", justifyContent: "space-between", gap: 12,
            padding: "12px 14px", borderRadius: 8,
            border: `1px solid ${resumeLink.hasResume ? "rgba(34,197,94,0.28)" : "rgba(248,113,113,0.28)"}`,
            background: resumeLink.hasResume ? "rgba(34,197,94,0.08)" : "rgba(248,113,113,0.08)",
            color: J.t2, fontFamily: F.sans,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
              <div style={{
                width: 30, height: 30, borderRadius: 9, flexShrink: 0,
                display: "flex", alignItems: "center", justifyContent: "center",
                background: resumeLink.hasResume ? "rgba(34,197,94,0.12)" : "rgba(248,113,113,0.12)",
                border: `1px solid ${resumeLink.hasResume ? "rgba(34,197,94,0.28)" : "rgba(248,113,113,0.28)"}`,
              }}>
                <ShieldCheck size={14} color={resumeLink.hasResume ? "#22c55e" : T.red} />
              </div>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 800, color: J.text, lineHeight: 1.25 }}>
                  {resumeLink.hasResume ? "Active resume linked to job matching" : "Resume is not linked to job matching"}
                </div>
                <div style={{ fontSize: 11, color: J.t2, lineHeight: 1.4, marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {resumeLink.hasResume
                    ? `${resumeLink.name || "Resume"}${resumeLink.score ? ` - Resume score ${resumeLink.score}` : ""}`
                    : resumeLink.error || "Upload or re-upload a resume from the Resumes tab."}
                </div>
              </div>
            </div>
            {!resumeLink.hasResume && (
              <button
                onClick={() => { window.location.href = "/dashboard/resumes"; }}
                style={{ height: 32, padding: "0 12px", borderRadius: 8, border: "none", background: T.grad, color: "#fff", fontSize: 12, fontWeight: 800, fontFamily: F.sans, cursor: "pointer", flexShrink: 0, width: isMobile ? "100%" : "auto" }}
              >
                Upload Resume
              </button>
            )}
          </div>
        )}

        {/* Active filters strip */}
        {(activeRole || activeCategory || search || location || countryFilter || visaProgramFilter || visaOnly || timeFilter) && (
          <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
            <span style={{ fontSize: 11, color: J.t2, fontFamily: F.sans, fontWeight: 750 }}>{filtered.length} of {total} positions</span>
            {activeCategory && (
              <span style={activeFilterChipStyle()}>
                Category: {activeCategory}
              </span>
            )}
            {activeRole && (
              <span style={activeFilterChipStyle()}>
                Role: {activeRole}
                <button onClick={() => { setActiveRole(null); setPage(1); }} style={clearChipButtonStyle()}><X size={10} /></button>
              </span>
            )}
            {search && (
              <span style={activeFilterChipStyle()}>
                Search: {search}
                <button onClick={() => { setSearchRaw(""); setSearch(""); setPage(1); }} style={clearChipButtonStyle()}><X size={10} /></button>
              </span>
            )}
            {location && (
              <span style={activeFilterChipStyle()}>
                Location: {location}
                <button onClick={() => { setLocationRaw(""); setLocation(""); setPage(1); }} style={clearChipButtonStyle()}><X size={10} /></button>
              </span>
            )}
            {visaOnly && (
              <span style={{ ...activeFilterChipStyle(), background: J.greenBg, color: "#86EFAC", border: "1px solid rgba(34,197,94,0.30)" }}>
                Visa-friendly
                <button onClick={() => { setVisaOnly(false); setPage(1); }} style={{ ...clearChipButtonStyle(), color: "#86EFAC" }}><X size={10} /></button>
              </span>
            )}
            {countryFilter && (
              <span style={activeFilterChipStyle()}>
                Country: {countryFlag(countryFilter)} {countryFilter}
                <button onClick={() => { setCountryFilter(""); setVisaProgramFilter(""); setPage(1); }} style={clearChipButtonStyle()}><X size={10} /></button>
              </span>
            )}
            {visaProgramFilter && (
              <span style={activeFilterChipStyle()}>
                Visa: {visibleVisaPrograms.find((program) => program.code === visaProgramFilter)?.name || visaProgramFilter}
                <button onClick={() => { setVisaProgramFilter(""); setPage(1); }} style={clearChipButtonStyle()}><X size={10} /></button>
              </span>
            )}
            {timeFilter && (
              <span style={activeFilterChipStyle()}>
                Time: {TIME_OPTIONS.find((chip) => chip.value === timeFilter)?.label || timeFilter}
                <button onClick={() => { setTimeFilter(""); setPage(1); }} style={clearChipButtonStyle()}><X size={10} /></button>
              </span>
            )}
          </div>
        )}

        {error && (
          <div style={{ padding: "14px 16px", borderRadius: 12, background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.28)", color: J.text, fontFamily: F.sans, fontSize: 13 }}>
            <div style={{ fontWeight: 800, marginBottom: 4, color: T.red }}>Couldn't load jobs</div>
            <div style={{ color: J.t2, marginBottom: 10 }}>{error}</div>
            <button
              onClick={() => setReloadKey((value) => value + 1)}
              style={{ height: 32, padding: "0 12px", borderRadius: 8, border: `1px solid ${J.line}`, background: "rgba(245,234,200,0.05)", color: J.text, fontSize: 12, fontWeight: 800, fontFamily: F.sans, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 6 }}
            >
              <RefreshCw size={12} />
              Retry
            </button>
          </div>
        )}

        {/* Job cards (pagination lives below the grid) */}
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: 14 }}>
          {loading && jobs.length === 0 && (
            <div style={{ gridColumn: "1 / -1", background: J.card, border: `1px solid ${J.line}`, borderRadius: 16, boxShadow: J.shadow, backdropFilter: "blur(24px)" }}>
              <LoadingLogo label="Loading jobs" />
            </div>
          )}
          {!loading && filtered.length === 0 && !error && (
            <div style={{ gridColumn: "1 / -1", textAlign: "center", padding: 40, background: J.card, border: `1px solid ${J.line}`, borderRadius: 16, color: J.t2, fontFamily: F.sans, boxShadow: J.shadow, backdropFilter: "blur(24px)" }}>
              <div style={{ fontSize: 14, fontWeight: 850, color: J.text, marginBottom: 6 }}>No jobs match the current filters.</div>
              <div style={{ fontSize: 12, color: J.t2, marginBottom: 12 }}>Try clearing the search, location, or time filter.</div>
              <button
                onClick={() => { setSearchRaw(""); setSearch(""); setLocationRaw(""); setLocation(""); setCountryFilter(""); setVisaProgramFilter(""); setVisaOnly(false); setTimeFilter(""); setActiveCategory(null); setActiveRole(null); setPersonalized(true); setPage(1); }}
                style={{ padding: "8px 14px", borderRadius: 8, border: `1px solid ${J.line}`, background: "rgba(245,234,200,0.05)", color: J.blue, fontSize: 12, fontWeight: 800, fontFamily: F.sans, cursor: "pointer" }}
              >Reset filters</button>
            </div>
          )}
          {filtered.map((job, i) => {
            const visaBadges = normalizeVisa(job.visa);
            const match = job.match_score ?? job.match ?? null;
            const id = String(job.id || "");
            const preview = cleanPreview(job.description).slice(0, 260);
            const role = (job as any).role || (job as any).taxonomy_category || job.status || "Active";
            const jobUrl = resolveJobUrl(job);
            const logo = companyLogoUrl(job);
            const visaRecord = getVisaRecord(job);
            const visaCountry = typeof visaRecord.visa_country === "string" && visaRecord.visa_country ? visaRecord.visa_country : "";
            const visaCountryName = typeof visaRecord.visa_country_name === "string" && visaRecord.visa_country_name ? visaRecord.visa_country_name : countryName(visaCountry, targetCountries);
            const sponsorVerified = Boolean(visaRecord.sponsor_verified || visaRecord.h1b_verified);
            const englishFriendly = Boolean(visaRecord.english_friendly);
            return (
              <motion.div
                key={id}
                initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}
                whileHover={{ y: -4, boxShadow: "0 16px 36px rgba(1,17,38,0.35)" }}
                onClick={() => onJobClick(id)}
                style={{
                  minHeight: isMobile ? 248 : 176,
                  background: "linear-gradient(135deg, rgba(1,17,38,0.86), rgba(64,18,18,0.58))",
                  border: `1px solid ${J.line}`,
                  boxShadow: "0 12px 28px rgba(1,17,38,0.24)",
                  borderRadius: 16,
                  padding: 14,
                  cursor: "pointer",
                  display: "grid",
                  gridTemplateColumns: "minmax(0, 1fr)",
                  gap: 12,
                  alignItems: "stretch",
                  color: J.text,
                  backdropFilter: "blur(24px)",
                }}
              >
                <div style={{ minWidth: 0, display: "flex", flexDirection: "column", gap: 9 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 14, alignItems: "flex-start", minHeight: 54 }}>
                    <div style={{ display: "flex", gap: 12, alignItems: "flex-start", minWidth: 0, flex: 1 }}>
                      {/* Company avatar — first-letter gradient circle.
                          Cheaper than fetching real logos and looks consistent
                          across every card. Color seed from the company name
                          so each company gets the same color every time. */}
                      <div
                        aria-hidden="true"
                        style={{
                          position: "relative", overflow: "hidden",
                          width: 44, height: 44, borderRadius: 11, flexShrink: 0,
                          display: "flex", alignItems: "center", justifyContent: "center",
                          fontFamily: F.sans, fontWeight: 700, fontSize: 17, color: "#fff",
                          background: `linear-gradient(135deg, ${
                            ["#ED7D2B", "#F2A341", "#C75A12", "#0891B2", "#059669", "#475569"][
                              Math.abs((job.company || "X").charCodeAt(0)) % 6
                            ]
                          }, #011126)`,
                          boxShadow: "0 4px 14px rgba(237,125,43,0.26)",
                        }}
                      >
                        {(job.company || "?").trim().charAt(0).toUpperCase()}
                        {logo && (
                          <img
                            src={logo}
                            alt=""
                            loading="lazy"
                            onError={(e) => { e.currentTarget.style.display = "none"; }}
                            style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "contain", padding: 6, background: "rgba(245,234,200,0.92)" }}
                          />
                        )}
                      </div>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ fontSize: 14, fontWeight: 850, color: J.text, fontFamily: F.sans, lineHeight: 1.28, marginBottom: 6, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{job.title || "Untitled role"}</div>
                        <div style={{ fontSize: 12, color: J.t2, fontFamily: F.sans, fontWeight: 650, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{job.company || "Unknown"}</div>
                      </div>
                    </div>
                    <ATSRing score={match} size={48} />
                  </div>
                  <div style={{ height: 1, background: "rgba(237,125,43,0.22)", marginTop: 2 }} />
                  <div style={{ display: "flex", gap: 8, fontSize: 11, color: J.t2, fontFamily: F.sans, flexWrap: "wrap", alignItems: "center" }}>
                    <span style={{ display: "inline-flex", gap: 5, alignItems: "center", minWidth: 0 }}><FlagIcon code={visaCountry} size={13} /><span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{job.location || visaCountryName || "Remote"}</span></span>
                    <span style={{ display: "inline-flex", gap: 5, alignItems: "center", padding: "3px 8px", borderRadius: 999, background: "rgba(237,125,43,0.08)", color: "#F5EAC8", border: "1px solid rgba(237,125,43,0.18)", whiteSpace: "nowrap" }}>
                      <Clock size={11} />
                      {publishDateLabel(job).replace("Publish date ", "")}
                    </span>
                  </div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {(() => {
                      // Highlight roles the user is actually targeting - their
                      // saved target roles get the orange brand treatment so
                      // matching cards stand out at a glance.
                      const isTargetRole = (userPrefs?.target_roles || []).some(
                        (t) => t && String(role).toLowerCase() === t.toLowerCase()
                      );
                      return (
                        <span style={{
                          display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, fontWeight: 750,
                          padding: "4px 8px", borderRadius: 999, fontFamily: F.sans,
                          background: isTargetRole ? "rgba(237,125,43,0.16)" : J.blueBg,
                          color: isTargetRole ? "#F2A341" : J.blue,
                          border: isTargetRole ? "1px solid rgba(237,125,43,0.4)" : "1px solid transparent",
                          boxShadow: isTargetRole ? "0 0 10px rgba(237,125,43,0.18)" : "none",
                        }}>
                          <Building2 size={11} />{role}{isTargetRole ? " *" : ""}
                        </span>
                      );
                    })()}
                    {englishFriendly && <span style={{ fontSize: 11, fontWeight: 750, padding: "4px 8px", borderRadius: 999, background: J.greenBg, color: "#86EFAC", fontFamily: F.sans }}>English-friendly</span>}
                    {sponsorVerified && <span style={{ fontSize: 11, fontWeight: 750, padding: "4px 8px", borderRadius: 999, background: "rgba(34,197,94,0.08)", color: "#86EFAC", fontFamily: F.sans }}>{sourceLabel(visaRecord.sponsor_source)}</span>}
                  </div>
                  {preview && (
                    <div style={{ fontSize: 12, color: J.t2, fontFamily: F.sans, lineHeight: 1.55, display: "-webkit-box", WebkitLineClamp: isMobile ? 3 : 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                      {preview}
                    </div>
                  )}
                  <div style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", gap: 10, marginTop: "auto" }}>
                    <div style={{ display: "flex", gap: 5, flexWrap: "wrap", minWidth: 0 }}>
                      {visaBadges.slice(0, 4).map((v) => {
                        const s = VISA_BADGES[v] ?? { bg: "#DCFCE7", color: "#15803D", border: "#BBF7D0" };
                        return <span key={v} style={{ fontSize: 10, fontWeight: 800, padding: "3px 8px", borderRadius: 999, background: s.bg, color: s.color, border: `1px solid ${s.border}`, fontFamily: F.sans }}>{v.replace(`${visaCountry}: `, "")}</span>;
                      })}
                      {visaBadges.length === 0 && <span style={{ fontSize: 10, color: J.t3, fontFamily: F.sans }}>Visa not verified</span>}
                    </div>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, borderTop: `1px solid ${J.line}`, paddingTop: 9 }}>
                      <span style={{ color: J.t3, fontSize: 10, fontFamily: F.sans }}>{getScoreMeta(match).label}</span>
                      <div style={{ display: "flex", gap: 6, flexShrink: 0, flexWrap: "wrap", justifyContent: "flex-end" }}>
                      <button onClick={(e) => {
                        e.stopPropagation();
                        const saved = Array.from(savedIds);
                        const next = savedIds.has(id) ? saved.filter((item) => item !== id) : [...saved, id];
                        localStorage.setItem("placeup_saved_jobs", JSON.stringify(next));
                        setSavedVersion((v) => v + 1);
                      }} style={{ width: 30, height: 28, borderRadius: 7, border: `1px solid ${savedIds.has(id) ? "rgba(248,113,113,0.35)" : J.line}`, background: savedIds.has(id) ? "rgba(248,113,113,0.10)" : "rgba(245,234,200,0.05)", color: savedIds.has(id) ? T.red : J.t2, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }} title={savedIds.has(id) ? "Unsave" : "Save job"}><Bookmark size={13} fill={savedIds.has(id) ? T.red : "none"}/></button>
                      <button onClick={async (e) => {
                        e.stopPropagation();
                        const cur = trackedJobs[id];
                        const nextStatus = cur === "applied" ? "interview" : "applied";
                        await persistApplication(job, nextStatus);
                      }} style={{ height: 28, padding: "0 9px", borderRadius: 7, border: `1px solid ${trackedJobs[id] === "interview" ? "rgba(237,125,43,0.35)" : trackedJobs[id] === "applied" ? "rgba(34,197,94,0.35)" : J.line}`, background: trackedJobs[id] === "interview" ? "rgba(237,125,43,0.10)" : trackedJobs[id] === "applied" ? "rgba(34,197,94,0.10)" : "rgba(245,234,200,0.05)", color: trackedJobs[id] === "interview" ? "#93C5FD" : trackedJobs[id] === "applied" ? "#86EFAC" : J.t2, fontSize: 10, fontWeight: 800, cursor: "pointer", fontFamily: F.sans, whiteSpace: "nowrap" }} title={trackedJobs[id] === "interview" ? "Interview stage" : trackedJobs[id] === "applied" ? "Applied - click to move to Interview" : "Track application status"}>
                        {trackedJobs[id] === "interview" ? "Interview" : trackedJobs[id] === "applied" ? "Applied" : "Track"}
                      </button>
                      <button
                        disabled={tailorQueueIds.has(id) || tailorBusyId === id || tailorUsage.used >= tailorUsage.limit}
                        onClick={async (e) => {
                          e.stopPropagation();
                          await addToTailorQueue(job);
                        }}
                        style={{
                          height: 28,
                          padding: "0 9px",
                          borderRadius: 7,
                          border: `1px solid ${tailorQueueIds.has(id) ? "rgba(34,197,94,0.30)" : "rgba(237,125,43,0.28)"}`,
                          background: tailorQueueIds.has(id) ? "rgba(34,197,94,0.10)" : "rgba(237,125,43,0.10)",
                          color: tailorQueueIds.has(id) ? "#86EFAC" : "#F2A341",
                          fontSize: 10,
                          fontWeight: 800,
                          cursor: tailorQueueIds.has(id) || tailorUsage.used >= tailorUsage.limit ? "not-allowed" : "pointer",
                          opacity: tailorUsage.used >= tailorUsage.limit && !tailorQueueIds.has(id) ? 0.55 : 1,
                          fontFamily: F.sans,
                          display: "flex",
                          alignItems: "center",
                          gap: 4,
                          whiteSpace: "nowrap",
                        }}
                        title={tailorQueueIds.has(id) ? "Already in tailor queue" : tailorUsage.used >= tailorUsage.limit ? "Daily tailor queue limit reached" : "Add to tailor queue"}
                      >
                        <Wand2 size={11} /> {tailorQueueIds.has(id) ? "Queued" : "Tailor"}
                      </button>
                      <button
                        onClick={async (e) => {
                          e.stopPropagation();
                          const url = jobUrl || `https://www.google.com/search?q=${encodeURIComponent(`${job.company || ""} ${job.title || ""} apply`)}`;
                          window.open(url, "_blank", "noopener,noreferrer");
                        }}
                        style={{ height: 28, padding: "0 10px", borderRadius: 7, border: `1px solid ${J.line}`, background: "rgba(245,234,200,0.05)", color: J.t2, fontSize: 10, cursor: "pointer", fontFamily: F.sans, fontWeight: 800, display: "flex", alignItems: "center", gap: 4 }}
                      ><ExternalLink size={11}/> Apply</button>
                      <button onClick={(e) => { e.stopPropagation(); onJobClick(id); }} style={{ height: 28, padding: "0 10px", borderRadius: 7, border: "none", background: T.grad, color: "#fff", fontSize: 10, cursor: "pointer", fontFamily: F.sans, fontWeight: 800, display: "flex", alignItems: "center", gap: 4 }}><ExternalLink size={11}/> View</button>
                      </div>
                    </div>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
        {paginationControls}
      </div>
    </div>
  );
}
