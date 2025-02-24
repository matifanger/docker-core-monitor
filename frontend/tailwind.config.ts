/** @type {import('tailwindcss').Config} */
export default {
  content: ["./src/**/*.{svelte,js,ts}"],
  theme: {
    extend: {
      fontFamily: {
        mono: ["Fira Code", "monospace"],
        display: ["Orbitron", "sans-serif"],
      },
      colors: {
        cyan: {
          400: "#00ffcc",
          500: "#00e6b8",
        },
        purple: {
          500: "#a855f7",
        },
      },
    },
  },
  plugins: [],
};