import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { useSearchParams } from "react-router";
import { motion } from "motion/react";
import { Search, Filter, X, Bookmark, ExternalLink, ShieldCheck, RefreshCw, Globe2, Route, Languages, Building2, Sparkles, Clock, Wand2 } from "lucide-react";
import * as api from "../../lib/api";
import { useAuth } from "../../context/AuthContext";
import { LoadingLogo } from "../LoadingLogo";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
// Aligned to the main-page cream + orange theme (navy surfaces, cream text,
// orange accent). Legacy accent keys (violet/blue/fuchsia) are kept but mapped
// to orange so every existing usage recolors automatically.
const T = {
  text: "var(--pu-f1f5f9-t)", t2: "var(--pu-226-232-240-072)", t3: "var(--pu-148-163-184-075)",
  border: "var(--pu-148-163-184-01)", glass: "var(--pu-15-30-55-055)",
  grad: "linear-gradient(135deg, var(--pu-2563eb), var(--pu-0ea5e9))",
  panel: "linear-gradient(135deg, var(--pu-1-17-38-092), var(--pu-15-30-55-05), var(--pu-122-52-8-028))",
  violet: "var(--pu-3b82f6-t)", blue: "var(--pu-60a5fa-t)", fuchsia: "var(--pu-3b82f6-b)", red: "var(--pu-3b82f6-t)", burnt: "var(--pu-1d4ed8)", dark: "var(--pu-0b1220)",
};

const J = {
  page: "transparent",
  card: "var(--pu-15-30-55-045)",
  line: "var(--pu-148-163-184-01)",
  text: "var(--pu-f1f5f9-t)",
  t2: "var(--pu-226-232-240-072)",
  t3: "var(--pu-148-163-184-075)",
  blue: "var(--pu-3b82f6-t)",
  blueBg: "var(--pu-59-130-246-012)",
  green: "var(--pu-3fb477)",
  greenBg: "var(--pu-63-180-119-012)",
  shadow: "0 18px 44px var(--pu-1-17-38-028)",
};

const TIME_OPTIONS = [
  { label: "Recent (24h)", value: "24h" },
  { label: "Last 8h", value: "8h" },
  { label: "Today", value: "today" },
  { label: "Yesterday", value: "yesterday" },
  { label: "Week", value: "week" },
  { label: "Month", value: "month" },
];
const SELECT_DARK_STYLE: CSSProperties = { background: "var(--pu-0b1220)", color: "var(--pu-f1f5f9-t)" };
const VISA_BADGES: Record<string, { bg: string; color: string; border: string }> = {
  "H-1B":   { bg: "var(--pu-59-130-246-015)", color: "var(--pu-f1f5f9-t)", border: "var(--pu-59-130-246-035)" },
  "OPT":    { bg: "var(--pu-37-99-235-012)", color: "var(--pu-93c5fd-t)", border: "var(--pu-59-130-246-03)" },
  "STEM":   { bg: "var(--pu-199-90-18-012)",  color: "var(--pu-f9a8d4-t)", border: "var(--pu-240-171-252-03)" },
  "Vol":    { bg: "var(--pu-34-197-94-01)", color: "var(--pu-22c55e-t)", border: "var(--pu-34-197-94-03)" },
  "No sponsorship": { bg: "var(--pu-148-163-184-008)", color: "var(--pu-148-163-184-062)", border: "var(--pu-148-163-184-018)" },
  "English-friendly": { bg: "var(--pu-34-197-94-01)", color: "var(--pu-86efac-t)", border: "var(--pu-34-197-94-026)" },
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
    // A2: treat 0 / negative as "no data" — never render $0K–$0K.
    const rawMin = (salary as any).min_salary, rawMax = (salary as any).max_salary;
    const min = typeof rawMin === "number" && rawMin > 0 ? rawMin : undefined;
    const max = typeof rawMax === "number" && rawMax > 0 ? rawMax : undefined;
    if (min !== undefined && max !== undefined) return `$${Math.round(min/1000)}K–$${Math.round(max/1000)}K`;
    if (min !== undefined) return `$${Math.round(min/1000)}K+`;
    if (max !== undefined) return `Up to $${Math.round(max/1000)}K`;
    if ((salary as any).display && !/\$0K/.test(String((salary as any).display))) return String((salary as any).display);
  }
  return "—";
}

interface TaxonomyRole { name: string; synonyms: string[] | string; visa: string[]; hot: boolean }
interface TaxonomyCategory { name: string; icon: string; roles: TaxonomyRole[] }
interface TaxonomyMeta {
  category_count?: number;
  role_count?: number;
  role_pipeline_count?: number;
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

/* ── Locale-aware dates ────────────────────────────────────────────────
   Dates render in the convention of the user's targeted country (their
   active country filter, else their first target location, else the
   browser default). E.g. US → 07/10/2026, DE → 10.07.2026. */
const COUNTRY_LOCALES: Record<string, string> = {
  US: "en-US", CA: "en-CA", GB: "en-GB", IE: "en-IE", AU: "en-AU", NZ: "en-NZ",
  IN: "en-IN", SG: "en-SG", HK: "en-HK", DE: "de-DE", AT: "de-AT", CH: "de-CH",
  NL: "nl-NL", BE: "nl-BE", FR: "fr-FR", LU: "fr-LU", ES: "es-ES", PT: "pt-PT",
  IT: "it-IT", SE: "sv-SE", DK: "da-DK", NO: "nb-NO", FI: "fi-FI", PL: "pl-PL",
  EE: "et-EE", CZ: "cs-CZ", QA: "ar-QA", SA: "ar-SA", AE: "ar-AE", JP: "ja-JP",
  KR: "ko-KR", TW: "zh-TW",
};

let activeDateLocale: string | undefined;

function setActiveDateLocale(countryCode: string | undefined | null) {
  activeDateLocale = (countryCode && COUNTRY_LOCALES[countryCode.toUpperCase()]) || undefined;
}

function resolveCountryFromLocations(locations: string[], countries: CountryOption[]): string | undefined {
  for (const loc of locations) {
    const needle = String(loc || "").trim().toLowerCase();
    if (!needle) continue;
    const hit = countries.find(
      (c) => c.code.toLowerCase() === needle || c.name.toLowerCase() === needle || needle.includes(c.name.toLowerCase()),
    );
    if (hit) return hit.code;
  }
  return undefined;
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
  return date.toLocaleDateString(activeDateLocale, { month: "short", day: "numeric", year: "numeric" });
}

function jobPostedRaw(job: api.JobPost): unknown {
  // last_seen_at is a verification timestamp, not a publication date. Calling
  // it "Posted today" made old jobs look new whenever the scraper revisited
  // them. Use the real posting date, or the date PlaceUp first discovered it.
  return job.posted_at || job.posted || job.first_seen_at;
}

function jobDateLabel(job: api.JobPost): string {
  const raw = jobPostedRaw(job);
  if (!raw) return "Publish date unavailable";
  const prefix = (job.posted_at || job.posted) ? "Posted" : "Added";
  return `${prefix} ${formatPosted(raw)}`;
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
      style={{ borderRadius: 2, display: "inline-block", verticalAlign: "-2px", boxShadow: "0 0 0 1px var(--pu-148-163-184-015)" }}
    />
  );
}

