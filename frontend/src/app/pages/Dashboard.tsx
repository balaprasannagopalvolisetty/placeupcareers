import { useState, useEffect } from "react";
import { motion, AnimatePresence, useMotionValue, useTransform, animate } from "motion/react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";
import {
  Home, FileText, Globe, Bell, BarChart3, Settings, LogOut,
  Menu, X, User, ChevronDown, Briefcase,
  TrendingUp, ChevronRight, CheckCircle2, Bookmark, Clock,
  ArrowUpRight, MapPin, DollarSign, FileCheck,
  Shield, Wand2,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import * as api from "../lib/api";
import FeedbackWidget from "../components/FeedbackWidget";
import { ResumePage } from "../components/dashboard/ResumePage";
import { JobsPage } from "../components/dashboard/JobsPage";
import { AlertsPage } from "../components/dashboard/AlertsPage";
import { AnalyticsPage } from "../components/dashboard/AnalyticsPage";
import { SettingsPage } from "../components/dashboard/SettingsPage";
import { UserProfilePage } from "../components/dashboard/UserProfilePage";
import { JobDetailPage } from "../components/dashboard/JobDetailPage";
import { RoleRequestPanel } from "../components/dashboard/RoleRequestPanel";
import { LoadingLogo } from "../components/LoadingLogo";
import { BrandLogo } from "../components/BrandLogo";

// ─── Design tokens ───
const T = {
  bg:     "#0B1220",
  surface: "#111E33",
  glass:  "rgba(13,28,53,0.7)",
  cardGlass: "rgba(15,30,55,0.45)",
  border: "rgba(148,163,184,0.08)",
  borderHover: "rgba(59,130,246,0.4)",
  text:   "#F1F5F9",
  t2:     "rgba(226,232,240,0.72)",
  t3:     "rgba(148,163,184,0.4)",
  grad:   "linear-gradient(135deg, #2563EB, #0EA5E9)",
  red:    "#3B82F6",
  burnt:  "#60A5FA",
  dark:   "#1D4ED8",
  shadow: "0 4px 20px rgba(1,17,38,0.3)",
  shadowH: "0 20px 50px rgba(1,17,38,0.4), 0 0 0 1px rgba(59,130,246,0.3)",
};
const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };

// ─── Helpers ───
function useViewportFlags() {
  const getWidth = () => (typeof window === "undefined" ? 1280 : window.innerWidth);
  const [width, setWidth] = useState(getWidth);

  useEffect(() => {
    const onResize = () => setWidth(getWidth());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return { width, isMobile: width < 640, isTablet: width < 1024 };
}

function normalizeVisa(visa: unknown): string[] {
  if (Array.isArray(visa)) return visa.filter((v): v is string => typeof v === "string");
  if (visa && typeof visa === "object") {
    const map: Record<string, string> = {
      visa_h1b: "H-1B",
      visa_opt: "F1-OPT",
      visa_stem_opt: "F1-STEM",
      h1b_verified: "H-1B Verified",
      green_card: "Green Card",
    };
    return Object.entries(visa as Record<string, unknown>)
      .filter(([key, value]) => key !== "visa_score" && Boolean(value))
      .map(([key]) => map[key] ?? key.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase()));
  }
  if (typeof visa === "string") return visa.split(",").map((s) => s.trim()).filter(Boolean);
  return [];
}

function formatSalary(salary: unknown): string {
  if (!salary) return "";
  if (typeof salary === "string") return salary;
  if (typeof salary === "object") {
    const min = (salary as any).min_salary;
    const max = (salary as any).max_salary;
    if (typeof min === "number" && typeof max === "number") return `$${Math.round(min / 1000)}K–$${Math.round(max / 1000)}K`;
    if (typeof min === "number") return `$${Math.round(min / 1000)}K+`;
    if (typeof max === "number") return `Up to $${Math.round(max / 1000)}K`;
    if ((salary as any).display) return String((salary as any).display);
  }
  return "Not specified";
}

// ─── Defaults (only used while loading or if API fails) ───
const NAV_ITEMS = [
  { icon: Home,     label: "Overview", to: "/dashboard" },
  { icon: FileText, label: "Resumes", to: "/dashboard/resumes" },
  { icon: Briefcase,label: "Jobs", to: "/dashboard/jobs" },
  { icon: Wand2,   label: "Tailor", to: "/dashboard/tailor" },
  { icon: Bell,     label: "Alerts", to: "/dashboard/alerts" },
  { icon: BarChart3,label: "Analytics", to: "/dashboard/analytics" },
  { icon: Settings, label: "Settings", to: "/dashboard/settings" },
];

// ─── Spring Counter ───
function SpringCounter({ target, suffix = "", prefix = "" }: { target: number; suffix?: string; prefix?: string }) {
  const count = useMotionValue(0);
  const display = useTransform(count, (v) => prefix + Math.round(v).toLocaleString() + suffix);
  useEffect(() => {
    const ctrl = animate(count, target, { type: "spring", stiffness: 60, damping: 20, mass: 1.2 });
    return ctrl.stop;
  }, [count, target]);
  return <motion.span>{display}</motion.span>;
}

// ─── ATS Ring (dashboard overview, 120px) ───
function ATSRing({ score }: { score: number }) {
  const safeScore = Math.max(0, Math.min(100, Number.isFinite(score) ? score : 0));
  const r = 52, circ = 2 * Math.PI * r, offset = circ * (1 - safeScore / 100);
  const ringColor = safeScore >= 80 ? "#22c55e" : safeScore >= 60 ? "#f59e0b" : safeScore > 0 ? "#F1F5F9" : "rgba(148,163,184,0.75)";
  return (
    <div style={{ position: "relative", width: 120, height: 120, flexShrink: 0 }}>
      <svg viewBox="0 0 120 120" style={{ width: "100%", height: "100%", transform: "rotate(-90deg)" }}>
        <defs>
          <linearGradient id="atsG" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={T.burnt} /><stop offset="50%" stopColor={T.red} /><stop offset="100%" stopColor={T.dark} />
          </linearGradient>
          <filter id="atsGlow"><feGaussianBlur stdDeviation="3" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
        </defs>
        <circle cx="60" cy="60" r={r} fill="none" stroke="rgba(148,163,184,0.16)" strokeWidth="9" />
        <motion.circle cx="60" cy="60" r={r} fill="none" stroke={ringColor} strokeWidth="9" strokeLinecap="round"
          strokeDasharray={circ} initial={{ strokeDashoffset: circ }} animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1.5, ease: "easeOut" }} filter="url(#atsGlow)" />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <span style={{ fontFamily: F.mono, fontSize: 28, fontWeight: 800, color: "#F1F5F9", lineHeight: 1, textShadow: "0 0 16px rgba(148,163,184,0.22)" }}>{safeScore || "--"}</span>
        <span style={{ fontSize: 9, letterSpacing: "0.1em", textTransform: "uppercase", color: T.t2, fontFamily: F.sans, marginTop: 3 }}>ATS Score</span>
      </div>
    </div>
  );
}

