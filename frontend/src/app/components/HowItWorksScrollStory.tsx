import { useState, useRef, useEffect } from "react";
import {
  motion, AnimatePresence,
  useScroll, useTransform, useSpring,
  useMotionValue, useMotionValueEvent,
  MotionValue,
} from "motion/react";
import { Check, MapPin, Mail, ChevronRight } from "lucide-react";

// ─── Tokens ───
const T = {
  bg:     "#011126",
  border: "rgba(242,238,179,0.08)",
  text:   "#F2EEB3",
  t2:     "rgba(242,238,179,0.65)",
  t3:     "rgba(242,238,179,0.38)",
  grad:   "linear-gradient(135deg, #F2A341, #ED7D2B, #C75A12)",
  red:    "#ED7D2B",
};
const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };

// ─── Story steps ───
const STEPS = [
  {
    num: "01", icon: "🔐",
    eyebrow: "Secure Sign In",
    title: "Your personalized\njob hub awaits",
    desc: "One-click access to your AI-powered visa-aware matching dashboard.",
  },
  {
    num: "02", icon: "📋",
    eyebrow: "Real-Time Feed",
    title: "47 new H-1B matches\nin the last 24 hours",
    desc: "Visa-verified roles from top tech companies, ranked by your ATS fit score.",
  },
  {
    num: "03", icon: "🎯",
    eyebrow: "Smart Selection",
    title: "Your #1 match:\nGoogle Senior SWE",
    desc: "94% ATS compatibility — one role that could change your career trajectory.",
  },
  {
    num: "04", icon: "📊",
    eyebrow: "Instant Analysis",
    title: "ATS breakdown +\napplication tracking",
    desc: "Keyword gaps, match score, and the direct email of the person who can hire you.",
  },
  {
    num: "05", icon: "🚀",
    eyebrow: "One-Click Apply",
    title: "Submitted to Google\nin 8 seconds flat",
    desc: "Your optimised resume delivered. Application tracker updated automatically.",
  },
  {
    num: "06", icon: "🎉",
    eyebrow: "It worked.",
    title: "Interview request\nreceived from Google",
    desc: "Congratulations — an interview has been scheduled. Check your inbox.",
  },
];

// ─── Job data ───
const JOBS = [
  { id: 1, title: "Senior Software Engineer", company: "Google", abbr: "G", color: "#4285F4", visa: "H-1B", ats: 94, location: "Mountain View, CA", tags: ["React", "Python", "K8s"] },
  { id: 2, title: "ML Engineer",              company: "Meta",   abbr: "M", color: "#1877F2", visa: "H-1B", ats: 87, location: "Menlo Park, CA",    tags: ["PyTorch", "CUDA", "LLMs"] },
  { id: 3, title: "Backend Engineer",         company: "Stripe", abbr: "S", color: "#635BFF", visa: "OPT",  ats: 91, location: "San Francisco, CA", tags: ["Go", "Ruby", "Kafka"] },
  { id: 4, title: "Software Engineer II",     company: "Amazon", abbr: "A", color: "#FF9900", visa: "H-1B", ats: 89, location: "Seattle, WA",       tags: ["Java", "AWS", "DynamoDB"] },
];

// ─── Step thresholds (step i starts at i/6) ───
const S = (i: number) => i / 6;

function getStep(v: number) { return Math.min(5, Math.floor(v * 6)); }

// ═══════════════════════
// BACKGROUND LAYERS
// ═══════════════════════

const GLOWS = [
  "radial-gradient(ellipse 70% 60% at 50% 55%, rgba(140,58,39,0.10) 0%, transparent 70%)",
  "radial-gradient(ellipse 70% 60% at 50% 55%, rgba(237,125,43,0.14) 0%, transparent 70%)",
  "radial-gradient(ellipse 70% 60% at 50% 55%, rgba(237,125,43,0.18) 0%, transparent 70%)",
  "radial-gradient(ellipse 70% 60% at 50% 55%, rgba(140,58,39,0.14) 0%, transparent 70%)",
  "radial-gradient(ellipse 70% 60% at 50% 55%, rgba(34,197,94,0.06) 0%, transparent 70%)",
  "radial-gradient(ellipse 70% 60% at 50% 55%, rgba(34,197,94,0.12) 0%, transparent 70%)",
];

