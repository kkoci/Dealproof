/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Offer Check colour system v3 (offercheck_colour_system_v3.md) — all values are CSS
        // custom properties from src/styles/tokens.css, derived from the two logo anchors
        // (teal #0D9488, navy #0F172A). Light mode only, no dark variant.
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
