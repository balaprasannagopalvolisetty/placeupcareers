import { useEffect, useRef } from "react";

interface ParticlesProps {
  particleColors?: string[];
  particleCount?: number;
  particleSpread?: number;
  speed?: number;
  particleBaseSize?: number;
  moveParticlesOnHover?: boolean;
  alphaParticles?: boolean;
  disableRotation?: boolean;
  pixelRatio?: number;
  className?: string;
  style?: React.CSSProperties;
}

export default function Particles({
  particleColors = ["#ffffff"],
  particleCount = 200,
  particleSpread = 10,
  speed = 0.1,
  particleBaseSize = 100,
  moveParticlesOnHover = false,
  alphaParticles = false,
  disableRotation = false,
  pixelRatio = 1,
  className,
  style,
}: ParticlesProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mouseRef = useRef({ x: 0, y: 0 });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    if (particleCount <= 0) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      return;
    }

    const resize = () => {
      canvas.width = canvas.offsetWidth * pixelRatio;
      canvas.height = canvas.offsetHeight * pixelRatio;
    };
    resize();
    window.addEventListener("resize", resize);

    // Parse hex → [r, g, b]
    const parseHex = (hex: string): [number, number, number] => {
      const h = hex.replace("#", "");
      const r = parseInt(h.slice(0, 2), 16);
      const g = parseInt(h.slice(2, 4), 16);
      const b = parseInt(h.slice(4, 6), 16);
      return [r, g, b];
    };
    const colorRGBs = particleColors.map(parseHex);

    // Build particle field in 3D — each particle has x,y,z in [-spread/2, spread/2]
    interface Particle3D {
      x: number; y: number; z: number;
      r: number; g: number; b: number;
      baseRadius: number;
    }
    const pts: Particle3D[] = Array.from({ length: particleCount }, () => {
      const [r, g, b] = colorRGBs[Math.floor(Math.random() * colorRGBs.length)];
      return {
        x: (Math.random() - 0.5) * particleSpread,
        y: (Math.random() - 0.5) * particleSpread,
        z: (Math.random() - 0.5) * particleSpread,
        r, g, b,
        baseRadius: 0.4 + Math.random() * 0.6,
      };
    });

    let rotAngle = 0;
    let animId: number;

    const handleMouseMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      mouseRef.current = {
        x: (e.clientX - rect.left - rect.width / 2) / (rect.width / 2),
        y: (e.clientY - rect.top - rect.height / 2) / (rect.height / 2),
      };
    };
    if (moveParticlesOnHover) {
      window.addEventListener("mousemove", handleMouseMove);
    }

    const animate = () => {
      const W = canvas.width;
      const H = canvas.height;
      ctx.clearRect(0, 0, W, H);

      if (!disableRotation) {
        rotAngle += speed * 0.005;
      }

      // Mouse influence on rotation
      const hoverStrength = moveParticlesOnHover ? 0.25 : 0;
      const rotY = rotAngle + mouseRef.current.x * hoverStrength;
      const rotX = -mouseRef.current.y * hoverStrength * 0.5;

      const cosY = Math.cos(rotY), sinY = Math.sin(rotY);
      const cosX = Math.cos(rotX), sinX = Math.sin(rotX);

      const focal = Math.max(W, H) * 0.9;
      const sizeScale = (particleBaseSize / 100) * (Math.min(W, H) / 600);

      // Project all particles
      const projected = pts.map((p) => {
        // Rotate Y axis
        const x1 =  p.x * cosY + p.z * sinY;
        const z1 = -p.x * sinY + p.z * cosY;
        // Rotate X axis
        const y1 =  p.y * cosX - z1 * sinX;
        const z2 =  p.y * sinX + z1 * cosX;

        const depth = focal + z2 * (focal / particleSpread);
        const scale = focal / depth;
        const unitW = W / particleSpread;
        const unitH = H / particleSpread;

        const sx = x1 * unitW * scale + W / 2;
        const sy = y1 * unitH * scale + H / 2;
        const radius = Math.max(0.3, p.baseRadius * sizeScale * scale * 1.5);
        const depthFactor = (z2 / (particleSpread / 2)) * 0.5 + 0.5; // 0→1
        const alpha = alphaParticles ? 0.15 + depthFactor * 0.85 : 1;

        return { sx, sy, radius, depthFactor, alpha, r: p.r, g: p.g, b: p.b, scale };
      });

      // Sort back-to-front for natural depth layering
      projected.sort((a, b) => a.scale - b.scale);

      projected.forEach(({ sx, sy, radius, alpha, r, g, b }) => {
        if (sx < -20 || sx > W + 20 || sy < -20 || sy > H + 20) return;
        ctx.beginPath();
        ctx.arc(sx, sy, radius, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${r},${g},${b},${alpha})`;
        ctx.fill();
      });

      animId = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", resize);
      if (moveParticlesOnHover) {
        window.removeEventListener("mousemove", handleMouseMove);
      }
    };
  }, [
    particleColors, particleCount, particleSpread, speed,
    particleBaseSize, moveParticlesOnHover, alphaParticles,
    disableRotation, pixelRatio,
  ]);

  return (
    <canvas
      ref={canvasRef}
      className={className}
      style={{ width: "100%", height: "100%", display: "block", ...style }}
    />
  );
}
