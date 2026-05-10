import { useState, useEffect } from "react";
import { motion } from "motion/react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar, Cell } from "recharts";
import { TrendingUp, Eye, FileText, Award } from "lucide-react";
import * as api from "../../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  text: "#F2EEB3", t2: "rgba(242,238,179,0.65)", t3: "rgba(242,238,179,0.45)",
  border: "rgba(242,238,179,0.08)", glass: "rgba(64,18,18,0.55)",
  grad: "linear-gradient(135deg, #8C3A27, #A6372D, #401212)", red: "#A6372D", burnt: "#8C3A27",
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

const FALLBACK_METRICS: MetricCard[] = [
  { icon: TrendingUp, label: "Applications", value: "24", trend: "+8 this month", color: T.red },
  { icon: Eye, label: "Profile Views", value: "312", trend: "+42 this week", color: T.burnt },
  { icon: FileText, label: "Resume Downloads", value: "28", trend: "+6 this week", color: T.red },
  { icon: Award, label: "Top Match", value: "96%", trend: "Stripe SFE", color: T.burnt },
];
const FALLBACK_TIME: TimePoint[] = [
  { month: "Oct", apps: 4, interviews: 1, matches: 32 },
  { month: "Nov", apps: 7, interviews: 2, matches: 45 },
  { month: "Dec", apps: 5, interviews: 1, matches: 38 },
  { month: "Jan", apps: 11, interviews: 3, matches: 58 },
  { month: "Feb", apps: 18, interviews: 5, matches: 74 },
  { month: "Mar", apps: 24, interviews: 8, matches: 91 },
];
const FALLBACK_SCORES: ScorePoint[] = [
  { version: "v1", score: 62 },
  { version: "v2", score: 74 },
  { version: "v3", score: 87 },
];

const ICON_BY_LABEL: Record<string, typeof TrendingUp> = {
  applications: TrendingUp,
  "profile views": Eye,
  "resume downloads": FileText,
  "top match": Award,
};

export function AnalyticsPage() {
  const [metrics, setMetrics] = useState<MetricCard[]>(FALLBACK_METRICS);
  const [timeSeries, setTimeSeries] = useState<TimePoint[]>(FALLBACK_TIME);
  const [scoreData, setScoreData] = useState<ScorePoint[]>(FALLBACK_SCORES);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);

    api
      .getAnalyticsDashboard()
      .then((data) => {
        if (!active) return;

        if (Array.isArray(data.metrics) && data.metrics.length) {
          setMetrics(
            data.metrics.map((m, i) => {
              const key = (m.label || "").toLowerCase();
              const Icon = ICON_BY_LABEL[key] ?? FALLBACK_METRICS[i % FALLBACK_METRICS.length].icon;
              const color = i % 2 === 0 ? T.red : T.burnt;
              return { icon: Icon, label: m.label, value: m.value, trend: m.trend, color };
            }),
          );
        }

        const time = data.applications_over_time ?? data.time_series;
        if (Array.isArray(time) && time.length) setTimeSeries(time as TimePoint[]);

        const scores = data.ats_score_history ?? data.resume_scores;
        if (Array.isArray(scores) && scores.length) setScoreData(scores as ScorePoint[]);
      })
      .catch((err) => {
        // Fall through to defaults so the page still renders.
        console.warn("Analytics dashboard fetch failed; using defaults.", err);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  if (loading) {
    return <div style={{ color: T.text, fontFamily: F.sans, textAlign: "center", padding: 40 }}>Loading analytics...</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Metric cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}>
        {metrics.map((m, i) => (
          <motion.div key={m.label} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.08 }}
            style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 16, padding: "20px" }}>
            <div style={{ width: 36, height: 36, borderRadius: 10, background: "rgba(166,55,45,0.1)", border: "1px solid rgba(166,55,45,0.2)", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 14 }}>
              <m.icon size={16} color={m.color} />
            </div>
            <div style={{ fontFamily: F.sans, fontSize: 30, fontWeight: 800, color: m.color, lineHeight: 1, marginBottom: 4 }}>{m.value}</div>
            <div style={{ fontSize: 13, fontWeight: 500, color: T.text, fontFamily: F.sans, marginBottom: 2 }}>{m.label}</div>
            <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans }}>{m.trend}</div>
          </motion.div>
        ))}
      </div>

      {/* Charts */}
      <div style={{ display: "grid", gridTemplateColumns: "1.5fr 1fr", gap: 16 }}>
        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: 24 }}>
          <div style={{ fontFamily: F.sans, fontSize: 15, fontWeight: 600, color: T.text, marginBottom: 20 }}>Applications Over Time</div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={timeSeries} margin={{ top: 5, right: 10, bottom: 0, left: -20 }}>
              <defs>
                <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#A6372D" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#A6372D" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="month" tick={{ fill: T.t3, fontSize: 11, fontFamily: F.sans }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: T.t3, fontSize: 11, fontFamily: F.sans }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: "rgba(64,18,18,0.9)", border: "1px solid rgba(242,238,179,0.1)", borderRadius: 10, color: T.text, fontFamily: F.sans, fontSize: 12 }} />
              <Area type="monotone" dataKey="apps" stroke="#A6372D" strokeWidth={2} fill="url(#areaGrad)" />
              <Area type="monotone" dataKey="interviews" stroke="#8C3A27" strokeWidth={2} fill="none" strokeDasharray="4 2" />
            </AreaChart>
          </ResponsiveContainer>
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
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={scoreData} margin={{ top: 5, right: 10, bottom: 0, left: -20 }}>
              <XAxis dataKey="version" tick={{ fill: T.t3, fontSize: 11, fontFamily: F.sans }} axisLine={false} tickLine={false} />
              <YAxis domain={[50, 100]} tick={{ fill: T.t3, fontSize: 11, fontFamily: F.sans }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: "rgba(64,18,18,0.9)", border: "1px solid rgba(242,238,179,0.1)", borderRadius: 10, color: T.text, fontFamily: F.sans, fontSize: 12 }} />
              <Bar dataKey="score" radius={[6, 6, 0, 0]}>
                {scoreData.map((_, i) => (
                  <Cell key={`cell-${i}`} fill={i === scoreData.length - 1 ? T.red : "rgba(166,55,45,0.35)"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
