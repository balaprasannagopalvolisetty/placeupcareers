import type { CSSProperties } from "react";
import { ImageWithFallback } from "./figma/ImageWithFallback";

type BrandLogoProps = {
  height?: number;
  alt?: string;
  style?: CSSProperties;
};

const SOURCE_SIZE = 512;
const ART_BOUNDS = {
  left: 61,
  top: 138,
  width: 390,
  height: 229,
};

export function BrandLogo({ height = 36, alt = "PlaceUp Career", style }: BrandLogoProps) {
  const width = height * (ART_BOUNDS.width / ART_BOUNDS.height);
  const imageSize = height * (SOURCE_SIZE / ART_BOUNDS.height);

  return (
    <span
      style={{
        position: "relative",
        overflow: "hidden",
        display: "block",
        height,
        width,
        flexShrink: 0,
        ...style,
      }}
    >
      <ImageWithFallback
        src="/logo_white.png"
        alt={alt}
        style={{
          position: "absolute",
          left: -(ART_BOUNDS.left / SOURCE_SIZE) * imageSize,
          top: -(ART_BOUNDS.top / SOURCE_SIZE) * imageSize,
          width: imageSize,
          height: imageSize,
          maxWidth: "none",
          objectFit: "contain",
          display: "block",
        }}
      />
    </span>
  );
}
