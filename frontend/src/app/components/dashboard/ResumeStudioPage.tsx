/**
 * Resume Studio — optional in-app editor for manual tweaks.
 *
 * Edits the structured resume spec (the same shape the tailoring engine
 * produces) and renders it server-side to an ATS-safe PDF/DOCX for live
 * preview + download. The per-position auto-render still happens in the apply
 * pipeline; this page is for hand-adjusting a resume before applying.
 *
 * Original PlaceUp UI — no third-party editor code or branding.
 * Follows the app rules: react-router, motion/react, theme tokens only.
 */
import { useEffect, useMemo, useState } from "react";
import { Download, Eye, Loader2, Plus, Trash2, FileText } from "lucide-react";
import * as api from "../../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  text: "var(--pu-f1f5f9-t)",
  t2: "var(--pu-226-232-240-072)",
  t3: "var(--pu-148-163-184-075)",
  border: "var(--pu-148-163-184-008)",
  card: "var(--pu-15-30-55-055)",
  field: "var(--pu-1-17-38-05)",
  grad: "linear-gradient(135deg, var(--pu-2563eb), var(--pu-0ea5e9))",
  warn: "var(--pu-f59e0b)",
};

function b64ToBlobUrl(b64: string, mime: string): string {
  const bytes = atob(b64);
  const arr = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
  return URL.createObjectURL(new Blob([arr], { type: mime }));
}

const input = (extra: React.CSSProperties = {}): React.CSSProperties => ({
  background: T.field, border: `1px solid ${T.border}`, borderRadius: 8,
  padding: "8px 10px", color: T.text, fontSize: 13, fontFamily: F.sans, width: "100%", ...extra,
});
const label: React.CSSProperties = { fontSize: 12, color: T.t2, display: "block", marginBottom: 4 };
const sectionTitle: React.CSSProperties = { fontSize: 14, fontWeight: 700, margin: "18px 0 8px" };

