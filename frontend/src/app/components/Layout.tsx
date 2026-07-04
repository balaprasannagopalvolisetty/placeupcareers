import { Outlet, useLocation } from "react-router";
import { useState, createContext, useContext } from "react";
import Particles from "./Particles";

type ThemeCtx = { dark: boolean; toggle: () => void };
export const ThemeContext = createContext<ThemeCtx>({ dark: true, toggle: () => {} });
export const useTheme = () => useContext(ThemeContext);

export default function Layout() {
  const location = useLocation();
  const [dark, setDark] = useState(true);
  const toggle = () => setDark((d) => !d);

  return (
    <ThemeContext.Provider value={{ dark, toggle }}>
      <div
        className={dark ? "dark" : ""}
        style={{
          position: "relative",
          background: dark ? "#07111F" : "#ffffff",
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
            particleColors={["#2F80ED"]}
            particleCount={location.pathname.startsWith("/dashboard") || location.pathname.startsWith("/ops-console") ? 0 : 48}
            particleSpread={9}
            speed={0.06}
            particleBaseSize={42}
            moveParticlesOnHover={false}
            alphaParticles
            disableRotation={false}
            pixelRatio={1}
          />
        </div>

        {/* ── Page content ── */}
        <div key={location.pathname} style={{ position: "relative", zIndex: 1 }}>
          <Outlet />
        </div>
      </div>
    </ThemeContext.Provider>
  );
}
