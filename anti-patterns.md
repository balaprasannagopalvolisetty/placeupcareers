# PlaceUp Career - Anti-Patterns

Things that will break the app, violate conventions, or create visual inconsistencies. Every rule here exists because the opposite was either attempted and failed, or would contradict the established codebase. Read this before writing any code.

---

## 1. Router Anti-Patterns

### NEVER: Import from `react-router-dom`
```tsx
// WRONG — this package doesn't work in this environment
import { Link } from "react-router-dom";
import { BrowserRouter } from "react-router-dom";

// CORRECT
import { Link } from "react-router";
import { createBrowserRouter, RouterProvider } from "react-router";
```

### NEVER: Use `<BrowserRouter>` wrapper pattern
```tsx
// WRONG — this project uses Data mode with createBrowserRouter
<BrowserRouter>
  <Routes>
    <Route path="/" element={<Home />} />
  </Routes>
</BrowserRouter>

// CORRECT — routes are defined in /src/app/routes.ts
export const router = createBrowserRouter([
  {
    path: "/",
    Component: Layout,
    children: [
      { index: true, Component: Home },
      { path: "dashboard", Component: Dashboard },
    ],
  },
]);
```

### NEVER: Add routes outside the Layout wrapper
```tsx
// WRONG — page won't have theme, cursor, or page transitions
createBrowserRouter([
  { path: "/", Component: Layout, children: [...] },
  { path: "/standalone", Component: StandalonePage },  // No Layout!
]);

// CORRECT — always nest under Layout
createBrowserRouter([
  {
    path: "/",
    Component: Layout,
    children: [
      { index: true, Component: Home },
      { path: "standalone", Component: StandalonePage },
    ],
  },
]);
```

### NEVER: Use `element` instead of `Component` in route config
```tsx
// WRONG
{ path: "about", element: <About /> }

// CORRECT
{ path: "about", Component: About }
```

---

## 2. Typography Anti-Patterns

### NEVER: Use Tailwind classes for font-size, font-weight, or line-height
```tsx
// WRONG
<h2 className="text-2xl font-bold leading-tight">Title</h2>

// CORRECT
<h2 style={{ fontSize: 28, fontWeight: 700, lineHeight: 1.2 }}>Title</h2>
```

This is a project-wide convention. The only exception is if the user explicitly asks to use Tailwind typography classes.

### NEVER: Forget to set fontFamily on headings/numbers
```tsx
// WRONG — will render in Inter (body font)
<h2 style={{ fontSize: 44, fontWeight: 700 }}>$19</h2>

// CORRECT — Space Grotesk for headings and display numbers
<h2 style={{ fontFamily: "'Space Grotesk'", fontSize: 44, fontWeight: 700 }}>$19</h2>
```

### NEVER: Use raw pixel strings instead of numbers in style objects
```tsx
// WRONG
style={{ fontSize: "16px", fontWeight: "600" }}

// CORRECT (React accepts numbers for px-based properties)
style={{ fontSize: 16, fontWeight: 600 }}

// EXCEPTION: clamp() must be a string
style={{ fontSize: "clamp(28px, 4vw, 44px)" }}
```

---

## 3. Animation Anti-Patterns

### NEVER: Import from `framer-motion`
```tsx
// WRONG — old package name, not installed
import { motion } from "framer-motion";

// CORRECT
import { motion } from "motion/react";
```

### NEVER: Use scroll reveal without `viewport={{ once: true }}`
```tsx
// WRONG — re-animates every time element enters viewport (janky)
<motion.div
  initial={{ opacity: 0, y: 30 }}
  whileInView={{ opacity: 1, y: 0 }}
>

// CORRECT — animates once
<motion.div
  initial={{ opacity: 0, y: 30 }}
  whileInView={{ opacity: 1, y: 0 }}
  viewport={{ once: true }}
>
```

### NEVER: Use motion on elements that don't need it
```tsx
// WRONG — wrapping a static div in motion adds overhead
<motion.div className="text-muted-foreground">Static text</motion.div>

// CORRECT — only use motion when you need animation props
<div className="text-muted-foreground">Static text</div>
```

### NEVER: Use `animate` for scroll-triggered reveals
```tsx
// WRONG — fires on mount, not on scroll
<motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>

// CORRECT — fires when scrolled into view
<motion.div initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: true }}>
```

**Exception:** Hero section and Dashboard content use `animate` intentionally because they're visible on load.

---

## 4. Styling Anti-Patterns

