import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { MessageSquarePlus, Star, X, Check } from "lucide-react";
import { useLocation } from "react-router";
import * as api from "../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif" };
const T = {
  surface: "var(--pu-ffffff-b)",
  border: "var(--pu-e2e8f0-b)",
  text: "var(--pu-0f172a-t)",
  t2: "var(--pu-475569-t)",
  t3: "var(--pu-94a3b8-t)",
  accent: "var(--pu-2563eb)",
  grad: "linear-gradient(135deg, var(--pu-2563eb), var(--pu-0ea5e9))",
  input: "var(--pu-f8fafc-b)",
};

const CATEGORIES: { value: string; label: string }[] = [
  { value: "general", label: "General" },
  { value: "bug", label: "Something's broken" },
  { value: "feature_request", label: "Feature idea" },
  { value: "job_quality", label: "Job match quality" },
  { value: "ux", label: "Design / usability" },
  { value: "pricing", label: "Pricing" },
];

/**
 * Floating feedback button + panel. Any signed-in user can rate their
 * experience and leave a comment; submissions flow to /api/feedback and show
 * up in the admin portal's Feedback tab.
 */
export default function FeedbackWidget() {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [rating, setRating] = useState(0);
  const [hover, setHover] = useState(0);
  const [category, setCategory] = useState("general");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setRating(0); setHover(0); setCategory("general"); setMessage(""); setError(null); setDone(false);
  };

  const submit = async () => {
    if (!rating) { setError("Please pick a star rating."); return; }
    setSubmitting(true);
    setError(null);
    try {
      await api.submitFeedback({ rating, category, message: message.trim(), page: location.pathname });
      setDone(true);
      setTimeout(() => { setOpen(false); reset(); }, 1600);
    } catch (err) {
      setError((err as Error).message || "Couldn't send feedback. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      {/* Launcher */}
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Send feedback"
        style={{
          position: "fixed", right: 20, bottom: 20, zIndex: 60,
          height: 48, padding: "0 16px", borderRadius: 999, border: "none",
          background: T.grad, color: "var(--pu-ffffff-t)", cursor: "pointer",
          display: "inline-flex", alignItems: "center", gap: 8,
          fontFamily: F.sans, fontSize: 13.5, fontWeight: 700,
          boxShadow: "0 8px 22px var(--pu-37-99-235-035)",
        }}
      >
        <MessageSquarePlus size={17} /> Feedback
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.98 }}
            transition={{ duration: 0.18 }}
            style={{
              position: "fixed", right: 20, bottom: 80, zIndex: 61, width: 340, maxWidth: "calc(100vw - 40px)",
              background: T.surface, border: `1px solid ${T.border}`, borderRadius: 18,
              boxShadow: "0 20px 50px var(--pu-15-23-42-022)", padding: 20, fontFamily: F.sans,
            }}
          >
            {done ? (
              <div style={{ textAlign: "center", padding: "18px 6px" }}>
                <span style={{ display: "inline-flex", width: 46, height: 46, borderRadius: 14, background: "var(--pu-22-163-74-01)", alignItems: "center", justifyContent: "center", marginBottom: 12 }}>
                  <Check size={22} color="var(--pu-16a34a)" />
                </span>
                <div style={{ fontSize: 16, fontWeight: 800, color: T.text, marginBottom: 4 }}>Thank you!</div>
                <div style={{ fontSize: 13, color: T.t2 }}>Your feedback helps us improve PlaceUp.</div>
              </div>
            ) : (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                  <div style={{ fontSize: 15.5, fontWeight: 800, color: T.text }}>Share your feedback</div>
                  <button onClick={() => setOpen(false)} style={{ background: "none", border: "none", cursor: "pointer", color: T.t3, padding: 2, display: "flex" }}><X size={18} /></button>
                </div>

                <div style={{ fontSize: 12.5, color: T.t2, marginBottom: 6 }}>How's your experience?</div>
                <div style={{ display: "flex", gap: 6, marginBottom: 16 }}>
                  {[1, 2, 3, 4, 5].map((n) => (
                    <button key={n} onMouseEnter={() => setHover(n)} onMouseLeave={() => setHover(0)} onClick={() => { setRating(n); setError(null); }}
                      style={{ background: "none", border: "none", cursor: "pointer", padding: 2, display: "flex" }}>
                      <Star size={28} color={(hover || rating) >= n ? "var(--pu-f59e0b-b)" : "var(--pu-cbd5e1-b)"} fill={(hover || rating) >= n ? "var(--pu-f59e0b-b)" : "none"} />
                    </button>
                  ))}
                </div>

                <div style={{ fontSize: 12.5, color: T.t2, marginBottom: 6 }}>What's it about?</div>
                <select value={category} onChange={(e) => setCategory(e.target.value)}
                  style={{ width: "100%", height: 42, padding: "0 12px", borderRadius: 10, border: `1px solid ${T.border}`, background: T.input, color: T.text, fontSize: 13.5, fontFamily: F.sans, marginBottom: 14, outline: "none" }}>
                  {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                </select>

                <textarea value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Tell us more (optional)…" rows={3}
                  style={{ width: "100%", padding: "10px 12px", borderRadius: 10, border: `1px solid ${T.border}`, background: T.input, color: T.text, fontSize: 13.5, fontFamily: F.sans, resize: "vertical", outline: "none", boxSizing: "border-box", marginBottom: 12 }} />

                {error && <div style={{ color: "var(--pu-dc2626)", fontSize: 12.5, marginBottom: 10 }}>{error}</div>}

                <button onClick={submit} disabled={submitting}
                  style={{ width: "100%", height: 44, borderRadius: 11, border: "none", background: T.grad, color: "var(--pu-ffffff-t)", fontSize: 14, fontWeight: 700, fontFamily: F.sans, cursor: submitting ? "wait" : "pointer", opacity: submitting ? 0.75 : 1 }}>
                  {submitting ? "Sending…" : "Send feedback"}
                </button>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
