import { useEffect, useState } from "react";
import { motion, useScroll, useTransform, AnimatePresence } from "motion/react";
import { Link } from "react-router";
import {
  ArrowRight, Target, Mail, Shield, BarChart3,
  Users, Bell, Mic, Check, ChevronDown, Send, Github, Twitter,
  Linkedin, MapPin, Phone, Globe,
} from "lucide-react";
import { Navbar } from "../components/Navbar";
import { HowItWorksScrollStory } from "../components/HowItWorksScrollStory";
import { FloatingParticles } from "../components/FloatingParticles";

// ─── Design Tokens ───
const T = {
  bgPage:   "#011126",
  bgGlass:  "rgba(64,18,18,0.65)",
  border:   "rgba(242,238,179,0.08)",
  borderHover: "rgba(166,55,45,0.4)",
  text:     "#F2EEB3",
  t2:       "rgba(242,238,179,0.65)",
  t3:       "rgba(242,238,179,0.45)",
  grad:     "linear-gradient(135deg, #8C3A27, #A6372D, #401212)",
  gradH:    "linear-gradient(135deg, #A6372D 0%, #8C3A27 50%, #401212 100%)",
  red:      "#A6372D",
  burnt:    "#8C3A27",
  dark:     "#401212",
  shadow:   "0 4px 24px rgba(1,17,38,0.25), 0 1px 4px rgba(1,17,38,0.15)",
  shadowH:  "0 16px 48px rgba(1,17,38,0.35), 0 4px 16px rgba(1,17,38,0.2)",
  glow:     "0 0 48px rgba(166,55,45,0.3), 0 0 16px rgba(166,55,45,0.15)",
};
const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };

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

// ─── Section Active Context ───
// (Removed – natural scroll uses whileInView instead)

// ═══════════════════════════
// UTILITY COMPONENTS
// ═══════════════════════════

function RevealLine({ children, delay = 0 }: { children: React.ReactNode; delay?: number }) {
  return (
    <div style={{ overflow: "hidden", display: "block" }}>
      <motion.div
        initial={{ y: "110%", opacity: 0 }}
        animate={{ y: "0%", opacity: 1 }}
        transition={{ duration: 1.0, delay, ease: [0.76, 0, 0.24, 1] }}
      >{children}</motion.div>
    </div>
  );
}

function SectionReveal({ children, delay = 0, y = 32 }: { children: React.ReactNode; delay?: number; y?: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.75, delay, ease: [0.25, 0.46, 0.45, 0.94] }}
    >{children}</motion.div>
  );
}

function SectionLabel({ text }: { text: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
      <div style={{ height: 1, width: 36, background: `linear-gradient(to right, transparent, ${T.red}50)` }} />
      <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: T.red, fontFamily: F.sans }}>
        {text}
      </span>
      <div style={{ height: 1, flex: 1, background: `linear-gradient(to right, ${T.red}50, transparent)` }} />
    </div>
  );
}

function GlassCard({ children, style = {}, hoverY = -8, className = "" }: {
  children: React.ReactNode; style?: React.CSSProperties; hoverY?: number; className?: string;
}) {
  const [isHovered, setIsHovered] = useState(false);

  return (
    <motion.div
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      whileHover={{ y: hoverY, boxShadow: `${T.shadowH}, ${T.glow}`, borderColor: "rgba(166,55,45,0.3)" }}
      whileTap={{ scale: 0.98 }}
      transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
      className={`group relative overflow-hidden ${className}`}
      style={{
        background: T.bgGlass,
        backdropFilter: "blur(24px) saturate(180%)",
        WebkitBackdropFilter: "blur(24px) saturate(180%)",
        border: `1px solid ${T.border}`,
        borderRadius: 20,
        boxShadow: T.shadow,
        ...style,
      }}
    >
      {/* Top glow on hover */}
      <motion.div
        animate={{ opacity: isHovered ? 1 : 0 }}
        transition={{ duration: 0.4 }}
        className="absolute inset-0 pointer-events-none"
        style={{
          background: "radial-gradient(ellipse at 50% -20%, rgba(166,55,45,0.18) 0%, transparent 65%)",
          zIndex: 0,
        }}
      />

      {/* Top border highlight */}
      <motion.div
        animate={{ opacity: isHovered ? 1 : 0 }}
        transition={{ duration: 0.4 }}
        className="absolute top-0 left-0 right-0 h-px pointer-events-none"
        style={{
          background: "linear-gradient(to right, transparent, rgba(166,55,45,0.6), transparent)",
        }}
      />

      {/* Animated gradient orb */}
      <motion.div
        animate={isHovered ? {
          scale: [1, 1.2, 1],
          opacity: [0.1, 0.15, 0.1],
        } : {}}
        transition={{ duration: 2, repeat: Infinity }}
        className="absolute pointer-events-none"
        style={{
          top: "-50%",
          right: "-20%",
          width: "150%",
          height: "150%",
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(140,58,39,0.2) 0%, transparent 50%)",
          filter: "blur(40px)",
          zIndex: 0,
        }}
      />

      <div style={{ position: "relative", zIndex: 1 }}>{children}</div>
    </motion.div>
  );
}

