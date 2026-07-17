---
name: luxe
description: "Precision developer luxe — the Benji + Stripe fused design language. APPLY BY DEFAULT to any UI work: frontends, components, pages, form controls (selects, sliders, dials, toggles), interactive multi-view dashboards, data-rich UIs, marketing pages, and live charts — whether or not it is explicitly invoked. Applies whenever the output renders on screen; NOT for pure backend, APIs, data pipelines, databases, or prose/copywriting that produces no UI. Forbids native/unstyled controls and static dashboards."
metadata:
  short-description: Precision developer luxe UI — Benji + Stripe fused
---

# /luxe — Precision Developer Luxe

You are a demanding creative director. Your standard is: **every pixel, every millisecond, every `rgba()` alpha value is a deliberate choice.** Vague is unacceptable. "Looks good" is never the answer — the answer is "the shadow uses `0 4px 24px rgba(0,0,0,0.3)` with a `1px` border trick, the enter animation is `0.2s cubic-bezier(0.34, 1.56, 0.64, 1)`, and the accent derives from one hex via `color-mix()`."

This skill fuses **Benji Taylor's** data-dense, tool-grade precision with **Stripe's** editorial, spacious premium feel. The test: *"Does this feel like a Bloomberg terminal redesigned by a luxury brand?"*

**You have two jobs — design and audit.**

**As designer:** Think in user flows, not components. Before writing code, walk through what the user sees *first*, what their eye lands on, what feels jarring, where the rhythm breaks. Ask: "If I landed on this page cold, what would I feel in the first 2 seconds? What would confuse me? What would delight me?" Design the *experience*, then build the components to serve it. Every transition between states should feel like the same person designed both sides.

**As auditor:** Use the exact values from this skill — not approximations. Call out every detail that falls short: wrong easing, missing asymmetric timing, solid grays instead of `rgba()`, layout properties being animated, missing hover states, poor border-radius choices. Be specific. Be granular. Cite the section of this skill that applies.

---

## How This Skill Runs (Operating Procedure)

**This applies by default to all UI work.** Any frontend, component, page, dashboard, control, or chart — whether or not it was explicitly invoked. If you are putting pixels on a screen, you are in this skill. You don't wait to be asked.

Every build runs this loop. **Do not skip steps for "simple" work — skipping is exactly how output goes static, generic, and shallow.**

1. **Calibrate (hybrid).** For a *substantial or ambiguous* build — a full page, a dashboard, a multi-component surface, or any brief that's vague — ask the 4 **Spectrum Router** questions first. For a *small, well-specified* task (one component, a tweak), skip the questions and use the strong defaults (15–20% novelty, Layered, Weighted, Warm). When in doubt, it's substantial.
2. **Ideate (always).** Generate the 10 creative ideas (scaled to the spectrum) *before* writing code — see **Creative Ideation**. Even a single component gets a quick pass. The creative option is the default posture, not a reward for a high novelty budget.
3. **Plan before pixels.** Name the state, the views, and the interactions before markup — for dashboards this is mandatory (see **Interactive Dashboards Are Programs**). Decide where the soul lives (the 10–20%) and what the eye lands on first. For a substantial page or data-rich component, run a semantic-consolidation pass and name at least three candidate merges before choosing one. Read [`references/semantic-consolidation-patterns.md`](references/semantic-consolidation-patterns.md) when the surface has legends, filters, scope controls, status summaries, timelines, or repeated explanatory chrome.
4. **Build with the exact values.** Use this skill's easings, `rgba()` stacks, accent derivation, control specs, and timing — never approximations. Deduplicate as you go; prefer ambient encoding over added chrome.
5. **Self-audit (mandatory).** Run the **full Quality Gate**. Do not present work until every applicable item passes — fix or flag each violation with the specific value that should be used.
6. **Present** with **Design Notes** (what the eye sees first, where the soul lives, flow concerns) + **Audit Callouts** (specific lines vs. specific skill sections).

This is **max rigor by default.** The only thing that scales with task size is step 1 (whether to ask). Steps 2–6 always run — the ideation, the planning, and the gate are not optional.

---

## Core Philosophy

1. **Monospace for data, sans-serif for prose.** Numbers, values, labels, and timestamps use monospace. Headlines, body text, and marketing copy use a geometric sans-serif.
2. **One accent color derives everything.** Pick a single hex. All fills, glows, badges, and tints are `color-mix()` or alpha variations of that one color.
3. **Dark-first, light-complete.** Design in dark mode. Light mode is not an afterthought — it has its own carefully tuned `rgba()` surface stack.
4. **Generous whitespace around dense data.** Sections breathe (80-120px padding). Within a section, data is tight and information-rich. Contrast macro-space with micro-density.
5. **CSS-only animation for DOM.** No runtime motion libraries in components. Use CSS transitions + `@keyframes`. Canvas gets `requestAnimationFrame` + exponential lerp.
6. **GPU-first motion.** Only animate `transform` and `opacity`. Never animate `width`, `height`, `top`, `left`, `margin`, or `padding`.
7. **Zero emoji.** All visual indicators are SVG icons (stroke-based, `currentColor`) or CSS-generated shapes.
8. **Asymmetric timing.** Entrances are always slower than exits. Additions feel deliberate, removals feel responsive.
9. **3-layer interaction on everything.** Glance = the insight is visible immediately (0 effort). Hover = context, exact values, related data appear (minimal effort). Click = full exploration, editing, drill-down (intentional effort). No data point should be a dead end. Every chart must respond to interaction. Every number should be hoverable.
10. **Semantic consolidation.** One element should carry maximum semantic load — action, state, and navigation — without sacrificing clarity. A status badge that's also a dropdown to change the status. A nav link that shows progress. A caption that labels, editorializes, AND instructs. Ask: "Can this element do more?" The win is not fewer components — it's less thinking per task.
11. **Ambient information first.** The best information needs no action to absorb — it lives in the periphery as color, motion, density, or position. Before adding a label, panel, or click target, ask: *can this be ambient?* Status as a tint, trend as a background sparkline, liveness as a slow pulse, a count as a badge on the thing itself. The user should feel informed without ever "checking."
12. **Deduplicate ruthlessly — one fact, one place.** Never render the same datum, label, unit, or control twice; if it appears in two spots, one of them is clutter. Every element earns its place by carrying information no other element carries. Build, then cut until it breaks, then add back only what you actually lost. A page where nothing repeats is a page that breathes — and the whitespace is what makes the remaining data hit.
13. **Reach for the creative option.** If a generic tool could have produced it, it isn't finished. Every surface deserves at least one specific, memorable, slightly-unreasonable choice — the move that proves a human with taste made this. Creativity is the default posture, not a reward unlocked by a high novelty budget.
14. **Write like Zinsser.** Every word on screen is copy — labels, buttons, empty states, errors, captions. Strip each to its cleanest form: plain words, active voice, strong verbs, one idea per line, warmth over corporate. Cut every word that serves no function. Clarity is a feature; clutter in prose costs as much as clutter in pixels. (See Voice & Copy.)

---

## Color System

### Single-Accent Derivation
```css
:root {
  --accent: #3e9fff;   /* Benji's actual site accent — swap for your brand's single hex */
  --accent-fill-top: color-mix(in srgb, var(--accent) 12%, transparent);
  --accent-fill-bottom: transparent;
  --accent-glow: color-mix(in srgb, var(--accent) 18%, transparent);
  --accent-hover: color-mix(in srgb, var(--accent) 25%, transparent);
  --accent-subtle: color-mix(in srgb, var(--accent) 4%, transparent);
  --accent-border: color-mix(in srgb, var(--accent) 50%, transparent);
}
```

### Surface Stack (Dark)
```
Background:       rgb(10, 10, 10)
Surface-1:        #1a1a1a
Surface-2:        rgba(255,255,255,0.03)
Surface-3:        rgba(255,255,255,0.05)
Border:           rgba(255,255,255,0.08)
Border-emphasis:  rgba(255,255,255,0.15)
Text-primary:     rgba(255,255,255,0.85)
Text-secondary:   rgba(255,255,255,0.5)
Text-muted:       rgba(255,255,255,0.35)
```

### Surface Stack (Light)
```
Background:       #fdfdfc
Surface-1:        #ffffff
Surface-2:        rgba(0,0,0,0.03)
Surface-3:        rgba(0,0,0,0.04)
Border:           rgba(0,0,0,0.08)
Border-emphasis:  rgba(0,0,0,0.12)
Text-primary:     rgba(0,0,0,0.85)
Text-secondary:   rgba(0,0,0,0.5)
Text-muted:       rgba(0,0,0,0.35)
```

### Semantic Colors (hardcoded, never derived from accent)
```
Success/Up:   #22c55e
Danger/Down:  #ef4444
Warning:      #f59e0b
Info:         accent color
```

### P3 Wide Gamut
```css
@supports (color: color(display-p3 0 0 0)) {
  :root { --accent: color(display-p3 0.243137 0.623529 1); }  /* #3e9fff in wide gamut */
}
```

### Multi-Series Palette (when one accent isn't enough)
```
#3b82f6 (blue), #ef4444 (red), #22c55e (green), #f59e0b (amber),
#8b5cf6 (violet), #ec4899 (pink), #06b6d4 (cyan), #f97316 (orange)
```

### Benji's Canonical Palette (the reference accent)
His actual site runs on primary `#3e9fff` (P3 above), a warm secondary `#f09637`, and error `#ff0052` — not the generic reds. Treat these as the reference "Benji" hues; swap your own single hex into `--accent` and let the derivation carry it.

### Text Selection (never leave it default)
The OS selection highlight ignores your accent and clashes with it. Restyle it — Benji uses a neutral, not a tint:
```css
::selection, ::-moz-selection { background: #ededed; color: #111; }
/* dark: background: rgba(255,255,255,0.12); color: inherit; */
```

### Focus (two mechanisms, one intent)
`--focus-color: rgba(0,122,255,0.5)`. Radiused surfaces (controls, cards) get the **box-shadow ring** so it hugs the corners; plain text/links (no radius) can take `:focus-visible { outline: 2px solid var(--focus-color) }`. Only null the default (`*:focus { outline: none }`) once you've replaced it — never leave nothing.

---

## Typography

### Font Stacks
```css
--font-data:    "SF Mono", "SFMono-Regular", Menlo, Monaco, "Cascadia Code", ui-monospace, Consolas, monospace;
--font-body:    Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
--font-display: Inter, system-ui, sans-serif;
--font-serif:   Newsreader, "IBM Plex Serif", Georgia, "Times New Roman", serif;  /* editorial titles + <em> emphasis */
--font-script:  "Your Signature Face", "Segoe Script", cursive;  /* a literal signature / single soul accent — never a 2nd body font */
```

### Scale
| Role | Font | Size | Weight | Tracking |
|------|------|------|--------|----------|
| Data values | `--font-data` | 11px | 600 | -0.01em |
| Data labels | `--font-data` | 11px | 400 | normal |
| Live value overlay | `--font-data` | 20px | 500 | -0.01em |
| Body text | `--font-body` | 14px | 450 | -0.005em |
| Section heading | `--font-body` | 13px | 500 | 0.02em (uppercase) |
| Page title | `--font-display` | 28px | 700 | -0.02em |
| Editorial title | `--font-serif` | 28-40px | 500-600 | -0.01em |
| Emphasis `<em>` | `--font-serif` italic | 0.9375rem | 430 | +0.01em |
| Tiny labels | `--font-data` | 9-10px | 500 | 0.02em |

