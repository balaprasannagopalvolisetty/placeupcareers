import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Link } from "react-router";
import {
  ArrowRight, Target, Mail, Shield, BarChart3,
  Users, Bell, Mic, Check, Send, MapPin, Phone, Globe,
  FileText, Search, Sparkles, Star,
} from "lucide-react";
import { Navbar } from "../components/Navbar";
import * as api from "../lib/api";

// ─── Design tokens: clean, light, professional SaaS ───
const T = {
  bg:        "#FFFFFF",
  bgAlt:     "#F8FAFC",
  card:      "#FFFFFF",
  border:    "#E2E8F0",
  text:      "#0F172A",
  t2:        "#475569",
  t3:        "#64748B",
  accent:    "#2563EB",
  accentDeep:"#1D4ED8",
  grad:      "linear-gradient(135deg, #2563EB, #0EA5E9)",
  shadow:    "0 1px 3px rgba(15,23,42,0.06), 0 8px 24px rgba(15,23,42,0.05)",
  shadowH:   "0 4px 12px rgba(15,23,42,0.08), 0 16px 40px rgba(15,23,42,0.10)",
};
const F = { sans: "'Plus Jakarta Sans', sans-serif" };

function useViewportFlags() {
  const getWidth = () => (typeof window === "undefined" ? 1280 : window.innerWidth);
  const [width, setWidth] = useState(getWidth);
  useEffect(() => {
    const onResize = () => setWidth(getWidth());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return { isMobile: width < 680 };
}

function Reveal({ children, delay = 0, y = 24 }: { children: React.ReactNode; delay?: number; y?: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.55, delay, ease: [0.25, 0.46, 0.45, 0.94] }}
    >{children}</motion.div>
  );
}

function SectionTag({ text }: { text: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "center", marginBottom: 16 }}>
      <span style={{
        display: "inline-block", padding: "6px 14px", borderRadius: 9999,
        background: "rgba(37,99,235,0.08)", border: "1px solid rgba(37,99,235,0.18)",
        fontSize: 12, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase",
        color: T.accent, fontFamily: F.sans,
      }}>{text}</span>
    </div>
  );
}

function Card({ children, style = {}, hover = true }: {
  children: React.ReactNode; style?: React.CSSProperties; hover?: boolean;
}) {
  return (
    <motion.div
      whileHover={hover ? { y: -4, boxShadow: T.shadowH } : undefined}
      transition={{ duration: 0.25 }}
      style={{
        background: T.card,
        border: `1px solid ${T.border}`,
        borderRadius: 16,
        boxShadow: T.shadow,
        ...style,
      }}
    >{children}</motion.div>
  );
}

// ═══════════════════════════
// MAIN HOME PAGE
// ═══════════════════════════
export default function Home() {
  return (
    <div style={{ background: T.bg, position: "relative", fontFamily: F.sans }}>
      <Navbar />
      <HeroSection />
      <HowItWorksSection />
      <FeaturesSection />
      <PricingSection />
      <ContactSection />
      <Footer />
    </div>
  );
}

