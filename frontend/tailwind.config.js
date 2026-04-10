/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: "1rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        borderStrong: "hsl(var(--sf-border-strong))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        panel: {
          DEFAULT: "hsl(var(--sf-panel))",
          foreground: "hsl(var(--sf-panel-foreground))",
        },
        accent: {
          cyan: "hsl(var(--sf-accent-cyan))",
          amber: "hsl(var(--sf-accent-amber))",
        },
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        panel: "var(--sf-radius-panel)",
      },
      boxShadow: {
        soft: "0 1px 2px 0 rgb(2 6 23 / 0.2), 0 8px 24px -12px rgb(2 6 23 / 0.4)",
        glow: "0 0 0 1px hsl(var(--sf-accent-cyan) / 0.25), 0 0 28px hsl(var(--sf-accent-cyan) / 0.14)",
        panel: "inset 0 1px 0 hsl(var(--sf-accent-cyan) / 0.12), 0 10px 32px -18px rgb(2 6 23 / 0.9)",
      },
      fontFamily: {
        sans: [
          "var(--font-sf-sans)",
          "Sora",
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "\"Segoe UI\"",
          "sans-serif",
        ],
        display: [
          "var(--font-sf-display)",
          "Exo 2",
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "\"Segoe UI\"",
          "sans-serif",
        ],
        mono: [
          "var(--font-sf-mono)",
          "Space Mono",
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
      },
      letterSpacing: {
        hud: "0.08em",
      },
    },
  },
  plugins: [],
};

