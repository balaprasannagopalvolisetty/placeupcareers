import type { CSSProperties } from "react";
import { ImageWithFallback } from "./figma/ImageWithFallback";

type BrandLogoProps = {
  height?: number;
  alt?: string;
  style?: CSSProperties;
};

export function BrandLogo({ height = 36, alt = "PlaceUp Career", style }: BrandLogoProps) {
  return (
    <ImageWithFallback
      src="/logo_white.png"
      alt={alt}
      style={{
        height,
        width: "auto",
        objectFit: "contain",
        display: "block",
        flexShrink: 0,
        ...style,
      }}
    />
  );
}
