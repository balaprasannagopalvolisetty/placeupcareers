# PlaceUp Career - Project Context

## What This Is

PlaceUp Career is a modern, dark-mode-first web platform for career placement, ATS (Applicant Tracking System) resume scoring, and visa sponsorship tracking. It targets global tech talent seeking jobs with visa-sponsoring employers.

## Tech Stack

| Layer | Technology | Version / Notes |
|---|---|---|
| Framework | React | 18.3.1 (via Vite, NOT Next.js) |
| Routing | react-router | 7.13.0 — uses `createBrowserRouter` Data mode. **Do NOT use `react-router-dom`**, it doesn't work in this environment. |
| Styling | Tailwind CSS | v4.1.12 — utility-first. No `tailwind.config.js`; config lives in `/src/styles/theme.css` via `@theme inline`. |
| Animation | motion | 12.23.24 — import as `import { motion } from "motion/react"`. This is the successor to Framer Motion. Always call it "Motion". |
| Icons | lucide-react | 0.487.0 |
| Charts | recharts | 2.15.2 (installed, not yet used — available for analytics pages) |
| Fonts | Inter + Space Grotesk | Loaded via Google Fonts in `/src/styles/fonts.css` |

## File Structure

```
/src
  /app
    App.tsx                          # Root — wraps RouterProvider in a `<div className="dark">`
    routes.ts                        # createBrowserRouter config — Layout wraps all routes
    /components
      Layout.tsx                     # Global layout: ThemeContext provider, AnimatePresence page transitions, CustomCursor
      CustomCursor.tsx               # SVG dot + trailing ring cursor with spring physics
      Navbar.tsx                     # Fixed top nav with glassmorphism, mobile hamburger menu, theme toggle, nav links
      GradientMeshBackground.tsx     # Canvas-based animated gradient mesh with floating orbs and particles (fixed, z-index: -1)
      CareerNetworkBackground.tsx    # Career-themed network background (deprecated - replaced by GradientMeshBackground)
      DNAHelixBackground.tsx         # Legacy DNA helix background (deprecated)
      ParticleBackground.tsx         # Legacy particle background (deprecated)
      /dashboard
        ResumePage.tsx               # Resume upload, ATS scoring, version management
        JobsPage.tsx                 # Job matching with filters (Title, Time, Location, Status)
        JobDetailPage.tsx            # Detailed job view with ATS analysis, keywords, visa info
        VisaTrackerPage.tsx          # Visa sponsorship data by employer
        AlertsPage.tsx               # Job alerts and notifications management
        AnalyticsPage.tsx            # Career analytics and insights
        SettingsPage.tsx             # User preferences and account settings
        UserProfilePage.tsx          # User profile and career information
      /sections
        HeroSection.tsx              # Landing hero with gradient orbs, staggered text reveal, stats bar
        HowItWorksSection.tsx        # 4-step card grid (Upload, ATS, Matching, Placement)
        FeaturesSection.tsx          # 6-feature card grid with hover effects
        PricingSection.tsx           # 3-tier pricing (Basic/Pro/Elite) with popular badge
        ContactSection.tsx           # Newsletter CTA + full footer with link columns
      /figma
        ImageWithFallback.tsx        # PROTECTED — do not modify. Use instead of <img> for new images.
      /ui                            # Empty — available for shared UI primitives
    /pages
      Home.tsx                       # Scrollytelling landing page with 5 sections (300vh scroll container)
      Dashboard.tsx                  # Authenticated dashboard with 8 pages (Overview + 7 sub-pages)
      SignIn.tsx                     # Authentication - Sign In page
      SignUp.tsx                     # Authentication - Sign Up page
  /styles
    fonts.css                        # Google Fonts imports (Inter, Space Grotesk)
    theme.css                        # CSS custom properties for light/dark mode + Tailwind @theme inline tokens
    index.css                        # Global entry CSS
    tailwind.css                     # Tailwind base imports
  /imports                           # Figma-imported assets (SVGs, pasted text)

/docs                                # All project documentation (single location)
  agents.md                          # AI agent instructions
  anti-patterns.md                   # Common mistakes to avoid
  backend-pipeline.md                # Google Cloud backend architecture & pipelines
  component-registry.md              # All components with props, state, dependencies
  context.md                         # This file — project architecture overview
  guidelines.md                      # Design system & development guidelines
  security-pipeline.md               # Google Cloud security architecture
  skills.md                          # Copy-paste component patterns
  ATTRIBUTIONS.md                    # Third-party attributions
```

## Design System

