# PlaceUp Career - Component Registry

Every component in the project, its exact file path, export type, props, internal state, dependencies, and rendering contract. Use this as the single source of truth when composing, extending, or refactoring.

---

## Table of Contents

| # | Component | Path | Export | Used By |
|---|---|---|---|---|
| 1 | App | `/src/app/App.tsx` | default | Entry point |
| 2 | Layout | `/src/app/components/Layout.tsx` | default | `routes.ts` |
| 3 | CustomCursor | `/src/app/components/CustomCursor.tsx` | named | `Layout` |
| 4 | Navbar | `/src/app/components/Navbar.tsx` | named | `Home` |
| 5 | GradientMeshBackground | `/src/app/components/GradientMeshBackground.tsx` | named | `Home` |
| 6 | Home | `/src/app/pages/Home.tsx` | default | `routes.ts` |
| 7 | Dashboard | `/src/app/pages/Dashboard.tsx` | default | `routes.ts` |
| 8 | SignIn | `/src/app/pages/SignIn.tsx` | default | `routes.ts` |
| 9 | SignUp | `/src/app/pages/SignUp.tsx` | default | `routes.ts` |
| 10 | ResumePage | `/src/app/components/dashboard/ResumePage.tsx` | named | `Dashboard` |
| 11 | JobsPage | `/src/app/components/dashboard/JobsPage.tsx` | named | `Dashboard` |
| 12 | JobDetailPage | `/src/app/components/dashboard/JobDetailPage.tsx` | named | `Dashboard` |
| 13 | VisaTrackerPage | `/src/app/components/dashboard/VisaTrackerPage.tsx` | named | `Dashboard` |
| 14 | AlertsPage | `/src/app/components/dashboard/AlertsPage.tsx` | named | `Dashboard` |
| 15 | AnalyticsPage | `/src/app/components/dashboard/AnalyticsPage.tsx` | named | `Dashboard` |
| 16 | SettingsPage | `/src/app/components/dashboard/SettingsPage.tsx` | named | `Dashboard` |
| 17 | UserProfilePage | `/src/app/components/dashboard/UserProfilePage.tsx` | named | `Dashboard` |
| 18 | ATSCircle | `/src/app/pages/Dashboard.tsx` (internal) | none (local) | `Dashboard` |
| 19 | ImageWithFallback | `/src/app/components/figma/ImageWithFallback.tsx` | named | PROTECTED — use for any new `<img>` |

---

## 1. App

**Path:** `/src/app/App.tsx`
**Export:** `export default function App()`
**Props:** None
**State:** None
**Dependencies:** `react-router` (`RouterProvider`), `./routes`

**What it does:**
Root shell. Wraps `<RouterProvider router={router} />` inside a `<div className="dark">` to set the initial dark theme class on the outermost DOM node.

**Rendering contract:**
```
<div className="dark">
  <RouterProvider router={router} />
</div>
```

**When to modify:** Almost never. Only touch this if you need to add a global provider that must live *above* the router (e.g., a Redux store, a top-level ErrorBoundary).

---

## 2. Layout

**Path:** `/src/app/components/Layout.tsx`
**Export:** `export default function Layout()` + named exports `ThemeContext`, `useTheme`
**Props:** None (receives children via `<Outlet />`)
**State:**
- `dark: boolean` (default `true`) — controls `.dark` class on wrapper div

**Dependencies:** `react-router` (`Outlet`, `useLocation`), `motion/react` (`AnimatePresence`, `motion`), `./CustomCursor`

**Context provided:**
```ts
type ThemeCtx = { dark: boolean; toggle: () => void };
export const ThemeContext = createContext<ThemeCtx>(...);
export const useTheme = () => useContext(ThemeContext);
```

**Rendering contract:**
```
ThemeContext.Provider
  └─ div (className={dark ? "dark" : ""})
     └─ div (bg-background text-foreground min-h-screen, fontFamily: Inter)
        ├─ CustomCursor
        └─ AnimatePresence mode="wait"
           └─ motion.div (clip-path wipe transition, keyed on pathname, position: relative)
              └─ <Outlet />
```

**Page transition animation:**
- Initial: `clipPath: "inset(0 100% 0 0)"` (hidden from right)
- Animate: `clipPath: "inset(0 0% 0 0)"` (fully revealed)
- Exit: `clipPath: "inset(0 0 0 100%)"` (hides to left)
- Duration: 0.5s, easing: `[0.76, 0, 0.24, 1]`
- **Important:** `style={{ position: "relative" }}` on `motion.div` — required for Motion `useScroll` offset calculation