function BackgroundLayers({ step }: { step: number }) {
  return (
    <>
      {/* Static dark base */}
      <div style={{ position: "absolute", inset: 0, background: T.bg, zIndex: 0 }} />
      {/* Radial glow per step */}
      <motion.div
        animate={{ background: GLOWS[step] }}
        transition={{ duration: 1.2 }}
        style={{ position: "absolute", inset: 0, zIndex: 1, pointerEvents: "none" }}
      />
      {/* Large watermark number */}
      <div style={{
        position: "absolute", inset: 0, zIndex: 2, display: "flex",
        alignItems: "center", justifyContent: "center", pointerEvents: "none", overflow: "hidden",
      }}>
        <AnimatePresence mode="wait">
          <motion.span
            key={step}
            initial={{ opacity: 0, scale: 0.88, y: 16 }}
            animate={{ opacity: 0.038, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 1.06, y: -12 }}
            transition={{ duration: 0.55 }}
            style={{
              fontSize: "clamp(160px, 28vw, 360px)", fontWeight: 800,
              color: step >= 4 ? "#22c55e" : T.red,
              fontFamily: F.sans, lineHeight: 1, userSelect: "none",
            }}
          >
            {STEPS[step].num}
          </motion.span>
        </AnimatePresence>
      </div>
    </>
  );
}

// ═══════════════════════
// TOP BAR
// ═══════════════════════

function TopBar({ step, sectionProgress }: { step: number; sectionProgress: MotionValue<string> }) {
  return (
    <div style={{
      flexShrink: 0, height: 52,
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "0 32px", position: "relative", zIndex: 10,
    }}>
      {/* Label */}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ height: 1, width: 20, background: T.red }} />
        <span style={{ fontFamily: F.sans, fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase" as const, color: T.red }}>
          How It Works
        </span>
      </div>

      {/* Step dots */}
      <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
        {STEPS.map((_, i) => (
          <motion.div
            key={i}
            animate={{
              width: step === i ? 20 : 6,
              background: step === i ? T.red : step > i ? "#22c55e" : "rgba(242,238,179,0.18)",
            }}
            transition={{ duration: 0.35 }}
            style={{ height: 5, borderRadius: 3 }}
          />
        ))}
      </div>

      {/* Counter */}
      <AnimatePresence mode="wait">
        <motion.span
          key={step}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.3 }}
          style={{ fontFamily: F.mono, fontSize: 11, color: T.t3 }}
        >
          {STEPS[step].num} / 06
        </motion.span>
      </AnimatePresence>
    </div>
  );
}

// ═══════════════════════
// STEP HEADER
// ═══════════════════════

