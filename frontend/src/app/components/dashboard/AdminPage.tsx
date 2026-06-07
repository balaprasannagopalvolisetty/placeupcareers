import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Database, Loader2, Lock, Mail, Shield, Upload, Users, WalletCards } from "lucide-react";
import * as api from "../../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  text: "#F2EEB3",
  t2: "rgba(242,238,179,0.65)",
  t3: "rgba(242,238,179,0.45)",
  border: "rgba(242,238,179,0.08)",
  glass: "rgba(64,18,18,0.55)",
  grad: "linear-gradient(135deg, #F2A341, #ED7D2B, #C75A12)",
  red: "#ED7D2B",
};

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ borderRadius: 18, border: `1px solid ${T.border}`, background: T.glass, backdropFilter: "blur(20px)", overflow: "hidden" }}>
      {children}
    </div>
  );
}

export function AdminPage() {
  const [summary, setSummary] = useState<api.AdminSummary | null>(null);
  const [users, setUsers] = useState<Array<Record<string, unknown>>>([]);
  const [paymentsNote, setPaymentsNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.allSettled([api.getAdminSummary(), api.getAdminUsers(), api.getAdminPayments()])
      .then(([summaryRes, usersRes, paymentsRes]) => {
        if (summaryRes.status === "fulfilled") setSummary(summaryRes.value);
        if (usersRes.status === "fulfilled") setUsers(usersRes.value.users);
        if (paymentsRes.status === "fulfilled") setPaymentsNote(paymentsRes.value.note || "");
        const rejected = [summaryRes, usersRes, paymentsRes].find((res) => res.status === "rejected");
        if (rejected && rejected.status === "rejected") setError(rejected.reason?.message || "Admin access required");
      });
  }, []);

  const uploadCsv = async (dryRun: boolean) => {
    if (!file) {
      setError("Choose a LinkedIn profile CSV first.");
      return;
    }
    setUploading(true);
    setError("");
    setResult(null);
    try {
      const response = await api.uploadAdminFinalScoutCsv(file, { limit: 500, concurrency: 4, dry_run: dryRun });
      setResult(response);
    } catch (err) {
      setError((err as Error)?.message || "CSV enrichment failed");
    } finally {
      setUploading(false);
    }
  };

  if (error && !summary) {
    return (
      <Panel>
        <div style={{ padding: 28, textAlign: "center", color: T.t2, fontFamily: F.sans }}>
          <Lock size={26} color={T.red} />
          <div style={{ color: T.text, fontSize: 18, fontWeight: 800, marginTop: 10 }}>Private admin area</div>
          <div style={{ fontSize: 13, marginTop: 6 }}>{error}</div>
        </div>
      </Panel>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18, fontFamily: F.sans }}>
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, color: T.red, fontSize: 12, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase" }}>
          <Shield size={15} /> Private Admin
        </div>
        <h2 style={{ color: T.text, fontSize: 24, fontWeight: 800, marginTop: 6, marginBottom: 4 }}>Users, payments, and email extraction</h2>
        <p style={{ color: T.t2, fontSize: 13, lineHeight: 1.6, maxWidth: 760 }}>
          This route is hidden from normal navigation and protected by backend admin authorization.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
        {[
          { icon: Users, label: "User accounts", value: summary?.users ?? 0 },
          { icon: WalletCards, label: "Payment setup", value: summary?.payments.configured ? "Ready" : "Needs links" },
          { icon: Mail, label: "FinalScout keys", value: summary?.finalscout.multi_key_configured ? "Configured" : "Missing" },
        ].map((item) => (
          <motion.div key={item.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} style={{ borderRadius: 16, border: `1px solid ${T.border}`, background: T.glass, padding: 16 }}>
            <item.icon size={17} color={T.red} />
            <div style={{ color: T.text, fontSize: 24, fontWeight: 900, marginTop: 10 }}>{item.value}</div>
            <div style={{ color: T.t3, fontSize: 12 }}>{item.label}</div>
          </motion.div>
        ))}
      </div>

      <Panel>
        <div style={{ padding: 18, borderBottom: `1px solid ${T.border}`, display: "flex", alignItems: "center", gap: 10 }}>
          <Upload size={17} color={T.red} />
          <div>
            <div style={{ color: T.text, fontSize: 15, fontWeight: 800 }}>LinkedIn CSV to email extraction</div>
            <div style={{ color: T.t3, fontSize: 12 }}>CSV columns: linkedin_url or first_name, last_name, company.</div>
          </div>
        </div>
        <div style={{ padding: 18, display: "flex", flexDirection: "column", gap: 12 }}>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(event) => setFile(event.target.files?.[0] || null)}
            style={{ color: T.t2, fontSize: 13 }}
          />
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button onClick={() => uploadCsv(true)} disabled={uploading} style={{ height: 38, padding: "0 14px", borderRadius: 10, border: `1px solid ${T.border}`, background: "rgba(242,238,179,0.05)", color: T.text, cursor: uploading ? "wait" : "pointer", fontSize: 12, fontWeight: 800 }}>
              Dry run
            </button>
            <button onClick={() => uploadCsv(false)} disabled={uploading} style={{ height: 38, padding: "0 14px", borderRadius: 10, border: "none", background: T.grad, color: "#fff", cursor: uploading ? "wait" : "pointer", fontSize: 12, fontWeight: 800, display: "flex", alignItems: "center", gap: 8 }}>
              {uploading && <Loader2 size={14} className="animate-spin" />}
              Extract emails
            </button>
          </div>
          {error && <div style={{ color: T.red, fontSize: 12 }}>{error}</div>}
          {result && (
            <pre style={{ margin: 0, padding: 12, borderRadius: 12, background: "rgba(1,17,38,0.55)", border: `1px solid ${T.border}`, color: T.t2, fontSize: 11, fontFamily: F.mono, overflowX: "auto" }}>
              {JSON.stringify(result, null, 2)}
            </pre>
          )}
        </div>
      </Panel>

      <Panel>
        <div style={{ padding: 18, borderBottom: `1px solid ${T.border}`, display: "flex", alignItems: "center", gap: 10 }}>
          <Database size={17} color={T.red} />
          <div style={{ color: T.text, fontSize: 15, fontWeight: 800 }}>User accounts</div>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", color: T.t2, fontSize: 12 }}>
            <thead>
              <tr style={{ color: T.t3, borderBottom: `1px solid ${T.border}` }}>
                {["Name", "Email", "Plan", "Visa", "Created"].map((label) => <th key={label} style={{ textAlign: "left", padding: 12, fontWeight: 700 }}>{label}</th>)}
              </tr>
            </thead>
            <tbody>
              {users.slice(0, 100).map((user) => (
                <tr key={String(user.id)} style={{ borderBottom: `1px solid ${T.border}` }}>
                  <td style={{ padding: 12, color: T.text }}>{String(user.first_name || "")} {String(user.last_name || "")}</td>
                  <td style={{ padding: 12 }}>{String(user.email || "")}</td>
                  <td style={{ padding: 12 }}>{String(user.plan || "Pro")}</td>
                  <td style={{ padding: 12 }}>{String(user.visa_status || "-")}</td>
                  <td style={{ padding: 12 }}>{String(user.created_at || "").slice(0, 10)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      {paymentsNote && <div style={{ color: T.t3, fontSize: 12 }}>{paymentsNote}</div>}
    </div>
  );
}
