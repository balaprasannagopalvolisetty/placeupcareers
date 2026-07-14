/**
 * One-Click Apply — positions sourced from Tier A candidate-apply APIs.
 *
 * A job is "ready" when PlaceUp holds a submit credential for its ATS (an open
 * API like Recruitee, or an approved partner token). Ready jobs submit through
 * the official API after the review-before-submit gate — no CAPTCHA, no browser
 * automation. Jobs whose ATS isn't credentialed yet are shown as "Prepare"
 * (they still tailor + review, but can't auto-submit until the credential is
 * added). The ready set grows automatically as partner programs are approved.
 *
 * Follows the app rules: react-router, motion/react, theme tokens only.
 */
import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import { Zap, ShieldCheck, Clock, RefreshCw, Building2, MapPin } from "lucide-react";
import { LoadingLogo } from "../LoadingLogo";
import * as api from "../../lib/api";
import { ReviewBeforeSubmit } from "./ReviewBeforeSubmit";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  text: "var(--pu-f1f5f9-t)",
  t2: "var(--pu-226-232-240-072)",
  t3: "var(--pu-148-163-184-075)",
  border: "var(--pu-148-163-184-008)",
  card: "var(--pu-15-30-55-055)",
  grad: "linear-gradient(135deg, var(--pu-2563eb), var(--pu-0ea5e9))",
  green: "var(--pu-22c55e-b)",
  warn: "var(--pu-f59e0b)",
};

export function OneClickApplyPage() {
  const [feed, setFeed] = useState<api.OneClickFeed | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [readyOnly, setReadyOnly] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [review, setReview] = useState<api.ApplicationRecord | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setFeed(await api.getOneClickJobs({ limit: 80, ready_only: readyOnly }));
    } catch (e: any) {
      setError(e?.message || "Could not load One-Click positions.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [readyOnly]);

  const jobs = feed?.jobs || [];
  const readyCount = useMemo(() => jobs.filter((j) => j.one_click_ready).length, [jobs]);

  async function startApply(job: api.OneClickJob) {
    setBusyId(job.job_id);
    setError(null);
    try {
      const appRecord = await api.startApplication({ job_id: job.job_id, generate_cover_letter: true });
      setReview(appRecord);
    } catch (e: any) {
      setError(e?.message || "Could not prepare this application.");
    } finally {
      setBusyId(null);
    }
  }

  if (loading && !feed) return <LoadingLogo />;

  return (
    <div style={{ maxWidth: 1240, margin: "0 auto", fontFamily: F.sans, color: T.text }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Zap size={22} style={{ color: "var(--pu-0ea5e9)" }} />
            <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0 }}>One-Click Apply</h1>
          </div>
          <p style={{ fontSize: 14, color: T.t2, margin: "8px 0 0", maxWidth: 720 }}>
            Positions from ATS platforms with a candidate-apply API. Ready jobs submit
            through the official API after your review — no CAPTCHA, no browser step.
            More light up as partner integrations are approved.
          </p>
        </div>
        <button onClick={load}
          style={{
            display: "flex", alignItems: "center", gap: 8, padding: "9px 14px",
            borderRadius: 10, fontSize: 13, cursor: "pointer", color: T.t2,
            background: "transparent", border: `1px solid ${T.border}`,
          }}>
          <RefreshCw size={15} /> Refresh
        </button>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 14, margin: "18px 0", flexWrap: "wrap" }}>
        <span style={{
          display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12,
          color: T.green, background: "var(--pu-1-17-38-04)", border: `1px solid ${T.border}`,
          padding: "5px 10px", borderRadius: 999,
        }}>
          <ShieldCheck size={14} /> {readyCount} ready to submit now
        </span>
        <span style={{ fontSize: 12, color: T.t3, fontFamily: F.mono }}>
          Credentialed: {(feed?.credentialed_ats || []).join(", ") || "none yet"}
        </span>
        {feed && !feed.live_submit_enabled && (
          <span style={{ fontSize: 12, color: T.warn }}>
            Live submission safety gate is off; preparation and review remain available.
          </span>
        )}
        <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13, color: T.t2, marginLeft: "auto", cursor: "pointer" }}>
          <input type="checkbox" checked={readyOnly} onChange={(e) => setReadyOnly(e.target.checked)} />
          Ready-to-submit only
        </label>
      </div>

      {error && <p style={{ color: T.warn, fontSize: 13, marginBottom: 12 }}>{error}</p>}

      {jobs.length === 0 ? (
        <div style={{
          textAlign: "center", padding: 48, borderRadius: 16, color: T.t2,
          background: T.card, border: `1px solid ${T.border}`,
        }}>
          No API-apply positions in the current window. Try turning off the
          "ready-to-submit only" filter, or refresh.
        </div>
      ) : (
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))" }}>
          {jobs.map((job) => (
            <motion.div key={job.job_id}
              initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.15 }}
              style={{
                background: T.card, border: `1px solid ${T.border}`, borderRadius: 14,
                padding: 16, display: "flex", flexDirection: "column", gap: 10, minWidth: 0,
              }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 15, fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{job.title}</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: T.t2, marginTop: 3 }}>
                    <Building2 size={13} /> {job.company}
                  </div>
                  {job.location && (
                    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: T.t3, marginTop: 2 }}>
                      <MapPin size={12} /> {job.location}
                    </div>
                  )}
                </div>
                <span style={{
                  height: "fit-content", fontSize: 11, fontFamily: F.mono, padding: "3px 8px",
                  borderRadius: 999, color: job.one_click_ready ? T.green : T.t3,
                  border: `1px solid ${T.border}`, background: "var(--pu-1-17-38-04)", whiteSpace: "nowrap",
                }}>
                  {job.ats_type}
                </span>
              </div>

              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "auto" }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, color: job.one_click_ready ? T.green : T.t3 }}>
                  {job.one_click_ready ? <ShieldCheck size={13} /> : <Clock size={13} />}
                  {job.one_click_ready ? "One-click ready" : "Prepare & review"}
                </span>
                <button onClick={() => startApply(job)} disabled={busyId === job.job_id}
                  style={{
                    display: "flex", alignItems: "center", gap: 6, padding: "8px 14px",
                    borderRadius: 10, fontSize: 13, fontWeight: 600, color: "var(--pu-ffffff-t)", border: "none",
                    cursor: busyId === job.job_id ? "wait" : "pointer",
                    opacity: busyId === job.job_id ? 0.6 : 1, background: T.grad,
                  }}>
                  <Zap size={14} /> {job.one_click_ready ? "Apply" : "Prepare"}
                </button>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {review && (
        <ReviewBeforeSubmit
          application={review}
          onClose={() => setReview(null)}
          onApproved={() => { setReview(null); load(); }}
        />
      )}
    </div>
  );
}

export default OneClickApplyPage;
