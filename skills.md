# PlaceUp Career - Design & Code Skills Reference

This document defines the exact patterns, component recipes, and visual language an AI agent must follow when extending this project. Copy these patterns exactly — do not deviate.

---

## Skill 1: Creating a New Page

```tsx
// /src/app/pages/NewPage.tsx
import { motion } from "motion/react";
import { Navbar } from "../components/Navbar";

export default function NewPage() {
  return (
    <div className="relative min-h-screen">
      <Navbar />
      <div className="pt-16 max-w-6xl mx-auto px-6 py-20">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          {/* Page content */}
        </motion.div>
      </div>
    </div>
  );
}
```

Then register in `/src/app/routes.ts`:
```ts
import NewPage from "./pages/NewPage";
// inside children array:
{ path: "new-page", Component: NewPage },
```

---

## Skill 2: Section Header Pattern

Every landing page section uses this header block:

```tsx
<motion.div
  initial={{ opacity: 0, y: 30 }}
  whileInView={{ opacity: 1, y: 0 }}
  viewport={{ once: true }}
  className="text-center mb-20"
>
  <span
    className="text-violet-400 mb-4 block"
    style={{ fontSize: 13, fontWeight: 600, letterSpacing: 2, textTransform: "uppercase" }}
  >
    SECTION LABEL
  </span>
  <h2 style={{ fontFamily: "'Space Grotesk'", fontSize: "clamp(28px, 4vw, 44px)", fontWeight: 700 }}>
    Heading with{" "}
    <span className="bg-gradient-to-r from-violet-400 to-indigo-400 bg-clip-text text-transparent">
      Gradient Word
    </span>
  </h2>
</motion.div>
```

---

## Skill 3: Card Component Pattern

All cards follow this structure:

```tsx
<motion.div
  initial={{ opacity: 0, y: 30 }}
  whileInView={{ opacity: 1, y: 0 }}
  viewport={{ once: true }}
  transition={{ delay: index * 0.1 }}
  whileHover={{ y: -8 }}
  whileTap={{ scale: 0.98 }}
  className="relative p-6 rounded-2xl border border-border bg-card/50 backdrop-blur-sm group overflow-hidden"
>
  {/* Hover gradient overlay */}
  <div className="absolute inset-0 bg-gradient-to-br from-violet-500/5 via-transparent to-indigo-500/5 opacity-0 group-hover:opacity-100 transition-opacity duration-500" />

  <div className="relative z-10">
    {/* Icon */}
    <div className="w-10 h-10 rounded-lg bg-violet-500/10 flex items-center justify-center mb-4">
      <IconComponent size={20} className="text-violet-400" />
    </div>
    {/* Title */}
    <h3 style={{ fontSize: 17, fontWeight: 600 }} className="mb-2">Title</h3>
    {/* Description */}
    <p className="text-muted-foreground" style={{ fontSize: 14, lineHeight: 1.6 }}>
      Description text.
    </p>
  </div>
</motion.div>
```

---

## Skill 4: Button Styles

### Primary CTA
```tsx
<Link
  to="/target"
  className="group px-8 py-4 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white flex items-center gap-2 hover:shadow-lg hover:shadow-violet-500/25 transition-all"
  style={{ fontSize: 16, fontWeight: 600 }}
>
  Button Text
  <ArrowRight size={18} className="group-hover:translate-x-1 transition-transform" />
</Link>
```

### Secondary/Outline
```tsx
<button
  className="px-8 py-4 rounded-xl border border-border text-foreground hover:bg-accent transition"
  style={{ fontSize: 16, fontWeight: 500 }}
>
  Secondary Action
</button>
```

### Small Ghost
```tsx
<button
  className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border text-muted-foreground hover:text-foreground transition"
  style={{ fontSize: 13 }}
>
  <FilterIcon size={14} /> Filter
</button>
```

---

## Skill 5: Badge / Tag Pattern

```tsx
// Status badge
<span className="px-2 py-1 rounded-md bg-violet-500/10 text-violet-400" style={{ fontSize: 11, fontWeight: 600 }}>
  TAG
</span>

// Visa badge
<span className="px-1.5 py-0.5 rounded bg-green-500/10 text-green-400" style={{ fontSize: 10, fontWeight: 600 }}>
  VISA
</span>

// Pill badge (like hero)
<div className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-violet-500/30 bg-violet-500/10">
  <Sparkles size={14} className="text-violet-400" />
  <span className="text-violet-300" style={{ fontSize: 13 }}>Label Text</span>
</div>
```

---

## Skill 6: Dashboard Panel / Data Card

