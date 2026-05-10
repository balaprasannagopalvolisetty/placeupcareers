import { motion } from "motion/react";

export function OrbitalSphereSmall({ size = 260 }: { size?: number }) {
  const cx = size / 2, cy = size / 2;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ overflow: "visible" }}>
      <defs>
        <radialGradient id="ssg" cx="35%" cy="30%" r="65%">
          <stop offset="0%" stopColor="rgba(166,55,45,0.95)" />
          <stop offset="55%" stopColor="rgba(140,58,39,0.5)" />
          <stop offset="100%" stopColor="rgba(64,18,18,0)" />
        </radialGradient>
        <radialGradient id="ssGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="rgba(166,55,45,0.35)" />
          <stop offset="100%" stopColor="rgba(166,55,45,0)" />
        </radialGradient>
        <filter id="ssBlur"><feGaussianBlur stdDeviation="14" /></filter>
        <filter id="ssRingGlow"><feGaussianBlur stdDeviation="2" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
      </defs>
      <circle cx={cx} cy={cy} r={75} fill="url(#ssGlow)" filter="url(#ssBlur)" />
      <motion.ellipse cx={cx} cy={cy} rx={100} ry={28} fill="none" stroke="rgba(140,58,39,0.6)" strokeWidth="1.2" filter="url(#ssRingGlow)"
        animate={{ rotateZ: [0, 360] }} transition={{ duration: 26, repeat: Infinity, ease: "linear" }} />
      <motion.ellipse cx={cx} cy={cy} rx={84} ry={55} fill="none" stroke="rgba(1,17,38,0.5)" strokeWidth="1.2"
        style={{ transformOrigin: `${cx}px ${cy}px`, rotate: "45deg" }}
        animate={{ rotateZ: [45, 405] }} transition={{ duration: 18, repeat: Infinity, ease: "linear" }} />
      <circle cx={cx} cy={cy} r={56} fill="url(#ssg)" />
      <ellipse cx={cx - 16} cy={cy - 16} rx={18} ry={12} fill="rgba(255,255,255,0.1)" />
      {[0, 72, 144, 216, 288, 30, 100].map((angle, i) => {
        const rad = (angle * Math.PI) / 180;
        const rx = i < 5 ? 100 : 84, ry = i < 5 ? 28 : 55;
        const px = cx + rx * Math.cos(rad), py = cy + ry * Math.sin(rad);
        return <motion.circle key={i} cx={px} cy={py} r={i % 3 === 0 ? 3 : 2} fill="rgba(255,255,255,0.8)"
          animate={{ opacity: [0.4, 1, 0.4] }} transition={{ duration: 2 + i * 0.4, repeat: Infinity, ease: "easeInOut" }} />;
      })}
    </svg>
  );
}
