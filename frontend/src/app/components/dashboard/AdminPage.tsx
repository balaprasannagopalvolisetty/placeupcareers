import { useEffect, useMemo, useState } from "react";
import {
  Activity, AlertTriangle, BarChart3, Briefcase, Globe, Loader2, MessageSquare,
  RefreshCw, Search, Shield, Star, Users, X, KeyRound, LogOut, ChevronRight,
} from "lucide-react";
import {
  ResponsiveContainer, AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, CartesianGrid,
} from "recharts";
import * as api from "../../lib/api";

// ─── Dark admin theme ────────────────────────────────────────────────────────
const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  bg: "#0B1220",
  panel: "rgba(17,28,49,0.7)",
  panel2: "rgba(15,30,55,0.5)",
  border: "rgba(148,163,184,0.14)",
  text: "#F1F5F9",
  t2: "rgba(226,232,240,0.72)",
  t3: "rgba(148,163,184,0.7)",
  accent: "#3B82F6",
  green: "#22C55E",
  amber: "#F59E0B",
  red: "#EF4444",
  violet: "#8B5CF6",
  cyan: "#06B6D4",
};
const CHART_COLORS = [T.accent, T.violet, T.cyan, T.green, T.amber, "#EC4899", "#14B8A6", "#F97316"];

function Panel({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 16, padding: 18, ...style }}>
      {children}
    </div>
  );
}

function StatCard({ icon, label, value, sub, tone = T.accent }: { icon: React.ReactNode; label: string; value: React.ReactNode; sub?: string; tone?: string }) {
  return (
    <Panel style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ width: 34, height: 34, borderRadius: 10, background: `${tone}22`, display: "inline-flex", alignItems: "center", justifyContent: "center", color: tone }}>{icon}</span>
        <span style={{ fontSize: 12, color: T.t3, fontFamily: F.sans, fontWeight: 600 }}>{label}</span>
      </div>
      <div style={{ fontSize: 26, fontWeight: 850, color: T.text, fontFamily: F.sans, letterSpacing: "-0.02em" }}>{value}</div>
      {sub && <div style={{ fontSize: 11.5, color: T.t3, fontFamily: F.sans }}>{sub}</div>}
    </Panel>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <div style={{ fontSize: 13, fontWeight: 700, color: T.text, fontFamily: F.sans, marginBottom: 12 }}>{children}</div>;
}

const tooltipStyle = { background: "#0F1B33", border: `1px solid ${T.border}`, borderRadius: 10, color: T.text, fontFamily: F.sans, fontSize: 12 };

