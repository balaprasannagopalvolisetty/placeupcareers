import { useState, useEffect } from "react";
import { motion } from "motion/react";
import { Bell, BellOff, Trash2, MapPin, DollarSign, Check, Sparkles, TrendingUp } from "lucide-react";
import { Link } from "react-router";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { LoadingLogo } from "../LoadingLogo";
import * as api from "../../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif" };
const T = {
  text: "#F1F5F9", t2: "rgba(226,232,240,0.72)", t3: "rgba(148,163,184,0.75)",
  border: "rgba(148,163,184,0.08)", glass: "rgba(15,30,55,0.55)",
  grad: "linear-gradient(135deg, #2563EB, #0EA5E9)", red: "#3B82F6",
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

export function AlertsPage() {
  const [alerts, setAlerts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [enabled, setEnabled] = useState({ email: true, daily: true, weekly: false });
  // Count of recently-added positions matching the roles the user picked at
  // signup. Reuses the existing personalized jobs feed (no new backend rule).
  const [recentCount, setRecentCount] = useState<number | null>(null);
  // Per-target-role "new positions" digest + personalized top picks.
  const [digest, setDigest] = useState<api.AlertsDigest | null>(null);
  const [topPicks, setTopPicks] = useState<any[]>([]);
  // Daily "positions added" series for the interactive chart.
  const [addedSeries, setAddedSeries] = useState<api.AlertsAddedSeries | null>(null);
  const [chartScope, setChartScope] = useState<"targets" | "all">("targets");

  useEffect(() => {
    let active = true;
    api.getAlertsAddedSeries({ days: 14, scope: chartScope })
      .then((d) => { if (active) setAddedSeries(d); })
      .catch(() => { if (active) setAddedSeries(null); });
    return () => { active = false; };
  }, [chartScope]);

  useEffect(() => {
    let active = true;
    setLoading(true);

    api.getAlertsDigest()
      .then((d) => { if (active) setDigest(d); })
      .catch(() => { if (active) setDigest(null); });

    api.getTopMatches({
      limit: 20,
      time_filter: "8h",
      fresh_basis: "added",
      min_score: 85,
      tz_offset: new Date().getTimezoneOffset(),
    })
      .then((resp: any) => {
        if (!active) return;
        const items = Array.isArray(resp?.jobs) ? resp.jobs : Array.isArray(resp) ? resp : [];
        setTopPicks(items.slice(0, 20));
        setRecentCount(typeof resp?.total === "number" ? resp.total : items.length);
      })
      .catch(() => {
        if (active) {
          setTopPicks([]);
          setRecentCount(null);
        }
      });

    Promise.all([
      withTimeout(api.getAlerts(), 8000, []).then(data => {
        if (active) setAlerts(Array.isArray(data) ? data : data.alerts || []);
      }),
      withTimeout(api.getAlertSettings(), 8000, { email_alerts: true, daily_digest: true, weekly_report: false }).then(data => {
        if (active && data) {
          setEnabled({
            email: data.email_alerts !== false,
            daily: data.daily_digest !== false,
            weekly: (data as any).weekly_report ?? (data as any).weekly_digest ?? false,
          });
        }
      }),
    ]).finally(() => {
      if (active) setLoading(false);
    });

    return () => { active = false; };
  }, []);

  const displayAlerts = Array.isArray(alerts) ? alerts : [];
  const unreadCount = displayAlerts.filter((alert) => alert.unread).length;

  const handleToggleSetting = async (key: 'email' | 'daily' | 'weekly', value: boolean) => {
    setEnabled(e => ({ ...e, [key]: value }));
    try {
      await api.updateAlertSettings({
        email_alerts: key === 'email' ? value : enabled.email,
        daily_digest: key === 'daily' ? value : enabled.daily,
        weekly_report: key === 'weekly' ? value : enabled.weekly,
      });
    } catch (err) {
      console.error('Failed to update alert settings:', err);
      setEnabled(e => ({ ...e, [key]: !value }));
    }
  };

  const handleMarkRead = async (alertId: number | string) => {
    try {
      await api.markAlertRead(String(alertId));
      setAlerts(a => a.map(x => x.id === alertId ? { ...x, unread: false } : x));
    } catch (err) {
      console.error('Failed to mark alert read:', err);
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await api.markAllAlertsRead();
      setAlerts(a => a.map(x => ({ ...x, unread: false })));
    } catch (err) {
      console.error('Failed to mark all alerts read:', err);
    }
  };

  const handleDeleteAlert = async (alertId: number | string) => {
    try {
      await api.deleteAlert(String(alertId));
      setAlerts(a => a.filter(x => x.id !== alertId));
    } catch (err) {
      console.error('Failed to delete alert:', err);
    }
  };

  if (loading) {
    return <LoadingLogo label="Loading alerts" />;
  }

  const chartData = (addedSeries?.series || []).map((p) => ({
    label: new Date(p.date + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" }),
    date: p.date,
    count: p.count,
  }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Interactive "positions added" chart */}
      <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: "18px 22px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <TrendingUp size={15} color={T.red} />
            <span style={{ fontFamily: F.sans, fontSize: 15, fontWeight: 600, color: T.text }}>Positions added</span>
            <span style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>last 14 days</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
            <div style={{ display: "flex", gap: 16 }}>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 18, fontWeight: 800, color: T.text, fontFamily: F.sans, lineHeight: 1 }}>{(addedSeries?.total_added ?? 0).toLocaleString()}</div>
                <div style={{ fontSize: 10.5, color: T.t3, fontFamily: F.sans }}>total added</div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 18, fontWeight: 800, color: T.red, fontFamily: F.sans, lineHeight: 1 }}>{(addedSeries?.peak_day ?? 0).toLocaleString()}</div>
                <div style={{ fontSize: 10.5, color: T.t3, fontFamily: F.sans }}>busiest day</div>
              </div>
            </div>
            <div style={{ display: "flex", borderRadius: 9, overflow: "hidden", border: `1px solid ${T.border}` }}>
              {([["targets", "My roles"], ["all", "All"]] as const).map(([value, label]) => (
                <button key={value} onClick={() => setChartScope(value)}
                  style={{ padding: "6px 12px", fontSize: 11.5, fontWeight: 700, fontFamily: F.sans, cursor: "pointer", border: "none",
                    background: chartScope === value ? "rgba(59,130,246,0.16)" : "transparent",
                    color: chartScope === value ? T.red : T.t3 }}>
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div style={{ height: 200 }}>
          {chartData.length === 0 ? (
            <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: T.t3, fontFamily: F.sans, fontSize: 13 }}>
              No new positions recorded in this window yet.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 6, right: 8, bottom: 0, left: -22 }}>
                <defs>
                  <linearGradient id="addedFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3B82F6" stopOpacity={0.55} />
                    <stop offset="100%" stopColor="#3B82F6" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.06)" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: "rgba(148,163,184,0.75)", fontSize: 11, fontFamily: F.sans }} tickLine={false} axisLine={false} minTickGap={18} />
                <YAxis allowDecimals={false} tick={{ fill: "rgba(148,163,184,0.75)", fontSize: 11, fontFamily: F.sans }} tickLine={false} axisLine={false} width={42} />
                <Tooltip
                  cursor={{ stroke: "rgba(59,130,246,0.4)", strokeWidth: 1 }}
                  contentStyle={{ background: "rgba(8,14,32,0.96)", border: `1px solid ${T.border}`, borderRadius: 12, fontFamily: F.sans, color: T.text }}
                  labelStyle={{ color: T.t2, fontSize: 12 }}
                  itemStyle={{ color: T.red, fontSize: 13, fontWeight: 700 }}
                  formatter={(value: number) => [`${value} new`, "Positions"]}
                />
                <Area type="monotone" dataKey="count" stroke="#3B82F6" strokeWidth={2} fill="url(#addedFill)" activeDot={{ r: 4, fill: "#3B82F6" }} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* New-positions digest for the user's target roles */}
      {digest?.has_target_roles && (
        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: "18px 22px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
            <TrendingUp size={15} color={T.red} />
            <span style={{ fontFamily: F.sans, fontSize: 15, fontWeight: 600, color: T.text }}>New positions for your target roles</span>
            <span style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>
              {digest.total_new_24h} in the last 24h · {digest.total_new_7d} this week
            </span>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {digest.target_roles.map((r) => (
              <Link key={r.role} to={`/dashboard/jobs?role=${encodeURIComponent(r.role)}`}
                style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "8px 14px", borderRadius: 10, background: "rgba(59,130,246,0.08)", border: "1px solid rgba(59,130,246,0.2)", textDecoration: "none" }}>
                <span style={{ fontSize: 12.5, fontWeight: 600, color: T.text, fontFamily: F.sans }}>{r.role}</span>
                <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 9999, background: r.new_24h > 0 ? T.grad : "rgba(148,163,184,0.08)", color: r.new_24h > 0 ? "#fff" : T.t3, fontFamily: F.sans }}>
                  +{r.new_24h} today
                </span>
                <span style={{ fontSize: 11, color: T.t3, fontFamily: F.sans }}>{r.new_7d} this week</span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Personalized top 85+ picks added in the last 8 hours */}
      <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, padding: "18px 22px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Sparkles size={15} color={T.red} />
            <span style={{ fontFamily: F.sans, fontSize: 15, fontWeight: 600, color: T.text }}>Top 85+ matches added in the last 8 hours</span>
          </div>
          <span style={{ fontSize: 11.5, color: T.t3, fontFamily: F.sans }}>
            {recentCount == null ? "Fresh database window" : `${Math.min(topPicks.length, 20)} of ${recentCount} positions`}
          </span>
        </div>
        {topPicks.length === 0 ? (
          <div style={{ padding: "28px 12px", textAlign: "center", color: T.t3, fontFamily: F.sans, fontSize: 13 }}>
            No 85+ ATS matches were added in the last 8 hours yet. New database entries will appear here automatically.
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: 10 }}>
            {topPicks.map((job: any) => (
              <Link key={String(job.id)} to={`/dashboard/jobs/${encodeURIComponent(String(job.id))}`}
                style={{ display: "block", padding: "12px 14px", borderRadius: 12, background: "rgba(148,163,184,0.03)", border: `1px solid ${T.border}`, textDecoration: "none", transition: "border-color 0.2s" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: T.text, fontFamily: F.sans, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{job.title}</span>
                  {typeof job.match_score === "number" && (
                    <span style={{ fontSize: 12, fontWeight: 700, color: T.red, fontFamily: F.sans, flexShrink: 0 }}>{job.match_score}%</span>
                  )}
                </div>
                <div style={{ fontSize: 11.5, color: T.t2, fontFamily: F.sans, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {job.company}{job.location ? ` · ${job.location}` : ""}
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Settings */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14 }}>
        {[
          { key: "email", label: "Email Alerts", desc: "Instant match notifications" },
          { key: "daily", label: "Daily Digest", desc: "Top 10 matches at 9AM EST" },
          { key: "weekly", label: "Weekly Report", desc: "Summary every Monday" },
        ].map((item) => (
          <div key={item.key} style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 16, padding: "18px 20px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, color: T.text, fontFamily: F.sans, marginBottom: 2 }}>{item.label}</div>
              <div style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>{item.desc}</div>
            </div>
            <button
              onClick={() => handleToggleSetting(item.key as 'email' | 'daily' | 'weekly', !enabled[item.key as keyof typeof enabled])}
              style={{ width: 44, height: 24, borderRadius: 9999, border: "none", background: enabled[item.key as keyof typeof enabled] ? T.grad : "rgba(148,163,184,0.1)", cursor: "pointer", position: "relative", transition: "background 0.25s", flexShrink: 0 }}
            >
              <div style={{ position: "absolute", top: 2, left: enabled[item.key as keyof typeof enabled] ? 22 : 2, width: 20, height: 20, borderRadius: "50%", background: "#fff", transition: "left 0.25s", boxShadow: "0 1px 4px rgba(0,0,0,0.3)" }} />
            </button>
          </div>
        ))}
      </div>

      {/* Alert feed */}
      <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, overflow: "hidden" }}>
        <div style={{ padding: "18px 24px", borderBottom: `1px solid ${T.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ fontFamily: F.sans, fontSize: 15, fontWeight: 600, color: T.text }}>
            Recent Alerts
            {recentCount != null && (
              <span style={{ fontSize: 12, color: T.red, fontWeight: 700, marginLeft: 6 }}>
                {recentCount} fresh 85+ {recentCount === 1 ? "position" : "positions"} in last 8h
              </span>
            )}
          </div>
          <button
            onClick={handleMarkAllRead}
            disabled={unreadCount === 0}
            style={{ fontSize: 12, color: unreadCount === 0 ? T.t3 : T.red, fontFamily: F.sans, background: "none", border: "none", cursor: unreadCount === 0 ? "default" : "pointer", fontWeight: 600 }}
          >
            {unreadCount === 0 ? "All caught up" : "Mark all read"}
          </button>
        </div>
        {displayAlerts.length === 0 ? (
          <div style={{ padding: "40px", textAlign: "center", color: T.t3, display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
            <BellOff size={22} color={T.t3} />
            <span>No alerts yet. Your job matches will appear here.</span>
          </div>
        ) : (
          displayAlerts.map((alert, i) => (
            <motion.div key={alert.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.06 }}
              style={{ display: "flex", alignItems: "center", gap: 14, padding: "16px 24px", borderBottom: i < displayAlerts.length - 1 ? `1px solid ${T.border}` : "none", background: alert.unread ? "rgba(59,130,246,0.04)" : "transparent", cursor: "pointer" }}
              onClick={() => alert.unread && handleMarkRead(alert.id)}>
              <div style={{ width: 40, height: 40, borderRadius: "50%", background: alert.match_score ? T.grad : "rgba(148,163,184,0.08)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                {alert.match_score ? <Bell size={16} color="#fff" /> : <Check size={16} color={T.red} />}
              </div>
              {alert.unread && <div style={{ width: 6, height: 6, borderRadius: "50%", background: T.red, boxShadow: `0 0 6px ${T.red}`, flexShrink: 0 }} />}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: T.text, fontFamily: F.sans, marginBottom: 2 }}>{alert.title || alert.message}</div>
                <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                  {alert.company && (
                    <>
                      <span style={{ fontSize: 12, color: T.t2, fontFamily: F.sans }}>{alert.company}</span>
                      {alert.location && <span style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 12, color: T.t3, fontFamily: F.sans }}><MapPin size={10} />{alert.location}</span>}
                      {alert.salary && <span style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 12, color: T.t3, fontFamily: F.sans }}><DollarSign size={10} />{alert.salary}</span>}
                    </>
                  )}
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
                {alert.match_score && <span style={{ fontSize: 13, fontWeight: 700, color: T.red, fontFamily: F.sans }}>{alert.match_score}%</span>}
                <span style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>{alert.created_at ? new Date(alert.created_at).toLocaleDateString() : 'Recently'}</span>
                <button onClick={(e) => { e.stopPropagation(); handleDeleteAlert(alert.id); }} style={{ background: "none", border: "none", cursor: "pointer", color: T.t3 }}>
                  <Trash2 size={14} />
                </button>
              </div>
            </motion.div>
          ))
   
     )}
      </div>
    </div>
  );
}