### NEVER: Hardcode colors instead of using theme tokens
```tsx
// WRONG
<div className="bg-[#1a1a1a] text-[#f5f5f5] border-[#333]">

// CORRECT — uses theme variables that adapt to light/dark mode
<div className="bg-background text-foreground border-border">
<div className="bg-card text-card-foreground">
<div className="text-muted-foreground">
```

### NEVER: Use `bg-white` or `bg-black` directly
```tsx
// WRONG — breaks in light/dark mode
<div className="bg-white text-black">
<div className="bg-black text-white">

// CORRECT
<div className="bg-background text-foreground">
<div className="bg-card text-card-foreground">
```

**Exception:** The brand gradient overlays (like CTA buttons) use hardcoded `text-white` because they're always on a violet/indigo gradient background regardless of theme.

### NEVER: Create cards without the glassmorphism pattern
```tsx
// WRONG — flat, looks out of place
<div className="p-6 rounded-lg bg-gray-800 border border-gray-700">

// CORRECT — matches the established glass aesthetic
<div className="p-6 rounded-2xl border border-border bg-card/50 backdrop-blur-sm">
```

### NEVER: Use `rounded-lg` for major cards/panels
```tsx
// WRONG — too small for this design language
<div className="rounded-lg ...">

// CORRECT — all cards/panels use 2xl
<div className="rounded-2xl ...">

// rounded-lg is for: icon containers, buttons, badges
// rounded-xl is for: buttons, inputs
// rounded-2xl is for: cards, panels, sections
// rounded-full is for: avatars, pills, notification dots
```

### NEVER: Create a `tailwind.config.js` file
This project uses Tailwind CSS v4. Configuration lives in `/src/styles/theme.css` via `@theme inline`. A config file would be ignored or cause conflicts.

---

## 5. Component Structure Anti-Patterns

### NEVER: Put all page code in App.tsx
```tsx
// WRONG
export default function App() {
  return (
    <div>
      <nav>...</nav>
      <section>...hero...</section>
      <section>...features...</section>
      {/* 500 lines of JSX */}
    </div>
  );
}

// CORRECT — compose from focused components
export default function Home() {
  return (
    <div className="relative">
      <ParticleBackground />
      <Navbar />
      <HeroSection />
      <FeaturesSection />
    </div>
  );
}
```

### NEVER: Use named exports for page components
```tsx
// WRONG — routes.ts expects default exports for Component prop
export function Dashboard() { ... }

// CORRECT
export default function Dashboard() { ... }
```

### NEVER: Create `.jsx` files
```
// WRONG
/src/app/components/NewThing.jsx

// CORRECT — this is a TypeScript project
/src/app/components/NewThing.tsx
```

### NEVER: Put components outside `/src/app/components/`
```
// WRONG
/src/components/MyWidget.tsx
/components/MyWidget.tsx

// CORRECT
/src/app/components/MyWidget.tsx
/src/app/components/sections/MySection.tsx
```

### NEVER: Put pages outside `/src/app/pages/`
```
// WRONG
/src/app/About.tsx
/src/pages/About.tsx

// CORRECT
/src/app/pages/About.tsx
```

---

## 6. Image Anti-Patterns

### NEVER: Use bare `<img>` tags for new images
```tsx
// WRONG
<img src="/photo.jpg" alt="..." />

// CORRECT
import { ImageWithFallback } from "./components/figma/ImageWithFallback";
<ImageWithFallback src="..." alt="..." className="..." />
```

### NEVER: Hardcode image URLs
```tsx
// WRONG
<ImageWithFallback src="https://images.unsplash.com/photo-abc123" />

// CORRECT — use the unsplash_tool to get URLs, or use figma:asset imports
```

### NEVER: Modify ImageWithFallback.tsx
This file is protected. Don't touch it, don't copy it, don't create alternatives.

---

## 7. State Management Anti-Patterns

### NEVER: Create a second theme context/provider
```tsx
// WRONG — duplicates existing ThemeContext from Layout
const MyThemeContext = createContext({ darkMode: false });

// CORRECT — use the existing one
import { useTheme } from "../components/Layout";
const { dark, toggle } = useTheme();
```

### NEVER: Use `localStorage` for theme without syncing to ThemeContext
```tsx
// WRONG — class won't update, components won't re-render
localStorage.setItem("theme", "light");
document.documentElement.classList.remove("dark");

// CORRECT — use the provided toggle function
const { toggle } = useTheme();
toggle();
```

---

## 8. Package Anti-Patterns

### NEVER: Import a package without checking it's installed
```tsx
// WRONG — will crash at build time
import confetti from "canvas-confetti";  // Is this installed? CHECK FIRST.

// CORRECT workflow:
// 1. Read /package.json
// 2. If not listed, use install_package tool
// 3. Then import
```