// ─── Gradient text helper ───
function GradText({ children }: { children: React.ReactNode }) {
  return (
    <span style={{ background: T.grad, WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
      {children}
    </span>
  );
}

// ─── Noise overlay ───
function NoiseOverlay() {
  return (
    <div className="fixed inset-0 pointer-events-none" style={{
      zIndex: 8,
      backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.80' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='200' height='200' filter='url(%23n)'/%3E%3C/svg%3E")`,
      opacity: 0.028,
    }} />
  );
}

// ─── Animated gradient background ───
function AnimatedGradientBg() {
  return (
    <div className="fixed inset-0 pointer-events-none" style={{ zIndex: 1, overflow: "hidden" }}>
      {/* Large radial glow 1 */}
      <motion.div
        animate={{
          x: ["-20%", "20%", "-20%"],
          y: ["-10%", "10%", "-10%"],
          scale: [1, 1.2, 1],
          opacity: [0.15, 0.25, 0.15],
        }}
        transition={{ duration: 20, repeat: Infinity, ease: "easeInOut" }}
        style={{
          position: "absolute",
          top: "10%",
          left: "20%",
          width: "60vw",
          height: "60vw",
          maxWidth: 800,
          maxHeight: 800,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(166,55,45,0.3) 0%, rgba(140,58,39,0.1) 40%, transparent 70%)",
          filter: "blur(80px)",
        }}
      />
      {/* Large radial glow 2 */}
      <motion.div
        animate={{
          x: ["20%", "-20%", "20%"],
          y: ["10%", "-10%", "10%"],
          scale: [1.2, 1, 1.2],
          opacity: [0.12, 0.22, 0.12],
        }}
        transition={{ duration: 25, repeat: Infinity, ease: "easeInOut" }}
        style={{
          position: "absolute",
          top: "40%",
          right: "15%",
          width: "50vw",
          height: "50vw",
          maxWidth: 700,
          maxHeight: 700,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(140,58,39,0.25) 0%, rgba(64,18,18,0.15) 40%, transparent 70%)",
          filter: "blur(90px)",
        }}
      />
      {/* Smaller accent glow */}
      <motion.div
        animate={{
          x: ["-10%", "10%", "-10%"],
          y: ["5%", "-5%", "5%"],
          scale: [1, 1.3, 1],
          opacity: [0.08, 0.18, 0.08],
        }}
        transition={{ duration: 15, repeat: Infinity, ease: "easeInOut" }}
        style={{
          position: "absolute",
          bottom: "20%",
          left: "50%",
          width: "40vw",
          height: "40vw",
          maxWidth: 600,
          maxHeight: 600,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(166,55,45,0.2) 0%, transparent 60%)",
          filter: "blur(70px)",
        }}
      />
    </div>
  );
}

