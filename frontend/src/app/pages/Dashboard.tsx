import { useState, useEffect } from "react";
import { motion, AnimatePresence, useMotionValue, useTransform, animate } from "motion/react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";
import {
  Home, FileText, Globe, Bell, BarChart3, Settings, LogOut,
  Search, Sun, Moon, Menu, X, User, ChevronDown, Briefcase,
  TrendingUp, ChevronRight, CheckCircle2, Bookmark, Clock,
  ArrowUpRight, Zap, Activity, MapPin, DollarSign, FileCheck,
  CreditCard, Shield,
} from "lucide-react";
import { useTheme } from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import * as api from "../lib/api";
import { ResumePage } from "../components/dashboard/ResumePage";
import { JobsPage } from "../components/dashboard/JobsPage";
import { VisaTrackerPage } from "../components/dashboard/VisaTrackerPage";
import { AlertsPage } from "../components/dashboard/AlertsPage";
import { AnalyticsPage } from "../components/dashboard/AnalyticsPage";
import { SettingsPage } from "../components/dashboard/SettingsPage";
import { UserProfilePage } from "../components/dashboard/UserProfilePage";
import { JobDetailPage } from "../components/dashboard/JobDetailPage";

// ─── Design tokens ───
const T = {
  bg:     "#011126",
  surface: "#0d1c35",
  glass:  "rgba(13,28,53,0.7)",
  cardGlass: "rgba(64,18,18,0.45)",
  border: "rgba(242,238,179,0.08)",
  borderHover: "rgba(166,55,45,0.4)",
  text:   "#F2EEB3",
  t2:     "rgba(242,238,179,0.65)",
  t3:     "rgba(242,238,179,0.4)",
  grad:   "linear-gradient(135deg, #8C3A27, #A6372D, #401212)",
  red:    "#A6372D",
  burnt:  "#8C3A27",
  dark:   "#401212",
  shadow: "0 4px 20px rgba(1,17,38,0.3)",
  shadowH: "0 20px 50px rgba(1,17,38,0.4), 0 0 0 1px rgba(166,55,45,0.3)",
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
  if (!salary) return "Not specified";
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
  { icon: Globe,    label: "Visa Tracker", to: "/dashboard/visa" },
  { icon: Bell,     label: "Alerts", to: "/dashboard/alerts" },
  { icon: BarChart3,label: "Analytics", to: "/dashboard/analytics" },
  { icon: CreditCard,label: "Billing", to: "/dashboard/billing" },
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
  const ringColor = safeScore >= 80 ? "#22c55e" : safeScore >= 60 ? "#f59e0b" : safeScore > 0 ? "#F2EEB3" : "rgba(242,238,179,0.45)";
  return (
    <div style={{ position: "relative", width: 120, height: 120, flexShrink: 0 }}>
      <svg viewBox="0 0 120 120" style={{ width: "100%", height: "100%", transform: "rotate(-90deg)" }}>
        <defs>
          <linearGradient id="atsG" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={T.burnt} /><stop offset="50%" stopColor={T.red} /><stop offset="100%" stopColor={T.dark} />
          </linearGradient>
          <filter id="atsGlow"><feGaussianBlur stdDeviation="3" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
        </defs>
        <circle cx="60" cy="60" r={r} fill="none" stroke="rgba(242,238,179,0.16)" strokeWidth="9" />
        <motion.circle cx="60" cy="60" r={r} fill="none" stroke={ringColor} strokeWidth="9" strokeLinecap="round"
          strokeDasharray={circ} initial={{ strokeDashoffset: circ }} animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1.5, ease: "easeOut" }} filter="url(#atsGlow)" />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <span style={{ fontFamily: F.mono, fontSize: 28, fontWeight: 800, color: "#F2EEB3", lineHeight: 1, textShadow: "0 0 16px rgba(242,238,179,0.22)" }}>{safeScore || "--"}</span>
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
        style={{ background: "radial-gradient(ellipse at 50% -25%, rgba(166,55,45,0.16) 0%, transparent 65%)", zIndex: 0 }} />
      <div className="absolute top-0 left-0 right-0 h-px pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-500"
        style={{ background: "linear-gradient(to right, transparent, rgba(166,55,45,0.45), transparent)" }} />
      <div style={{ position: "relative", zIndex: 1 }}>{children}</div>
    </motion.div>
  );
}

