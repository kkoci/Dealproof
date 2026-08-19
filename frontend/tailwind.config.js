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
      },
      // Type scale — see the v4 design plan. Two roles (Inter for display/body, JetBrains Mono for
      // data), differentiated by size/weight, not a third face. `hero` is the one size reserved for
      // the gap-percentage/balance-meter reading — the product's actual mechanic gets the biggest
      // number on the page, not a generic page title.
      fontSize: {
        hero: ['2.5rem', { lineHeight: '1.05', letterSpacing: '-0.01em', fontWeight: '600' }],
        'hero-sm': ['2rem', { lineHeight: '1.05', letterSpacing: '-0.01em', fontWeight: '600' }],
        'data-label': ['0.6875rem', { lineHeight: '1.3', letterSpacing: '0.06em', fontWeight: '500' }],
        'data-value': ['0.8125rem', { lineHeight: '1.3', letterSpacing: '-0.01em', fontWeight: '500' }],
        micro: ['0.6875rem', { lineHeight: '1.3', letterSpacing: '0.02em', fontWeight: '400' }],
      },
      // Elevation — a real 2-step scale (card / elevated) replacing the single inline boxShadow
      // string previously copy-pasted on every card, plus one ceremonial treatment (`seal`) reserved
      // for the attestation/proof block, the one place this system allows itself to feel heavier
      // than its calm baseline. All ink-tinted (rgba on the text-primary hue), not neutral black.
      boxShadow: {
        card: '0 0 0 1px rgba(19,31,27,0.04), 0 1px 3px rgba(19,31,27,0.06)',
        elevated: '0 0 0 1px rgba(19,31,27,0.05), 0 4px 16px rgba(19,31,27,0.08), 0 12px 32px rgba(19,31,27,0.06)',
        seal: '0 0 0 1px rgba(19,31,27,0.06), inset 0 1px 0 rgba(255,255,255,0.6), inset 0 -1px 0 rgba(19,31,27,0.04), 0 6px 20px rgba(19,31,27,0.07)',
      },
      animation: {
        'pulse-slow': 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'blink': 'blink 1s step-end infinite',
        // luxe SKILL.md "Motion Restraint" — one entrance keyframe, reused everywhere a
        // panel/notice mounts (rise-in only; there is no matching exit, see docs/design/luxe audit notes).
        'rise-in': 'riseIn 300ms cubic-bezier(0.22, 1, 0.36, 1) both',
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
      }
    },
  },
  plugins: [],
}