function publishDateLabel(job: api.JobPost): string {
  const raw = jobPostedRaw(job);
  if (!raw) return "Publish date —";
  const date = new Date(String(raw));
  if (Number.isNaN(date.getTime())) return `Publish date ${String(raw).slice(0, 18)}`;
  // Numeric date in the user's targeted-country convention (en-US →
  // MM/DD/YYYY, de-DE → DD.MM.YYYY, en-GB → DD/MM/YYYY, ...).
  const prefix = (job.posted_at || job.posted) ? "Publish date" : "First collected";
  return `${prefix} ${date.toLocaleDateString(activeDateLocale, { day: "2-digit", month: "2-digit", year: "numeric" })}`;
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
    height: 40,
    padding: "0 13px",
    borderRadius: 10,
    border: `1px solid ${J.line}`,
    background: "var(--pu-148-163-184-004)",
    color: J.text,
    fontSize: 12.5,
    fontWeight: 600,
    fontFamily: F.sans,
    outline: "none",
    boxShadow: "none",
    backdropFilter: "blur(16px)",
    transition: "border-color 0.15s ease, background 0.15s ease",
    ...extra,
  };
}

function filterPillStyle(active = false): CSSProperties {
  return {
    height: 30,
    padding: "0 10px",
    borderRadius: 999,
    border: `1px solid ${active ? "var(--pu-34-197-94-03)" : J.line}`,
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
    border: "1px solid var(--pu-59-130-246-028)",
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
    border: `1px solid ${active ? "var(--pu-59-130-246-046)" : J.line}`,
    background: active ? "var(--pu-59-130-246-018)" : "var(--pu-148-163-184-005)",
    color: disabled ? J.t3 : active ? "var(--pu-f1f5f9-t)" : J.t2,
    fontSize: 12,
    fontWeight: 850,
    fontFamily: F.sans,
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.52 : 1,
    boxShadow: active ? "0 12px 30px var(--pu-59-130-246-02)" : "none",
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

function resolveJobUrl(job: api.JobPost): string {
  const j: any = job;
  const candidates = [j.job_url, j.source_url, j.job_url_direct, j.apply_url, j.url, j.company_url, j.external_url];
  const first = candidates.find((url) => typeof url === "string" && url.trim().length > 0);
  if (!first) return "";
  const trimmed = String(first).trim();
  return /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
}

function applyLabelForJob(job: api.JobPost, jobUrl: string): string {
  const source = String((job as any).source || (job as any).source_name || "").toLowerCase();
  const boardLabels: Array<[string, string]> = [
    ["linkedin", "LinkedIn"],
    ["indeed", "Indeed"],
    ["dice", "Dice"],
    ["handshake", "Handshake"],
    ["glassdoor", "Glassdoor"],
    ["ziprecruiter", "ZipRecruiter"],
  ];
  const sourceHit = boardLabels.find(([needle]) => source.includes(needle));
  if (sourceHit) return `Apply on ${sourceHit[1]}`;
  if (!jobUrl) return "Search this role";
  try {
    const host = new URL(jobUrl).hostname.toLowerCase();
    const hostHit = boardLabels.find(([needle]) => host.includes(needle));
    if (hostHit) return `Apply on ${hostHit[1]}`;
  } catch {
    return "Apply";
  }
  return "Apply on Company";
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
  const color = !hasScore ? J.t3 : safeScore >= 80 ? "var(--pu-22c55e-b)" : safeScore >= 60 ? J.blue : safeScore >= 40 ? "var(--pu-f59e0b-b)" : "var(--pu-f87171-b)";
  const textColor = hasScore ? color : J.t3;
  return (
    <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
      <svg viewBox={`0 0 ${size} ${size}`} style={{ width: "100%", height: "100%", transform: "rotate(-90deg)" }}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="var(--pu-148-163-184-02)" strokeWidth="5" />
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

function getScoreMeta(score: number | null | undefined, scoreType?: string) {
  if (typeof score !== "number" || !Number.isFinite(score)) {
    if (scoreType === "insufficient_jd") {
      return {
        label: "Job details incomplete",
        detail: "Waiting for a complete description",
        color: T.t3,
        bg: "var(--pu-148-163-184-005)",
        border: T.border,
      };
    }
    if (scoreType === "resume_required") {
      return {
        label: "Resume ATS unavailable",
        detail: "Upload or re-upload resume",
        color: T.t3,
        bg: "var(--pu-148-163-184-005)",
        border: T.border,
      };
    }
    return {
      label: "Resume needed",
      detail: "Upload resume for score",
      color: T.t3,
      bg: "var(--pu-148-163-184-005)",
      border: T.border,
    };
  }
  if (scoreType === "baseline_ats") {
    return { label: "ATS estimate", detail: "Resume score still loading", color: T.t2, bg: "var(--pu-148-163-184-006)", border: T.border };
  }
  if (scoreType === "insufficient_jd") {
    return { label: "ATS estimate", detail: "Job description still being enriched", color: T.t2, bg: "var(--pu-148-163-184-006)", border: T.border };
  }
  if (score >= 80) return { label: "Strong match", detail: "High keyword overlap", color: "var(--pu-22c55e-t)", bg: "var(--pu-34-197-94-01)", border: "var(--pu-34-197-94-025)" };
  if (score >= 60) return { label: "Good match", detail: "Review missing keywords", color: T.violet, bg: "var(--pu-59-130-246-012)", border: "var(--pu-59-130-246-028)" };
  if (score >= 40) return { label: "Partial match", detail: "Resume may need tailoring", color: T.burnt, bg: "var(--pu-245-158-11-012)", border: "var(--pu-245-158-11-028)" };
  return { label: "Low match", detail: "Large skill gap detected", color: "var(--pu-f1f5f9-t)", bg: "var(--pu-148-163-184-006)", border: "var(--pu-148-163-184-012)" };
}

const HIDDEN_ROLE_PATTERN = /\b(volunteer|intern|open source contributor|community tech educator|growth hacker)\b/i;
const isVisibleRole = (role: string) => Boolean(role.trim()) && !HIDDEN_ROLE_PATTERN.test(role);

export function JobsPage({ onJobClick }: { onJobClick: (id: string) => void }) {
  const { loading: authLoading, isAuthenticated } = useAuth();
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
  const [timeFilter, setTimeFilter] = useState("24h");
  const [maxYears, setMaxYears] = useState(10);
  const [visaOnly, setVisaOnly] = useState(false);
  const [personalized, setPersonalized] = useState(true);
  const [sortBy, setSortBy] = useState<"match" | "recent">("match");
  // Minimal-by-default filters: the Refine row stays collapsed behind a
  // "Filters" toggle until the user opens it (or has refinements active).
  const [refineOpen, setRefineOpen] = useState(false);

  // Persist + restore the filter setup across navigation (opening a job and
  // coming back used to reset every filter — #3a). Restored once on mount.
  // Version 2 retires old sessions that permanently restored Last 8h / 0-2
  // years and made a healthy 24-hour inventory look empty after deployment.
  const JOB_FILTERS_STORAGE_KEY = "placeup_jobs_filters_v2";
  const filtersRestored = useRef(false);
  const countryFilterInitialized = useRef(false);
  useEffect(() => {
    if (filtersRestored.current) return;
    filtersRestored.current = true;
    let f: any = {};
    try { f = JSON.parse(sessionStorage.getItem(JOB_FILTERS_STORAGE_KEY) || "{}"); } catch { f = {}; }
    if (f && Object.keys(f).length) {
      if (f.searchRaw) { setSearchRaw(f.searchRaw); setSearch(f.searchRaw); }
      if (f.locationRaw) { setLocationRaw(f.locationRaw); setLocation(f.locationRaw); }
      if (Object.prototype.hasOwnProperty.call(f, "countryFilter")) {
        // Empty was the legacy "all countries" value. Let preferences replace
        // that legacy default once; the new explicit override persists as
        // the unambiguous string "all".
        if (f.countryFilter) {
          setCountryFilter(f.countryFilter);
          countryFilterInitialized.current = true;
        }
      }
      if (f.visaProgramFilter) setVisaProgramFilter(f.visaProgramFilter);
      if (f.timeFilter) setTimeFilter(f.timeFilter);
      if (typeof f.maxYears === "number") setMaxYears(f.maxYears);
      if (typeof f.visaOnly === "boolean") setVisaOnly(f.visaOnly);
      if (f.sortBy === "match" || f.sortBy === "recent") setSortBy(f.sortBy);
      if (f.activeCategory) setActiveCategory(f.activeCategory);
      if (f.activeRole) setActiveRole(f.activeRole);
    }
  }, []);
  useEffect(() => {
    try {
      sessionStorage.setItem(JOB_FILTERS_STORAGE_KEY, JSON.stringify({
        searchRaw, locationRaw, countryFilter, visaProgramFilter, timeFilter,
        maxYears, visaOnly, sortBy, activeCategory, activeRole,
      }));
    } catch { /* storage disabled */ }
  }, [searchRaw, locationRaw, countryFilter, visaProgramFilter, timeFilter, maxYears, visaOnly, sortBy, activeCategory, activeRole]);

  // Dates follow the user's targeted country: the active country filter
  // wins, else the first saved target location that maps to a country.
  useEffect(() => {
    const fromFilter = countryFilter && countryFilter !== "all" ? countryFilter : undefined;
    const fromPrefs = userPrefs
      ? resolveCountryFromLocations(userPrefs.target_locations || [], targetCountries)
      : undefined;
    setActiveDateLocale(fromFilter || fromPrefs);
  }, [countryFilter, userPrefs, targetCountries]);

  const defaultTargetCountry = useMemo(
    () => userPrefs ? resolveCountryFromLocations(userPrefs.target_locations || [], targetCountries) : undefined,
    [userPrefs, targetCountries],
  );

  // First visit defaults to the user's saved destination country. An explicit
  // All countries selection is persisted as "all" and is never overwritten.
  useEffect(() => {
    if (countryFilterInitialized.current || !userPrefs || targetCountries.length === 0) return;
    setCountryFilter(defaultTargetCountry || "all");
    countryFilterInitialized.current = true;
  }, [defaultTargetCountry, userPrefs, targetCountries]);

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
  const [sourceBreakdown, setSourceBreakdown] = useState<{ direct: number; aggregator: number }>({ direct: 0, aggregator: 0 });
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
    activeCategory || activeRole || search || location || (countryFilter && countryFilter !== "all") || visaProgramFilter || visaOnly || timeFilter ||
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
    if (authLoading || !isAuthenticated) {
      setLoading(authLoading);
      return;
    }
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
  }, [authLoading, isAuthenticated, appliedVersion]);

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
    const refreshForResumeChange = () => {
      setPage(1);
      setResumeVersion(typeof window !== "undefined" ? localStorage.getItem("placeup_resume_version") || String(Date.now()) : String(Date.now()));
      // Re-read saved/tracked state from localStorage whenever the window regains
      // focus — e.g. user saved a job from the detail view and navigated back.
      setSavedVersion((v) => v + 1);
      setAppliedVersion((v) => v + 1);
    };
    const refreshTrackingState = () => {
      setSavedVersion((v) => v + 1);
      setAppliedVersion((v) => v + 1);
    };
    window.addEventListener("placeup:resume-changed", refreshForResumeChange as EventListener);
    window.addEventListener("focus", refreshTrackingState);
    return () => {
      window.removeEventListener("placeup:resume-changed", refreshForResumeChange as EventListener);
      window.removeEventListener("focus", refreshTrackingState);
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
  // NOTE: jobs no longer wait for the resume-status roundtrip. Scores are
  // always requested, so gating on resumeLink.checked only delayed the first
  // page load by a full extra network round trip.
  useEffect(() => {
    if (authLoading || !isAuthenticated) {
      setLoading(authLoading);
      return;
    }
    let active = true;
    const requestId = jobsRequestId.current + 1;
    jobsRequestId.current = requestId;
    setLoading(true);
    setError(null);
    if (page === 1) {
      setJobs([]);
      setTotal(0);
      setTotalPages(1);
      setSourceBreakdown({ direct: 0, aggregator: 0 });
    }

    const params: Record<string, string | number | boolean> = { page, page_size: pageSize, max_years: maxYears, sort: sortBy, personalized, tz_offset: new Date().getTimezoneOffset() };
    // Always ask for scores: the backend returns score_type
    // "resume_required" gracefully when no resume exists. Gating this on
    // resumeLink.hasResume made ALL match scores vanish whenever the
    // parsed-resume/summary calls failed or raced the auth refresh.
    params.include_scores = true;
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
        setSourceBreakdown({
          direct: Number(response?.source_breakdown?.direct || 0),
          aggregator: Number(response?.source_breakdown?.aggregator || 0),
        });
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
  }, [authLoading, isAuthenticated, activeCategory, activeRole, search, location, countryFilter, visaProgramFilter, visaOnly, timeFilter, maxYears, personalized, sortBy, page, resumeVersion, reloadKey]);

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
  }, [activeCategory, activeRole, search, location, countryFilter, visaProgramFilter, visaOnly, timeFilter, maxYears, personalized]);

  const savedIds = useMemo(() => getSavedIds(), [savedVersion]);
  const trackedJobs = useMemo(() => ({ ...getTrackedJobs(), ...serverTrackedJobs }), [appliedVersion, serverTrackedJobs]);

  const visibleAfterTrackingFilter = jobs.filter((job) => {
    const id = String(job.id || "");
    const status = id ? trackedJobs[id] : "";
    return status !== "applied" && status !== "interview";
  });
  const filtered = visibleAfterTrackingFilter.length > 0 || jobs.length === 0
    ? visibleAfterTrackingFilter
    : jobs;
  const trackingFilterFallback = jobs.length > 0 && visibleAfterTrackingFilter.length === 0;

  const allRoles = useMemo(
    () => Array.from(new Set(taxonomy.flatMap((cat) => cat.roles.map((role) => role.name)).filter(Boolean)))
      .filter(isVisibleRole)
      .sort((a, b) => a.localeCompare(b)),
    [taxonomy],
  );
  const visibleVisaPrograms = useMemo(
    () => visaPrograms.filter((program) => !countryFilter || countryFilter === "all" || program.country_code === countryFilter),
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
  const safeTotalPages = Math.max(1, totalPages);
  const pageNumbers = useMemo(
    () => paginationPages(page, safeTotalPages, isMobile ? 5 : 7),
    [page, safeTotalPages, isMobile],
  );
  const currentPageStart = total > 0 ? ((page - 1) * pageSize) + 1 : 0;
  const currentPageEnd = total > 0 && filtered.length > 0
    ? currentPageStart + filtered.length - 1
    : currentPageStart;
  const canGoPrevious = page > 1 && !loading;
  const canGoNext = page < safeTotalPages && !loading;
  const taxonomyRoleCount = Number(taxonomyMeta?.role_count || allRoles.length || 0);
  const rolePipelineCount = Number(taxonomyMeta?.role_pipeline_count || 117);
  const scrapeTermCount = Number(taxonomyMeta?.scrape_term_count || 0);
  const targetRoleCount = userPrefs?.target_roles?.length || 0;
  const savedRoleMode = personalized && targetRoleCount > 0;
  const onlyAggregatorMatchesToday = Boolean(
    savedRoleMode && timeFilter === "24h" && sourceBreakdown.direct === 0 && sourceBreakdown.aggregator > 0
  );
  const globalOpenPositionsCount = allJobsCount || total;
  const matchingPositionsCount = total;
  const timeFilterLabel = TIME_OPTIONS.find((chip) => chip.value === timeFilter)?.label || timeFilter;
  const pageCountLabel = `${filtered.length.toLocaleString()} of ${Math.min(pageSize, total || filtered.length).toLocaleString()} positions`;
  const filterSummaryParts = [
    pageCountLabel,
    visaOnly ? "Visa-friendly" : "",
    countryFilter && countryFilter !== "all" ? `Country: ${countryFlag(countryFilter)} ${countryFilter}` : "",
    timeFilter ? `Time: ${timeFilterLabel}` : "",
    activeRole ? `Role: ${activeRole}` : "",
    activeCategory ? `Category: ${activeCategory}` : "",
    visaProgramFilter ? `Visa: ${visibleVisaPrograms.find((program) => program.code === visaProgramFilter)?.name || visaProgramFilter}` : "",
  ].filter(Boolean);

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

  // Keep the page footer visible even when filters yield one page. Besides
  // making the current page/total explicit, this avoids the list appearing
  // abruptly cut off when Prev/Next are simply unavailable.
  const paginationControls = total > 0 ? (
    <div
      style={{
        marginTop: 8,
        marginBottom: 8,
        padding: isMobile ? "12px 10px" : "14px 16px",
        borderRadius: 12,
        border: `1px solid ${J.line}`,
        background: "var(--pu-1-17-38-068)",
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
          <div style={{ position: "absolute", inset: 0, background: "radial-gradient(circle at 12% 0%, var(--pu-59-130-246-02), transparent 36%), radial-gradient(circle at 88% 8%, var(--pu-199-90-18-016), transparent 32%)", pointerEvents: "none" }} />
          <div style={{ position: "relative", display: "grid", gridTemplateColumns: isTablet ? "1fr" : "minmax(0, 1.3fr) minmax(310px, 0.7fr)", gap: 18, alignItems: "stretch" }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ display: "inline-flex", alignItems: "center", gap: 8, height: 28, padding: "0 10px", borderRadius: 999, border: "1px solid var(--pu-59-130-246-03)", background: J.blueBg, color: J.blue, fontSize: 11, fontWeight: 800, fontFamily: F.sans }}>
                <Sparkles size={13} />
                Global visa search
              </div>
              <div style={{ marginTop: 10, color: J.text, fontSize: isMobile ? 22 : 30, fontWeight: 850, lineHeight: 1.08, letterSpacing: 0, fontFamily: F.sans }}>
                English-friendly roles by country and visa route
              </div>
              <div style={{ marginTop: 9, color: J.t2, fontSize: 13, lineHeight: 1.55, maxWidth: 680, fontFamily: F.sans }}>
                Search current roles across the 32-country target map, then narrow by local visa names like H-1B, LMIA, Skilled Worker, EU Blue Card, Employment Pass, and more.
              </div>
              <div style={{ marginTop: 14, display: "flex", flexWrap: "wrap", gap: 8 }}>
                {(targetCountries.length ? targetCountries : priorityCountries).map((country) => (
                  <button
                    key={country.code}
                    title={country.name || country.code}
                    onClick={() => { setCountryFilter(country.code === countryFilter ? "all" : country.code); setVisaProgramFilter(""); setPage(1); }}
                    style={{ ...filterPillStyle(countryFilter === country.code), display: "inline-flex", alignItems: "center", gap: 6 }}
                  >
                    <FlagIcon code={country.code} size={13} /> {country.code}
                  </button>
                ))}
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              {[
                { icon: Globe2, label: "Countries", value: targetCountries.length || "30+", color: T.blue },
                { icon: Route, label: "Visa routes", value: visaPrograms.length || 58, color: T.violet },
                { icon: Building2, label: savedRoleMode ? "Global roles" : "Open roles", value: globalOpenPositionsCount, color: "var(--pu-86efac-t)" },
                { icon: Languages, label: "English signals", value: "Active", color: T.fuchsia },
              ].map((item) => {
                const Icon = item.icon;
                return (
                  <div key={item.label} style={{ minHeight: 82, borderRadius: 12, border: `1px solid ${J.line}`, background: "var(--pu-1-17-38-054)", padding: 12, display: "flex", flexDirection: "column", justifyContent: "space-between", backdropFilter: "blur(18px)" }}>
                    <div style={{ width: 30, height: 30, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", background: "var(--pu-148-163-184-006)", border: `1px solid ${J.line}` }}>
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
          style={{ background: "linear-gradient(135deg, var(--pu-1-17-38-07), var(--pu-8-18-38-052))", border: `1px solid ${J.line}`, borderRadius: 16, padding: isMobile ? "12px" : "14px 16px", display: "flex", gap: 9, alignItems: "center", flexWrap: "wrap", rowGap: 10, boxShadow: J.shadow, backdropFilter: "blur(24px)" }}
        >
          <div style={{ flexBasis: "100%", display: "flex", alignItems: isMobile ? "flex-start" : "center", justifyContent: "space-between", gap: 10, flexDirection: isMobile ? "column" : "row" }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 850, color: J.text, fontFamily: F.sans, lineHeight: 1.25 }}>Search & filters</div>
              <div style={{ marginTop: 3, color: J.t2, fontSize: 11, fontFamily: F.sans, lineHeight: 1.4 }}>
                {filtered.length.toLocaleString()} visible
                {matchingPositionsCount ? ` / ${matchingPositionsCount.toLocaleString()} ${savedRoleMode || hasServerFilters ? "matching" : "open"}` : ""}
                {savedRoleMode ? ` - personalized from ${targetRoleCount} saved roles` : ""}
                {pipelineStatus?.last_scraped_at ? ` - refreshed ${formatPosted(pipelineStatus.last_scraped_at)}` : ""}
              </div>
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: isMobile ? "flex-start" : "flex-end" }}>
              {filterSummaryParts.map((part) => (
                <span key={part} style={activeFilterChipStyle()}>{part}</span>
              ))}
            </div>
          </div>
          {/* ── Row 1 · WHAT: role + search — the primary questions ── */}
          <div style={{ flexBasis: "100%", display: "flex", gap: 9, flexWrap: "wrap", alignItems: "center" }}>
            <select
              value={activeRole || ""}
              onChange={(e) => { setActiveRole(e.target.value || null); setActiveCategory(null); setPage(1); }}
              style={controlStyle({ minWidth: isMobile ? "100%" : 210, fontSize: 13 })}
            >
              <option style={SELECT_DARK_STYLE} value="">{savedRoleMode ? `All ${targetRoleCount} saved roles` : "All roles"}</option>
              {[...allRoles].sort((a, b) => a.localeCompare(b)).map((role) => <option style={SELECT_DARK_STYLE} key={role} value={role}>{role}</option>)}
            </select>
            {targetRoleCount > 0 && (
              <button
                onClick={() => { setPersonalized((value) => !value); setPage(1); }}
                style={{
                  ...controlStyle(),
                  border: `1px solid ${savedRoleMode ? "var(--pu-59-130-246-032)" : J.line}`,
                  background: savedRoleMode ? J.blueBg : J.card,
                  color: savedRoleMode ? J.blue : J.t2,
                  cursor: "pointer",
                  fontWeight: 800,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 7,
                }}
                title={savedRoleMode ? "Showing jobs matched to your saved target roles" : "Showing all active roles"}
              >
                <Sparkles size={13} />
                {savedRoleMode ? `Saved roles (${targetRoleCount})` : "All roles"}
              </button>
            )}
            <div style={controlStyle({ display: "flex", alignItems: "center", gap: 8, flex: "1 1 240px", minWidth: isMobile ? "100%" : 200 })}>
              <Search size={13} color={J.t3} />
              <input value={searchRaw} onChange={(e) => setSearchRaw(e.target.value)} placeholder="Search title, company, JD..."
                style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: J.text, fontSize: 13, fontFamily: F.sans }} />
            </div>
            <input value={locationRaw} onChange={(e) => setLocationRaw(e.target.value)} placeholder="Location"
              style={controlStyle({ width: isMobile ? "100%" : 140, flex: isMobile ? "1 1 100%" : "0 0 auto", fontSize: 13 })} />
            {(() => {
              const refineCount =
                (countryFilter ? 1 : 0) + (visaProgramFilter ? 1 : 0) + (visaOnly ? 1 : 0) +
                (timeFilter && timeFilter !== "24h" ? 1 : 0) + (maxYears !== 10 ? 1 : 0) + (sortBy !== "match" ? 1 : 0);
              const open = refineOpen || refineCount > 0;
              return (
                <button
                  onClick={() => setRefineOpen((v) => !v)}
                  style={{
                    ...controlStyle(),
                    border: `1px solid ${open ? "var(--pu-59-130-246-032)" : J.line}`,
                    background: open ? J.blueBg : J.card,
                    color: open ? J.blue : J.t2,
                    cursor: "pointer", fontWeight: 800,
                    display: "flex", alignItems: "center", gap: 6,
                  }}
                  title={open ? "Hide refinement filters" : "Show refinement filters"}
                >
                  <Filter size={12} /> Filters
                  {refineCount > 0 && (
                    <span style={{ minWidth: 16, height: 16, borderRadius: 999, background: J.blue, color: "var(--pu-ffffff-t)", fontSize: 9.5, fontWeight: 900, display: "inline-flex", alignItems: "center", justifyContent: "center", padding: "0 4px" }}>
                      {refineCount}
                    </span>
                  )}
                </button>
              );
            })()}
          </div>

          {/* ── Row 2 · WHERE + HOW: refine group, collapsed by default ── */}
          {(refineOpen || countryFilter || visaProgramFilter || visaOnly || (timeFilter && timeFilter !== "24h") || maxYears !== 10 || sortBy !== "match") && (
          <div style={{ flexBasis: "100%", display: "flex", gap: 9, flexWrap: "wrap", alignItems: "center", paddingTop: 10, borderTop: `1px solid ${J.line}` }}>
            <span style={{ fontSize: 10, fontWeight: 850, letterSpacing: "0.12em", textTransform: "uppercase", color: J.t3, fontFamily: F.sans, marginRight: 2 }}>
              Refine
            </span>
            <select
              value={countryFilter}
              onChange={(e) => { setCountryFilter(e.target.value); setVisaProgramFilter(""); setPage(1); }}
              style={controlStyle({ width: isMobile ? "100%" : 180 })}
            >
              <option style={SELECT_DARK_STYLE} value="all">Country: All countries</option>
              {[...targetCountries].sort((a, b) => a.name.localeCompare(b.name)).map((country) => <option style={SELECT_DARK_STYLE} key={country.code} value={country.code}>{countryFlag(country.code)} {country.code} - {country.name}</option>)}
            </select>
            <select
              value={visaProgramFilter}
              onChange={(e) => { setVisaProgramFilter(e.target.value); setPage(1); }}
              style={controlStyle({ width: isMobile ? "100%" : 220 })}
            >
              <option style={SELECT_DARK_STYLE} value="">Visa-friendly: All routes</option>
              {[...visibleVisaPrograms].sort((a, b) => routeLabel(a).localeCompare(routeLabel(b))).map((program) => <option style={SELECT_DARK_STYLE} key={`${program.country_code}-${program.code}`} value={program.code}>{countryFlag(program.country_code)} {program.country_code} - {program.name}</option>)}
            </select>
            <button onClick={() => { setVisaOnly(!visaOnly); setPage(1); }}
              style={{ ...controlStyle(), border: `1px solid ${visaOnly ? "var(--pu-34-197-94-032)" : J.line}`, background: visaOnly ? J.greenBg : J.card, color: visaOnly ? "var(--pu-86efac-t)" : J.t2, cursor: "pointer", display: "flex", alignItems: "center", gap: 5 }}>
              <Filter size={12} /> Visa-friendly
            </button>
            <select
              value={timeFilter}
              onChange={(e) => { setTimeFilter(e.target.value); setPage(1); }}
              style={controlStyle({ width: isMobile ? "100%" : 132 })}
            >
              {TIME_OPTIONS.map((chip) => <option style={SELECT_DARK_STYLE} key={chip.label} value={chip.value}>{chip.label}</option>)}
            </select>
            <select
              value={maxYears}
              onChange={(e) => { setMaxYears(Number(e.target.value)); setPage(1); }}
              style={controlStyle({ width: isMobile ? "100%" : 150 })}
              title="Maximum required experience"
            >
              <option style={SELECT_DARK_STYLE} value={2}>Experience: 0-2 yrs</option>
              <option style={SELECT_DARK_STYLE} value={5}>Experience: 0-5 yrs</option>
              <option style={SELECT_DARK_STYLE} value={10}>Experience: 0-10 yrs</option>
              <option style={SELECT_DARK_STYLE} value={50}>Experience: Any</option>
            </select>
            <select
              value={sortBy}
              onChange={(e) => { setSortBy(e.target.value as "match" | "recent"); setPage(1); }}
              style={controlStyle({ width: isMobile ? "100%" : 160 })}
              title="Sort results"
            >
              <option style={SELECT_DARK_STYLE} value="match">Sort: Best match</option>
              <option style={SELECT_DARK_STYLE} value="recent">Sort: Newest</option>
            </select>
            <span style={{ flex: 1 }} />
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
            {hasServerFilters && (
              <button
                onClick={() => { setSearchRaw(""); setSearch(""); setLocationRaw(""); setLocation(""); setCountryFilter(defaultTargetCountry || "all"); setVisaProgramFilter(""); setVisaOnly(false); setTimeFilter("24h"); setMaxYears(10); setActiveCategory(null); setActiveRole(null); setPersonalized(true); setPage(1); }}
                style={{ ...controlStyle(), cursor: "pointer", fontWeight: 800, color: J.t2, display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}
                title="Reset all filters"
              >
                <X size={13} />
                Clear filters
              </button>
            )}
          </div>
          )}
          <div style={{ flexBasis: "100%", color: J.t2, fontSize: 11, fontFamily: F.sans }}>
            {filtered.length.toLocaleString()} visible
            {matchingPositionsCount ? ` / ${matchingPositionsCount.toLocaleString()} ${savedRoleMode || hasServerFilters ? "matching" : "open"}` : ""}
            {savedRoleMode && globalOpenPositionsCount ? ` - ${globalOpenPositionsCount.toLocaleString()} global open` : ""}
            {rolePipelineCount ? ` - ${rolePipelineCount.toLocaleString()} role pipelines` : ""}
            {taxonomyRoleCount ? ` covering ${taxonomyRoleCount.toLocaleString()} titles` : ""}
            {scrapeTermCount ? ` / ${scrapeTermCount.toLocaleString()} scrape terms` : ""}
            {savedRoleMode ? ` - personalized from ${targetRoleCount} saved roles` : ""}
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
                    border: `1px solid ${visaProgramFilter === program.code ? "var(--pu-59-130-246-032)" : J.line}`,
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

        <div style={{
          display: "flex", flexDirection: isMobile ? "column" : "row", alignItems: isMobile ? "stretch" : "center", justifyContent: "space-between", gap: 10,
          padding: "11px 13px", borderRadius: 10, border: `1px solid ${J.line}`, background: "var(--pu-15-30-55-036)",
          color: J.t2, fontFamily: F.sans, fontSize: 11.5,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7, minWidth: 0 }}>
            <ShieldCheck size={13} color="var(--pu-86efac-t)" style={{ flexShrink: 0 }} />
            <span style={{ lineHeight: 1.45 }}>
              Official-source pipeline: Greenhouse, Workday, Lever, Ashby, Rippling, iCIMS, BambooHR, Workable, JazzHR, Jobvite, Oracle, UKG, ADP, SmartRecruiters, and similar career pages across {targetCountries.length || 32} countries.
            </span>
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: isMobile ? "flex-start" : "flex-end" }}>
            {filterSummaryParts.map((part) => (
              <span key={part} style={activeFilterChipStyle()}>{part}</span>
            ))}
          </div>
        </div>

        {resumeLink.checked && (
          <div style={{
            display: "flex", flexDirection: isMobile ? "column" : "row", alignItems: isMobile ? "stretch" : "center", justifyContent: "space-between", gap: 12,
            padding: "12px 14px", borderRadius: 8,
            border: `1px solid ${resumeLink.hasResume ? "var(--pu-34-197-94-028)" : "var(--pu-248-113-113-028)"}`,
            background: resumeLink.hasResume ? "var(--pu-34-197-94-008)" : "var(--pu-248-113-113-008)",
            color: J.t2, fontFamily: F.sans,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
              <div style={{
                width: 30, height: 30, borderRadius: 9, flexShrink: 0,
                display: "flex", alignItems: "center", justifyContent: "center",
                background: resumeLink.hasResume ? "var(--pu-34-197-94-012)" : "var(--pu-248-113-113-012)",
                border: `1px solid ${resumeLink.hasResume ? "var(--pu-34-197-94-028)" : "var(--pu-248-113-113-028)"}`,
              }}>
                <ShieldCheck size={14} color={resumeLink.hasResume ? "var(--pu-22c55e-b)" : T.red} />
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
                style={{ height: 32, padding: "0 12px", borderRadius: 8, border: "none", background: T.grad, color: "var(--pu-ffffff-t)", fontSize: 12, fontWeight: 800, fontFamily: F.sans, cursor: "pointer", flexShrink: 0, width: isMobile ? "100%" : "auto" }}
              >
                Upload Resume
              </button>
            )}
          </div>
        )}

        {error && (
          <div style={{ padding: "14px 16px", borderRadius: 12, background: "var(--pu-248-113-113-008)", border: "1px solid var(--pu-248-113-113-028)", color: J.text, fontFamily: F.sans, fontSize: 13 }}>
            <div style={{ fontWeight: 800, marginBottom: 4, color: T.red }}>Couldn't load jobs</div>
            <div style={{ color: J.t2, marginBottom: 10 }}>{error}</div>
            <button
              onClick={() => setReloadKey((value) => value + 1)}
              style={{ height: 32, padding: "0 12px", borderRadius: 8, border: `1px solid ${J.line}`, background: "var(--pu-148-163-184-005)", color: J.text, fontSize: 12, fontWeight: 800, fontFamily: F.sans, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 6 }}
            >
              <RefreshCw size={12} />
              Retry
            </button>
          </div>
        )}

        {trackingFilterFallback && !error && (
          <div style={{ padding: "10px 12px", borderRadius: 10, background: "var(--pu-59-130-246-008)", border: "1px solid var(--pu-59-130-246-022)", color: J.t2, fontFamily: F.sans, fontSize: 12 }}>
            Showing the full fetched page because every position on this page was already marked applied or interview.
          </div>
        )}

        {onlyAggregatorMatchesToday && !loading && !error && (
          <div style={{ padding: "12px 14px", borderRadius: 10, background: "var(--pu-245-158-11-008)", border: "1px solid var(--pu-245-158-11-025)", color: J.t2, fontFamily: F.sans, fontSize: 12, lineHeight: 1.5, display: "flex", alignItems: isMobile ? "stretch" : "center", justifyContent: "space-between", gap: 10, flexDirection: isMobile ? "column" : "row" }}>
            <span>
              No direct ATS posting matched these exact saved roles in the last 24 hours. Showing all {sourceBreakdown.aggregator.toLocaleString()} matching jobs posted today from verified job boards; dates are not being widened or invented.
            </span>
            <button onClick={() => { window.location.href = "/dashboard/one-click-apply"; }}
              style={{ height: 32, padding: "0 12px", borderRadius: 8, border: `1px solid ${J.line}`, background: J.card, color: J.blue, fontSize: 11.5, fontWeight: 800, fontFamily: F.sans, cursor: "pointer", whiteSpace: "nowrap" }}>
              View recent direct ATS roles
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
                onClick={() => { setSearchRaw(""); setSearch(""); setLocationRaw(""); setLocation(""); setCountryFilter(defaultTargetCountry || "all"); setVisaProgramFilter(""); setVisaOnly(false); setTimeFilter("24h"); setMaxYears(10); setActiveCategory(null); setActiveRole(null); setPersonalized(true); setPage(1); }}
                style={{ padding: "8px 14px", borderRadius: 8, border: `1px solid ${J.line}`, background: "var(--pu-148-163-184-005)", color: J.blue, fontSize: 12, fontWeight: 800, fontFamily: F.sans, cursor: "pointer" }}
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
                whileHover={{ y: -4, borderColor: "var(--pu-59-130-246-032)", boxShadow: "0 18px 40px var(--pu-1-17-38-04)" }}
                onClick={() => onJobClick(id)}
                style={{
                  minHeight: isMobile ? 248 : 176,
                  background: "var(--pu-8-18-38-055)",
                  border: `1px solid ${J.line}`,
                  boxShadow: "0 1px 2px var(--pu-1-17-38-03)",
                  borderRadius: 14,
                  padding: 16,
                  cursor: "pointer",
                  display: "grid",
                  gridTemplateColumns: isMobile ? "1fr" : "minmax(0, 1fr) 136px",
                  gap: 14,
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
                          fontFamily: F.sans, fontWeight: 700, fontSize: 17, color: "var(--pu-ffffff-t)",
                          background: `linear-gradient(135deg, ${
                            ["var(--pu-3b82f6-b)", "var(--pu-60a5fa-b)", "var(--pu-1d4ed8)", "var(--pu-0891b2)", "var(--pu-059669)", "var(--pu-475569-b)"][
                              Math.abs((job.company || "X").charCodeAt(0)) % 6
                            ]
                          }, var(--pu-0b1220))`,
                          boxShadow: "0 4px 14px var(--pu-59-130-246-026)",
                        }}
                      >
                        {(job.company || "?").trim().charAt(0).toUpperCase()}
                        {logo && (
                          <img
                            src={logo}
                            alt=""
                            loading="lazy"
                            onError={(e) => { e.currentTarget.style.display = "none"; }}
                            style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "contain", padding: 6, background: "var(--pu-148-163-184-092)" }}
                          />
                        )}
                      </div>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ fontSize: 14, fontWeight: 850, color: J.text, fontFamily: F.sans, lineHeight: 1.28, marginBottom: 6, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{job.title || "Untitled role"}</div>
                        <div style={{ fontSize: 12, color: J.t2, fontFamily: F.sans, fontWeight: 650, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{job.company || "Unknown"}</div>
                      </div>
                    </div>
                    {isMobile && <ATSRing score={match} size={48} />}
                  </div>
                  <div style={{ height: 1, background: "var(--pu-59-130-246-022)", marginTop: 2 }} />
                  <div style={{ display: "flex", gap: 8, fontSize: 11, color: J.t2, fontFamily: F.sans, flexWrap: "wrap", alignItems: "center" }}>
                    <span style={{ display: "inline-flex", gap: 5, alignItems: "center", minWidth: 0 }}><FlagIcon code={visaCountry} size={13} /><span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{job.location || visaCountryName || "Remote"}</span></span>
                    <span style={{ display: "inline-flex", gap: 5, alignItems: "center", padding: "3px 8px", borderRadius: 999, background: "var(--pu-59-130-246-008)", color: "var(--pu-f1f5f9-t)", border: "1px solid var(--pu-59-130-246-018)", whiteSpace: "nowrap" }}>
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
                          background: isTargetRole ? "var(--pu-59-130-246-016)" : J.blueBg,
                          color: isTargetRole ? "var(--pu-60a5fa-t)" : J.blue,
                          border: isTargetRole ? "1px solid var(--pu-59-130-246-04)" : "1px solid transparent",
                          boxShadow: isTargetRole ? "0 0 10px var(--pu-59-130-246-018)" : "none",
                        }}>
                          <Building2 size={11} />{role}{isTargetRole ? " *" : ""}
                        </span>
                      );
                    })()}
                    {englishFriendly && <span style={{ fontSize: 11, fontWeight: 750, padding: "4px 8px", borderRadius: 999, background: J.greenBg, color: "var(--pu-86efac-t)", fontFamily: F.sans }}>English-friendly</span>}
                    {sponsorVerified && <span style={{ fontSize: 11, fontWeight: 750, padding: "4px 8px", borderRadius: 999, background: "var(--pu-34-197-94-008)", color: "var(--pu-86efac-t)", fontFamily: F.sans }}>{sourceLabel(visaRecord.sponsor_source)}</span>}
                  </div>
                  {preview && (
                    <div style={{ fontSize: 12, color: J.t2, fontFamily: F.sans, lineHeight: 1.55, display: "-webkit-box", WebkitLineClamp: isMobile ? 3 : 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                      {preview}
                    </div>
                  )}
                  <button
                    disabled={tailorQueueIds.has(id) || tailorBusyId === id || tailorUsage.used >= tailorUsage.limit}
                    onClick={async (e) => {
                      e.stopPropagation();
                      await addToTailorQueue(job);
                    }}
                    style={{
                      width: "100%",
                      minHeight: 38,
                      padding: "0 14px",
                      borderRadius: 10,
                      border: `1px solid ${tailorQueueIds.has(id) ? "var(--pu-34-197-94-034)" : "var(--pu-59-130-246-036)"}`,
                      background: tailorQueueIds.has(id)
                        ? "var(--pu-34-197-94-01)"
                        : "linear-gradient(135deg, var(--pu-242-163-65-022), var(--pu-59-130-246-018))",
                      color: tailorQueueIds.has(id) ? "var(--pu-86efac-t)" : "var(--pu-f1f5f9-t)",
                      fontSize: 12,
                      fontWeight: 900,
                      cursor: tailorQueueIds.has(id) || tailorUsage.used >= tailorUsage.limit ? "not-allowed" : "pointer",
                      opacity: tailorUsage.used >= tailorUsage.limit && !tailorQueueIds.has(id) ? 0.55 : 1,
                      fontFamily: F.sans,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: 7,
                      boxShadow: tailorQueueIds.has(id) ? "none" : "0 10px 24px var(--pu-59-130-246-016)",
                    }}
                    title={tailorQueueIds.has(id) ? "Already in tailor queue" : tailorUsage.used >= tailorUsage.limit ? "Daily tailor queue limit reached" : "Add this job to Tailor Queue"}
                  >
                    <Wand2 size={14} />
                    {tailorQueueIds.has(id) ? "Added to Tailor Queue" : tailorBusyId === id ? "Adding to Tailor Queue..." : "Tailor Resume"}
                    <span style={{ color: tailorQueueIds.has(id) ? "var(--pu-86efac-t)" : "var(--pu-148-163-184-068)", fontSize: 10, fontWeight: 800 }}>
                      {tailorUsage.used}/{tailorUsage.limit} today
                    </span>
                  </button>
                  <div style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", gap: 10, marginTop: "auto" }}>
                    <div style={{ display: "flex", gap: 5, flexWrap: "wrap", minWidth: 0 }}>
                      {visaBadges.slice(0, 4).map((v) => {
                        const s = VISA_BADGES[v] ?? { bg: "var(--pu-dcfce7)", color: "var(--pu-15803d)", border: "var(--pu-bbf7d0)" };
                        return <span key={v} style={{ fontSize: 10, fontWeight: 800, padding: "3px 8px", borderRadius: 999, background: s.bg, color: s.color, border: `1px solid ${s.border}`, fontFamily: F.sans }}>{v.replace(`${visaCountry}: `, "")}</span>;
                      })}
                      {visaBadges.length === 0 && <span style={{ fontSize: 10, color: J.t3, fontFamily: F.sans }}>Visa not verified</span>}
                    </div>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, borderTop: `1px solid ${J.line}`, paddingTop: 9 }}>
                      <span style={{ color: J.t3, fontSize: 10, fontFamily: F.sans }}>{getScoreMeta(match, job.score_type).label}</span>
                      <div style={{ display: "flex", gap: 6, flexShrink: 0, flexWrap: "wrap", justifyContent: "flex-end" }}>
                      <button onClick={(e) => {
                        e.stopPropagation();
                        const saved = Array.from(savedIds);
                        const next = savedIds.has(id) ? saved.filter((item) => item !== id) : [...saved, id];
                        localStorage.setItem("placeup_saved_jobs", JSON.stringify(next));
                        setSavedVersion((v) => v + 1);
                      }} style={{ width: 30, height: 28, borderRadius: 7, border: `1px solid ${savedIds.has(id) ? "var(--pu-248-113-113-035)" : J.line}`, background: savedIds.has(id) ? "var(--pu-248-113-113-01)" : "var(--pu-148-163-184-005)", color: savedIds.has(id) ? T.red : J.t2, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }} title={savedIds.has(id) ? "Unsave" : "Save job"}><Bookmark size={13} fill={savedIds.has(id) ? T.red : "none"}/></button>
                      <button onClick={async (e) => {
                        e.stopPropagation();
                        const cur = trackedJobs[id];
                        const nextStatus = cur === "applied" ? "interview" : "applied";
                        await persistApplication(job, nextStatus);
                      }} style={{ height: 28, padding: "0 9px", borderRadius: 7, border: `1px solid ${trackedJobs[id] === "interview" ? "var(--pu-59-130-246-035)" : trackedJobs[id] === "applied" ? "var(--pu-34-197-94-035)" : J.line}`, background: trackedJobs[id] === "interview" ? "var(--pu-59-130-246-01)" : trackedJobs[id] === "applied" ? "var(--pu-34-197-94-01)" : "var(--pu-148-163-184-005)", color: trackedJobs[id] === "interview" ? "var(--pu-93c5fd-t)" : trackedJobs[id] === "applied" ? "var(--pu-86efac-t)" : J.t2, fontSize: 10, fontWeight: 800, cursor: "pointer", fontFamily: F.sans, whiteSpace: "nowrap" }} title={trackedJobs[id] === "interview" ? "Interview stage" : trackedJobs[id] === "applied" ? "Applied - click to move to Interview" : "Track application status"}>
                        {trackedJobs[id] === "interview" ? "Interview" : trackedJobs[id] === "applied" ? "Applied" : "Track"}
                      </button>
                      <button
                        onClick={async (e) => {
                          e.stopPropagation();
                          const url = jobUrl || `https://www.google.com/search?q=${encodeURIComponent(`${job.company || ""} ${job.title || ""} apply`)}`;
                          window.open(url, "_blank", "noopener,noreferrer");
                        }}
                        style={{ height: 28, padding: "0 10px", borderRadius: 7, border: `1px solid ${J.line}`, background: "var(--pu-148-163-184-005)", color: J.t2, fontSize: 10, cursor: "pointer", fontFamily: F.sans, fontWeight: 800, display: "flex", alignItems: "center", gap: 4 }}
                      ><ExternalLink size={11}/> {applyLabelForJob(job, jobUrl)}</button>
                      <button onClick={(e) => { e.stopPropagation(); onJobClick(id); }} style={{ height: 28, padding: "0 10px", borderRadius: 7, border: "none", background: T.grad, color: "var(--pu-ffffff-t)", fontSize: 10, cursor: "pointer", fontFamily: F.sans, fontWeight: 800, display: "flex", alignItems: "center", gap: 4 }}><ExternalLink size={11}/> View</button>
                      </div>
                    </div>
                  </div>
                </div>
                {!isMobile && (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 9, padding: "16px 8px", borderRadius: 12, background: "var(--pu-1-17-38-05)", border: "1px solid var(--pu-59-130-246-02)" }}>
                    <ATSRing score={match} size={66} />
                    <div style={{ fontSize: 10, fontWeight: 900, letterSpacing: "0.04em", textTransform: "uppercase", color: getScoreMeta(match, job.score_type).color, fontFamily: F.sans, textAlign: "center", lineHeight: 1.3 }}>{getScoreMeta(match, job.score_type).label}</div>
                    {sponsorVerified && <div style={{ fontSize: 10, color: "var(--pu-86efac-t)", fontFamily: F.sans, display: "flex", alignItems: "center", gap: 4, textAlign: "center", lineHeight: 1.3 }}><ShieldCheck size={11} /> Sponsor likely</div>}
                  </div>
                )}
              </motion.div>
            );
          })}
        </div>
        {paginationControls}
      </div>
    </div>
  );
}
