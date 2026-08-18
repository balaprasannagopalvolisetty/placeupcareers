import { useEffect, useMemo, useState } from "react";
import { LoadingLogo } from "../LoadingLogo";
import { Link } from "react-router";
import { motion } from "motion/react";
import { Download, ExternalLink, Search, RefreshCw, CheckCircle2, Clock } from "lucide-react";
import * as api from "../../lib/api";
import { ReviewBeforeSubmit } from "./ReviewBeforeSubmit";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  text: "var(--pu-f1f5f9-t)",
  t2: "var(--pu-226-232-240-072)",
  t3: "var(--pu-148-163-184-075)",
  border: "var(--pu-148-163-184-008)",
  glass: "var(--pu-15-30-55-055)",
  grad: "linear-gradient(135deg, var(--pu-2563eb), var(--pu-0ea5e9))",
  red: "var(--pu-3b82f6-t)",
};

type Row = api.UserApplicationRow;

function formatDate(value?: string): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value.slice(0, 10);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

// Applied means genuinely applied. Merely opened/tracked/skipped positions
// are never shown or counted on this page.
const isApplied = (r: Row) => r.status === "applied";

export function ApplicationsPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [automated, setAutomated] = useState<api.ApplicationRecord[]>([]);
  const [reviewing, setReviewing] = useState<api.ApplicationRecord | null>(null);

  async function downloadDocument(appId: string, kind: "resume" | "cover_letter") {
    try {
      const { blob, filename } = await api.getApplicationDocument(appId, kind, "pdf");
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err: any) {
      setError(err?.message || "Document is not available.");
    }
  }

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    Promise.allSettled([api.getUserApplications(), api.listApplications()])
      .then(([trackedResult, automatedResult]) => {
        if (!active) return;
        const data = trackedResult.status === "fulfilled" ? trackedResult.value : [];
        const sorted = [...(Array.isArray(data) ? data : [])]
          .filter(isApplied)
          .sort((a, b) => {
            const ta = new Date(a.updated_at || a.created_at || 0).getTime();
            const tb = new Date(b.updated_at || b.created_at || 0).getTime();
            return tb - ta;
          });
        setRows(sorted);
        if (automatedResult.status === "fulfilled") {
          setAutomated([...(automatedResult.value || [])]
            .filter((app) => app.status === "applied")
            .sort((a, b) =>
              new Date(b.updated_at || b.created_at || 0).getTime() - new Date(a.updated_at || a.created_at || 0).getTime()
            ));
        }
        if (trackedResult.status === "rejected" && automatedResult.status === "rejected") {
          setError("Could not load your applications.");
        }
      })
      .catch((err) => {
        if (!active) return;
        setError((err as Error)?.message || "Could not load your applications.");
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

  const counts = useMemo(() => ({
    applied: rows.length,
    heard: rows.filter((r) => r.heard_back === true).length,
  }), [rows]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) => `${r.title || ""} ${r.company || ""}`.toLowerCase().includes(q));
  }, [rows, search]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18, width: "100%", minWidth: 0 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ fontFamily: F.sans, fontSize: 22, fontWeight: 700, color: T.text, marginBottom: 4 }}>
            Applications
          </h2>
          <p style={{ fontSize: 13, color: T.t2, fontFamily: F.sans, marginTop: 0 }}>
            Positions you actually applied to.
          </p>
        </div>
        <button
          onClick={() => setReloadKey((v) => v + 1)}
          style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            padding: "8px 12px", borderRadius: 10,
            border: `1px solid ${T.border}`, background: "var(--pu-148-163-184-004)",
            color: T.t2, fontSize: 12, fontFamily: F.sans, cursor: "pointer",
          }}
        >
          <RefreshCw size={12} /> Refresh
        </button>
      </div>

      {automated.length > 0 && (
        <div style={{ background: T.glass, border: `1px solid ${T.border}`, borderRadius: 14, padding: 14 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: T.text, fontFamily: F.sans, marginBottom: 10 }}>PlaceUp-assisted applications</div>
          <div style={{ display: "grid", gap: 8 }}>
            {automated.slice(0, 20).map((app) => (
              <div key={app.id} style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: 10, alignItems: "center", padding: "10px 12px", borderRadius: 10, border: `1px solid ${T.border}`, background: "var(--pu-148-163-184-003)" }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ color: T.text, fontSize: 13, fontWeight: 700, fontFamily: F.sans, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{app.title || "Application"}</div>
                  <div style={{ color: T.t3, fontSize: 11, fontFamily: F.sans, marginTop: 2 }}>{app.company || "Unknown company"} · {app.status.replaceAll("_", " ")}</div>
                  {app.confirmation_ref && <div style={{ color: "var(--pu-86efac-t)", fontSize: 11, fontFamily: F.mono, marginTop: 4 }}>ATS confirmation: {app.confirmation_ref}</div>}
                  {app.submitted_at && <div style={{ color: T.t3, fontSize: 10, marginTop: 2 }}>Submitted {formatDate(app.submitted_at)}{app.confirmation_email_sent ? " · receipt emailed" : ""}</div>}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
                {app.status === "needs_review" ? (
                  <button onClick={() => setReviewing(app)} style={{ padding: "7px 11px", borderRadius: 8, border: "none", background: T.grad, color: "white", fontSize: 11, fontWeight: 700, cursor: "pointer" }}>Review</button>
                ) : null}
                {app.tailored_resume_url && <button onClick={() => downloadDocument(app.id, "resume")} title="Download tailored resume" style={{ width: 30, height: 30, borderRadius: 8, border: `1px solid ${T.border}`, background: "transparent", color: T.t2, cursor: "pointer" }}><Download size={12} /></button>}
                {app.job_url ? (
                  <a href={app.job_url} target="_blank" rel="noopener noreferrer" style={{ color: T.t2, fontSize: 11, textDecoration: "none" }}>Open <ExternalLink size={10} /></a>
                ) : null}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Stat strip — applied positions only */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 10 }}>
        {[
          { label: "Applied", value: counts.applied, icon: CheckCircle2, color: T.red },
          { label: "Heard back", value: counts.heard, icon: Clock, color: "var(--pu-22c55e-t)" },
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
              background: "var(--pu-59-130-246-01)", border: "1px solid var(--pu-59-130-246-022)",
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

      {/* Search */}
      <div style={{
        background: T.glass, backdropFilter: "blur(20px)",
        border: `1px solid ${T.border}`, borderRadius: 14,
        padding: "10px 14px", display: "flex", gap: 10, alignItems: "center",
      }}>
        <div style={{
          display: "flex", alignItems: "center", gap: 8, flex: 1,
          height: 36, padding: "0 12px", borderRadius: 8,
          border: `1px solid ${T.border}`, background: "var(--pu-148-163-184-004)",
        }}>
          <Search size={13} color={T.t3} />
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by company or title…"
            style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: T.text, fontSize: 13, fontFamily: F.sans }} />
        </div>
      </div>

      {error && (
        <div style={{ padding: "14px 16px", borderRadius: 12,
          background: "var(--pu-59-130-246-008)", border: "1px solid var(--pu-59-130-246-025)",
          color: T.text, fontFamily: F.sans, fontSize: 13 }}>
          {error}
        </div>
      )}

      {/* Minimal rows: title · posted date · applied date */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {loading && rows.length === 0 && (
          <LoadingLogo label="Loading your applications" />
        )}
        {!loading && filtered.length === 0 && !error && (
          <div style={{ textAlign: "center", padding: 40, background: T.glass, border: `1px solid ${T.border}`, borderRadius: 16, color: T.t2, fontFamily: F.sans }}>
            <div style={{ fontSize: 14, marginBottom: 6 }}>No applications yet.</div>
            <div style={{ fontSize: 12, color: T.t3, marginBottom: 12 }}>
              Apply to any job and it will be tracked here.
            </div>
            <Link to="/dashboard/jobs" style={{ color: T.red, fontWeight: 600 }}>Browse jobs →</Link>
          </div>
        )}
        {filtered.map((row, i) => (
          <motion.div key={`${row.job_id}-${row.created_at || i}`}
            initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(0.02 * i, 0.3) }}
            style={{
              background: T.glass, backdropFilter: "blur(20px)",
              border: `1px solid ${T.border}`, borderRadius: 12, padding: "12px 16px",
              display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto auto", gap: 14, alignItems: "center",
            }}>
            <Link to={`/dashboard/jobs/${row.job_id}`}
              title={`${row.title || "Untitled role"}${row.company ? ` · ${row.company}` : ""}`}
              style={{ fontSize: 14, fontWeight: 600, color: T.text, fontFamily: F.sans, textDecoration: "none", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {row.title || "Untitled role"}
            </Link>
            <span style={{ fontSize: 11, color: T.t3, fontFamily: F.sans, whiteSpace: "nowrap" }}>
              Posted {formatDate(row.posted_at)}
            </span>
            <span style={{ fontSize: 11, color: T.t2, fontFamily: F.sans, whiteSpace: "nowrap" }}>
              Applied {formatDate(row.created_at || row.updated_at)}
            </span>
          </motion.div>
        ))}
      </div>
      {reviewing && (
        <ReviewBeforeSubmit
          application={reviewing}
          onClose={() => setReviewing(null)}
          onApproved={(updated) => setAutomated((items) => items.map((item) => item.id === updated.id ? updated : item))}
        />
      )}
    </div>
  );
}

export default ApplicationsPage;
