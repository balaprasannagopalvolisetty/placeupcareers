import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import { Search, Filter, X, MapPin, DollarSign, Clock, Bookmark, ExternalLink, Flame } from "lucide-react";
import * as api from "../../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  text: "#F2EEB3", t2: "rgba(242,238,179,0.65)", t3: "rgba(242,238,179,0.45)",
  border: "rgba(242,238,179,0.08)", glass: "rgba(64,18,18,0.55)",
  grad: "linear-gradient(135deg, #8C3A27, #A6372D, #401212)",
  red: "#A6372D", burnt: "#8C3A27", dark: "#401212",
};

const STATUS_CHIPS = ["All", "New", "Applied", "Interview", "Saved"];
const VISA_BADGES: Record<string, { bg: string; color: string; border: string }> = {
  "H-1B":   { bg: "rgba(140,58,39,0.15)", color: "#8C3A27", border: "rgba(140,58,39,0.35)" },
  "OPT":    { bg: "rgba(166,55,45,0.12)", color: "#A6372D", border: "rgba(166,55,45,0.3)" },
  "STEM":   { bg: "rgba(64,18,18,0.15)",  color: "#A6372D", border: "rgba(64,18,18,0.3)" },
  "Vol":    { bg: "rgba(34,197,94,0.10)", color: "#22c55e", border: "rgba(34,197,94,0.3)" },
};

function normalizeVisa(visa: unknown): string[] {
  if (Array.isArray(visa)) return visa.filter((v): v is string => typeof v === "string");
  if (visa && typeof visa === "object") {
    const map: Record<string, string> = {
      visa_h1b: "H-1B", visa_opt: "OPT", visa_stem_opt: "STEM",
      h1b_verified: "H-1B Verified", green_card: "Green Card",
    };
    return Object.entries(visa as Record<string, unknown>)
      .filter(([key, value]) => key !== "visa_score" && Boolean(value))
      .map(([key]) => map[key] ?? key.replace(/_/g, " "));
  }
  if (typeof visa === "string") return visa.split(",").map((s) => s.trim()).filter(Boolean);
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

interface TaxonomyRole { name: string; synonyms: string[]; visa: string[]; hot: boolean }
interface TaxonomyCategory { name: string; icon: string; roles: TaxonomyRole[] }

function ATSRing({ score, size = 60 }: { score: number; size?: number }) {
  const r = (size/2) - 5, circ = 2*Math.PI*r;
  const offset = circ * (1 - score/100);
  const color = score >= 80 ? T.red : score >= 60 ? T.burnt : T.dark;
  return (
    <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
      <svg viewBox={`0 0 ${size} ${size}`} style={{ width: "100%", height: "100%", transform: "rotate(-90deg)" }}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="rgba(242,238,179,0.08)" strokeWidth="5" />
        <motion.circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth="5" strokeLinecap="round"
          strokeDasharray={circ} initial={{ strokeDashoffset: circ }} animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1.2, ease: "easeOut" }} />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <span style={{ fontFamily: F.mono, fontSize: 13, fontWeight: 500, color }}>{score}</span>
        <span style={{ fontSize: 7, color: T.t3, fontFamily: F.sans, letterSpacing: "0.05em" }}>ATS</span>
      </div>
    </div>
  );
}

