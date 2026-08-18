/**
 * Review-before-submit modal — the non-optional human gate from the
 * automated application architecture (doc section J).
 *
 * Given an application in `needs_review`, this shows the EXACT payload the
 * adapter will submit (or the browser screenshot), lets the user edit any
 * mapped field, surfaces EEO/voluntary questions last, flags anything the
 * system could not fill, and only enables Approve once the user ticks the
 * explicit confirmation. Approve calls `approveApplication(..., {confirm:true})`.
 *
 * Follows the app rules: react-router, motion/react, theme tokens only.
 */
import { useMemo, useState } from "react";
import { motion } from "motion/react";
import { AlertTriangle, CheckCircle2, Download, FileText, Loader2, ShieldCheck, X } from "lucide-react";
import * as api from "../../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  text: "var(--pu-f1f5f9-t)",
  t2: "var(--pu-226-232-240-072)",
  t3: "var(--pu-148-163-184-075)",
  border: "var(--pu-148-163-184-008)",
  glass: "var(--pu-15-30-55-055)",
  grad: "linear-gradient(135deg, var(--pu-2563eb), var(--pu-0ea5e9))",
  warn: "var(--pu-f59e0b)",
};

interface Props {
  application: api.ApplicationRecord;
  onClose: () => void;
  onApproved?: (updated: api.ApplicationRecord) => void;
}

