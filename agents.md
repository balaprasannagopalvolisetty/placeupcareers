# PlaceUp Career - Agent Instructions

You are an AI agent extending the PlaceUp Career web application. Read this file, then `/docs/context.md` for project architecture, and `/docs/skills.md` for exact code patterns. Follow them precisely.

---

## Before You Write Any Code

1. **Read these files first** (in order):
   - `/docs/agents.md` (this file)
   - `/docs/context.md` (architecture, file structure, routing, theme, data schemas)
   - `/docs/skills.md` (copy-paste-ready component patterns)
   - `/package.json` (check what's installed)
   - `/src/app/routes.ts` (current routes)
   - `/src/app/components/Layout.tsx` (theme context, page transitions)
   - `/src/styles/theme.css` (color tokens)

2. **Understand the visual language**: This is a premium dark-mode-first SaaS with a violet-indigo-fuchsia gradient brand. Every surface uses glassmorphism (`bg-card/50 backdrop-blur-sm border border-border`). Cards lift on hover. Text uses Inter (body) and Space Grotesk (headings/numbers). All font sizing is done via inline `style={}`, NOT Tailwind text/font classes.

---

## Critical Rules (Non-Negotiable)

| Rule | Details |
|---|---|
| Router | `import { ... } from "react-router"` — NEVER `react-router-dom` |
| Motion | `import { motion } from "motion/react"` — NEVER `framer-motion` |
| Font sizing | Use inline `style={{ fontSize: N }}` — NEVER Tailwind `text-*` classes |
| Font weight | Use inline `style={{ fontWeight: N }}` — NEVER Tailwind `font-*` classes |
| Line height | Use inline style — NEVER Tailwind `leading-*` classes |
| Images | Use `ImageWithFallback` from `/src/app/components/figma/ImageWithFallback.tsx` for new images. Never hardcode image URLs. |
| Protected files | NEVER modify `/src/app/components/figma/ImageWithFallback.tsx` or `/pnpm-lock.yaml` |
| Default exports | All page components MUST use `export default function PageName()` |
| Keys | Always provide unique `key` props in lists |
| Package installs | Check `package.json` first. If a package isn't there, install it before importing. |

---

## How to Add a New Page

### Step 1: Create the page file

Create `/src/app/pages/YourPage.tsx`. Use `export default function YourPage()`.

- If it's a **landing/marketing page**: include `<Navbar />` and optionally `<ParticleBackground />`
- If it's a **dashboard/app page**: use the sidebar layout pattern from `Dashboard.tsx`

### Step 2: Register the route

Edit `/src/app/routes.ts`:
```ts
import YourPage from "./pages/YourPage";

// Add to children array:
{ path: "your-page", Component: YourPage },
```

### Step 3: Add navigation

- For landing pages: add a link in `Navbar.tsx`
- For dashboard pages: add an item to the `navItems` array in `Dashboard.tsx` or create a shared sidebar component

---

## How to Add a New Dashboard Sub-View

The current Dashboard uses a local `activeNav` state to switch between views (only "Overview" is built). To add more views:

**Option A (Simple — local state):**
Add conditional rendering inside `Dashboard.tsx` based on `activeNav`:
```tsx
{activeNav === "Resumes" && <ResumesView />}
{activeNav === "Analytics" && <AnalyticsView />}
```

**Option B (Proper — nested routes):**
Convert dashboard nav items to nested routes:
```ts
// routes.ts
{
  path: "dashboard",
  Component: DashboardLayout,
  children: [
    { index: true, Component: DashboardOverview },
    { path: "resumes", Component: Resumes },
    { path: "analytics", Component: Analytics },
  ],
}
```

---

## How to Add a New Section to the Landing Page

1. Create `/src/app/components/sections/YourSection.tsx`
2. Use the section header pattern from `/docs/skills.md` (Skill 2)
3. Import and add it to `/src/app/pages/Home.tsx` in the desired position
4. Use `id="your-section"` for anchor link navigation
5. Add the nav link in `Navbar.tsx`'s nav items array

---

## Component Placement Rules

| Type | Directory | Import Pattern |
|---|---|---|
| Pages | `/src/app/pages/` | Default export, registered in `routes.ts` |
| Shared components | `/src/app/components/` | Named export |
| Section components | `/src/app/components/sections/` | Named export |
| UI primitives | `/src/app/components/ui/` | Named export |

---

## Styling Quick Reference

### Surfaces
```
Page background:    bg-background
Card:               bg-card/50 backdrop-blur-sm border border-border rounded-2xl
Navbar/Topbar:      backdrop-blur-xl bg-background/60 border-b border-border
```

### Text Colors
```
Primary text:       (default, no class needed — inherits text-foreground)
Secondary text:     text-muted-foreground
Accent text:        text-violet-400
Gradient text:      bg-gradient-to-r from-violet-400 to-indigo-400 bg-clip-text text-transparent
Success:            text-green-400
Error:              text-red-400
```

### Spacing Convention
```
Section padding:    py-32 (vertical), px-6 (horizontal)
Max width:          max-w-6xl mx-auto (content), max-w-7xl mx-auto (navbar)
Card padding:       p-6 or p-8
Card gap:           gap-6
```

### Border Radius
```
Cards/Panels:       rounded-2xl
Buttons:            rounded-xl
Badges:             rounded-md or rounded-lg
Icons containers:   rounded-lg or rounded-xl
Full round:         rounded-full
```

---

## Available But Unused Packages

These are installed and ready to use without installation:

- **recharts** — Use for analytics charts, graphs, dashboards
- **@radix-ui/**** — Full suite of accessible UI primitives (dialog, select, tabs, tooltip, etc.)
- **react-day-picker + date-fns** — Date picking
- **cmdk** — Command palette
- **sonner** — Toast notifications (`import { toast } from "sonner"`)
- **react-dnd** — Drag and drop
- **embla-carousel-react** — Carousels
- **react-resizable-panels** — Resizable split panels
- **vaul** — Drawer component
- **canvas-confetti** — Celebration effects
- **react-hook-form** — Form handling (v7.55.0)

---

## Dashboard Views to Build (Roadmap)

These sidebar items exist in navigation but have no UI yet:

1. **Resumes** — Resume list, upload, ATS score per resume, version comparison
2. **Jobs** — Extended job board with filters (location, salary, visa, status)
3. **Visa Tracker** — Expanded visa data with charts, employer deep-dives, status timeline
4. **Alerts** — Alert preferences UI (skills, locations, salary range, visa toggle)
5. **Analytics** — Charts showing application funnel, response rates, market positioning (use recharts)
6. **Settings** — Profile, subscription management, notification preferences, data export

---

## Data Patterns for New Features

When creating new features, maintain consistency with existing mock data:

```ts
// Always give mock data realistic values
// Always include id fields for keys
// Match the career/visa/job domain

// Example: Resume mock
const resumes = [
  { id: 1, name: "Software Engineer Resume", atsScore: 87, lastUpdated: "2 days ago", version: 3, status: "active" },
  { id: 2, name: "Full Stack Resume", atsScore: 74, lastUpdated: "1 week ago", version: 1, status: "draft" },
];

// Example: Alert mock
const alerts = [
  { id: 1, title: "Frontend roles in SF", skills: ["React", "TypeScript"], minSalary: 150000, visaRequired: true, active: true },
];
```

---

## Checklist Before Finishing

- [ ] All new pages have default exports
- [ ] All new routes are registered in `routes.ts`
- [ ] No Tailwind text-*/font-*/leading-* classes used for typography
- [ ] Motion imported from `"motion/react"`
- [ ] Router imported from `"react-router"`
- [ ] Cards use glassmorphism: `bg-card/50 backdrop-blur-sm border border-border rounded-2xl`
- [ ] Interactive elements have `whileHover` and/or `whileTap` Motion props
- [ ] Lists have unique `key` props
- [ ] Responsive: works on mobile (use `md:` and `lg:` breakpoints)
- [ ] Dark mode compatible (using theme tokens, not hardcoded colors)