### NEVER: Install `react-router-dom`
It doesn't work in this environment. Use `react-router` (already installed).

### NEVER: Install `framer-motion`
Use the `motion` package (already installed). Import from `motion/react`.

### NEVER: Install `@react-three/fiber`, `three`, or `gsap`
These were in the original prompt's wishlist but are NOT installed and would add massive bundle size. The project uses CSS/canvas-based visual effects instead.

### NEVER: Edit `package.json` directly to add packages
Always use the `install_package` tool.

### NEVER: Modify `/pnpm-lock.yaml`
This file is protected.

---

## 9. Font Anti-Patterns

### NEVER: Add font imports anywhere except `/src/styles/fonts.css`
```css
/* WRONG — font import in a component CSS module or theme.css */
@import url('https://fonts.googleapis.com/css2?family=Roboto...');

/* CORRECT — only in /src/styles/fonts.css */
```

### NEVER: Use fonts that aren't imported
The project uses exactly two font families:
- `Inter` — body text, UI elements
- `Space Grotesk` — headings, brand text, display numbers

If you need a third font, add it to `/src/styles/fonts.css` first.

---

## 10. Dashboard-Specific Anti-Patterns

### NEVER: Mount ParticleBackground on Dashboard
```tsx
// WRONG — wastes GPU on a data-heavy page
export default function Dashboard() {
  return (
    <div>
      <ParticleBackground />  {/* NO! */}
      ...
    </div>
  );
}

// CORRECT — Dashboard has no particle background, no 3D, no canvas
export default function Dashboard() {
  return (
    <div className="flex min-h-screen bg-background">
      <aside>...</aside>
      <main>...</main>
    </div>
  );
}
```

### NEVER: Use the Navbar component on Dashboard
Dashboard has its own top bar and sidebar. The `<Navbar>` is only for landing/marketing pages.

### NEVER: Forget the mobile sidebar
Every dashboard layout must include:
1. Desktop sidebar (`hidden lg:flex`)
2. Mobile hamburger trigger (`lg:hidden`)
3. Mobile sidebar overlay with backdrop

---

## 11. Accessibility Anti-Patterns

### NEVER: Use color alone to convey meaning
```tsx
// WRONG — colorblind users can't distinguish
<span className="text-green-400">{score}</span>

// BETTER — add a text label or icon alongside the color
<span className="flex items-center gap-1 text-green-400">
  <CheckCircle2 size={14} /> {score}
</span>
```

### NEVER: Forget alt text on images
```tsx
// WRONG
<ImageWithFallback src="..." />

// CORRECT
<ImageWithFallback src="..." alt="Career placement dashboard showing ATS scores" />
```

### NEVER: Make non-interactive elements look clickable
```tsx
// WRONG — cursor-pointer on a non-clickable div
<div className="cursor-pointer p-4 rounded-2xl ...">
  <h3>Just a label</h3>
</div>

// CORRECT — only use cursor-pointer on elements with onClick or Link/a
```

---

## 12. Performance Anti-Patterns

### NEVER: Animate layout properties with Motion
```tsx
// WRONG — animating width/height triggers layout recalculation
<motion.div animate={{ width: expanded ? 300 : 64 }}>

// CORRECT — use transform-based animations
<motion.div animate={{ x: expanded ? 0 : -236 }}>
// OR use CSS transitions on non-layout properties
```

### NEVER: Use `useEffect` to set initial animation states
```tsx
// WRONG
const [visible, setVisible] = useState(false);
useEffect(() => setVisible(true), []);
return <div style={{ opacity: visible ? 1 : 0 }}>

// CORRECT — let Motion handle it
<motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
```

---

## Quick Reference: The Right Way

| Task | Correct Approach |
|---|---|
| Add a page | Default export in `/src/app/pages/`, register in `routes.ts` as child of Layout |
| Add a component | Named export in `/src/app/components/`, import with relative path |
| Style text | Inline `style={{ fontSize, fontWeight, fontFamily }}` |
| Style a card | `rounded-2xl border border-border bg-card/50 backdrop-blur-sm` |
| Animate on scroll | `whileInView` + `viewport={{ once: true }}` |
| Animate on mount | `initial` + `animate` |
| Lift on hover | `whileHover={{ y: -8 }}` |
| Press feedback | `whileTap={{ scale: 0.98 }}` |
| Access theme | `import { useTheme } from "../components/Layout"` |
| Add navigation | Landing: `Navbar.tsx` array. Dashboard: `navItems` array in `Dashboard.tsx` |
| Use images | `<ImageWithFallback>` component, stock photos from `unsplash_tool` |
| Install packages | Check `package.json` first, then `install_package` tool |