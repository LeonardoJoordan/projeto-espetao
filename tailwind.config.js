/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./templates/**/*.jinja",
    "./templates/**/*.jinja2",
    "./static/js/**/*.js",
    "./**/*.py" // se classes Tailwind são montadas no Python
  ],
  safelist: [
    'lg:static',
    'lg:translate-x-0',
    'transform',
    '-translate-x-full',
    {
      pattern: /lg:grid-cols-\[18rem,1fr\]/,
    },
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        poppins: ['Poppins', 'sans-serif'],
        roboto: ['Roboto', 'sans-serif'],
      },
    },
  },
  plugins: [],
}