export function JobsPage({ onJobClick }: { onJobClick: (id: string) => void }) {
  const [taxonomy, setTaxonomy] = useState<TaxonomyCategory[]>([]);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [activeRole, setActiveRole] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");
  const [location, setLocation] = useState("");
  const [visaOnly, setVisaOnly] = useState(false);

  const [jobs, setJobs] = useState<api.JobPost[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load taxonomy once.
  useEffect(() => {
    fetch("/api/jobs/taxonomy")
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data?.categories)) setTaxonomy(data.categories);
      })
      .catch(() => {});
  }, []);

  // Reload jobs whenever filters change.
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    const params: Record<string, string | number | boolean> = { page: 1, page_size: 50 };
    if (search) params.search = search;
    if (location) params.location = location;
    if (visaOnly) params.visa_only = true;
    if (activeCategory && !activeRole) params.category = activeCategory;
    if (activeRole) params.role = activeRole;

    api.getJobs(params)
      .then((response) => {
        if (!active) return;
        setJobs(response.jobs || []);
        setTotal(response.total ?? response.jobs?.length ?? 0);
      })
      .catch((err) => {
        if (active) {
          setError((err as Error).message || "Could not load jobs");
          setJobs([]);
          setTotal(0);
        }
      })
      .finally(() => { if (active) setLoading(false); });

    return () => { active = false; };
  }, [activeCategory, activeRole, search, location, visaOnly]);

  const filtered = useMemo(() => {
    if (statusFilter === "All") return jobs;
    return jobs.filter((j) => (j.status || "New") === statusFilter);
  }, [jobs, statusFilter]);

  const currentCategory = taxonomy.find((c) => c.name === activeCategory);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 20 }}>
      {/* CATEGORY SIDEBAR */}
      <aside style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 16, padding: 12, height: "fit-content", position: "sticky", top: 20 }}>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: T.t3, fontFamily: F.sans, padding: "8px 10px 12px" }}>Categories</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 2, maxHeight: "70vh", overflowY: "auto" }}>
          {taxonomy.map((cat) => {
            const isActive = cat.name === activeCategory;
            return (
              <div key={cat.name}>
                <button
                  onClick={() => { setActiveCategory(cat.name); setActiveRole(null); }}
                  style={{
                    width: "100%", textAlign: "left", padding: "9px 10px", borderRadius: 8,
                    border: "none", background: isActive ? "rgba(166,55,45,0.10)" : "transparent",
                    color: isActive ? T.red : T.t2, fontSize: 13, fontFamily: F.sans, cursor: "pointer",
                    fontWeight: isActive ? 600 : 400, display: "flex", justifyContent: "space-between", alignItems: "center",
                  }}
                >
                  {cat.name}
                  <span style={{ fontSize: 11, color: T.t3 }}>{cat.roles.length}</span>
                </button>
                {isActive && (
                  <div style={{ marginLeft: 8, paddingLeft: 8, borderLeft: `1px solid ${T.border}`, marginTop: 4, marginBottom: 4 }}>
                    {cat.roles.map((role) => (
                      <button
                        key={role.name}
                        onClick={() => setActiveRole(activeRole === role.name ? null : role.name)}
                        style={{
                          width: "100%", textAlign: "left", padding: "6px 8px", borderRadius: 6,
                          border: "none", background: activeRole === role.name ? "rgba(166,55,45,0.06)" : "transparent",
                          color: activeRole === role.name ? T.red : T.t3, fontSize: 12, fontFamily: F.sans, cursor: "pointer",
                          display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6,
                        }}
                      >
                        <span>{role.name}</span>
                        <span style={{ display: "flex", gap: 3, alignItems: "center", flexShrink: 0 }}>
                          {role.hot && <Flame size={9} color={T.red} />}
                          {role.visa.slice(0, 2).map((v) => {
                            const s = VISA_BADGES[v] ?? VISA_BADGES["OPT"];
                            return <span key={v} style={{ fontSize: 8, fontWeight: 700, padding: "1px 4px", borderRadius: 3, background: s.bg, color: s.color, border: `1px solid ${s.border}` }}>{v}</span>;
                          })}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </aside>

      {/* JOBS LIST */}
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {/* Search + filter bar */}
        <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 14, padding: "12px 16px", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1, minWidth: 200, height: 36, padding: "0 12px", borderRadius: 8, border: `1px solid ${T.border}`, background: "rgba(242,238,179,0.04)" }}>
            <Search size={13} color={T.t3} />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search title, company, JD..."
              style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: T.text, fontSize: 13, fontFamily: F.sans }} />
          </div>
          <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Location"
            style={{ width: 140, height: 36, padding: "0 12px", borderRadius: 8, border: `1px solid ${T.border}`, background: "rgba(242,238,179,0.04)", color: T.text, fontSize: 13, outline: "none" }} />
          <button onClick={() => setVisaOnly(!visaOnly)}
            style={{ height: 36, padding: "0 12px", borderRadius: 8, border: `1px solid ${visaOnly ? "rgba(166,55,45,0.4)" : T.border}`, background: visaOnly ? "rgba(166,55,45,0.10)" : "transparent", color: visaOnly ? T.red : T.t2, fontSize: 12, fontFamily: F.sans, cursor: "pointer", display: "flex", alignItems: "center", gap: 5 }}>
            <Filter size={12} /> Visa-friendly
          </button>
          <div style={{ display: "flex", gap: 6 }}>
            {STATUS_CHIPS.map((s) => (
              <button key={s} onClick={() => setStatusFilter(s)}
                style={{ height: 32, padding: "0 12px", borderRadius: 9999, border: `1px solid ${statusFilter === s ? "transparent" : T.border}`, background: statusFilter === s ? T.grad : "transparent", color: statusFilter === s ? "#fff" : T.t2, fontSize: 12, cursor: "pointer", fontFamily: F.sans, fontWeight: statusFilter === s ? 600 : 400 }}>
                {s}
              </button>
            ))}
          </div>
        </div>

        {/* Active filters strip */}
        {(activeRole || activeCategory) && (
          <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
            <span style={{ fontSize: 11, color: T.t3, fontFamily: F.sans }}>{filtered.length} of {total} positions</span>
            {activeCategory && (
              <span style={{ display: "inline-flex", gap: 4, alignItems: "center", fontSize: 11, padding: "3px 8px", borderRadius: 4, background: "rgba(166,55,45,0.08)", color: T.red, border: "1px solid rgba(166,55,45,0.25)", fontFamily: F.sans }}>
                Category: {activeCategory}
              </span>
            )}
            {activeRole && (
              <span style={{ display: "inline-flex", gap: 4, alignItems: "center", fontSize: 11, padding: "3px 8px", borderRadius: 4, background: "rgba(166,55,45,0.08)", color: T.red, border: "1px solid rgba(166,55,45,0.25)", fontFamily: F.sans }}>
                Role: {activeRole}
                <button onClick={() => setActiveRole(null)} style={{ background: "none", border: "none", cursor: "pointer", color: T.red, padding: 0 }}><X size={10} /></button>
              </span>
            )}
          </div>
        )}

        {error && <div style={{ color: T.red, fontFamily: F.sans, fontSize: 13 }}>Error: {error}</div>}

        {/* Job cards */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          {loading && (
            <div style={{ gridColumn: "1 / -1", textAlign: "center", padding: 40, color: T.t3, fontFamily: F.sans }}>Loading jobs…</div>
          )}
          {!loading && filtered.length === 0 && (
            <div style={{ gridColumn: "1 / -1", textAlign: "center", padding: 40, background: T.glass, border: `1px solid ${T.border}`, borderRadius: 16, color: T.t2, fontFamily: F.sans }}>
              <div style={{ fontSize: 14, marginBottom: 6 }}>No jobs found yet for this filter.</div>
              <div style={{ fontSize: 12, color: T.t3 }}>The scraper runs every 6h. Clear filters or trigger a fresh scrape from the admin endpoint.</div>
            </div>
          )}
          {filtered.map((job, i) => {
            const visaBadges = normalizeVisa(job.visa);
            const match = job.match_score ?? job.match ?? 0;
            const id = String(job.id || "");
            return (
              <motion.div
                key={id}
                initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}
                whileHover={{ y: -4, boxShadow: "0 16px 36px rgba(1,17,38,0.35)" }}
                onClick={() => onJobClick(id)}
                style={{
                  background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`,
                  borderLeft: `4px solid ${match >= 80 ? T.red : match >= 60 ? T.burnt : T.dark}`,
                  borderRadius: 16, padding: 18, cursor: "pointer",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 14, fontWeight: 600, color: T.text, fontFamily: F.sans, lineHeight: 1.3, marginBottom: 4 }}>{job.title || "Untitled role"}</div>
                    <div style={{ fontSize: 12, color: T.t2, fontFamily: F.sans, marginBottom: 8 }}>{job.company || "Unknown"}</div>
                    <div style={{ display: "flex", gap: 10, fontSize: 11, color: T.t3, fontFamily: F.sans, marginBottom: 8, flexWrap: "wrap" }}>
                      <span style={{ display: "inline-flex", gap: 3, alignItems: "center" }}><MapPin size={10} />{job.location || "Remote"}</span>
                      <span style={{ display: "inline-flex", gap: 3, alignItems: "center" }}><DollarSign size={10} />{formatSalary(job.salary)}</span>
                      <span style={{ display: "inline-flex", gap: 3, alignItems: "center" }}><Clock size={10} />{job.posted_at || "Recently"}</span>
                    </div>
                    {job.description && (
                      <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans, lineHeight: 1.55, marginBottom: 8, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                        {String(job.description).slice(0, 220)}
                      </div>
                    )}
                    <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                      {visaBadges.slice(0, 4).map((v) => {
                        const s = VISA_BADGES[v] ?? { bg: "rgba(64,18,18,0.1)", color: T.t2, border: T.border };
                        return <span key={v} style={{ fontSize: 9, fontWeight: 700, padding: "2px 7px", borderRadius: 3, background: s.bg, color: s.color, border: `1px solid ${s.border}`, fontFamily: F.sans }}>{v}</span>;
                      })}
                      {(job as any).category && (
                        <span style={{ fontSize: 9, padding: "2px 7px", borderRadius: 3, background: "rgba(242,238,179,0.05)", color: T.t3, border: `1px solid ${T.border}`, fontFamily: F.sans }}>{(job as any).category}</span>
                      )}
                    </div>
                  </div>
                  <ATSRing score={match} size={64} />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12, paddingTop: 10, borderTop: `1px solid ${T.border}` }}>
                  <span style={{ fontSize: 11, color: T.t3, fontFamily: F.sans }}>{(job as any).role || job.status || "New"}</span>
                  <div style={{ display: "flex", gap: 6 }}>
                    <button onClick={(e) => e.stopPropagation()} style={{ padding: "5px 10px", borderRadius: 6, border: `1px solid ${T.border}`, background: "transparent", color: T.t2, fontSize: 11, cursor: "pointer", fontFamily: F.sans, display: "flex", alignItems: "center", gap: 3 }}><Bookmark size={10}/> Save</button>
                    <button onClick={(e) => { e.stopPropagation(); onJobClick(id); }} style={{ padding: "5px 10px", borderRadius: 6, border: "none", background: T.grad, color: "#fff", fontSize: 11, cursor: "pointer", fontFamily: F.sans, fontWeight: 600, display: "flex", alignItems: "center", gap: 3 }}><ExternalLink size={10}/> View</button>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

