# PlaceUp Career - Development Guidelines

## General Guidelines

* **Dark Mode First**: Always design with dark mode as the default. Light mode is secondary.
* **Responsive Design**: Use Tailwind's responsive prefixes (`sm:`, `md:`, `lg:`, `xl:`). Mobile-first approach.
* **Motion Animations**: Use Motion (not Framer Motion) for all animations. Import as `import { motion } from "motion/react"`.
* **Component Structure**: Keep components small and focused. Extract repeated UI patterns into separate components.
* **File Organization**: Dashboard components go in `/src/app/components/dashboard/`. Shared components in `/src/app/components/`.
* **No External Images**: Always use the `unsplash_tool` for images. For Figma imports, use the `figma:asset` scheme.
* **State Management**: Use `useState` for local state. Use `ThemeContext` for theme. No Redux/Zustand needed yet.
* **Routing**: Use `react-router` (NOT `react-router-dom`). Use Data mode with `createBrowserRouter`.
* **Documentation**: All MD docs live in `/docs/`. Never create docs outside this folder.

---

## Design System Guidelines

### Color Palette

**Primary Colors:**
* Violet: `#8b5cf6` (violet-500)
* Indigo: `#6366f1` (indigo-500)
* Use gradient combinations: `from-violet-600 to-indigo-600`

**Accent Colors:**
* Fuchsia: `#d946ef`
* Purple: `#9333ea`

**Semantic Colors:**
* Success/Visa: `#22c55e` (green-500)
* Warning: `#f59e0b` (orange-500)
* Error: `#ef4444` (red-500)
* Info: `#3b82f6` (blue-500)

**Background:**
* Dark mode: `#030712` (gray-950)
* Light mode: `#ffffff`
* Card backgrounds: `bg-card/50` with `backdrop-blur-md`

### Typography

**Font Families:**
* **Headings**: Space Grotesk (700-800 weight)
* **Body**: Inter (400-600 weight)

**Font Sizes (use inline styles, not Tailwind classes):**
* Hero heading: `clamp(40px, 8vw, 80px)`
* Section heading: `clamp(28px, 4vw, 44px)`
* Card title: `18px` (weight 600)
* Body text: `14px` (line-height 1.6)
* Small text: `12-13px`

**DO NOT use Tailwind font classes** like `text-2xl`, `font-bold`, or `leading-none` unless user specifically requests it.

### Spacing & Layout

* **Card padding**: `p-6` or `p-8` for large cards
* **Grid gaps**: `gap-4` (16px) or `gap-6` (24px)
* **Section spacing**: `space-y-6` between major sections
* **Max width containers**: `max-w-7xl` for dashboard, `max-w-5xl` for landing content

### Glassmorphism Pattern

**Standard Card:**
```tsx
className="p-6 rounded-2xl border border-border bg-card/50 backdrop-blur-md"
```

**Hover States:**
```tsx
className="hover:border-violet-500/30 transition cursor-pointer"
whileHover={{ y: -4 }}
```

### Animation Patterns

**Card Hover Lift:**
```tsx
whileHover={{ y: -8 }}
transition={{ duration: 0.3 }}
```

**Button Press:**
```tsx
whileTap={{ scale: 0.95 }}
```

**Staggered Grid Reveal:**
```tsx
initial={{ opacity: 0, y: 20 }}
animate={{ opacity: 1, y: 0 }}
transition={{ delay: index * 0.1 }}
```

**Scroll-Driven (Home page):**
```tsx
const opacity = useTransform(scrollYProgress, [start, end], [0, 1])
```

### Buttons

**Primary Button (CTA):**
```tsx
className="px-6 py-3 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white hover:opacity-90 transition"
```

**Secondary Button (Outline):**
```tsx
className="px-6 py-3 rounded-xl border border-border hover:bg-accent transition"
```

**Icon Button:**
```tsx
className="p-3 rounded-lg hover:bg-accent transition"
```

### Badges

**Status Badge:**
```tsx
className="px-2 py-1 rounded bg-violet-500/10 text-violet-400"
```

**Visa Sponsored:**
```tsx
className="px-3 py-1 rounded-full bg-green-500/10 text-green-400 border border-green-500/30"
```

---

## Home Page Guidelines

