import { Outlet, useLocation } from "react-router";
import { useState, useEffect, useCallback, createContext, useContext } from "react";
import Particles from "./Particles";

/* ── Theme system ──────────────────────────────────────────────────────
   Dark + light mode for the whole app. All component colors resolve to
   CSS variables defined in src/styles/theme-tokens.css, switched by the
   `data-theme` attribute on <html>. The `.dark` class is kept in sync
   for the shadcn/Tailwind components.

   Resolution order:
     1. Explicit user choice (localStorage "placeup-theme")
     2. OS preference (prefers-color-scheme), tracked live
   index.html applies the same logic pre-paint to avoid a flash. */

const THEME_KEY = "placeup-theme";

type ThemeCtx = { dark: boolean; toggle: () => void };
export const ThemeContext = createContext<ThemeCtx>({ dark: true, toggle: () => {} });
export const useTheme = () => useContext(ThemeContext);

function systemPrefersDark(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches;
}

function initialDark(): boolean {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored === "dark") return true;
    if (stored === "light") return false;
  } catch { /* private mode */ }
  return systemPrefersDark();
}

function applyTheme(dark: boolean) {
  const root = document.documentElement;
  root.dataset.theme = dark ? "dark" : "light";
  root.classList.toggle("dark", dark);
  root.style.colorScheme = dark ? "dark" : "light";
}

export default function Layout() {
  const location = useLocation();
  const [dark, setDark] = useState<boolean>(initialDark);

  // Apply on mount + whenever the mode changes.
  useEffect(() => { applyTheme(dark); }, [dark]);

  // Follow OS changes live while the user hasn't made an explicit choice.
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return;
    const onChange = (e: MediaQueryListEvent) => {
      try {
        if (!localStorage.getItem(THEME_KEY)) setDark(e.matches);
      } catch { setDark(e.matches); }
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const toggle = useCallback(() => {
    setDark((d) => {
      const next = !d;
      try { localStorage.setItem(THEME_KEY, next ? "dark" : "light"); } catch { /* ignore */ }
      return next;
    });
  }, []);

  return (
    <ThemeContext.Provider value={{ dark, toggle }}>
      <div
        style={{
          position: "relative",
          background: "var(--pu-07111f)",
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
            opacity: dark ? 1 : 0.35,
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

/* ── Theme toggle button ───────────────────────────────────────────────
   Drop-in sun/moon switch. Used in the public navbar and the dashboard
   header; safe anywhere inside the Layout tree. */
export function ThemeToggle({ size = 34 }: { size?: number }) {
  const { dark, toggle } = useTheme();
  return (
    <button
      onClick={toggle}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      title={dark ? "Switch to light mode" : "Switch to dark mode"}
      style={{
        width: size,
        height: size,
        borderRadius: 10,
        border: "1px solid var(--pu-148-163-184-018)",
        background: "var(--pu-148-163-184-006)",
        color: "var(--pu-f1f5f9-t)",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        cursor: "pointer",
        flexShrink: 0,
        transition: "background 0.2s ease, transform 0.15s ease",
      }}
    >
      {dark ? (
        /* Sun icon */
        <svg width={size * 0.5} height={size * 0.5} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
        </svg>
      ) : (
        /* Moon icon */
        <svg width={size * 0.5} height={size * 0.5} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
        </svg>
      )}
    </button>
  );
}
