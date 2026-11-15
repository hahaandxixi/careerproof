import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/app/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          ink: "var(--ink-primary)",
          secondary: "var(--ink-secondary)",
          primary: "var(--brand-primary)",
          hover: "var(--brand-hover)",
          surface: "rgb(var(--brand-surface-rgb) / <alpha-value>)",
          line: "var(--ink-line)",
          border: "var(--brand-border)",
          halo: "var(--brand-halo)",
        },
      },
    },
  },
  plugins: [],
};

export default config;
