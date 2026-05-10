Here is the complete Figma UI design prompt with all colors replaced by your specified palette (#011126, #F2EEB3, #8C3A27, #A6372D, #401212). Nothing else has been changed—structure, component definitions, page layouts, and all other specifications remain exactly as you provided.

```text
╔══════════════════════════════════════════════════════════════════════════════════╗
║          PLACEUP CAREER — COMPLETE FIGMA UI DESIGN PROMPT                      ║
║          For Outstanding 3D-Interactive Premium Website                         ║
║          Version 1.0 · March 2026 · Confidential                               ║
╚══════════════════════════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SECTION 0 — READ THIS BEFORE OPENING FIGMA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BENCHMARK SITES — Study all of these. Understand WHY they feel premium:
  • https://jobright.ai            ← Primary UI benchmark (surpass this)
  • https://linear.app             ← Precision, clean glass, depth
  • https://vercel.com/dashboard   ← Dashboard information density done right
  • https://www.framer.com         ← Scroll animation + 3D visual integration
  • https://apple.com/airpods-pro  ← Scroll-driven 3D product storytelling

WHAT MAKES THIS DIFFERENT FROM GENERIC AI STARTUP DESIGNS:
  ✗ NOT: purple gradient dumped on white background
  ✗ NOT: generic hero with floating emoji icons
  ✗ NOT: inconsistent card padding and misaligned text
  ✗ NOT: light mode that just "inverts" the dark mode colors
  ✗ NOT: 3D that feels bolted on, disconnected from the rest of the page

  ✓ YES: Deep space dark with precise green-teal-blue gradient accents
  ✓ YES: 3D home page where the visual IS the story — not decoration
  ✓ YES: Perfect 8px grid alignment — every element snaps
  ✓ YES: Light mode that is a genuinely different design, not a color swap
  ✓ YES: Dashboard that feels like a Bloomberg terminal meets Linear

PRODUCT: PlaceUp Career — AI-powered job placement for international students
  on F1-CPT, F1-OPT, F1-STEM OPT, H-1B visa pathways in US + Canada.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SECTION 1 — FIGMA VARIABLES SETUP (DO THIS FIRST — BEFORE ANY FRAMES)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Create a Variables collection named "PlaceUp / Design Tokens"
Every color in every frame MUST reference a variable. Raw hex = rejected.

── 1A. COLOR VARIABLES ──────────────────────────────────────────────────────────

Group: bg/
  bg/page           Dark:#011126    Light:#F2EEB3
  bg/surface        Dark:#401212    Light:#FFFFFF
  bg/elevated       Dark:#8C3A27    Light:#F2EEB3
  bg/glass          Dark:rgba(64,18,18,0.7)   Light:rgba(242,238,179,0.88)
  bg/glass-hover    Dark:rgba(64,18,18,0.85)   Light:rgba(242,238,179,0.97)
  bg/overlay        Dark:rgba(1,17,38,0.92)      Light:rgba(242,238,179,0.92)

Group: text/
  text/primary      Dark:#F2EEB3    Light:#011126
  text/secondary    Dark:rgba(242,238,179,0.7)    Light:#401212
  text/tertiary     Dark:rgba(242,238,179,0.5)    Light:#8C3A27
  text/accent       Dark:#A6372D    Light:#A6372D
  text/on-gradient  Dark:#FFFFFF    Light:#FFFFFF   (always white — on gradient BGs)

Group: border/
  border/default    Dark:#401212    Light:#8C3A27
  border/subtle     Dark:#011126    Light:#F2EEB3
  border/focus      Dark:#A6372D    Light:#A6372D
  border/glass      Dark:rgba(242,238,179,0.08)  Light:rgba(1,17,38,0.06)
  border/hover      Dark:rgba(166,55,45,0.4)     Light:rgba(166,55,45,0.4)
  border/elite      Dark:rgba(140,58,39,0.5)    Light:rgba(140,58,39,0.5)

Group: brand/
  brand/grad-start  #8C3A27   (both modes)
  brand/grad-mid    #A6372D   (both modes)
  brand/grad-end    #401212   (both modes)
  brand/violet      #A6372D   (both modes)
  brand/indigo      #8C3A27   (both modes)
  brand/glow        rgba(166,55,45,0.25)
  brand/violet-glow rgba(140,58,39,0.3)

Group: semantic/
  semantic/success  #A6372D
  semantic/warning  #8C3A27
  semantic/error    #401212
  semantic/info     #011126

Group: ats/
  ats/high          #A6372D    (score 80-100 — red)
  ats/medium        #8C3A27    (score 60-79 — burnt red)
  ats/low           #401212    (score 0-59  — dark red)
  ats/ring-track    rgba(242,238,179,0.08)

Group: plan/
  plan/basic        #8C3A27
  plan/pro          #A6372D
  plan/elite        #401212
  plan/elite-glow   rgba(64,18,18,0.35)

── 1B. TEXT STYLE LIBRARY ───────────────────────────────────────────────────────

Font families used:
  Headings / Numbers: "Plus Jakarta Sans" (weights 600, 700, 800)
  Body / UI:          "Plus Jakarta Sans" (weights 300, 400, 500)
  Monospace:          "JetBrains Mono" (weights 400, 500) — OTP, ATS scores, code

NOTE: Do NOT use Inter, Space Grotesk, or system fonts.
Plus Jakarta Sans is the single font family for both headings and body.
It has enough weight range to carry both roles with excellent screen rendering.

Text Styles:

  Display/Hero
    Font: Plus Jakarta Sans 800
    Size: 72px (design at this; responsive via clamp in code)
    Line height: 1.06
    Letter spacing: -2.5%

  Display/Section
    Font: Plus Jakarta Sans 700
    Size: 48px
    Line height: 1.1
    Letter spacing: -1.5%

  Display/Subsection
    Font: Plus Jakarta Sans 700
    Size: 32px
    Line height: 1.2
    Letter spacing: -1%

  Heading/Card
    Font: Plus Jakarta Sans 600
    Size: 18px
    Line height: 1.3

  Heading/Small
    Font: Plus Jakarta Sans 600
    Size: 15px
    Line height: 1.4

  Body/Large
    Font: Plus Jakarta Sans 400
    Size: 17px
    Line height: 1.75

  Body/Base
    Font: Plus Jakarta Sans 400
    Size: 14px
    Line height: 1.65

  Body/Small
    Font: Plus Jakarta Sans 400
    Size: 13px
    Line height: 1.55

  Label/Overline
    Font: Plus Jakarta Sans 600
    Size: 11px
    Line height: 1.4
    Letter spacing: +10%
    Text transform: UPPERCASE

  Label/Badge
    Font: Plus Jakarta Sans 700
    Size: 11px
    Letter spacing: +5%

  Mono/Display
    Font: JetBrains Mono 500
    Size: 28px

  Mono/OTP
    Font: JetBrains Mono 400
    Size: 24px
    Letter spacing: +8px (wide for OTP boxes)

── 1C. EFFECT STYLES ────────────────────────────────────────────────────────────

Glass/Card-Dark
  Fill: bg/glass
  Backdrop filter: blur(24px) saturate(180%)
  Border: 1px border/glass
  Corner radius: 20px

Glass/Card-Light
  Fill: bg/glass
  Backdrop filter: blur(24px) saturate(180%)
  Border: 1px rgba(1,17,38,0.06)
  Drop shadow: 0 4px 32px rgba(1,17,38,0.06), 0 1px 4px rgba(1,17,38,0.04)
  Corner radius: 20px

Glow/Green (primary brand)
  Drop shadow: 0 0 48px rgba(166,55,45,0.35), 0 0 16px rgba(166,55,45,0.2)

Glow/Violet (elite / ATS high)
  Drop shadow: 0 0 48px rgba(140,58,39,0.35), 0 0 16px rgba(140,58,39,0.2)

Glow/Blue
  Drop shadow: 0 0 32px rgba(1,17,38,0.3)

Shadow/Card
  Drop shadow: 0 4px 24px rgba(1,17,38,0.12), 0 1px 4px rgba(1,17,38,0.08)

Shadow/Card-Hover
  Drop shadow: 0 16px 48px rgba(1,17,38,0.22), 0 4px 16px rgba(1,17,38,0.12)

Shadow/Navbar
  Drop shadow: 0 1px 0 border/default (bottom only)

── 1D. SPACING SYSTEM ───────────────────────────────────────────────────────────

Base unit: 8px
Scale: 4, 8, 12, 16, 20, 24, 32, 40, 48, 56, 64, 80, 96, 128, 160px
Grid: 12 columns, 24px gutters, 64px margins (desktop), 24px (tablet), 16px (mobile)
Max content width: 1280px centered
Section vertical padding: 96px (desktop), 64px (tablet), 48px (mobile)
Card internal padding: 24px (standard), 32px (large), 40px (hero-size)

── 1E. BORDER RADIUS SCALE ──────────────────────────────────────────────────────

4px   — tags, small badges, table cells
8px   — inputs, icon containers, small buttons
12px  — buttons, chips, tooltips
16px  — panels, form sections
20px  — cards (primary radius)
28px  — large feature cards, modals
9999px — pills, avatar circles, notification dots

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SECTION 2 — COMPONENT LIBRARY (BUILD ALL BEFORE ANY SCREENS)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Every component: 4 variants minimum = Default / Hover / Focus / Disabled
Every component: 2 mode variants = Dark / Light
Build as Figma components with auto-layout.

── COMPONENT 01: BUTTON ─────────────────────────────────────────────────────────

Variants: Primary / Secondary / Ghost / Destructive / Icon-only
Sizes: SM (h:36px) / MD (h:44px) / LG (h:52px)

PRIMARY (gradient brand):
  Background: linear-gradient(135deg, #8C3A27 0%, #A6372D 50%, #401212 100%)
  Text: Plus Jakarta Sans 15px 700, text/on-gradient (#FFFFFF)
  Padding: 0 28px (LG), 0 22px (MD), 0 16px (SM)
  Corner radius: 12px
  Right icon: ArrowRight 18px (translateX +3px on hover in prototype)
  Hover state: opacity 0.88 + Glow/Green shadow + translateY -2px
  Active state: scale 0.97

SECONDARY (glass outline):
  Background: bg/glass
  Border: 1px border/glass → 1px border/focus on hover
  Text: text/primary
  Padding: same as primary
  Corner radius: 12px
  Hover: bg/glass-hover + border/hover

GHOST (text only):
  No background, no border
  Text: text/secondary → text/primary on hover
  Padding: 0 12px

── COMPONENT 02: INPUT FIELD ────────────────────────────────────────────────────

Height: 48px
Background: rgba(242,238,179,0.04) dark / rgba(1,17,38,0.03) light
Border: 1px border/default
Corner radius: 12px
Padding: 0 16px
Font: Plus Jakarta Sans 14px 400

States:
  Default: border/default
  Focus: border/focus + 0 0 0 3px rgba(166,55,45,0.15) outer glow
  Filled: border/default, darker background tint
  Error: border/semantic/error + shake animation note + error text below
  Success: border/semantic/success + checkmark icon right 16px

Floating label variant:
  Label starts at center (placeholder position)
  On focus/fill: label moves to top-left, 11px, text/accent color

── COMPONENT 03: GLASS CARD ─────────────────────────────────────────────────────

Base: Glass/Card-Dark or Glass/Card-Light effect
Padding: 24px
Corner radius: 20px
Content slots: Header / Body / Footer / Icon (all optional)

Hover state (separate variant):
  Glass/Card-Dark + Shadow/Card-Hover + border/hover
  translateY: -8px (describe in variant note)

Left accent variant (for Job Cards):
  Left side: 4px solid color-by-ATS (green/amber/red)
  All other sides: glass border

Featured variant:
  Top border: 2px gradient linear (brand/grad-start → brand/grad-end)
  Background: slightly higher opacity than default glass

── COMPONENT 04: ATS SCORE RING ─────────────────────────────────────────────────

Canvas: 80px × 80px (card size), 120px × 120px (detail page)
Ring track: 8px stroke, ats/ring-track color
Ring progress: 8px stroke, color by score
Corner of ring ends: round linecap

High (80-100): stroke color #A6372D + Glow: 0 0 16px rgba(166,55,45,0.4)
Medium (60-79): stroke color #8C3A27 + Glow: 0 0 16px rgba(140,58,39,0.4)
Low (0-59):    stroke color #401212 + Glow: 0 0 16px rgba(64,18,18,0.4)

Center content (80px version):
  Score: JetBrains Mono 500 22px, color matches ring
  "ATS" label: 10px text/tertiary below

Center content (120px detail version):
  Score: JetBrains Mono 500 32px
  "/100": 16px text/tertiary
  "ATS Match": 11px text/tertiary below

── COMPONENT 05: JOB CARD ───────────────────────────────────────────────────────

This is the most used and most important component. Design perfectly.

Width: flexible (min 340px, max 480px)
Height: auto
Background: Glass/Card
Left accent: 4px solid (ats/high, ats/medium, or ats/low)
Corner radius: 20px
Padding: 22px 24px

Layout (top to bottom, with auto-layout):

  ROW 1 (space between):
    Left cluster:
      Company logo: 44px × 44px circle, gradient background with initials if no logo
      Stack: Job title (Heading/Card, Plus Jakarta Sans 600 17px) + Company · Location (13px text/secondary)
    Right: ATS Ring Component (80px)

  DIVIDER: 1px border/subtle, margin 12px 0

  ROW 2: Visa status badges (horizontal flex, gap 6px, flex-wrap)
    F1-CPT:  bg rgba(1,17,38,0.12) text #011126 border rgba(1,17,38,0.25)
    F1-OPT:  bg rgba(166,55,45,0.12) text #A6372D border rgba(166,55,45,0.25)
    F1-STEM: bg rgba(140,58,39,0.12)  text #8C3A27 border rgba(140,58,39,0.25)
    H1B:     bg rgba(64,18,18,0.12) text #401212 border rgba(64,18,18,0.25)

  ROW 3: ATS progress bar
    Full width, height 4px, corner radius 2px
    Track: rgba(242,238,179,0.06)
    Fill: color matches ring (green/amber/red), animated left to right on load

  ROW 4: Skill badges (gap 6px, flex-wrap)
    Matched: bg rgba(166,55,45,0.1) text #A6372D border rgba(166,55,45,0.2) — "React" "TypeScript"
    Missing: bg rgba(64,18,18,0.1) text #401212 border rgba(64,18,18,0.2) — prefix "Missing:"

  ROW 5 (space between, margin-top 16px):
    Left: Posted date (12px text/tertiary) + Featured badge if applicable
    Right: "Apply Now ↗" ghost button + "Details" ghost button

Hover state of entire card: translateY -8px + Shadow/Card-Hover + border/hover glow

── COMPONENT 06: BADGE / CHIP ───────────────────────────────────────────────────

Sizes: XS (h:20px) / SM (h:24px) / MD (h:28px)
Corner radius: 4px

Variants:
  Default:    border/glass bg, text/secondary
  Visa:       color-coded as Job Card row 2 above
  Matched:    green tint (as above)
  Missing:    red tint (as above)
  Featured:   bg linear-gradient(brand/grad-start, brand/grad-end), text white, no border
  Plan-Basic: plan/basic colors
  Plan-Pro:   plan/pro colors
  Plan-Elite: plan/elite colors + Glow/Violet

── COMPONENT 07: NAVBAR ─────────────────────────────────────────────────────────

Height: 64px
Position: fixed top
Background at top: transparent
Background on scroll: bg/glass + backdrop-blur-xl + Shadow/Navbar bottom
Border bottom: 1px border/default (appears on scroll only)

Layout (12-col grid, max-width 1280px):
  Left (3 cols): Logo mark (28px gradient rounded square) + "PlaceUp" Plus Jakarta Sans 700 18px + "Career" text/accent 600 14px
  Center (6 cols): Nav items flex centered, gap 4px — "How It Works" "Features" "Pricing" "Contact Us"
  Right (3 cols): Dark/Light toggle pill + "Sign In" ghost button + "Get Started" primary button SM

Nav item:
  Default: text/secondary 14px 500, no underline
  Active: text/primary + 2px bottom border brand/grad-start
  Hover: text/primary, smooth 200ms

Mobile (< 768px):
  Right side: Hamburger menu only (24px icon)
  Drawer opens from right: full height, bg/overlay, all nav items stacked
  Drawer animation: translateX(100%) → translateX(0), 300ms ease

── COMPONENT 08: SIDEBAR NAV ITEM ───────────────────────────────────────────────

Height: 40px
Padding: 0 12px
Corner radius: 10px
Gap: 10px (icon + label)
Icon: 18px lucide-react icon

Default: text/secondary, no background
Hover: bg/elevated, text/primary
Active: bg rgba(166,55,45,0.09), left border 2px brand/grad-start, text brand/grad-start 600

── COMPONENT 09: OTP INPUT (6 boxes) ────────────────────────────────────────────

Each box: 52px wide × 60px tall
Gap between boxes: 8px
Background: rgba(242,238,179,0.04)
Border: 1.5px border/default
Corner radius: 12px
Font: JetBrains Mono 400 24px center-aligned

States:
  Empty: border/default
  Focused (current active box): border/focus + 0 0 0 4px rgba(166,55,45,0.15)
  Filled: border rgba(242,238,179,0.15), slightly lighter background
  Error: border/semantic/error + horizontal shake (show in prototype)
  Success: border/semantic/success

Countdown timer (below boxes):
  Circular SVG: 40px × 40px
  Track: 2px rgba(242,238,179,0.08)
  Progress: 2px brand/grad-start → ats/medium (60s) → ats/low (30s)
  Center: countdown time, JetBrains Mono 12px, text matches ring color
  Disappears at 0, replaced by "Resend OTP" text link

── COMPONENT 10: PRICING CARD ───────────────────────────────────────────────────

Width: 360px (max), flexible minimum
Corner radius: 24px
Padding: 40px 32px

BASIC:
  Background: Glass/Card
  Top label: "Basic" Plan/basic color, Label/Overline
  Price: "$9.99" Plus Jakarta Sans 800 52px + "/mo" 16px text/secondary

PRO (most popular):
  Background: Glass/Card + slight red tint bg rgba(166,55,45,0.04)
  Top border: 2px solid brand/grad-start (replaces standard glass border)
  Glow: Glow/Green shadow
  "MOST POPULAR" badge: pill above card, gradient bg, brand colors
  Price: "$25.99" same spec

ELITE (premium):
  Background: Glass/Card + dark red tint bg rgba(64,18,18,0.06)
  Top border: 2px solid brand/violet
  Glow: Glow/Violet shadow
  "$150" Plus Jakarta Sans 800 52px + " one-time" 14px text/secondary
  "Premium" badge: purple colors

Feature list (all 3 cards):
  Gap: 10px per item
  Included: ✓ (brand/grad-start colored) + 14px text/primary
  Not included: — + 14px text/tertiary, 45% opacity

CTA button: full width, matches plan color theme

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SECTION 3 — FRAME SIZES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Design at these breakpoints. Primary = 1440px.

  Desktop Large:  1920 × 1080
  Desktop:        1440 × 900   ← PRIMARY design surface
  Laptop:         1280 × 800
  Tablet:         768 × 1024
  Mobile Large:   390 × 844    (iPhone 15 Pro)
  Mobile Small:   360 × 780

Design DARK MODE first. Create a light mode page with matching frames.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SECTION 4 — ALL PAGE DESIGNS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

══════════════════════════════════════════════════════════════
PAGE 01: HOME / HERO (1440 × 900) — The Most Important Page
══════════════════════════════════════════════════════════════

This page is the 3D scrollytelling home. Figma shows the
VISUAL OUTPUT STATE of each scroll section as flat frames.
The actual website uses Three.js + Lenis + GSAP for motion.
Design as if you've captured a perfect screenshot of the 3D scene.

── HERO FRAME (Scroll position 0%) ──

Background layers (z-index bottom to top):

  Layer 1 — Page BG: solid bg/page (#011126)

  Layer 2 — Star field: scattered white dots (opacity 40-80%), 3 sizes:
    Small: 1px, ~200 dots scattered across canvas
    Medium: 2px, ~40 dots, slightly brighter
    Large: 3px, ~10 dots with small glow halos

  Layer 3 — Nebula clouds (Figma shapes with blur):
    Cloud 1: 480px × 480px circle, brand/grad-start at 6% opacity, blur 120px, top-left
    Cloud 2: 420px × 420px circle, brand/violet at 7% opacity, blur 100px, right 20%
    Cloud 3: 360px × 360px circle, brand/grad-end at 5% opacity, blur 90px, bottom-center

  Layer 4 — Subtle dot grid:
    40px grid, rgba(242,238,179,0.02) dots at intersections
    Only visible in center area, fade to edges

  Layer 5 — 3D Scene Illustration (represents the Three.js scene at scroll 0%):
    Position: right side of frame, vertically centered, ~520px width
    
    Central sphere:
      Circle 200px diameter
      Fill: radial-gradient(circle, rgba(166,55,45,0.9) 0%, rgba(140,58,39,0.4) 60%, transparent 100%)
      Glow: Glow/Green (0 0 80px rgba(166,55,45,0.5))
      Inner highlight: small white ellipse, 30% opacity, top-left of sphere
    
    Orbital ring 1 (widest):
      Ellipse 360px × 100px
      Stroke: 1.5px, rgba(140,58,39,0.7)
      Rotation: 0deg (nearly flat ellipse = front-facing ring)
      Glow: 0 0 12px rgba(140,58,39,0.4)
    
    Orbital ring 2 (medium):
      Ellipse 300px × 200px
      Stroke: 1.5px, rgba(1,17,38,0.65)
      Rotation: 45deg tilt (create with skew/transform)
    
    Orbital ring 3 (smallest):
      Ellipse 240px × 60px
      Stroke: 1.5px, rgba(166,55,45,0.55)
      Rotation: -30deg
    
    Orbital particles (12 dots):
      4px circle, white, opacity 60-90%
      Placed along ring paths at varying intervals
      2 of them slightly larger (6px) with small glow

  ── Hero Content (left side, vertically centered) ──

  Status badge pill:
    Background: rgba(166,55,45,0.08)
    Border: 1px rgba(166,55,45,0.25)
    Corner radius: 9999px
    Content:
      Red pulse dot: 6px circle, #A6372D, animate:pulse
      "NOW SERVING OPT · STEM OPT · H-1B STUDENTS"
      Font: Label/Overline, color brand/grad-start
    Padding: 8px 16px
    Margin bottom: 28px

  H1 Headline (three lines):
    Line 1: "Land Your"          — Display/Hero, text/primary
    Line 2: "Dream Job"          — Display/Hero, gradient fill:
              linear-gradient(135deg, #8C3A27, #A6372D, #401212)
              Apply as text fill (not background-clip in Figma)
    Line 3: "in the US & Canada" — Display/Hero, text/primary
    Width: max 620px
    Margin bottom: 24px

  Subheading:
    "AI-powered job matching with real-time ATS scoring,
    hiring manager contacts, and visa-aware filtering —
    built exclusively for international students."
    Font: Body/Large 17px, text/secondary, max-width 500px
    Margin bottom: 40px

  CTA Button row (gap 16px):
    Button 1: "Get Started Free →" Primary LG
    Button 2: "How It Works" Secondary LG

  Stats bar (4 mini cards, gap 12px, margin-top 56px):
    Each card: Glass/Card, padding 16px 20px
    Number: Plus Jakarta Sans 800 26px, gradient text fill
    Label: 12px text/secondary
    Content: "300+" Jobs | "10" Categories | "87%" Placement | "2hr" Refresh

  Scroll indicator (absolute bottom-center):
    "SCROLL" — Label/Overline, text/tertiary
    Animated double-chevron below (show as 2 chevrons stacked, opacity suggests animation)

── HOW IT WORKS FRAME (Scroll ~30%) ──

Same background (space + stars + nebula)

3D scene changes (new Three.js state):
  4 hex prism columns rising from bottom-center, different heights
  Colors: brand/grad-start, brand/grad-mid, brand/grad-end, brand/violet
  Each prism: hexagonal shape with emissive glow, wireframe outer shell
  Connecting dashed path between prism tops (drawn line)
  (Represent these as flat colored hexagons with glow halos in Figma)

HTML content overlay:
  Section label: "THE PROCESS" Label/Overline brand/grad-start
  Heading: "From Upload to" + gradient "Offer Letter"
  
  4 Step cards in 2×2 grid (gap 20px, max-width 880px centered):
    Each: Glass/Card, padding 28px 24px
    Step number: top-right, Plus Jakarta Sans 700 13px, text/accent opacity 0.4
    Icon: 44px emoji in 52px gradient icon box (radius 12px)
    Title: Heading/Card 18px 600
    Body: 14px text/secondary, line-height 1.75
    
    Step 1: 📄  "Upload Your Resume" — ATS engine scores your resume vs 300+ positions
    Step 2: 🎯  "Get Matched Jobs" — See ATS score, skill gaps, hiring manager contacts
    Step 3: 📧  "Receive Email Alerts" — Top 10 daily matches, visa-aware, 9AM EST
    Step 4: 🚀  "Apply with Confidence" — Track applications, contact recruiters, land offers

── FEATURES FRAME (Scroll ~55%) ──

Section label: "FEATURES" Label/Overline brand/grad-start
Heading: "Everything You Need to" + gradient "Get Hired"

6-feature glass card grid (2×3 desktop, gap 18px):
  Each: Glass/Card, padding 28px

  1. 🛡  Visa-Aware Matching
     Filter by F1-CPT, F1-OPT, STEM OPT, H-1B. Every listing verified.
     
  2. 🎯  Real-Time ATS Scoring
     Know your match score before applying. Keyword gap analysis included.
     
  3. 👤  Hiring Manager Contacts
     Direct email + LinkedIn of the person who can hire you — per listing.
     
  4. 📊  Application Tracker
     Full history of applications, dates, status — all in one place.
     
  5. 🔔  Smart Email Alerts
     Daily top 10 job matches. OPT/H-1B filtered. Never miss the right one.
     
  6. 🎤  Mock Interview Sessions
     Elite members: weekly 1:1 with top recruiters. Practice every round.

3D scene in background: 6 glass panel shapes in semicircle arc behind the HTML
(Represent as semi-transparent glass rectangles arranged in slight arc)

── PRICING FRAME (Scroll ~72%) ──

Section label + heading as per design system

3 pricing cards (Component 10) in horizontal row, max-width 1100px
(Already fully specified in Component 10 above)

3D scene: 3 crystal prisms rising from below
(Represent as octahedral diamond shapes with translucent fill, colored glow underneath)

── CONTACT FRAME (Scroll ~90%) ──

Section heading: "Get in" + gradient "Touch"

Two-column layout:
  Left: Contact info cards (Glass/Card, 3 info items: Email, Website, Phone)
  Right: Contact form (Glass/Card with form fields)

Contact form fields:
  Full Name, Email, Subject (dropdown), Message (textarea 120px height)
  Submit button: Primary LG full-width

3D scene: Single central orb with particle ring
(Represent as glowing circle surrounded by small dots in circular arrangement)

Footer strip:
  Logo left, copyright center, legal links right
  Dark/Light mode toggle pill right corner

══════════════════════════════════════════════════════════════
PAGE 02: SIGN UP — 4-STEP FLOW (1440 × 900 per step)
══════════════════════════════════════════════════════════════

Background: Same space/star/nebula as home (slightly dimmer, 70% opacity orbs)

Central card: 580px wide, Glass/Card + Shadow/Card, padding 44px, radius 28px

Step progress bar (top of card):
  4 circles connected by lines
  Circle size: 30px diameter
  Active: gradient fill, white Plus Jakarta Sans 700 number inside
  Complete: gradient fill, white checkmark icon
  Inactive: border/glass 1.5px, text/tertiary number
  Connecting line: 32px long, border/default → brand/grad-start (completed steps)

── STEP 1: Account Info ──

H2: "Create Your Account" Plus Jakarta Sans 700 26px
Sub: "Join thousands of international students landing their dream jobs" 13px text/secondary

Form (2-column for names, 1-column for rest):
  First Name + Last Name (2-col grid, gap 16px)
  Phone Number (full width)
  Email Address (full width)
  Password (full width) — with eye-toggle icon right, strength meter below
  Confirm Password (full width)

Password strength meter:
  4 segments, 4px height, gap 4px, radius 2px
  Red (1/4) → Amber (2/4) → Blue (3/4) → Green (4/4)
  Label below: "Weak / Fair / Good / Strong" matching color

CTA: "Continue →" Primary LG full-width, margin-top 24px
Footer: "Already have an account? Sign In" center aligned

── STEP 2: Career Profile ──

H2: "Tell Us About You"

Fields:
  VISA Status: dropdown (F1-CPT / F1-OPT / F1-STEM OPT / H-1B / Other)
  Years of Experience: dropdown (0-1 / 1-3 / 3-5 / 5+)
  Current Status: dropdown (Student / Employed / Unemployed)
  Target Positions (5 input fields, compact, labeled "1" through "5"):
    Each field: 44px height, full width, gap 8px
    At least 1 required indicator

  Resume Upload zone:
    Dashed border 1.5px border/focus, radius 16px, padding 28px
    Centered: cloud-upload icon 32px brand/grad-start
    "Drop your resume here or click to upload" 14px text/primary
    "PDF or DOCX · Max 5MB" 12px text/tertiary
    Filled state: shows filename + file size + green checkmark

── STEP 3: Email OTP Verification ──

Email icon: 56px circle gradient background, white envelope icon 28px
H2: "Verify Your Email" centered
"OTP sent to" text + email highlighted brand/grad-start + "Check your inbox"

OTP Input Component (6 boxes) centered, width matches card

Below boxes: countdown timer component
"Didn't receive it? Resend OTP" — appears after 60s (show as active in one variant)

Security note (bottom of card):
  Lock icon 14px + "OTP is one-time use. Expires in 3 minutes. Never share it."
  12px text/tertiary

── STEP 4: Plan + Payment ──

H2: "Choose Your Plan"

3 mini plan cards (horizontal, compact):
  Same as Component 10 but height-compressed (no feature list, just price + plan name)
  Selection state: outer border brand color 2px + checkmark overlay top-right corner

Payment form (appears below when plan selected):
  Stripe Element UI mockup:
    Card number (with Stripe card icons right)
    Expiry + CVV (2-col)
    Cardholder name
  
  Order summary box:
    Glass/Card smaller, border brand color
    Plan name + price
    "Billed immediately" text
  
  "Complete Payment & Access Dashboard 🔒" Primary LG full-width
  
  Security badges row (centered, horizontal):
    PCI-DSS icon, SSL Secure icon, Stripe badge
    All 12px text/tertiary

══════════════════════════════════════════════════════════════
PAGE 03: SIGN IN (1440 × 900)
══════════════════════════════════════════════════════════════

Layout: Two-panel split (50% / 50%)

LEFT PANEL (50%):
  Background: Space visual with 3D orbital sphere (same as hero, 50% viewport)
  Floating glass card (positioned at center-left):
    "87% of PlaceUp users land interviews within 6 weeks"
    Plus Jakarta Sans 600 17px
    Author: "Sarah L. · Software Engineer · Google (H-1B)"
    Avatar: 36px circle

RIGHT PANEL (50%):
  Background: bg/surface (Dark: #401212, Light: #FFFFFF)
  Vertical center alignment

  Auth card (420px wide, centered):
    Logo mark + "PlaceUp Career" at top (centered)
    Margin-bottom 32px

    H2: "Welcome Back" Plus Jakarta Sans 700 26px
    Sub: "Sign in to access your job matches" 13px text/secondary

    Email field (full width)
    Password field (full width) + "Forgot password?" link right-aligned below
    Margin-top 8px

    "Sign In →" Primary LG full-width, margin-top 20px

    Divider: "or continue with" — line · text · line
    Social buttons: Google + LinkedIn (outline style, full width, gap 12px)

    "Don't have an account? Get Started" centered 13px

  OTP STEP (second screen — separate frame):
    Same card, email + password replaced with OTP Component 09
    "Verify your identity to continue" heading
    Countdown timer
    Back button top-left of card

══════════════════════════════════════════════════════════════
PAGE 04: DASHBOARD — OVERVIEW (1440 × 900)
══════════════════════════════════════════════════════════════

Layout: sidebar 256px fixed + main area flex-1

SIDEBAR:
  Background: bg/surface with right border 1px border/default
  Width: 256px

  Top (logo area, 64px height, padding 0 24px):
    Same logo as navbar

  Nav section (padding 12px):
    7 items using Component 08:
    Overview (active state), Resumes, Jobs, Visa Tracker, Alerts, Analytics, Settings
    Icons: Home, FileText, Briefcase, Globe, Bell, BarChart3, Settings

  Saved jobs indicator (below nav):
    Small section: "Saved Jobs" label + "5/5" pill (green if <5, red if =5)
    5 bookmark icons showing filled/empty slots

  Bottom area:
    User card: avatar 36px + "Alex Kumar" 14px 500 + "Pro Plan" badge
    Logout button: text/tertiary, hover text/error

TOPBAR (main area):
  Height: 64px, sticky
  Background: bg/glass + backdrop-blur-xl + border-bottom border/default

  Left: Hamburger icon (tablet/mobile) + Page title "Overview" 16px 600
  Right:
    Search bar (280px): Ghost/Card style, "Search jobs..." placeholder, search icon left
    Bell icon button: notification dot if unread
    Dark/Light toggle: pill with sun/moon icon
    User avatar: 36px circle + dropdown on click

OVERVIEW PAGE CONTENT (main area, padding 24px):

  Welcome row:
    "Good morning, Alex! 👋" Plus Jakarta Sans 700 22px
    "3 new jobs match your profile today." 14px text/secondary

  Stats row (4 cards, gap 16px, margin-bottom 24px):

    Card 1 — ATS Score:
      Glass/Card, padding 20px
      ATS Ring (large 120px) centered
      "Your Resume Score" 12px text/secondary below
      Background: slight red tint

    Card 2 — Applications:
      Stat: "24" Plus Jakarta Sans 800 36px gradient text
      Label: "Applications this month"
      Trend: "+3 this week" green arrow

    Card 3 — Interviews:
      Stat: "8"
      Label: "Interviews scheduled"
      Next: "Next: Tomorrow 2PM"

    Card 4 — Saved Jobs:
      Stat: "5/5"
      Label: "Saved job slots"
      Progress bar: 100% if full (red indicator)

  Featured Jobs section:
    Label: "⭐ Featured Positions" 13px 600 text/accent
    Right: "View All →" text link brand/grad-start
    3 Job Cards (Component 05) in a row, featured variant

  Recent Activity panel (full width, bottom):
    Glass/Card
    Header: "Recent Activity" 15px 600
    List: 4 items showing recent searches/applications with relative time

══════════════════════════════════════════════════════════════
PAGE 05: DASHBOARD — JOBS PAGE (1440 × 900)
══════════════════════════════════════════════════════════════

(Same sidebar + topbar as Overview)

Filter bar (sticky, full width below topbar):
  Background: bg/surface + border-bottom border/default
  Height: 60px
  Padding: 0 24px
  
  Left cluster (gap 12px):
    Search input (280px, Component 02 style)
    "Filters" ghost button SM with count badge
    
  Right cluster (gap 8px):
    Status pills: "All" "New" "Applied" "Interview" "Saved"
    Active pill: gradient background, white text
    Inactive pill: border/glass, text/secondary

  Expanded filters panel (below filter bar, Glass/Card):
    3-column grid:
      Job Title dropdown
      Time Posted dropdown: Today / Yesterday / 3 Days / 7 Days / 1 Month
      Location dropdown
    Active filters pills row: tag chips with × to remove
    "Clear All Filters" text link, text/error

Jobs content:
  Left panel (70%): Job cards 2-column grid, gap 16px
  Right panel (30%, sticky): Selected job preview or "Select a job to preview" empty state

  Job cards use Component 05

  Pagination (centered below cards):
    "Showing 1-20 of 247 results" 13px text/secondary
    Prev | 1 | 2 | 3 | ... | 13 | Next
    Active page: gradient background 32px circle

══════════════════════════════════════════════════════════════
PAGE 06: DASHBOARD — JOB DETAIL (1440 × 900)
══════════════════════════════════════════════════════════════

Main content (65%) + Sidebar (35%)

MAIN CONTENT:
  Back button: "← All Jobs" ghost, 14px text/secondary
  
  Header card (Glass/Card full width):
    Left: Company logo 60px + Stack: Title Plus Jakarta Sans 700 22px + Company · Location · Est. Salary
    Middle: Visa badges row + Posted date
    Right: ATS Ring 80px + "94% Match" 11px text/secondary below
    Actions row: "Apply on Company Website ↗" Primary MD + "Save" Secondary + "Share" icon

  ATS Breakdown card (Glass/Card):
    "ATS Score for This Position"
    Large ATS ring 120px, centered
    Two columns below ring:
      Left: "Strong Keywords ✓" — green badges grid
      Right: "Missing Keywords ✗" — red badges grid with impact levels

  Job Description card (Glass/Card):
    Tabs: "Responsibilities" | "Requirements" | "Nice to Have"
    Content: bulleted list with text/secondary items

  "Did You Apply?" modal overlay (show as separate frame/variant):
    Centered modal, 400px wide, dark overlay behind
    "Did you apply for this position?" 18px 600
    Company + Title displayed
    "Yes, I Applied! 🎉" Primary LG + "No" Secondary LG (horizontal)
    If No: textarea appears for "Why not?" (optional)

SIDEBAR (right):
  Hiring Manager card (Glass/Card):
    Pro/Elite state:
      Avatar 48px circle + Name 15px 600 + Title 13px text/secondary
      Email row: email address + copy icon
      LinkedIn row: linked text, brand color
    Basic state:
      Blurred avatar + blurred name/email
      "Upgrade to Pro" CTA overlay

  Visa Info card (Glass/Card):
    Badges: visa types sponsored
    Approval rate: circular progress 60px
    "42% approval rate" + "Last year: 1,283 petitions"

  Benefits card (Glass/Card):
    List: remote, health insurance, 401k, stock options, etc.
    Each: icon + text

══════════════════════════════════════════════════════════════
PAGE 07: MOBILE — HOME HERO (390 × 844)
══════════════════════════════════════════════════════════════

Navbar:
  Height: 56px
  Logo left, Hamburger right only
  Mobile menu: full-screen overlay, white 5% opacity, all links stacked 48px height

Hero content (vertical, centered padding 24px 20px):
  Status badge (same design, full-width max-content)
  H1: 44px, same gradient treatment, wrapped
  Subheading: 15px
  3D sphere illustration: 240px centered, above buttons
  CTA buttons: stacked full-width, gap 12px
  Stats: 2×2 grid, gap 12px

══════════════════════════════════════════════════════════════
PAGE 08: MOBILE — DASHBOARD JOBS (390 × 844)
══════════════════════════════════════════════════════════════

Topbar: Hamburger + "Jobs" + Filter icon (3 horizontal lines with dot)
Filter: Horizontal scroll pill row below topbar
Search: Full width, 44px
Job cards: Single column, full width, gap 12px

Bottom navigation bar (mobile dashboard):
  5 items: Overview / Jobs / Resumes / Alerts / Settings
  Active: gradient icon color
  Height: 64px + safe area

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SECTION 5 — FIGMA PROTOTYPE CONNECTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Connect all frames for a clickable demo:

01 Navbar "Get Started" → Sign Up Step 1         Slide Right 300ms
02 Navbar "Sign In" → Sign In page               Slide Right 300ms
03 Sign Up Step 1 "Continue" → Step 2            Push Right 280ms
04 Sign Up Step 2 "Continue" → Step 3 OTP        Push Right 280ms
05 Sign Up Step 3 "Verify" → Step 4 Plan         Push Right 280ms
06 Sign Up Step 4 "Complete Payment" → Dashboard  Dissolve 400ms
07 Sign In "Sign In" → OTP step                  Push Right 280ms
08 OTP step "Verify" → Dashboard                 Dissolve 400ms
09 Dashboard sidebar "Jobs" → Jobs page          Instant
10 Dashboard sidebar "Overview" → Overview       Instant
11 Jobs page job card "Details" → Job Detail     Slide Right 280ms
12 Job Detail "← All Jobs" → Jobs page          Slide Left 280ms
13 Job Detail "Apply ↗" → "Did You Apply?" modal Scale 200ms
14 Modal "Yes" → Applied state (same page)       Instant
15 Home scroll: use Figma Scroll Position for section visibility

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SECTION 6 — LIGHT MODE DESIGN RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Light mode is NOT a color inversion. It is a completely different visual feel.
Design it as a premium SaaS day mode — clean, airy, precise.

  Background: Pure white #FFFFFF
  Cards: White + 6px shadow (not blur — shadows work better on white)
  Text: Deep navy #011126 for primary, #401212 for secondary
  Gradient accents: SAME gradient (red→burnt red→dark red) — it pops more on white
  Border: #8C3A27 (subtle red)
  Stars/nebula on home: hidden (replaced by subtle light-red gradient mesh)
  ATS rings: same colors (they work on both backgrounds)
  Glass effect: White 88% opacity + blur (still glass but light-toned)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SECTION 7 — DELIVERABLES CHECKLIST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Figma file structure (create these pages in order):

  ✦ PAGE: "🎨 Design Tokens"        → All Variables + Text Styles + Effect Styles
  ✦ PAGE: "🧩 Components"           → All 10 components with all variants (dark + light)
  ✦ PAGE: "🌑 Dark Mode"            → All 8 frames at 1440px
  ✦ PAGE: "☀️ Light Mode"           → Matching 8 frames at 1440px
  ✦ PAGE: "📱 Mobile Dark"          → Hero + Dashboard + SignUp (390px)
  ✦ PAGE: "📱 Mobile Light"         → Same frames in light mode
  ✦ PAGE: "🔗 Prototype Flow"       → All frames connected with transitions
  ✦ PAGE: "📐 Design System Guide"  → Written spec doc inside Figma

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SECTION 8 — ACCEPTANCE CRITERIA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✓ ZERO raw hex values in any frame — every color = Variable token
✓ Both modes look independently premium (not just a recolor)
✓ Every interactive component has Default + Hover + Focus + Disabled variants
✓ Hero section communicates the 3D scroll experience visually in 2D
✓ Job card component has identical internal padding across ALL instances
✓ ATS rings are color-coded (green/amber/red) consistently everywhere
✓ Typography hierarchy immediately clear on first glance
✓ Glass cards have 3 properties: fill opacity + border + blur (all 3 always present)
✓ 8px grid — verify alignment with Figma grid toggle
✓ All text passes WCAG AA contrast (use "Stark" or "Contrast" Figma plugin)
✓ Mobile frames redesigned for touch — not shrunken desktop
✓ Prototype is fully clickable end-to-end (home → signup → dashboard → jobs → detail)

╔══════════════════════════════════════════════════════════════════════════════════╗
║  END OF FIGMA PROMPT · PlaceUp Career v1.0 · March 2026                        ║
╚══════════════════════════════════════════════════════════════════════════════════╝
```