// ═══════════════════════════
// OVERVIEW PAGE
// ═══════════════════════════
export function OverviewPage({ onJobClick }: { onJobClick?: (id: string | number) => void }) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { isMobile, isTablet } = useViewportFlags();
  type FeaturedJob = { id: string | number; title: string; company: string; location: string; salary: string; match: number; visa: string[]; posted: string };
  const [featuredJobs, setFeaturedJobs] = useState<FeaturedJob[]>([]);
  const [totalJobs, setTotalJobs] = useState(0);
  const [resumeScore, setResumeScore] = useState(0);
  const [hasResume, setHasResume] = useState(false);
  const [activeResumeName, setActiveResumeName] = useState("");
  const [totalApplications, setTotalApplications] = useState(0);
  const [totalResumes, setTotalResumes] = useState(0);
  type ActivityItem = { icon: typeof Zap; label: string; sub: string; time: string; color: string };
  const [activityItems, setActivityItems] = useState<ActivityItem[]>([]);

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
    api.getTopMatches({ limit: 3 })
      .then((response) => {
        if (!active) return;
        setFeaturedJobs(response.jobs.map((job) => ({
          id: job.id ?? "",
          title: job.title ?? "Untitled role",
          company: job.company ?? "Unknown",
          location: job.location ?? "Remote",
          salary: formatSalary(job.salary),
          match: job.match_score ?? 0,
          visa: normalizeVisa(job.visa),
          posted: job.posted_at ?? "Recently",
        })));
      })
      .catch(() => {});
    return () => { active = false; };
  }, []);

  // Fetch dashboard summary (resume score, applications, activity)
  useEffect(() => {
    let active = true;
    Promise.allSettled([
      api.getDashboardSummary(),
      api.getResumeList(),
      api.getJobPipelineStatus(),
    ])
      .then(([summaryResult, resumesResult, pipelineResult]) => {
        if (!active) return;
        const summary = summaryResult.status === "fulfilled" ? summaryResult.value : null;
        const resumes = resumesResult.status === "fulfilled" ? resumesResult.value : [];
        const pipeline = pipelineResult.status === "fulfilled" ? pipelineResult.value : null;
        const activeResume = resumes.find((resume) => resume.active) || resumes[0];

        if (!summary && !resumes.length && !pipeline) return;

        const resolvedScore = Number(summary?.resume_score || activeResume?.score || 0);
        const resolvedResumeCount = Math.max(
          Number(summary?.total_resumes || 0),
          resumes.length,
          activeResume ? 1 : 0,
        );
        const resolvedResumeName = summary?.active_resume_name || activeResume?.name || "";

        setResumeScore(resolvedScore);
        setHasResume(Boolean(summary?.has_resume || resolvedResumeName || resolvedResumeCount > 0));
        setActiveResumeName(resolvedResumeName);
        setTotalApplications(Number(summary?.total_applications || 0));
        setTotalResumes(resolvedResumeCount);
        setTotalJobs(Number(pipeline?.total_jobs || pipeline?.active_jobs || summary?.total_jobs || 0));
        // Derive activity feed from recent alerts
        const items: ActivityItem[] = (summary?.recent_alerts || []).map((a) => {
          const matchPct = a.match_score;
          return {
            icon: matchPct > 0 ? Zap : Bell,
            label: matchPct > 0 ? `New match: ${a.title} (${matchPct}%)` : (a.message || a.title),
            sub: a.company ? `at ${a.company}` : "Job alert",
            time: a.time,
            color: matchPct > 80 ? T.red : T.burnt,
          };
        });
        setActivityItems(items);
      })
      .catch(() => {});
    return () => { active = false; };
  }, []);

  const visibleJobs = featuredJobs;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: isMobile ? 16 : 22, width: "100%", minWidth: 0 }}>
      {/* Welcome */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
        <h2 style={{ fontFamily: F.sans, fontSize: 22, fontWeight: 700, color: T.text, marginBottom: 4 }}>{greeting}, {displayFirstName}! 👋</h2>
        <p style={{ fontSize: 14, color: T.t2, fontFamily: F.sans }}>
          Showing {visibleJobs.length} of {totalJobs.toLocaleString()} scraped jobs available in your dashboard.
        </p>
      </motion.div>

      {/* 4-stat row */}
      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : isTablet ? "repeat(2, minmax(0, 1fr))" : "repeat(4, 1fr)", gap: 14 }}>
        {/* ATS Score */}
        <GlowCard style={{ padding: 20, gridColumn: "span 1" }}>
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
        <GlowCard style={{ padding: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
            <div style={{ width: 36, height: 36, borderRadius: 10, background: "rgba(166,55,45,0.1)", border: "1px solid rgba(166,55,45,0.2)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <Briefcase size={16} color={T.red} />
            </div>
          </div>
          <div style={{ fontFamily: F.sans, fontSize: isMobile ? 30 : 38, fontWeight: 800, color: T.text, lineHeight: 1, marginBottom: 4 }}><SpringCounter target={totalJobs} /></div>
          <div style={{ fontSize: 13, color: T.t2, fontFamily: F.sans }}>Scraped jobs</div>
          <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans, marginTop: 2 }}>In database</div>
        </GlowCard>

        {/* Applications */}
        <GlowCard style={{ padding: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
            <div style={{ width: 36, height: 36, borderRadius: 10, background: "rgba(140,58,39,0.1)", border: "1px solid rgba(140,58,39,0.2)", display: "flex", alignItems: "center", justifyContent: "center" }}>
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
          <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans, marginTop: 2 }}>Tracked submissions</div>
        </GlowCard>

        {/* Resumes */}
        <GlowCard style={{ padding: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
            <div style={{ width: 36, height: 36, borderRadius: 10, background: "rgba(64,18,18,0.2)", border: "1px solid rgba(64,18,18,0.4)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <FileCheck size={16} color={T.text} />
            </div>
            {hasResume && (
              <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 8px", borderRadius: 9999, background: "rgba(166,55,45,0.12)", color: T.red, border: "1px solid rgba(166,55,45,0.25)", fontFamily: F.sans }}>Active</span>
            )}
          </div>
          <div style={{ fontFamily: F.sans, fontSize: isMobile ? 30 : 38, fontWeight: 800, color: T.text, lineHeight: 1, marginBottom: 4 }}><SpringCounter target={totalResumes} /></div>
          <div style={{ fontSize: 13, color: T.t2, fontFamily: F.sans }}>Resumes</div>
          <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans, marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{activeResumeName || "Uploaded files"}</div>
        </GlowCard>
      </div>

      {/* Featured Jobs */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: T.red, fontFamily: F.sans }}>⭐ Featured Positions</span>
          <button onClick={() => navigate("/dashboard/jobs")} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, color: T.red, fontFamily: F.sans, background: "none", border: "none", cursor: "pointer" }}>
            View All <ChevronRight size={13} />
          </button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : isTablet ? "repeat(2, minmax(0, 1fr))" : "repeat(3, 1fr)", gap: 14 }}>
          {visibleJobs.map((job, i) => (
            <motion.div key={job.id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 + i * 0.08 }}>
              <GlowCard style={{ padding: 20 }} onClick={() => handleJobClick(job.id)}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                  <div style={{ width: 40, height: 40, borderRadius: "50%", background: T.grad, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, fontWeight: 700, color: "#fff", fontFamily: F.sans, boxShadow: "0 0 12px rgba(166,55,45,0.3)" }}>
                    {job.company[0]}
                  </div>
                  <span style={{ fontSize: 16, fontWeight: 800, color: T.red, fontFamily: F.mono }}>{job.match}%</span>
                </div>
                <div style={{ fontSize: 14, fontWeight: 600, color: T.text, fontFamily: F.sans, marginBottom: 4, lineHeight: 1.3 }}>{job.title}</div>
                <div style={{ fontSize: 12, color: T.t2, fontFamily: F.sans, marginBottom: 10 }}>{job.company}</div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
                  {job.visa.map((v) => (
                    <span key={v} style={{ fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 4, background: "rgba(140,58,39,0.15)", color: T.burnt, border: "1px solid rgba(140,58,39,0.3)", fontFamily: F.sans }}>{v}</span>
                  ))}
                </div>
                <div style={{ display: "flex", gap: 8, fontSize: 11, color: T.t3, fontFamily: F.sans }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 3 }}><MapPin size={10} />{job.location}</span>
                  <span style={{ display: "flex", alignItems: "center", gap: 3 }}><DollarSign size={10} />{job.salary}</span>
                </div>
                <div style={{ height: 3, borderRadius: 2, background: "rgba(242,238,179,0.05)", marginTop: 12, overflow: "hidden" }}>
                  <motion.div initial={{ width: 0 }} animate={{ width: `${job.match}%` }} transition={{ duration: 1, ease: "easeOut", delay: 0.3 + i * 0.08 }}
                    style={{ height: "100%", borderRadius: 2, background: T.grad }} />
                </div>
              </GlowCard>
            </motion.div>
          ))}
        </div>
      </div>

      {/* Recent Activity */}
      <GlowCard style={{ overflow: "hidden" }}>
        <div style={{ padding: "18px 24px", borderBottom: `1px solid ${T.border}`, display: "flex", justifyContent: "space-between" }}>
          <span style={{ fontFamily: F.sans, fontSize: 15, fontWeight: 600, color: T.text }}>Recent Activity</span>
          <Activity size={16} color={T.t3} />
        </div>
        {activityItems.length === 0 && (
          <div style={{ padding: "24px", textAlign: "center", color: T.t3, fontSize: 13, fontFamily: F.sans }}>
            No recent activity yet. Alerts and matches will appear here.
          </div>
        )}
        {activityItems.map((item, i) => (
          <motion.div key={i} initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.4 + i * 0.07 }}
            style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 24px", borderBottom: i < activityItems.length - 1 ? `1px solid ${T.border}` : "none" }}>
            <div style={{ width: 36, height: 36, borderRadius: 10, background: "rgba(166,55,45,0.1)", border: "1px solid rgba(166,55,45,0.18)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <item.icon size={15} color={item.color} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: T.text, fontFamily: F.sans, marginBottom: 1 }}>{item.label}</div>
              <div style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>{item.sub}</div>
            </div>
            <span style={{ fontSize: 11, color: T.t3, fontFamily: F.sans, flexShrink: 0 }}>{item.time}</span>
          </motion.div>
        ))}
      </GlowCard>
    </div>
  );
}