export function ResumeStudioPage() {
  const [spec, setSpec] = useState<api.ResumeSpec>(() => api.emptyResumeSpec());
  const [contactText, setContactText] = useState("");
  const [cover, setCover] = useState("");
  const [rendering, setRendering] = useState(false);
  const [docs, setDocs] = useState<api.RenderedDocuments | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pdfUrl = useMemo(
    () => (docs?.resume_pdf ? b64ToBlobUrl(docs.resume_pdf, "application/pdf") : null),
    [docs],
  );

  useEffect(() => () => {
    if (pdfUrl) URL.revokeObjectURL(pdfUrl);
  }, [pdfUrl]);

  function patch(p: Partial<api.ResumeSpec>) { setSpec((s) => ({ ...s, ...p })); }

  async function renderNow() {
    setRendering(true);
    setError(null);
    try {
      const resume: api.ResumeSpec = {
        ...spec,
        contact: contactText.split(",").map((x) => x.trim()).filter(Boolean),
      };
      setDocs(await api.renderResumeDocuments(resume, cover));
    } catch (e: any) {
      setError(e?.message || "Could not render documents.");
    } finally {
      setRendering(false);
    }
  }

  function download(b64: string | undefined, mime: string, filename: string) {
    if (!b64) return;
    const a = document.createElement("a");
    a.href = b64ToBlobUrl(b64, mime);
    a.download = filename;
    a.click();
  }

  // ── skills / experience helpers ──
  const addSkill = () => patch({ skills: [...spec.skills, { category: "", items: [] }] });
  const addExp = () => patch({ experience: [...spec.experience, { title: "", company: "", dates: "", bullets: [""] }] });

  return (
    <div style={{ maxWidth: 1280, margin: "0 auto", fontFamily: F.sans, color: T.text }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <FileText size={22} style={{ color: "var(--pu-0ea5e9)" }} />
        <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0 }}>Resume Studio</h1>
      </div>
      <p style={{ fontSize: 14, color: T.t2, margin: "8px 0 18px", maxWidth: 760 }}>
        Hand-tweak a resume and render it to an ATS-safe PDF/DOCX. Every application
        also gets a freshly tailored resume automatically — this is for manual edits.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)", gap: 18 }}>
        {/* Editor */}
        <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 14, padding: 18 }}>
          <label style={label}>Full name</label>
          <input style={input()} value={spec.name} onChange={(e) => patch({ name: e.target.value })} />

          <label style={{ ...label, marginTop: 12 }}>Contact (comma-separated: email, phone, city, LinkedIn)</label>
          <input style={input()} value={contactText} onChange={(e) => setContactText(e.target.value)} />

          <label style={{ ...label, marginTop: 12 }}>Summary</label>
          <textarea style={input({ minHeight: 70, resize: "vertical" })} value={spec.summary}
            onChange={(e) => patch({ summary: e.target.value })} />

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={sectionTitle}>Core Skills</div>
            <button onClick={addSkill} style={miniBtn}><Plus size={13} /> Add group</button>
          </div>
          {spec.skills.map((g, i) => (
            <div key={i} style={{ display: "flex", gap: 8, marginBottom: 8 }}>
              <input style={input({ flex: "0 0 40%" })} placeholder="Category" value={g.category}
                onChange={(e) => { const s = [...spec.skills]; s[i] = { ...g, category: e.target.value }; patch({ skills: s }); }} />
              <input style={input()} placeholder="Comma-separated skills" value={g.items.join(", ")}
                onChange={(e) => { const s = [...spec.skills]; s[i] = { ...g, items: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) }; patch({ skills: s }); }} />
              <button onClick={() => patch({ skills: spec.skills.filter((_, j) => j !== i) })} style={iconBtn}><Trash2 size={14} /></button>
            </div>
          ))}

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={sectionTitle}>Experience</div>
            <button onClick={addExp} style={miniBtn}><Plus size={13} /> Add role</button>
          </div>
          {spec.experience.map((x, i) => (
            <div key={i} style={{ border: `1px solid ${T.border}`, borderRadius: 10, padding: 10, marginBottom: 10 }}>
              <div style={{ display: "flex", gap: 8, marginBottom: 6 }}>
                <input style={input()} placeholder="Title" value={x.title}
                  onChange={(e) => { const s = [...spec.experience]; s[i] = { ...x, title: e.target.value }; patch({ experience: s }); }} />
                <input style={input()} placeholder="Company" value={x.company}
                  onChange={(e) => { const s = [...spec.experience]; s[i] = { ...x, company: e.target.value }; patch({ experience: s }); }} />
              </div>
              <div style={{ display: "flex", gap: 8, marginBottom: 6 }}>
                <input style={input()} placeholder="Dates (Mon YYYY - Present)" value={x.dates || ""}
                  onChange={(e) => { const s = [...spec.experience]; s[i] = { ...x, dates: e.target.value }; patch({ experience: s }); }} />
                <input style={input()} placeholder="Location" value={x.location || ""}
                  onChange={(e) => { const s = [...spec.experience]; s[i] = { ...x, location: e.target.value }; patch({ experience: s }); }} />
                <button onClick={() => patch({ experience: spec.experience.filter((_, j) => j !== i) })} style={iconBtn}><Trash2 size={14} /></button>
              </div>
              <textarea style={input({ minHeight: 70, resize: "vertical" })}
                placeholder="One bullet per line" value={x.bullets.join("\n")}
                onChange={(e) => { const s = [...spec.experience]; s[i] = { ...x, bullets: e.target.value.split("\n").map((b) => b.trim()).filter(Boolean) }; patch({ experience: s }); }} />
            </div>
          ))}

          <div style={sectionTitle}>Education (one per line: Degree — Institution — Dates)</div>
          <textarea style={input({ minHeight: 54, resize: "vertical" })}
            value={spec.education.map((e) => [e.degree, e.institution, e.dates].filter(Boolean).join(" — ")).join("\n")}
            onChange={(e) => patch({ education: e.target.value.split("\n").filter(Boolean).map((line) => {
              const [degree, institution, dates] = line.split("—").map((x) => x.trim());
              return { degree: degree || "", institution, dates };
            }) })} />

          <div style={sectionTitle}>Certifications (one per line)</div>
          <textarea style={input({ minHeight: 44, resize: "vertical" })} value={spec.certifications.join("\n")}
            onChange={(e) => patch({ certifications: e.target.value.split("\n").map((x) => x.trim()).filter(Boolean) })} />

          <div style={sectionTitle}>Projects (one per line)</div>
          <textarea style={input({ minHeight: 44, resize: "vertical" })} value={spec.projects.join("\n")}
            onChange={(e) => patch({ projects: e.target.value.split("\n").map((x) => x.trim()).filter(Boolean) })} />

          <div style={sectionTitle}>Cover letter (optional)</div>
          <textarea style={input({ minHeight: 90, resize: "vertical" })} value={cover}
            onChange={(e) => setCover(e.target.value)} placeholder="Leave blank to skip. Blank line between paragraphs." />
        </div>

        {/* Preview + actions */}
        <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 14, padding: 18, display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button onClick={renderNow} disabled={rendering}
              style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 16px", borderRadius: 10, fontSize: 14, fontWeight: 600, color: "var(--pu-ffffff-t)", border: "none", background: T.grad, cursor: rendering ? "wait" : "pointer" }}>
              {rendering ? <Loader2 size={16} className="animate-spin" /> : <Eye size={16} />} Preview
            </button>
            <button onClick={() => download(docs?.resume_pdf, "application/pdf", "resume.pdf")} disabled={!docs?.resume_pdf} style={outlineBtn(!docs?.resume_pdf)}>
              <Download size={15} /> PDF
            </button>
            <button onClick={() => download(docs?.resume_docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "resume.docx")} disabled={!docs?.resume_docx} style={outlineBtn(!docs?.resume_docx)}>
              <Download size={15} /> DOCX
            </button>
            {docs?.cover_letter_pdf && (
              <button onClick={() => download(docs?.cover_letter_pdf, "application/pdf", "cover-letter.pdf")} style={outlineBtn(false)}>
                <Download size={15} /> Cover letter
              </button>
            )}
          </div>
          {error && <p style={{ color: T.warn, fontSize: 13 }}>{error}</p>}
          <div style={{ flex: 1, minHeight: 520, border: `1px solid ${T.border}`, borderRadius: 10, overflow: "hidden", background: "var(--pu-1-17-38-04)" }}>
            {pdfUrl ? (
              <iframe title="Resume preview" src={pdfUrl} style={{ width: "100%", height: "100%", minHeight: 520, border: "none" }} />
            ) : (
              <div style={{ height: "100%", minHeight: 520, display: "flex", alignItems: "center", justifyContent: "center", color: T.t3, fontSize: 13, padding: 24, textAlign: "center" }}>
                Fill in the resume and press Preview to render an ATS-safe PDF.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

const miniBtn: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, color: T.t2,
  background: "transparent", border: `1px solid ${T.border}`, borderRadius: 8, padding: "4px 8px", cursor: "pointer",
};
const iconBtn: React.CSSProperties = {
  flex: "0 0 auto", background: "transparent", border: `1px solid ${T.border}`, borderRadius: 8,
  color: T.t3, cursor: "pointer", padding: "0 8px",
};
function outlineBtn(disabled: boolean): React.CSSProperties {
  return {
    display: "flex", alignItems: "center", gap: 6, padding: "9px 14px", borderRadius: 10, fontSize: 13,
    color: T.t2, background: "transparent", border: `1px solid ${T.border}`,
    opacity: disabled ? 0.4 : 1, cursor: disabled ? "not-allowed" : "pointer",
  };
}

export default ResumeStudioPage;
