import { Outlet, useLocation } from "react-router";
import { AnimatePresence, motion } from "motion/react";
import { useState, createContext, useContext } from "react";
import Particles from "./Particles";
import { PrivacyGuard } from "./PrivacyGuard";

type ThemeCtx = { dark: boolean; toggle: () => void };
export const ThemeContext = createContext<ThemeCtx>({ dark: true, toggle: () => {} });
export const useTheme = () => useContext(ThemeContext);

export default function Layout() {
  const location = useLocation();
  const [dark, setDark] = useState(true);
  const toggle = () => setDark((d) => !d);

  return (
    <ThemeContext.Provider value={{ dark, toggle }}>
      <PrivacyGuard />
      <div
        className={dark ? "dark" : ""}
        style={{
          position: "relative",
          background: dark ? "#011126" : "#ffffff",
          minHeight: "100vh",
          fontFamily: "'Plus Jakarta Sans', sans-serif",
        }}
      >
        {/* ── Global Particles background ── */}
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 0,
            pointerEvents: "none",
          }}
        >
          <Particles
            particleColors={["#b81414"]}
            particleCount={200}
            particleSpread={10}
            speed={0.1}
            particleBaseSize={100}
            moveParticlesOnHover
            alphaParticles={false}
            disableRotation={false}
            pixelRatio={1}
          />
        </div>

        {/* ── Page content ── */}
        <AnimatePresence mode="wait">
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            style={{ position: "relative", zIndex: 1 }}
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </div>
    </ThemeContext.Provider>
  );
}