function StepHeader({ step }: { step: number }) {
  const s = STEPS[step];
  return (
    <div style={{ textAlign: "center", padding: "0 24px", flexShrink: 0 }}>
      <AnimatePresence mode="wait">
        <motion.div
          key={step}
          initial={{ opacity: 0, y: 22, filter: "blur(6px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          exit={{ opacity: 0, y: -18, filter: "blur(4px)" }}
          transition={{ duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94] }}
        >
          {/* Eyebrow */}
          <div style={{
            display: "inline-flex", alignItems: "center", gap: 7, marginBottom: 10,
            padding: "4px 12px", borderRadius: 99,
            background: "rgba(237,125,43,0.10)", border: "1px solid rgba(237,125,43,0.22)",
          }}>
            <span style={{ fontSize: 13 }}>{s.icon}</span>
            <span style={{ fontFamily: F.sans, fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" as const, color: T.red }}>
              {s.eyebrow}
            </span>
          </div>

          {/* Title */}
          <h2 style={{
            fontFamily: F.sans, fontWeight: 800,
            fontSize: "clamp(18px, 2.8vw, 32px)",
            lineHeight: 1.18, letterSpacing: "-0.02em",
            color: T.text, margin: "0 0 8px",
            whiteSpace: "pre-line" as const,
          }}>
            {s.title}
          </h2>

          {/* Desc */}
          <p style={{ fontFamily: F.sans, fontSize: 13, color: T.t2, lineHeight: 1.65, maxWidth: 440, margin: "0 auto" }}>
            {s.desc}
          </p>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

// ═══════════════════════
// BROWSER CONTENT — all scroll-driven
// ═══════════════════════

// ── Login Screen ──
function LoginScreen({ p0 }: { p0: MotionValue<number> }) {
  const EMAIL = "sarah.chen@mit.edu";
  const [typedStr, setTypedStr] = useState("");
  const [phase, setPhase] = useState(0); // 0 typing, 1 done, 2 clicking

  // Scroll drives the typewriter
  const typedCount = useTransform(p0, [0.05, 0.52], [0, EMAIL.length]);
  useMotionValueEvent(typedCount, "change", (v) => {
    setTypedStr(EMAIL.slice(0, Math.round(v)));
    if (Math.round(v) >= EMAIL.length) setPhase(1);
  });

  // Scroll drives button click
  const buttonScale = useTransform(p0, [0.72, 0.78, 0.84, 0.90], [1, 0.96, 1.03, 1]);
  const buttonGlow  = useTransform(p0, [0.72, 0.82], [0, 1]);
  const signingIn   = useTransform(p0, [0.74, 0.78], [0, 1]);
  const [isClicking, setIsClicking] = useState(false);
  useMotionValueEvent(signingIn, "change", (v) => setIsClicking(v > 0.5));

  // Border color driven by scroll – computed as a MotionValue at hook level
  const emailBorderColor = useTransform(
    p0, [0.45, 0.6],
    ["rgba(242,238,179,0.08)", "rgba(237,125,43,0.40)"]
  );
  const buttonBoxShadow = useTransform(
    buttonGlow, [0, 1],
    ["0 0 0px rgba(237,125,43,0)", "0 0 26px rgba(237,125,43,0.6)"]
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.4 }}
      style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", padding: "16px 20px" }}
    >
      <div style={{
        width: "100%", maxWidth: 290,
        background: "rgba(1,17,38,0.92)", backdropFilter: "blur(24px)",
        border: "1px solid rgba(242,238,179,0.09)",
        borderRadius: 18, padding: "24px 20px",
        boxShadow: "0 20px 60px rgba(1,17,38,0.7)",
      }}>
        {/* Logo */}
        <div style={{ textAlign: "center", marginBottom: 18 }}>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <div style={{ width: 24, height: 24, borderRadius: 6, background: T.grad, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <span style={{ fontFamily: F.sans, fontSize: 11, fontWeight: 800, color: "#fff" }}>P</span>
            </div>
            <span style={{ fontFamily: F.sans, fontSize: 13, fontWeight: 700, color: T.text }}>PlaceUp</span>
          </div>
          <p style={{ fontFamily: F.sans, fontSize: 11, color: T.t3, margin: 0 }}>Welcome back 👋</p>
        </div>

        {/* Email */}
        <div style={{ marginBottom: 9 }}>
          <label style={{ display: "block", fontSize: 9, color: T.t3, fontFamily: F.sans, marginBottom: 4, letterSpacing: "0.07em", textTransform: "uppercase" as const }}>Email</label>
          <motion.div
            style={{
              background: "rgba(242,238,179,0.04)",
              borderRadius: 9, padding: "8px 10px",
              border: "1px solid",
              borderColor: emailBorderColor,
            }}
          >
            <span style={{ fontFamily: F.mono, fontSize: 11, color: T.text }}>
              {typedStr}
              {phase === 0 && (
                <motion.span
                  animate={{ opacity: [1, 0, 1] }}
                  transition={{ duration: 0.65, repeat: Infinity }}
                  style={{ display: "inline-block", width: 1.5, height: 10, background: T.red, marginLeft: 1, verticalAlign: "middle" }}
                />
              )}
            </span>
          </motion.div>
        </div>

        {/* Password */}
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: "block", fontSize: 9, color: T.t3, fontFamily: F.sans, marginBottom: 4, letterSpacing: "0.07em", textTransform: "uppercase" as const }}>Password</label>
          <div style={{ background: "rgba(242,238,179,0.04)", border: `1px solid ${T.border}`, borderRadius: 9, padding: "8px 10px" }}>
            <span style={{ fontFamily: F.mono, fontSize: 12, color: T.t3, letterSpacing: "0.07em" }}>••••••••••</span>
          </div>
        </div>

        {/* Button */}
        <motion.div
          style={{
            display: "flex", alignItems: "center", justifyContent: "center", gap: 7,
            background: T.grad, borderRadius: 9, padding: "10px 14px", cursor: "pointer",
            scale: buttonScale,
            boxShadow: buttonBoxShadow,
          }}
        >
          <span style={{ fontFamily: F.sans, fontSize: 12, fontWeight: 700, color: "#fff" }}>
            {isClicking ? "Signing in…" : "Sign In"}
          </span>
          {isClicking && <ChevronRight size={12} color="#fff" />}
        </motion.div>
      </div>
    </motion.div>
  );
}

// ── Live Dot ──
function LiveDot() {
  return (
    <motion.div
      animate={{ scale: [1, 1.5, 1], opacity: [1, 0.5, 1] }}
      transition={{ duration: 1.6, repeat: Infinity }}
      style={{ width: 5, height: 5, borderRadius: "50%", background: "#22c55e", flexShrink: 0 }}
    />
  );
}

// ── Animated Job Card ──
function AnimatedJobCard({ job, p1, p2, index }: {
  job: typeof JOBS[0];
  p1: MotionValue<number>;
  p2: MotionValue<number>;
  index: number;
}) {
  const delay = Math.min(index * 0.18, 0.52);
  const opac  = useTransform(p1, [delay, Math.min(delay + 0.28, 0.9)], [0, 1]);
  const yVal  = useTransform(p1, [delay, Math.min(delay + 0.28, 0.9)], [18, 0]);

  const isSelected = job.id === 1; // Google always selected in step 2+
  const selScale   = useTransform(p2, [0.08, 0.35], [1, isSelected ? 1.025 : 1]);
  const dimOp      = useTransform(p2, [0.08, 0.35], [1, isSelected ? 1 : 0.22]);
  const borderGlow = useTransform(p2, [0.08, 0.40], [0, isSelected ? 1 : 0]);

  const cardScore  = useTransform(p2, [0.08, 0.35], [T.t2, isSelected ? T.red : T.t3]);
  const cardShadow = useTransform(
    borderGlow, [0, 1],
    [`0 0 0 1px rgba(242,238,179,0.08)`, `0 0 0 1px rgba(237,125,43,0.55), 0 0 22px rgba(237,125,43,0.18)`]
  );

  return (
    <motion.div
      style={{
        opacity: opac, y: yVal, scale: selScale,
        position: "relative" as const,
        padding: "9px 11px", borderRadius: 12, cursor: "default",
        background: isSelected ? "rgba(237,125,43,0.09)" : "rgba(242,238,179,0.025)",
      }}
    >
      {/* Animated border via box-shadow */}
      <motion.div
        style={{
          position: "absolute" as const, inset: 0, borderRadius: 12,
          pointerEvents: "none" as const,
          boxShadow: cardShadow,
        }}
      />
      <motion.div style={{ opacity: dimOp, display: "flex", alignItems: "flex-start", gap: 9 }}>
        <div style={{
          width: 32, height: 32, borderRadius: 7, flexShrink: 0,
          background: `${job.color}18`, border: `1px solid ${job.color}35`,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 12, fontWeight: 700, color: job.color, fontFamily: F.sans,
        }}>{job.abbr}</div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 4 }}>
            <span style={{ fontFamily: F.sans, fontSize: 10, fontWeight: 600, color: T.text, lineHeight: 1.3 }}>{job.title}</span>
            <motion.span style={{ fontFamily: F.sans, fontSize: 11, fontWeight: 700, flexShrink: 0, color: cardScore }}>
              {job.ats}%
            </motion.span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 5, marginTop: 2 }}>
            <span style={{ fontFamily: F.sans, fontSize: 9, color: T.t3 }}>{job.company}</span>
            <span style={{ fontSize: 8, color: T.t3 }}>·</span>
            <span style={{ fontFamily: F.sans, fontSize: 9, color: T.t3, display: "flex", alignItems: "center", gap: 2 }}>
              <MapPin size={7} />{job.location}
            </span>
          </div>
          <div style={{ display: "flex", gap: 3, marginTop: 5 }}>
            <div style={{
              padding: "1px 5px", borderRadius: 3,
              background: job.visa === "H-1B" ? "rgba(34,197,94,0.09)" : "rgba(59,130,246,0.09)",
              border: `1px solid ${job.visa === "H-1B" ? "rgba(34,197,94,0.28)" : "rgba(59,130,246,0.28)"}`,
              fontSize: 8, fontWeight: 600, fontFamily: F.sans,
              color: job.visa === "H-1B" ? "#22c55e" : "#60a5fa",
            }}>{job.visa}</div>
            {job.tags.slice(0, 2).map((t) => (
              <div key={t} style={{ padding: "1px 5px", borderRadius: 3, background: "rgba(242,238,179,0.04)", border: `1px solid ${T.border}`, fontSize: 8, color: T.t3, fontFamily: F.sans }}>{t}</div>
            ))}
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

// ── Job Feed Screen ──
function JobFeedScreen({ p1, p2 }: { p1: MotionValue<number>; p2: MotionValue<number> }) {
  const headerOp = useTransform(p1, [0, 0.18], [0, 1]);
  const headerY  = useTransform(p1, [0, 0.18], [14, 0]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.35 }}
      style={{ padding: "12px 12px 8px", height: "100%", display: "flex", flexDirection: "column", overflow: "hidden" }}
    >
      {/* Header */}
      <motion.div style={{ opacity: headerOp, y: headerY, display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 9, flexShrink: 0 }}>
        <div>
          <div style={{ fontFamily: F.sans, fontSize: 11, fontWeight: 600, color: T.text, marginBottom: 3 }}>Job Matches</div>
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <LiveDot />
            <span style={{ fontFamily: F.sans, fontSize: 9, color: "#22c55e" }}>Last 24 hours · 47 new</span>
          </div>
        </div>
        <div style={{ display: "flex", gap: 4 }}>
          {["All", "H-1B", "OPT"].map((f) => (
            <div key={f} style={{
              padding: "2px 7px", borderRadius: 5, fontSize: 8, fontFamily: F.sans, fontWeight: 600,
              background: f === "All" ? "rgba(237,125,43,0.14)" : "rgba(242,238,179,0.03)",
              border: f === "All" ? "1px solid rgba(237,125,43,0.32)" : `1px solid ${T.border}`,
              color: f === "All" ? T.red : T.t3,
            }}>{f}</div>
          ))}
        </div>
      </motion.div>

      {/* Cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: 6, overflowY: "auto", flex: 1 }}>
        {JOBS.map((job, i) => (
          <div key={job.id} style={{ position: "relative" }}>
            <AnimatedJobCard job={job} p1={p1} p2={p2} index={i} />
          </div>
        ))}
      </div>
    </motion.div>
  );
}

// ── ATS Circle (stroke drawn by scroll) ──
function ATSCircle({ p3, size = 70 }: { p3: MotionValue<number>; size?: number }) {
  const r    = size * 0.38;
  const circ = 2 * Math.PI * r;
  const cx = size / 2, cy = size / 2;
  const sw   = size * 0.09;
  const finalOffset = circ - 0.94 * circ;
  const strokeDashoffset = useTransform(p3, [0.05, 0.65], [circ, finalOffset]);

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ display: "block" }}>
      <defs>
        <linearGradient id="atsG3" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#ED7D2B" />
          <stop offset="100%" stopColor="#F2A341" />
        </linearGradient>
      </defs>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(242,238,179,0.06)" strokeWidth={sw} />
      <motion.circle
        cx={cx} cy={cy} r={r} fill="none"
        stroke="url(#atsG3)" strokeWidth={sw} strokeLinecap="round"
        strokeDasharray={circ}
        style={{ strokeDashoffset }}
        transform={`rotate(-90 ${cx} ${cy})`}
      />
      <text x={cx} y={cy + size * 0.07} textAnchor="middle" fill={T.text}
        fontSize={size * 0.22} fontWeight={700} fontFamily={F.sans}>
        94%
      </text>
    </svg>
  );
}

// ── ATS Overlay Card ──
function ATSCard({ p3 }: { p3: MotionValue<number> }) {
  const cardOpac = useTransform(p3, [0, 0.22], [0, 1]);
  const cardX    = useTransform(p3, [0, 0.22], [60, 0]);

  return (
    <motion.div
      style={{
        position: "absolute", bottom: 14, right: 12, zIndex: 20,
        opacity: cardOpac, x: cardX,
        background: "rgba(1,11,28,0.96)", backdropFilter: "blur(24px)",
        border: "1px solid rgba(237,125,43,0.42)", borderRadius: 14,
        padding: "12px 14px", minWidth: 126,
        boxShadow: "0 14px 44px rgba(1,17,38,0.80)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "center", marginBottom: 5 }}>
        <ATSCircle p3={p3} size={68} />
      </div>
      <div style={{ fontFamily: F.sans, fontSize: 8, fontWeight: 700, color: T.t3, textAlign: "center", letterSpacing: "0.08em", textTransform: "uppercase" as const }}>ATS Match</div>
      <div style={{ fontFamily: F.sans, fontSize: 9, color: "#22c55e", textAlign: "center", marginTop: 3, fontWeight: 600 }}>✓ Excellent</div>
    </motion.div>
  );
}

// ── Application Insight Card ──
function HMCard({ p3 }: { p3: MotionValue<number> }) {
  const cardOpac = useTransform(p3, [0.28, 0.55], [0, 1]);
  const cardY    = useTransform(p3, [0.28, 0.55], [-40, 0]);

  return (
    <motion.div
      style={{
        position: "absolute", top: 14, right: 12, zIndex: 20,
        opacity: cardOpac, y: cardY,
        background: "rgba(1,11,28,0.96)", backdropFilter: "blur(24px)",
        border: "1px solid rgba(242,238,179,0.09)",
        borderRadius: 12, padding: "10px 12px", minWidth: 180,
        boxShadow: "0 12px 40px rgba(1,17,38,0.80)",
      }}
    >
      <div style={{ fontFamily: F.sans, fontSize: 8, color: T.t3, letterSpacing: "0.08em", textTransform: "uppercase" as const, marginBottom: 7 }}>Application Fit</div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 9 }}>
        <div style={{
          width: 28, height: 28, borderRadius: "50%", flexShrink: 0,
          background: "rgba(237,125,43,0.18)", border: "1px solid rgba(237,125,43,0.38)",
          display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12,
        }}>👤</div>
        <div>
          <div style={{ fontFamily: F.sans, fontSize: 11, fontWeight: 600, color: T.text }}>Sarah Chen</div>
          <div style={{ fontFamily: F.sans, fontSize: 9, color: T.t3 }}>Eng Manager @ Google</div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 5 }}>
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 3, padding: "5px 7px", borderRadius: 7, background: "rgba(237,125,43,0.14)", border: "1px solid rgba(237,125,43,0.30)" }}>
          <Mail size={8} color={T.red} /><span style={{ fontFamily: F.sans, fontSize: 8, color: T.red, fontWeight: 600 }}>Email</span>
        </div>
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "5px 7px", borderRadius: 7, background: "rgba(242,238,179,0.04)", border: `1px solid ${T.border}` }}>
          <span style={{ fontFamily: F.sans, fontSize: 8, color: T.t3 }}>LinkedIn</span>
        </div>
      </div>
    </motion.div>
  );
}

// ── Apply Overlay ──
function ApplyOverlay({ p4, applied }: { p4: MotionValue<number>; applied: boolean }) {
  const overlayOp = useTransform(p4, [0, 0.2], [0, 1]);
  const overlayY  = useTransform(p4, [0, 0.2], [20, 0]);

  return (
    <motion.div
      style={{
        position: "absolute", bottom: 0, left: 0, right: 0, zIndex: 15,
        opacity: overlayOp, y: overlayY,
        background: "linear-gradient(to top, rgba(1,17,38,1) 55%, transparent)",
        padding: "28px 14px 12px",
      }}
    >
      <motion.div
        animate={applied ? {
          scale: [1, 0.96, 1.02, 1],
          boxShadow: ["0 0 20px rgba(237,125,43,0.4)", "0 0 28px rgba(34,197,94,0.55)", "0 0 18px rgba(34,197,94,0.30)"],
        } : {}}
        transition={{ duration: 0.55 }}
        style={{
          display: "flex", alignItems: "center", justifyContent: "center", gap: 7,
          padding: "11px 18px", borderRadius: 11, cursor: "pointer",
          background: applied ? "linear-gradient(135deg, #15803d, #22c55e)" : T.grad,
          transition: "background 0.4s ease",
          boxShadow: applied ? "0 0 22px rgba(34,197,94,0.35)" : "0 0 22px rgba(237,125,43,0.35)",
        }}
      >
        <AnimatePresence mode="wait">
          {applied ? (
            <motion.span key="done" initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }}
              style={{ fontFamily: F.sans, fontSize: 12, fontWeight: 700, color: "#fff" }}>✓ Submitted</motion.span>
          ) : (
            <motion.span key="apply" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              style={{ fontFamily: F.sans, fontSize: 12, fontWeight: 700, color: "#fff" }}>Apply Now →</motion.span>
          )}
        </AnimatePresence>
      </motion.div>
    </motion.div>
  );
}

// ── Email Toast ──
function EmailToast({ p5 }: { p5: MotionValue<number> }) {
  const toastY  = useTransform(p5, [0.02, 0.30], [-80, 0]);
  const toastOp = useTransform(p5, [0.02, 0.30], [0, 1]);

  return (
    <motion.div
      style={{
        position: "absolute", top: 10, left: 10, right: 10, zIndex: 30,
        y: toastY, opacity: toastOp,
        background: "rgba(2,14,32,0.97)", backdropFilter: "blur(28px)",
        border: "1px solid rgba(34,197,94,0.38)",
        borderRadius: 14, padding: "11px 13px",
        boxShadow: "0 14px 44px rgba(1,17,38,0.90)",
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 9 }}>
        <motion.span
          animate={{ scale: [1, 1.3, 1] }}
          transition={{ duration: 0.5, delay: 0.5, repeat: 2 }}
          style={{ fontSize: 16, flexShrink: 0, lineHeight: 1.3 }}
        >🎉</motion.span>
        <div style={{ flex: 1 }}>
          <div style={{ fontFamily: F.sans, fontSize: 11, fontWeight: 700, color: T.text, marginBottom: 3 }}>Interview Request!</div>
          <div style={{ fontFamily: F.sans, fontSize: 10, color: T.t2, lineHeight: 1.55 }}>
            <strong style={{ color: "#4285F4" }}>Google</strong> – Senior Software Engineer
            <br />Check your email — an interview has been scheduled.
          </div>
        </div>
        <div style={{
          display: "flex", alignItems: "center", gap: 3, padding: "3px 7px",
          borderRadius: 6, background: "rgba(34,197,94,0.10)", border: "1px solid rgba(34,197,94,0.28)", flexShrink: 0,
        }}>
          <Mail size={8} color="#22c55e" />
          <span style={{ fontFamily: F.sans, fontSize: 8, color: "#22c55e", fontWeight: 600 }}>View</span>
        </div>
      </div>
    </motion.div>
  );
}

// ── Composite Mockup Content ──
function MockupContent({
  step, p0, p1, p2, p3, p4, p5, applied,
}: {
  step: number;
  p0: MotionValue<number>; p1: MotionValue<number>; p2: MotionValue<number>;
  p3: MotionValue<number>; p4: MotionValue<number>; p5: MotionValue<number>;
  applied: boolean;
}) {
  const showLogin = step === 0;
  const showFeed  = step >= 1;
  const showATS   = step >= 3;
  const showHM    = step >= 3;
  const showApply = step >= 4;
  const showToast = step >= 5;

  return (
    <div style={{ position: "relative", height: "100%", overflow: "hidden" }}>
      {/* Login */}
      <AnimatePresence>
        {showLogin && (
          <div key="login" style={{ position: "absolute", inset: 0 }}>
            <LoginScreen p0={p0} />
          </div>
        )}
      </AnimatePresence>

      {/* Feed — stays mounted from step 1 onwards */}
      <AnimatePresence>
        {showFeed && (
          <motion.div key="feed" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }}
            style={{ position: "absolute", inset: 0 }}>
            <JobFeedScreen p1={p1} p2={p2} />
          </motion.div>
        )}
      </AnimatePresence>

      {/* ATS Card */}
      <AnimatePresence>
        {showATS && <ATSCard key="ats" p3={p3} />}
      </AnimatePresence>

      {/* HM Card */}
      <AnimatePresence>
        {showHM && <HMCard key="hm" p3={p3} />}
      </AnimatePresence>

      {/* Apply button */}
      <AnimatePresence>
        {showApply && <ApplyOverlay key="apply" p4={p4} applied={applied} />}
      </AnimatePresence>

      {/* Toast */}
      <AnimatePresence>
        {showToast && <EmailToast key="toast" p5={p5} />}
      </AnimatePresence>
    </div>
  );
}

