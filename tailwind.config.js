/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html", // Diz ao Tailwind para olhar seus arquivos HTML
    "./static/js/**/*.js"    // E também seus arquivos JavaScript
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}