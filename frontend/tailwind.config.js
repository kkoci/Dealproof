/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Offer Check colour system v4 — "Ledger & Instrument" (src/styles/tokens.css). All values
        // are CSS custom properties; key names are unchanged from v3 so every existing className in
        // this vertical keeps resolving — only the underlying hexes moved. Light mode only, no dark
        // variant (a deliberate product decision, not an oversight — see tokens.css header comment).
        bg: {
          primary: 'var(--color-bg-primary)',
          surface: 'var(--color-bg-surface)',
          elevated: 'var(--color-bg-elevated)',
          input: 'var(--color-bg-input)',
        },
        ink: {
          primary: 'var(--color-text-primary)',
          secondary: 'var(--color-text-secondary)',
          muted: 'var(--color-text-muted)',
          inverse: 'var(--color-text-inverse)',
        },
        border: {
          DEFAULT: 'var(--color-border-default)',
          strong: 'var(--color-border-strong)',
          accent: 'var(--color-border-accent)',
        },
        teal: {
          DEFAULT: 'var(--color-teal)',
          hover: 'var(--color-teal-hover)',
          subtle: 'var(--color-teal-subtle)',
          border: 'var(--color-teal-border)',
          text: 'var(--color-teal-text)',
        },
        sealed: {
          DEFAULT: 'var(--color-sealed)',
          hover: 'var(--color-sealed-hover)',
          subtle: 'var(--color-sealed-subtle)',
          border: 'var(--color-sealed-border)',
          text: 'var(--color-sealed-text)',
          icon: 'var(--color-sealed-icon)',
        },
        success: {
          DEFAULT: 'var(--color-success)',
          hover: 'var(--color-success-hover)',
          subtle: 'var(--color-success-subtle)',
          text: 'var(--color-success-text)',
        },
        danger: {
          DEFAULT: 'var(--color-danger)',
          hover: 'var(--color-danger-hover)',
          subtle: 'var(--color-danger-subtle)',
          text: 'var(--color-danger-text)',
        },
        gap: {
          large: 'var(--color-gap-large)',
          closing: 'var(--color-gap-closing)',
          zero: 'var(--color-gap-zero)',
        },
        neutral: {
          DEFAULT: 'var(--color-neutral)',
          hover: 'var(--color-neutral-hover)',
          subtle: 'var(--color-neutral-subtle)',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
        // v5 "The Enclave" — a genuinely characterful display face (Space Grotesk: engineered,
        // slightly mechanical letterforms) for headings only, applied via `font-display`. Body
        // copy stays on Inter for pure legibility at paragraph sizes — a distinctive voice on
        // every word would fight the "still a tool people use for real decisions" constraint.
        display: ['"Space Grotesk"', 'Inter', 'system-ui', 'sans-serif'],
      },
      // Type scale — `hero` is the one size reserved for the gap-percentage/gauge reading — the
      // product's actual mechanic gets the biggest number on the page, not a generic page title.
      fontSize: {
        hero: ['2.75rem', { lineHeight: '1.02', letterSpacing: '-0.015em', fontWeight: '600' }],
        'hero-sm': ['2rem', { lineHeight: '1.05', letterSpacing: '-0.01em', fontWeight: '600' }],
        'data-label': ['0.6875rem', { lineHeight: '1.3', letterSpacing: '0.08em', fontWeight: '500' }],
        'data-value': ['0.8125rem', { lineHeight: '1.3', letterSpacing: '-0.01em', fontWeight: '500' }],
        micro: ['0.6875rem', { lineHeight: '1.3', letterSpacing: '0.02em', fontWeight: '400' }],
      },
      // Elevation, redone for a dark surface stack — a black drop-shadow is invisible on a
      // near-black page, so depth here comes from a faint light inset (top edge catching light)
      // plus, at the two higher tiers, an actual glow in the accent colour — the instrument-panel
      // register this whole direction is built on. `seal` is the ceremonial exception, reserved
      // for the attestation/proof moment.
      boxShadow: {
        card: '0 0 0 1px rgba(255,255,255,0.05), inset 0 1px 0 rgba(255,255,255,0.03)',
        elevated: '0 0 0 1px rgba(217,140,61,0.28), 0 0 0 1px rgba(255,255,255,0.03) inset, 0 12px 32px rgba(0,0,0,0.5), 0 0 28px rgba(217,140,61,0.07)',
        seal: '0 0 0 1px rgba(217,140,61,0.45), inset 0 1px 0 rgba(255,255,255,0.08), 0 0 48px rgba(217,140,61,0.22)',
        gauge: '0 0 32px rgba(63,220,196,0.18)',
      },
      animation: {
        'pulse-slow': 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'blink': 'blink 1s step-end infinite',
        // luxe SKILL.md "Motion Restraint" — one entrance keyframe, reused everywhere a
        // panel/notice mounts (rise-in only; there is no matching exit, see docs/design/luxe audit notes).
        'rise-in': 'riseIn 300ms cubic-bezier(0.22, 1, 0.36, 1) both',
        // The proof-reveal signature moment only — a seal going from dormant to lit. One-shot,
        // never repeats, and — like every animation in this file — inert under prefers-reduced-motion
        // via the global media query in index.css (durations collapse to 0.01ms).
        'seal-ignite': 'sealIgnite 700ms cubic-bezier(0.22, 1, 0.36, 1) both',
      },
      keyframes: {
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0' },
        },
        riseIn: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        sealIgnite: {
          '0%': { opacity: '0', transform: 'scale(0.90)', filter: 'brightness(0.5) saturate(0.6)' },
          '60%': { opacity: '1', transform: 'scale(1.03)', filter: 'brightness(1.15) saturate(1.1)' },
          '100%': { opacity: '1', transform: 'scale(1)', filter: 'brightness(1) saturate(1)' },
        },
      }
    },
  },
  plugins: [],
}
