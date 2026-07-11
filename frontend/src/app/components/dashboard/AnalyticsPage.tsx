import { useState, useEffect } from "react";
import { Link } from "react-router";
import { motion } from "motion/react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar, Cell, CartesianGrid } from "recharts";
import { TrendingUp, Award, ExternalLink } from "lucide-react";
import { LoadingLogo } from "../LoadingLogo";

function useViewportFlags() {
  const getWidth = () => (typeof window === "undefined" ? 1280 : window.innerWidth);
  const [width, setWidth] = useState(getWidth);
  useEffect(() => {
    const onResize = () => setWidth(getWidth());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return { isMobile: width < 640, isTablet: width < 1024 };
}
import * as api from "../../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  text: "var(--pu-f1f5f9-t)", t2: "var(--pu-226-232-240-072)", t3: "var(--pu-148-163-184-075)",
  border: "var(--pu-148-163-184-008)", glass: "var(--pu-15-30-55-055)",
  grad: "linear-gradient(135deg, var(--pu-2563eb), var(--pu-0ea5e9))", red: "var(--pu-3b82f6-t)", burnt: "var(--pu-60a5fa-t)",
};

interface MetricCard {
  icon: typeof TrendingUp;
  label: string;
  value: string;
  trend: string;
  color: string;
}

interface TimePoint { month: string; apps: number; interviews: number; matches: number }
interface ScorePoint { version: string; score: number }

const ICON_BY_LABEL: Record<string, typeof TrendingUp> = {
  applications: TrendingUp,
  "top match": Award,
};

function withTimeout<T>(promise: Promise<T>, ms: number, fallback: T): Promise<T> {
  return new Promise((resolve) => {
    const timer = window.setTimeout(() => resolve(fallback), ms);
    promise.then(
      (value) => { window.clearTimeout(timer); resolve(value); },
      () => { window.clearTimeout(timer); resolve(fallback); },
    );
  });
}

export function AnalyticsPage() {
  const { isMobile, isTablet } = useViewportFlags();
  const [metrics, setMetrics] = useState<MetricCard[]>([]);
  const [timeSeries, setTimeSeries] = useState<TimePoint[]>([]);
  const [scoreData, setScoreData] = useState<ScorePoint[]>([]);
  const [applications, setApplications] = useState<api.UserApplicationRow[]>([]);
  const [market, setMarket] = useState<api.MarketAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api.getMarketAnalytics()
      .then((m) => { if (active) setMarket(m); })
      .catch(() => { if (active) setMarket(null); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    Promise.all([
      withTimeout(api.getAnalyticsDashboard(), 8000, { metrics: [], applications_over_time: [], ats_score_history: [] }),
      withTimeout(api.getUserApplications(), 8000, []),
    ])
      .then(([data, appRows]) => {
        if (!active) return;

        if (Array.isArray(data.metrics) && data.metrics.length) {
          setMetrics(
            data.metrics.filter((m) => !["profile views", "resume downloads"].includes((m.label || "").toLowerCase())).map((m, i) => {
              const key = (m.label || "").toLowerCase();
              const Icon = ICON_BY_LABEL[key] ?? TrendingUp;
              const color = i % 2 === 0 ? T.red : T.burnt;
              return { icon: Icon, label: m.label, value: m.value, trend: m.trend, color };
            }),
          );
        }

        const time = data.applications_over_time ?? data.time_series;
        if (Array.isArray(time) && time.length) setTimeSeries(time as TimePoint[]);

        const scores = data.ats_score_history ?? data.resume_scores;
        if (Array.isArray(scores) && scores.length) setScoreData(scores as ScorePoint[]);
        setApplications(appRows || []);
      })
      .catch((err) => {
        if (active) setError((err as Error).message || "Could not load analytics.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  if (loading) {
    return <LoadingLogo label="Loading analytics" />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {error && <div style={{ color: T.red, fontFamily: F.sans, fontSize: 13 }}>Error: {error}</div>}
      {/* Metric cards */}
      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr 1fr" : isTablet ? "repeat(2, 1fr)" : "repeat(4, 1fr)", gap: 14 }}>
        {metrics.length === 0 && (
          <div style={{ gridColumn: "1 / -1", padding: 30, textAlign: "center", color: T.t3, fontFamily: F.sans, background: T.glass, border: `1px solid ${T.border}`, borderRadius: 16 }}>
            No analytics yet. Upload a resume and start tracking applications to populate this page.
          </div>
        )}
        {metrics.map((m, i) => (
          <motion.div key={m.label} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.08 }}
            style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 16, padding: "20px" }}>
            <div style={{ width: 36, height: 36, borderRadius: 10, background: "var(--pu-59-130-246-01)", border: "1px solid var(--pu-59-130-246-02)", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 14 }}>
              <m.icon size={16} color={m.color} />
            </div>
            <div style={{ fontFamily: F.sans, fontSize: 30, fontWeight: 800, color: m.color, lineHeight: 1, marginBottom: 4 }}>{m.value}</div>
            <div style={{ fontSize: 13, fontWeight: 500, color: T.text, fontFamily: F.sans, marginBottom: 2 }}>{m.label}</div>
            <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans }}>{m.trend}</div>
          </motion.div>
        ))}
      </div>

      {/* Live job market — always-populated, real backend data */}
      {market && (
        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: 24 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap", marginBottom: 18 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <TrendingUp size={15} color={T.red} />
              <span style={{ fontFamily: F.sans, fontSize: 15, fontWeight: 700, color: T.text }}>Live job market</span>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontFamily: F.mono, fontSize: 22, fontWeight: 800, color: T.red, lineHeight: 1 }}>{(market.total_active || 0).toLocaleString()}</div>
              <div style={{ fontSize: 10.5, color: T.t3, fontFamily: F.sans }}>{market.targeted ? "target-role positions" : "active positions"}</div>
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: isTablet ? "1fr" : "1.5fr 1fr", gap: 16 }}>
            <div>
              <div style={{ fontFamily: F.sans, fontSize: 12.5, fontWeight: 600, color: T.t2, marginBottom: 10 }}>Positions added — last 14 days</div>
              {(market.added_series || []).length === 0 ? (
                <div style={{ height: 200, display: "flex", alignItems: "center", justifyContent: "center", color: T.t3, fontFamily: F.sans, fontSize: 13 }}>No recent additions recorded.</div>
              ) : (
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={(market.added_series || []).map((p) => ({ label: new Date(p.date + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" }), count: p.count }))} margin={{ top: 6, right: 8, bottom: 0, left: -20 }}>
                    <defs>
                      <linearGradient id="mktFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--pu-3b82f6-b)" stopOpacity={0.5} />
                        <stop offset="100%" stopColor="var(--pu-3b82f6-b)" stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--pu-148-163-184-006)" vertical={false} />
                    <XAxis dataKey="label" tick={{ fill: T.t3, fontSize: 11, fontFamily: F.sans }} axisLine={false} tickLine={false} minTickGap={18} />
                    <YAxis allowDecimals={false} tick={{ fill: T.t3, fontSize: 11, fontFamily: F.sans }} axisLine={false} tickLine={false} width={40} />
                    <Tooltip contentStyle={{ background: "var(--pu-8-14-32-096)", border: `1px solid ${T.border}`, borderRadius: 10, color: T.text, fontFamily: F.sans, fontSize: 12 }} formatter={(v: number) => [`${v} new`, "Positions"]} />
                    <Area type="monotone" dataKey="count" stroke="var(--pu-3b82f6-t)" strokeWidth={2} fill="url(#mktFill)" activeDot={{ r: 4 }} />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </div>
            <div>
              <div style={{ fontFamily: F.sans, fontSize: 12.5, fontWeight: 600, color: T.t2, marginBottom: 10 }}>Top countries</div>
              {(market.by_country || []).length === 0 ? (
                <div style={{ height: 200, display: "flex", alignItems: "center", justifyContent: "center", color: T.t3, fontFamily: F.sans, fontSize: 13 }}>No country data.</div>
              ) : (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={(market.by_country || []).map((c) => ({ key: c.key, count: c.count }))} layout="vertical" margin={{ top: 0, right: 12, bottom: 0, left: 8 }}>
                    <XAxis type="number" hide />
                    <YAxis type="category" dataKey="key" tick={{ fill: T.t2, fontSize: 11, fontFamily: F.sans }} axisLine={false} tickLine={false} width={44} />
                    <Tooltip cursor={{ fill: "var(--pu-59-130-246-008)" }} contentStyle={{ background: "var(--pu-8-14-32-096)", border: `1px solid ${T.border}`, borderRadius: 10, color: T.text, fontFamily: F.sans, fontSize: 12 }} formatter={(v: number) => [v.toLocaleString(), "Positions"]} />
                    <Bar dataKey="count" radius={[0, 6, 6, 0]} fill="var(--pu-3b82f6-t)" />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>
        </div>
      )}

      <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: 24 }}>
        <div style={{ fontFamily: F.sans, fontSize: 15, fontWeight: 600, color: T.text, marginBottom: 16 }}>Applied Positions</div>
        {applications.length === 0 ? (
          <div style={{ color: T.t3, fontFamily: F.sans, fontSize: 13 }}>No applied positions yet.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {applications.map((app) => (
              <div key={`${app.job_id}-${app.updated_at || app.created_at || app.title}`} style={{ padding: 14, borderRadius: 14, border: `1px solid ${T.border}`, background: "var(--pu-148-163-184-004)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start", flexWrap: "wrap" }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: T.text, fontFamily: F.sans }}>{app.title || "Applied position"}</div>
                    <div style={{ fontSize: 12, color: T.t2, fontFamily: F.sans, marginTop: 3 }}>{app.company || "Unknown company"} · {app.location || "Location not specified"}</div>
                  </div>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    <span style={{ fontSize: 11, color: T.red, fontFamily: F.sans, fontWeight: 700 }}>{app.match_score || 0}% match</span>
                    {app.job_id && (
                      // Link to OUR job post page (not the company URL) — company
                      // listings often get closed once interviews start.
                      <Link to={`/dashboard/jobs/${app.job_id}`} style={{ display: "inline-flex", alignItems: "center", gap: 5, color: T.t2, fontSize: 11, fontFamily: F.sans, textDecoration: "none" }}>
                        <ExternalLink size={12} /> Job post
                      </Link>
                    )}
                  </div>
                </div>
                {(app.description || app.notes) && (
                  <div style={{ marginTop: 10, fontSize: 12, color: T.t3, fontFamily: F.sans, lineHeight: 1.55, display: "-webkit-box", WebkitLineClamp: 4, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                    {app.description || app.notes}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Charts */}
      <div style={{ display: "grid", gridTemplateColumns: isTablet ? "1fr" : "1.5fr 1fr", gap: 16 }}>
        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: 24 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start", flexWrap: "wrap", marginBottom: 18 }}>
            <div>
              <div style={{ fontFamily: F.sans, fontSize: 15, fontWeight: 700, color: T.text }}>Applications Over Time</div>
              <div style={{ fontFamily: F.sans, fontSize: 12, color: T.t3, marginTop: 3 }}>Tracked applications and interviews by period.</div>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {[{ label: "Applications", value: timeSeries.reduce((sum, point) => sum + (point.apps || 0), 0), color: T.red }, { label: "Interviews", value: timeSeries.reduce((sum, point) => sum + (point.interviews || 0), 0), color: T.burnt }].map((item) => (
                <div key={item.label} style={{ minWidth: 92, padding: "8px 10px", borderRadius: 10, border: `1px solid ${T.border}`, background: "var(--pu-148-163-184-004)" }}>
                  <div style={{ fontFamily: F.mono, fontSize: 18, fontWeight: 700, color: item.color, lineHeight: 1 }}>{item.value}</div>
                  <div style={{ fontFamily: F.sans, fontSize: 10, color: T.t3, marginTop: 3 }}>{item.label}</div>
                </div>
              ))}
            </div>
          </div>
          {timeSeries.length === 0 ? (
            <div style={{ height: 200, display: "flex", alignItems: "center", justifyContent: "center", color: T.t3, fontFamily: F.sans, fontSize: 13 }}>No application timeline yet.</div>
          ) : (
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={timeSeries} margin={{ top: 8, right: 10, bottom: 0, left: -18 }}>
              <defs>
                <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--pu-3b82f6-b)" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="var(--pu-3b82f6-b)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="var(--pu-148-163-184-008)" vertical={false} />
              <XAxis dataKey="month" tick={{ fill: T.t3, fontSize: 11, fontFamily: F.sans }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: T.t3, fontSize: 11, fontFamily: F.sans }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: "var(--pu-15-30-55-09)", border: "1px solid var(--pu-148-163-184-01)", borderRadius: 10, color: T.text, fontFamily: F.sans, fontSize: 12 }} />
              <Area type="monotone" dataKey="apps" stroke="var(--pu-3b82f6-t)" strokeWidth={2} fill="url(#areaGrad)" />
              <Area type="monotone" dataKey="interviews" stroke="var(--pu-60a5fa-t)" strokeWidth={2} fill="none" strokeDasharray="4 2" />
            </AreaChart>
          </ResponsiveContainer>
          )}
          <div style={{ display: "flex", gap: 16, marginTop: 8 }}>
            {[{ color: T.red, label: "Applications" }, { color: T.burnt, label: "Interviews" }].map((l) => (
              <div key={l.label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <div style={{ width: 20, height: 2, background: l.color, borderRadius: 1 }} />
                <span style={{ fontSize: 11, color: T.t3, fontFamily: F.sans }}>{l.label}</span>
              </div>
            ))}
          </div>
        </div>

        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: 24 }}>
          <div style={{ fontFamily: F.sans, fontSize: 15, fontWeight: 600, color: T.text, marginBottom: 20 }}>ATS Score History</div>
          {scoreData.length === 0 ? (
            <div style={{ height: 200, display: "flex", alignItems: "center", justifyContent: "center", color: T.t3, fontFamily: F.sans, fontSize: 13 }}>Upload a resume to see score history.</div>
          ) : (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={scoreData} margin={{ top: 5, right: 10, bottom: 0, left: -20 }}>
              <XAxis dataKey="version" tick={{ fill: T.t3, fontSize: 11, fontFamily: F.sans }} axisLine={false} tickLine={false} />
              <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={{ fill: T.t3, fontSize: 11, fontFamily: F.sans }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: "var(--pu-15-30-55-09)", border: "1px solid var(--pu-148-163-184-01)", borderRadius: 10, color: T.text, fontFamily: F.sans, fontSize: 12 }} />
              <Bar dataKey="score" radius={[6, 6, 0, 0]}>
                {scoreData.map((_, i) => (
                  <Cell key={`cell-${i}`} fill={i === scoreData.length - 1 ? T.red : "var(--pu-59-130-246-035)"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}
