import { motion } from "motion/react";
import { CheckCircle2, ShieldCheck } from "lucide-react";

const F = { sans: "'Plus Jakarta Sans', sans-serif" };
const T = {
  text: "var(--pu-f1f5f9-t)",
  t2: "var(--pu-226-232-240-072)",
  border: "var(--pu-148-163-184-008)",
  glass: "var(--pu-15-30-55-055)",
  grad: "linear-gradient(135deg, var(--pu-2563eb), var(--pu-0ea5e9))",
  red: "var(--pu-3b82f6-t)",
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
        <div style={{ padding: "10px 12px", borderRadius: 12, border: `1px solid ${T.border}`, background: "var(--pu-34-197-94-008)", color: "var(--pu-22c55e-t)", fontSize: 12, fontWeight: 800 }}>
          Launch preview
        </div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        style={{
          borderRadius: 18,
          border: `1px solid var(--pu-59-130-246-032)`,
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
                border: `1px solid ${plan.featured ? "var(--pu-59-130-246-042)" : T.border}`,
                background: plan.featured ? "var(--pu-37-99-235-012)" : "var(--pu-15-23-42-036)",
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
                    <CheckCircle2 size={15} color="var(--pu-22c55e-t)" style={{ flexShrink: 0, marginTop: 1 }} />
                    {feature}
                  </div>
                ))}
              </div>
            </motion.div>
          ))}
        </div>
        <div style={{ marginTop: 16, padding: 12, borderRadius: 12, background: "var(--pu-148-163-184-004)", border: `1px solid ${T.border}`, color: T.t2, fontSize: 12, lineHeight: 1.55 }}>
          Checkout is not required during launch preview. Your plan selection is still saved for access limits and support routing.
        </div>
      </motion.div>
    </div>
  );
}
