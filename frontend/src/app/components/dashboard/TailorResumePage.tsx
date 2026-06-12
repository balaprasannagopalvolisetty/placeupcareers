import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import { Download, FileText, RefreshCw, Sparkles, Wand2 } from "lucide-react";
import * as api from "../../lib/api";
import { LoadingLogo } from "../LoadingLogo";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  text: "#F5EAC8",
  t2: "rgba(245,234,200,0.66)",
  t3: "rgba(245,234,200,0.45)",
  border: "rgba(245,234,200,0.10)",
  card: "rgba(64,18,18,0.45)",
  panel: "linear-gradient(135deg, rgba(1,17,38,0.90), rgba(64,18,18,0.55))",
  grad: "linear-gradient(135deg, #F2A341, #ED7D2B, #C75A12)",
  orange: "#ED7D2B",
  green: "#86EFAC",
};

function downloadBase64(payload: api.TailoredResumeDownload) {
  const binary = atob(payload.data_base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  const blob = new Blob([bytes], { type: payload.content_type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = payload.filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function dateLabel(value?: string) {
  if (!value) return "Queued recently";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Queued recently";
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function scoreColor(score?: number) {
  if (!score) return T.t3;
  if (score >= 95) return T.green;
  if (score >= 80) return "#F2A341";
  return "#F87171";
}

export function TailorResumePage() {
  const [queue, setQueue] = useState<api.TailorQueueResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");

  const loadQueue = () => {
    setLoading(true);
    setError("");
    api.getTailorQueue()
      .then(setQueue)
      .catch((err) => setError((err as Error)?.message || "Could not load tailor queue"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadQueue();
    const refresh = () => loadQueue();
    window.addEventListener("placeup:tailor-queue-changed", refresh as EventListener);
    return () => window.removeEventListener("placeup:tailor-queue-changed", refresh as EventListener);
  }, []);

  const items = queue?.items || [];
  const generatedCount = useMemo(() => items.filter((item) => item.status === "generated").length, [items]);

  const generate = async (item: api.TailorQueueItem, format: "doc" | "pdf") => {
    setBusyId(`${item.id}:${format}`);
    setError("");
    try {
      const payload = await api.generateTailoredResume(item.id, format);
      downloadBase64(payload);
      await api.getTailorQueue().then(setQueue);
    } catch (err) {
      setError((err as Error)?.message || "Could not generate tailored resume");
    } finally {
      setBusyId("");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18, width: "100%" }}>
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        style={{
          padding: 22,
          borderRadius: 18,
          border: `1px solid ${T.border}`,
          background: T.panel,
          boxShadow: "0 18px 44px rgba(1,17,38,0.28)",
          color: T.text,
        }}
      >
        <div style={{ display: "flex", gap: 14, alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap" }}>
          <div style={{ display: "flex", gap: 13, alignItems: "center", minWidth: 0 }}>
            <div style={{ width: 44, height: 44, borderRadius: 13, background: T.grad, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <Wand2 size={20} color="#fff" />
            </div>
            <div style={{ minWidth: 0 }}>
              <h2 style={{ fontFamily: F.sans, fontSize: 22, fontWeight: 850, lineHeight: 1.15, margin: 0 }}>Resume Tailor Queue</h2>
              <p style={{ fontSize: 13, color: T.t2, lineHeight: 1.55, margin: "6px 0 0" }}>
                Add jobs from the Jobs page, then generate a targeted DOC or PDF version from your active resume.
              </p>
            </div>
          </div>
          <button
            onClick={loadQueue}
            style={{ height: 36, padding: "0 12px", borderRadius: 9, border: `1px solid ${T.border}`, background: "rgba(245,234,200,0.05)", color: T.text, display: "flex", alignItems: "center", gap: 7, cursor: "pointer", fontSize: 12, fontWeight: 800, fontFamily: F.sans }}
          >
            <RefreshCw size={13} /> Refresh
          </button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10, marginTop: 18 }}>
          {[
            { label: "Used today", value: `${queue?.used_today ?? 0}/${queue?.daily_limit ?? 25}` },
            { label: "Remaining", value: String(queue?.remaining_today ?? 25) },
            { label: "In queue", value: String(items.length) },
            { label: "Generated", value: String(generatedCount) },
          ].map((stat) => (
            <div key={stat.label} style={{ padding: 14, borderRadius: 13, background: "rgba(245,234,200,0.04)", border: `1px solid ${T.border}` }}>
              <div style={{ fontSize: 11, color: T.t3, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.08em" }}>{stat.label}</div>
              <div style={{ fontFamily: F.mono, fontSize: 26, fontWeight: 850, color: T.text, lineHeight: 1.1, marginTop: 5 }}>{stat.value}</div>
            </div>
          ))}
        </div>
      </motion.div>

      {error && (
        <div style={{ padding: "12px 14px", borderRadius: 12, border: "1px solid rgba(248,113,113,0.28)", background: "rgba(248,113,113,0.08)", color: "#FECACA", fontSize: 13 }}>
          {error}
        </div>
      )}

      {loading ? (
        <div style={{ borderRadius: 16, border: `1px solid ${T.border}`, background: T.card }}>
          <LoadingLogo label="Loading tailor queue" />
        </div>
      ) : items.length === 0 ? (
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          style={{ padding: 34, borderRadius: 18, border: `1px solid ${T.border}`, background: T.card, textAlign: "center", color: T.text }}
        >
          <Sparkles size={28} color={T.orange} />
          <div style={{ fontSize: 16, fontWeight: 850, marginTop: 10 }}>No jobs in the tailor queue yet</div>
          <div style={{ fontSize: 13, color: T.t2, lineHeight: 1.55, marginTop: 6 }}>
            Open Jobs and use the Tailor button on up to 25 positions per day.
          </div>
        </motion.div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: 12 }}>
          {items.map((item, index) => (
            <motion.div
              key={item.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.035 }}
              whileHover={{ y: -3 }}
              style={{ padding: 16, borderRadius: 16, border: `1px solid ${T.border}`, background: "linear-gradient(135deg, rgba(1,17,38,0.84), rgba(64,18,18,0.52))", boxShadow: "0 12px 28px rgba(1,17,38,0.24)", color: T.text }}
            >
              <div style={{ display: "flex", gap: 14, justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap" }}>
                <div style={{ display: "flex", gap: 12, minWidth: 0, flex: 1 }}>
                  <div style={{ width: 42, height: 42, borderRadius: 12, background: "rgba(237,125,43,0.13)", border: "1px solid rgba(237,125,43,0.26)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                    <FileText size={18} color={T.orange} />
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 15, fontWeight: 850, lineHeight: 1.3, marginBottom: 4 }}>{item.title || "Untitled role"}</div>
                    <div style={{ fontSize: 12, color: T.t2, lineHeight: 1.45 }}>
                      {item.company || "Unknown company"} - {item.location || "Remote"} - {dateLabel(item.created_at)}
                    </div>
                    <div style={{ display: "flex", gap: 7, flexWrap: "wrap", marginTop: 9 }}>
                      <span style={{ fontSize: 11, fontWeight: 800, padding: "4px 8px", borderRadius: 999, background: "rgba(237,125,43,0.12)", color: T.orange }}>
                        Current match {item.match_score || 0}%
                      </span>
                      <span style={{ fontSize: 11, fontWeight: 800, padding: "4px 8px", borderRadius: 999, background: "rgba(34,197,94,0.10)", color: scoreColor(item.ats_score) }}>
                        Tailored ATS {item.ats_score ? `${item.ats_score}%` : "Ready"}
                      </span>
                    </div>
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
                  <button
                    disabled={busyId === `${item.id}:doc`}
                    onClick={() => generate(item, "doc")}
                    style={{ height: 34, padding: "0 12px", borderRadius: 9, border: "none", background: T.grad, color: "#fff", display: "flex", alignItems: "center", gap: 7, cursor: busyId ? "wait" : "pointer", fontSize: 12, fontWeight: 850, fontFamily: F.sans }}
                  >
                    <Download size={13} /> DOC
                  </button>
                  <button
                    disabled={busyId === `${item.id}:pdf`}
                    onClick={() => generate(item, "pdf")}
                    style={{ height: 34, padding: "0 12px", borderRadius: 9, border: `1px solid ${T.border}`, background: "rgba(245,234,200,0.05)", color: T.text, display: "flex", alignItems: "center", gap: 7, cursor: busyId ? "wait" : "pointer", fontSize: 12, fontWeight: 850, fontFamily: F.sans }}
                  >
                    <Download size={13} /> PDF
                  </button>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}

export default TailorResumePage;