function fmtDate(iso?: string) {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
function fmtDateTime(iso?: string) {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}
function str(v: unknown): string { return v == null ? "" : String(v); }

type Tab = "overview" | "users" | "activity" | "positions" | "feedback";

// ─── Reusable chart blocks ───────────────────────────────────────────────────
function TrendArea({ data, color, label }: { data: api.DayCount[]; color: string; label: string }) {
  return (
    <Panel>
      <SectionTitle>{label}</SectionTitle>
      <div style={{ height: 200 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
            <defs>
              <linearGradient id={`g-${label}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.45} />
                <stop offset="100%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.1)" vertical={false} />
            <XAxis dataKey="date" tick={{ fill: T.t3, fontSize: 10 }} tickFormatter={(d) => String(d).slice(5)} minTickGap={24} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: T.t3, fontSize: 10 }} allowDecimals={false} axisLine={false} tickLine={false} width={34} />
            <Tooltip contentStyle={tooltipStyle} labelStyle={{ color: T.t2 }} />
            <Area type="monotone" dataKey="count" stroke={color} strokeWidth={2} fill={`url(#g-${label})`} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

function BarBlock({ data, label }: { data: api.LabelCount[]; label: string }) {
  return (
    <Panel>
      <SectionTitle>{label}</SectionTitle>
      {data.length === 0 ? (
        <div style={{ color: T.t3, fontSize: 12, fontFamily: F.sans, padding: "24px 0", textAlign: "center" }}>No data yet.</div>
      ) : (
        <div style={{ height: Math.max(160, data.length * 34) }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ top: 0, right: 12, left: 8, bottom: 0 }}>
              <XAxis type="number" hide allowDecimals={false} />
              <YAxis type="category" dataKey="label" tick={{ fill: T.t2, fontSize: 11 }} width={130} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(148,163,184,0.08)" }} />
              <Bar dataKey="count" radius={[0, 6, 6, 0]} barSize={16}>
                {data.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Panel>
  );
}

// ─── Main ────────────────────────────────────────────────────────────────────
export function AdminPage() {
  const [tab, setTab] = useState<Tab>("overview");
  const [metrics, setMetrics] = useState<api.AdminMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const reload = () => {
    setLoading(true);
    api.getAdminMetrics(30)
      .then((m) => { setMetrics(m); setErr(""); })
      .catch((e) => setErr((e as Error).message || "Could not load metrics."))
      .finally(() => setLoading(false));
  };
  useEffect(reload, []);

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: "overview", label: "Overview", icon: <BarChart3 size={15} /> },
    { id: "users", label: "Users", icon: <Users size={15} /> },
    { id: "activity", label: "Activity", icon: <Activity size={15} /> },
    { id: "positions", label: "Positions", icon: <Briefcase size={15} /> },
    { id: "feedback", label: "Feedback", icon: <MessageSquare size={15} /> },
  ];

  return (
    <div style={{ fontFamily: F.sans, color: T.text }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18, flexWrap: "wrap", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ width: 40, height: 40, borderRadius: 12, background: `${T.accent}22`, display: "inline-flex", alignItems: "center", justifyContent: "center", color: T.accent }}><Shield size={20} /></span>
          <div>
            <div style={{ fontSize: 20, fontWeight: 850, letterSpacing: "-0.02em" }}>Admin Portal</div>
            <div style={{ fontSize: 12, color: T.t3 }}>Live view of users, activity, positions & feedback</div>
          </div>
        </div>
        <button onClick={reload} style={{ display: "inline-flex", alignItems: "center", gap: 7, height: 38, padding: "0 14px", borderRadius: 10, border: `1px solid ${T.border}`, background: T.panel, color: T.t2, fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: F.sans }}>
          {loading ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />} Refresh
        </button>
      </div>

      {err && (
        <Panel style={{ borderColor: "rgba(239,68,68,0.35)", background: "rgba(239,68,68,0.08)", marginBottom: 16, display: "flex", gap: 10, alignItems: "center" }}>
          <AlertTriangle size={16} color={T.red} /> <span style={{ fontSize: 13, color: "#FCA5A5" }}>{err}</span>
        </Panel>
      )}

      {/* KPI row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12, marginBottom: 18 }}>
        <StatCard icon={<Users size={17} />} label="Total users" value={metrics?.totals.users ?? "—"} sub={`${metrics?.totals.signups_7d ?? 0} in last 7 days`} tone={T.accent} />
        <StatCard icon={<Briefcase size={17} />} label="Events logged" value={metrics?.totals.events ?? "—"} tone={T.violet} />
        <StatCard icon={<Star size={17} />} label="Avg rating" value={metrics?.totals.avg_rating ? `${metrics.totals.avg_rating}★` : "—"} sub={`${metrics?.totals.feedback ?? 0} responses`} tone={T.amber} />
        <StatCard icon={<AlertTriangle size={17} />} label="Errors logged" value={metrics?.totals.errors ?? "—"} tone={T.red} />
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 6, marginBottom: 18, flexWrap: "wrap" }}>
        {tabs.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            display: "inline-flex", alignItems: "center", gap: 7, height: 38, padding: "0 15px", borderRadius: 10,
            border: `1px solid ${tab === t.id ? T.accent : T.border}`, background: tab === t.id ? `${T.accent}22` : "transparent",
            color: tab === t.id ? T.text : T.t3, fontSize: 13, fontWeight: 700, cursor: "pointer", fontFamily: F.sans,
          }}>{t.icon} {t.label}</button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab metrics={metrics} />}
      {tab === "users" && <UsersTab />}
      {tab === "activity" && <ActivityTab />}
      {tab === "positions" && <PositionsTab />}
      {tab === "feedback" && <FeedbackTab />}

      <style>{`.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}

// ─── Overview ────────────────────────────────────────────────────────────────
function OverviewTab({ metrics }: { metrics: api.AdminMetrics | null }) {
  if (!metrics) return <Panel><div style={{ color: T.t3, fontSize: 13, padding: 20, textAlign: "center" }}>Loading charts…</div></Panel>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 14 }}>
        <TrendArea data={metrics.signups_series} color={T.accent} label="New signups (per day)" />
        <TrendArea data={metrics.activity_series} color={T.violet} label="Activity volume (per day)" />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14 }}>
        <BarBlock data={metrics.by_plan} label="Users by plan" />
        <BarBlock data={metrics.by_visa} label="Users by visa status" />
        <BarBlock data={metrics.by_country} label="Users by country" />
        <BarBlock data={metrics.by_experience} label="Users by experience" />
      </div>
    </div>
  );
}

// ─── Users ───────────────────────────────────────────────────────────────────
function UsersTab() {
  const [users, setUsers] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    api.getAdminUsers(500).then((r: any) => setUsers(r.users || r || [])).catch(() => setUsers([])).finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return users;
    return users.filter((u) => `${str(u.first_name)} ${str(u.last_name)} ${str(u.email)} ${str(u.country)}`.toLowerCase().includes(s));
  }, [users, q]);

  return (
    <Panel>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
        <SectionTitle>All users ({filtered.length})</SectionTitle>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8, height: 38, padding: "0 12px", borderRadius: 10, background: T.panel2, border: `1px solid ${T.border}`, minWidth: 220 }}>
          <Search size={14} color={T.t3} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, email, country…" style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: T.text, fontSize: 13, fontFamily: F.sans }} />
        </div>
      </div>
      {loading ? (
        <div style={{ color: T.t3, fontSize: 13, padding: 20, textAlign: "center" }}>Loading users…</div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
            <thead>
              <tr style={{ color: T.t3, textAlign: "left" }}>
                {["Name", "Email", "Plan", "Visa", "Country", "Joined", ""].map((h) => (
                  <th key={h} style={{ padding: "8px 10px", fontWeight: 600, borderBottom: `1px solid ${T.border}`, whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((u, i) => (
                <tr key={str(u.id) || i} onClick={() => setSelected(str(u.id))} style={{ cursor: "pointer", background: i % 2 ? "rgba(148,163,184,0.03)" : "transparent" }}>
                  <td style={{ padding: "9px 10px", color: T.text, fontWeight: 600, whiteSpace: "nowrap" }}>{str(u.first_name)} {str(u.last_name)}</td>
                  <td style={{ padding: "9px 10px", color: T.t2 }}>{str(u.email)}</td>
                  <td style={{ padding: "9px 10px", color: T.t2 }}>{str(u.plan) || "—"}</td>
                  <td style={{ padding: "9px 10px", color: T.t2 }}>{str(u.visa_status) || "—"}</td>
                  <td style={{ padding: "9px 10px", color: T.t2 }}>{str(u.country) || "—"}</td>
                  <td style={{ padding: "9px 10px", color: T.t3, whiteSpace: "nowrap" }}>{fmtDate(str(u.created_at))}</td>
                  <td style={{ padding: "9px 10px", color: T.t3 }}><ChevronRight size={14} /></td>
                </tr>
              ))}
              {filtered.length === 0 && <tr><td colSpan={7} style={{ padding: 20, textAlign: "center", color: T.t3 }}>No users match your search.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {selected && <UserDrawer userId={selected} onClose={() => setSelected(null)} />}
    </Panel>
  );
}

function UserDrawer({ userId, onClose }: { userId: string; onClose: () => void }) {
  const [detail, setDetail] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    setLoading(true);
    api.getAdminUserDetail(userId).then(setDetail).catch(() => setMsg("Could not load user.")).finally(() => setLoading(false));
  }, [userId]);

  const user = detail?.user || {};
  const events: any[] = detail?.events || [];
  const resumes: any[] = detail?.resumes || [];
  const prefs = detail?.preferences || {};

  const doReset = async () => { try { await api.adminTriggerPasswordReset(userId); setMsg("Password-reset email sent."); } catch (e) { setMsg((e as Error).message); } };
  const doRevoke = async () => { try { const r = await api.adminRevokeSessions(userId); setMsg(`Revoked ${r.revoked} session(s).`); } catch (e) { setMsg((e as Error).message); } };

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(2,6,20,0.6)", zIndex: 70, display: "flex", justifyContent: "flex-end" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: 460, maxWidth: "100vw", height: "100%", overflowY: "auto", background: "#0D1729", borderLeft: `1px solid ${T.border}`, padding: 22, boxSizing: "border-box" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <div style={{ fontSize: 16, fontWeight: 800, color: T.text }}>User details</div>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: T.t3 }}><X size={18} /></button>
        </div>
        {loading ? <div style={{ color: T.t3, fontSize: 13 }}>Loading…</div> : (
          <>
            <div style={{ fontSize: 18, fontWeight: 800, color: T.text }}>{str(user.first_name)} {str(user.last_name)}</div>
            <div style={{ fontSize: 13, color: T.t2, marginBottom: 14 }}>{str(user.email)}</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 16 }}>
              {[["Plan", str(user.plan)], ["Visa", str(user.visa_status)], ["Country", str(user.country)], ["Experience", str(user.experience_years)], ["Phone", str(user.phone)], ["Joined", fmtDate(str(user.created_at))]].map(([k, v]) => (
                <div key={k} style={{ background: T.panel2, border: `1px solid ${T.border}`, borderRadius: 9, padding: "8px 10px" }}>
                  <div style={{ fontSize: 10, color: T.t3, textTransform: "uppercase", letterSpacing: "0.06em" }}>{k}</div>
                  <div style={{ fontSize: 13, color: T.text, fontWeight: 600 }}>{v || "—"}</div>
                </div>
              ))}
            </div>

            {Array.isArray(prefs.target_roles) && prefs.target_roles.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, color: T.t3, marginBottom: 6, fontWeight: 600 }}>Target positions</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {prefs.target_roles.map((r: string) => <span key={r} style={{ fontSize: 11, padding: "4px 8px", borderRadius: 999, background: `${T.accent}18`, color: "#93C5FD", border: `1px solid ${T.accent}33` }}>{r}</span>)}
                </div>
              </div>
            )}

            <div style={{ fontSize: 12, color: T.t3, marginBottom: 6, fontWeight: 600 }}>Resumes ({resumes.length})</div>
            <div style={{ marginBottom: 16 }}>
              {resumes.length === 0 ? <div style={{ fontSize: 12, color: T.t3 }}>None uploaded.</div> :
                resumes.map((r: any, i: number) => <div key={i} style={{ fontSize: 12.5, color: T.t2, padding: "4px 0" }}>• {str(r.name) || str(r.filename) || "Resume"} <span style={{ color: T.t3 }}>({fmtDate(str(r.created_at))})</span></div>)}
            </div>

            <div style={{ fontSize: 12, color: T.t3, marginBottom: 6, fontWeight: 600 }}>Recent activity</div>
            <div style={{ marginBottom: 18, display: "flex", flexDirection: "column", gap: 4, maxHeight: 220, overflowY: "auto" }}>
              {events.length === 0 ? <div style={{ fontSize: 12, color: T.t3 }}>No activity.</div> :
                events.slice(0, 30).map((e: any, i: number) => (
                  <div key={i} style={{ fontSize: 12, color: T.t2, display: "flex", justifyContent: "space-between", gap: 8, padding: "5px 0", borderBottom: `1px solid ${T.border}` }}>
                    <span>{str(e.label) || str(e.kind)}</span>
                    <span style={{ color: T.t3, whiteSpace: "nowrap" }}>{fmtDateTime(str(e.created_at))}</span>
                  </div>
                ))}
            </div>

            {msg && <div style={{ fontSize: 12.5, color: "#93C5FD", marginBottom: 10 }}>{msg}</div>}
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={doReset} style={{ flex: 1, height: 40, borderRadius: 10, border: `1px solid ${T.border}`, background: T.panel, color: T.t2, fontSize: 12.5, fontWeight: 600, cursor: "pointer", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6, fontFamily: F.sans }}><KeyRound size={14} /> Reset password</button>
              <button onClick={doRevoke} style={{ flex: 1, height: 40, borderRadius: 10, border: `1px solid rgba(239,68,68,0.35)`, background: "rgba(239,68,68,0.1)", color: "#FCA5A5", fontSize: 12.5, fontWeight: 600, cursor: "pointer", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6, fontFamily: F.sans }}><LogOut size={14} /> Revoke sessions</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ─── Activity ────────────────────────────────────────────────────────────────
function ActivityTab() {
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [kind, setKind] = useState("");

  useEffect(() => {
    setLoading(true);
    api.getAdminEvents({ limit: 200, kind: kind || undefined }).then((r: any) => setEvents(r.events || [])).catch(() => setEvents([])).finally(() => setLoading(false));
  }, [kind]);

  const kinds = useMemo(() => Array.from(new Set(events.map((e) => str(e.kind)).filter(Boolean))), [events]);
  const levelColor = (l: string) => l === "error" ? T.red : l === "warning" ? T.amber : T.accent;

  return (
    <Panel>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
        <SectionTitle>Activity & audit log</SectionTitle>
        <select value={kind} onChange={(e) => setKind(e.target.value)} style={{ marginLeft: "auto", height: 36, padding: "0 10px", borderRadius: 9, background: T.panel2, border: `1px solid ${T.border}`, color: T.text, fontSize: 12.5, fontFamily: F.sans }}>
          <option value="">All event types</option>
          {kinds.map((k) => <option key={k} value={k}>{k}</option>)}
        </select>
      </div>
      {loading ? <div style={{ color: T.t3, fontSize: 13, padding: 20, textAlign: "center" }}>Loading activity…</div> : (
        <div style={{ display: "flex", flexDirection: "column" }}>
          {events.length === 0 && <div style={{ color: T.t3, fontSize: 13, padding: 20, textAlign: "center" }}>No events yet.</div>}
          {events.map((e, i) => (
            <div key={str(e.id) || i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 4px", borderBottom: `1px solid ${T.border}` }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: levelColor(str(e.level)), flexShrink: 0 }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, color: T.text, fontWeight: 600 }}>{str(e.label) || str(e.kind)}</div>
                <div style={{ fontSize: 11.5, color: T.t3 }}>{str(e.email) || str(e.user_id) || "system"} · <span style={{ fontFamily: F.mono }}>{str(e.kind)}</span></div>
              </div>
              <div style={{ fontSize: 11.5, color: T.t3, whiteSpace: "nowrap" }}>{fmtDateTime(str(e.created_at))}</div>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

// ─── Positions ───────────────────────────────────────────────────────────────
function PositionsTab() {
  const [cov, setCov] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    api.getAdminCoverage().then(setCov).catch(() => setCov(null)).finally(() => setLoading(false));
  }, []);

  const perCountry: any[] = cov?.per_country || [];
  const chartData: api.LabelCount[] = perCountry.slice(0, 10).map((c) => ({ label: str(c.country || c.country_name), count: Number(c.positions) || 0 }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px,1fr))", gap: 12 }}>
        <StatCard icon={<Briefcase size={17} />} label="Total positions" value={loading ? "…" : (cov?.total_positions ?? 0)} tone={T.accent} />
        <StatCard icon={<Globe size={17} />} label="Countries covered" value={loading ? "…" : perCountry.length} tone={T.cyan} />
      </div>
      <BarBlock data={chartData} label="Positions by country (top 10)" />
      <Panel>
        <SectionTitle>Roles by country</SectionTitle>
        {perCountry.length === 0 ? <div style={{ color: T.t3, fontSize: 12, padding: 16, textAlign: "center" }}>No coverage data.</div> :
          perCountry.map((c: any) => (
            <div key={str(c.country)} style={{ borderBottom: `1px solid ${T.border}` }}>
              <div onClick={() => setOpen(open === str(c.country) ? null : str(c.country))} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "11px 4px", cursor: "pointer" }}>
                <span style={{ fontSize: 13, color: T.text, fontWeight: 600 }}>{str(c.country || c.country_name)}</span>
                <span style={{ fontSize: 12.5, color: T.t2, fontFamily: F.mono }}>{Number(c.positions) || 0} positions <ChevronRight size={13} style={{ verticalAlign: "middle", transform: open === str(c.country) ? "rotate(90deg)" : "none" }} /></span>
              </div>
              {open === str(c.country) && Array.isArray(c.top_roles) && (
                <div style={{ padding: "0 4px 12px", display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {c.top_roles.length === 0 ? <span style={{ fontSize: 12, color: T.t3 }}>No role breakdown.</span> :
                    c.top_roles.map((r: any, i: number) => <span key={i} style={{ fontSize: 11.5, padding: "4px 9px", borderRadius: 999, background: T.panel2, border: `1px solid ${T.border}`, color: T.t2 }}>{str(r.role)} · {Number(r.count) || 0}</span>)}
                </div>
              )}
            </div>
          ))}
      </Panel>
    </div>
  );
}

// ─── Feedback ────────────────────────────────────────────────────────────────
function FeedbackTab() {
  const [data, setData] = useState<{ feedback: api.FeedbackItem[]; stats: api.FeedbackStats } | null>(null);
  const [loading, setLoading] = useState(true);

  const load = () => { setLoading(true); api.getAdminFeedback({ limit: 300 }).then(setData).catch(() => setData(null)).finally(() => setLoading(false)); };
  useEffect(load, []);

  const stats = data?.stats;
  const distData: api.LabelCount[] = stats ? [5, 4, 3, 2, 1].map((n) => ({ label: `${n}★`, count: stats.distribution[String(n)] || 0 })) : [];
  const catData: api.LabelCount[] = stats ? Object.entries(stats.by_category).map(([label, count]) => ({ label, count: count as number })) : [];

  const setStatus = async (id: string, s: "new" | "reviewed" | "resolved") => {
    try { await api.setAdminFeedbackStatus(id, s); load(); } catch { /* ignore */ }
  };
  const statusColor = (s: string) => s === "resolved" ? T.green : s === "reviewed" ? T.amber : T.accent;

  if (loading) return <Panel><div style={{ color: T.t3, fontSize: 13, padding: 20, textAlign: "center" }}>Loading feedback…</div></Panel>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px,1fr))", gap: 12 }}>
        <StatCard icon={<MessageSquare size={17} />} label="Total responses" value={stats?.total ?? 0} tone={T.accent} />
        <StatCard icon={<Star size={17} />} label="Average rating" value={stats?.average_rating ? `${stats.average_rating}★` : "—"} tone={T.amber} />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px,1fr))", gap: 14 }}>
        <Panel>
          <SectionTitle>Rating distribution</SectionTitle>
          <div style={{ height: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={distData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.1)" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: T.t3, fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: T.t3, fontSize: 10 }} allowDecimals={false} axisLine={false} tickLine={false} width={28} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(148,163,184,0.08)" }} />
                <Bar dataKey="count" radius={[6, 6, 0, 0]} barSize={34}>
                  {distData.map((_, i) => <Cell key={i} fill={[T.green, T.green, T.amber, T.red, T.red][i]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
        <Panel>
          <SectionTitle>By category</SectionTitle>
          <div style={{ height: 200, display: "flex", alignItems: "center" }}>
            {catData.length === 0 ? <div style={{ color: T.t3, fontSize: 12, width: "100%", textAlign: "center" }}>No feedback yet.</div> : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={catData} dataKey="count" nameKey="label" cx="50%" cy="50%" outerRadius={78} label={(e: any) => e.label}>
                    {catData.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                  </Pie>
                  <Tooltip contentStyle={tooltipStyle} />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </Panel>
      </div>

      <Panel>
        <SectionTitle>Latest feedback</SectionTitle>
        {(data?.feedback || []).length === 0 ? <div style={{ color: T.t3, fontSize: 13, padding: 16, textAlign: "center" }}>No feedback submitted yet.</div> : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {data!.feedback.map((f) => (
              <div key={f.id} style={{ background: T.panel2, border: `1px solid ${T.border}`, borderRadius: 12, padding: 14 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, flexWrap: "wrap" }}>
                  <span style={{ color: T.amber, fontSize: 13 }}>{"★".repeat(f.rating)}<span style={{ color: T.t3 }}>{"★".repeat(Math.max(0, 5 - f.rating))}</span></span>
                  <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 999, background: `${T.accent}18`, color: "#93C5FD", border: `1px solid ${T.accent}33` }}>{f.category}</span>
                  <span style={{ fontSize: 11.5, color: T.t3 }}>{f.email || f.user_id}</span>
                  <span style={{ fontSize: 11.5, color: T.t3, marginLeft: "auto" }}>{fmtDateTime(f.created_at)}</span>
                </div>
                {f.message && <div style={{ fontSize: 13, color: T.t2, lineHeight: 1.5, marginBottom: 8 }}>{f.message}</div>}
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <span style={{ fontSize: 11, color: statusColor(str(f.status)), fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em" }}>{f.status || "new"}</span>
                  <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                    {(["reviewed", "resolved"] as const).map((s) => (
                      <button key={s} onClick={() => setStatus(f.id, s)} style={{ height: 28, padding: "0 10px", borderRadius: 8, border: `1px solid ${T.border}`, background: "transparent", color: T.t2, fontSize: 11.5, fontWeight: 600, cursor: "pointer", fontFamily: F.sans }}>Mark {s}</button>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