// ─── Progress Dots ───
function ProgressDots({ step }: { step: number }) {
  return (
    <div style={{ display: "flex", justifyContent: "center", gap: 6, flexShrink: 0 }}>
      {STEPS.map((_, i) => (
        <motion.div
          key={i}
          animate={{
            width: step === i ? 20 : 7,
            background: step === i ? T.red : step > i ? "#22c55e" : "rgba(242,238,179,0.12)",
          }}
          transition={{ duration: 0.3 }}
          style={{ height: 6, borderRadius: 3 }}
        />
      ))}
    </div>
  );
}

// ═══════════════════════════════
// MAIN EXPORT
// ═══════════════════════════════
export function HowItWorksScrollStory() {
  const wrapperRef  = useRef<HTMLDivElement>(null);
  const mockupRef   = useRef<HTMLDivElement>(null);

  // ── Manual section-local scroll progress ──
  // Use window scrollY directly (avoids Motion's container position warning)
  const { scrollY } = useScroll();
  const boundsRef   = useRef({ start: 0, length: 1 });

  useEffect(() => {
    const update = () => {
      const el = wrapperRef.current;
      if (!el) return;
      const rect   = el.getBoundingClientRect();
      const start  = rect.top + window.scrollY;
      const length = Math.max(1, el.offsetHeight - window.innerHeight);
      boundsRef.current = { start, length };
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  // 0 → 1 over the section's scroll range
  const scrollYProgress = useTransform(scrollY, (sy) => {
    const { start, length } = boundsRef.current;
    return Math.max(0, Math.min(1, (sy - start) / length));
  });

  // Per-step continuous progress (each step occupies 1/6 of section scroll)
  const p0 = useTransform(scrollYProgress, [S(0), S(1)], [0, 1]);
  const p1 = useTransform(scrollYProgress, [S(1), S(2)], [0, 1]);
  const p2 = useTransform(scrollYProgress, [S(2), S(3)], [0, 1]);
  const p3 = useTransform(scrollYProgress, [S(3), S(4)], [0, 1]);
  const p4 = useTransform(scrollYProgress, [S(4), S(5)], [0, 1]);
  const p5 = useTransform(scrollYProgress, [S(5), S(6)], [0, 1]);

  // Section progress bar
  const barWidth = useTransform(scrollYProgress, [0, 1], ["0%", "100%"]);
  const barColor = useTransform(
    scrollYProgress, [0, 0.67, 0.84, 1],
    ["#ED7D2B", "#F2A341", "#16a34a", "#22c55e"]
  );

  // Discrete step state
  const [step, setStep]       = useState(0);
  const [applied, setApplied] = useState(false);

  useMotionValueEvent(scrollYProgress, "change", (v) => {
    setStep(getStep(v));
    setApplied(v >= S(4) + (1 / 6) * 0.5);
  });

  // ── Mouse → 3D tilt ──
  const rawX    = useMotionValue(0);
  const rawY    = useMotionValue(0);
  const rotateY = useSpring(rawX, { stiffness: 110, damping: 24, mass: 0.55 });
  const rotateX = useSpring(rawY, { stiffness: 110, damping: 24, mass: 0.55 });

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = mockupRef.current?.getBoundingClientRect();
    if (!rect) return;
    rawX.set(((e.clientX - rect.left) / rect.width  - 0.5) * 16);
    rawY.set(-((e.clientY - rect.top)  / rect.height - 0.5) * 9);
  };
  const handleMouseLeave = () => { rawX.set(0); rawY.set(0); };

  return (
    <div
      id="how-it-works"
      ref={wrapperRef}
      style={{ height: "600vh", position: "relative" }}
    >
      {/* ── STICKY VIEWPORT ── */}
      <div
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        style={{
          position: "sticky", top: 0, height: "100vh",
          overflow: "hidden", display: "flex", flexDirection: "column",
          paddingTop: 64,
        }}
      >
        <BackgroundLayers step={step} />

        {/* Section progress bar */}
        <motion.div style={{
          position: "absolute", top: 0, left: 0, height: 3, zIndex: 50,
          width: barWidth, background: barColor,
        }} />

        <TopBar step={step} sectionProgress={barWidth} />

        {/* ── MAIN AREA ── */}
        <div style={{
          flex: 1, position: "relative", zIndex: 5,
          display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center",
          gap: 16, padding: "0 24px 12px",
          overflow: "hidden",
        }}>
          <StepHeader step={step} />

          {/* Browser + floating cards */}
          <div
            ref={mockupRef}
            style={{ position: "relative", width: "100%", maxWidth: 640, display: "flex", justifyContent: "center" }}
          >
            <motion.div style={{ width: "100%", perspective: 1100 }}>
              <motion.div style={{ rotateY, rotateX, transformStyle: "preserve-3d" as const }}>
                {/* Chrome bar */}
                <div style={{
                  borderRadius: "14px 14px 0 0",
                  background: "rgba(242,238,179,0.03)", border: `1px solid ${T.border}`, borderBottom: "none",
                  padding: "8px 12px", display: "flex", alignItems: "center", gap: 7,
                  position: "relative",
                }}>
                  <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
                    {["#ef4444", "#f59e0b", "#22c55e"].map((c, i) => (
                      <div key={i} style={{ width: 9, height: 9, borderRadius: "50%", background: c, opacity: 0.65 }} />
                    ))}
                  </div>
                  <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 6, background: "rgba(242,238,179,0.04)", border: `1px solid ${T.border}`, borderRadius: 6, padding: "3px 9px" }}>
                    <div style={{ width: 5, height: 5, borderRadius: "50%", background: "#22c55e", opacity: 0.75 }} />
                    <span style={{ fontFamily: F.mono, fontSize: 9, color: T.t3, overflow: "hidden", whiteSpace: "nowrap" as const, textOverflow: "ellipsis" }}>
                      app.placeup.careers/dashboard
                    </span>
                  </div>
                  <AnimatePresence>
                    {step === 0 && (
                      <motion.div
                        initial={{ width: "0%" }}
                        animate={{ width: ["0%", "70%", "100%"] }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 1.5, times: [0, 0.7, 1], delay: 0.8 }}
                        style={{ height: 2, borderRadius: 1, background: T.grad, position: "absolute", bottom: 0, left: 0 }}
                      />
                    )}
                  </AnimatePresence>
                </div>

                {/* Content area */}
                <div style={{
                  height: "clamp(300px, 44vh, 400px)",
                  position: "relative", overflow: "hidden",
                  background: "rgba(1,14,34,0.92)",
                  border: `1px solid ${T.border}`, borderTop: "none",
                  borderRadius: "0 0 14px 14px",
                }}>
                  <MockupContent
                    step={step} applied={applied}
                    p0={p0} p1={p1} p2={p2} p3={p3} p4={p4} p5={p5}
                  />
                </div>
              </motion.div>
            </motion.div>
          </div>

          <ProgressDots step={step} />
        </div>

        {/* Scroll hint */}
        <AnimatePresence>
          {step === 0 && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ delay: 1, duration: 0.6 }}
              style={{
                position: "absolute", bottom: 20, left: "50%", transform: "translateX(-50%)",
                zIndex: 10, display: "flex", flexDirection: "column", alignItems: "center", gap: 5,
              }}
            >
              <motion.div
                animate={{ y: [0, 6, 0] }}
                transition={{ duration: 1.3, repeat: Infinity }}
                style={{ width: 1, height: 28, background: `linear-gradient(to bottom, ${T.red}80, transparent)` }}
              />
              <span style={{ fontFamily: F.sans, fontSize: 9, color: T.t3, letterSpacing: "0.1em", textTransform: "uppercase" as const }}>
                scroll to continue
              </span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
