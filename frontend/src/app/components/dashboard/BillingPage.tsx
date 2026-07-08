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

const plans = [
  {
    id: "basic",
    name: "Basic",
    price: "$9.99",
    features: ["Job matching", "Resume ATS score", "Saved jobs"],
  },
  {
    id: "pro",
    name: "Pro",
    price: "$24.99",
    featured: true,
    features: ["Everything in Basic", "Recruiter contacts", "Application tracking", "Priority job alerts"],
  },
  {
    id: "elite",
    name: "Elite",
    price: "$149.99",
    features: [
      "Everything in Pro",
      "Premium enrichment",
      "Visa sponsor insights",
      "Concierge support",
      "Dedicated employee applies for you to 25-30 filtered positions daily",
    ],
  },
];

export function BillingPage() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18, fontFamily: F.sans }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, color: T.red, fontSize: 12, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase" }}>
            <ShieldCheck size={15} /> Monthly plans
          </div>
          <h2 style={{ color: T.text, fontSize: 24, fontWeight: 800, marginTop: 6, marginBottom: 4 }}>Billing and plan access</h2>
          <p style={{ color: T.t2, fontSize: 13, lineHeight: 1.6, maxWidth: 620 }}>
            Choose the support level that fits your search, from self-serve matching to daily concierge applications.
          </p>
        </div>
        <div style={{ padding: "10px 12px", borderRadius: 12, border: `1px solid ${T.border}`, background: "rgba(34,197,94,0.08)", color: "#22c55e", fontSize: 12, fontWeight: 800 }}>
          Launch preview
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
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
          {plans.map((plan) => (
            <motion.div
              key={plan.id}
              whileHover={{ y: -3 }}
              style={{
                minHeight: 238,
                borderRadius: 16,
                border: `1px solid ${plan.featured ? "rgba(59,130,246,0.42)" : T.border}`,
                background: plan.featured ? "rgba(37,99,235,0.12)" : "rgba(15,23,42,0.36)",
                padding: 16,
                display: "flex",
                flexDirection: "column",
                gap: 12,
              }}
            >
              <div>
                <div style={{ color: T.text, fontSize: 16, fontWeight: 800 }}>{plan.name}</div>
                <div style={{ color: T.text, fontSize: 26, fontWeight: 900, marginTop: 6 }}>
                  {plan.price}
                  <span style={{ color: T.t2, fontSize: 12, fontWeight: 700 }}> / m</span>
                </div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {plan.features.map((feature) => (
                  <div key={feature} style={{ display: "flex", gap: 8, color: T.t2, fontSize: 12.5, lineHeight: 1.45 }}>
                    <CheckCircle2 size={15} color="#22c55e" style={{ flexShrink: 0, marginTop: 1 }} />
                    {feature}
                  </div>
                ))}
              </div>
            </motion.div>
          ))}
        </div>
        <div style={{ marginTop: 16, padding: 12, borderRadius: 12, background: "rgba(148,163,184,0.04)", border: `1px solid ${T.border}`, color: T.t2, fontSize: 12, lineHeight: 1.55 }}>
          Checkout is not required during launch preview. Your plan selection is still saved for access limits and support routing.
        </div>
      </motion.div>
    </div>
  );
}
