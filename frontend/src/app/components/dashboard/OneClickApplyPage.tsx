/**
 * One-Click Apply — personalized positions sourced from direct ATS boards.
 *
 * A job is "ready" when PlaceUp holds a submit credential for its ATS (an open
 * API like Recruitee, or an approved partner token). Ready jobs submit through
 * the official API after the review-before-submit gate — no CAPTCHA, no browser
 * automation. Jobs whose ATS isn't credentialed yet are shown as "Prepare"
 * (they still tailor + review, but can't auto-submit until the credential is
 * added). All other direct ATS roles can still be tailored and prepared.
 *
 * Follows the app rules: react-router, motion/react, theme tokens only.
 */
import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import { Link, useNavigate } from "react-router";
import { Zap, ShieldCheck, Clock, RefreshCw, Building2, MapPin, FileText, CalendarDays } from "lucide-react";
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
  const navigate = useNavigate();
  const [feed, setFeed] = useState<api.OneClickFeed | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [readyOnly, setReadyOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [review, setReview] = useState<api.ApplicationRecord | null>(null);
  const [applications, setApplications] = useState<Record<string, api.ApplicationRecord>>({});

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [nextFeed, appRows] = await Promise.all([
        api.getOneClickJobs({ page, page_size: 40, ready_only: readyOnly }),
        api.listApplications().catch(() => [] as api.ApplicationRecord[]),
      ]);
      setFeed(nextFeed);
      setApplications(Object.fromEntries((appRows || []).map((app) => [String(app.job_id), app])));
    } catch (e: any) {
      setError(e?.message || "Could not load One-Click positions.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [readyOnly, page]);

  const jobs = feed?.jobs || [];
  const readyCount = feed?.ready_total ?? jobs.filter((j) => j.one_click_ready).length;
  // Elite users get automated submission; Pro users see every position and
  // can tailor + prepare, then apply themselves.
  const oneClickAllowed = feed?.one_click_allowed !== false;
  const pageNumbers = useMemo(() => {
    const pages = feed?.total_pages || 1;
    const start = Math.max(1, Math.min(page - 2, pages - 4));
    return Array.from({ length: Math.min(5, pages) }, (_, index) => start + index);
  }, [feed?.total_pages, page]);

  const formatPosted = (value?: string) => {
    if (!value) return "Date unavailable";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Date unavailable";
    return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(date);
  };

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
          <p style={{ fontSize: 14, color: T.t2, margin: "8px 0 0", maxWidth: 760 }}>
            Your saved-role matches from direct ATS platforms, ranked by resume match score.
            Open any position to review its complete JD, then tailor your resume and cover letter
            before the review-and-submit step.
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
          <ShieldCheck size={14} /> {readyCount.toLocaleString()} ready to submit now
        </span>
        <span style={{ fontSize: 12, color: T.t2 }}>
          {(feed?.total || 0).toLocaleString()} relevant ATS roles
          {feed?.target_country ? ` in ${feed.target_country}` : ""} · latest {feed?.window_days || 30} days
        </span>
        <span style={{ fontSize: 12, color: T.t3, fontFamily: F.mono }}>
          Credentialed: {(feed?.credentialed_ats || []).join(", ") || "none yet"}
        </span>
        {feed && !feed.live_submit_enabled && (
          <span style={{ fontSize: 12, color: T.warn }}>
            Live submission safety gate is off; preparation and review remain available.
          </span>
        )}
        {feed && !oneClickAllowed && (
          <span style={{ fontSize: 12, color: T.warn }}>
            One-click submission is an Elite feature. You can still tailor, prepare, and apply yourself —{" "}
            <Link to="/dashboard/settings" style={{ color: "var(--pu-60a5fa-t)" }}>upgrade to Elite</Link> for automated submission.
          </span>
        )}
        <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13, color: T.t2, marginLeft: "auto", cursor: "pointer" }}>
          <input type="checkbox" checked={readyOnly} onChange={(e) => { setReadyOnly(e.target.checked); setPage(1); }} />
          Ready-to-submit only
        </label>
        <Link to="/dashboard/applications" style={{ fontSize: 12, color: "var(--pu-60a5fa-t)", textDecoration: "none" }}>View submission tracker →</Link>
      </div>

      {error && <p style={{ color: T.warn, fontSize: 13, marginBottom: 12 }}>{error}</p>}

      {jobs.length === 0 ? (
        <div style={{
          textAlign: "center", padding: 48, borderRadius: 16, color: T.t2,
          background: T.card, border: `1px solid ${T.border}`,
        }}>
          No recently verified direct ATS positions match your saved roles and target country in this window.
          Try turning off the "ready-to-submit only" filter, or update your saved roles.
        </div>
      ) : (
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))" }}>
          {jobs.map((job) => (
            <motion.div key={job.job_id}
              initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.15 }}
              role="button" tabIndex={0}
              onClick={() => navigate(`/dashboard/jobs/${job.job_id}`)}
              onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") navigate(`/dashboard/jobs/${job.job_id}`); }}
              style={{
                background: T.card, border: `1px solid ${T.border}`, borderRadius: 14,
                padding: 16, display: "flex", flexDirection: "column", gap: 10, minWidth: 0, cursor: "pointer",
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
                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
                  <span style={{ fontSize: 22, fontWeight: 850, lineHeight: 1, color: job.match_score >= 70 ? T.green : job.match_score >= 50 ? T.warn : T.t2 }}>
                    {job.match_score}%
                  </span>
                  <span style={{ fontSize: 10, color: T.t3 }}>resume match</span>
                  <span style={{
                    height: "fit-content", fontSize: 11, fontFamily: F.mono, padding: "3px 8px",
                    borderRadius: 999, color: job.one_click_ready ? T.green : T.t3,
                    border: `1px solid ${T.border}`, background: "var(--pu-1-17-38-04)", whiteSpace: "nowrap",
                  }}>
                    {job.ats_type}
                  </span>
                </div>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", fontSize: 11, color: T.t3 }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><CalendarDays size={12} /> Posted {formatPosted(job.posted_at)}</span>
                <span>Direct source: {job.source || job.ats_type}</span>
                {applications[job.job_id] && (
                  <span style={{ color: applications[job.job_id].status === "applied" ? T.green : T.warn, fontWeight: 750 }}>
                    Status: {applications[job.job_id].status.replaceAll("_", " ")}
                    {applications[job.job_id].confirmation_ref ? ` · ${applications[job.job_id].confirmation_ref}` : ""}
                  </span>
                )}
              </div>

              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginTop: "auto", flexWrap: "wrap" }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, color: job.one_click_ready ? T.green : T.t3 }}>
                  {job.one_click_ready ? <ShieldCheck size={13} /> : <Clock size={13} />}
                  {job.one_click_ready ? "One-click ready" : "Prepare & review"}
                </span>
                <div style={{ display: "flex", gap: 7, marginLeft: "auto" }}>
                <button onClick={(event) => { event.stopPropagation(); navigate(`/dashboard/jobs/${job.job_id}`); }}
                  style={{
                    display: "flex", alignItems: "center", gap: 6, padding: "8px 12px",
                    borderRadius: 10, fontSize: 12, fontWeight: 650, color: T.t2,
                    border: `1px solid ${T.border}`, cursor: "pointer", background: "transparent",
                  }}>
                  <FileText size={14} /> View full JD
                </button>
                <button onClick={(event) => { event.stopPropagation(); startApply(job); }} disabled={busyId === job.job_id}
                  style={{
                    display: "flex", alignItems: "center", gap: 6, padding: "8px 14px",
                    borderRadius: 10, fontSize: 13, fontWeight: 600, color: "var(--pu-ffffff-t)", border: "none",
                    cursor: busyId === job.job_id ? "wait" : "pointer",
                    opacity: busyId === job.job_id ? 0.6 : 1, background: T.grad,
                  }}>
                  <Zap size={14} /> {busyId === job.job_id ? "Tailoring..." : job.one_click_ready && oneClickAllowed ? "Tailor & Apply" : "Tailor & Prepare"}
                </button>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {(feed?.total_pages || 1) > 1 && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 7, marginTop: 18, flexWrap: "wrap" }}>
          <button disabled={page <= 1 || loading} onClick={() => setPage((value) => Math.max(1, value - 1))}
            style={{ padding: "8px 12px", borderRadius: 9, border: `1px solid ${T.border}`, background: "transparent", color: T.t2, cursor: page <= 1 ? "default" : "pointer", opacity: page <= 1 ? 0.45 : 1 }}>Previous</button>
          {pageNumbers.map((pageNumber) => (
            <button key={pageNumber} onClick={() => setPage(pageNumber)}
              style={{ width: 34, height: 34, borderRadius: 9, border: `1px solid ${T.border}`, background: page === pageNumber ? T.grad : "transparent", color: page === pageNumber ? "var(--pu-ffffff-t)" : T.t2, cursor: "pointer" }}>{pageNumber}</button>
          ))}
          <button disabled={page >= (feed?.total_pages || 1) || loading} onClick={() => setPage((value) => Math.min(feed?.total_pages || 1, value + 1))}
            style={{ padding: "8px 12px", borderRadius: 9, border: `1px solid ${T.border}`, background: "transparent", color: T.t2, cursor: page >= (feed?.total_pages || 1) ? "default" : "pointer", opacity: page >= (feed?.total_pages || 1) ? 0.45 : 1 }}>Next</button>
          <span style={{ fontSize: 12, color: T.t3, marginLeft: 4 }}>Page {feed?.page || page} of {feed?.total_pages || 1}</span>
        </div>
      )}

      {review && (
        <ReviewBeforeSubmit
          application={review}
          onClose={() => setReview(null)}
          onApproved={(updated) => { setReview(updated); }}
        />
      )}
    </div>
  );
}

export default OneClickApplyPage;
