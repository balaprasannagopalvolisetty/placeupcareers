/**
 * RoleRequestPanel — lets a signed-in user ask PlaceUp to add coverage for a
 * role that isn't tracked yet. Requests go into the admin approval queue.
 */
import { useEffect, useState } from "react";
import { Plus, Check, Clock, X } from "lucide-react";
import * as api from "../../lib/api";

const F = "'Plus Jakarta Sans', sans-serif";
const T = {
  text: "var(--pu-f1f5f9-t)",
  t2: "var(--pu-226-232-240-072)",
  t3: "var(--pu-148-163-184-075)",
  border: "var(--pu-148-163-184-01)",
  input: "var(--pu-148-163-184-005)",
  red: "var(--pu-3b82f6-t)",
  grad: "linear-gradient(135deg, var(--pu-2563eb), var(--pu-0ea5e9))",
  panel: "var(--pu-1-17-38-055)",
};

function statusChip(status: string) {
  const map: Record<string, { bg: string; fg: string; icon: React.ReactNode; label: string }> = {
    pending: { bg: "var(--pu-59-130-246-012)", fg: T.red, icon: <Clock size={11} />, label: "Pending" },
    approved: { bg: "var(--pu-34-197-94-012)", fg: "var(--pu-22c55e-t)", icon: <Check size={11} />, label: "Approved" },
    rejected: { bg: "var(--pu-239-68-68-012)", fg: "var(--pu-f87171-t)", icon: <X size={11} />, label: "Rejected" },
  };
  const s = map[status] || map.pending;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 9999, background: s.bg, color: s.fg, fontFamily: F }}>
      {s.icon} {s.label}
    </span>
  );
}

export function RoleRequestPanel() {
  const [role, setRole] = useState("");
  const [country, setCountry] = useState("");
  const [note, setNote] = useState("");
  const [requests, setRequests] = useState<api.RoleRequest[]>([]);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [open, setOpen] = useState(false);

  const load = () => {
    api.getMyRoleRequests().then((r) => setRequests(r.requests || [])).catch(() => {});
  };
  useEffect(load, []);

  const submit = async () => {
    if (role.trim().length < 2) { setMsg({ kind: "err", text: "Enter the role you'd like us to add." }); return; }
    setLoading(true);
    setMsg(null);
    try {
      await api.createRoleRequest({ role: role.trim(), country: country.trim(), note: note.trim() });
      setRole(""); setCountry(""); setNote("");
      setMsg({ kind: "ok", text: "Request submitted — our team will review it shortly." });
      load();
    } catch (e) {
      setMsg({ kind: "err", text: (e as Error).message || "Could not submit request." });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ borderRadius: 16, border: `1px solid ${T.border}`, background: T.panel, padding: 18 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
        <div>
          <div style={{ fontFamily: F, fontSize: 15, fontWeight: 700, color: T.text }}>Can't find a role?</div>
          <div style={{ fontSize: 12, color: T.t2, fontFamily: F, marginTop: 2 }}>
            Request a role and our team will add it to coverage after review.
          </div>
        </div>
        <button type="button" onClick={() => setOpen((v) => !v)}
          style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "8px 14px", borderRadius: 10, border: "none", background: T.grad, color: "var(--pu-ffffff-t)", fontSize: 12, fontWeight: 600, fontFamily: F, cursor: "pointer", whiteSpace: "nowrap" }}>
          <Plus size={14} /> Request a role
        </button>
      </div>

      {open && (
        <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <div style={{ gridColumn: "1 / -1" }}>
            <input value={role} onChange={(e) => setRole(e.target.value)} placeholder="Role / position (e.g. Solutions Architect)"
              style={inputStyle} />
          </div>
          <input value={country} onChange={(e) => setCountry(e.target.value)} placeholder="Country (optional)" style={inputStyle} />
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Anything else? (optional)" style={inputStyle} />
          <div style={{ gridColumn: "1 / -1", display: "flex", gap: 8 }}>
            <button type="button" onClick={submit} disabled={loading}
              style={{ padding: "9px 16px", borderRadius: 10, border: "none", background: T.grad, color: "var(--pu-ffffff-t)", fontSize: 12, fontWeight: 600, fontFamily: F, cursor: loading ? "wait" : "pointer" }}>
              {loading ? "Submitting…" : "Submit request"}
            </button>
          </div>
        </div>
      )}

      {msg && (
        <div style={{ marginTop: 12, fontSize: 12, fontFamily: F, color: msg.kind === "ok" ? "var(--pu-22c55e-t)" : "var(--pu-f87171-t)" }}>{msg.text}</div>
      )}

      {requests.length > 0 && (
        <div style={{ marginTop: 16, borderTop: `1px solid ${T.border}`, paddingTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
          {requests.slice(0, 6).map((r) => (
            <div key={r.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 13, color: T.text, fontFamily: F, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {r.role}{r.country ? ` · ${r.country}` : ""}
                </div>
                {r.admin_note ? <div style={{ fontSize: 11, color: T.t3, fontFamily: F }}>{r.admin_note}</div> : null}
              </div>
              {statusChip(r.status)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  height: 40, padding: "0 12px", borderRadius: 10, border: `1px solid ${T.border}`,
  background: T.input, color: T.text, fontSize: 13, fontFamily: F, outline: "none", boxSizing: "border-box", width: "100%",
};