**When to modify:** Add new global providers here. Wrap around `<Outlet />` if you need layout-level sidebars or persistent headers across all routes.

---

## 3. CustomCursor

**Path:** `/src/app/components/CustomCursor.tsx`
**Export:** `export function CustomCursor()`
**Props:** None
**State:**
- `pos: { x: number, y: number }` — raw mouse position (instant dot)
- `visible: boolean` — hides when mouse leaves window

**Motion values:**
- `springX`, `springY` — `useSpring(0, { stiffness: 500, damping: 28 })` — trailing ring

**Rendering contract:**
```
<> (Fragment)
  ├─ div.fixed (z-[9999]) — 8x8px violet dot at exact mouse pos
  └─ motion.div.fixed (z-[9998]) — 32x32px violet ring with spring follow
</>
```

**Z-index:** 9999 (dot), 9998 (ring) — always above everything
**Pointer events:** `pointer-events-none` on both elements

**When to modify:** To change cursor appearance (color, size) or add cursor state changes on hover over interactive elements.

---

## 4. Navbar

**Path:** `/src/app/components/Navbar.tsx`
**Export:** `export function Navbar()`
**Props:** None
**State:**
- `open: boolean` — mobile menu toggle

**Dependencies:** `react-router` (`Link`), `motion/react`, `./Layout` (`useTheme`), `lucide-react` (`Sun`, `Moon`, `Menu`, `X`)

**Nav items (hardcoded array):**
```ts
["How It Works", "Features", "Pricing", "Contact"]
```
Each generates a button with smooth scroll to section.

**Rendering contract:**
```
motion.nav.fixed (z-50, backdrop-blur-xl, bg-background/60)
  └─ div.max-w-7xl (h-16, flex between)
     ├─ Link to="/" — Logo (gradient box + "PlaceUp" in Space Grotesk)
     ├─ div.hidden.md:flex — Desktop nav links + Dashboard button + theme toggle
     └─ button.md:hidden — Hamburger (toggles `open`)

  └─ (if open) motion.div.md:hidden — Mobile dropdown menu
```

**Entry animation:** `initial={{ y: -80 }} animate={{ y: 0 }}` — slides down on mount

**When to modify:** To add new nav links, change the logo, or add auth-state-aware items (e.g., "Log In" vs user avatar).

---

## 5. GradientMeshBackground

**Path:** `/src/app/components/GradientMeshBackground.tsx`
**Export:** `export function GradientMeshBackground({ scrollProgress })`
**Props:**
- `scrollProgress: number` — 0-1 scroll value for scroll-reactive animations

**Canvas setup:**
- **Gradient Orbs:** 6 large blurred gradient orbs with gentle circular motion
- **Floating Particles:** 50 small violet particles that float upward
- **Subtle Grid:** Faint grid lines that move with scroll
- **Colors:** Violet, indigo, purple gradients with theme-aware opacity

**Animation features:**
- Orbs perform slow circular motion with varying speeds
- Particles float upward and wrap around
- Grid lines scroll with page progress
- All elements react to scroll position

**Rendering contract:**
```
<canvas.fixed (inset-0, z-index: -1, bg: dark ? #030712 : #ffffff) />
```

**Lifecycle:** Starts RAF loop on mount, cleans up on unmount. Resizes on window resize.

**When to modify:** To change colors, orb count, particle density, or add new visual elements.

---

## 6. Home (Page)

**Path:** `/src/app/pages/Home.tsx`
**Export:** `export default function Home()`
**Props:** None
**State:**
- `progress: number` — tracks scroll progress (0-1)

**Composition (Scrollytelling):**
```
div.relative (height: 300vh, position: relative) — Scroll container
  ├─ GradientMeshBackground (scrollProgress prop)
  └─ div.fixed.inset-0.overflow-hidden (z-10) — Viewport
     ├─ Navbar
     ├─ SectionWrapper (Hero: 0-0.19)
     ├─ SectionWrapper (How It Works: 0.14-0.38)
     ├─ SectionWrapper (Features: 0.33-0.58)
     ├─ SectionWrapper (Pricing: 0.53-0.78)
     ├─ SectionWrapper (Contact: 0.73-1.00)
     ├─ ScrollIndicator
     └─ Progress bar (bottom, violet gradient)
```

**Section visibility logic:**
Each section fades in/out based on scroll ranges:
- Fade in: opacity 0 → 1
- Fade out: opacity 1 → 0
- Y translation: slight parallax effect
- Pointer events disabled when not visible

