# Design System: LociGraph

## 1. Visual Theme & Atmosphere
LociGraph is an archivist's cockpit — warm, amber-lit, and dense with meaning. The atmosphere sits between a well-worn study stacked with evidence and a spacecraft's navigation room tracking known space. The dominant feeling is **earned focus**: every element earns its place in view.

The design encodes **two primary modes sharing one core color system**:

- **Hearth Mode** (Cozy/Reading): Density 4/10, generous vertical rhythm, wider cards, larger type. Evokes a reading lamp at night. Used for contemplative research and document review.
- **Meridian Mode** (Operational/Command): Density 8/10, tight row heights, compact metadata, multi-column layouts. Command center energy. Used for graph navigation, data ingestion, and system monitoring.

---

## 2. Color Palette & Roles

### Base System
- **Void** (`#0F0D0B`): Deepest background. Used only for overlays and the base of high-contrast Meridian views.
- **Archive** (`#141210`): Primary canvas. The floor everything rests on.
- **Chamber** (`#1E1A17`): Card and panel surfaces. Slightly elevated.
- **Dust** (`#F5EDE2`): Primary text. Warm cream, aged paper.
- **Ash** (`#A89070`): Secondary text, metadata, and labels.
- **Ember** (`#D4882F`): The single accent. CTAs, active states, and focus rings.

### Hearth Alternate (Teal/Light)
- **Hearth Surface** (`#f4fbfa`): Soft cream-teal for light mode reading.
- **Hearth Accent** (`#2d6a6a`): Muted teal for interactive elements in Hearth mode.

---

## 3. Typography
- **Headings:** `Outfit`. Weight 500-600. Used for page titles and card headers.
- **UI & Navigation:** `Geist`. Clean, modern sans-serif for labels and buttons.
- **Data & Telemetry:** `Geist Mono`. Essential for UUIDs, coordinates, timestamps, and confidence scores.

---

## 4. Component Stylings

### Navigation (The Archivist's Companion)
- **The Orb/Core:** A sentient companion that serves as the navigational anchor.
  - **Hearth Orb:** A soft, pulsing teal companion in the bottom corner. Expands into a floating radial "Archivist's Dock."
  - **Meridian Core:** An operational center-bottom core with high-frequency scanning pulses. Toggles the "Instrument Panel" top-nav.

### Cards & Surfaces
- **Radius:** 10px (Hearth) / 6px (Meridian).
- **Border:** `1px solid rgba(245,237,226,0.07)` (Whisper).
- **Elevation:** Flat. No heavy shadows; use subtle borders for separation.

### Status Badges (Geist Mono)
- **VERIFIED:** Signal Green (`#5A8C5A`) on muted background.
- **INGESTING:** Pulsing Ember (`#D4882F`) dot.
- **QUARANTINED:** Signal Amber (`#8C6A2A`).

---

## 5. Layout Principles
- **Asymmetric Balance:** Avoid 3-equal-column layouts. Use grid-anchored offsets.
- **Viewport Priority:** Navigation elements should be toggleable or floating to maximize the viewport for the Knowledge Graph and document content.
- **Density Toggling:** Spacing tokens must scale between Hearth (2rem gap) and Meridian (0.5rem gap) seamlessly.

---

## 6. Motion & Interaction
- **Spring Physics:** Weighty and settled.
- **Orb Animation:** Subtle "breathing" pulse (1.4s infinite).
- **Layout Transitions:** Layout reflows with a 200ms cross-fade between modes.

---

## 7. Key Screens (Stitch Prompts)

Use these as individual Stitch screen generation prompts. Apply the DESIGN.md as the design system for all.

---

### Screen 1 — Login
> A single-user login screen for LociGraph, a personal knowledge engine. Deep warm dark background (`#141210`). Centered card (`#1E1A17`) with subtle amber border glow on focus. Outfit heading "LociGraph" in warm cream (`#F5EDE2`) at top, small descriptive subtext in muted amber (`#A89070`). Password field with amber focus ring. Single amber primary button "Enter Archive". No logo placeholder. No decorative illustration. Sparse, intentional, slightly ceremonial — like unlocking a private study.

