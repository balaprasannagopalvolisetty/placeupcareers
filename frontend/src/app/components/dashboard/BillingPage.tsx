import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { CheckCircle2, CreditCard, Loader2, ShieldCheck } from "lucide-react";
import * as api from "../../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif" };
const T = {
  text: "#F2EEB3",
  t2: "rgba(242,238,179,0.65)",
  t3: "rgba(242,238,179,0.45)",
  border: "rgba(242,238,179,0.08)",
  glass: "rgba(64,18,18,0.55)",
  grad: "linear-gradient(135deg, #F2A341, #ED7D2B, #C75A12)",
  red: "#ED7D2B",
};

const fallbackPlans: api.PaymentPlan[] = [
  { id: "basic", name: "Basic", price: 9.99, interval: "month", features: ["Job matching", "Resume ATS score", "Saved jobs"] },
  { id: "pro", name: "Pro", price: 15.99, interval: "month", features: ["Everything in Basic", "Recruiter contacts", "Application tracking", "Priority job alerts"] },
  { id: "elite", name: "Elite", price: 45, interval: "month", features: ["Everything in Pro", "Premium enrichment", "Visa sponsor insights", "Concierge support"] },
];

export function BillingPage() {
  const [plans, setPlans] = useState<api.PaymentPlan[]>(fallbackPlans);
  const [loadingPlan, setLoadingPlan] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    api.getPaymentPlans().then((res) => setPlans(res.plans)).catch(() => setPlans(fallbackPlans));
  }, []);

  const startCheckout = async (planId: string) => {
    setLoadingPlan(planId);
    setMessage("");
    try {
      const res = await api.createCheckout(planId);
      window.location.href = res.checkout_url;
    } catch (err) {
      setMessage((err as Error)?.message || "Checkout is not configured yet.");
    } finally {
      setLoadingPlan("");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18, fontFamily: F.sans }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, color: T.red, fontSize: 12, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase" }}>
            <CreditCard size={15} /> Billing
          </div>
          <h2 style={{ color: T.text, fontSize: 24, fontWeight: 800, marginTop: 6, marginBottom: 4 }}>Choose your PlaceUp plan</h2>
          <p style={{ color: T.t2, fontSize: 13, lineHeight: 1.6, maxWidth: 620 }}>
            Payments are handled through hosted checkout so card numbers never touch PlaceUp servers.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 12px", borderRadius: 12, border: `1px solid ${T.border}`, background: "rgba(242,238,179,0.04)", color: T.t2, fontSize: 12 }}>
          <ShieldCheck size={15} color="#22c55e" /> Secure hosted payment
        </div>
      </div>

      {message && (
        <div style={{ padding: 14, borderRadius: 12, border: "1px solid rgba(237,125,43,0.28)", background: "rgba(237,125,43,0.08)", color: T.text, fontSize: 13 }}>
          {message}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 14 }}>
        {plans.map((plan, index) => (
          <motion.div
            key={plan.id}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.06 }}
            whileHover={{ y: -6 }}
            style={{
              borderRadius: 18,
              border: `1px solid ${plan.id === "pro" ? "rgba(237,125,43,0.38)" : T.border}`,
              background: plan.id === "pro" ? "linear-gradient(135deg, rgba(64,18,18,0.72), rgba(25,18,32,0.78))" : T.glass,
              backdropFilter: "blur(20px)",
              padding: 20,
              minHeight: 330,
              display: "flex",
              flexDirection: "column",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
              <h3 style={{ color: T.text, fontSize: 18, fontWeight: 800 }}>{plan.name}</h3>
              {plan.id === "pro" && <span style={{ fontSize: 10, color: "#fff", background: T.grad, borderRadius: 999, padding: "4px 8px", fontWeight: 800 }}>POPULAR</span>}
            </div>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 6, marginBottom: 18 }}>
              <span style={{ color: T.text, fontSize: 40, fontWeight: 900, lineHeight: 1 }}>${plan.price.toFixed(plan.price % 1 ? 2 : 0)}</span>
              <span style={{ color: T.t3, fontSize: 12, marginBottom: 5 }}>/{plan.interval}</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10, flex: 1 }}>
              {plan.features.map((feature) => (
                <div key={feature} style={{ display: "flex", gap: 8, color: T.t2, fontSize: 13, lineHeight: 1.45 }}>
                  <CheckCircle2 size={15} color="#22c55e" style={{ flexShrink: 0, marginTop: 1 }} />
                  {feature}
                </div>
              ))}
            </div>
            <button
              onClick={() => startCheckout(plan.id)}
              disabled={Boolean(loadingPlan)}
              style={{ height: 42, marginTop: 20, borderRadius: 12, border: "none", background: T.grad, color: "#fff", cursor: loadingPlan ? "wait" : "pointer", fontSize: 13, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}
            >
              {loadingPlan === plan.id && <Loader2 size={15} className="animate-spin" />}
              Start {plan.name}
            </button>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