// ═══════════════════════════
// MAIN DASHBOARD
// ═══════════════════════════
export default function Dashboard() {
  const { dark, toggle } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const { user, loading: authLoading, isAuthenticated, signOut } = useAuth();
  const { isMobile } = useViewportFlags();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [notifications, setNotifications] = useState<Array<{ id: string | number; text: string; time: string; unread: boolean }>>([]);

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
  }, [isAuthenticated]);

  const displayName = user ? `${user.first_name} ${user.last_name}` : "Loading...";
  const displayPlan = user?.plan || "";
  const displayAvatar = user ? `${user.first_name?.[0] ?? "P"}${user.last_name?.[0] ?? "U"}` : "PU";
  const isAdmin = String(user?.plan || "").toLowerCase() === "admin" || ["admin@placeupcareer.com", "jobs@placeupcareer.com"].includes(String(user?.email || "").toLowerCase());
  const navItems = isAdmin ? [...NAV_ITEMS, { icon: Shield, label: "Admin", to: "/dashboard/admin" }] : NAV_ITEMS;

  const routeLabel = location.pathname.startsWith("/dashboard/jobs/") ? "Job Detail" :
    location.pathname.startsWith("/dashboard/profile") ? "Profile" :
    navItems.find((item) => item.to !== "/dashboard" ? location.pathname.startsWith(item.to) : location.pathname === "/dashboard")?.label ?? "Overview";

  const unread = notifications.filter((n) => n.unread).length;

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: T.bg, position: "relative", fontFamily: F.sans, overflowX: "hidden" }}>
      {/* Ambient orbs */}
      <div style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: 0, overflow: "hidden" }}>
        <div style={{ position: "absolute", top: "-8%", left: "-4%", width: 500, height: 500, borderRadius: "50%", filter: "blur(120px)", background: "rgba(140,58,39,0.12)" }} />
        <div style={{ position: "absolute", bottom: "5%", right: "-6%", width: 420, height: 420, borderRadius: "50%", filter: "blur(120px)", background: "rgba(166,55,45,0.09)" }} />
      </div>

      {/* ── Desktop Sidebar ── */}
      <aside className="hidden lg:flex flex-col" style={{ width: 256, borderRight: `1px solid ${T.border}`, background: "rgba(1,17,38,0.85)", backdropFilter: "blur(24px)", position: "relative", zIndex: 10, flexShrink: 0 }}>
        {/* Logo */}
        <div style={{ padding: "0 24px", height: 64, display: "flex", alignItems: "center", borderBottom: `1px solid ${T.border}` }}>
          <Link to="/" style={{ display: "flex", alignItems: "center", gap: 10, textDecoration: "none" }}>
            <div style={{ width: 32, height: 32, borderRadius: 9, background: T.grad, display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 0 14px rgba(166,55,45,0.35)" }}>
              <span style={{ color: "#fff", fontSize: 13, fontWeight: 800, fontFamily: F.sans }}>P</span>
            </div>
            <span style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 16, color: T.text, letterSpacing: "-0.02em" }}>
              PlaceUp <span style={{ color: T.red, fontSize: 13, fontWeight: 600 }}>Career</span>
            </span>
          </Link>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: "14px 10px", display: "flex", flexDirection: "column", gap: 2 }}>
          {navItems.map((item) => (
            <NavLink key={item.label} to={item.to!} end={item.to === "/dashboard"}
              style={({ isActive }) => ({
                width: "100%",
                display: "flex",
                alignItems: "center",
                gap: 10,
                height: 40,
                padding: "0 12px",
                borderRadius: 10,
                textDecoration: "none",
                cursor: "pointer",
                background: isActive ? "rgba(166,55,45,0.09)" : "transparent",
                color: isActive ? T.red : T.t2,
                fontSize: 13,
                fontFamily: F.sans,
                fontWeight: isActive ? 600 : 400,
                textAlign: "left",
                position: "relative",
                transition: "all 0.2s",
                boxShadow: isActive ? "0 0 0 1px rgba(166,55,45,0.2)" : "none",
              })}
            >
              {({ isActive }) => (
                <>
                  {isActive && <div style={{ position: "absolute", left: 0, top: "50%", transform: "translateY(-50%)", width: 3, height: 18, borderRadius: 9999, background: T.grad }} />}
                  <item.icon size={17} />
                  {item.label}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Saved jobs indicator */}
        <div style={{ padding: "10px 14px", borderTop: `1px solid ${T.border}`, borderBottom: `1px solid ${T.border}` }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: T.t3, fontFamily: F.sans }}>Saved Jobs</span>
            <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 9999, background: "rgba(166,55,45,0.12)", color: T.red, border: "1px solid rgba(166,55,45,0.25)", fontFamily: F.sans }}>5/5</span>
          </div>
          <div style={{ display: "flex", gap: 5 }}>
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} style={{ flex: 1, height: 4, borderRadius: 2, background: i <= 5 ? T.grad : "rgba(242,238,179,0.08)" }} />
            ))}
          </div>
        </div>

        {/* User */}
        <div style={{ padding: "10px" }}>
          <motion.button whileTap={{ scale: 0.97 }} onClick={() => navigate("/dashboard/profile")}
            style={{ width: "100%", display: "flex", alignItems: "center", gap: 10, padding: "10px 12px", borderRadius: 10, border: "none", cursor: "pointer", background: "transparent", textAlign: "left", transition: "background 0.2s" }}
            className="hover:bg-[rgba(242,238,179,0.03)]">
            <div style={{ width: 34, height: 34, borderRadius: "50%", background: T.grad, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 12, fontWeight: 700, fontFamily: F.sans, boxShadow: "0 2px 8px rgba(166,55,45,0.35)", flexShrink: 0 }}>
              {displayAvatar}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: T.text, fontFamily: F.sans, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{displayName}</div>
              <div style={{ fontSize: 11, color: T.red, fontFamily: F.sans }}>{displayPlan} Plan</div>
            </div>
          </motion.button>
        </div>
      </aside>

      {/* ── Mobile Sidebar ── */}
      <AnimatePresence>
        {sidebarOpen && (
          <div className="lg:hidden fixed inset-0" style={{ zIndex: 50 }}>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              onClick={() => setSidebarOpen(false)} style={{ position: "absolute", inset: 0, background: "rgba(1,17,38,0.85)", backdropFilter: "blur(4px)" }} />
            <motion.aside initial={{ x: -280 }} animate={{ x: 0 }} exit={{ x: -280 }}
              transition={{ type: "spring", stiffness: 300, damping: 30 }}
              style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 256, background: "rgba(1,17,38,0.98)", backdropFilter: "blur(24px)", borderRight: `1px solid ${T.border}`, padding: "24px 10px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", padding: "0 12px", marginBottom: 20 }}>
                <span style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 16, color: T.text }}>PlaceUp</span>
                <button onClick={() => setSidebarOpen(false)} style={{ background: "rgba(242,238,179,0.05)", border: "none", cursor: "pointer", color: T.text, padding: 6, borderRadius: 6 }}><X size={16} /></button>
              </div>
              {navItems.map((item) => (
                <button key={item.label} onClick={() => { navigate(item.to!); setSidebarOpen(false); }}
                  style={{ width: "100%", display: "flex", alignItems: "center", gap: 10, height: 40, padding: "0 12px", borderRadius: 10, border: "none", cursor: "pointer", marginBottom: 2, background: location.pathname.startsWith(item.to!) ? "rgba(166,55,45,0.09)" : "transparent", color: location.pathname.startsWith(item.to!) ? T.red : T.t2, fontSize: 13, fontFamily: F.sans, textAlign: "left" }}>
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
            <button className="lg:hidden" onClick={() => setSidebarOpen(true)} style={{ background: "rgba(242,238,179,0.05)", border: "none", cursor: "pointer", color: T.text, padding: 8, borderRadius: 8 }}>
              <Menu size={18} />
            </button>
            <div>
              <div style={{ fontFamily: F.sans, fontSize: 18, fontWeight: 700, color: T.text, lineHeight: 1.2 }}>{routeLabel}</div>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: isMobile ? 6 : 8 }}>
            {/* Search */}
            <div className="hidden sm:flex items-center gap-2" style={{ height: 38, padding: "0 12px", borderRadius: 10, background: "rgba(242,238,179,0.04)", border: `1px solid ${T.border}` }}>
              <Search size={14} color={T.t3} />
              <input placeholder="Search jobs..." style={{ background: "transparent", border: "none", outline: "none", width: 160, fontSize: 13, color: T.text, fontFamily: F.sans }} />
            </div>

            {/* Theme toggle */}
            <motion.button whileTap={{ scale: 0.92 }} onClick={toggle} style={{ width: 38, height: 38, borderRadius: 10, border: `1px solid ${T.border}`, background: "rgba(242,238,179,0.04)", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", color: T.t2 }}>
              {dark ? <Sun size={16} /> : <Moon size={16} />}
            </motion.button>

            {/* Notifications */}
            <div style={{ position: "relative" }}>
              <motion.button whileTap={{ scale: 0.92 }} onClick={() => { setNotifOpen(!notifOpen); setUserMenuOpen(false); }}
                style={{ width: 38, height: 38, borderRadius: 10, border: `1px solid ${notifOpen ? "rgba(166,55,45,0.35)" : T.border}`, background: notifOpen ? "rgba(166,55,45,0.08)" : "rgba(242,238,179,0.04)", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", color: T.t2, position: "relative" }}>
                <Bell size={16} />
                {unread > 0 && <div style={{ position: "absolute", top: 7, right: 7, width: 7, height: 7, borderRadius: "50%", background: T.red, boxShadow: `0 0 6px ${T.red}` }} />}
              </motion.button>
              <AnimatePresence>
                {notifOpen && (
                  <motion.div initial={{ opacity: 0, y: 6, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 6, scale: 0.97 }} transition={{ duration: 0.16 }}
                    style={{ position: "absolute", right: isMobile ? -52 : 0, top: "calc(100% + 8px)", width: isMobile ? "calc(100vw - 24px)" : 320, maxWidth: 320, borderRadius: 16, background: "rgba(8,14,32,0.97)", backdropFilter: "blur(24px)", border: `1px solid ${T.border}`, boxShadow: "0 20px 40px rgba(1,17,38,0.5)", overflow: "hidden" }}>
                    <div style={{ padding: "14px 20px", borderBottom: `1px solid ${T.border}`, display: "flex", justifyContent: "space-between" }}>
                      <span style={{ fontFamily: F.sans, fontSize: 14, fontWeight: 700, color: T.text }}>Notifications</span>
                      <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 9999, background: "rgba(166,55,45,0.15)", color: T.red, fontFamily: F.sans }}>{unread} new</span>
                    </div>
                    {notifications.map((n) => (
                      <div key={n.id} style={{ padding: "12px 20px", borderBottom: `1px solid ${T.border}`, background: n.unread ? "rgba(166,55,45,0.04)" : "transparent", display: "flex", gap: 10, alignItems: "flex-start" }}>
                        {n.unread && <div style={{ width: 6, height: 6, borderRadius: "50%", background: T.red, flexShrink: 0, marginTop: 5, boxShadow: `0 0 4px ${T.red}` }} />}
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: 12, color: T.t2, fontFamily: F.sans, lineHeight: 1.5 }}>{n.text}</div>
                          <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans, marginTop: 3 }}>{n.time}</div>
                        </div>
                      </div>
                    ))}
                    <div style={{ padding: "12px 20px" }}>
                      <button onClick={() => { navigate("/dashboard/alerts"); setNotifOpen(false); }} style={{ width: "100%", padding: "9px", borderRadius: 10, cursor: "pointer", background: "rgba(166,55,45,0.08)", border: "1px solid rgba(166,55,45,0.2)", color: T.red, fontSize: 12, fontWeight: 600, fontFamily: F.sans }}>
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
                style={{ display: "flex", alignItems: "center", gap: 7, padding: "5px 8px 5px 5px", borderRadius: 10, border: `1px solid ${T.border}`, background: "rgba(242,238,179,0.03)", cursor: "pointer" }}>
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
                        className="hover:bg-[rgba(242,238,179,0.05)]">
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
    </div>
  );
}