### Scrollytelling Structure

* **Total height**: `300vh` scroll container
* **Fixed viewport**: All content rendered in fixed overlay
* **5 Sections**: Each section has defined scroll ranges (0-1)
* **Section transitions**: Fade in/out with slight Y parallax
* **Background**: `GradientMeshBackground` with scroll-reactive animations

### Section Visibility Ranges

```ts
Hero:        0.00 → 0.19
How It Works: 0.14 → 0.38
Features:     0.33 → 0.58
Pricing:      0.53 → 0.78
Contact:      0.73 → 1.00
```

### Scroll Indicator

* Only visible at scroll position 0-0.06
* Animated chevron with "SCROLL" text
* Fades out as user starts scrolling

---

## Dashboard Guidelines

### Navigation Pattern

* **Sidebar**: 7 navigation items (Overview, Resumes, Jobs, Visa Tracker, Alerts, Analytics, Settings)
* **Active state**: Violet background with border
* **Mobile**: Slide-in sidebar with backdrop overlay
* **Top bar**: Search, notifications (with badge), theme toggle, user menu

### Dashboard Page Types

**Overview Page:**
* Large stats cards (ATS score circle, applications, interviews)
* Top job matches (3-5 items)
* Visa tracker preview

**List Pages (Jobs, Resumes, Alerts):**
* Search bar at top
* Filter buttons/dropdowns
* Stats overview (4 cards)
* List of items with actions

**Detail Pages (Job Detail, User Profile):**
* Back button
* Header section with key info
* Multiple content sections
* Sidebar with related info

### Job Detail Page Structure

**Required Sections:**
1. Header (title, company, match score, actions)
2. ATS Score for This Position
3. Strong Keywords (from resume)
4. Missing Keywords (suggestions)
5. Job Description (responsibilities, requirements, nice-to-have)
6. Sidebar (visa info, benefits, company info)

### Filter Patterns

**Advanced Filters:**
* Collapsible panel with `AnimatePresence`
* 3-column grid for filter dropdowns
* Active filters displayed as removable pills
* Filter count badge on Filters button
* "Clear All" button when filters active

**Filter Types:**
* **Status**: Horizontal button group (All, New, Applied, Interview, Saved)
* **Dropdown**: Job Title, Time Posted, Location
* **Search**: Real-time text filtering

---

## Backend Infrastructure Guidelines

All backend services run on **Google Cloud Platform (GCP)**. The domain `placeupcareer.com` is managed via **Google Cloud DNS**. The primary database is **Firebase Firestore** (NoSQL, serverless).

### Google Cloud + Firebase Services Used

| Service | GCP / Firebase Product |
|---------|------------------------|
| WAF & DDoS | Google Cloud Armor |
| Load Balancer | Google Cloud HTTP(S) Load Balancing |
| API Gateway | Google Cloud Apigee |
| Compute | Google Cloud Run (serverless) |
| Task Queue | Google Cloud Tasks + Cloud Pub/Sub |
| **Database** | **Firebase Firestore (NoSQL document DB)** |
| Cache | Cloud Memorystore (Redis) |
| Object Storage | Google Cloud Storage (GCS) |
| Secrets | Google Secret Manager |
| Encryption | Cloud KMS (field-level PII encryption) |
| Email | Gmail API via Google Workspace |
| CI/CD | Google Cloud Build + Artifact Registry |
| DNS | Google Cloud DNS |
| Monitoring | Cloud Monitoring + Cloud Logging |
| Security | Security Command Center (SCC) |
| Scheduler | Google Cloud Scheduler |
| Full-text Search | Algolia (Firebase Extension) |

### Firebase Firestore Key Rules
- Server-side access via **Firebase Admin SDK** (Cloud Run) — bypasses Security Rules
- Client-side access via **Firebase Client SDK** (browser) — governed by Security Rules
- **Never** expose Admin SDK credentials to the browser
- **Firestore Security Rules** (`firestore.rules`) enforce client-side multi-tenant isolation
- **CMEK** via Cloud KMS available on Blaze plan for encryption key control
- Sensitive PII fields (MFA secrets, contact emails) encrypted with Cloud KMS before writing to Firestore

See `/docs/backend-pipeline.md` for full architecture details.
See `/docs/security-pipeline.md` for security configuration.