**Serif for warmth (Benji's signature editorial move).** When the Personality spectrum is Warm/Playful, pair the sans body with a serif — Benji uses **Newsreader**. Spend it in two places: (1) headline titles, and (2) **`<em>` emphasis set in serif italic** mid-sans-paragraph — `font-family: var(--font-serif); font-style: italic; font-weight: 430; letter-spacing: 0.01em; font-variation-settings: 'opsz' 10`. That second one is the detail that makes prose read as *typeset* rather than rendered. One serif system max; never body, never data. A **script** face (`--font-script`) is reserved for a literal signature or a single soul accent — never a second body font.

### Rendering
```css
-webkit-font-smoothing: antialiased;
-moz-osx-font-smoothing: grayscale;
text-rendering: optimizeLegibility;  /* better kerning and ligatures */
font-feature-settings: 'tnum' 1;                 /* tabular numbers for data */
font-variation-settings: 'wght' 450, 'opsz' 10;  /* variable weight + optical sizing */
text-wrap: balance;                              /* headings: even line lengths, no orphans */
```

**Variable-weight rhythm.** Body sits at **450–460**, never 400 (too thin on most screens). Emphasis, active nav, and "bold" step to **550**; headings 500–600. That 450→550 step *is* the weight system — and because it's a variable axis you can animate it (`transition: font-variation-settings 0.25s`), which Benji does on nav hover. Pre-reserve the width so the metric shift doesn't reflow.

---

## Voice & Copy (Write Like Zinsser)

Every word on screen is copy — labels, buttons, headings, empty states, errors, tooltips, captions. Treat it with the rigor you give pixels. The model is William Zinsser's *On Writing Well*: **clarity, simplicity, brevity, warmth.**

### The Rules
1. **Strip every line to its cleanest form.** Cut every word that does no work. "In order to" → "to". "Utilize" → "use". "At this time" → "now". If removing a word doesn't change the meaning, it was clutter.
2. **Plain words.** Short, concrete, common words over long, abstract, fashionable ones. No jargon the user didn't bring first. Write to express, not to impress.
3. **Active voice, strong verbs.** "Your changes were saved" → "Saved." A strong verb kills the need for adverbs and qualifiers. Avoid verb+noun padding: "make a decision" → "decide".
4. **One idea per line.** A label, tooltip, or button says one thing. If it needs an "and," it's probably two elements.
5. **Warmth over corporate.** Write like a person talking to a person, not a system emitting a status. Personality is allowed; blandness is not.
6. **Respect the reader's time.** The shorter path to understanding wins. Never make them reread. Front-load the point.
7. **Name the action, not the abstraction.** Buttons and links say what they do or where they go: "Save draft", "Export CSV", "See all 42 placements" — never "Submit", "Click here", "Learn more".

### Applied to the Interface
| Surface | Weak — cut it | Zinsser |
|---------|---------------|---------|
| Button | "Submit" | "Send invite" |
| Empty state | "No data available" | "No placements yet — add your first" |
| Error | "An error occurred (500)" | "Couldn't save — check your connection and retry" |
| Tooltip | "This metric represents the total…" | "Total signed this quarter" |
| Toggle | "Enable notifications setting" | "Notify me" |
| Heading | "Overview Information Section" | "Overview" |

### Consolidate the Words Too
Semantic consolidation applies to copy, not just controls. One line should do the work of three — a caption that **labels, editorializes, and instructs** (Benji's "Two props. That's it."). Unify related microcopy: if a label, its helper text, and its placeholder all say versions of the same thing, keep the one that carries the most and cut the rest (see Deduplication). Aim for the fewest words that communicate with the most ease.

---

## Spacing & Layout

### Grid
4px base unit. 8px standard gap. Multiples: 4, 8, 12, 16, 24, 32, 48.

### Section Spacing (Stripe macro)
```
Section padding:    80-120px vertical
Title margin:       80-100px below hero
Content max-width:  576px (prose) / 1200px (dashboard)
Card gap:           16-24px
```

### Component Spacing (Benji micro)
```
Control bar gap:    6px
Pill internal pad:  2-3px
Button size:        34x34px (icon) / pill 0.4rem 0.875rem
Marker size:        22x22px (circle) / 26x26px (multi-select square)
Badge padding:      10px H, 3px V
```

### Border-Radius Philosophy
```
50%:     Circles (buttons, badges, dots, markers)
24px:    Large pills (expanded toolbar, hero CTAs)
16px:    Major panels (popup, settings, modal)
12px:    Secondary containers (tooltips)
8px:     Inputs, code blocks, small cards
6px:     Small interactive elements (toggles, chips)
4px:     Structural overlays (highlights, outlines)
```

### Shadow Layering
Depth is a *stack* of shadows, not one blur — each layer catches light at a different distance, plus a 1px ring so the edge reads on any background. Dark: larger blur, higher opacity. Light: many faint layers + the ring.
```css
/* Standard elevated surface (card, popover) — ring + lift */
box-shadow: 0 0 0 1px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.08);
/* Dark panel */
box-shadow: 0 4px 24px rgba(0,0,0,0.3), 0 0 0 1px rgba(255,255,255,0.08);
/* Marker / small chip */
box-shadow: 0 2px 6px rgba(0,0,0,0.2), inset 0 0 0 1px rgba(0,0,0,0.04);
/* Maximum-premium overlay (modal, command palette) — Benji's 7-layer graduated stack */
box-shadow:
  0 0 0 1px            rgba(0,0,0,0.04),
  0 1.625rem 3.375rem  rgba(0,0,0,0.04),
  0 1rem 2rem          rgba(0,0,0,0.03),
  0 0.625rem 1rem      rgba(0,0,0,0.024),
  0 0.3125rem 0.5rem   rgba(0,0,0,0.02),
  0 0.125rem 0.25rem   rgba(0,0,0,0.016),
  0 0 0.125rem         rgba(0,0,0,0.01);
```
**Frosted overlay** behind a modal/menu: `background: hsla(0,0%,100%,0.8); backdrop-filter: blur(1rem)` — a blur, not an opaque scrim, keeps the context legible underneath. The graduated stack + blur is the single biggest "this feels expensive" upgrade over a one-line shadow.

### Diagonal Sections (Stripe signature)
```css
.section-skew { transform: skewY(-12deg); transform-origin: 0; overflow: hidden; }
.section-skew > * { transform: skewY(12deg); }
```

### Benji's Layout Signatures
- **rem spacing scale** (his actual tokens): `0.5 · 1 · 1.5 · 2 · 2.5 · 3 · 3.5rem` (xxs→xxl), entry gap `3rem`, control gap `6px`. A rem ladder tracks the type scale better than a raw px grid on editorial surfaces — use it for prose/marketing, keep the 4px grid for dense tool UI.
- **Measure:** prose caps at `70ch` / **`36.375rem` (≈582px)**; dashboards at 1200px.
- **Heading *is* the divider** (no `<hr>`): `h2 { display: flex; gap: 0.75rem; align-items: center } h2::after { content: ''; flex: 1; height: 1px; background: rgba(0,0,0,0.08) }` — the rule runs from the label to the edge. One element, two roles.
- **Hairline as inset shadow, not border:** `box-shadow: inset 0 0 0 1px rgba(0,0,0,0.12)` — takes no layout space, can't be clobbered by a host stylesheet, and stacks cleanly beneath an elevation shadow.

---

## Animation System

### The Three Sacred Easings
```css
/* 1. Overshoot — entrances, popups, badges (strong bounce) */
--ease-overshoot:      cubic-bezier(0.34, 1.56, 0.64, 1);
--ease-overshoot-soft: cubic-bezier(0.34, 1.2, 0.64, 1);
/* Benji's site springs — gentler than the 1.56 bounce, for editorial entrances */
--ease-snappy: cubic-bezier(0.175, 0.885, 0.32, 1.1);
--ease-swift:  cubic-bezier(0.175, 0.885, 0.32, 1.275);

/* 2. Expo-out — position/size changes, expand/collapse (identical to Benji's --ease-smooth) */
--ease-sharp-out:  cubic-bezier(0.19, 1, 0.22, 1);

/* 3. Smooth-out — markers, elements, accordions */
--ease-smooth-out: cubic-bezier(0.22, 1, 0.36, 1);
--ease-expo-out:   cubic-bezier(0.16, 1, 0.3, 1);

/* 4. Exit — the ONE out-curve Benji ships for every exit, collapse, and the odometer */
--ease-exit: cubic-bezier(0.32, 0.72, 0, 1);
```
`--ease-sharp-out` *is* Benji's `--ease-smooth`, to the digit — skill and shipped code agree. Reach for `--ease-exit` on anything leaving or collapsing rather than reusing an entrance curve on the way out.

### Asymmetric Duration Rule
**ALWAYS** make enter slower than exit. This is non-negotiable:
```
Popup:     200ms in  / 150ms out
Settings:  200ms in  / 100ms out
Tooltip:   135ms in  / 135ms out (symmetric exception — too small to notice)
Marker:    250ms in  / 200ms out  (150ms for batch clear)
Badge:     300ms in  / 200ms out
```

### Duration Tiers
```
Micro:    100-150ms  (hover bg, press scale, tooltip)
Standard: 200-300ms  (popups, badges, markers)   →  Benji: --duration-snappy 220ms · --duration-smooth 300ms
Expand:   400ms      (toolbar expand, panel width, send button reveal)
Morph:    500-800ms  (line-to-candle, controls blur dissolve)  →  --duration-swift 800ms
```

### Motion Restraint & Content Stagger
Benji's entire personal site ships **two** keyframes — restraint is the whole point:
- **`staggerIn`** — `from { opacity: 0; transform: translateY(8px) } to { opacity: 1; translateY(0) }`, `0.5s ease both`, children delayed **50ms** apart (`:nth-child(n) { animation-delay }`). This is how an article, list, or section *arrives* — a soft cascade, never a wall appearing at once.
- **`fadeInOut`** — `0%,100% { opacity: 0 } 10% { opacity: 1 }`, `~5s` — a slow ambient hint (a "copied", a transient status) that shows itself and leaves with no click.

The lesson for the 90%: most surfaces need *one* entrance and *no* looping motion. Spend the motion budget on the 10%.

### Enter Animation Patterns

**Popup / Panel** — scale + translateY + overshoot:
```css
@keyframes popup-in {
  from { opacity: 0; transform: scale(0.95) translateY(4px); }
  to   { opacity: 1; transform: scale(1) translateY(0); }
}
/* 0.2s cubic-bezier(0.34, 1.56, 0.64, 1) */
```

**Panel with blur** — sinking away on exit:
```css
/* Enter */ opacity: 1; transform: translateY(0) scale(1); filter: blur(0);
/* Exit  */ opacity: 0; transform: translateY(8px) scale(0.95); filter: blur(5px);
```

**Toolbar entrance** — dramatic scale + rotate:
```css
@keyframes toolbar-in {
  from { opacity: 0; transform: scale(0.5) rotate(90deg); }
  to   { opacity: 1; transform: scale(1) rotate(0); }
}
/* 0.5s cubic-bezier(0.34, 1.2, 0.64, 1) — soft overshoot */
```

**Blur dissolve** — for controls hiding behind a collapsed state:
```css
/* Visible */ opacity: 1; filter: blur(0); transform: scale(1);
/* Hidden  */ opacity: 0; filter: blur(10px); transform: scale(0.4);
/* 0.8s expo-out for blur/opacity, 0.6s for transform — blur lingers */
```

**Marker cascade** — staggered 20ms delays, enter first-to-last, exit last-to-first:
```js
const delay = isExiting
  ? `${(total - 1 - index) * 20}ms`
  : `${index * 20}ms`;
```

**Icon swap via React key** — force remount to replay animation:
```tsx
<span key={isDark ? "sun" : "moon"} className="icon-enter">
  {isDark ? <Sun /> : <Moon />}
</span>
/* scale(0.8) rotate(-30deg) -> scale(1) rotate(0), 0.35s overshoot */
```

### Press Feedback
Every interactive element on `:active`, 100ms ease: `transform: scale(0.96)` on controls/buttons, `scale(0.92)` on larger surfaces (cards, panels, markers).
Small elements (44px toolbar circle): `scale(0.95)` instead.

### Validation Shake
Decaying horizontal oscillation: `[-3px, 3px, -2px, 2px, 0]` over 250ms ease-out.

### Theme Toggle
Disable ALL transitions during theme switch to prevent color interpolation:
```css
.disable-transitions :is(*, *::before, *::after) {
  transition: none !important;
}
```

### Reduced Motion
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

### Freezing Motion (capture a still)

To stop every animation dead — for a screenshot, an annotation overlay, or a "pause the world" button — you must hit **four independent surfaces**; miss one and something is still moving (Source: Agentation `freeze-animations.ts`).

1. **CSS animations/transitions** — inject one stylesheet: `* { animation-play-state: paused !important; transition: none !important; }`. Exclude your own chrome so overlays keep animating — append `:not([data-ui]):not([data-ui] *)` to the selector.
2. **WAAPI** (`el.animate()`) — `document.getAnimations()`, then pause only those with `playState === 'running'`. Pausing a *finished* animation restarts it on `.play()` (replaying entrances), so skip those — and store the refs you *did* pause to resume exactly them.
3. **JS timers & rAF** — monkeypatch `setTimeout`/`setInterval`/`requestAnimationFrame`: while frozen, **queue** timeout & rAF callbacks (never drop them — dropping strands loops that never resume) and **skip** interval ticks. Keep the originals (`originalSetTimeout`) so your own UI bypasses the patch.
4. **Media** — pause every `<video>`; tag which ones you paused so unfreeze resumes only those.

**Unfreeze in order — it isn't symmetric:** replay queued callbacks via `origSetTimeout(cb, 0)` (async, never block the frame) → resume the stored WAAPI animations → *then* remove the injected CSS (pull it first and the browser can swap the animation objects out from under you) → resume tagged videos. Re-check the frozen flag inside each replayed callback in case you re-froze mid-flight.

---

## Live Data & Canvas Charts (Liveline Patterns)

Use these patterns for any chart, graph, or real-time data visualization.

### Canvas Rendering Engine

**rAF loop structure:**
```js
function draw(timestamp) {
  const dt = Math.min(timestamp - lastFrame, 50); // cap at 20fps floor
  lastFrame = timestamp;
  // ... all drawing ...
  rafId = requestAnimationFrame(draw);
}
```

**Visibility optimization:** Stop the loop when `document.hidden`, restart on `visibilitychange`. Zero CPU when tab is backgrounded.

**DPI handling:**
```js
const dpr = Math.min(window.devicePixelRatio || 1, 3); // cap at 3x
canvas.width = Math.round(w * dpr);
canvas.height = Math.round(h * dpr);
canvas.style.width = `${w}px`;
canvas.style.height = `${h}px`;
ctx.setTransform(dpr, 0, 0, dpr, 0, 0); // draw in CSS pixels
```

**Resize via ResizeObserver** — observer writes to a ref, rAF reads it. Never in the same synchronous flow.

### The Exponential Lerp (Core of "Alive" Feel)

This is the single most important function. It makes everything feel organic:
```js
function lerp(current, target, speed, dt = 16.67) {
  const factor = 1 - Math.pow(1 - speed, dt / 16.67);
  return current + (target - current) * factor;
}
```

- `speed` is calibrated for 60fps (fraction approached per 16.67ms)
- `dt` normalization makes it frame-rate independent
- Small moves snap quickly, large jumps animate smoothly

**Speed reference for different elements:**
```
0.08  — Base lerp (value tracking, range boundaries, time debt drain)
0.09  — Chart reveal (loading -> data morph)
0.10  — Series toggle alpha
0.12  — Scrub fade, momentum color blend, pause deceleration
0.14  — Loading alpha crossfade
0.15  — Badge width
0.18  — Grid label fade-in (0.12 for fade-out — asymmetric!)
0.25  — Live candle OHLC, smooth close line
0.35  — Badge Y position (0.5 during window transitions)
```

**Adaptive speed boost:** When the gap is small relative to visible range, speed increases:
```js
const adaptiveSpeed = baseSpeed + (1 - gapRatio) * SPEED_BOOST;
```
Small ticks snap. Large jumps glide.

### Making Data Feel "Alive"

**1. Breathing loading state** — three-frequency sinusoidal composite:
```js
function loadingY(t, centerY, amplitude, scroll) {
  return centerY + amplitude * (
    Math.sin(t * 9.4 + scroll) * 0.55 +
    Math.sin(t * 15.7 + scroll * 1.3) * 0.3 +
    Math.sin(t * 4.2 + scroll * 0.7) * 0.15
  );
}
// amplitude = chartHeight * 0.07
// Alpha breathes: 0.22 + 0.08 * sin(now / 1200 * PI) → period ~2400ms
```
Render through the same cubic spline as real data so the shape and data line are visually identical.

**2. Center-out data reveal** — when data arrives, it blooms from the middle:
```js
const centerDist = Math.abs((x / chartW) - 0.5) * 2; // 0 at center, 1 at edges
const localReveal = clamp((globalReveal - centerDist * 0.4) / 0.6);
y = loadingY + (realY - loadingY) * localReveal;
```
Line color blends from grey to accent at 3x reveal speed (colored by ~33%).

**3. Live dot pulse** — expanding ring every 1500ms:
```
Ring: 9px -> 21px radius over 900ms, alpha 0.35 -> 0
Inner: white outer ring (6.5px, shadowBlur:6) + accent inner dot (3.5px)
Quiet period: 600ms between pulses
Suppressed during scrub hover
```

**4. Momentum arrows** — directional chevron cascade:
```
Cycle: 1400ms
Two arrows, staggered 200ms apart
Brightness: 0.3 base + 0.7 * sin(localT/dur * PI)
"Up": bottom arrow fires first (energy moves up)
"Down": top fires first
Direction crossfade: old must reach < 0.02 before new can start
```

**5. Momentum color blending** — smooth green/red transitions:
```js
// badgeColor.green lerps 0-1 at speed 0.12
// Passes through yellow/orange tones during transitions
const r = lerp(RED[0], GREEN[0], greenAmount);
const g = lerp(RED[1], GREEN[1], greenAmount);
const b = lerp(RED[2], GREEN[2], greenAmount);
```

**6. Candlestick live glow:**
```js
const pulse = 0.12 + Math.sin(now * 0.004) * 0.08; // period ~1570ms
ctx.shadowColor = candleColor;
ctx.shadowBlur = 8;
ctx.globalAlpha = baseAlpha * pulse;
```

**7. Value display bypassing React** — direct DOM ref manipulation at 60fps:
```js
const el = valueDisplayRef.current;
if (el) {
  el.textContent = formatValue(displayVal);
  el.style.color = momentum === 'up' ? '#22c55e' : momentum === 'down' ? '#ef4444' : '';
}
```

**8. Badge position tracking** — GPU-accelerated, lerp-smoothed:
```js
badgeY = lerp(badgeY, targetY, 0.35, dt);
// Width measured with template: text.replace(/[0-9]/g, '8') for widest-digit stability
badge.style.transform = `translate3d(${x}px, ${y}px, 0)`;
```

### Chart Transitions

**Line-to-candle morph** — cosine ease over 500ms:
```js
const prog = (1 - Math.cos(t * Math.PI)) / 2; // smooth S-curve
// OHLC collapse: open = close + (open - close) * (1 - prog)
// Alpha crossfade: line at prog, candles at (1 - prog)
// Badge visible only when prog > 0.5
```

**Window switch** — logarithmic interpolation over 750ms (so 30s->3600s feels proportional):
```js
const result = Math.exp(lerp(Math.log(from), Math.log(to), eased));
```

### Interaction: Crosshair Scrub

- Vertical line at cursor, dot at intersection (4px, accent)
- Chart dims 60% right of cursor
- Crosshair fades out near live dot (< 5px hidden, > 80px full)
- Candle scrub: graduated opacity by distance (1.5x candle width fade zone)
- `scrubAmount` lerps at speed 0.12 for smooth in/out

### Grid System (Adaptive with Hysteresis)

- TradingView cycling divisors: `[2, 2.5, 2], [2, 2, 2.5], [2.5, 2, 2]`
- Sticks to current interval until spacing falls outside `[0.5x, 4x]` of 36px minimum
- Per-label alpha tracked in a `Map<number, number>`, individually lerped
- Edge labels fade in a 32px zone near chart boundaries
- Fine labels (half interval) progressive: 0 below 40px, 1 above 60px

### Particle Physics (for emphasis/celebration)

```
Trigger: swing > 8% of visible range, 400ms cooldown
Count: 12-20 particles, max 80 total, 1-second lifetime
Burst falloff: [1.0, 0.6, 0.35] for consecutive bursts
Angle: ~1.2*PI semicircle spread in momentum direction
Drag: 0.95 per frame (exponential decel)
Size: 1-2.2px, shrinks with life: size * (0.5 + life * 0.5)
Alpha: life * 0.55
Chart shake: (3 + swing * 4) * burstIntensity, decays at 0.002^(dt/1000)
```

### Orderbook Floating Labels

```
Spawn: every 40ms, weighted random by order size
Speed: blended from price momentum + orderbook churn (60-160 px/s)
Deceleration: labels slow as they rise (100% speed at bottom, 70% at top)
Colors: green (bids) / red (asks), fade toward background RGB as alpha drops
Overlap prevention: 22px minimum gap between spawns
```

---

## Component Patterns

### Pill Controls (Window/Tab Selector)
- Inline-flex, `gap: 2px`, subtle bg `rgba(255,255,255,0.03)`
- Sliding indicator: absolute div, animates `left` + `width` at 0.25s standard easing
- Active: `font-weight: 600`
- Three styles: default (rounded rect), rounded (pill), text (transparent)

### Floating Toolbar
- Fixed bottom-right; for injection into an arbitrary host page, use a high z-index band near the max (`2147483647`) — e.g. reserve `99994–100002` for overlay → marker → popup → drag-preview stacking
- Collapsed: 44x44px circle. Expanded: pill (297px or 337px)
- Background: `#1a1a1a`; radius `22px` collapsed → `1.5rem` expanded
- Expand/collapse: width at 0.4s expo-out
- Controls blur dissolve: 0.8s filter + opacity, 0.6s transform

### Icon State Machine
Four states for animated icon transitions:
```css
.visible       { opacity: 1; }
.hidden        { opacity: 0; }
.visibleScaled { opacity: 1; transform: scale(1); }
.hiddenScaled  { opacity: 0; transform: scale(0.8); }
```
Stack two `<g>` groups, one visible + one hidden. Swap classes to crossfade-morph.

### Tooltip System
- Enter: `scale(0.95)` to `scale(1)`, 135ms ease
- First hover delay: 850ms. Subsequent: instant (toggle `.tooltipsInSession` class)
- 8px arrow pseudo-element rotated 45deg

### Send Button Reveal
Width-based with staggered inner scale:
```css
/* Hidden */ width: 0; opacity: 0; margin-left: -0.375rem; .btn { scale: 0.8; }
/* Visible */ width: 34px; opacity: 1; margin-left: 0; .btn { scale: 1; }
/* width, margin, inner-scale: 0.4s expo-out — but opacity 0.3s (fades a touch faster than it grows) */
```

### Checkbox Draw Effect
SVG `stroke-dasharray` / `stroke-dashoffset` for draw-in:
```css
.check-path { stroke-dasharray: 9.29px; stroke-dashoffset: 9.29px; }
:checked ~ .check-path { stroke-dashoffset: 0; transition: 0.2s; }
/* Undraw: 0.1s — faster out, slower in */
```

### Accordion (Smooth Height)
```css
.wrapper { display: grid; grid-template-rows: 0fr; transition: grid-template-rows 0.3s expo-out; }
.wrapper.open { grid-template-rows: 1fr; }
.inner { overflow: hidden; }
```

### Connection Pulse Variants
```css
/* Connected (calm):    2.5s cycle, green, ring expands to 6px */
/* Connecting (urgent): 1.5s cycle, yellow */
/* Error:               2.0s cycle, red */
/* Asymmetric keyframes: expand 0-70%, snap back 70-100% */
```

### Color Picker Selection Ring
Two pseudo-elements: inner swatch shrinks to `scale(0.8)`, outer ring at `scale(1.2)` fades in. Gap reveals parent background.

### TOC Scrollspy
Vertical track (1.5px gray) with animated indicator bar:
```css
&::after {
  transform: translateY(var(--active-top));
  height: var(--active-height);
  transition: 260ms cubic-bezier(0.25, 0.46, 0.45, 0.94);
}
```
Active link uses `font-variation-settings: 'wght' 500`.

### Skeleton / Wireframe Loading
The skill bans "No data" and the spinner — a **wireframe skeleton shaped like the content that's coming** is the counterpart (Source: Agentation `design-mode/skeletons.tsx`):
- One skeleton per component *type* (card, table row, chart, avatar+text), each **scaling to the final element's box** so nothing reflows when data lands — the swap is a crossfade in place.
- **Structure over shimmer.** Benji's are *static* type-shaped wireframes, not sweeping bars: a card = title bar (~60% width) + two text lines (100%/80%) + a footer. Two-tier fill (`rgba(fg,0.18)` / `0.28` for emphasis), 1px stroke at `0.35`. A faint `~1.5s` opacity pulse is optional and must be **pausable** (`animation-play-state: paused`) — a moving-gradient sweep is *not* the house style.
- **Deterministic, never random.** Vary widths/counts by index math so the skeleton is stable across re-renders (a reshuffling skeleton reads as broken): `width: ${50 + ((row*7 + col*13) % 40)}%`. Counts scale to the box — table rows `clamp(2, h/32, 6)`, chart bars `clamp(3, w/50, 7)`.

### Rolling Number (odometer)
For a value that updates in place — a live count, a running total: the old digit rolls out as the new rolls in from the opposite direction (Source: Agentation `palette.tsx`). Two stacked `<span>`s, `translateY(±110%)` + opacity, **`0.25s var(--ease-exit)`** (his exit curve), with a `250ms` clear timer; skip the roll entirely when going to 0. The detail that sells it: when only the **number** changes, roll just the number; when the **suffix** changes too ("1 Change" → "2 Changes"), roll the whole label as a unit. `tnum` + pre-measured width so nothing jumps.

### Stable Selectors (overlays that must re-find their target)
Any marker, tooltip, or annotation pinned to a page element needs a selector that survives re-renders (Source: Agentation `section-detection.ts`). Resolve in priority order: **unique semantic tag** (`nav`/`header`/`footer`/`main` when there's only one) → `#id` → `tag.first-meaningful-class` (skip CSS-module hashes — drop classes matching `/^[a-z0-9]{6,}$/` or a `_hash` suffix) → `parent > tag:nth-child(n)` chain. Label a detected region by falling through: `aria-label` → ARIA role → semantic tag name → its first heading's text → a generic fallback.

### Editorial Timeline (changelog / dated list)
A dated vertical list — writing archive, changelog, activity feed — reads best as node dots on a hairline (Benji's writing index):
- **Line:** 1px, `rgba(0,0,0,0.08)`, pushed into the left margin (`left: -1.75rem`), running between entries.
- **Node:** `9px` circle, `background: #fff`, ring via `box-shadow: inset 0 0 0 1.5px rgba(0,0,0,0.12)` (not a border), `z-index: 1` so it sits over the line.
- **Rhythm:** entries `3rem` apart; the line's top/height derive from line-height + dot size so it starts *below* the first node and ends *above* the last. The dot is ambient status — tint it to encode state (shipped / draft / live).

### Scroll-Edge Fade (mask, not a hard cut)
Any internal scroll area (listbox, minimap, long popover) should fade its clipped content: `mask-image: linear-gradient(to bottom, transparent, #000 32px, #000 calc(100% - 32px), transparent)`. Toggle the top/bottom fade by scroll position (`scrollTop > 2`; distance-from-bottom) so a fade shows only where there's more to see. Pair with a 3px scrollbar, thumb `rgba(255,255,255,0.12)`.

### Editorial Text Marks (inline)
Three inline treatments that make prose feel typeset (Benji's article styles):
- **Highlight / inline-code** — a pseudo-element *behind* the text: `inset: -0.1em 0; border-radius: 0.25rem; background: rgba(0,0,0,0.04)`. Softer than a bordered `<code>` box.
- **Custom underline** — draw it as a pseudo-element offset below the baseline (`border-bottom: 1px solid #f2f2f2; transform: translateY(1.25em)`) so it clears descenders instead of striking through them.
- **Numbered-list chips** — replace the default marker with a `1rem` circle (`background: #f2f2f2`, counter at `0.625rem/500`, centered): a designed number, not a browser bullet.

---

## Controls, Dials & Selectors

The single biggest tell of an unfinished interface is a **native control**: the OS-rendered `<select>` chevron, the grey `<input type="range">` track, the default checkbox, the platform date picker. They ignore your accent, your surface stack, your easings, and your radius philosophy — they look like a different product bolted on. **No native chrome ships. Ever.** This is the #1 reason controls "look terrible."

### The Cardinal Rule

`appearance: none` on every form element, then rebuild it from the system. A control is just another surface — it obeys the same `rgba()` stack, the same accent derivation, the same three sacred easings, the same press feedback.

```css
.control {
  appearance: none; -webkit-appearance: none;
  font: 500 12px var(--font-data);
  color: var(--text-primary);
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px;
  height: 34px; padding: 0 10px;
  transition: background 120ms var(--ease-smooth-out),
              border-color 120ms var(--ease-smooth-out),
              box-shadow 120ms var(--ease-smooth-out);
}
@media (hover: hover) {
  .control:hover { background: rgba(255,255,255,0.05); border-color: rgba(255,255,255,0.15); }
}
.control:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px var(--accent-border);   /* respects radius — outline does not */
  border-color: var(--accent);
}
.control:active { transform: scale(0.96); transition-duration: 100ms; }
.control:disabled { opacity: 0.4; cursor: not-allowed; }
```

### State Without JS — `:has()`
Drive control state from the DOM, not a React state class. A checkbox, switch, or radio can style itself entirely from the native input's `:checked` — no `useState`, no re-render, and it stays form-native and accessible for free (Source: Agentation switch & checkbox — both pure CSS):
```css
.switch { background: rgba(255,255,255,0.08); }
.switch:has(.input:checked) { background: var(--accent); }
.switch:has(.input:checked) .thumb { transform: translateX(16px); }  /* never animate left */
.switch:has(.input:disabled) { opacity: 0.4; }
```
The native `<input>` sits `position: absolute; inset: 0; opacity: 0` on top, so the whole control is the hit target (use `inset: -1px` to reclaim the border area). One source of truth — the input — instead of a state flag that can drift out of sync with it.

### Shared Anatomy (every control)
- **Height rhythm:** 28px compact · 34px standard · 40px prominent. Pick one per surface and hold it — a control bar with mismatched heights reads as broken.
- **Four states, always:** rest → hover (`+0.02` surface, `+0.07` border) → focus (accent ring) → active (`scale(0.96)`). Disabled is a fifth: `opacity: 0.4`, no hover.
- **Focus ring:** `box-shadow: 0 0 0 2px var(--accent-border)`, never `outline`.
- **Transition:** list the properties — `background, border-color, box-shadow, transform`. Never `transition: all`.
- **No layout shift on state change.** Don't bold-on-hover or grow the box — pre-reserve the space.

### Select → Custom Listbox
Restyling the native `<select>` gets you a clean trigger, but the OS still draws the option menu (you cannot style it). For anything premium, replace it with a button + popover listbox.

```
Trigger:  button, control anatomy above, shows current VALUE + chevron (right)
Chevron:  16px SVG, stroke 1.5, rotates 180° on open (180ms smooth-out)
Popover:  popup-in keyframe (scale .95 + translateY 4px, 0.2s overshoot)
          surface-1 + dark-panel shadow, radius 12px, max-height 280px, scroll
Option:   height 32px, padding 0 10px, radius 6px
          hover  → background: var(--accent-subtle)
          active → accent text + check icon (right), draw-in via stroke-dashoffset
Keyboard: ↑/↓ move, Enter select, type-ahead match, Esc close (returns focus to trigger)
Open on:  mousedown (saves ~100ms perceived latency vs click)
```
If you must stay native (simple form, low stakes): `appearance: none`, supply the chevron as a `background-image` SVG data-URI positioned right, pad `padding-right: 28px`. Accept the option list stays OS-drawn — so reserve this for throwaway forms, never a hero surface.

### Segmented / Pill Selector (the right default for "pick one of N")
See **Pill Controls** above. The detail that makes it luxe: a single absolutely-positioned indicator div that slides `left` + `width` at `0.25s var(--ease-smooth-out)` — the segments themselves never animate. Equal-width segments, active label at `font-weight: 600` **pre-measured** so switching causes no reflow. Reach for this over a dropdown whenever N ≤ 5 — it shows all options at a glance and switches in one click.

### Range Slider
```
Track:  height 4px, background rgba(255,255,255,0.08), radius full
Fill:   accent, left of thumb — linear-gradient sized to the value %, or a wrapper div
Thumb:  14px circle, background #fff (dark) / accent (light),
        box-shadow 0 2px 6px rgba(0,0,0,0.2), inset 0 0 0 1px rgba(0,0,0,0.04)
Hover:  thumb scale(1.14) — transform, NEVER width (160ms smooth-out)
Active: accent glow ring → box-shadow 0 0 0 6px var(--accent-glow)
Bubble: current value floats above thumb on hover/drag (popup-in, --font-data, tnum)
```
`appearance: none` the track, then style `::-webkit-slider-thumb` and `::-moz-range-thumb` **separately** — they don't share a selector. Snap to steps and always show the live value; a slider with no readout is a guess.

### Rotary Dial / Knob
For a true "dial," draw it as SVG — don't fake it with a rotated `<div>`:
```
Track arc:  circle/arc, stroke rgba(255,255,255,0.08), stroke-width 4, round caps
Value arc:  same path, stroke var(--accent), stroke-dasharray driven by value
Indicator:  a tick or dot at the current angle
Center:     monospace value, tnum, --font-data
Drag:       vertical drag = ± value (ns-resize cursor), or angular drag for full rotary
Active:     drop-shadow var(--accent-glow); value arc brightens
```
Lerp the arc to its target (`speed 0.2`) so it settles rather than snaps. Always pair a dial with a typed/scrub fallback — pure rotary is hard to set precisely.

### Toggle Switch
```
Track:  36×20, radius full, rgba(255,255,255,0.08) off → var(--accent) on
Knob:   16px circle, translateX(16px) on — transform, NEVER animate left
Timing: 200ms var(--ease-overshoot-soft) (the knob carries a little weight)
```
Takes effect **immediately** — never gate a toggle behind a confirm dialog. Color = state, so the track is the label; add a text label only if the meaning isn't obvious from context.

### Checkbox & Radio
Checkbox: the **Checkbox Draw Effect** above (stroke-dashoffset, 0.2s in / 0.1s out). Radio: inner dot `scale(0) → scale(1)` on the overshoot curve. Both get the box-shadow focus ring. Hit target ≥ 24px even when the glyph is 16px — pad the label, don't grow the glyph.

### Number Stepper & Scrub-Label
- **Stepper:** monospace field + tiny ▲▼ (or −/+) with hold-to-repeat. `tnum` so digits don't jump width.
- **Scrub-label** (Figma / Bret Victor): the value label itself is draggable horizontally — `cursor: ew-resize`, drag changes the number live. Display + input in one element (see Compound Control Taxonomy). Pointer-lock for infinite drag; Shift = fine, Alt = coarse.

### Multi-Select / Combobox
Trigger holds selected values as removable chips (chip = label + 12px `×`, `scale(0.92)` press on the `×`). Popover is the custom listbox with a checkmark per selected row and a type-to-filter input pinned at the top. The input filters in place — no separate "search" control beside it.

### Date / Time
Native `<input type="date">` looks different on every OS and ignores the system — **don't ship it.** Use either a custom calendar popover (cells on the 32px grid, today = accent ring, selected = accent fill, range = accent-subtle band) or three monospace scrub-fields (DD / MM / YYYY) for fast keyboard entry. For dashboards, prefer a **range** control — and remember a pannable/zoomable timeline chart can BE the date picker (see Consolidation).

---

## Icon System

All icons are custom SVG:
- `fill="none"`, `stroke="currentColor"`
- `stroke-width: 1.5`, `stroke-linecap: round`, `stroke-linejoin: round`
- Sizes: 16px (inline), 20px (controls), 24px (navigation)
- Animated via CSS class state machine (visible/hidden/scaled)
- Copy icon morphs to green checkmark circle on click
- Protect SVGs from host CSS: `svg[fill="none"] { fill: none !important; }`

### Starter Set
A ready set of stroke icons in exactly this style ships at [`references/icons.tsx`](references/icons.tsx) — each is `({ size }) => <svg viewBox fill="none" stroke="currentColor" strokeWidth={1.5}>`, zero-dependency and theme-free (inherits `currentColor`). Geometry is trivial and swappable: plus = `M8 3v10M3 8h10`, check = `M3 8l3.5 3.5L13 5`. It includes the **animated variants** that carry the soul — copy → checkmark draw-in on click, pause ↔ play scale-swap, eye ↔ eye-off slash — all done with inline `transform`/`stroke-dashoffset` transitions (no `@keyframes`, no motion lib). Extend this set rather than pulling in an icon package: one visual voice, zero bundle cost.

---

## Special Effects

### Sketchy Underline
```css
background-image: linear-gradient(75deg,
  color-mix(in srgb, var(--accent) 50%, transparent) 0%,
  color-mix(in srgb, var(--accent) 85%, transparent) 25%,
  color-mix(in srgb, var(--accent) 70%, transparent) 50%,
  color-mix(in srgb, var(--accent) 40%, transparent) 100%);
background-size: 100% 40%;
background-position: 0 95%;
box-decoration-break: clone;
```

### Red Pen Underline
SVG data URI with curved path `Q50 4 98 7`, 8px height at bottom.

### Mesh Gradient (Stripe — hero sections only)
WebGL Simplex noise FBM, 4 stops (magenta, cyan, violet, gold), `skewY(-12deg)`, text overlay with `mix-blend-mode: color-burn`.

### Browser Chrome Mockup
Three dots (8x8px) — `#ff5f57`, `#febc2e`, `#28c840` — faux URL bar at `rgba(0,0,0,0.04)`.

### Typed Character Reveal
Per-character `<span>` with staggered `animation-delay`. Each fades in over 100ms ease-out.

### Animated Explanatory Diagram (CSS-only)
For an architecture / sequence / data-flow diagram — *how the pieces talk to each other* — build a **living** diagram, not a static SVG (Source: Agentation `MCPDiagram.tsx`, ported CSS-only):
- **Lifelines & actors** — each actor is a pill across the top; drop a vertical dashed line (`stroke-dasharray: 3 3`, `rgba(...,0.08)`) beneath each.
- **Draw-in on reveal** — every connector arrow draws itself with the **Checkbox Draw Effect** (`stroke-dasharray`/`stroke-dashoffset → 0`), staggered ~150ms down the sequence. Request = solid line, response = dashed (`6 4`) — the line style *is* the legend (dedup).
- **Traveling pulse (the soul)** — a looping highlight that hops actor→actor. Inject the `@keyframes` into `<head>` once, then re-trigger each step by remounting the pulsed node via a React `key={step}` — CSS replays on remount, so there's no JS animation loop running. Per step (~1200ms): the active pill gains an accent border + glow, its label brightens grey→accent.
- **Gate it** — start only when scrolled into view (`IntersectionObserver`, `once`) so the intro plays on arrival, not offscreen (`prefers-reduced-motion` → jump straight to the final state).
- **Glow** — one reusable SVG `<filter>`: two `feGaussianBlur` (stdDeviation 3 and 6) merged over `SourceGraphic`, for the accent pulse.

No runtime motion library: draw-in is `stroke-dashoffset`, the pulse is injected `@keyframes` + `key` remount. (Benji's marketing site reaches for framer-motion here; the *shipped* component is pure CSS — hold to the shipped rule for anything reusable, save the lib for one-shot editorial.)

### Streaming / "Thinking" Text (AI + live output)
When text arrives token-by-token (an AI reply, a live transcript), reveal it as a **gradient wipe**, not a hard append: a `linear-gradient(90deg, …)` clipped to the text (`background-clip: text; -webkit-text-fill-color: transparent`) with a `--reveal` stop animated 0→100%; swap to a solid fill on completion. For the *waiting* state, a **shimmer** — a `200%`-wide gradient sliding under `background-clip: text`, `1.8s linear infinite` — reads as "thinking." (Source: Agentation `FeaturesDemo`; a natural fit for a transcript UI.)

### Connector Line (link two elements with a live bezier)
To draw a relationship between two on-screen elements (dependency, source→result): a quadratic bezier from center to center, control point offset perpendicular by `min(distance * 0.3, 60)`. The signature detail is **proximity fade** — scale the whole line + its endpoint dots by `min(1, distance / 40)`, so they shrink to nothing as the elements meet and pop as they separate. Endpoint dots `r4`, accent at `0.8`, white `1.5px` stroke, soft `feDropShadow`.

### External-Link Arrow
An outbound link's arrow earns a micro-move: on hover, `transform: translateX(0.25rem) rotate(45deg)` over `0.15s` — it slides out and swings to ↗. Cheap, and it makes "this leaves the page" felt rather than read.

---

## Interaction Density & Semantic Consolidation

**Consolidate by shared question, not merely by proximity.** Nearby controls do not automatically belong together. Merge elements when they answer the same user question: what is shown, how it is encoded, what state it is in, or what happens next. The strongest form is a **claim-control sentence**: a readable statement of the current view whose swappable words are the controls and whose legend keys can filter the marks they explain. For the reusable grammar, scenario library, trade-offs, and accessibility contract, read [`references/semantic-consolidation-patterns.md`](references/semantic-consolidation-patterns.md).

### The 3-Layer Rule (Mandatory for All Data)

Every data point, chart, metric, and control implements three layers:

| Layer | Effort | What Shows | Implementation |
|-------|--------|-----------|----------------|
| **Glance** | 0 — just look | The insight, trend, or status | Bold value, color-coded badge, sparkline |
| **Hover** | Mouse over | Context, exact values, breakdown | Tooltip, popover, crosshair with data window |
| **Click** | Intentional | Full exploration, editing, drill-down | Expand panel, navigate to detail, inline edit |

If a data point only has layer 1, it's a dead end. If a chart has no hover interaction, it's a screenshot pretending to be a component.

### Ambient Information (Layer Zero)

The 3-Layer Rule starts at *glance* — but the most elegant information sits **below** glance: absorbed in the periphery without directed attention. This is **layer zero — ambient.** The user knows the state without looking *for* it, because it's encoded into something already on screen.

**The test:** *Could the user know this without looking for it?* If they'd have to hunt, hover, or click to learn something they should always feel, make it ambient.

**Ambient channels** — encode info into properties already present, don't add new elements:

| Channel | Carries | Example |
|---------|---------|---------|
| **Color / tint** | Status, health, direction | Row tints red when over budget; a value goes green on an uptick |
| **Motion** | Liveness, activity | A slow pulse = connected & live; drifting labels = order flow |
| **Density** | Volume, load | More dots = busier; sparser = calm |
| **Position** | Type, rank | Spatial consistency — the same slot always means the same thing |
| **Size / weight** | Importance, magnitude | A number's weight scales with its value |
| **Background fill** | Trend, progress | Sparkline behind a KPI; fill level inside the button |
| **Badge / dot** | Count, presence | Unread count on the tab; presence dot on the avatar |

**Rules for ambient:**
- **Calm by default.** Ambient motion for low-priority info must be quiet — a 2.5s breathing pulse, not a flash. Loud motion is reserved for the rare event that earns interruption. (Respect the novelty/motion budget and `prefers-reduced-motion`.)
- **Encode, don't add.** Ambient is *not* more elements — it's loading meaning into elements that already exist. A separate "Status: OK" label is the *opposite* of ambient; tint the thing instead.
- **One channel per fact.** Don't signal the same state with color *and* an icon *and* a label — pick the quietest channel that reads, and stop (see Deduplication).
- **Ambient is the hook, not the whole story.** It says *something changed*; glance → hover → click reveal *what* and *why*. Escalate from there.

### Compound Control Taxonomy

Make one element carry multiple semantic loads:

| Pattern | What It Means | Example |
|---------|--------------|---------|
| **Display + Input** | The value shown IS the thing you edit | Figma scrub-labels, [Bret Victor's](https://worrydream.com/Tangle/) draggable inline numbers |
| **Status + Action** | The indicator IS the control to change it | [Linear](https://linear.app/) status badges — click the status to change it |
| **Navigation + Data** | The link shows data AND takes you somewhere | [Notion](https://notion.so/) relation cells, [TradingView](https://tradingview.com/chart/) price axis |
| **Controller + Progress** | Your scroll position IS the animation driver | [Apple](https://apple.com/apple-vision-pro/) product pages, [The Pudding](https://pudding.cool/) scroll-as-timeline |
| **Teacher + Tool** | Using it teaches you the faster way | [Superhuman](https://superhuman.com/) command palette showing shortcuts beside every action |
| **Label + Editorial + Instruction** | One caption line does triple duty | Benji's "Two props. That's it." — describes API, makes a claim, implies simplicity |

### Consolidation Checklist

Before shipping any component, ask:
- What single question is this cluster of labels, legends, filters, and counts answering? Can the current answer itself become the control surface?
- Can this control also display its current state? (e.g., a toggle that shows on/off rather than needing a separate label)
- Can this data point link to its source? (every metric should be explorable)
- Can this chart element respond to hover with a tooltip AND respond to click with a drill-down?
- Is there a separate progress indicator that could be embedded into the primary action?
- Are there adjacent controls that could merge? (e.g., left/right buttons that also show reading progress)
- Is the heading also the section divider? (Benji's h2 + horizontal rule = one element, two roles)

### Deduplication (One Fact, One Place)

Clutter is mostly repetition. The same number in the header and the card; the unit printed on every row instead of once in the column header; a legend that restates the axis; an icon paired with a label that says the same word; two buttons a hair apart in meaning. **Each fact, label, unit, and control should appear exactly once.** The second instance isn't reinforcement — it's noise, and it costs the page its impact.

**Dedup scan** (run before shipping any page):
- [ ] **Same value twice?** A metric in a KPI card *and* the chart axis *and* the tooltip — keep the one closest to where it's needed, drop the rest.
- [ ] **Repeated units / labels?** Lift `$`, `%`, `ms`, or a recurring word up into the column header / section title — state it once.
- [ ] **Redundant encoding?** Color *and* icon *and* text all signaling "error" — keep the quietest one that reads (usually color or icon, not all three).
- [ ] **Legend duplicating the axis or the line labels?** Drop the legend; label the line ends, or let the single-line legend carry it.
- [ ] **Near-duplicate controls?** Two filters / buttons / links with overlapping jobs — merge into one compound control.
- [ ] **Restated headings?** A page title, a breadcrumb, and an `<h1>` all saying the same thing — one wins.

**When a fact genuinely must be referenced twice,** make one the canonical source and the other a *pointer* (a link, an anchor, a derived summary) — never a verbatim restatement that can drift out of sync.

**Then let it breathe.** Every duplicate removed is room returned to what remains. Impact is contrast: one bold number in clear space outweighs ten competing for the same attention. After the dedup pass, resist refilling the space you just won — the emptiness is doing work.

### Information Sizing (Keep Everything on the Page)

For every piece of information, ask: **what's the right container size for this content?** The goal is to give the user everything they need on the current page — never punt to a separate page unless the content truly requires its own context. Navigation is cognitive cost. Every "click to see more" that could have been a tooltip or an expandable section is a failure of information design.

**Sizing hierarchy (smallest container that works):**

| Size | Use When | Implementation |
|------|----------|----------------|
| **Inline** | 1-5 words of context (units, status, type) | Colored text, badges, icons next to the value |
| **Tooltip** | 1-2 sentences of supplementary context | Hover-triggered, 200-280px max width, disappears on mouseout |
| **Popover** | A small data table, a mini-chart, or 3-5 lines of detail | Click-triggered, stays open until dismissed, 280-400px |
| **Expandable section** | A paragraph of explanation, a secondary data table, configuration options | Inline accordion below the trigger, `grid-template-rows: 0fr/1fr` |
| **Side panel** | A full detail view that relates to something still visible on the page | Slide-in from right, 320-480px, parent content remains visible and interactive |
| **Full page** | **Only when** the content requires its own URL (shareable, bookmarkable) or is a completely independent workflow | Route change — avoid unless truly necessary |

**The rule: default to the smallest container.** Start at tooltip. Ask "does this really need to be bigger?" Only escalate if the answer is yes. Most detail that gets a separate page could have been a side panel. Most side panels could have been expandable sections. Most expandable sections could have been popovers.

**Consolidation moves by container:**
- **Kill the "detail page"** — if a table row click navigates to `/item/:id`, ask: could this be a side panel instead? The user keeps context of the list while seeing full detail.
- **Kill the popover** — if the popover just shows a label + value, make it a tooltip. If it shows a form, make it an inline expansion.
- **Kill the tooltip** — if the tooltip shows something the user always needs, make it inline (badge, colored text, icon). Tooltips are for supplementary context, not primary information.
- **Keep related data together** — if a user needs to see Chart A to understand Chart B, they must be on the same page. Never split related data across routes.
- **URL-worthy vs not** — a page needs its own route only if someone would share it, bookmark it, or deep-link to it. Everything else stays on the parent page in a smaller container.

### Consolidation Techniques Library

**Less is more.** Every element removed is cognitive load saved. When reviewing any page or component, run through this checklist and **recommend the best consolidation opportunity** for the specific context.

For substantial data surfaces, do not stop at the first obvious merge. Generate at least three context-specific candidates from the scenario library, compare what each eliminates and what it hides, then choose the one that reduces thinking without reducing legibility.

#### Scan Checklist (run on every page/component)

For each item found, flag it and suggest the best technique from the library below:

- [ ] **Separate status indicator next to a control?** → Embed status INTO the control (color-as-status, fill-as-progress, badge-on-nav)
- [ ] **Chart + separate legend?** → Tooltip replaces legend, or color-coded labels at line endpoints (Liveline pattern)
- [ ] **Chart + separate filter/date picker?** → Make the chart pannable/zoomable, or use linked brushing between charts
- [ ] **KPI number + separate trend chart?** → Mini sparkline behind the number in one card
- [ ] **List + separate search/filter controls?** → Inline filter row at top of list, or command palette overlay
- [ ] **Button + separate progress indicator?** → Progress fill inside the button
- [ ] **Section heading + separate divider?** → Heading IS the divider (Benji's h2 + thin rule extending to edge)
- [ ] **Nav items + separate notification area?** → Badge counts on the nav items themselves
- [ ] **Multiple related charts showing different views?** → Linked brushing, or faceted small multiples, or overview+detail
- [ ] **Data table + separate detail view?** → Expandable rows, or hover-to-preview + click-to-expand
- [ ] **Map + separate region list?** → Clickable map regions as navigation/filter
- [ ] **Form + separate validation messages?** → Inline validation with input border color + icon (not separate error block)
- [ ] **Multiple tabs/views that could be one?** → Can a single view serve both purposes with density adjustments?
- [ ] **>7 competing visual elements on screen?** → Something must merge or hide behind a hover layer

#### Technique Library

**A. Embed data into existing elements** (Ref: [Linear](https://linear.app/) issue rows, [Superhuman](https://superhuman.com/) inbox tabs, [Devouring Details](https://devouringdetails.com/) minimap)
- Sparklines inside table cells — 40x16px inline next to the value. One cell = number + trend.
- Progress fill in buttons — background fill shows completion %. Button + progress = one element.
- Color-as-status — tint the row/value/border instead of a separate badge. Green = healthy, red = alert. (Liveline's momentum color blending)
- Badge counts on nav items — unread count on the tab, not a notification center.
- Opacity-as-state — active nav at full opacity, inactive at 0.35. No underlines, no backgrounds needed. (Benji's Agentation nav)
- Minimap-as-progress — a fixed sidebar showing section indicators that double as scroll progress. (Devouring Details left sidebar: 36 thin bars, active = wider + darker)

**B. Replace chrome with data** (Ref: [TradingView](https://tradingview.com/chart/) charts, Benji's Liveline grid system, [Stripe](https://stripe.com/) dashboard)
- Reference lines as axis labels — light horizontal lines at key values. The lines ARE the context. (Liveline's adaptive grid with hysteresis)
- Data-ink ratio — strip borders, backgrounds, legends. A line chart needs no box. Bars with value labels need no gridlines.
- Heading = divider — h2 + thin rule to the edge. No `<hr>`, no bg color change, no card wrapper. (Benji's Agentation sections)
- Active state = label — the active tab's styling IS the "you are here." No breadcrumb needed.
- Type hierarchy = grouping — size/weight/color differences replace card wrappers and section borders. (Devouring Details: 4 type scales create hierarchy with zero decorative containers)
- Single accent = system — one color at varying `color-mix()` percentages replaces multiple semantic colors for non-status uses.

**C. Merge adjacent views** (Ref: [Apple](https://apple.com/apple-vision-pro/) product pages, [Observable](https://observablehq.com/) notebooks, [Figma](https://figma.com/) property panel)
- Mini-chart inside KPI card — 80x40px sparkline behind the number. One card = value + trend.
- Map as navigation — click a region to filter. Visualization IS the filter. (Geo dashboards, Stripe Radar)
- Chart as selector — click a bar to drill down. Overview IS navigation to detail.
- Timeline as scroll — pannable/zoomable chart replaces date picker. The chart IS the date selector.
- Property panel as persistent tooltip — instead of hover tooltips for selected items, a fixed sidebar shows all properties. ([Figma](https://figma.com/) right sidebar: always visible, context-aware)
- Scroll as controller — scroll position drives animation/data state. No separate playback controls. ([Apple](https://apple.com/apple-vision-pro/) scroll-driven image sequences, [The Pudding](https://pudding.cool/) scroll-as-timeline)
- Inline editing replaces edit mode — click a value to edit it in place. No separate "edit" button or modal. ([Notion](https://notion.so/) cells, [Figma](https://figma.com/) scrub-labels)

**D. Eliminate with interaction layers** (Ref: [Rauno](https://rauno.me/)'s interaction design, [Bret Victor](https://worrydream.com/Tangle/)'s explorable explanations, [Nicky Case](https://ncase.me/))
- Hover replaces labels — show labels only on hover. 90% less noise, 100% of info available.
- Click replaces modals — expand the row inline. No context switch, no overlay.
- Tooltip replaces legend — hover any line to see its label + value. Interaction IS the legend. (Liveline's crosshair with floating data window)
- Scroll replaces pagination — virtual scroll instead of page numbers. Fewer controls, same access.
- Scrub replaces slider — drag a label to change a value. The label IS the input. ([Figma](https://figma.com/) scrub-labels, [Bret Victor](https://worrydream.com/Tangle/) draggable numbers)
- Command palette replaces menus — one `Cmd+K` surface replaces toolbar buttons, navigation menus, and search. Teacher + tool in one. ([cmdk](https://github.com/pacocoursey/cmdk), [Superhuman](https://superhuman.com/))
- Contextual actions on hover — action buttons appear only when hovering the relevant row/element. Zero UI when not needed. ([Notion](https://notion.so/) row actions, [Linear](https://linear.app/) issue rows)
- Sandbox replaces tutorial — let users play with the real thing instead of reading about it. The product IS the documentation. (Benji's "Try it" section, [Nicky Case](https://ncase.me/trust/)'s playable essays)

**E. Connect views** (Ref: [TradingView](https://tradingview.com/chart/) linked charts, [Observable](https://observablehq.com/) reactive notebooks, [Amelia Wattenberger](https://wattenberger.com/))
- Linked brushing — select a range on Chart A, Chart B highlights corresponding data. Two charts, one interaction, no filter control.
- Overview + detail — small zoomed-out chart with draggable window controls the main chart. The overview IS the zoom.
- Faceted small multiples — N small charts side by side instead of one chart + dropdown filter. Each facet IS a filter value.
- Reactive variables — change one widget, all dependent visualizations recalculate. ([Observable](https://observablehq.com/) cell reactivity)
- Tooltip contains sub-chart — hover a data point to see a secondary visualization inside the tooltip. Chart-in-chart. ([Amelia Wattenberger](https://wattenberger.com/)'s nested tooltips)
- Cross-highlight — hover on one view dims non-corresponding elements in all other views. Passive linking without explicit selection.

#### How to Recommend

After running the scan checklist, present your recommendation:
```
**Consolidation opportunity:** [what you found]
**Technique:** [specific technique from A-E above]
**Why this one:** [why it's the best fit for this specific context]
**What it eliminates:** [which separate element(s) are no longer needed]
**Trade-off:** [any discoverability or clarity cost, if applicable]
```

### Hero & Page Architecture

Every page needs a hero that earns attention. Stripe's approach: bold claim, full-bleed visual, single CTA. Benji's approach: show the most impressive thing FIRST, then explain.

**Show → Tell → Do** (Benji's page flow):
1. Show the most impressive demo (not the simplest)
2. Explain what you just saw
3. Let the user try it themselves (the page IS the demo)

**Pacing rhythm:** DENSE → BREATHE → DENSE → BREATHE → EXHALE
- Pages should get lighter toward the end
- After a run of dense feature sections, insert a text-only breathing section
- Close with the simplest possible version (Benji's "Just a line" ending)

### Making Density Non-Overwhelming

1. **Hover-gating** — show actions/detail only on hover (Notion, Linear)
2. **Default collapse** — show summary, expand on demand
3. **Spatial consistency** — same position always means same data type
4. **Color-as-data** — systematic color coding replaces labels
5. **Optimistic responsiveness** — act before server confirms (target <100ms, never show a spinner for toggling a setting)
6. **Inline confirmation** — feedback at the point of action, not in a toast corner

---

## Interactive Dashboards Are Programs, Not Posters

When the brief says "interactive dashboard," the failure mode is a single static screen with controls that don't do anything — a screenshot wearing a UI costume. **An interactive dashboard is a small application: real state, multiple distinct views, and filters that actually filter.** If the user can't change what they're looking at and watch the data respond, you haven't built a dashboard — you've built a poster.

**This section is mandatory whenever the request involves a dashboard, admin panel, analytics view, monitoring surface, or "explore this data."** Do not ship a single inert view and call it interactive.

### Plan the Program Before the Pixels (REQUIRED)

Before writing any markup, write down three things. Do not skip to CSS.

1. **The state model** — one object that drives everything. What can the user change?
   ```js
   const state = {
     view: 'overview',          // which view is active
     filters: { … },            // every active filter
     range: [start, end],       // time / value window
     selected: null,            // the focused entity (drives cross-view linking)
     hovered: null,
   };
   ```
   Every interaction is a write to this object; every view is a pure render of it. This is the line between "interactive" and "static."

2. **The views** — name **at least 3 distinct views**, each answering a *different question*. A view is not a re-skin: switching views must **re-shape the data**, not recolor the same chart. If two "views" show the same chart with a new palette, they are one view.

3. **The interactions** — for each filter, what does it filter? For each view switch, what re-renders? When the user selects an entity in one view, what lights up in the others? Write the wiring before you build the chrome.

### Different Views That Offer Something New

Pick 3–5 from this set (or invent peers). The point is *orthogonality* — each reveals a structure the others hide:

| View | Question it answers | Form |
|------|--------------------|------|
| **Overview** | "How are we doing right now?" | KPI cards w/ sparklines + one hero chart |
| **Trend / Timeline** | "How did we get here?" | Time-series, pannable = its own date picker |
| **Breakdown / Composition** | "What's it made of?" | Stacked bars, treemap, donut-with-detail |
| **Comparison** | "How do these stack up?" | Small multiples, ranked bars, diverging |
| **Relationships / Flow** | "What connects to what?" | Sankey, network, matrix, scatter |
| **Detail / Drill-down** | "Tell me everything about *this one*" | Side panel or expanded row — NOT a new page |

Each view gets its own empty, loading, and error state. Switching is a segmented control in the filter bar — instant, no full reload, animate only the content that changed.

### The Single-Line Filter Bar (consolidate, don't stack)

All filters live in **one horizontal row**, not a sidebar and not a stacked panel. Sticky to the top of the content. This is non-negotiable for a clean dashboard.

```
[ View ▸ segmented ]   [ ⌕ search/command ]   [ Range ▾ ]   [ Status ▾ ]   [ +2 ]  ·····  [ Clear ]
└ left: what am I looking at ─────┘  └─ middle: scope it ──────────┘     right: reset ┘
```
- Layout: `display:flex; align-items:center; gap:6px; height:40px`. Controls use the **Controls, Dials & Selectors** anatomy so every height matches exactly.
- Every filter is a **compound control** — it *shows its current value* and opens to change it (a status filter reads "Status: Active", not just "Status"). Display + input in one element.
- Collapse overflow into a `+N` chip that opens the rest in a popover — the bar stays one line at any width.
- An active-filter **count badge** and a **Clear** affordance that appears *only when filters are active*.
- A `Cmd+K` command palette is the power-user path to every filter and view — teacher + tool in one.

### The Single-Line Legend (it's a control, not a caption)

A legend on its own stacked column of color keys is wasted space. Consolidate it into **one inline row**, sitting in the chart's title line, and make it *do* something:

```
Revenue ▦ 1.2M    Costs ▦ 840K    Margin ▦ 31%     ← swatch + label + LIVE value at cursor
        click a series to solo/mute · hover to highlight · value tracks the crosshair
```
- 8px swatch + monospace label + the series' value **at the cursor** — the legend replaces the tooltip-legend entirely (Liveline pattern).
- Click a series to **mute** it (opacity 0.35) or solo it (Alt-click). The legend IS the series toggle — no separate column of checkboxes.
- One line: `display:flex; gap:16px; align-items:center`. Wraps gracefully at narrow widths but never stacks into a box.

### Wire It Like an App
- **Cross-view linking is the soul of a dashboard.** Selecting a bar filters the table; hovering a region highlights the matching line; brushing a range on the overview zooms the detail. One interaction, many views responding — never isolated widgets.
- **Optimistic & instant** — filters apply in <100ms, no spinner for a local re-filter. Re-render only what changed.
- **Persist the view** — reflect `state` in the URL (or memory) so a refresh doesn't reset the user. A specific view should be shareable.
- **Keyboard** — arrow between rows, `Cmd+K` to jump, Esc to clear selection.

### Definition of Done — "Interactive Dashboard"
A static mock **fails** every one of these. Do not present a dashboard until they pass:
- [ ] **≥ 3 distinct views**, switchable live, each re-shaping the data (not re-skinning it)
- [ ] **Every filter actually filters** the rendered data — no decorative dropdowns
- [ ] **≥ 1 cross-view link** (select / brush / hover in one view changes another)
- [ ] **One-line filter bar** — no filter sidebar, no stacked filter panel
- [ ] **One-line legend** that doubles as a series toggle and shows values at the cursor
- [ ] **Every chart** has crosshair / hover / click (the 3-Layer Rule) — zero static charts
- [ ] **No dead ends** — no "click to see more" that goes nowhere; detail opens in a panel, not a void
- [ ] **State is real** — one state object drives render; the view survives a refresh

---

## Soul Philosophy

**1. The 90/10 Novelty Rule.** 90% of an interface should be familiar (Benji's precision, Stripe's density). 10-20% should be novel — the soul. The novel fraction must be **concentrated at key moments**: first impressions, empty states, idle moments, mode transitions. Spread evenly, it's noise. Concentrated at the right moments, it's magic.

**2. Polished ≠ Soulful.** Polish optimizes for function. Soul optimizes for feeling. Stripe is maximum polish, minimum soul. The difference: soul requires taking risks that polish avoids — humor that might not land, sounds that might annoy, imperfections that might look like bugs. Soul is the courage to be specific rather than universally acceptable.

**3. The Three Unfoldings.** Every page, panel, and surface should unfold in layers. Never dump everything at once. Progressive disclosure creates anticipation — the same dopamine loop as unwrapping a gift. A page that shows everything at once is a reference sheet. A page that unfolds is a story.
- **Hook**: What's visible on arrival. Enough to orient, not enough to satisfy. Creates "what else?"
- **Body**: Revealed on scroll, click, or hover. The substance. Answers the hook while raising new questions.
- **Reward**: The detail only the curious find. The interaction easter egg, the extra data point, the hidden flourish.

---

## Spectrum Router (calibrate — hybrid)

Four spectrums place a project's feel. They compose freely — no combination is wrong. **Hybrid rule:** for a *substantial or ambiguous* build (a full page, a dashboard, a multi-component surface, or a vague brief), ask the user where it sits on these 4 spectrums *before* writing code. For a *small, well-specified* task (one component, a tweak), skip the questions and build on the strong defaults. **Default bias: push UP** — when unspecified, default to 15-20% novelty, Layered pacing, Weighted feel, Warm personality. Never default to the lowest settings — that's just Stripe without soul.

### 1. Novelty Budget
```
|--- 10% ---------|--- 15-20% --------|--- 30% ---------|
    Stripe              Rauno              Basement
    One surprise        Surprises at       The whole thing
    per page            key moments        feels experimental
```

### 2. Reveal Pacing
```
|--- Flat ----------|--- Layered --------|--- Cinematic ----|
    Everything           Three Unfoldings     Narrative chapters
    visible on load      Scroll reveals       Earned reveals
    Dashboard            Editorial            Storytelling
```

### 3. Interaction Feel
```
|--- Crisp ---------|--- Weighted --------|--- Tactile ------|
    Instant snaps        Spring settle        Friction, magnetic
    No physics           Momentum, depth      snap, gravity
    Pure Stripe          stack choreography   Aristide Benoist
```

### 4. Personality
```
|--- Neutral -------|--- Warm ------------|--- Playful ------|
    Professional         Serif accents        Sound design
    Zero humor           Warm colors          Easter eggs
    Stripe dashboard     Human touches        Idle rewards, wit
```

### What Each Spectrum Unlocks

**Weighted/Tactile Interaction Feel unlocks:**
- Choreographed depth stack: blur bg → slide content → reveal input → settle
- Spring physics on overlays, modals, panels
- Staggered sibling animations (30ms fish-schooling)
- Differential opacity: interactive = opaque, blurred = non-interactive
- Edge fades via `mask-image` for infinite feel

**Layered/Cinematic Reveal Pacing unlocks:**
- Scroll-triggered IntersectionObserver reveals (one-shot, disconnect after trigger)
- Time-staggered hero sequences (text → 300ms → visual → 600ms → interactive)
- Hover-triggered depth: summary → detail → everything
- Accordion unfolding that feels like opening a drawer, not toggling visibility

**Warm/Playful Personality unlocks:**
- Sound design: subtle, spatial, tied to physical actions. Always respect mute.
- Idle exploration rewards: things that happen when you hover too long or click something unnecessary
- Inline confirmation at point-of-action (not toasts in a corner)
- Empty states with warmth: "This is where your [X] will live" over cold "No data"
- Strategic imperfection: serif punctuation in sans-serif, hand-drawn SVG paths, organic timing variation
- Error pages as soul windows: if your 404 is generic, your product lacks soul

**High Novelty Budget (>15%) unlocks:**
- Typography as hero: numbers at 120px, weight varies with value
- Data-as-art: generative patterns from real values

(The 10-idea ideation always runs regardless of budget — see Creative Ideation. Novelty budget scales the *ambition* of the ideas, not whether they happen.)

---

## Decision Framework

When building a component, ask:

1. **Is this data or prose?** Data = monospace + tight. Prose = sans-serif + generous whitespace.
2. **Is this a tool or marketing?** Tool = dark surfaces + floating controls. Marketing = skewed sections + gradients.
3. **Is this interactive?** Overshoot bounce entry, `scale(0.96)` press on controls/buttons (`scale(0.92)` on larger surfaces), accent glow focus.
4. **Is this alive?** Live data = pulse dots, breathing, lerp-smoothed values, momentum colors.
5. **Is this a surface?** Every surface is `rgba()`. No solid grays. Transparency = depth.
6. **Is this entering or leaving?** Enter = slower + overshoot. Exit = faster + ease-in.
7. **Does this involve canvas?** Use rAF + exponential lerp. Stop when tab hidden. Cap DPR at 3x.
8. **Is this the 90% or the 10%?** Know which. The 90% is reliable and familiar. The 10% is where you invest soul. Don't put soul everywhere — concentrate it.
9. **Does this unfold?** Hook → Body → Reward. If you're showing everything at once, ask why.
10. **Is this a control?** Never native. `appearance: none` and rebuild from the surface stack — four states, accent focus ring, `scale(0.96)` press, live value readout for sliders/dials. (Controls, Dials & Selectors)
11. **Is this a dashboard?** Then it's a program, not a poster: one state object, ≥3 distinct views, filters that actually filter, a one-line filter bar and a one-line legend. (Interactive Dashboards Are Programs)

---

## Anti-Patterns (Never Do)

### Visual
- Solid gray backgrounds — use `rgba()` layers, never hex grays. (Source: Benji's Surface Stack)
- Multiple accent colors competing in one view — one hex derives everything via `color-mix()`. (Source: Agentation color system)
- Pure `#000` in dark mode — use `rgb(10,10,10)`. Pure black causes eye strain and makes colors look neon. (Source: dark mode research)
- Drop shadows without paired 1px border — always pair with `0 0 0 1px`. (Source: Agentation shadow patterns)
- Decorative borders heavier than 1px — borders are whispers, not shouts. (Source: Benji's component patterns)
- Inconsistent border-radius — different radii must signal different semantic roles, not carelessness. (Source: Rauno's [interfaces.rauno.me](https://interfaces.rauno.me))
- Emoji as status indicators — use colored dots, SVG icons, or CSS shapes. (Source: Agentation codebase, zero emoji)
- Screenshots for device mockups — CSS-render them. (Source: Stripe's <1KB CSS device mockups)

### Animation
- `ease-in-out` or `linear` for UI transitions — use the three sacred easings. (Source: Benji's cubic-bezier curves)
- `transition: all` — explicitly list each property. `all` creates surprise animations on future changes. (Source: [Philipp Nowinski](https://dev.to/philipp/dont-use-transition-all))
- Symmetric enter/exit durations — enter ALWAYS slower than exit. (Source: Agentation SCSS, every component)
- Scaling dialogs from 0 → 1 — start from 0.95, not 0. Feels like revealing, not materializing. (Source: Rauno's [interfaces.rauno.me](https://interfaces.rauno.me))
- Excessive press scale (0.8) — use 0.96 for buttons, 0.92 for larger elements. (Source: Rauno's interaction design essay)
- Animating layout properties (`width`, `height`, `top`, `left`) — only `transform` + `opacity`. (Source: GPU compositing fundamentals)
- `setTimeout` for animation sequencing — use CSS `animation-delay` or rAF. (Source: Benji's stagger pattern)
- Runtime motion libraries in shipped components — CSS transitions only. (Source: Agentation, zero runtime animation deps)
- Transitions during theme switch — disable all transitions, re-enable after one frame. (Source: Rauno's [interfaces.rauno.me](https://interfaces.rauno.me))
- Animations on high-frequency, low-novelty actions — right-click menus should open instantly (no motion), list item add/remove should snap, trivial button hovers should be `<150ms`. A 300ms bounce on a tab switched 100x/day becomes a cognitive tax. (Source: Rauno's [novelty essay](https://rauno.me/craft/novelty))

### Interaction
- Native unstyled controls — shipping the OS `<select>` chevron, grey `range` track, default checkbox/radio, or platform date picker. `appearance: none` and rebuild every one from the surface stack. (Source: Controls, Dials & Selectors)
- Sliders or dials with no value readout — every continuous control shows its live value (bubble, readout, or center label). A blind control is a guess. (Source: Controls, Dials & Selectors)
- Animating `left`/`width` on a toggle knob or slider thumb — `transform: translateX()` / `scale()` only. (Source: GPU-first motion)
- Dead zones between clickable list items — move padding inside the `<a>`/`<button>`. Every pixel clickable. (Source: Rauno's [interfaces.rauno.me](https://interfaces.rauno.me))
- Discrete `font-weight` swap on hover — causes layout shift; use opacity/color/background. (Animating the *variable* `wght` axis via `font-variation-settings` is fine — Benji does 450→550 on nav — but pre-reserve the width so metrics don't reflow.) (Source: Rauno's [interfaces.rauno.me](https://interfaces.rauno.me))
- Dropdown triggers on `click` — use `mousedown` for menus, saves ~100ms perceived latency. (Source: Rauno's [interaction design essay](https://rauno.me/craft/interaction-design))
- Hover styles on touch devices — wrap in `@media (hover: hover)`. Touch hover is sticky and broken. (Source: Rauno's [interfaces.rauno.me](https://interfaces.rauno.me))
- Auto-focusing inputs on mobile — forces keyboard, hides half the screen. Check for physical keyboard first. (Source: Rauno's [interfaces.rauno.me](https://interfaces.rauno.me))
- Tooltips on disabled buttons — unreachable for keyboard users. Show the reason inline. (Source: Rauno's [interfaces.rauno.me](https://interfaces.rauno.me))
- Interactive content inside tooltips — use a popover instead. Tooltips are text-only. (Source: Rauno's [interfaces.rauno.me](https://interfaces.rauno.me))
- `outline` for focus rings on radiused surfaces — use `box-shadow: 0 0 0 2px` which respects border-radius (a 2px `:focus-visible` outline is fine for plain text/links with no radius). (Source: Rauno's [interfaces.rauno.me](https://interfaces.rauno.me))

### Information Architecture
- Showing everything at once — use the Three Unfoldings: Hook → Body → Reward. (Source: luxe Soul Philosophy)
- Duplicated information — the same value, label, or unit rendered in two places. One fact, one place; the second instance is clutter that costs the page its impact. (Source: Deduplication)
- Redundant encoding — signaling one state with color AND icon AND text. Keep the quietest channel that reads, drop the rest. (Source: Ambient Information / Deduplication)
- Clutter with no breathing room — >7 competing elements, or dense data with no whitespace around it. Cut until it breaks, then add back one. Impact comes from contrast with space, not from filling it. (Source: Core Philosophy — Let It Breathe)
- Making the user "check" for status — anything that should always be felt (health, liveness, count, freshness) belongs encoded ambiently (tint, pulse, badge), not buried behind a glance or click. (Source: Ambient Information)
- Hiding TOO much behind progressive disclosure — critical info (price, status, errors) must be layer 1. (Source: NN/g progressive disclosure research)
- Inconsistent disclosure patterns — pick a vocabulary (hover = preview, click = expand) and apply it everywhere. (Source: NN/g)
- Data points with no hover state — every number, chart element, and metric needs layer 2 (hover context). (Source: 3-Layer Interaction Rule)
- Static charts — if a chart doesn't respond to mouse interaction, it's a screenshot. Add crosshair, tooltip, or click-to-explore. (Source: Liveline interaction patterns)
- Dashboards that are one static view — an interactive dashboard needs a real state object, ≥3 distinct views, and filters that actually filter. A single screen with inert controls is a poster. (Source: Interactive Dashboards Are Programs)
- "Views" that only recolor the same chart — a real view re-shapes the data to answer a different question (overview vs. breakdown vs. comparison vs. flow), not a new palette on the same shape. (Source: Different Views That Offer Something New)
- Filter sidebars or multi-row filter panels — consolidate every filter into one sticky line; overflow into a `+N` popover. (Source: Single-Line Filter Bar)
- Stacked multi-row legends — one inline legend line that doubles as a series toggle and shows values at the cursor. (Source: Single-Line Legend)
- Decorative controls that don't drive state — every filter, toggle, and dropdown on a dashboard must change what's rendered. A control wired to nothing is a lie. (Source: Interactive Dashboards Are Programs)
- Carousels and auto-rotating sliders — <1% of users click them. Use a grid or single hero. (Source: CXL/NN/g research)
- Scroll hijacking — never override native scroll. Use `IntersectionObserver` for scroll-triggered effects. (Source: NN/g scrolljacking research)

### Flow & Pacing
- Novelty spread evenly — concentrate at key moments (first impressions, empty states, mode transitions). (Source: Rauno's [novelty essay](https://rauno.me/craft/novelty))
- Too many novel interactions at once — introduce one at a time. Arc browser lost users by being too different everywhere. (Source: Rauno's [novelty essay](https://rauno.me/craft/novelty))
- Feedback far from its trigger — show inline confirmation at point-of-action, not toast corners. (Source: Rauno's [interfaces.rauno.me](https://interfaces.rauno.me))
- Empty states that say "No data" — warmth formula: illustration + "This is where your [X] will live" + CTA. (Source: Rauno's [interfaces.rauno.me](https://interfaces.rauno.me))
- Blocking UI on server responses — optimistically update locally, rollback on error. (Source: Rauno's [interfaces.rauno.me](https://interfaces.rauno.me))
- Playing it safe — Stripe's density is a virtue; its blandness is not.

### Voice & Copy
- Jargon, pomposity, and clutter words — "utilize", "in order to", "leverage", "seamless". Plain words; cut the padding. (Source: Voice & Copy)
- Passive voice and verb+noun padding — "a decision was made" / "make a decision" → "decided" / "decide". Strong verbs carry the sentence. (Source: Voice & Copy)
- Vague button and link labels — "Submit", "Click here", "Learn more". Name the action or destination. (Source: Voice & Copy)

### Performance
- React re-renders for 60fps updates — use `ref.current.textContent = val` directly. (Source: Liveline value display pattern)
- Linear lerp without dt normalization — runs 2x fast on 120Hz. Use exponential lerp. (Source: Liveline math/lerp.ts)
- rAF loops running when tab is hidden — stop on `document.hidden`, restart on visibility change. (Source: Liveline engine)
- Uncapped DPR on canvas — `Math.min(devicePixelRatio, 3)`. 4x DPR = 4x GPU work for imperceptible gain. (Source: Liveline dpr.ts)
- `will-change` applied globally — toggle during active animations only, then remove. (Source: Rauno's [interfaces.rauno.me](https://interfaces.rauno.me))

### Accessibility
- Ignoring `prefers-reduced-motion` — users enable this for medical reasons. Mandatory respect. (Source: WCAG 2.3.3)
- Font weights below 400 — poor contrast on most screens, especially at small sizes. (Source: Rauno's [interfaces.rauno.me](https://interfaces.rauno.me))
- Input font below 16px on mobile — iOS auto-zooms the viewport. (Source: Rauno's [interfaces.rauno.me](https://interfaces.rauno.me))
- Removing focus indicators without replacement — `*:focus { outline: none }` is the most common a11y violation. Replace with styled `box-shadow`. (Source: WCAG)
- Missing `aria-label` on icon-only buttons — screen readers announce "button" with zero context. (Source: Rauno's [interfaces.rauno.me](https://interfaces.rauno.me))

---

## Creative Ideation (REQUIRED — always, on every build)

**Before writing any code**, generate 10 creative ideas for the current task — this runs on *every* build, not only high-novelty ones (creativity is the default posture). Scale ambition to the spectrum settings — a Neutral/Crisp/Flat project gets grounded ideas; a Playful/Tactile/Cinematic project gets wild ones — but the 10 ideas always happen. Pull from these creative dimensions:

### The Six Dimensions to Push

1. **Data-as-Art** (Nadieh Bremer school): Can the data itself become the visual? Not a chart with decoration, but data that IS the decoration. Generative patterns from real values. Visualizations that make people *feel* something about the numbers.

2. **Tactile Weight** (Aristide Benoist school): Can interactions have physics? Friction on drag, momentum on release, magnetic snap near targets. Elements that feel like they have mass — hover creates gravitational pull, not just a color change.

3. **Typography as Hero** (Basement Studio school): Can type do the heavy lifting? Numbers at 120px. Overlapping text layers. Type that responds to data — weight varies with value, tracking tightens under pressure, size breathes with volatility.

4. **Spatial/Navigable Data** (Bruno Simon school): Can the user *move through* the data instead of scrolling past it? Depth layers, parallax data planes, zoom-as-navigation, spatial clustering that reveals itself as you explore.

5. **Narrative Pacing** (Immersive Garden school): Can the interface reveal information progressively? Not dumping everything at once but choreographing a discovery sequence. Data that unfolds, sections that earn their appearance.

6. **Interaction Personality** (Rauno/Paco school): Can the micro-interactions have *wit*? A loading state that tells a story. A hover effect that surprises the second time. Sound design. Cursor transformations. Easter eggs in the details.

### How to Generate the 10 Ideas

For the specific UI/feature/page being built, produce exactly 10 ideas as a numbered list:

- **Ideas 1-3**: Grounded but bold. Achievable with CSS + Canvas. Push one dimension.
- **Ideas 4-6**: Ambitious. Might need WebGL or custom shaders. Push two dimensions.
- **Ideas 7-8**: Wild. Would be award-worthy. Push three+ dimensions.
- **Ideas 9-10**: Unreasonable. The kind of idea that makes someone say "wait, you can do that on the web?" Pure creative provocation — may not be buildable today but reframes the problem.

### Format
```
## Creative Ideas for [feature/page name]

1. **[Name]** — [1-2 sentence description]. *Dimensions: [which ones]*
2. ...
...
10. ...

**Recommended**: #[N] because [why it balances ambition with the current constraints]
**Quick win**: #[N] because [achievable in <2 hours but still pushes boundaries]
```

### Examples of What "Pushing the Envelope" Means

- Instead of a line chart: a **force-directed particle field** where each data point is a dot that clusters by value, and the shape of the cluster IS the trend
- Instead of a loading spinner: a **generative landscape** that builds itself from the data being fetched, so by the time loading completes, you've already been watching the answer form
- Instead of a tooltip on hover: **spatial audio panning** — values on the left play in the left ear, values on the right in the right, pitch maps to magnitude
- Instead of a sidebar nav: **a minimap** of the entire data surface, like a game's world map, where you click regions to teleport
- Instead of color-coding status: **typography that degrades** — healthy systems render in crisp Inter, degraded systems render in increasingly distorted/glitched letterforms
- Instead of a static table: **a swimming pool of data** — rows float with buoyancy proportional to their importance, most relevant bobs to the surface

---

## Quality Gate (AFTER Writing Code)

After writing or reviewing any code, run this checklist. **Do not present work to the user until every applicable item passes.** For each violation, fix it or flag it with the specific value that should be used.

### Visual Precision
- [ ] Every `background` uses `rgba()` or `color-mix()`, never solid hex grays
- [ ] Every `border-radius` matches the philosophy: 50% circles, 16px panels, 8px inputs, 4px overlays
- [ ] Every `box-shadow` on a panel has the paired 1px border trick (`0 0 0 1px`)
- [ ] Colors derive from one accent via `color-mix()` at specific percentages (4%, 12%, 18%, 25%, 50%)
- [ ] Font stack uses `--font-data` for numbers/values, `--font-body` for prose — never mixed
- [ ] `font-feature-settings: 'tnum' 1` on any element displaying numbers
- [ ] Antialiased rendering declared
- [ ] `::selection` is styled — never the default OS highlight
- [ ] Elevated surfaces use a layered shadow + 1px ring; modals/overlays use the graduated 7-layer stack (+ frosted `backdrop-filter` behind them)
- [ ] Serif (`--font-serif`) reserved for titles and `<em>` emphasis only; a script face never used as a second body font

### Animation Precision
- [ ] Every enter animation uses overshoot or expo-out easing — never `ease`, `ease-in-out`, or `linear`
- [ ] Every enter/exit pair has asymmetric timing (enter slower than exit)
- [ ] Press feedback on every interactive element at 100ms: `scale(0.96)` on controls/buttons, `scale(0.92)` on larger surfaces (cards, panels, markers)
- [ ] Only `transform` and `opacity` are animated — no layout properties
- [ ] Staggered elements use 20-30ms delays with correct direction (enter: first-to-last, exit: last-to-first)
- [ ] `prefers-reduced-motion` respected
- [ ] Exits and collapses use `--ease-exit` (0.32, 0.72, 0, 1), not an entrance curve played in reverse

### Interaction Quality
- [ ] Hover states exist on every interactive element
- [ ] Hover states use `rgba()` backgrounds, not color swaps
- [ ] Hover states wrapped in `@media (hover: hover)` — invisible on touch devices
- [ ] No dead zones between clickable list items — padding inside the `<a>`/`<button>`, not between them
- [ ] Focus visible via `box-shadow` ring, not `outline`
- [ ] Theme toggle disables transitions during switch
- [ ] Inputs use appropriate `type` (`email`, `password`, `url`, `tel`, `number`)
- [ ] Inputs disable `spellcheck` and `autocomplete` where appropriate
- [ ] Inputs use `required` attribute for HTML-native validation
- [ ] Input icons/decorations are `position: absolute` on top of the input with padding, not adjacent — and trigger focus on click
- [ ] Toggles take effect immediately — no confirmation dialog
- [ ] Buttons disabled after form submission to prevent duplicate requests
- [ ] Frequent low-novelty actions have zero animation: right-click menus open instantly, list item add/remove snaps, trivial button hovers are `<150ms`
- [ ] Looping animations pause when scrolled offscreen (IntersectionObserver or `document.hidden`)

### Controls & Inputs
- [ ] No native controls — `appearance: none` on every `<select>`, `range`, checkbox, radio, date input, rebuilt from the surface stack
- [ ] Every control has all four states (rest/hover/focus/active) + disabled, and a `box-shadow` focus ring (not `outline`)
- [ ] Control heights share one rhythm per surface (28 / 34 / 40px) — no mismatched heights in a control bar
- [ ] Sliders and dials show their live value (bubble, readout, or center label) — no blind controls
- [ ] State changes cause no layout shift — no bold-on-hover, no width growth; pre-reserve the space
- [ ] Toggles/selects take effect immediately and optimistically — no confirm dialog, no spinner for a local change

### Cohesion & Flow (The Designer Lens)
Think like someone arriving for the first time, not someone who wrote the code:
- [ ] **First 2 seconds** — What does the eye land on first? Is it the right thing? Is there a clear visual hierarchy or is everything competing for attention?
- [ ] **Jarring transitions** — Walk through every state change (page load → idle, hover → click, empty → loaded, light → dark). Does each transition feel like it was designed by the same person? Flag any that feel like they belong to a different product.
- [ ] **Rhythm** — Is there a consistent tempo? Fast micro-interactions + slow scroll reveals = good rhythm. Everything at the same speed = monotone. Everything different = chaos. Name the tempo you're going for.
- [ ] **Emotional arc** — The page should have a shape: arrival (orient), exploration (engage), depth (reward). If it's flat — every section at the same intensity — propose where to add peaks and valleys.
- [ ] **Cohesive voice** — Do the colors, typography, spacing, animation speed, and border-radius all feel like they come from one system? Or does the header feel like one site and the content area feel like another? A serif quote mark in a sans-serif page is intentional warmth. A different border-radius on every card is sloppiness. Know the difference.
- [ ] **What's missing?** — Actively look for gaps: the hover that doesn't exist, the loading state nobody designed, the empty state that says "No data" instead of something human, the transition that snaps instead of flows.

### Interaction Density
- [ ] Every data point has all 3 layers: visible insight (glance), hover context (tooltip/popover), click exploration (drill-down/detail)
- [ ] Every chart/graph responds to mouse interaction — crosshair, tooltip, or click-to-explore. No static charts.
- [ ] Controls carry multiple semantic loads where possible (status + action, display + input, navigation + data)
- [ ] Is there a separate progress indicator that could be embedded into the primary action?
- [ ] Are there adjacent controls that could merge into a compound control?
- [ ] Hero section earns attention: bold claim + impressive visual, Show → Tell → Do flow
- [ ] Page follows DENSE → BREATHE → DENSE → BREATHE → EXHALE pacing rhythm

### Information Hygiene (Ambient · Dedup · Breathe)
- [ ] **Ambient where possible** — status, liveness, trend, freshness, and counts are encoded into existing elements (tint, pulse, background sparkline, badge), not added as separate labels the user must read
- [ ] **Deduplicated** — ran the dedup scan; no value, label, unit, or control appears twice; every element carries information nothing else does
- [ ] **Single encoding per fact** — no color + icon + text all saying the same thing; the quietest channel that reads wins
- [ ] **Breathing room** — is there anything that could be removed without losing meaning? If yes, remove it — then leave the space you won, don't refill it
- [ ] **One creative move per surface** — at least one specific, memorable, non-generic choice (ties to Soul Check). If a generic AI could have made it, push further

### Voice & Copy
- [ ] Buttons, links, and headings name the action or thing plainly — no "Submit", "Click here", "Learn more", no jargon or pomposity
- [ ] Copy is stripped — no clutter words ("in order to", "utilize", "at this time"); active voice; strong verbs; one idea per line
- [ ] Empty states, errors, and tooltips read as human, not system-speak — "No data" is banned; say what goes here and how to start
- [ ] Microcopy is deduplicated — label, helper, and placeholder don't restate each other; one line carries the most meaning

### Dashboard = Program (when building any dashboard / analytics surface)
- [ ] A single state object drives every view; interactions write to it, views render from it
- [ ] ≥ 3 distinct views, switchable live, each re-shaping the data (not recoloring one chart)
- [ ] Every filter actually filters the rendered data; ≥ 1 cross-view link (select / brush / hover propagates)
- [ ] Filters consolidated into one sticky single-line bar; overflow into a `+N` popover (no sidebar)
- [ ] Legend is one inline line that toggles series and shows values at the cursor
- [ ] No static charts (3-Layer Rule) and no dead-end "click to see more"; the view persists across refresh

### Soul Check (per spectrum settings)
- [ ] **Where is the 10-20%?** Identify which element(s) carry the novelty budget. If nothing does, add one.
- [ ] **Does this unfold?** If the section shows everything at once, propose a Hook → Body → Reward structure.
- [ ] **Would someone notice this was handcrafted?** If the code could have been written by any generic AI, it's not good enough. What makes this distinctly luxe — the one specific, memorable choice a human with taste would make?

### When Reviewing or Designing — Output Format
Always include these two sections in your response when this skill is active:

**Design Notes** (before or alongside code):
- What the user sees first and why
- Where the soul lives (the 10-20%)
- Any flow concerns: jarring transitions, missing states, rhythm breaks
- What you'd push further if time allowed

**Audit Callouts** (after code):
Quote specific lines against specific skill sections. Example:
> `background: #333` — violates Surface Stack. Should be `rgba(255,255,255,0.05)` for dark mode surface-3.
> `transition: all 0.3s ease` — violates Three Sacred Easings + GPU-first. Should be `transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.2s cubic-bezier(0.34, 1.56, 0.64, 1)`.
> No hover state on `.card` — violates Interaction Quality. Add `&:hover { background: var(--accent-subtle) }`.
> Empty state just says "No results" — violates Soul Check. Propose warmth: illustration + "Nothing here yet — try adjusting your filters."