```tsx
<motion.div
  initial={{ opacity: 0, y: 20 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ delay: 0.1 }}
  className="rounded-2xl border border-border bg-card/50 backdrop-blur-sm"
>
  {/* Header */}
  <div className="p-6 flex items-center justify-between border-b border-border">
    <h3 style={{ fontSize: 16, fontWeight: 600 }}>Panel Title</h3>
    {/* Optional action button */}
  </div>
  {/* Content */}
  <div className="p-6">
    {/* Content here */}
  </div>
</motion.div>
```

---

## Skill 7: SVG Circular Progress (ATS Score)

```tsx
function CircularScore({ score, size = 128 }: { score: number; size?: number }) {
  const r = (size / 2) - 10;
  const c = 2 * Math.PI * r;
  const offset = c - (score / 100) * c;
  const color = score >= 80 ? "#8b5cf6" : score >= 60 ? "#f59e0b" : "#ef4444";

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} className="w-full h-full -rotate-90">
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="currentColor" className="text-border" strokeWidth="8" />
        <motion.circle
          cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth="8" strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1.5, ease: "easeOut" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span style={{ fontFamily: "'Space Grotesk'", fontSize: 28, fontWeight: 700 }}>{score}</span>
        <span className="text-muted-foreground" style={{ fontSize: 11 }}>ATS Score</span>
      </div>
    </div>
  );
}
```

---

## Skill 8: Table Pattern (Visa Tracker style)

```tsx
<div className="overflow-x-auto">
  <table className="w-full" style={{ fontSize: 14 }}>
    <thead>
      <tr className="text-muted-foreground border-b border-border">
        <th className="text-left p-4" style={{ fontWeight: 500 }}>Column</th>
      </tr>
    </thead>
    <tbody className="divide-y divide-border">
      {data.map((row) => (
        <tr key={row.id} className="hover:bg-accent/30 transition">
          <td className="p-4">{row.value}</td>
        </tr>
      ))}
    </tbody>
  </table>
</div>
```

---

## Skill 9: Stat Block

```tsx
<div className="text-center">
  <div
    style={{ fontFamily: "'Space Grotesk'", fontSize: 28, fontWeight: 700 }}
    className="bg-gradient-to-r from-violet-400 to-indigo-400 bg-clip-text text-transparent"
  >
    50K+
  </div>
  <div className="text-muted-foreground" style={{ fontSize: 13 }}>Label</div>
</div>
```

---

## Skill 10: Form Input Pattern

```tsx
<input
  type="text"
  placeholder="Placeholder..."
  className="w-full px-4 py-3 rounded-xl bg-card/50 border border-border backdrop-blur-sm focus:outline-none focus:border-violet-500 transition"
/>
```

---

## Skill 11: Sidebar Navigation Item

```tsx
<button
  onClick={() => setActive(label)}
  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition ${
    isActive
      ? "bg-violet-500/10 text-violet-400"
      : "text-muted-foreground hover:text-foreground hover:bg-accent"
  }`}
  style={{ fontSize: 14 }}
>
  <Icon size={18} />
  {label}
</button>
```

---

## Skill 12: List Row with Hover (Job Card style)

```tsx
<motion.div
  whileHover={{ backgroundColor: "rgba(139, 92, 246, 0.03)" }}
  className="p-5 flex items-center gap-4 cursor-pointer transition"
>
  {/* Left icon */}
  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500/20 to-indigo-500/20 flex items-center justify-center shrink-0">
    <Icon size={18} className="text-violet-400" />
  </div>
  {/* Content */}
  <div className="flex-1 min-w-0">
    <div style={{ fontSize: 15, fontWeight: 600 }} className="truncate">Title</div>
    <div className="text-muted-foreground" style={{ fontSize: 13 }}>Subtitle details</div>
  </div>
  {/* Right */}
  <ChevronRight size={16} className="text-muted-foreground" />
</motion.div>
```

---

## Skill 13: Using Theme Toggle

```tsx
import { useTheme } from "../components/Layout";

function MyComponent() {
  const { dark, toggle } = useTheme();
  return (
    <button onClick={toggle} className="p-2 rounded-lg hover:bg-accent transition">
      {dark ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}
```

---

## Skill 14: Gradient Glow Orbs (Background Decoration)

```tsx
<div className="absolute top-1/4 left-1/4 w-96 h-96 bg-violet-600/20 rounded-full blur-[120px] animate-pulse" />
<div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-indigo-600/15 rounded-full blur-[100px] animate-pulse" style={{ animationDelay: "1s" }} />
```

---

## Skill 15: Notification Dot

```tsx
<button className="relative p-2 rounded-lg hover:bg-accent transition">
  <Bell size={18} />
  <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-violet-500" />
</button>
```