// ─── Orbital Sphere SVG visual (hero right panel) ───
function OrbitalSphere({ size = 480 }: { size?: number }) {
  const cx = size / 2, cy = size / 2;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ overflow: "visible" }}>
      <defs>
        <radialGradient id="sphereGrad" cx="35%" cy="30%" r="65%">
          <stop offset="0%" stopColor="rgba(166,55,45,0.95)" />
          <stop offset="55%" stopColor="rgba(140,58,39,0.55)" />
          <stop offset="100%" stopColor="rgba(64,18,18,0)" />
        </radialGradient>
        <radialGradient id="sphereGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="rgba(166,55,45,0.4)" />
          <stop offset="100%" stopColor="rgba(166,55,45,0)" />
        </radialGradient>
        <filter id="sphereBlur"><feGaussianBlur stdDeviation="20" /></filter>
        <filter id="ringGlow"><feGaussianBlur stdDeviation="2.5" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
      </defs>

      {/* Outer glow */}
      <circle cx={cx} cy={cy} r={130} fill="url(#sphereGlow)" filter="url(#sphereBlur)" />

      {/* Orbital ring 1 — wide, nearly flat */}
      <motion.ellipse cx={cx} cy={cy} rx={175} ry={48}
        fill="none" stroke="rgba(140,58,39,0.65)" strokeWidth="1.5"
        filter="url(#ringGlow)"
        animate={{ rotateZ: [0, 360] }} transition={{ duration: 28, repeat: Infinity, ease: "linear" }}
      />
      {/* Orbital ring 2 — tilted */}
      <motion.ellipse cx={cx} cy={cy} rx={145} ry={95}
        fill="none" stroke="rgba(1,17,38,0.55)" strokeWidth="1.5"
        style={{ transformOrigin: `${cx}px ${cy}px`, rotate: "45deg" }}
        animate={{ rotateZ: [45, 405] }} transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
      />
      {/* Orbital ring 3 — angled */}
      <motion.ellipse cx={cx} cy={cy} rx={118} ry={30}
        fill="none" stroke="rgba(166,55,45,0.5)" strokeWidth="1.5"
        style={{ transformOrigin: `${cx}px ${cy}px`, rotate: "-30deg" }}
        animate={{ rotateZ: [-30, 330] }} transition={{ duration: 16, repeat: Infinity, ease: "linear" }}
      />

      {/* Central sphere */}
      <circle cx={cx} cy={cy} r={96} fill="url(#sphereGrad)" />
      {/* Inner highlight */}
      <ellipse cx={cx - 28} cy={cy - 28} rx={32} ry={22} fill="rgba(255,255,255,0.12)" />

      {/* Orbital particles */}
      {[0, 60, 120, 180, 240, 300, 40, 100, 160, 220, 280, 340].map((angle, i) => {
        const rad = (angle * Math.PI) / 180;
        const rx = i < 6 ? 175 : 118, ry = i < 6 ? 48 : 30;
        const px = cx + rx * Math.cos(rad), py = cy + ry * Math.sin(rad);
        const isLarge = i % 5 === 0;
        return (
          <motion.circle
            key={i}
            cx={px} cy={py}
            r={isLarge ? 4 : 2.5}
            fill="rgba(255,255,255,0.85)"
            animate={{ opacity: [0.5, 1, 0.5], r: [isLarge ? 3.5 : 2, isLarge ? 5 : 3.5, isLarge ? 3.5 : 2] }}
            transition={{ duration: 2 + i * 0.3, repeat: Infinity, ease: "easeInOut" }}
          />
        );
      })}
    </svg>
  );
}

// ═══════════════════════════
// MAIN HOME PAGE
// ═══════════════════════════

export default function Home() {
  const { scrollYProgress } = useScroll();
  const progressWidth = useTransform(scrollYProgress, [0, 1], ["0%", "100%"]);
  const scrollHintOp  = useTransform(scrollYProgress, [0, 0.04], [1, 0]);

  return (
    <div style={{ background: T.bgPage, position: "relative" }}>
      <Navbar />
      <AnimatedGradientBg />
      <FloatingParticles />
      <NoiseOverlay />
      <HeroSection />
      <HowItWorksScrollStory />
      <FeaturesSection />
      <PricingSection />
      <ContactSection />

      {/* Scroll indicator */}
      <motion.div
        style={{ opacity: scrollHintOp, position: "fixed", bottom: 32, left: "50%", transform: "translateX(-50%)", zIndex: 50, display: "flex", flexDirection: "column", alignItems: "center", gap: 6, pointerEvents: "none" }}
      >
        <motion.div style={{ width: 1, height: 44, background: `linear-gradient(to bottom, transparent, ${T.red}, transparent)` }}
          animate={{ scaleY: [0.5, 1, 0.5], opacity: [0.3, 1, 0.3] }}
          transition={{ duration: 2, repeat: Infinity }} />
        <span style={{ fontSize: 8, letterSpacing: "0.3em", textTransform: "uppercase", color: `${T.red}80`, fontFamily: F.sans }}>scroll</span>
        <ChevronDown size={14} color={`${T.red}60`} />
      </motion.div>

      {/* Progress bar */}
      <motion.div style={{ position: "fixed", bottom: 0, left: 0, height: 2, zIndex: 100, width: progressWidth, background: T.grad }} />
    </div>
  );
}

