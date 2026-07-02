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
  bg: "#07111F",                       // deep professional navy
  bgWarm: "#0B1728",                   // alternate navy surface
  glass: "rgba(11,23,40,0.72)",        // clean glass panel
  border: "rgba(226,232,240,0.13)",    // slate hairline

  // Text (cream family)
  text: "#F8FAFC",                     // primary
  t2: "rgba(226,232,240,0.72)",        // secondary
  t3: "rgba(148,163,184,0.72)",        // tertiary / muted

  // Accent (orange family) — `red` kept as an alias so legacy `T.red` → orange
  accent: "#2F80ED",                   // primary blue
  accentSoft: "#38BDF8",               // sky
  accentDeep: "#1D4ED8",               // deep blue
  red: "#2F80ED",                      // legacy alias
  grad: "linear-gradient(135deg, #2563EB, #0EA5E9, #14B8A6)",

  // Status
  green: "#22C55E",
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