**To add a new section:** Import it, wrap in SectionWrapper with custom ranges.

---

## 7. Dashboard (Page)

**Path:** `/src/app/pages/Dashboard.tsx`
**Export:** `export default function Dashboard()`
**Props:** None
**State:**
- `sidebarOpen: boolean` — mobile sidebar toggle
- `activeNav: string` (default `"Overview"`) — tracks selected sidebar item
- `notificationsOpen: boolean` — notification dropdown state
- `userMenuOpen: boolean` — user menu dropdown state
- `selectedJobId: number | null` — for job detail navigation

**Dependencies:** `react-router` (`Link`, `useNavigate`), `motion/react`, `lucide-react`, `../components/Layout` (`useTheme`), all dashboard page components

**Layout structure:**
```
div.flex.min-h-screen
  ├─ aside.hidden.lg:flex (w-64) — Desktop sidebar
  │   ├─ Logo header (border-b)
  │   ├─ nav (7 items, highlight active with violet)
  │   └─ Logout button (hover:bg-red)
  │
  ├─ (if sidebarOpen) Mobile sidebar overlay
  │   ├─ Backdrop (bg-black/50, click to close)
  │   └─ motion.aside (slide from left)
  │
  └─ main.flex-1.overflow-auto
     ├─ Sticky top bar (search, notifications, theme toggle, user menu)
     └─ div.p-6.max-w-7xl
        └─ {renderPage()} — Conditional page rendering
```

**Page routing (internal state-based):**
```ts
renderPage() {
  switch (activeNav) {
    case "Overview": return <OverviewPage onJobClick={...} />
    case "Resumes": return <ResumePage />
    case "Jobs": return <JobsPage onJobClick={...} />
    case "Job Detail": return <JobDetailPage jobId={...} onBack={...} />
    case "Visa Tracker": return <VisaTrackerPage />
    case "Alerts": return <AlertsPage />
    case "Analytics": return <AnalyticsPage />
    case "Settings": return <SettingsPage />
    case "Profile": return <UserProfilePage />
  }
}
```

**Sidebar nav items:**
```ts
[Home, FileText, Briefcase, Globe, Bell, BarChart3, Settings]
// labels: Overview, Resumes, Jobs, Visa Tracker, Alerts, Analytics, Settings
```

---

## 8. SignIn

**Path:** `/src/app/pages/SignIn.tsx`
**Export:** `export default function SignIn()`
**Props:** None
**State:**
- `email: string`
- `password: string`
- `rememberMe: boolean`

**Features:**
- Email/password form
- Remember me checkbox
- Sign in button (redirects to dashboard)
- Link to sign up page
- Social auth buttons (Google, GitHub)

---

## 9. SignUp

**Path:** `/src/app/pages/SignUp.tsx`
**Export:** `export default function SignUp()`
**Props:** None
**State:**
- `name: string`
- `email: string`
- `password: string`
- `acceptTerms: boolean`

**Features:**
- Name, email, password form
- Terms acceptance checkbox
- Sign up button (redirects to dashboard)
- Link to sign in page
- Social auth buttons (Google, GitHub)

---

## 10. ResumePage

**Path:** `/src/app/components/dashboard/ResumePage.tsx`
**Export:** `export function ResumePage()`

**Features:**
- Resume upload dropzone
- Resume version management (tabs)
- ATS score display with circular progress
- Download/delete resume buttons
- Keywords analysis
- Improvement suggestions

---

## 11. JobsPage

**Path:** `/src/app/components/dashboard/JobsPage.tsx`
**Export:** `export function JobsPage({ onJobClick })`
**Props:**
- `onJobClick?: (jobId: number) => void` — callback when user clicks "View Details"

**State:**
- `searchTerm: string` — text search
- `selectedStatus: string` — all/new/applied/interview/saved
- `selectedTitle: string` — job title filter
- `selectedTime: string` — 6h/1d/3d/all time posted filter
- `selectedLocation: string` — location filter
- `showFilters: boolean` — advanced filters panel toggle

**Advanced Filters:**
1. **Job Title Dropdown:** All unique job titles
2. **Time Posted Dropdown:** 6 Hours, 1 Day, 3 Days, All Time
3. **Location Dropdown:** All unique locations
4. **Active Filters Display:** Pills with remove buttons
5. **Clear All Button:** Resets all filters

---

## 12. JobDetailPage

**Path:** `/src/app/components/dashboard/JobDetailPage.tsx`
**Export:** `export function JobDetailPage({ jobId, onBack })`
**Props:**
- `jobId: number` — ID of the job to display
- `onBack: () => void` — callback to return to jobs list

