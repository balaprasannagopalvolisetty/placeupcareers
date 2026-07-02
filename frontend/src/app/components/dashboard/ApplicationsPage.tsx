import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { motion } from "motion/react";
import { Briefcase, ExternalLink, Search, RefreshCw, CheckCircle2, XCircle, Clock } from "lucide-react";
import * as api from "../../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  text: "#F1F5F9",
  t2: "rgba(226,232,240,0.72)",
  t3: "rgba(148,163,184,0.75)",
  border: "rgba(148,163,184,0.08)",
  glass: "rgba(15,30,55,0.55)",
  grad: "linear-gradient(135deg, #2563EB, #0EA5E9)",
  red: "#3B82F6",
};

type Row = api.UserApplicationRow;

const STATUS_PILLS: { label: string; value: string }[] = [
  { label: "All",           value: "all" },
  { label: "Applied",       value: "applied" },
  { label: "Heard back",    value: "heard_back" },
  { label: "Position open", value: "position_open" },
  { label: "Skipped",       value: "not_applied" },
];

function statusBadge(row: Row): { label: string; color: string; bg: string; border: string } {
  if (row.heard_back === true) {
    return { label: "Heard back", color: "#22c55e", bg: "rgba(34,197,94,0.12)", border: "rgba(34,197,94,0.3)" };
  }
  if (row.status === "applied") {
    return { label: "Applied", color: T.red, bg: "rgba(59,130,246,0.12)", border: "rgba(59,130,246,0.3)" };
  }
  if (row.status === "not_applied") {
    return { label: row.not_applied_reason || "Skipped", color: T.t3, bg: "rgba(148,163,184,0.04)", border: T.border };
  }
  return { label: row.status || "Tracked", color: T.t2, bg: "rgba(148,163,184,0.04)", border: T.border };
}

