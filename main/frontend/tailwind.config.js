/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: { extend: { colors: { ink: '#0b0b12', violet: '#9483ff', accent: '#7c6cf5', surface: { DEFAULT: '#11111a', glass: 'rgba(255,255,255,.05)' } }, fontFamily: { display: ['Sora', 'sans-serif'], sans: ['Inter', 'sans-serif'] } } },
  plugins: [],
};