---

## Performance Guidelines

* **Canvas animations**: Always use `requestAnimationFrame`
* **Scroll events**: Use Motion's `useScroll` hook, not raw event listeners
* **Conditional rendering**: Use `AnimatePresence` for mount/unmount animations
* **Image loading**: Use `ImageWithFallback` component for error handling
* **Large lists**: Consider virtualization if > 100 items (not implemented yet)

---

## Accessibility Guidelines

* **Semantic HTML**: Use `<button>`, `<nav>`, `<section>`, `<header>` appropriately
* **ARIA labels**: Add to icon-only buttons
* **Focus states**: Always visible with `focus:` Tailwind classes
* **Color contrast**: Maintain WCAG AA standards (especially in light mode)
* **Keyboard navigation**: All interactive elements keyboard accessible

---

## Code Style Guidelines

**Component Structure:**
```tsx
// 1. Imports
import { useState } from "react";
import { motion } from "motion/react";

// 2. Mock data / constants (if component-specific)
const jobs = [...];

// 3. Component
export function ComponentName({ prop1 }: Props) {
  // 4. State
  const [value, setValue] = useState("");
  
  // 5. Handlers
  const handleClick = () => { ... };
  
  // 6. Render
  return ( ... );
}
```

**Naming Conventions:**
* **Components**: PascalCase (`JobsPage`, `ATSCircle`)
* **Props**: camelCase (`onJobClick`, `selectedId`)
* **Files**: PascalCase for components (`JobsPage.tsx`)
* **State variables**: camelCase (`isOpen`, `selectedFilter`)

**Import Order:**
1. React imports
2. Third-party libraries (motion, lucide-react, etc.)
3. Local components
4. Types (if separate file)

---

## Testing & Validation

**Before committing:**
* [ ] Test in both dark and light modes
* [ ] Check mobile responsiveness (sm, md, lg, xl breakpoints)
* [ ] Verify all animations are smooth (60fps)
* [ ] Test keyboard navigation
* [ ] Check console for errors/warnings
* [ ] Verify all links/buttons have proper hover states

---

## Common Mistakes to Avoid

* ❌ Using `react-router-dom` instead of `react-router`
* ❌ Adding Tailwind config file (use `@theme inline` in theme.css)
* ❌ Using Framer Motion (use Motion instead)
* ❌ Hardcoding font sizes with Tailwind classes
* ❌ Forgetting to add `whileHover`/`whileTap` to interactive elements
* ❌ Not extracting repeated components
* ❌ Modifying protected files (`ImageWithFallback.tsx`)
* ❌ Adding absolute positioning unnecessarily
* ❌ Putting docs/MD files outside `/docs/`
* ❌ Using AWS/Cloudflare/Supabase services — all infrastructure is Google Cloud + Firebase
* ❌ Exposing Firebase Admin SDK credentials to the browser
* ❌ Writing raw SQL — Firestore uses document queries, not SQL
* ❌ Storing plaintext PII (MFA secrets, emails) in Firestore without Cloud KMS encryption

---

## Future Enhancements Roadmap

**Phase 1 (Current):**
* ✅ Complete landing page with scrollytelling
* ✅ Authentication pages (Sign In/Sign Up)
* ✅ Dashboard with 8 pages
* ✅ Job detail page with ATS analysis
* ✅ Advanced job filters
* ✅ Google Cloud infrastructure migration

**Phase 2 (Next):**
* [ ] Backend API integration (Google Cloud Run services)
* [ ] Real ATS scoring engine
* [ ] Live visa data feeds (Firebase Firestore real-time listeners)
* [ ] Resume AI rewrite service (Vertex AI)
* [ ] Interview scheduling
* [ ] Google Sign-In OAuth2 integration
* [ ] Algolia search integration for job full-text search

**Phase 3 (Future):**
* [ ] One-click apply integration
* [ ] Salary negotiation tools (Vertex AI)
* [ ] Career coaching AI (Gemini API)
* [ ] Mobile app (React Native)
* [ ] Multi-region GCP deployment


 Some of the base components you are using may have styling(eg. gap/typography) baked in as defaults.
So make sure you explicitly set any styling information from the guidelines in the generated react to override the defaults.