// ═══════════════════════════
// 1. HERO
// ═══════════════════════════
function HeroSection() {
  const { isMobile } = useViewportFlags();
  const stats = [
    { val: "300+", label: "Jobs", delay: 0 },
    { val: "10",   label: "Categories", delay: 0.1 },
    { val: "87%",  label: "Placement", delay: 0.2 },
    { val: "2hr",  label: "Refresh", delay: 0.3 },
  ];

  return (
    <section style={{ minHeight: "100svh", paddingTop: 64, display: "flex", flexDirection: "column", background: T.bgPage, position: "relative", overflow: "hidden" }}>
      {/* Decorative grid overlay */}
      <div style={{
        position: "absolute",
        inset: 0,
        backgroundImage: `linear-gradient(rgba(242,238,179,0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(242,238,179,0.02) 1px, transparent 1px)`,
        backgroundSize: "60px 60px",
        opacity: 0.3,
        pointerEvents: "none",
      }} />

      {/* Animated orbital sphere background */}
      <motion.div
        animate={{
          rotate: [0, 360],
          scale: [1, 1.05, 1],
        }}
        transition={{ duration: 40, repeat: Infinity, ease: "linear" }}
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          opacity: 0.08,
          pointerEvents: "none",
        }}
      >
        <OrbitalSphere size={680} />
      </motion.div>

      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: isMobile ? "40px 18px 28px" : "0 32px", position: "relative", zIndex: 2 }}>
        <div style={{ maxWidth: 780, width: "100%", textAlign: "center" }}>
          {/* Status badge */}
          <motion.div
            initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.1 }}
            style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "8px 16px", borderRadius: 9999, marginBottom: 28, background: "rgba(166,55,45,0.08)", border: "1px solid rgba(166,55,45,0.25)" }}
          >
            <motion.div
              animate={{ scale: [1, 1.4, 1], opacity: [1, 0.6, 1] }}
              transition={{ duration: 1.8, repeat: Infinity }}
              style={{ width: 6, height: 6, borderRadius: "50%", background: T.red, boxShadow: `0 0 6px ${T.red}` }}
            />
            <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: T.burnt, fontFamily: F.sans }}>
              Now Serving OPT · STEM OPT · H-1B Students
            </span>
          </motion.div>

          {/* Headline */}
          <div style={{ marginBottom: 24 }}>
            <RevealLine delay={0.18}>
              <h1 style={{ fontFamily: F.sans, fontSize: "clamp(48px, 7vw, 80px)", fontWeight: 800, lineHeight: 1.06, letterSpacing: "-0.025em", color: T.text }}>
                Land Your
              </h1>
            </RevealLine>
            <RevealLine delay={0.30}>
              <h1 style={{ fontFamily: F.sans, fontSize: "clamp(48px, 7vw, 80px)", fontWeight: 800, lineHeight: 1.06, letterSpacing: "-0.025em", background: T.grad, WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
                Dream Job
              </h1>
            </RevealLine>
            <RevealLine delay={0.42}>
              <h1 style={{ fontFamily: F.sans, fontSize: "clamp(48px, 7vw, 80px)", fontWeight: 800, lineHeight: 1.06, letterSpacing: "-0.025em", color: T.text }}>
                in the US & Canada
              </h1>
            </RevealLine>
          </div>

          {/* Subheading */}
          <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.8, delay: 0.65 }}
            style={{ fontSize: 17, lineHeight: 1.75, color: T.t2, fontFamily: F.sans, fontWeight: 400, maxWidth: 560, margin: "0 auto 40px" }}>
            AI-powered job matching with real-time ATS scoring, hiring manager contacts, and visa-aware filtering — built exclusively for international students.
          </motion.p>

          {/* CTA Buttons */}
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.85 }}
            style={{ display: "flex", gap: 14, marginBottom: 56, flexWrap: "wrap", justifyContent: "center" }}>
            <motion.div
              whileHover={{ scale: 1.05, boxShadow: "0 0 40px rgba(166,55,45,0.6)" }}
              whileTap={{ scale: 0.98 }}
              transition={{ duration: 0.2 }}
            >
              <Link to="/signup" style={{
                display: "inline-flex", alignItems: "center", gap: 8,
                padding: "14px 28px", borderRadius: 12, background: T.grad,
                color: "#fff", fontSize: 15, fontWeight: 700, fontFamily: F.sans,
                textDecoration: "none", boxShadow: `0 0 28px rgba(166,55,45,0.4)`,
              }}>
                Get Started Free <motion.div
                  animate={{ x: [0, 4, 0] }}
                  transition={{ duration: 1.5, repeat: Infinity }}
                >
                  <ArrowRight size={16} />
                </motion.div>
              </Link>
            </motion.div>
            <motion.button
              whileHover={{ scale: 1.03, borderColor: "rgba(166,55,45,0.4)" }}
              whileTap={{ scale: 0.98 }}
              transition={{ duration: 0.2 }}
              onClick={() => document.getElementById("how-it-works")?.scrollIntoView({ behavior: "smooth" })}
              style={{
                display: "inline-flex", alignItems: "center", gap: 8,
                padding: "14px 24px", borderRadius: 12,
                background: "rgba(242,238,179,0.04)",
                border: "1px solid rgba(242,238,179,0.12)",
                color: T.text, fontSize: 15, fontFamily: F.sans, fontWeight: 500,
                cursor: "pointer",
              }}>
              How It Works
            </motion.button>
          </motion.div>

          {/* Stats row */}
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", justifyContent: "center" }}>
            {stats.map((s) => (
              <motion.div
                key={s.label}
                initial={{ opacity: 0, y: 20, scale: 0.9 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.6, delay: 1.1 + s.delay, ease: [0.25, 0.46, 0.45, 0.94] }}
              >
                <GlassCard style={{ padding: "16px 20px", textAlign: "center", minWidth: 100 }} hoverY={-6}>
                  <motion.div
                    initial={{ scale: 0.8, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    transition={{ duration: 0.5, delay: 1.3 + s.delay }}
                    style={{ fontFamily: F.sans, fontSize: 24, fontWeight: 800, lineHeight: 1, background: T.grad, WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", marginBottom: 4 }}
                  >
                    {s.val}
                  </motion.div>
                  <div style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>{s.label}</div>
                </GlassCard>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

// ═══════════════════════════
// 3. FEATURES
// ═══════════════════════════
const features = [
  { icon: Shield,   emoji: "🛡",  title: "Visa-Aware Matching",       desc: "Filter by F1-CPT, F1-OPT, STEM OPT, H-1B. Every listing is verified for sponsorship status." },
  { icon: Target,   emoji: "🎯",  title: "Real-Time ATS Scoring",     desc: "Know your match score before applying. Full keyword gap analysis included." },
  { icon: Users,    emoji: "👤",  title: "Hiring Manager Contacts",   desc: "Direct email + LinkedIn of the person who can hire you — per listing." },
  { icon: BarChart3,emoji: "📊",  title: "Application Tracker",       desc: "Full history of applications, dates, and status — all in one clean dashboard." },
  { icon: Bell,     emoji: "🔔",  title: "Smart Email Alerts",        desc: "Daily top 10 matches. OPT/H-1B filtered. Never miss the perfect opportunity." },
  { icon: Mic,      emoji: "🎤",  title: "Mock Interview Sessions",   desc: "Elite members get weekly 1:1 with top US recruiters. Practice every round." },
];

function FeaturesSection() {
  const { isMobile } = useViewportFlags();
  return (
    <section id="features" style={{ minHeight: "100vh", paddingTop: 80, paddingBottom: 80, display: "flex", alignItems: "center", background: T.bgPage, position: "relative" }}>
      {/* Decorative background elements */}
      <div style={{
        position: "absolute",
        top: "20%",
        left: "10%",
        width: "300px",
        height: "300px",
        borderRadius: "50%",
        background: "radial-gradient(circle, rgba(166,55,45,0.08) 0%, transparent 70%)",
        filter: "blur(60px)",
        pointerEvents: "none",
      }} />
      <div style={{
        position: "absolute",
        bottom: "15%",
        right: "15%",
        width: "400px",
        height: "400px",
        borderRadius: "50%",
        background: "radial-gradient(circle, rgba(140,58,39,0.06) 0%, transparent 70%)",
        filter: "blur(70px)",
        pointerEvents: "none",
      }} />

      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "0 32px", width: "100%", position: "relative", zIndex: 1 }}>
        <SectionReveal delay={0}><SectionLabel text="Features" /></SectionReveal>
        <SectionReveal delay={0.1}>
          <h2 style={{ fontFamily: F.sans, fontWeight: 700, fontSize: "clamp(28px, 4vw, 48px)", lineHeight: 1.1, letterSpacing: "-0.015em", textAlign: "center", color: T.text, marginBottom: 48 }}>
            Everything You Need to <GradText>Get Hired</GradText>
          </h2>
        </SectionReveal>
        <div style={{ display: "grid", gridTemplateColumns: `repeat(auto-fit, minmax(${isMobile ? "240px" : "300px"}, 1fr))`, gap: 18 }}>
          {features.map((f, i) => (
            <SectionReveal key={f.title} delay={0.15 + i * 0.07} y={30}>
              <GlassCard style={{ padding: 28, height: "100%" }}>
                <motion.div
                  animate={{
                    rotate: [0, 10, -10, 0],
                    scale: [1, 1.1, 1],
                  }}
                  transition={{ duration: 3, delay: i * 0.2, repeat: Infinity, repeatDelay: 5 }}
                  style={{ fontSize: 32, marginBottom: 16, display: "inline-block" }}
                >
                  {f.emoji}
                </motion.div>
                <h3 style={{ fontFamily: F.sans, fontSize: 17, fontWeight: 600, color: T.text, marginBottom: 10 }}>{f.title}</h3>
                <p style={{ fontSize: 14, lineHeight: 1.7, color: T.t2, fontFamily: F.sans }}>{f.desc}</p>
              </GlassCard>
            </SectionReveal>
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
    name: "Basic", price: "$9.99", period: "/mo", desc: "Core tools to start your search",
    badge: null, featured: false, borderColor: T.border,
    features: [
      ["ATS Score (5/mo)", true], ["Basic Job Alerts", true], ["Public Visa Data", true],
      ["1 Resume Upload", true], ["Community Support", true],
      ["Hiring Manager Contacts", false], ["One-Click Apply", false],
    ],
    cta: "Start Basic", ctaLink: "/signup",
  },
  {
    name: "Pro", price: "$15.99", period: "/mo", desc: "For serious international job seekers",
    badge: "Most Popular", featured: true, borderColor: T.red,
    features: [
      ["Unlimited ATS Scoring", true], ["Smart Daily Alerts", true], ["Full Visa Tracker", true],
      ["5 Resume Versions", true], ["Hiring Manager Contacts", true],
      ["One-Click Apply (50+ boards)", true], ["Career Analytics Dashboard", true],
    ],
    cta: "Go Pro →", ctaLink: "/signup",
  },
  {
    name: "Elite", price: "$45", period: "/mo", desc: "White-glove placement service",
    badge: "Premium", featured: false, borderColor: T.burnt,
    features: [
      ["Everything in Pro", true], ["1:1 Career Coaching", true], ["AI Resume Rewrite", true],
      ["Mock Interview Sessions", true], ["Salary Negotiation Tools", true],
      ["Visa Attorney Access", true], ["Dedicated Account Manager", true],
    ],
    cta: "Go Elite", ctaLink: "/signup",
  },
];

function PricingSection() {
  const { isMobile } = useViewportFlags();
  return (
    <section id="pricing" style={{ minHeight: "100vh", paddingTop: 80, paddingBottom: 80, display: "flex", flexDirection: "column", alignItems: "center", background: T.bgPage, position: "relative" }}>
      {/* Decorative background */}
      <motion.div
        animate={{
          scale: [1, 1.1, 1],
          opacity: [0.05, 0.08, 0.05],
        }}
        transition={{ duration: 12, repeat: Infinity }}
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          width: "600px",
          height: "600px",
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(166,55,45,0.15) 0%, transparent 60%)",
          filter: "blur(80px)",
          pointerEvents: "none",
        }}
      />

      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "0 32px", width: "100%", position: "relative", zIndex: 1 }}>
        <SectionReveal delay={0}><SectionLabel text="Pricing" /></SectionReveal>
        <SectionReveal delay={0.1}>
          <h2 style={{ fontFamily: F.sans, fontWeight: 700, fontSize: "clamp(28px, 4vw, 48px)", lineHeight: 1.1, letterSpacing: "-0.015em", textAlign: "center", color: T.text, marginBottom: 10 }}>
            Simple, <GradText>Transparent</GradText> Pricing
          </h2>
        </SectionReveal>
        <SectionReveal delay={0.15}>
          <p style={{ textAlign: "center", fontSize: 14, color: T.t3, fontFamily: F.sans, marginBottom: 44, lineHeight: 1.7 }}>
            Cancel anytime. No credit card required to get started.
          </p>
        </SectionReveal>

        <div style={{ display: "grid", gridTemplateColumns: `repeat(auto-fit, minmax(${isMobile ? "240px" : "300px"}, 1fr))`, gap: 20 }}>
          {plans.map((plan, i) => (
            <SectionReveal key={plan.name} delay={0.2 + i * 0.1} y={40}>
              <div style={{ position: "relative", paddingTop: plan.badge ? 16 : 0 }}>
                {plan.badge && (
                  <div style={{ position: "absolute", top: 0, left: "50%", transform: "translateX(-50%)", padding: "5px 14px", borderRadius: 9999, background: T.grad, color: "#fff", fontSize: 10, fontWeight: 700, fontFamily: F.sans, whiteSpace: "nowrap", boxShadow: "0 4px 16px rgba(166,55,45,0.4)", zIndex: 2 }}>
                    ⭐ {plan.badge}
                  </div>
                )}
                <GlassCard style={{
                  padding: "36px 28px",
                  border: `1px solid ${plan.borderColor}`,
                  boxShadow: plan.featured ? `${T.shadow}, ${T.glow}` : T.shadow,
                }}>
                  <div style={{ marginBottom: 6 }}>
                    <span style={{ fontFamily: F.sans, fontSize: 18, fontWeight: 700, color: T.text }}>{plan.name}</span>
                  </div>
                  <p style={{ fontSize: 13, color: T.t3, fontFamily: F.sans, marginBottom: 20, lineHeight: 1.5 }}>{plan.desc}</p>
                  <div style={{ display: "flex", alignItems: "flex-end", gap: 4, marginBottom: 24 }}>
                    <span style={{ fontFamily: F.sans, fontSize: 48, fontWeight: 800, lineHeight: 1, color: T.text }}>{plan.price}</span>
                    <span style={{ fontSize: 14, color: T.t3, marginBottom: 6, fontFamily: F.sans }}>{plan.period}</span>
                  </div>
                  <motion.div
                    whileHover={{ scale: 1.02, boxShadow: plan.featured ? "0 12px 32px rgba(166,55,45,0.5)" : "0 4px 16px rgba(242,238,179,0.1)" }}
                    whileTap={{ scale: 0.98 }}
                    transition={{ duration: 0.2 }}
                  >
                    <Link to={plan.ctaLink} style={{
                      display: "block", textAlign: "center", padding: "13px",
                      borderRadius: 12, marginBottom: 24,
                      background: plan.featured ? T.grad : "rgba(242,238,179,0.06)",
                      border: plan.featured ? "none" : `1px solid ${T.border}`,
                      color: "#fff", fontSize: 14, fontWeight: 600, fontFamily: F.sans,
                      textDecoration: "none",
                      boxShadow: plan.featured ? "0 8px 24px rgba(166,55,45,0.35)" : "none",
                    }}>{plan.cta}</Link>
                  </motion.div>
                  <ul style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {(plan.features as [string, boolean][]).map(([feat, included]) => (
                      <li key={feat} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <div style={{ width: 18, height: 18, borderRadius: "50%", background: included ? "rgba(166,55,45,0.15)" : "rgba(242,238,179,0.04)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, border: included ? "1px solid rgba(166,55,45,0.3)" : "1px solid rgba(242,238,179,0.06)" }}>
                          {included ? <Check size={10} color={T.red} /> : <span style={{ fontSize: 10, color: T.t3 }}>—</span>}
                        </div>
                        <span style={{ fontSize: 13, color: included ? T.t2 : T.t3, fontFamily: F.sans, lineHeight: 1.4, opacity: included ? 1 : 0.55 }}>{feat}</span>
                      </li>
                    ))}
                  </ul>
                </GlassCard>
              </div>
            </SectionReveal>
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

  return (
    <section id="contact" style={{ minHeight: "100vh", display: "flex", flexDirection: "column", paddingTop: 64, background: T.bgPage, position: "relative" }}>
      {/* Decorative elements */}
      <div style={{
        position: "absolute",
        top: "30%",
        left: "5%",
        width: "350px",
        height: "350px",
        borderRadius: "50%",
        background: "radial-gradient(circle, rgba(140,58,39,0.1) 0%, transparent 65%)",
        filter: "blur(70px)",
        pointerEvents: "none",
      }} />
      <div style={{
        position: "absolute",
        bottom: "20%",
        right: "10%",
        width: "300px",
        height: "300px",
        borderRadius: "50%",
        background: "radial-gradient(circle, rgba(166,55,45,0.08) 0%, transparent 65%)",
        filter: "blur(60px)",
        pointerEvents: "none",
      }} />

      <div style={{ flex: 1, padding: "48px 32px 0", position: "relative", zIndex: 1 }}>
        <div style={{ maxWidth: 1100, margin: "0 auto" }}>
          <SectionReveal delay={0}><SectionLabel text="Contact" /></SectionReveal>
          <SectionReveal delay={0.1}>
            <h2 style={{ fontFamily: F.sans, fontWeight: 700, fontSize: "clamp(28px, 4vw, 48px)", lineHeight: 1.1, letterSpacing: "-0.015em", textAlign: "center", color: T.text, marginBottom: 40 }}>
              Get in <GradText>Touch</GradText>
            </h2>
          </SectionReveal>

          <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1.4fr", gap: 24, marginBottom: 48 }}>
            {/* Contact info */}
            <SectionReveal delay={0.2}>
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                {[
                  { icon: Mail, label: "Email", value: "hello@placeup.career" },
                  { icon: Globe, label: "Website", value: "www.placeup.career" },
                  { icon: Phone, label: "Phone", value: "+1 (800) 555-0199" },
                  { icon: MapPin, label: "Address", value: "New York, NY 10001" },
                ].map((item) => (
                  <GlassCard key={item.label} style={{ padding: "20px 22px" }} hoverY={-4}>
                    <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                      <div style={{ width: 40, height: 40, borderRadius: 10, background: T.grad, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                        <item.icon size={16} color="#fff" />
                      </div>
                      <div>
                        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: T.t3, fontFamily: F.sans, marginBottom: 2 }}>{item.label}</div>
                        <div style={{ fontSize: 14, color: T.text, fontFamily: F.sans, fontWeight: 500 }}>{item.value}</div>
                      </div>
                    </div>
                  </GlassCard>
                ))}
              </div>
            </SectionReveal>

            {/* Contact form */}
            <SectionReveal delay={0.3}>
              <GlassCard style={{ padding: 28 }}>
                <AnimatePresence mode="wait">
                  {sent ? (
                    <motion.div key="success" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}
                      style={{ textAlign: "center", padding: "40px 0" }}>
                      <div style={{ fontSize: 40, marginBottom: 16 }}>🎉</div>
                      <div style={{ fontFamily: F.sans, fontSize: 18, fontWeight: 600, color: T.text, marginBottom: 8 }}>Message Sent!</div>
                      <div style={{ fontSize: 14, color: T.t2, fontFamily: F.sans }}>We'll get back to you within 24 hours.</div>
                    </motion.div>
                  ) : (
                    <motion.div key="form">
                      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 14, marginBottom: 14 }}>
                        <input placeholder="Full Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                          style={{ padding: "12px 14px", borderRadius: 12, border: `1px solid ${T.border}`, background: "rgba(242,238,179,0.04)", color: T.text, fontSize: 14, fontFamily: F.sans, outline: "none", transition: "border-color 0.3s, background 0.3s" }}
                          onFocus={(e) => { e.currentTarget.style.borderColor = "rgba(166,55,45,0.4)"; e.currentTarget.style.background = "rgba(242,238,179,0.06)"; }}
                          onBlur={(e) => { e.currentTarget.style.borderColor = T.border; e.currentTarget.style.background = "rgba(242,238,179,0.04)"; }}
                        />
                        <input placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })}
                          style={{ padding: "12px 14px", borderRadius: 12, border: `1px solid ${T.border}`, background: "rgba(242,238,179,0.04)", color: T.text, fontSize: 14, fontFamily: F.sans, outline: "none", transition: "border-color 0.3s, background 0.3s" }}
                          onFocus={(e) => { e.currentTarget.style.borderColor = "rgba(166,55,45,0.4)"; e.currentTarget.style.background = "rgba(242,238,179,0.06)"; }}
                          onBlur={(e) => { e.currentTarget.style.borderColor = T.border; e.currentTarget.style.background = "rgba(242,238,179,0.04)"; }}
                        />
                      </div>
                      <select value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })}
                        style={{ width: "100%", padding: "12px 14px", borderRadius: 12, border: `1px solid ${T.border}`, background: "rgba(1,17,38,0.85)", color: form.subject ? T.text : T.t3, fontSize: 14, fontFamily: F.sans, marginBottom: 14, outline: "none", appearance: "none", transition: "border-color 0.3s" }}
                        onFocus={(e) => { e.currentTarget.style.borderColor = "rgba(166,55,45,0.4)"; }}
                        onBlur={(e) => { e.currentTarget.style.borderColor = T.border; }}
                      >
                        <option value="">Subject</option>
                        <option>General Inquiry</option>
                        <option>Technical Support</option>
                        <option>Billing</option>
                        <option>Partnership</option>
                      </select>
                      <textarea placeholder="Your message..." value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })}
                        style={{ width: "100%", height: 110, padding: "12px 14px", borderRadius: 12, border: `1px solid ${T.border}`, background: "rgba(242,238,179,0.04)", color: T.text, fontSize: 14, fontFamily: F.sans, resize: "none", outline: "none", marginBottom: 14, transition: "border-color 0.3s, background 0.3s" }}
                        onFocus={(e) => { e.currentTarget.style.borderColor = "rgba(166,55,45,0.4)"; e.currentTarget.style.background = "rgba(242,238,179,0.06)"; }}
                        onBlur={(e) => { e.currentTarget.style.borderColor = T.border; e.currentTarget.style.background = "rgba(242,238,179,0.04)"; }}
                      />
                      <motion.button
                        whileTap={{ scale: 0.96 }}
                        whileHover={{ scale: 1.02, boxShadow: "0 0 32px rgba(166,55,45,0.5)" }}
                        onClick={() => form.name && form.email && setSent(true)}
                        transition={{ duration: 0.2 }}
                        style={{ width: "100%", padding: "14px", borderRadius: 12, border: "none", cursor: "pointer", background: T.grad, color: "#fff", fontSize: 15, fontWeight: 600, fontFamily: F.sans, display: "flex", alignItems: "center", justifyContent: "center", gap: 8, boxShadow: "0 0 24px rgba(166,55,45,0.35)" }}>
                        Send Message <motion.div
                          animate={{ x: [0, 3, 0] }}
                          transition={{ duration: 1.2, repeat: Infinity }}
                        >
                          <Send size={15} />
                        </motion.div>
                      </motion.button>
                    </motion.div>
                  )}
                </AnimatePresence>
              </GlassCard>
            </SectionReveal>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div style={{ flexShrink: 0, borderTop: "1px solid rgba(242,238,179,0.06)", padding: "14px 32px" }}>
        <div style={{ maxWidth: 1100, margin: "0 auto", display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 22, height: 22, borderRadius: 6, background: T.grad, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <span style={{ color: "#fff", fontSize: 9, fontWeight: 800, fontFamily: F.sans }}>P</span>
            </div>
            <span style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 13, color: T.t2 }}>PlaceUp Career</span>
          </div>
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
            {["Product", "Privacy", "Terms", "GDPR"].map((l) => (
              <a key={l} href="#" style={{ fontSize: 11, color: T.t3, textDecoration: "none", fontFamily: F.sans }}>{l}</a>
            ))}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <span style={{ fontSize: 11, color: T.t3, fontFamily: F.sans }}>© 2026 PlaceUp Career</span>
            {[Github, Twitter, Linkedin].map((Icon, i) => (
              <a key={i} href="#" style={{ color: T.t3 }}><Icon size={14} /></a>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