// ─── GlowCard ───
function GlowCard({ children, style = {}, hoverY = -6, onClick }: {
  children: React.ReactNode; style?: React.CSSProperties; hoverY?: number; onClick?: () => void;
}) {
  return (
    <motion.div
      className="group relative overflow-hidden"
      whileHover={{ y: hoverY, boxShadow: T.shadowH }}
      whileTap={{ scale: 0.985 }}
      onClick={onClick}
      transition={{ duration: 0.28, ease: [0.25, 0.46, 0.45, 0.94] }}
      style={{
        background: T.cardGlass, backdropFilter: "blur(20px) saturate(180%)",
        WebkitBackdropFilter: "blur(20px) saturate(180%)",
        border: `1px solid ${T.border}`, borderRadius: 20,
        boxShadow: T.shadow, cursor: onClick ? "pointer" : "default", ...style,
      }}
    >
      <div className="absolute inset-0 pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-500"
        style={{ background: "radial-gradient(ellipse at 50% -25%, rgba(59,130,246,0.16) 0%, transparent 65%)", zIndex: 0 }} />
      <div className="absolute top-0 left-0 right-0 h-px pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-500"
        style={{ background: "linear-gradient(to right, transparent, rgba(59,130,246,0.45), transparent)" }} />
      <div style={{ position: "relative", zIndex: 1 }}>{children}</div>
    </motion.div>
  );
}

// ═══════════════════════════
// OVERVIEW PAGE
// ═══════════════════════════
type FeaturedJob = { id: string | number; title: string; company: string; location: string; salary: string; match: number | null; visa: string[]; posted: string };

// Module-level snapshot so returning to Overview renders the last result
// instantly instead of flashing an empty "Featured Positions Today" while the
// network refetches. Survives route changes; refreshed in the background.
const _overviewSnapshot: { featured: FeaturedJob[] } = { featured: [] };

