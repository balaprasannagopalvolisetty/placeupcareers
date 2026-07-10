import { useEffect, useRef, useState } from "react";
import { LoadingLogo } from "../LoadingLogo";
import { motion } from "motion/react";
import { Upload, FileText, Trash2 } from "lucide-react";
import * as api from "../../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  text: "var(--pu-f1f5f9-t)", t2: "var(--pu-226-232-240-072)", t3: "var(--pu-148-163-184-075)",
  border: "var(--pu-148-163-184-008)", glass: "var(--pu-15-30-55-055)",
  grad: "linear-gradient(135deg, var(--pu-2563eb), var(--pu-0ea5e9))", red: "var(--pu-3b82f6-t)",
};

function ScoreRing({ score }: { score: number }) {
  const r = 28, circ = 2 * Math.PI * r;
  const color = score >= 80 ? T.red : score >= 60 ? "var(--pu-60a5fa-b)" : "var(--pu-1d4ed8)";
  return (
    <div style={{ position: "relative", width: 72, height: 72 }}>
      <svg viewBox="0 0 72 72" style={{ width: "100%", height: "100%", transform: "rotate(-90deg)" }}>
        <circle cx="36" cy="36" r={r} fill="none" stroke="var(--pu-148-163-184-007)" strokeWidth="6" />
        <motion.circle cx="36" cy="36" r={r} fill="none" stroke={color} strokeWidth="6" strokeLinecap="round"
          strokeDasharray={circ} initial={{ strokeDashoffset: circ }}
          animate={{ strokeDashoffset: circ * (1 - score / 100) }} transition={{ duration: 1.2, ease: "easeOut" }} />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span style={{ fontFamily: F.mono, fontSize: 16, fontWeight: 500, color }}>{score}</span>
      </div>
    </div>
  );
}

function humanizeDate(iso: string): string {
  try {
    const ts = new Date(iso);
    const diff = (Date.now() - ts.getTime()) / 1000;
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
    return ts.toLocaleDateString();
  } catch { return "recently"; }
}
function humanizeSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function notifyResumeChanged() {
  if (typeof window === "undefined") return;
  const version = String(Date.now());
  localStorage.setItem("placeup_resume_version", version);
  window.dispatchEvent(new CustomEvent("placeup:resume-changed", { detail: { version } }));
}

function withTimeout<T>(promise: Promise<T>, ms: number, fallback: T): Promise<T> {
  return new Promise((resolve) => {
    const timer = window.setTimeout(() => resolve(fallback), ms);
    promise.then(
      (value) => { window.clearTimeout(timer); resolve(value); },
      () => { window.clearTimeout(timer); resolve(fallback); },
    );
  });
}

