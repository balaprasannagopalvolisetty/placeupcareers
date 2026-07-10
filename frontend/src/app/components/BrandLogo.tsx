import type { CSSProperties } from "react";
import { ImageWithFallback } from "./figma/ImageWithFallback";
import { useTheme } from "./Layout";

type BrandLogoProps = {
  height?: number;
  alt?: string;
  style?: CSSProperties;
  /**
   * full  — cream wordmark + bunny (for dark/navy backgrounds). Default.
   * dark  — navy wordmark + bunny (for white/light backgrounds).
   * mark  — bunny + star only, no text (tight spots: compact sidebar, spinners).
   */
  variant?: "full" | "dark" | "mark";
};

// Tightly cropped brand assets in /public — no CSS crop hacks needed.
const ASSETS: Record<NonNullable<BrandLogoProps["variant"]>, { src: string; ratio: number }> = {
  full: { src: "/logo_light.png", ratio: 550 / 320 },
  dark: { src: "/logo_dark.png", ratio: 550 / 320 },
  mark: { src: "/logo_mark.png", ratio: 265 / 320 },
};

export function BrandLogo({ height = 36, alt = "PlaceUp Career", style, variant = "full" }: BrandLogoProps) {
  // Theme-aware: "full" (cream, for dark surfaces) and "dark" (navy, for
  // light surfaces) auto-swap with the active theme so the wordmark stays
  // readable in both modes. "mark" is theme-neutral. Outside the provider
  // the context default ({ dark: true }) keeps the original behavior.
  const { dark: isDarkMode } = useTheme();
  const resolved: NonNullable<BrandLogoProps["variant"]> =
    variant === "mark" ? "mark" : isDarkMode ? "full" : "dark";
  const asset = ASSETS[resolved];
  const width = height * asset.ratio;

  return (
    <ImageWithFallback
      src={asset.src}
      alt={alt}
      style={{
        display: "block",
        height,
        width,
        objectFit: "contain",
        flexShrink: 0,
        ...style,
      }}
    />
  );
}
