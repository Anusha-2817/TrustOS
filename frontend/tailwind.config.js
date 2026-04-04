import tailwindcssAnimate from "tailwindcss-animate";

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', "system-ui", "sans-serif"],
        display: ["Fraunces", "Georgia", "serif"],
      },
      boxShadow: {
        trust:
          "0 1px 2px rgb(15 23 42 / 0.04), 0 4px 24px -4px rgb(15 118 110 / 0.08), 0 12px 48px -12px rgb(15 23 42 / 0.06)",
        "trust-card":
          "0 1px 3px rgb(15 23 42 / 0.06), 0 8px 32px -8px rgb(13 148 136 / 0.12)",
        "trust-soft":
          "0 1px 2px rgb(15 23 42 / 0.04), 0 0 0 1px rgb(45 212 191 / 0.05), 0 12px 40px -16px rgb(13 148 136 / 0.1)",
      },
      backgroundImage: {
        "gradient-trust-mist":
          "linear-gradient(145deg, rgb(255,255,255) 0%, rgb(240,253,250) 48%, rgb(236,253,245) 100%)",
        "gradient-trust-dusk":
          "linear-gradient(165deg, hsl(210 48% 99%) 0%, hsl(195 40% 96.5%) 45%, hsl(185 38% 94%) 100%)",
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [tailwindcssAnimate],
};