export function ResumePage() {
  const [dragging, setDragging] = useState(false);
  const [resumes, setResumes] = useState<api.ResumeMetadata[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    withTimeout(api.getResumeList(), 8000, [])
      .then((list) => { if (active) setResumes(list); })
      .catch((err) => { if (active) setUploadError((err as Error).message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const handleFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    if (resumes.length >= 5) {
      setUploadError("Resume limit reached. Delete an old resume before uploading another.");
      return;
    }
    setUploadError(null);
    setUploading(true);
    try {
      const uploaded = await api.uploadResume(files[0]);
      setResumes((current) => [
        uploaded,
        ...current
          .map((resume) => ({ ...resume, active: false }))
          .filter((resume) => resume.id !== uploaded.id),
      ]);
      notifyResumeChanged();
    } catch (error) {
      setUploadError((error as Error).message || "Failed to upload resume.");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const setActive = async (id: string) => {
    try {
      const updated = await api.setActiveResume(id);
      setResumes((rs) => rs.map((r) => ({ ...r, active: r.id === updated.id })));
      notifyResumeChanged();
    } catch (e) {
      setUploadError((e as Error).message);
    }
  };

  const remove = async (id: string) => {
    const previous = resumes;
    setResumes((rs) => rs.filter((r) => r.id !== id));
    try {
      await api.deleteResume(id);
      notifyResumeChanged();
    } catch (e) {
      setUploadError((e as Error).message);
      setResumes(previous);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files); }}
        style={{ padding: 36, borderRadius: 20, border: `2px dashed ${dragging ? T.red : "var(--pu-59-130-246-03)"}`, background: dragging ? "var(--pu-59-130-246-006)" : T.glass, backdropFilter: "blur(20px)", textAlign: "center", cursor: "pointer", transition: "all 0.2s" }}
      >
        <Upload size={32} color={T.red} style={{ margin: "0 auto 12px" }} />
        <div style={{ fontSize: 15, fontWeight: 500, color: T.text, fontFamily: F.sans, marginBottom: 6 }}>Drop your resume here or click to upload</div>
        <div style={{ fontSize: 13, color: T.t3, fontFamily: F.sans, marginBottom: 16 }}>PDF or DOCX · Max 10MB · 5 resume limit</div>
        <label style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "11px 22px", borderRadius: 10, background: T.grad, color: "var(--pu-ffffff-t)", fontSize: 13, fontWeight: 600, fontFamily: F.sans, cursor: "pointer", boxShadow: "0 0 20px var(--pu-59-130-246-03)" }}>
          <Upload size={14} /> {uploading ? "Uploading…" : "Choose File"}
          <input ref={inputRef} type="file" accept=".pdf,.docx" style={{ display: "none" }}
            onChange={(e) => handleFiles(e.target.files)} disabled={uploading} />
        </label>
        {uploadError ? <div style={{ marginTop: 12, color: T.red, fontSize: 13, fontFamily: F.sans }}>{uploadError}</div> : null}
      </div>

      <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, overflow: "hidden" }}>
        <div style={{ padding: "18px 24px", borderBottom: `1px solid ${T.border}`, display: "flex", justifyContent: "space-between" }}>
          <span style={{ fontFamily: F.sans, fontSize: 15, fontWeight: 600, color: T.text }}>Your Resumes ({resumes.length})</span>
          <span style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>Active version is matched against jobs</span>
        </div>
        {loading ? (
          <LoadingLogo label="Loading resumes" />
        ) : resumes.length === 0 ? (
          <div style={{ padding: 40, textAlign: "center", color: T.t3, fontFamily: F.sans }}>No resumes yet. Upload your first one above.</div>
        ) : (
          resumes.map((r, i) => (
            <motion.div key={r.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.07 }}
              style={{ padding: "18px 24px", borderBottom: i < resumes.length - 1 ? `1px solid ${T.border}` : "none", display: "flex", alignItems: "center", gap: 16 }}>
              <div style={{ width: 44, height: 44, borderRadius: 10, background: r.active ? "var(--pu-59-130-246-012)" : "var(--pu-148-163-184-004)", border: `1px solid ${r.active ? "var(--pu-59-130-246-03)" : T.border}`, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <FileText size={18} color={r.active ? T.red : T.t3} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: T.text, fontFamily: F.sans, marginBottom: 2 }}>{r.name}</div>
                <div style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>{humanizeSize(r.size_bytes)} · Uploaded {humanizeDate(r.uploaded_at)}</div>
              </div>
              <ScoreRing score={r.score} />
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                {r.active
                  ? <span style={{ fontSize: 11, fontWeight: 700, padding: "4px 10px", borderRadius: 9999, background: "var(--pu-59-130-246-012)", color: T.red, border: "1px solid var(--pu-59-130-246-025)", fontFamily: F.sans }}>Active</span>
                  : <button onClick={() => setActive(r.id)} style={{ padding: "6px 12px", borderRadius: 8, border: `1px solid ${T.border}`, background: "transparent", color: T.t2, fontSize: 12, fontFamily: F.sans, cursor: "pointer" }}>Set Active</button>
                }
                <button onClick={() => remove(r.id)} style={{ background: "none", border: "none", cursor: "pointer", color: T.t3 }}>
                  <Trash2 size={15} />
                </button>
              </div>
            </motion.div>
          ))
        )}
      </div>
    </div>
  );
}
