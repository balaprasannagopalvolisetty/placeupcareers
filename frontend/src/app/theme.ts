/**
 * PlaceUp — single source of truth for colors, fonts, and responsive breakpoints.
 *
 * Cream + orange identity. Historically every component declared its own local
 * `const T = {...}` / `const C = {...}` with a brick-red accent (#A6372D). This
 * module replaces that: import `T` (or `C`) and `F` here so the whole app shares
 * one palette and a single recolor changes everything.
 *
 * Migration recipe for an existing component:
 *   1. delete its local `const F = {...}` and `const T = {...}` / `const C = {...}`
 *   2. add at the top:  import { T, F } from "<relative>/theme";
 *      (if the file used `C`, write:  import { C, F } from "<relative>/theme";)
 * Every key the old objects used (text, t2, t3, border, glass, grad, red, bg)
 * exists here, so usages keep working — `T.red` now renders orange.
 */

// ─── Palette: cream + orange on deep warm surfaces ───────────────────────────
export const T = {
  // Surfaces
  bg: "#0E1116",                       // deep neutral base (kept dark for contrast)
  bgWarm: "#16110C",                   // warm alt surface for sections
  glass: "rgba(38,24,12,0.55)",        // warm glass panel
  border: "rgba(245,234,200,0.10)",    // cream-tinted hairline

  // Text (cream family)
  text: "#F5EAC8",                     // primary cream
  t2: "rgba(245,234,200,0.66)",        // secondary
  t3: "rgba(245,234,200,0.45)",        // tertiary / muted

  // Accent (orange family) — `red` kept as an alias so legacy `T.red` → orange
  accent: "#ED7D2B",                   // primary orange
  accentSoft: "#F2A341",               // light orange
  accentDeep: "#C75A12",               // deep orange
  red: "#ED7D2B",                      // ALIAS for backward-compat (was brick red)
  grad: "linear-gradient(135deg, #F2A341, #ED7D2B, #C75A12)",

  // Status
  green: "#3FB477",
  warn: "#E8A93C",
} as const;

// `C` is an alias so files that imported a `C` object keep working.
export const C = T;

export const F = {
  sans: "'Plus Jakarta Sans', sans-serif",
  display: "'Space Grotesk', 'Plus Jakarta Sans', sans-serif",
  mono: "'JetBrains Mono', ui-monospace, monospace",
} as const;

// ─── Responsive breakpoints (mobile / tablet-iPad / laptop+) ─────────────────
export const BREAKPOINTS = { mobile: 640, tablet: 1024 } as const;

import { useState, useEffect } from "react";

export type Viewport = { width: number; isMobile: boolean; isTablet: boolean; isDesktop: boolean };

/**
 * Shared viewport hook so each page can branch layout for phone / iPad / laptop
 * instead of every file re-implementing its own resize listener.
 *   isMobile  : < 640px   (phones)
 *   isTablet  : 640–1023  (iPad / small tablets)
 *   isDesktop : >= 1024   (laptop and up)
 */
export function useViewport(): Viewport {
  const read = () => (typeof window === "undefined" ? 1280 : window.innerWidth);
  const [width, setWidth] = useState<number>(read);
  useEffect(() => {
    const onResize = () => setWidth(read());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return {
    width,
    isMobile: width < BREAKPOINTS.mobile,
    isTablet: width >= BREAKPOINTS.mobile && width < BREAKPOINTS.tablet,
    isDesktop: width >= BREAKPOINTS.tablet,
  };
}
