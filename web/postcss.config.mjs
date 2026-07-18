/** Tailwind v4's Next.js integration — a PostCSS plugin, not the Vite
 * plugin the `dashmint_ai-trang` prototype uses (that's Vite-only). This
 * is the standard Tailwind v4 + Next.js wiring. */
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