export function ReviewBeforeSubmit({ application, onClose, onApproved }: Props) {
  const [current, setCurrent] = useState(application);
  const payload = (application.prepared_payload || {}) as Record<string, any>;
  const initialFields = (payload.fields || {}) as Record<string, string>;
  const eeoFields = (payload.eeo_fields || {}) as Record<string, string>;
  const missing = (payload.missing_required || []) as string[];
  const notes = (payload.notes || []) as string[];
  const attachments = (payload.attachments || {}) as Record<string, string>;

  const [fields, setFields] = useState<Record<string, string>>({ ...initialFields });
  const [confirmed, setConfirmed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const unresolved = useMemo(
    () => missing.filter((m) => !(fields[m] && String(fields[m]).trim())),
    [missing, fields],
  );

  const isBrowser = current.submission_method === "browser";
  const missingResume = !isBrowser && !attachments.resume;
  const canApprove = confirmed && unresolved.length === 0 && !missingResume && !submitting;

  async function openDocument(kind: "resume" | "cover_letter", format: "pdf" | "docx") {
    try {
      const { blob, filename } = await api.getApplicationDocument(current.id, kind, format);
      const url = URL.createObjectURL(blob);
      if (format === "pdf") window.open(url, "_blank", "noopener,noreferrer");
      else {
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        link.click();
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (e: any) {
      setError(e?.message || "Document is not available yet.");
    }
  }

  async function approve() {
    if (!canApprove) return;
    setSubmitting(true);
    setError(null);
    try {
      const answers: Record<string, string> = {};
      for (const [k, v] of Object.entries(fields)) {
        if (v !== initialFields[k]) answers[k] = v;
      }
      const updated = await api.approveApplication(application.id, { confirm: true, answers });
      setCurrent(updated);
      onApproved?.(updated);
      let latest = updated;
      for (let attempt = 0; attempt < 20 && ["queued", "in_flight"].includes(latest.status); attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        latest = await api.getApplication(application.id);
        setCurrent(latest);
        onApproved?.(latest);
      }
    } catch (e: any) {
      setError(e?.message || "Could not submit for approval.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 60, display: "flex",
        alignItems: "center", justifyContent: "center", padding: 20,
        background: "var(--pu-0-0-0-05)", backdropFilter: "blur(4px)",
      }}
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, y: 16, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.18 }}
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(720px, 100%)", maxHeight: "88vh", overflow: "auto",
          background: T.glass, border: `1px solid ${T.border}`, borderRadius: 18,
          padding: 24, fontFamily: F.sans, color: T.text,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <ShieldCheck size={18} style={{ color: "var(--pu-0ea5e9)" }} />
              <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>
                Step 2 of 2 · Review & auto-apply
              </h2>
            </div>
            <p style={{ fontSize: 12, color: T.t3, margin: "4px 0 0" }}>
              Step 1 tailored your resume and cover letter for this position. Approving below
              submits the application on your behalf using these documents.
            </p>
            <p style={{ fontSize: 13, color: T.t2, margin: "6px 0 0" }}>
              {application.title} · {application.company} ·{" "}
              <span style={{ fontFamily: F.mono }}>Tier {application.tier}</span>{" "}
              ({isBrowser ? "browser" : "API"} submission)
            </p>
          </div>
          <button onClick={onClose} aria-label="Close"
            style={{ background: "transparent", border: "none", color: T.t3, cursor: "pointer" }}>
            <X size={20} />
          </button>
        </div>

        <div style={{ marginTop: 16, display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 10 }}>
          {(["resume", "cover_letter"] as const).map((kind) => (
            <div key={kind} style={{ padding: 12, borderRadius: 12, border: `1px solid ${T.border}`, background: "var(--pu-1-17-38-04)", display: "grid", gap: 9 }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <FileText size={16} style={{ color: "var(--pu-60a5fa-t)" }} />
                <div>
                  <div style={{ fontSize: 13, fontWeight: 750 }}>{kind === "resume" ? "Tailored resume" : "Cover letter"}</div>
                  <div style={{ fontSize: 11, color: T.t3 }}>Private · generated for this position</div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 7 }}>
                <button type="button" onClick={() => openDocument(kind, "pdf")} style={{ flex: 1, padding: "7px 9px", borderRadius: 8, border: `1px solid ${T.border}`, background: "transparent", color: T.t2, cursor: "pointer", fontSize: 11 }}>Preview PDF</button>
                <button type="button" onClick={() => openDocument(kind, "docx")} style={{ width: 36, borderRadius: 8, border: `1px solid ${T.border}`, background: "transparent", color: T.t2, cursor: "pointer" }} title="Download DOCX"><Download size={13} /></button>
              </div>
            </div>
          ))}
        </div>

        {current.status !== "needs_review" && (
          <div style={{ marginTop: 14, padding: 13, borderRadius: 11, border: `1px solid ${current.status === "applied" ? "var(--pu-34-197-94-035)" : T.border}`, background: current.status === "applied" ? "var(--pu-34-197-94-01)" : "var(--pu-1-17-38-04)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 750, fontSize: 13 }}>
              {["queued", "in_flight"].includes(current.status) ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
              {current.status === "applied" ? "Application submitted successfully" : current.status === "needs_you" ? "Your action is required" : current.status === "failed" ? "Submission failed" : "Submission in progress"}
            </div>
            {current.confirmation_ref && <div style={{ marginTop: 6, fontSize: 12, color: T.t2, fontFamily: F.mono }}>ATS confirmation: {current.confirmation_ref}</div>}
            {current.status === "applied" && <div style={{ marginTop: 4, fontSize: 11, color: T.t3 }}>{current.confirmation_email_sent ? "A PlaceUp receipt was emailed to you." : "Saved in Applications. Employer email is controlled by the ATS."}</div>}
            {current.error && <div style={{ marginTop: 6, fontSize: 12, color: T.warn }}>{current.error}</div>}
          </div>
        )}

        {isBrowser ? (
          <div style={{ marginTop: 18 }}>
            {application.confirmation_screenshot_url ? (
              <img src={application.confirmation_screenshot_url} alt="Form preview"
                style={{ width: "100%", borderRadius: 12, border: `1px solid ${T.border}` }} />
            ) : (
              <div style={{
                marginTop: 8, padding: 14, borderRadius: 12, fontSize: 13,
                color: T.t2, background: "var(--pu-1-17-38-04)", border: `1px solid ${T.border}`,
              }}>
                This ATS is web-form only. On approval the assistant fills the form up to
                the submit button and hands control to you for any CAPTCHA, OTP, or bot-check —
                it never bypasses a security control.
              </div>
            )}
            {Object.keys(fields).length > 0 && (
              <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
                <p style={{ fontSize: 12, color: T.t3, margin: 0 }}>
                  These answers from your profile will be typed into the form — edit anything before approving:
                </p>
                {Object.keys(fields).map((k) => (
                  <label key={k} style={{ display: "grid", gap: 4 }}>
                    <span style={{ fontSize: 12, color: T.t2 }}>{k}</span>
                    <input
                      value={fields[k] ?? ""}
                      onChange={(e) => setFields((f) => ({ ...f, [k]: e.target.value }))}
                      style={{
                        background: "var(--pu-1-17-38-05)", border: `1px solid ${T.border}`,
                        borderRadius: 8, padding: "8px 10px", color: T.text, fontSize: 13,
                        fontFamily: F.sans,
                      }}
                    />
                  </label>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div style={{ marginTop: 18 }}>
            <p style={{ fontSize: 12, color: T.t3, margin: "0 0 6px", fontFamily: F.mono }}>
              {String(payload.endpoint || "")}
            </p>
            <div style={{ display: "grid", gap: 10 }}>
              {Object.keys(fields).map((k) => (
                <label key={k} style={{ display: "grid", gap: 4 }}>
                  <span style={{ fontSize: 12, color: T.t2 }}>{k}</span>
                  <input
                    value={fields[k] ?? ""}
                    onChange={(e) => setFields((f) => ({ ...f, [k]: e.target.value }))}
                    style={{
                      background: "var(--pu-1-17-38-05)", border: `1px solid ${T.border}`,
                      borderRadius: 8, padding: "8px 10px", color: T.text, fontSize: 13,
                      fontFamily: F.sans,
                    }}
                  />
                </label>
              ))}
            </div>

            {Object.keys(eeoFields).length > 0 && (
              <div style={{ marginTop: 14 }}>
                <p style={{ fontSize: 12, color: T.t3, margin: "0 0 6px" }}>
                  Voluntary self-identification (optional, shown last)
                </p>
                <div style={{ display: "grid", gap: 6 }}>
                  {Object.entries(eeoFields).map(([k, v]) => (
                    <div key={k} style={{ fontSize: 12, color: T.t2 }}>
                      {k}: <span style={{ color: T.text }}>{String(v)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {unresolved.length > 0 && (
          <div style={{
            marginTop: 14, padding: 12, borderRadius: 10, fontSize: 13,
            display: "flex", gap: 8, alignItems: "flex-start",
            color: T.warn, background: "var(--pu-1-17-38-04)", border: `1px solid ${T.border}`,
          }}>
            <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
            <span>Fill these required fields before approving: {unresolved.join(", ")}</span>
          </div>
        )}

        {missingResume && (
          <div style={{ marginTop: 14, padding: 12, borderRadius: 10, fontSize: 13, color: T.warn, background: "var(--pu-1-17-38-04)", border: `1px solid ${T.border}` }}>
            A submission-ready resume file is not available yet. Upload or activate a resume before approving this application.
          </div>
        )}

        {notes.map((n, i) => (
          <p key={i} style={{ fontSize: 12, color: T.t3, margin: "8px 0 0" }}>• {n}</p>
        ))}

        {current.status === "needs_review" && <label style={{ display: "flex", gap: 8, alignItems: "flex-start", marginTop: 18, cursor: "pointer" }}>
          <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)}
            style={{ marginTop: 3 }} />
          <span style={{ fontSize: 13, color: T.t2 }}>
            I have reviewed the answers above and authorize PlaceUp to submit this application
            on my behalf. All answers (work authorization, EEO) are accurate.
          </span>
        </label>}

        {error && <p style={{ color: T.warn, fontSize: 13, marginTop: 10 }}>{error}</p>}

        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 18 }}>
          <button onClick={onClose}
            style={{
              padding: "9px 16px", borderRadius: 10, fontSize: 14, cursor: "pointer",
              background: "transparent", color: T.t2, border: `1px solid ${T.border}`,
            }}>
            Cancel
          </button>
          {current.status === "needs_review" && <button onClick={approve} disabled={!canApprove}
            style={{
              padding: "9px 18px", borderRadius: 10, fontSize: 14, fontWeight: 600,
              cursor: canApprove ? "pointer" : "not-allowed",
              opacity: canApprove ? 1 : 0.5, color: "#fff", border: "none", background: T.grad,
              display: "flex", alignItems: "center", gap: 8,
            }}>
            {submitting ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
            {isBrowser ? "Approve & continue" : "Approve & Auto-Apply"}
          </button>}
        </div>
      </motion.div>
    </div>
  );
}

export default ReviewBeforeSubmit;
