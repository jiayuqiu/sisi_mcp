import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: "rgb(var(--canvas) / <alpha-value>)",
        panel: "rgb(var(--panel) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        divider: "rgb(var(--divider) / <alpha-value>)",
        outline: {
          DEFAULT: "rgb(var(--outline) / <alpha-value>)",
          strong: "rgb(var(--outline-strong) / <alpha-value>)",
        },
        fg: {
          DEFAULT: "rgb(var(--fg) / <alpha-value>)",
          strong: "rgb(var(--fg-strong) / <alpha-value>)",
          subtle: "rgb(var(--fg-subtle) / <alpha-value>)",
          secondary: "rgb(var(--fg-secondary) / <alpha-value>)",
          muted: "rgb(var(--fg-muted) / <alpha-value>)",
          quiet: "rgb(var(--fg-quiet) / <alpha-value>)",
        },
        teal: {
          400: "rgb(var(--teal-400) / <alpha-value>)",
          500: "rgb(var(--teal-500) / <alpha-value>)",
        },
        "brand-emphasis": "rgb(var(--brand-emphasis) / <alpha-value>)",
        accent: "rgb(var(--accent) / <alpha-value>)",
        warning: "rgb(var(--warning) / <alpha-value>)",
        danger: "rgb(var(--danger) / <alpha-value>)",
        info: "rgb(var(--info) / <alpha-value>)",
        "chart-duration": "rgb(var(--chart-duration) / <alpha-value>)",
        overlay: "rgb(var(--shadow-overlay))",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      animation: {
        "fade-in": "fadeIn 0.3s ease-in-out",
        "slide-up": "slideUp 0.3s ease-out",
        "typing": "typing 1.2s steps(3) infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { transform: "translateY(10px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
        typing: {
          "0%, 100%": { content: "'●'" },
          "33%": { content: "'●●'" },
          "66%": { content: "'●●●'" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
