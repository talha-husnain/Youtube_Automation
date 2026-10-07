/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Shortkaar: every colour follows the active theme (tokens.css);
        // color-mix keeps Tailwind alpha modifiers like bg-brass/10 working.
        paper: "color-mix(in oklab, var(--color-paper) calc(<alpha-value> * 100%), transparent)",
        paper2: "color-mix(in oklab, var(--color-paper-2) calc(<alpha-value> * 100%), transparent)",
        paper3: "color-mix(in oklab, var(--color-paper-3) calc(<alpha-value> * 100%), transparent)",
        ink: "color-mix(in oklab, var(--color-ink) calc(<alpha-value> * 100%), transparent)",
        ink2: "color-mix(in oklab, var(--color-ink-2) calc(<alpha-value> * 100%), transparent)",
        muted: "color-mix(in oklab, var(--color-muted) calc(<alpha-value> * 100%), transparent)",
        brass: "color-mix(in oklab, var(--color-accent) calc(<alpha-value> * 100%), transparent)",
        brassink: "color-mix(in oklab, var(--color-accent-ink) calc(<alpha-value> * 100%), transparent)",
        coral: "color-mix(in oklab, var(--color-accent-2) calc(<alpha-value> * 100%), transparent)",
        ok: "color-mix(in oklab, var(--color-ok) calc(<alpha-value> * 100%), transparent)",
        warn: "color-mix(in oklab, var(--color-warn) calc(<alpha-value> * 100%), transparent)",
        danger: "color-mix(in oklab, var(--color-danger) calc(<alpha-value> * 100%), transparent)",
        // legacy aliases so untouched files degrade gracefully
        background: "color-mix(in oklab, var(--color-paper) calc(<alpha-value> * 100%), transparent)",
        surface: "color-mix(in oklab, var(--color-paper-2) calc(<alpha-value> * 100%), transparent)",
        primary: "color-mix(in oklab, var(--color-accent) calc(<alpha-value> * 100%), transparent)",
        accent: "color-mix(in oklab, var(--color-accent-2) calc(<alpha-value> * 100%), transparent)",
      },
      fontFamily: {
        display: "var(--font-display)",
        body: "var(--font-body)",
        sans: "var(--font-body)",
        serif: "var(--font-display)",
        mono: "var(--font-mono)",
      },
      borderColor: {
        rule: "var(--color-rule)",
        rule2: "var(--color-rule-2)",
      },
      borderRadius: {
        card: "var(--radius-card)",
        input: "var(--radius-input)",
      },
      fontSize: {
        micro: ["10.5px", { letterSpacing: "0.10em" }],
      },
      transitionTimingFunction: {
        out: "var(--ease-out)",
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade': 'fadeIn 0.4s var(--ease-out)',
        // mobile shell: the nav drawer flies in from the edge, sheets rise
        'slide-in-left': 'slideInLeft 0.24s var(--ease-out)',
        'sheet-up': 'sheetUp 0.26s var(--ease-out)',
      },
      keyframes: {
        fadeIn: {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        slideInLeft: {
          from: { transform: 'translateX(-100%)' },
          to: { transform: 'translateX(0)' },
        },
        sheetUp: {
          from: { transform: 'translateY(12px)', opacity: '0' },
          to: { transform: 'translateY(0)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