function formatDate(value?: string): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value.slice(0, 10);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function ApplicationsPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    api.getUserApplications()
      .then((data) => {
        if (!active) return;
        // Sort newest-first; backends may return either created_at or updated_at.
        const sorted = [...(Array.isArray(data) ? data : [])].sort((a, b) => {
          const ta = new Date(a.updated_at || a.created_at || 0).getTime();
          const tb = new Date(b.updated_at || b.created_at || 0).getTime();
          return tb - ta;
        });
        setRows(sorted);
      })
      .catch((err) => {
        if (!active) return;
        setError((err as Error)?.message || "Could not load your tracked applications.");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [reloadKey]);

  // Auto-refresh when JobDetailPage saves a new application.
  useEffect(() => {
    const handler = () => setReloadKey((v) => v + 1);
    window.addEventListener("placeup:application-changed", handler);
    return () => window.removeEventListener("placeup:application-changed", handler);
  }, []);

  const counts = useMemo(() => {
    const total = rows.length;
    const applied = rows.filter((r) => r.status === "applied").length;
    const heard = rows.filter((r) => r.heard_back === true).length;
    const skipped = rows.filter((r) => r.status === "not_applied").length;
    return { total, applied, heard, skipped };
  }, [rows]);

  // Per-day bucket of applied / heard_back over the last 14 days.
  // Used by the trend chart below — keeps the math simple by counting
  // each row at its created_at (or updated_at if created_at is absent).
  const trend = useMemo(() => {
    const days = 14;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const buckets: Array<{ date: Date; key: string; label: string; applied: number; heard: number }> = [];
    for (let i = days - 1; i >= 0; i -= 1) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      const key = d.toISOString().slice(0, 10);
      buckets.push({
        date: d,
        key,
        label: d.toLocaleDateString(undefined, { month: "short", day: "numeric" }),
        applied: 0,
        heard: 0,
      });
    }
    const byKey = new Map(buckets.map((b) => [b.key, b]));
    for (const r of rows) {
      const appliedTs = r.created_at || r.updated_at;
      if (r.status === "applied" && appliedTs) {
        const bucket = byKey.get(String(appliedTs).slice(0, 10));
        if (bucket) bucket.applied += 1;
      }
      const heardTs = r.updated_at || r.created_at;
      if (r.heard_back === true && heardTs) {
        const bucket = byKey.get(String(heardTs).slice(0, 10));
        if (bucket) bucket.heard += 1;
      }
    }
    const maxVal = Math.max(1, ...buckets.map((b) => Math.max(b.applied, b.heard)));
    return { buckets, maxVal };
  }, [rows]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => {
      if (filter === "applied" && r.status !== "applied") return false;
      if (filter === "heard_back" && r.heard_back !== true) return false;
      if (filter === "position_open" && r.position_open !== true) return false;
      if (filter === "not_applied" && r.status !== "not_applied") return false;
      if (!q) return true;
      const hay = `${r.title || ""} ${r.company || ""} ${r.location || ""}`.toLowerCase();
      return hay.includes(q);
    });
  }, [rows, search, filter]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18, width: "100%", minWidth: 0 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ fontFamily: F.sans, fontSize: 22, fontWeight: 700, color: T.text, marginBottom: 4 }}>
            Application Tracker
          </h2>
          <p style={{ fontSize: 13, color: T.t2, fontFamily: F.sans, marginTop: 0 }}>
            Every job you've applied to or skipped — and the follow-ups you logged.
          </p>
        </div>
        <button
          onClick={() => setReloadKey((v) => v + 1)}
          style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            padding: "8px 12px", borderRadius: 10,
            border: `1px solid ${T.border}`, background: "rgba(148,163,184,0.04)",
            color: T.t2, fontSize: 12, fontFamily: F.sans, cursor: "pointer",
          }}
        >
          <RefreshCw size={12} /> Refresh
        </button>
      </div>

      {/* Stat strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 10 }}>
        {[
          { label: "Tracked", value: counts.total, icon: Briefcase, color: T.t2 },
          { label: "Applied", value: counts.applied, icon: CheckCircle2, color: T.red },
          { label: "Heard back", value: counts.heard, icon: Clock, color: "#22c55e" },
          { label: "Skipped", value: counts.skipped, icon: XCircle, color: T.t3 },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label}
            style={{
              background: T.glass, backdropFilter: "blur(20px)",
              border: `1px solid ${T.border}`, borderRadius: 14,
              padding: "12px 14px", display: "flex", gap: 10, alignItems: "center",
            }}
          >
            <div style={{
              width: 32, height: 32, borderRadius: 9,
              background: "rgba(59,130,246,0.10)", border: "1px solid rgba(59,130,246,0.22)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <Icon size={14} color={color} />
            </div>
            <div>
              <div style={{ fontFamily: F.mono, fontWeight: 700, fontSize: 18, color: T.text, lineHeight: 1 }}>{value}</div>
              <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans, marginTop: 2 }}>{label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* 14-day applied vs heard-back trend chart.
         Pure inline SVG — no chart library needed. One bar per day,
         red = applied that day, green = heard back that day. */}
      <div style={{
        background: T.glass, backdropFilter: "blur(20px)",
        border: `1px solid ${T.border}`, borderRadius: 14, padding: "14px 18px",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: T.text, fontFamily: F.sans }}>14-day activity</div>
          <div style={{ display: "flex", gap: 14, fontSize: 11, color: T.t3, fontFamily: F.sans }}>
            <span><span style={{ display: "inline-block", width: 10, height: 10, background: T.red, borderRadius: 2, marginRight: 5, verticalAlign: "middle" }} /> Applied</span>
            <span><span style={{ display: "inline-block", width: 10, height: 10, background: "#22c55e", borderRadius: 2, marginRight: 5, verticalAlign: "middle" }} /> Heard back</span>
          </div>
        </div>
        <svg width="100%" height="120" viewBox={`0 0 ${trend.buckets.length * 28} 120`} preserveAspectRatio="none" role="img" aria-label="Daily applications trend">
          {trend.buckets.map((b, i) => {
            const x = i * 28;
            const appliedH = (b.applied / trend.maxVal) * 90;
            const heardH = (b.heard / trend.maxVal) * 90;
            return (
              <g key={b.key} transform={`translate(${x}, 0)`}>
                {/* Y axis lives in the parent — these are stacked vertical bars
                    anchored to the 100 baseline so growth pushes upward. */}
                <rect x={3} y={100 - appliedH} width={9} height={appliedH || 0} fill={T.red} rx={1.5} opacity={0.95} />
                <rect x={14} y={100 - heardH} width={9} height={heardH || 0} fill="#22c55e" rx={1.5} opacity={0.95} />
                {i % 2 === 0 && (
                  <text x={13} y={114} textAnchor="middle" fontSize="8" fill={T.t3} fontFamily="monospace">{b.label.split(" ")[1]}</text>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      {/* Search + filter chips */}
      <div style={{
        background: T.glass, backdropFilter: "blur(20px)",
        border: `1px solid ${T.border}`, borderRadius: 14,
        padding: "10px 14px", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap",
      }}>
        <div style={{
          display: "flex", alignItems: "center", gap: 8, flex: "1 1 220px",
          height: 36, padding: "0 12px", borderRadius: 8,
          border: `1px solid ${T.border}`, background: "rgba(148,163,184,0.04)",
        }}>
          <Search size={13} color={T.t3} />
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by company, title, or location…"
            style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: T.text, fontSize: 13, fontFamily: F.sans }} />
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {STATUS_PILLS.map((p) => (
            <button key={p.value} onClick={() => setFilter(p.value)}
              style={{
                height: 32, padding: "0 12px", borderRadius: 9999,
                border: `1px solid ${filter === p.value ? "transparent" : T.border}`,
                background: filter === p.value ? T.grad : "transparent",
                color: filter === p.value ? "#fff" : T.t2,
                fontSize: 12, cursor: "pointer", fontFamily: F.sans,
                fontWeight: filter === p.value ? 600 : 400,
              }}>{p.label}</button>
          ))}
        </div>
      </div>

      {error && (
        <div style={{ padding: "14px 16px", borderRadius: 12,
          background: "rgba(59,130,246,0.08)", border: "1px solid rgba(59,130,246,0.25)",
          color: T.text, fontFamily: F.sans, fontSize: 13 }}>
          {error}
        </div>
      )}

      {/* Rows */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {loading && rows.length === 0 && (
          <div style={{ textAlign: "center", padding: 40, color: T.t2, fontFamily: F.sans, background: T.glass, border: `1px solid ${T.border}`, borderRadius: 16 }}>
            Loading your applications…
          </div>
        )}
        {!loading && filtered.length === 0 && !error && (
          <div style={{ textAlign: "center", padding: 40, background: T.glass, border: `1px solid ${T.border}`, borderRadius: 16, color: T.t2, fontFamily: F.sans }}>
            <div style={{ fontSize: 14, marginBottom: 6 }}>No tracked applications yet.</div>
            <div style={{ fontSize: 12, color: T.t3, marginBottom: 12 }}>
              Click <strong>Apply on Company Website</strong> on any job and we'll log it here for you.
            </div>
            <Link to="/dashboard/jobs" style={{ color: T.red, fontWeight: 600 }}>Browse jobs →</Link>
          </div>
        )}
        {filtered.map((row, i) => {
          const badge = statusBadge(row);
          return (
            <motion.div key={`${row.job_id}-${row.created_at || i}`}
              initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(0.02 * i, 0.3) }}
              style={{
                background: "linear-gradient(135deg, rgba(15,30,55,0.62), rgba(25,18,32,0.72))",
                backdropFilter: "blur(20px)", border: `1px solid ${T.border}`,
                borderRadius: 14, padding: 14,
                display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: 12, alignItems: "center",
              }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4, flexWrap: "wrap" }}>
                  <span style={{
                    fontSize: 10, fontWeight: 700, padding: "3px 8px", borderRadius: 999,
                    background: badge.bg, color: badge.color, border: `1px solid ${badge.border}`,
                    fontFamily: F.sans, letterSpacing: "0.04em", textTransform: "uppercase",
                  }}>{badge.label}</span>
                  {typeof row.match_score === "number" && row.match_score > 0 && (
                    <span style={{ fontSize: 10, color: T.t3, fontFamily: F.mono }}>{row.match_score}% match</span>
                  )}
                  <span style={{ fontSize: 10, color: T.t3, fontFamily: F.sans }}>{formatDate(row.updated_at || row.created_at)}</span>
                </div>
                <Link to={`/dashboard/jobs/${row.job_id}`}
                  style={{ fontSize: 15, fontWeight: 700, color: T.text, fontFamily: F.sans, textDecoration: "none" }}>
                  {row.title || "Untitled role"}
                </Link>
                <div style={{ fontSize: 12, color: T.t2, fontFamily: F.sans, marginTop: 2 }}>
                  {row.company || "Unknown company"}{row.location ? ` · ${row.location}` : ""}
                </div>
                {row.notes && (
                  <div style={{ fontSize: 12, color: T.t3, fontFamily: F.sans, marginTop: 6, lineHeight: 1.5 }}>
                    Note: {row.notes}
                  </div>
                )}
                {row.salary_offered && (
                  <div style={{ fontSize: 12, color: T.t3, fontFamily: F.sans, marginTop: 4 }}>
                    Salary discussed: {row.salary_offered}
                  </div>
                )}
              </div>
              {row.job_url && (
                <a href={row.job_url} target="_blank" rel="noopener noreferrer"
                  style={{
                    display: "inline-flex", alignItems: "center", gap: 5,
                    padding: "8px 12px", borderRadius: 9,
                    border: `1px solid ${T.border}`, color: T.t2, fontSize: 12,
                    fontFamily: F.sans, textDecoration: "none",
                  }}>
                  Posting <ExternalLink size={11} />
                </a>
              )}
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

export default ApplicationsPage;