export function OverviewPage({ onJobClick }: { onJobClick?: (id: string | number) => void }) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { isMobile, isTablet } = useViewportFlags();
  const [featuredJobs, setFeaturedJobs] = useState<FeaturedJob[]>(_overviewSnapshot.featured);
  const [resumeScore, setResumeScore] = useState(0);
  const [hasResume, setHasResume] = useState(false);
  const [activeResumeName, setActiveResumeName] = useState("");
  const [totalApplications, setTotalApplications] = useState(0);
  const [applications, setApplications] = useState<api.UserApplicationRow[]>([]);
  const [totalResumes, setTotalResumes] = useState(0);
  // Distinguishes "still loading" from "genuinely has no resume". Without this
  // the cards flashed "0 / Upload a resume" on every slow fetch even for users
  // who DO have a resume, which looked broken.
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [featuredLoading, setFeaturedLoading] = useState(true);

  const handleJobClick = (id: string | number) => {
    if (onJobClick) {
      onJobClick(id);
    } else {
      navigate(`/dashboard/jobs/${id}`);
    }
  };

  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const displayFirstName = user?.first_name || "there";

  // Fetch top resume matches for featured jobs. Do not use this endpoint for
  // the dashboard's scraped-jobs count: it intentionally returns only a small
  // matched subset and made the Overview look like there were only ~43 jobs.
  useEffect(() => {
    let active = true;
    setFeaturedLoading(true);
    const mapJobs = (jobs: api.JobPost[]): FeaturedJob[] => jobs.map((job) => ({
      id: job.id ?? "",
      title: job.title ?? "Untitled role",
      company: job.company ?? "Unknown",
      location: job.location ?? "Remote",
      salary: formatSalary(job.salary),
      match: typeof job.match_score === "number" ? job.match_score : null,
      visa: normalizeVisa(job.visa),
      posted: job.posted_at ?? "Recently",
    }));
    const commit = (jobs: FeaturedJob[]) => {
      if (!active) return;
      _overviewSnapshot.featured = jobs;
      setFeaturedJobs(jobs);
      setFeaturedLoading(false);
    };
    // Prefer today's matches, but never leave "Featured Positions Today" empty:
    // if nothing was posted/scraped today, fall back to the most recent matches
    // so the section always shows positions.
    api.getTopMatches({ limit: 20, time_filter: "today", tz_offset: new Date().getTimezoneOffset() })
      .then((response) => {
        if (!active) return;
        const todayJobs = mapJobs(response.jobs);
        if (todayJobs.length > 0) {
          commit(todayJobs);
          return;
        }
        api.getTopMatches({ limit: 20, tz_offset: new Date().getTimezoneOffset() })
          .then((fallback) => commit(mapJobs(fallback.jobs)))
          .catch(() => { if (active) setFeaturedLoading(false); });
      })
      .catch(() => {
        // Network/timeout: keep any cached snapshot rather than blanking.
        api.getTopMatches({ limit: 20, tz_offset: new Date().getTimezoneOffset() })
          .then((fallback) => commit(mapJobs(fallback.jobs)))
          .catch(() => { if (active) setFeaturedLoading(false); });
      });
    return () => { active = false; };
  }, []);

  // Fetch dashboard summary (resume score, applications, activity)
  useEffect(() => {
    let active = true;
    setSummaryLoading(true);
    Promise.allSettled([
      api.getDashboardSummary(),
      api.getResumeList(),
      api.getUserApplications(),
      // Fourth source: the parsed-active-resume endpoint. It reads the same
      // resume the Jobs page uses, so even if the summary/list calls are slow
      // or fail, the ATS score and "has resume" state still resolve correctly.
      api.getParsedActiveResume().catch(() => null),
    ])
      .then(([summaryResult, resumesResult, applicationsResult, parsedResult]) => {
        if (!active) return;
        const summary = summaryResult.status === "fulfilled" ? summaryResult.value : null;
        const resumes = resumesResult.status === "fulfilled" ? resumesResult.value : [];
        const applicationRows = applicationsResult.status === "fulfilled" ? applicationsResult.value : [];
        const parsed = parsedResult.status === "fulfilled" ? parsedResult.value : null;
        const activeResume = resumes.find((resume) => resume.active) || resumes[0];

        const resolvedScore = Number(
          summary?.resume_score || activeResume?.score || (parsed as any)?.score || 0,
        );
        const resolvedResumeCount = Math.max(
          Number(summary?.total_resumes || 0),
          resumes.length,
          activeResume ? 1 : 0,
          (parsed as any)?.has_resume ? 1 : 0,
        );
        const resolvedResumeName =
          summary?.active_resume_name || activeResume?.name || (parsed as any)?.name || "";

        setResumeScore(resolvedScore);
        setHasResume(Boolean(summary?.has_resume || (parsed as any)?.has_resume || resolvedResumeName || resolvedResumeCount > 0));
        setActiveResumeName(resolvedResumeName);
        setApplications(applicationRows.filter((row) => row.status === "applied" || row.status === "interview"));
        setTotalApplications(Number(summary?.total_applications || applicationRows.length || 0));
        setTotalResumes(resolvedResumeCount);
      })
      .finally(() => { if (active) setSummaryLoading(false); });
    return () => { active = false; };
  }, []);

  const visibleJobs = featuredJobs;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: isMobile ? 16 : 22, width: "100%", minWidth: 0 }}>
      {/* Welcome */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
        <h2 style={{ fontFamily: F.sans, fontSize: 22, fontWeight: 700, color: T.text, marginBottom: 4 }}>{greeting}, {displayFirstName}! 👋</h2>
        <p style={{ fontSize: 14, color: T.t2, fontFamily: F.sans }}>
          {featuredLoading
            ? "Loading your top resume-matched positions…"
            : visibleJobs.length > 0
              ? `Showing today's top ${visibleJobs.length} resume-matched positions from the roles you selected.`
              : "No matched positions yet. Add target roles or upload a resume to start matching."}
        </p>
      </motion.div>

      {/* Summary row */}
      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : isTablet ? "repeat(2, minmax(0, 1fr))" : "repeat(3, 1fr)", gap: 14 }}>
        {/* ATS Score */}
        <GlowCard style={{ padding: 20, gridColumn: "span 1" }} onClick={() => navigate("/dashboard/resumes")}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: T.t3, fontFamily: F.sans }}>Resume ATS Score</div>
            {hasResume && (
              <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 7px", borderRadius: 9999, background: "rgba(34,197,94,0.10)", color: "#22c55e", border: "1px solid rgba(34,197,94,0.25)", fontFamily: F.sans, letterSpacing: "0.04em" }}>LOADED</span>
            )}
          </div>
          <div style={{ display: "flex", justifyContent: "center" }}><ATSRing score={resumeScore} /></div>
          <div style={{ fontSize: 12, color: resumeScore > 0 ? T.t2 : T.t3, fontFamily: F.sans, textAlign: "center", marginTop: 8 }}>
            {resumeScore > 0
              ? `ATS Score: ${resumeScore}/100`
              : summaryLoading
                ? "Loading your resume…"
                : hasResume
                  ? "Re-scoring active resume…"
                  : "Upload a resume to show score"}
          </div>
          {activeResumeName ? (
            <div title={activeResumeName} style={{ fontSize: 11, color: T.t2, fontFamily: F.sans, textAlign: "center", marginTop: 4, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              📄 {activeResumeName}
            </div>
          ) : hasResume ? (
            <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans, textAlign: "center", marginTop: 4 }}>
              Resume on file
            </div>
          ) : null}
        </GlowCard>

        {/* Applications */}
        <GlowCard style={{ padding: 20 }} onClick={() => navigate("/dashboard/analytics")}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
            <div style={{ width: 36, height: 36, borderRadius: 10, background: "rgba(37,99,235,0.1)", border: "1px solid rgba(37,99,235,0.2)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <CheckCircle2 size={16} color={T.burnt} />
            </div>
            {totalApplications > 0 && (
            <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: "#22c55e", fontFamily: F.sans, fontWeight: 600 }}>
              <ArrowUpRight size={12} /> {totalApplications}
            </div>
            )}
          </div>
          <div style={{ fontFamily: F.sans, fontSize: isMobile ? 30 : 38, fontWeight: 800, color: T.text, lineHeight: 1, marginBottom: 4 }}><SpringCounter target={totalApplications} /></div>
          <div style={{ fontSize: 13, color: T.t2, fontFamily: F.sans }}>Applications</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 2, marginTop: 6 }}>
            {applications.length === 0 ? (
              <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans }}>Tracked submissions</div>
            ) : applications.slice(0, 4).map((app) => (
              <div key={`${app.job_id}-${app.title}`} style={{ fontSize: 11, color: T.t3, fontFamily: F.sans, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {app.title || "Applied role"}
              </div>
            ))}
          </div>
        </GlowCard>

        {/* Resumes */}
        <GlowCard style={{ padding: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
            <div style={{ width: 36, height: 36, borderRadius: 10, background: "rgba(15,30,55,0.2)", border: "1px solid rgba(15,30,55,0.4)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <FileCheck size={16} color={T.text} />
            </div>
            {hasResume && (
              <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 8px", borderRadius: 9999, background: "rgba(59,130,246,0.12)", color: T.red, border: "1px solid rgba(59,130,246,0.25)", fontFamily: F.sans }}>Active</span>
            )}
          </div>
          <div style={{ fontFamily: F.sans, fontSize: isMobile ? 30 : 38, fontWeight: 800, color: T.text, lineHeight: 1, marginBottom: 4 }}><SpringCounter target={totalResumes} /></div>
          <div style={{ fontSize: 13, color: T.t2, fontFamily: F.sans }}>Resumes</div>
          <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans, marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{activeResumeName || "Uploaded files"}</div>
        </GlowCard>
      </div>

      {/* Request a role → admin approval queue */}
      <RoleRequestPanel />

      {/* Featured Jobs */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: T.red, fontFamily: F.sans }}>Featured Positions Today</span>
          <button onClick={() => navigate("/dashboard/jobs")} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, color: T.red, fontFamily: F.sans, background: "none", border: "none", cursor: "pointer" }}>
            View All <ChevronRight size={13} />
          </button>
        </div>
        {featuredLoading && visibleJobs.length === 0 ? (
          <LoadingLogo label="Loading featured positions" />
        ) : !featuredLoading && visibleJobs.length === 0 ? (
          <div style={{ padding: 34, borderRadius: 16, border: `1px solid ${T.border}`, background: "rgba(148,163,184,0.03)", textAlign: "center" }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: T.text, fontFamily: F.sans, marginBottom: 6 }}>No matched positions yet</div>
            <div style={{ fontSize: 12.5, color: T.t2, fontFamily: F.sans, lineHeight: 1.6 }}>
              Make sure you have an active resume and at least 5 target roles selected. New matches appear here as they are scraped.
            </div>
          </div>
        ) : (
        <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : isTablet ? "repeat(2, minmax(0, 1fr))" : "repeat(3, 1fr)", gap: 14 }}>
          {visibleJobs.map((job, i) => (
            <motion.div key={job.id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 + i * 0.08 }}>
              <GlowCard style={{ padding: 20 }} onClick={() => handleJobClick(job.id)}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                  <div style={{ width: 40, height: 40, borderRadius: "50%", background: T.grad, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, fontWeight: 700, color: "#fff", fontFamily: F.sans, boxShadow: "0 0 12px rgba(59,130,246,0.3)" }}>
                    {job.company[0]}
                  </div>
                  <span style={{ fontSize: 14, fontWeight: 800, color: job.match === null ? T.t3 : T.red, fontFamily: F.mono }}>
                    {job.match === null ? "Resume needed" : `${job.match}%`}
                  </span>
                </div>
                <div style={{ fontSize: 14, fontWeight: 600, color: T.text, fontFamily: F.sans, marginBottom: 4, lineHeight: 1.3 }}>{job.title}</div>
                <div style={{ fontSize: 12, color: T.t2, fontFamily: F.sans, marginBottom: 10 }}>{job.company}</div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
                  {job.visa.map((v) => (
                    <span key={v} style={{ fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 4, background: "rgba(37,99,235,0.15)", color: T.burnt, border: "1px solid rgba(37,99,235,0.3)", fontFamily: F.sans }}>{v}</span>
                  ))}
                </div>
                <div style={{ display: "flex", gap: 8, fontSize: 11, color: T.t3, fontFamily: F.sans }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 3 }}><MapPin size={10} />{job.location}</span>
                  {job.salary && <span style={{ display: "flex", alignItems: "center", gap: 3 }}><DollarSign size={10} />{job.salary}</span>}
                </div>
                <div style={{ height: 3, borderRadius: 2, background: "rgba(148,163,184,0.05)", marginTop: 12, overflow: "hidden" }}>
                  <motion.div initial={{ width: 0 }} animate={{ width: `${job.match ?? 0}%` }} transition={{ duration: 1, ease: "easeOut", delay: 0.3 + i * 0.08 }}
                    style={{ height: "100%", borderRadius: 2, background: T.grad }} />
                </div>
              </GlowCard>
            </motion.div>
          ))}
        </div>
        )}
      </div>

    </div>
  );
}

