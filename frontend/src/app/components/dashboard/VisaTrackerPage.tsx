import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Shield, TrendingUp, Users, Globe, Search } from "lucide-react";
import * as api from "../../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  text: "#F2EEB3", t2: "rgba(242,238,179,0.65)", t3: "rgba(242,238,179,0.45)",
  border: "rgba(242,238,179,0.08)", glass: "rgba(64,18,18,0.55)",
  grad: "linear-gradient(135deg, #8C3A27, #A6372D, #401212)", red: "#A6372D", burnt: "#8C3A27",
};

interface SponsorRow {
  employer: string;
  city?: string;
  state?: string;
  type: string;
  fiscal_year?: number;
  approvals: number;
  new_approvals?: number;
  continuing_approvals?: number;
  denials: number;
  rate: number;
  status: string;
  total_petitions?: number;
}

interface SponsorListResponse {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  sponsors: SponsorRow[];
}

interface DashboardResponse {
  stats: {
    h1b_sponsors: string;
    opt_roles: string;
    avg_approval_rate: string;
    petitions_last_year: string;
  };
  sponsors: SponsorRow[];
}

export function VisaTrackerPage() {
  const [stats, setStats] = useState({
    h1b_sponsors: "—", opt_roles: "—", avg_approval_rate: "—", petitions_last_year: "—",
  });
  const [sponsors, setSponsors] = useState<SponsorRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [search, setSearch] = useState("");
  const [stateFilter, setStateFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Headline stats — once.
  useEffect(() => {
    fetch("/api/visa/dashboard")
      .then((r) => r.json() as Promise<DashboardResponse>)
      .then((data) => { if (data?.stats) setStats({ ...stats, ...data.stats }); })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Sponsor list — debounced on search/state/page.
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    const handle = setTimeout(() => {
      const params = new URLSearchParams();
      if (search.trim()) params.set("company", search.trim());
      if (stateFilter.trim()) params.set("state", stateFilter.trim());
      params.set("page", String(page));
      params.set("page_size", String(pageSize));
      fetch(`/api/visa/sponsors?${params.toString()}`)
        .then((r) => r.json() as Promise<SponsorListResponse>)
        .then((data) => {
          if (!active) return;
          setSponsors(data?.sponsors || []);
          setTotal(data?.total || 0);
        })
        .catch((err) => { if (active) setError((err as Error).message); })
        .finally(() => { if (active) setLoading(false); });
    }, 300);
    return () => { active = false; clearTimeout(handle); };
  }, [search, stateFilter, page, pageSize]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const statCards = [
    { icon: Shield,      label: "H-1B Sponsors",       value: stats.h1b_sponsors,        color: T.red },
    { icon: Globe,       label: "OPT Roles Active",    value: stats.opt_roles,           color: T.burnt },
    { icon: TrendingUp,  label: "Top-25 Approval Rate",value: stats.avg_approval_rate,   color: T.red },
    { icon: Users,       label: "Petitions (Top-25)",  value: stats.petitions_last_year, color: T.burnt },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {/* Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}>
        {statCards.map((s, i) => (
          <motion.div key={s.label} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}
            style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 14, padding: "16px 18px" }}>
            <div style={{ width: 32, height: 32, borderRadius: 8, background: "rgba(166,55,45,0.10)", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 10 }}>
              <s.icon size={14} color={s.color} />
            </div>
            <div style={{ fontFamily: F.sans, fontSize: 22, fontWeight: 800, color: s.color, lineHeight: 1, marginBottom: 4 }}>{s.value}</div>
            <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans }}>{s.label}</div>
          </motion.div>
        ))}
      </div>

      {/* Search bar */}
      <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 14, padding: "12px 16px", display: "flex", gap: 10, alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1, height: 36, padding: "0 12px", borderRadius: 8, border: `1px solid ${T.border}`, background: "rgba(242,238,179,0.04)" }}>
          <Search size={13} color={T.t3} />
          <input
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            placeholder="Search by company name (e.g. Google, Stripe, Microsoft)"
            style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: T.text, fontSize: 13, fontFamily: F.sans }}
          />
        </div>
        <input
          value={stateFilter}
          onChange={(e) => { setStateFilter(e.target.value.toUpperCase()); setPage(1); }}
          placeholder="State (CA, NY...)"
          maxLength={2}
          style={{ width: 110, height: 36, padding: "0 12px", borderRadius: 8, border: `1px solid ${T.border}`, background: "rgba(242,238,179,0.04)", color: T.text, fontSize: 13, outline: "none", fontFamily: F.sans, textTransform: "uppercase" }}
        />
        <span style={{ fontSize: 12, color: T.t3, fontFamily: F.sans, whiteSpace: "nowrap" }}>
          {loading ? "…" : `${total.toLocaleString()} match${total === 1 ? "" : "es"}`}
        </span>
      </div>

      {/* Sponsor table */}
      <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 16, overflow: "hidden" }}>
        {error && <div style={{ padding: 16, color: T.red, fontFamily: F.sans, fontSize: 13 }}>Error: {error}</div>}
        <div style={{ overflowX: "auto", maxHeight: "60vh", overflowY: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead style={{ position: "sticky", top: 0, background: "rgba(8,14,32,0.95)", backdropFilter: "blur(20px)" }}>
              <tr>
                {["Employer", "Location", "Type", "FY", "Approvals", "Denials", "Approval Rate", "Status"].map((h) => (
                  <th key={h} style={{ padding: "12px 16px", textAlign: "left", fontSize: 10, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: T.t3, fontFamily: F.sans, borderBottom: `1px solid ${T.border}` }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && sponsors.length === 0 && (
                <tr><td colSpan={8} style={{ padding: 30, textAlign: "center", color: T.t3, fontFamily: F.sans, fontSize: 13 }}>Loading H1B records…</td></tr>
              )}
              {!loading && sponsors.length === 0 && (
                <tr><td colSpan={8} style={{ padding: 30, textAlign: "center", color: T.t3, fontFamily: F.sans, fontSize: 13 }}>No matching sponsors found.</td></tr>
              )}
              {sponsors.map((row, i) => (
                <motion.tr key={`${row.employer}-${i}-${row.city}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.02 * i }} style={{ borderBottom: `1px solid ${T.border}` }}>
                  <td style={{ padding: "11px 16px", fontSize: 12.5, fontWeight: 600, color: T.text, fontFamily: F.sans }}>{row.employer}</td>
                  <td style={{ padding: "11px 16px", fontSize: 12, color: T.t2, fontFamily: F.sans }}>{[row.city, row.state].filter(Boolean).join(", ") || "—"}</td>
                  <td style={{ padding: "11px 16px" }}>
                    <span style={{ fontSize: 9, fontWeight: 700, padding: "3px 7px", borderRadius: 3, background: "rgba(140,58,39,0.15)", color: T.burnt, border: "1px solid rgba(140,58,39,0.3)", fontFamily: F.sans }}>{row.type}</span>
                  </td>
                  <td style={{ padding: "11px 16px", fontSize: 11, color: T.t3, fontFamily: F.mono }}>{row.fiscal_year || "—"}</td>
                  <td style={{ padding: "11px 16px", fontSize: 12, fontFamily: F.mono, fontWeight: 500, color: T.red }}>{row.approvals.toLocaleString()}</td>
                  <td style={{ padding: "11px 16px", fontSize: 12, fontFamily: F.mono, color: "rgba(242,100,100,0.8)" }}>{row.denials}</td>
                  <td style={{ padding: "11px 16px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <div style={{ width: 56, height: 4, borderRadius: 2, background: "rgba(242,238,179,0.06)", overflow: "hidden" }}>
                        <motion.div initial={{ width: 0 }} animate={{ width: `${row.rate}%` }} transition={{ duration: 0.7 }} style={{ height: "100%", background: T.grad }} />
                      </div>
                      <span style={{ fontSize: 11, fontWeight: 700, color: T.red, fontFamily: F.mono }}>{row.rate}%</span>
                    </div>
                  </td>
                  <td style={{ padding: "11px 16px" }}>
                    <span style={{ fontSize: 9, padding: "3px 7px", borderRadius: 3, background: row.status === "Active" ? "rgba(34,197,94,0.08)" : "rgba(242,238,179,0.05)", color: row.status === "Active" ? "#22c55e" : T.t3, border: `1px solid ${row.status === "Active" ? "rgba(34,197,94,0.2)" : T.border}`, fontFamily: F.sans, fontWeight: 600 }}>{row.status}</span>
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
        {/* Pagination */}
        {totalPages > 1 && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 16px", borderTop: `1px solid ${T.border}` }}>
            <span style={{ fontSize: 11, color: T.t3, fontFamily: F.sans }}>Page {page} of {totalPages}</span>
            <div style={{ display: "flex", gap: 6 }}>
              <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}
                style={{ padding: "6px 12px", borderRadius: 6, border: `1px solid ${T.border}`, background: "transparent", color: page <= 1 ? T.t3 : T.t2, fontSize: 11, cursor: page <= 1 ? "not-allowed" : "pointer", fontFamily: F.sans }}>
                Previous
              </button>
              <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages}
                style={{ padding: "6px 12px", borderRadius: 6, border: "none", background: page >= totalPages ? "rgba(242,238,179,0.05)" : T.grad, color: page >= totalPages ? T.t3 : "#fff", fontSize: 11, cursor: page >= totalPages ? "not-allowed" : "pointer", fontFamily: F.sans, fontWeight: 600 }}>
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