---

### Screen 2 — Dashboard (Hearth Mode)
> LociGraph dashboard in Hearth Mode. Soft cream-teal canvas (`#f4fbfa`). Left sidebar with teal active indicator on "Overview". Main content: large Outfit heading "Archive Overview" in dark warm text. Three stat cards showing: total sources, total observations, pending jobs — each with a Geist Mono number in teal accent (`#2d6a6a`) and an Ash label. Below: recent activity list with staggered row entries showing source name, status badge, and timestamp in Geist Mono. Generous spacing, cards with 10px radius, no heavy shadows. Cozy, soft, like a lit reading room. Hearth Orb in bottom corner — soft pulsing teal circle.

---

### Screen 3 — Dashboard (Meridian Mode)
> LociGraph dashboard in Meridian Mode. Dark warm canvas (`#141210`). Center-bottom Meridian Core with high-frequency scanning pulse ring. Instrument Panel top-nav with compact controls. Dense data tables with Geist Mono timestamps, small Ash column headers in uppercase. Status badges inline with source rows. Job queue panel showing active background tasks with 2px amber progress bars. Dense, focused, command-center energy. Small typography (12–14px), row striping with barely-visible warm tint. Meridian Core at bottom center, operational pulse animation.

---

### Screen 4 — Import / Ingest
> LociGraph source import screen. Dark warm background. Page title "Import Source" in Outfit 28px cream. Large dashed-border drop zone with ember-amber dashed border at 30% opacity, rounded 12px corners. Inside the drop zone: a minimal line-art icon (document stack) in Ash, label "Drop files here" in Ash 14px Outfit, subtext "JSON · PDF · HTML · Markdown · ChatGPT export · Meta export" in Ash 12px Geist. Below: a grid of format cards in Chamber, each showing format type in Outfit cream and file extension in Geist Mono amber. One primary amber button "Browse Files". Progress feedback area below for active upload.

---

### Screen 5 — Sources List
> LociGraph sources browser. Meridian density. Page title "Sources" with a small amber badge showing total count in Geist Mono. Filter bar: status filter pills (All / Pending / Ingesting / Verified / Quarantined / Purged), right-aligned search input. Data table below: columns for filename (Outfit cream), type badge (small pill), status badge (color-coded), file size (Geist Mono Ash), import timestamp (Geist Mono Ash), observations count (Geist Mono amber), action icon. Row hover in Ledge. PURGED rows have muted Ash filename with subtle strikethrough. Table uses border-top dividers, no outer card border.

---

### Screen 6 — Observation Browser
> LociGraph observation browser in Hearth Mode. Soft cream-teal canvas. Filter bar at top with source filter, date range, speaker filter, status filter. Below: stacked observation cards in white/light surface with subtle border. Each card shows: observation content text in Outfit dark 15px, line-height 1.7, max 65ch; below that a metadata row in Geist Mono muted 11px — timestamp · source name · speaker (if present) · confidence score. Teal left-border accent on active/selected observation. Hearth Orb in bottom corner.

---

## 8. Anti-Patterns (Banned)

- No emojis anywhere in the UI
- No `Inter` font — use `Geist` and `Outfit` exclusively
- No pure black (`#000000`) — Void (`#0F0D0B`) is the darkest value
- No neon outer glow shadows
- No purple, blue-neon, or cyberpunk palette touches
- No oversaturated accents — Ember stays below 65% saturation
- No gradient text on headings
- No 3-equal-column feature card layouts
- No centered Hero layouts for any primary content view
- No custom mouse cursors
- No overlapping elements — every element in its own spatial zone
- No AI copywriting: "Seamless", "Unleash", "Next-Gen", "Elevate", "Empower"
- No circular loading spinners — skeletal loaders only
- No scroll arrows, bounce chevrons, or "Scroll to explore" filler
