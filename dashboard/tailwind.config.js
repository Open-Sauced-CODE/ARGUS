/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        mist: '#E9EEEC',
        paper: '#F9FAF8',
        ink: {
          DEFAULT: '#0F2428',
          muted: '#4A6266',
          faint: '#879B9E',
          border: '#D3DDD9',
        },
        peacock: {
          DEFAULT: '#0A2E33',
          hover: '#0E3B42',
          light: '#13474F',
          dark: '#061D20',
        },
        contour: '#1B5058',
        brass: {
          DEFAULT: '#B58A3C',
          glow: 'rgba(181, 138, 60, 0.35)',
        },
        verdigris: '#2E9C82',
        forest: '#1E7A65',
        saffron: {
          DEFAULT: '#E2992A',
          dark: '#B87616',
        },
        garnet: '#BE3144',
        terracotta: '#BE3144',
        copper: '#B56328',
        lapis: '#4C6EA8',
      },
      fontFamily: {
        headline: ['Newsreader', 'serif'],
        sans: ['"Hanken Grotesk"', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'monospace'],
      },
      borderRadius: {
        panel: '20px',
        control: '8px',
      },
      boxShadow: {
        soft: '0 4px 20px -2px rgba(15, 36, 40, 0.06), 0 2px 6px -1px rgba(15, 36, 40, 0.04)',
        brass: '0 0 16px rgba(181, 138, 60, 0.45)',
      },
    },
  },
  plugins: [],
}

