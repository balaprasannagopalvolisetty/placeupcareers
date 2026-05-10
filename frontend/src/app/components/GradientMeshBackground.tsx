import { useEffect, useRef } from "react";

interface Props { scrollProgress: number; }

// ─── Career Network Mesh — Deep Navy × Warm Red Edition ───
// Three depth layers: navy bg, burnt-red mid, red-cream fg
// Orbital particles + ambient glow orbs + vignette

export function GradientMeshBackground({ scrollProgress }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const scrollRef = useRef(scrollProgress);
  scrollRef.current = scrollProgress;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener("resize", resize);

    // Warm-red palette per layer
    const PALETTES = [
      [[64, 18, 18], [140, 58, 39], [1, 17, 38]],   // bg  — dark reds / navy
      [[140, 58, 39], [166, 55, 45], [64, 18, 18]],  // mid — burnt reds
      [[166, 55, 45], [242, 238, 179], [140, 58, 39]], // fg  — red + cream accent
    ];

    class NetworkNode {
      x = 0; y = 0;
      baseX: number; baseY: number;
      layer: number; size: number;
      r: number; g: number; b: number;
      pulsePhase: number;
      driftAngle: number; driftSpeed: number; driftRadius: number;

      constructor(px: number, py: number, layer: number) {
        this.baseX = this.x = px;
        this.baseY = this.y = py;
        this.layer = layer;
        this.pulsePhase = Math.random() * Math.PI * 2;
        this.driftAngle = Math.random() * Math.PI * 2;
        this.driftSpeed = 0.0003 + Math.random() * 0.0003;
        this.driftRadius = layer === 0 ? 12 + Math.random() * 18
                         : layer === 1 ? 22 + Math.random() * 30
                         : 36 + Math.random() * 44;
        const palette = PALETTES[layer];
        const [r, g, b] = palette[Math.floor(Math.random() * palette.length)];
        this.r = r; this.g = g; this.b = b;
        this.size = layer === 0 ? 1.2 + Math.random() * 1.8
                  : layer === 1 ? 2.5 + Math.random() * 3.5
                  : 5 + Math.random() * 7;
      }

      update(_time: number, scroll: number) {
        this.driftAngle += this.driftSpeed;
        const parallax = [25, 70, 140][this.layer];
        this.x = this.baseX + Math.cos(this.driftAngle) * this.driftRadius;
        this.y = this.baseY + Math.sin(this.driftAngle) * this.driftRadius - scroll * parallax;
      }

      draw(ctx: CanvasRenderingContext2D, time: number) {
        const pulse = 0.75 + 0.25 * Math.sin(time * 0.0011 + this.pulsePhase);
        const { r, g, b, x, y, size, layer } = this;

        if (layer === 2) {
          const haloR = size * 3.5;
          const halo = ctx.createRadialGradient(x, y, 0, x, y, haloR);
          halo.addColorStop(0, `rgba(${r},${g},${b},${0.22 * pulse})`);
          halo.addColorStop(1, `rgba(${r},${g},${b},0)`);
          ctx.beginPath(); ctx.arc(x, y, haloR, 0, Math.PI * 2);
          ctx.fillStyle = halo; ctx.fill();

          ctx.beginPath(); ctx.arc(x, y, size * pulse, 0, Math.PI * 2);
          ctx.shadowBlur = 20;
          ctx.shadowColor = `rgba(${r},${g},${b},0.9)`;
          ctx.fillStyle = `rgba(${r},${g},${b},${0.9 * pulse})`;
          ctx.fill(); ctx.shadowBlur = 0;

          ctx.beginPath(); ctx.arc(x, y, size * 0.25, 0, Math.PI * 2);
          ctx.fillStyle = "rgba(255,255,255,0.9)"; ctx.fill();

        } else if (layer === 1) {
          ctx.beginPath(); ctx.arc(x, y, size * pulse, 0, Math.PI * 2);
          ctx.shadowBlur = 8;
          ctx.shadowColor = `rgba(${r},${g},${b},0.6)`;
          ctx.fillStyle = `rgba(${r},${g},${b},${0.55 * pulse})`;
          ctx.fill(); ctx.shadowBlur = 0;

          ctx.beginPath(); ctx.arc(x, y, size * 0.3, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(255,255,255,0.55)`; ctx.fill();

        } else {
          ctx.beginPath(); ctx.arc(x, y, size, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(${r},${g},${b},0.22)`; ctx.fill();
        }
      }
    }

    const spawnNodes = (count: number, layer: number): NetworkNode[] =>
      Array.from({ length: count }, () =>
        new NetworkNode(Math.random() * canvas.width, Math.random() * canvas.height, layer)
      );

    const bgNodes  = spawnNodes(16, 0);
    const midNodes = spawnNodes(10, 1);
    const fgNodes  = spawnNodes(5, 2);

    const drawConnections = (nodesA: NetworkNode[], nodesB: NetworkNode[], threshold: number, maxAlpha: number) => {
      nodesA.forEach((a) => {
        nodesB.forEach((b) => {
          if (a === b) return;
          const dx = a.x - b.x, dy = a.y - b.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < threshold) {
            const alpha = (1 - dist / threshold) * maxAlpha;
            ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
            if (nodesA !== nodesB) {
              const grad = ctx.createLinearGradient(a.x, a.y, b.x, b.y);
              grad.addColorStop(0, `rgba(${a.r},${a.g},${a.b},${alpha})`);
              grad.addColorStop(1, `rgba(${b.r},${b.g},${b.b},${alpha})`);
              ctx.strokeStyle = grad;
            } else {
              ctx.strokeStyle = `rgba(${a.r},${a.g},${a.b},${alpha})`;
            }
            ctx.lineWidth = nodesA === fgNodes ? 1.1 : 0.6;
            ctx.stroke();
          }
        });
      });
    };

    // Ambient orbs — warm red + navy palette
    const orbConfigs = [
      { xf: 0.10, yf: 0.12, r: 380, color: [140, 58, 39], a: 0.18 },
      { xf: 0.85, yf: 0.22, r: 340, color: [166, 55, 45], a: 0.14 },
      { xf: 0.55, yf: 0.65, r: 300, color: [64, 18, 18],  a: 0.12 },
      { xf: 0.25, yf: 0.82, r: 320, color: [1, 17, 38],   a: 0.20 },
      { xf: 0.72, yf: 0.88, r: 260, color: [140, 58, 39],  a: 0.10 },
      { xf: 0.62, yf: 0.08, r: 240, color: [166, 55, 45],  a: 0.12 },
    ];

    // Rising particles — cream + red tones
    class Particle {
      x: number; y: number; size: number; speed: number; opacity: number;
      r: number; g: number; b: number;
      constructor() {
        this.x = Math.random() * (canvas?.width ?? 1920);
        this.y = Math.random() * (canvas?.height ?? 1080);
        this.size = 0.4 + Math.random() * 1.2;
        this.speed = 0.12 + Math.random() * 0.35;
        this.opacity = 0.06 + Math.random() * 0.18;
        const cols = [[166, 55, 45], [242, 238, 179], [140, 58, 39]];
        [this.r, this.g, this.b] = cols[Math.floor(Math.random() * 3)];
      }
      update(scroll: number) {
        this.y -= this.speed + scroll * 0.4;
        if (this.y < -10) {
          this.y = (canvas?.height ?? 1080) + 10;
          this.x = Math.random() * (canvas?.width ?? 1920);
        }
      }
      draw(ctx: CanvasRenderingContext2D) {
        ctx.beginPath(); ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${this.r},${this.g},${this.b},${this.opacity})`;
        ctx.fill();
      }
    }

    const particles = Array.from({ length: 80 }, () => new Particle());
    let animId: number;

    const animate = () => {
      const time = Date.now();
      const scroll = scrollRef.current;
      const W = canvas.width, H = canvas.height;

      // Deep navy bg gradient
      const bgGrad = ctx.createRadialGradient(W * 0.5, H * 0.4, 0, W * 0.5, H * 0.5, W * 0.9);
      bgGrad.addColorStop(0, "#070e1f");
      bgGrad.addColorStop(1, "#011126");
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, W, H);

      // Ambient orbs (heavy blur)
      ctx.filter = "blur(85px)";
      orbConfigs.forEach(({ xf, yf, r, color: [cr, cg, cb], a }) => {
        const ox = W * xf, oy = H * yf - scroll * 110;
        const grad = ctx.createRadialGradient(ox, oy, 0, ox, oy, r);
        grad.addColorStop(0, `rgba(${cr},${cg},${cb},${a})`);
        grad.addColorStop(1, `rgba(${cr},${cg},${cb},0)`);
        ctx.beginPath(); ctx.arc(ox, oy, r, 0, Math.PI * 2);
        ctx.fillStyle = grad; ctx.fill();
      });
      ctx.filter = "none";

      [...bgNodes, ...midNodes, ...fgNodes].forEach((n) => n.update(time, scroll));

      // Background layer
      ctx.filter = "blur(3.5px)";
      drawConnections(bgNodes, bgNodes, 190, 0.09);
      bgNodes.forEach((n) => n.draw(ctx, time));
      ctx.filter = "none";

      ctx.filter = "blur(1.5px)";
      drawConnections(bgNodes, midNodes, 150, 0.06);
      ctx.filter = "none";

      ctx.filter = "blur(1px)";
      drawConnections(midNodes, midNodes, 230, 0.16);
      midNodes.forEach((n) => n.draw(ctx, time));
      ctx.filter = "none";

      drawConnections(midNodes, fgNodes, 190, 0.11);
      drawConnections(fgNodes, fgNodes, 270, 0.30);
      fgNodes.forEach((n) => n.draw(ctx, time));

      particles.forEach((p) => { p.update(scroll); p.draw(ctx); });

      // Vignette
      const vignette = ctx.createRadialGradient(W / 2, H / 2, H * 0.22, W / 2, H / 2, W * 0.88);
      vignette.addColorStop(0, "rgba(1,17,38,0)");
      vignette.addColorStop(1, "rgba(1,17,38,0.72)");
      ctx.fillStyle = vignette; ctx.fillRect(0, 0, W, H);

      animId = requestAnimationFrame(animate);
    };

    animate();
    return () => {
      window.removeEventListener("resize", resize);
      cancelAnimationFrame(animId);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0"
      style={{ zIndex: 0, background: "#011126" }}
    />
  );
}
