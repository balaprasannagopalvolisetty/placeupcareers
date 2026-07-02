import { motion } from "motion/react";
import { CheckCircle2, ShieldCheck } from "lucide-react";

const F = { sans: "'Plus Jakarta Sans', sans-serif" };
const T = {
  text: "#F1F5F9",
  t2: "rgba(226,232,240,0.72)",
  border: "rgba(148,163,184,0.08)",
  glass: "rgba(15,30,55,0.55)",
  grad: "linear-gradient(135deg, #2563EB, #0EA5E9)",
  red: "#3B82F6",
};

const included = [
  "Global job matching",
  "Resume ATS score",
  "Resume uploads and tailoring",
  "Application tracker",
  "Alerts and analytics",
  "Visa sponsor signals",
  "Role requests",
];

export function BillingPage() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18, fontFamily: F.sans }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, color: T.red, fontSize: 12, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase" }}>
            <ShieldCheck size={15} /> Free preview access
          </div>
          <h2 style={{ color: T.text, fontSize: 24, fontWeight: 800, marginTop: 6, marginBottom: 4 }}>Complete access is enabled</h2>
          <p style={{ color: T.t2, fontSize: 13, lineHeight: 1.6, maxWidth: 620 }}>
            Payments and hosted checkout are temporarily disabled. You can use the full application without entering card details.
          </p>
        </div>
        <div style={{ padding: "10px 12px", borderRadius: 12, border: `1px solid ${T.border}`, background: "rgba(34,197,94,0.08)", color: "#22c55e", fontSize: 12, fontWeight: 800 }}>
          Active
        </div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        style={{
          borderRadius: 18,
          border: `1px solid rgba(59,130,246,0.32)`,
          background: T.glass,
          backdropFilter: "blur(20px)",
          padding: 20,
        }}
      >
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 10 }}>
          {included.map((feature) => (
            <div key={feature} style={{ display: "flex", gap: 8, color: T.t2, fontSize: 13, lineHeight: 1.45 }}>
              <CheckCircle2 size={15} color="#22c55e" style={{ flexShrink: 0, marginTop: 1 }} />
              {feature}
            </div>
          ))}
        </div>
        <div style={{ marginTop: 16, padding: 12, borderRadius: 12, background: "rgba(148,163,184,0.04)", border: `1px solid ${T.border}`, color: T.t2, fontSize: 12, lineHeight: 1.55 }}>
          When billing is re-enabled later, we will announce it before any paid plan is required.
        </div>
      </motion.div>
    </div>
  );
}
