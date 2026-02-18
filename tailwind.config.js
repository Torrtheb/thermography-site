/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./**/templates/**/*.html",
    "./**/*.py",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#f0f7f8",
          100: "#d6eaed",
          200: "#add5db",
          300: "#7fbac4",
          400: "#5a9faa",
          500: "#458a95",
          600: "#3b7a84",
          700: "#33656d",
          800: "#2b5259",
          900: "#243f45",
        },
      },
    },
  },
  plugins: [
    require("@tailwindcss/typography"),
    require("@tailwindcss/line-clamp"),
  ],
};