**Sections:**
1. Header (title, company, match score, actions)
2. ATS Score for This Position
3. Strong Keywords (from resume)
4. Missing Keywords (suggestions)
5. Job Description (responsibilities, requirements, nice-to-have)
6. Sidebar (visa info, benefits, company info)

---

## 13. VisaTrackerPage

**Path:** `/src/app/components/dashboard/VisaTrackerPage.tsx`
**Export:** `export function VisaTrackerPage()`

**Features:**
- Visa sponsorship statistics table
- Employer name, visa type, approval/denial counts
- Approval rate calculation
- Search and filter functionality

---

## 14. AlertsPage

**Path:** `/src/app/components/dashboard/AlertsPage.tsx`
**Export:** `export function AlertsPage()`

**Features:**
- Job alert management
- Alert creation with filters
- Active alerts list
- Alert history

---

## 15. AnalyticsPage

**Path:** `/src/app/components/dashboard/AnalyticsPage.tsx`
**Export:** `export function AnalyticsPage()`

**Features:**
- Application pipeline visualization
- Response rate analytics
- Market positioning insights
- Career progress tracking

---

## 16. SettingsPage

**Path:** `/src/app/components/dashboard/SettingsPage.tsx`
**Export:** `export function SettingsPage()`

**Features:**
- Theme toggle (Dark/Light)
- Email preferences
- Notification settings
- Privacy controls
- Account management

---

## 17. UserProfilePage

**Path:** `/src/app/components/dashboard/UserProfilePage.tsx`
**Export:** `export function UserProfilePage()`

**Features:**
- Profile information display
- Avatar upload
- Skills management
- Experience editing
- Career goals

---

## 18. ATSCircle (Internal)

**Path:** `/src/app/pages/Dashboard.tsx` (defined inside file, not exported)
**Props:** `{ score: number }`
**State:** None

**SVG specs:**
- ViewBox: `0 0 120 120`
- Radius: 54
- Stroke width: 8
- Background circle: `text-border` color
- Progress circle: animated via `motion.circle` with `strokeDashoffset`
- Color logic: `>= 80` violet, `>= 60` amber, else red
- Animation: 1.5s ease-out from full offset to calculated offset

**Note:** If you need this component elsewhere, extract it to `/src/app/components/ATSCircle.tsx` as a named export.

---

## 19. ImageWithFallback (PROTECTED)

**Path:** `/src/app/components/figma/ImageWithFallback.tsx`
**Export:** `export function ImageWithFallback`
**Props:** Same as `<img>` (HTMLImageElement attributes)

**NEVER modify this file.** Use it instead of `<img>` when adding new images:
```tsx
import { ImageWithFallback } from "./components/figma/ImageWithFallback";
<ImageWithFallback src="..." alt="..." className="..." />
```

---

## Component Dependency Graph

```
App
  └─ RouterProvider
       └─ Layout (provides ThemeContext)
            ├─ CustomCursor
            ├─ Home
            │    ├─ GradientMeshBackground
            │    ├─ Navbar (consumes useTheme)
            │    └─ 5 inline sections (Hero, HowItWorks, Features, Pricing, Contact)
            ├─ Dashboard (consumes useTheme)
            │    ├─ OverviewPage
            │    ├─ ResumePage
            │    ├─ JobsPage
            │    ├─ JobDetailPage
            │    ├─ VisaTrackerPage
            │    ├─ AlertsPage
            │    ├─ AnalyticsPage
            │    ├─ SettingsPage
            │    ├─ UserProfilePage
            │    └─ ATSCircle (internal)
            ├─ SignIn
            └─ SignUp
```

---

## Shared Patterns Across Components

| Pattern | Components Using It |
|---|---|
| `whileInView` scroll reveal | Home sections |
| `whileHover={{ y: -N }}` card lift | Job cards (-2), dashboard cards (-4) |
| `whileTap={{ scale: 0.95 }}` | All buttons |
| Section header (uppercase label + gradient heading) | All home sections |
| Glassmorphism card (`bg-card/50 backdrop-blur-sm border-border rounded-2xl`) | Dashboard, Home sections |
| Gradient icon box (`bg-violet-500/10` or gradient bg) | Dashboard, Home |
| Hover gradient overlay (`absolute inset-0 opacity-0 group-hover:opacity-100`) | Feature cards |
| Staggered `delay: i * 0.1` | All grid layouts |
| AnimatePresence for conditional UI | Filters panel, notifications, mobile menu |