import { motion } from "motion/react";
import { ImageWithFallback } from "./figma/ImageWithFallback";

const F = { sans: "'Plus Jakarta Sans', sans-serif" };
const T = {
  text: "#F1F5F9",
  t2: "rgba(148,163,184,0.65)",
  border: "rgba(148,163,184,0.08)",
  grad: "linear-gradient(135deg, #2563EB, #0EA5E9)",
};

export function LoadingLogo({ label = "Loading", fullScreen = false }: { label?: string; fullScreen?: boolean }) {
  return (
    <div
      style={{
        minHeight: fullScreen ? "100vh" : 180,
        width: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 28,
        boxSizing: "border-box",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 1.6, repeat: Infinity, ease: "linear" }}
          style={{
            width: 76,
            height: 76,
            borderRadius: "50%",
            padding: 3,
            background: `conic-gradient(from 0deg, rgba(148,163,184,0.08), #3B82F6, #60A5FA, rgba(148,163,184,0.08))`,
          }}
        >
          <div
            style={{
              width: "100%",
              height: "100%",
              borderRadius: "50%",
              background: "rgba(1,17,38,0.94)",
              border: `1px solid ${T.border}`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 18px 40px rgba(1,17,38,0.42)",
            }}
          >
            <motion.div
              animate={{ rotate: -360, scale: [1, 1.04, 1] }}
              transition={{ rotate: { duration: 1.6, repeat: Infinity, ease: "linear" }, scale: { duration: 1.2, repeat: Infinity, ease: "easeInOut" } }}
              style={{ width: 42, height: 42, display: "flex", alignItems: "center", justifyContent: "center" }}
            >
              <ImageWithFallback
                src="/logo_white.png"
                alt="PlaceUp Career"
                style={{ width: 42, height: 42, objectFit: "contain" }}
              />
            </motion.div>
          </div>
        </motion.div>
        <div style={{ fontFamily: F.sans, color: T.text, fontSize: 13, fontWeight: 700, letterSpacing: "0.02em" }}>{label}</div>
        <div style={{ width: 120, height: 3, borderRadius: 999, background: "rgba(148,163,184,0.08)", overflow: "hidden" }}>
          <motion.div
            animate={{ x: ["-45%", "120%"] }}
            transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut" }}
            style={{ width: 70, height: "100%", borderRadius: 999, background: T.grad }}
          />
        </div>
        <div style={{ fontFamily: F.sans, color: T.t2, fontSize: 11 }}>Refreshing your workspace</div>
      </div>
    </div>
  );
}