### Colors
- **Primary**: Violet (#8b5cf6) / Indigo (#6366f1) gradients
- **Accent**: Fuchsia (#d946ef) / Purple (#9333ea)
- **Success**: Green (#22c55e)
- **Warning**: Orange (#f59e0b)
- **Error**: Red (#ef4444)
- **Background**: 
  - Dark: #030712 (gray-950)
  - Light: #ffffff
- **Glassmorphism**: `backdrop-blur-md` + `bg-card/30` + `border-border`

### Typography
- **Headings**: Space Grotesk (700-800 weight)
- **Body**: Inter (400-600 weight)
- **Font sizes**: Responsive via `clamp()` for headings

### Animation Patterns
- **Scroll-driven**: Home page uses 300vh scroll container with section fade in/out
- **Page transitions**: Spatial wipe effect via Motion AnimatePresence
- **Hover states**: `whileHover={{ y: -8 }}` for cards
- **Stagger children**: `transition={{ delay: index * 0.1 }}`

## Key Features

### Home Page (Scrollytelling)
- **300vh scroll container** with fixed viewport
- **5 sections**: Hero, How It Works, Features, Pricing, Contact
- **Gradient Mesh Background**: Animated orbs with blur effect, subtle grid, floating particles
- **Scroll progress bar**: Bottom of page, violet gradient
- **Section transitions**: Fade in/out based on scroll position (0-1)
- **Scroll indicator**: Animated chevron at bottom of hero

### Dashboard (8 Pages)
1. **Overview**: ATS score circle, top job matches, visa tracker preview
2. **Resumes**: Upload, manage versions, ATS scoring
3. **Jobs**: Advanced filtering (Title, Time Posted, Location, Status), job cards with match scores
4. **Job Detail**: Full job description, ATS score for position, strong/missing keywords, visa info, benefits
5. **Visa Tracker**: Employer sponsorship data, approval rates
6. **Alerts**: Job notifications and alert management
7. **Analytics**: Career insights and statistics
8. **Settings**: User preferences, theme toggle, account management

### Job Detail Page Features
- Full job information (title, company, location, salary, description)
- **ATS Score for specific position** (94/100)
- **Strong Keywords**: Matched keywords from resume with frequency counts
- **Missing Keywords**: Impact levels + specific suggestions for improvement
- **Visa Information**: Sponsorship types, approval rate, recent approvals
- **Benefits & Perks**: Complete list
- **Apply button**: Redirects to original job post
- Back navigation to jobs list

### Advanced Job Filters
- **Job Title**: Dropdown with all unique job titles
- **Time Posted**: 6 Hours, 1 Day, 3 Days, All Time
- **Location**: Dropdown with all unique locations
- **Status**: All, New, Applied, Interview, Saved
- **Search**: Real-time search across title, company, location
- **Active Filters Display**: Pills showing active filters with remove buttons
- **Clear All**: One-click filter reset

### Authentication
- Sign In page with email/password
- Sign Up page with terms acceptance
- Redirect to dashboard after auth
- Logout functionality in user menu

### Theme System
- **Dark mode default**: Violet-tinted dark backgrounds
- **Light mode**: Clean white backgrounds with subtle violet accents
- **Toggle**: Sun/Moon icon in navbar and settings
- **Context**: ThemeContext provides `{ dark, toggle }` globally

## Animation Performance
- **Motion variants**: Used for complex stagger/fade animations
- **Canvas animations**: RequestAnimationFrame for smooth 60fps
- **Lazy rendering**: Particles reduce on low-end hardware
- **Will-change**: Applied to frequently animated elements

## State Management
- **React Context**: Theme (dark/light mode)
- **useState**: Local component state (filters, modals, selected items)
- **Navigation state**: React Router handles page state

## Routing Strategy
- **Home** (`/`): Landing page
- **Dashboard** (`/dashboard`): Protected dashboard with sub-pages rendered conditionally
- **Sign In** (`/signin`): Authentication
- **Sign Up** (`/signup`): Registration

## Mock Data
All data is currently mocked:
- Job listings with match scores, visa status, timestamps
- Visa sponsorship statistics by employer
- User profile information
- Resume versions and ATS scores

## Backend Infrastructure (Google Cloud + Firebase)
See `/docs/backend-pipeline.md` for full details.

- **Compute**: Google Cloud Run (serverless containers)
- **Database**: **Firebase Firestore** (NoSQL document database — replaces PostgreSQL)
- **Firestore Security**: Firestore Security Rules (client-side) + Firebase Admin SDK (server-side)
- **Cache**: Cloud Memorystore (Redis)
- **Queue**: Cloud Tasks + Cloud Pub/Sub
- **Scheduler**: Google Cloud Scheduler
- **Storage**: Google Cloud Storage (GCS) — resume files, backups
- **Secrets**: Google Secret Manager
- **WAF/DDoS**: Google Cloud Armor
- **Load Balancer**: Google Cloud HTTP(S) Load Balancing
- **API Gateway**: Google Cloud Apigee
- **CI/CD**: Google Cloud Build + Artifact Registry
- **DNS**: Google Cloud DNS (domain managed via Google)
- **Email**: Gmail API via Google Workspace (jobs@placeupcareer.com)
- **Monitoring**: Cloud Monitoring + Cloud Logging + Security Command Center
- **Search**: Algolia (full-text job search — Firestore extension)

## Browser Support
- Modern browsers (Chrome, Firefox, Safari, Edge)
- CSS Grid, Flexbox
- Canvas 2D API
- CSS backdrop-filter (for glassmorphism)

## Performance Considerations
- Canvas animations use requestAnimationFrame
- Images use lazy loading
- Components use React.memo where appropriate
- Scroll events throttled in Home.tsx

## Accessibility
- Semantic HTML elements
- ARIA labels on interactive elements
- Keyboard navigation support
- Color contrast meets WCAG AA standards
- Focus visible states

## Future Enhancements
- Backend API integration (currently all mock data)
- Real-time ATS scoring engine
- Live visa data feeds
- Interview scheduling
- Resume AI rewrite service
- Salary negotiation tools