// ═══════════════════════════
// MAIN DASHBOARD
// ═══════════════════════════
export default function Dashboard() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, loading: authLoading, isAuthenticated, signOut } = useAuth();
  const { isMobile } = useViewportFlags();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [notifications, setNotifications] = useState<Array<{ id: string | number; text: string; time: string; unread: boolean }>>([]);
  const [rolesDigest, setRolesDigest] = useState<api.AlertsDigest | null>(null);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      navigate("/signin");
    }
  }, [authLoading, isAuthenticated, navigate]);

  useEffect(() => {
    if (!isAuthenticated) return;
    api.getNotifications().then((data) => {
      setNotifications(data.map((item) => ({ ...item, unread: Boolean((item as any).unread) })));
    }).catch(() => {
      setNotifications([]);
    });
    // Target-role digest powers the bell badge: how many roles matching the
    // user's target positions were added to the database in the last 24h.
    api.getAlertsDigest().then(setRolesDigest).catch(() => setRolesDigest(null));
  }, [isAuthenticated]);

  const displayName = user ? `${user.first_name} ${user.last_name}` : "Loading...";
  const displayPlan = user?.plan || "";
  const displayAvatar = user ? `${user.first_name?.[0] ?? "P"}${user.last_name?.[0] ?? "U"}` : "PU";
  // Admin console is intentionally NOT linked in the sidebar. It lives at an
  // unguessable top-level path and is protected by the backend allowlist.
  const navItems = NAV_ITEMS;

  const routeLabel = location.pathname.startsWith("/dashboard/jobs/") ? "Job Detail" :
    location.pathname.startsWith("/dashboard/profile") ? "Profile" :
    navItems.find((item) => item.to !== "/dashboard" ? location.pathname.startsWith(item.to) : location.pathname === "/dashboard")?.label ?? "Overview";

  const isNavItemActive = (to: string) =>
    to === "/dashboard" ? location.pathname === "/dashboard" : location.pathname.startsWith(to);
  const unread = notifications.filter((n) => n.unread).length;
  const newTargetRoles = Math.max(0, Number(rolesDigest?.total_new_24h || 0));
  const bellCount = newTargetRoles + unread;
  // Compact icon rail on EVERY dashboard page so content gets the full width.
  // Moving the mouse over the rail expands it (as an overlay — the page
  // underneath never reflows); moving away collapses it again.
  const [sidebarHovered, setSidebarHovered] = useState(false);
  const compactSidebar = !sidebarHovered;

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: T.bg, position: "relative", fontFamily: F.sans, overflowX: "hidden" }}>
      {/* Ambient orbs */}
      <div style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: 0, overflow: "hidden" }}>
        <div style={{ position: "absolute", top: "-8%", left: "-4%", width: 500, height: 500, borderRadius: "50%", filter: "blur(120px)", background: "rgba(37,99,235,0.12)" }} />
        <div style={{ position: "absolute", bottom: "5%", right: "-6%", width: 420, height: 420, borderRadius: "50%", filter: "blur(120px)", background: "rgba(59,130,246,0.09)" }} />
      </div>

      {/* ── Desktop Sidebar: 76px gutter in layout; expands over content on hover ── */}
      <div className="hidden lg:block" style={{ width: 76, flexShrink: 0, position: "relative", zIndex: 40 }}>
      <aside
        onMouseEnter={() => setSidebarHovered(true)}
        onMouseLeave={() => setSidebarHovered(false)}
        className="hidden lg:flex flex-col"
        style={{ position: "fixed", top: 0, left: 0, height: "100vh", width: compactSidebar ? 76 : 256, borderRight: `1px solid ${T.border}`, background: compactSidebar ? "rgba(1,17,38,0.85)" : "rgba(1,17,38,0.97)", backdropFilter: "blur(24px)", zIndex: 40, overflow: "hidden", transition: "width 0.22s ease, background 0.22s ease", boxShadow: compactSidebar ? "none" : "16px 0 48px rgba(1,17,38,0.55)" }}>
        {/* Logo */}
        <div style={{ padding: compactSidebar ? "0 16px" : "0 24px", height: 64, display: "flex", alignItems: "center", justifyContent: compactSidebar ? "center" : "flex-start", borderBottom: `1px solid ${T.border}` }}>
          <Link to="/" title="PlaceUp Career" style={{ display: "flex", alignItems: "center", textDecoration: "none" }}>
            {compactSidebar
              ? <BrandLogo variant="mark" height={34} />
              : <BrandLogo height={40} />}
          </Link>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: compactSidebar ? "14px 8px" : "14px 10px", display: "flex", flexDirection: "column", gap: 2 }}>
          {navItems.map((item) => (
            <NavLink key={item.label} to={item.to!} end={item.to === "/dashboard"}
              title={item.label}
              style={({ isActive }) => ({
                width: "100%",
                display: "flex",
                alignItems: "center",
                justifyContent: compactSidebar ? "center" : "flex-start",
                gap: compactSidebar ? 0 : 10,
                height: 40,
                padding: compactSidebar ? 0 : "0 12px",
                borderRadius: 10,
                textDecoration: "none",
                cursor: "pointer",
                background: isActive ? "rgba(59,130,246,0.09)" : "transparent",
                color: isActive ? T.red : T.t2,
                fontSize: 13,
                fontFamily: F.sans,
                fontWeight: isActive ? 600 : 400,
                textAlign: "left",
                position: "relative",
                transition: "all 0.2s",
                boxShadow: isActive ? "0 0 0 1px rgba(59,130,246,0.2)" : "none",
              })}
            >
              {({ isActive }) => (
                <>
                  {isActive && <div style={{ position: "absolute", left: 0, top: "50%", transform: "translateY(-50%)", width: 3, height: 18, borderRadius: 9999, background: T.grad }} />}
                  <item.icon size={17} />
                  {!compactSidebar && item.label}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Saved jobs indicator */}
        {!compactSidebar && <div style={{ padding: "10px 14px", borderTop: `1px solid ${T.border}`, borderBottom: `1px solid ${T.border}` }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: T.t3, fontFamily: F.sans }}>Saved Jobs</span>
            <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 9999, background: "rgba(59,130,246,0.12)", color: T.red, border: "1px solid rgba(59,130,246,0.25)", fontFamily: F.sans }}>5/5</span>
          </div>
          <div style={{ display: "flex", gap: 5 }}>
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} style={{ flex: 1, height: 4, borderRadius: 2, background: i <= 5 ? T.grad : "rgba(148,163,184,0.08)" }} />
            ))}
          </div>
        </div>}

        {/* User */}
        <div style={{ padding: "10px" }}>
          <motion.button whileTap={{ scale: 0.97 }} onClick={() => navigate("/dashboard/profile")}
            title={displayName}
            style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: compactSidebar ? "center" : "flex-start", gap: compactSidebar ? 0 : 10, padding: compactSidebar ? "10px 0" : "10px 12px", borderRadius: 10, border: "none", cursor: "pointer", background: "transparent", textAlign: "left", transition: "background 0.2s" }}
            className="hover:bg-[rgba(148,163,184,0.03)]">
            <div style={{ width: 34, height: 34, borderRadius: "50%", background: T.grad, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 12, fontWeight: 700, fontFamily: F.sans, boxShadow: "0 2px 8px rgba(59,130,246,0.35)", flexShrink: 0 }}>
              {displayAvatar}
            </div>
            {!compactSidebar && <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: T.text, fontFamily: F.sans, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{displayName}</div>
              <div style={{ fontSize: 11, color: T.red, fontFamily: F.sans }}>{displayPlan} Plan</div>
            </div>}
          </motion.button>
        </div>
      </aside>
      </div>

      {/* ── Mobile Sidebar ── */}
      <AnimatePresence>
        {sidebarOpen && (
          <div className={compactSidebar ? "fixed inset-0" : "lg:hidden fixed inset-0"} style={{ zIndex: 50 }}>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              onClick={() => setSidebarOpen(false)} style={{ position: "absolute", inset: 0, background: "rgba(1,17,38,0.85)", backdropFilter: "blur(4px)" }} />
            <motion.aside initial={{ x: -280 }} animate={{ x: 0 }} exit={{ x: -280 }}
              transition={{ type: "spring", stiffness: 300, damping: 30 }}
              style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 256, background: "rgba(1,17,38,0.98)", backdropFilter: "blur(24px)", borderRight: `1px solid ${T.border}`, padding: "24px 10px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", padding: "0 12px", marginBottom: 20 }}>
                <BrandLogo height={36} />
                <button onClick={() => setSidebarOpen(false)} style={{ background: "rgba(148,163,184,0.05)", border: "none", cursor: "pointer", color: T.text, padding: 6, borderRadius: 6 }}><X size={16} /></button>
              </div>
              {navItems.map((item) => (
                <button key={item.label} onClick={() => { navigate(item.to!); setSidebarOpen(false); }}
                  style={{ width: "100%", display: "flex", alignItems: "center", gap: 10, height: 40, padding: "0 12px", borderRadius: 10, border: "none", cursor: "pointer", marginBottom: 2, background: isNavItemActive(item.to!) ? "rgba(59,130,246,0.09)" : "transparent", color: isNavItemActive(item.to!) ? T.red : T.t2, fontSize: 13, fontFamily: F.sans, textAlign: "left" }}>
                  <item.icon size={16} />{item.label}
                </button>
              ))}
            </motion.aside>
          </div>
        )}
      </AnimatePresence>

      {/* ── Main Content ── */}
      <main style={{ flex: 1, minWidth: 0, overflow: "auto", position: "relative", zIndex: 1 }}>
        {/* Topbar */}
        <div style={{ position: "sticky", top: 0, zIndex: 40, height: 64, background: "rgba(1,17,38,0.85)", backdropFilter: "blur(24px)", borderBottom: `1px solid ${T.border}`, display: "flex", alignItems: "center", justifyContent: "space-between", padding: isMobile ? "0 12px" : "0 24px", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <button
              className={compactSidebar ? "" : "lg:hidden"}
              aria-label="Open navigation"
              onClick={() => setSidebarOpen(true)}
              style={{ background: "rgba(148,163,184,0.05)", border: "none", cursor: "pointer", color: T.text, padding: 8, borderRadius: 8 }}
            >
              <Menu size={18} />
            </button>
            <div>
              <div style={{ fontFamily: F.sans, fontSize: 18, fontWeight: 700, color: T.text, lineHeight: 1.2 }}>{routeLabel}</div>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: isMobile ? 6 : 8 }}>
            {/* Notifications */}
            <div style={{ position: "relative" }}>
              <motion.button whileTap={{ scale: 0.92 }} onClick={() => { setNotifOpen(!notifOpen); setUserMenuOpen(false); }}
                style={{ width: 38, height: 38, borderRadius: 10, border: `1px solid ${notifOpen ? "rgba(59,130,246,0.35)" : T.border}`, background: notifOpen ? "rgba(59,130,246,0.08)" : "rgba(148,163,184,0.04)", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", color: T.t2, position: "relative" }}>
                <Bell size={16} />
                {bellCount > 0 && (
                  <div style={{ position: "absolute", top: -5, right: -5, minWidth: 17, height: 17, padding: "0 4px", borderRadius: 9999, background: T.red, color: "#fff", fontSize: 10, fontWeight: 800, fontFamily: F.sans, display: "flex", alignItems: "center", justifyContent: "center", boxShadow: `0 0 6px ${T.red}`, lineHeight: 1 }}>
                    {bellCount > 99 ? "99+" : bellCount}
                  </div>
                )}
              </motion.button>
              <AnimatePresence>
                {notifOpen && (
                  <motion.div initial={{ opacity: 0, y: 6, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 6, scale: 0.97 }} transition={{ duration: 0.16 }}
                    style={{ position: "absolute", right: isMobile ? -52 : 0, top: "calc(100% + 8px)", width: isMobile ? "calc(100vw - 24px)" : 320, maxWidth: 320, borderRadius: 16, background: "rgba(8,14,32,0.97)", backdropFilter: "blur(24px)", border: `1px solid ${T.border}`, boxShadow: "0 20px 40px rgba(1,17,38,0.5)", overflow: "hidden" }}>
                    <div style={{ padding: "14px 20px", borderBottom: `1px solid ${T.border}`, display: "flex", justifyContent: "space-between" }}>
                      <span style={{ fontFamily: F.sans, fontSize: 14, fontWeight: 700, color: T.text }}>Notifications</span>
                      <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 9999, background: "rgba(59,130,246,0.15)", color: T.red, fontFamily: F.sans }}>{bellCount} new</span>
                    </div>
                    {newTargetRoles > 0 && (
                      <div style={{ padding: "12px 20px", borderBottom: `1px solid ${T.border}`, background: "rgba(59,130,246,0.06)" }}>
                        <div style={{ fontSize: 12.5, fontWeight: 700, color: T.text, fontFamily: F.sans, marginBottom: 6 }}>
                          {newTargetRoles} new {newTargetRoles === 1 ? "job matches" : "jobs match"} your target roles (24h)
                        </div>
                        {(rolesDigest?.target_roles || []).filter((r) => r.new_24h > 0).slice(0, 5).map((r) => (
                          <div key={r.role} style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 11.5, color: T.t2, fontFamily: F.sans, lineHeight: 1.9 }}>
                            <span>{r.role}</span>
                            <span style={{ fontWeight: 700, color: T.red }}>+{r.new_24h}</span>
                          </div>
                        ))}
                        <button onClick={() => { navigate("/dashboard/jobs"); setNotifOpen(false); }}
                          style={{ marginTop: 8, width: "100%", padding: "7px", borderRadius: 8, cursor: "pointer", background: "rgba(59,130,246,0.12)", border: "1px solid rgba(59,130,246,0.25)", color: T.red, fontSize: 11.5, fontWeight: 700, fontFamily: F.sans }}>
                          View new positions
                        </button>
                      </div>
                    )}
                    {notifications.map((n) => (
                      <div key={n.id} style={{ padding: "12px 20px", borderBottom: `1px solid ${T.border}`, background: n.unread ? "rgba(59,130,246,0.04)" : "transparent", display: "flex", gap: 10, alignItems: "flex-start" }}>
                        {n.unread && <div style={{ width: 6, height: 6, borderRadius: "50%", background: T.red, flexShrink: 0, marginTop: 5, boxShadow: `0 0 4px ${T.red}` }} />}
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: 12, color: T.t2, fontFamily: F.sans, lineHeight: 1.5 }}>{n.text}</div>
                          <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans, marginTop: 3 }}>{n.time}</div>
                        </div>
                      </div>
                    ))}
                    <div style={{ padding: "12px 20px" }}>
                      <button onClick={() => { navigate("/dashboard/alerts"); setNotifOpen(false); }} style={{ width: "100%", padding: "9px", borderRadius: 10, cursor: "pointer", background: "rgba(59,130,246,0.08)", border: "1px solid rgba(59,130,246,0.2)", color: T.red, fontSize: 12, fontWeight: 600, fontFamily: F.sans }}>
                        View All Alerts
                      </button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* User menu */}
            <div style={{ position: "relative" }}>
              <motion.button whileTap={{ scale: 0.95 }} onClick={() => { setUserMenuOpen(!userMenuOpen); setNotifOpen(false); }}
                style={{ display: "flex", alignItems: "center", gap: 7, padding: "5px 8px 5px 5px", borderRadius: 10, border: `1px solid ${T.border}`, background: "rgba(148,163,184,0.03)", cursor: "pointer" }}>
                <div style={{ width: 28, height: 28, borderRadius: "50%", background: T.grad, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 11, fontWeight: 700, fontFamily: F.sans }}>{displayAvatar}</div>
                <ChevronDown size={13} color={T.t3} />
              </motion.button>
              <AnimatePresence>
                {userMenuOpen && (
                  <motion.div initial={{ opacity: 0, y: 6, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 6, scale: 0.97 }} transition={{ duration: 0.16 }}
                    style={{ position: "absolute", right: 0, top: "calc(100% + 8px)", width: 190, borderRadius: 14, padding: 6, background: "rgba(8,14,32,0.97)", backdropFilter: "blur(24px)", border: `1px solid ${T.border}`, boxShadow: "0 16px 36px rgba(1,17,38,0.5)" }}>
                    {[{ icon: User, label: "My Profile", action: () => { navigate("/dashboard/profile"); setUserMenuOpen(false); } }, { icon: Settings, label: "Settings", action: () => { navigate("/dashboard/settings"); setUserMenuOpen(false); } }].map((item) => (
                      <button key={item.label} onClick={item.action}
                        style={{ width: "100%", display: "flex", alignItems: "center", gap: 9, padding: "9px 12px", borderRadius: 8, border: "none", cursor: "pointer", background: "transparent", color: T.t2, fontSize: 13, fontFamily: F.sans, textAlign: "left", transition: "background 0.15s" }}
                        className="hover:bg-[rgba(148,163,184,0.05)]">
                        <item.icon size={14} /> {item.label}
                      </button>
                    ))}
                    <div style={{ height: 1, background: T.border, margin: "4px 0" }} />
                    <button onClick={() => { signOut(); navigate("/signin"); }}
                      style={{ width: "100%", display: "flex", alignItems: "center", gap: 9, padding: "9px 12px", borderRadius: 8, border: "none", cursor: "pointer", background: "transparent", color: "#ef4444", fontSize: 13, fontFamily: F.sans, textAlign: "left", transition: "background 0.15s" }}
                      className="hover:bg-[rgba(239,68,68,0.06)]">
                      <LogOut size={14} /> Logout
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>

        {/* Page content */}
        <div style={{ padding: isMobile ? "16px 12px 32px" : "28px 28px 48px", maxWidth: 1280, width: "100%", boxSizing: "border-box", margin: "0 auto" }}>
          <AnimatePresence mode="wait">
            <motion.div key={location.pathname} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.22 }}>
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
      <FeedbackWidget />
    </div>
  );
}