// ═══════════════════════════
// 1. HERO
// ═══════════════════════════
function HeroSection() {
  const { isMobile } = useViewportFlags();
  const [liveJobs, setLiveJobs] = useState<number | null>(null);
  const [liveCategories, setLiveCategories] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    api.getJobStats()
      .then((s) => {
        if (!active) return;
        if (typeof s?.total_jobs === "number") setLiveJobs(s.total_jobs);
        const cats = s?.by_category ? Object.keys(s.by_category).length : 0;
        if (cats) setLiveCategories(cats);
      })
      .catch(() => {});
    return () => { active = false; };
  }, []);

  const jobsLabel = liveJobs && liveJobs > 0
    ? (liveJobs >= 1000 ? `${(liveJobs / 1000).toFixed(liveJobs >= 10000 ? 0 : 1)}k+` : `${liveJobs}+`)
    : "1k+";
  const stats = [
    { val: jobsLabel, label: "Live roles" },
    { val: liveCategories ? String(liveCategories) : "10", label: "Categories" },
    { val: "25", label: "Countries" },
    { val: "6hr", label: "Refresh" },
  ];

  return (
    <section style={{
      paddingTop: isMobile ? 120 : 150, paddingBottom: isMobile ? 64 : 96,
      background: `radial-gradient(1200px 500px at 50% -10%, rgba(37,99,235,0.07), transparent 70%), ${T.bg}`,
      position: "relative",
    }}>
      <div style={{ maxWidth: 860, margin: "0 auto", padding: "0 24px", textAlign: "center" }}>
        {/* Status badge */}
        <Reveal delay={0.05} y={12}>
          <div style={{
            display: "inline-flex", alignItems: "center", gap: 8, padding: "8px 16px",
            borderRadius: 9999, marginBottom: 28,
            background: "rgba(37,99,235,0.06)", border: "1px solid rgba(37,99,235,0.16)",
          }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#22C55E", boxShadow: "0 0 0 3px rgba(34,197,94,0.18)" }} />
            <span style={{ fontSize: 12.5, fontWeight: 600, color: T.accent, fontFamily: F.sans }}>
              Visa-friendly roles in 25 countries, refreshed every 6 hours
            </span>
          </div>
        </Reveal>

        {/* Headline */}
        <Reveal delay={0.12}>
          <h1 style={{
            fontFamily: F.sans, fontSize: "clamp(38px, 6vw, 68px)", fontWeight: 800,
            lineHeight: 1.08, letterSpacing: "-0.03em", color: T.text, marginBottom: 22,
          }}>
            Land your dream job,{" "}
            <span style={{ background: T.grad, WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
              anywhere in the world
            </span>
          </h1>
        </Reveal>

        {/* Subheading */}
        <Reveal delay={0.2}>
          <p style={{
            fontSize: 18, lineHeight: 1.7, color: T.t2, fontFamily: F.sans,
            maxWidth: 620, margin: "0 auto 36px",
          }}>
            Freshly posted, visa-friendly roles across 25 countries, including H-1B, EU Blue Card,
            Skilled Worker, and Employment Pass. Every job is scored against your resume in real time,
            so you apply only where you can actually get hired and sponsored.
          </p>
        </Reveal>

        {/* CTA buttons */}
        <Reveal delay={0.28}>
          <div style={{ display: "flex", gap: 14, marginBottom: 52, flexWrap: "wrap", justifyContent: "center" }}>
            <Link to="/signup" style={{
              display: "inline-flex", alignItems: "center", gap: 8,
              padding: "15px 30px", borderRadius: 12, background: T.grad,
              color: "#fff", fontSize: 16, fontWeight: 700, fontFamily: F.sans,
              textDecoration: "none", boxShadow: "0 8px 24px rgba(37,99,235,0.28)",
            }}>
              Get started free <ArrowRight size={17} />
            </Link>
            <button
              onClick={() => document.getElementById("how-it-works")?.scrollIntoView({ behavior: "smooth" })}
              style={{
                display: "inline-flex", alignItems: "center", gap: 8,
                padding: "15px 26px", borderRadius: 12,
                background: "#fff", border: `1px solid ${T.border}`,
                color: T.text, fontSize: 16, fontFamily: F.sans, fontWeight: 600,
                cursor: "pointer", boxShadow: T.shadow,
              }}>
              How it works
            </button>
          </div>
        </Reveal>

        {/* Stats row */}
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", justifyContent: "center" }}>
          {stats.map((s, i) => (
            <Reveal key={s.label} delay={0.34 + i * 0.06} y={16}>
              <Card style={{ padding: "18px 26px", textAlign: "center", minWidth: 112 }}>
                <div style={{
                  fontFamily: F.sans, fontSize: 26, fontWeight: 800, lineHeight: 1,
                  background: T.grad, WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
                  marginBottom: 6,
                }}>{s.val}</div>
                <div style={{ fontSize: 13, color: T.t3, fontFamily: F.sans, fontWeight: 500 }}>{s.label}</div>
              </Card>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

// ═══════════════════════════
// 2. HOW IT WORKS
// ═══════════════════════════
const steps = [
  {
    icon: FileText, step: "01", title: "Upload your resume",
    desc: "Add your resume once. We parse your skills, experience, and target roles to build your matching profile.",
  },
  {
    icon: Search, step: "02", title: "We find visa-friendly jobs",
    desc: "Our pipeline collects fresh postings from official company sources across 25 countries and screens each one for sponsorship signals.",
  },
  {
    icon: Sparkles, step: "03", title: "Every job is scored for you",
    desc: "Each posting gets an ATS match score against your resume, with a keyword-level breakdown of what is strong and what is missing.",
  },
  {
    icon: Target, step: "04", title: "Apply where you can win",
    desc: "Apply directly at the source with confidence, track every application, and get daily alerts for new top matches.",
  },
];

function HowItWorksSection() {
  const { isMobile } = useViewportFlags();
  return (
    <section id="how-it-works" style={{ padding: isMobile ? "64px 0" : "96px 0", background: T.bgAlt }}>
      <div style={{ maxWidth: 1140, margin: "0 auto", padding: "0 24px" }}>
        <Reveal><SectionTag text="How it works" /></Reveal>
        <Reveal delay={0.08}>
          <h2 style={{
            fontFamily: F.sans, fontWeight: 800, fontSize: "clamp(28px, 4vw, 44px)",
            lineHeight: 1.15, letterSpacing: "-0.02em", textAlign: "center",
            color: T.text, marginBottom: 14,
          }}>
            From resume to offer, in four steps
          </h2>
        </Reveal>
        <Reveal delay={0.12}>
          <p style={{ textAlign: "center", fontSize: 16, color: T.t2, fontFamily: F.sans, maxWidth: 560, margin: "0 auto 52px", lineHeight: 1.7 }}>
            No endless scrolling through job boards. We do the searching, screening, and scoring so you can focus on applying well.
          </p>
        </Reveal>
        <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "repeat(auto-fit, minmax(240px, 1fr))", gap: 18 }}>
          {steps.map((s, i) => (
            <Reveal key={s.step} delay={0.15 + i * 0.07}>
              <Card style={{ padding: 28, height: "100%" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18 }}>
                  <div style={{
                    width: 44, height: 44, borderRadius: 12, background: "rgba(37,99,235,0.08)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                  }}>
                    <s.icon size={20} color={T.accent} />
                  </div>
                  <span style={{ fontFamily: F.sans, fontSize: 13, fontWeight: 700, color: "#CBD5E1" }}>{s.step}</span>
                </div>
                <h3 style={{ fontFamily: F.sans, fontSize: 17, fontWeight: 700, color: T.text, marginBottom: 8 }}>{s.title}</h3>
                <p style={{ fontSize: 14.5, lineHeight: 1.65, color: T.t2, fontFamily: F.sans }}>{s.desc}</p>
              </Card>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

// ═══════════════════════════
// 3. FEATURES
// ═══════════════════════════
const features = [
  { icon: Shield, title: "Visa-Aware Job Matching", desc: "Every listing is screened for sponsorship signals such as F1-CPT, F1-OPT, STEM OPT, and H-1B, backed by real petition data, so you only apply where you are eligible." },
  { icon: Target, title: "Resume Match Scoring", desc: "See how your active resume scores against any posting before you apply, with a keyword-by-keyword breakdown of what is strong and what is missing." },
  { icon: Users, title: "Direct Company Links", desc: "We trace each posting back to the company's official careers page, so you apply at the source, where recruiters actually look first." },
  { icon: BarChart3, title: "Application Tracker", desc: "Applied, saved, and skipped roles in one dashboard, with dates and statuses, so you never duplicate effort or lose track of a follow-up." },
  { icon: Bell, title: "Smart Daily Alerts", desc: "Your top matches delivered every morning, pre-filtered by visa status, role, and location. No noise, just jobs worth your time." },
  { icon: Mic, title: "Interview & Career Coaching", desc: "Elite members get one-on-one mock interviews, AI resume rewrites, and salary negotiation support from experienced US recruiters." },
];

function FeaturesSection() {
  const { isMobile } = useViewportFlags();
  return (
    <section id="features" style={{ padding: isMobile ? "64px 0" : "96px 0", background: T.bg }}>
      <div style={{ maxWidth: 1140, margin: "0 auto", padding: "0 24px" }}>
        <Reveal><SectionTag text="Features" /></Reveal>
        <Reveal delay={0.08}>
          <h2 style={{
            fontFamily: F.sans, fontWeight: 800, fontSize: "clamp(28px, 4vw, 44px)",
            lineHeight: 1.15, letterSpacing: "-0.02em", textAlign: "center",
            color: T.text, marginBottom: 52,
          }}>
            Everything you need to get hired
          </h2>
        </Reveal>
        <div style={{ display: "grid", gridTemplateColumns: `repeat(auto-fit, minmax(${isMobile ? "240px" : "300px"}, 1fr))`, gap: 18 }}>
          {features.map((f, i) => (
            <Reveal key={f.title} delay={0.1 + i * 0.06}>
              <Card style={{ padding: 28, height: "100%" }}>
                <div style={{
                  width: 44, height: 44, borderRadius: 12, background: T.grad,
                  display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 18,
                  boxShadow: "0 6px 16px rgba(37,99,235,0.22)",
                }}>
                  <f.icon size={20} color="#fff" />
                </div>
                <h3 style={{ fontFamily: F.sans, fontSize: 17, fontWeight: 700, color: T.text, marginBottom: 8 }}>{f.title}</h3>
                <p style={{ fontSize: 14.5, lineHeight: 1.65, color: T.t2, fontFamily: F.sans }}>{f.desc}</p>
              </Card>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

// ═══════════════════════════
// 4. PRICING
// ═══════════════════════════
const plans = [
  {
    name: "Preview", price: "$0", desc: "Complete access while we finish launch hardening",
    badge: "Free now", featured: false,
    features: [
      "Job matching", "Resume ATS score", "Public visa signals",
      "Resume upload", "Application tracker", "Role requests", "No payment required",
    ],
    cta: "Create free account", ctaLink: "/signup",
  },
  {
    name: "Pro Access", price: "$0", desc: "All Pro workflows are open during preview",
    badge: "Included", featured: true,
    features: [
      "Unlimited ATS scoring", "Smart daily alerts", "Global visa tracker",
      "Multiple resumes", "Application tracker", "Direct apply links", "Career analytics dashboard",
    ],
    cta: "Start free", ctaLink: "/signup",
  },
  {
    name: "Elite Tools", price: "$0", desc: "Premium tools stay open until billing is re-enabled",
    badge: "Preview", featured: false,
    features: [
      "Everything in Pro", "Resume tailoring", "Recruiter contacts",
      "Market analytics", "Visa sponsor insights", "Admin-reviewed role requests", "No checkout step",
    ],
    cta: "Join preview", ctaLink: "/signup",
  },
];

function PricingSection() {
  const { isMobile } = useViewportFlags();
  return (
    <section id="pricing" style={{ padding: isMobile ? "64px 0" : "96px 0", background: T.bgAlt }}>
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "0 24px" }}>
        <Reveal><SectionTag text="Pricing" /></Reveal>
        <Reveal delay={0.08}>
          <h2 style={{
            fontFamily: F.sans, fontWeight: 800, fontSize: "clamp(28px, 4vw, 44px)",
            lineHeight: 1.15, letterSpacing: "-0.02em", textAlign: "center",
            color: T.text, marginBottom: 12,
          }}>
            Free Preview Access
          </h2>
        </Reveal>
        <Reveal delay={0.12}>
          <p style={{ textAlign: "center", fontSize: 16, color: T.t2, fontFamily: F.sans, marginBottom: 52, lineHeight: 1.7 }}>
            Complete application access is free right now. No card, checkout, or payment step is required.
          </p>
        </Reveal>

        <div style={{ display: "grid", gridTemplateColumns: `repeat(auto-fit, minmax(${isMobile ? "240px" : "290px"}, 1fr))`, gap: 20, alignItems: "start" }}>
          {plans.map((plan, i) => (
            <Reveal key={plan.name} delay={0.15 + i * 0.08}>
              <div style={{ position: "relative", paddingTop: 16 }}>
                <div style={{
                  position: "absolute", top: 0, left: "50%", transform: "translateX(-50%)",
                  display: "inline-flex", alignItems: "center", gap: 5,
                  padding: "5px 14px", borderRadius: 9999,
                  background: plan.featured ? T.grad : "#fff",
                  border: plan.featured ? "none" : `1px solid ${T.border}`,
                  color: plan.featured ? "#fff" : T.accent,
                  fontSize: 11.5, fontWeight: 700, fontFamily: F.sans, whiteSpace: "nowrap",
                  boxShadow: T.shadow, zIndex: 2,
                }}>
                  <Star size={11} fill="currentColor" /> {plan.badge}
                </div>
                <Card hover={false} style={{
                  padding: "38px 28px 30px",
                  border: plan.featured ? `2px solid ${T.accent}` : `1px solid ${T.border}`,
                  boxShadow: plan.featured ? T.shadowH : T.shadow,
                }}>
                  <div style={{ fontFamily: F.sans, fontSize: 19, fontWeight: 800, color: T.text, marginBottom: 6 }}>{plan.name}</div>
                  <p style={{ fontSize: 13.5, color: T.t3, fontFamily: F.sans, marginBottom: 20, lineHeight: 1.55, minHeight: 42 }}>{plan.desc}</p>
                  <div style={{ display: "flex", alignItems: "flex-end", gap: 6, marginBottom: 22 }}>
                    <span style={{ fontFamily: F.sans, fontSize: 44, fontWeight: 800, lineHeight: 1, color: T.text }}>{plan.price}</span>
                  </div>
                  <Link to={plan.ctaLink} style={{
                    display: "block", textAlign: "center", padding: "13px",
                    borderRadius: 12, marginBottom: 24,
                    background: plan.featured ? T.grad : "#fff",
                    border: plan.featured ? "none" : `1px solid ${T.border}`,
                    color: plan.featured ? "#fff" : T.text,
                    fontSize: 14.5, fontWeight: 700, fontFamily: F.sans,
                    textDecoration: "none",
                    boxShadow: plan.featured ? "0 8px 20px rgba(37,99,235,0.28)" : "none",
                  }}>{plan.cta}</Link>
                  <ul style={{ display: "flex", flexDirection: "column", gap: 11, listStyle: "none", padding: 0, margin: 0 }}>
                    {plan.features.map((feat) => (
                      <li key={feat} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <span style={{
                          width: 18, height: 18, borderRadius: "50%", background: "rgba(34,197,94,0.12)",
                          display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
                        }}>
                          <Check size={11} color="#16A34A" strokeWidth={3} />
                        </span>
                        <span style={{ fontSize: 14, color: T.t2, fontFamily: F.sans, lineHeight: 1.4 }}>{feat}</span>
                      </li>
                    ))}
                  </ul>
                </Card>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

// ═══════════════════════════
// 5. CONTACT
// ═══════════════════════════
function ContactSection() {
  const { isMobile } = useViewportFlags();
  const [form, setForm] = useState({ name: "", email: "", subject: "", message: "" });
  const [sent, setSent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [contactError, setContactError] = useState("");

  const submitContact = async () => {
    setContactError("");
    if (!form.name.trim() || !form.email.trim() || !form.message.trim()) {
      setContactError("Please enter your name, email, and message.");
      return;
    }
    setSubmitting(true);
    try {
      await api.submitContactMessage({
        name: form.name.trim(),
        email: form.email.trim(),
        subject: form.subject || "General Inquiry",
        message: form.message.trim(),
      });
      setSent(true);
    } catch (err) {
      setContactError((err as Error).message || "Could not send your message. Please email operations@placeupcareer.com directly.");
    } finally {
      setSubmitting(false);
    }
  };

  const inputStyle: React.CSSProperties = {
    padding: "13px 15px", borderRadius: 10, border: `1px solid ${T.border}`,
    background: "#fff", color: T.text, fontSize: 14.5, fontFamily: F.sans,
    outline: "none", width: "100%",
  };

  return (
    <section id="contact" style={{ padding: isMobile ? "64px 0" : "96px 0", background: T.bg }}>
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "0 24px" }}>
        <Reveal><SectionTag text="Contact" /></Reveal>
        <Reveal delay={0.08}>
          <h2 style={{
            fontFamily: F.sans, fontWeight: 800, fontSize: "clamp(28px, 4vw, 44px)",
            lineHeight: 1.15, letterSpacing: "-0.02em", textAlign: "center",
            color: T.text, marginBottom: 48,
          }}>
            Get in touch
          </h2>
        </Reveal>

        <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1.4fr", gap: 22 }}>
          {/* Contact info */}
          <Reveal delay={0.12}>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {[
                { icon: Mail, label: "Email", value: "operations@placeupcareer.com", href: "mailto:operations@placeupcareer.com" },
                { icon: Globe, label: "Website", value: "placeupcareer.com", href: "https://placeupcareer.com/" },
                { icon: Phone, label: "Phone", value: "+1 (307) 400-5526", href: "tel:+13074005526" },
                { icon: MapPin, label: "Address", value: "30 N Gould St Ste N, Sheridan, WY 82801", href: undefined },
              ].map((item) => (
                <Card key={item.label} style={{ padding: "20px 22px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                    <div style={{
                      width: 42, height: 42, borderRadius: 11, background: "rgba(37,99,235,0.08)",
                      display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
                    }}>
                      <item.icon size={17} color={T.accent} />
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 11.5, fontWeight: 700, letterSpacing: "0.07em", textTransform: "uppercase", color: T.t3, fontFamily: F.sans, marginBottom: 3 }}>{item.label}</div>
                      {item.href
                        ? <a href={item.href} target={item.href.startsWith("http") ? "_blank" : undefined} rel="noopener noreferrer"
                            style={{ fontSize: 14.5, color: T.text, fontFamily: F.sans, fontWeight: 600, textDecoration: "none", wordBreak: "break-word" }}>{item.value}</a>
                        : <div style={{ fontSize: 14.5, color: T.text, fontFamily: F.sans, fontWeight: 600 }}>{item.value}</div>}
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          </Reveal>

          {/* Contact form */}
          <Reveal delay={0.18}>
            <Card hover={false} style={{ padding: 28 }}>
              {sent ? (
                <div style={{ textAlign: "center", padding: "48px 0" }}>
                  <div style={{
                    width: 56, height: 56, borderRadius: "50%", background: "rgba(34,197,94,0.12)",
                    display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 18px",
                  }}>
                    <Check size={26} color="#16A34A" strokeWidth={3} />
                  </div>
                  <div style={{ fontFamily: F.sans, fontSize: 19, fontWeight: 700, color: T.text, marginBottom: 8 }}>Message sent!</div>
                  <div style={{ fontSize: 14.5, color: T.t2, fontFamily: F.sans }}>We will get back to you within 24 hours.</div>
                </div>
              ) : (
                <div>
                  <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 14, marginBottom: 14 }}>
                    <input placeholder="Full name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} style={inputStyle} />
                    <input placeholder="Email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} style={inputStyle} />
                  </div>
                  <select className="pu-light-select" value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })}
                    style={{ ...inputStyle, marginBottom: 14, color: form.subject ? T.text : T.t3 }}>
                    <option value="">Subject</option>
                    <option>General Inquiry</option>
                    <option>Technical Support</option>
                    <option>Account Access</option>
                    <option>Partnership</option>
                  </select>
                  <textarea placeholder="Your message..." value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })}
                    style={{ ...inputStyle, height: 120, resize: "none", marginBottom: 14 }} />
                  {contactError && (
                    <div style={{ color: "#DC2626", fontSize: 13, fontFamily: F.sans, marginBottom: 12 }}>{contactError}</div>
                  )}
                  <button onClick={submitContact} disabled={submitting}
                    style={{
                      width: "100%", padding: "14px", borderRadius: 12, border: "none",
                      cursor: submitting ? "wait" : "pointer", background: T.grad, color: "#fff",
                      fontSize: 15.5, fontWeight: 700, fontFamily: F.sans,
                      display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                      boxShadow: "0 8px 20px rgba(37,99,235,0.25)", opacity: submitting ? 0.75 : 1,
                    }}>
                    {submitting ? "Sending..." : "Send message"} <Send size={15} />
                  </button>
                </div>
              )}
            </Card>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

// ═══════════════════════════
// 6. FOOTER
// ═══════════════════════════
function Footer() {
  return (
    <div style={{ borderTop: `1px solid ${T.border}`, padding: "22px 24px", background: T.bgAlt }}>
      <div style={{
        maxWidth: 1100, margin: "0 auto", display: "flex", flexWrap: "wrap",
        alignItems: "center", justifyContent: "space-between", gap: 12,
      }}>
        <span style={{ fontFamily: F.sans, fontSize: 15, fontWeight: 800, color: T.text }}>
          PlaceUp <span style={{ color: T.accent }}>Career</span>
        </span>
        <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
          {[
            { l: "Privacy", to: "/privacy" },
            { l: "Terms", to: "/terms" },
            { l: "Cookies", to: "/cookies" },
            { l: "Disclaimer", to: "/disclaimer" },
            { l: "Return Policy", to: "/return-policy" },
          ].map((item) => (
            <Link key={item.l} to={item.to} style={{ fontSize: 12.5, color: T.t3, textDecoration: "none", fontFamily: F.sans, fontWeight: 500 }}>{item.l}</Link>
          ))}
        </div>
        <span style={{ fontSize: 12.5, color: T.t3, fontFamily: F.sans }}>© 2026 PlaceUp Career</span>
      </div>
    </div>
  );
}
