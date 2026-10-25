/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "#1B4332", 50: "#EEF5F1", 100: "#D8E9DF", 600: "#2D6A4F", 700: "#1F5A40", 800: "#1B4332", 900: "#11291F" },
        accent: { DEFAULT: "#D97706", 50: "#FEF6E7", 100: "#FDE8C4", 600: "#D97706", 700: "#B45309" },
        canvas: "#F7F5F0",
        ink: { DEFAULT: "#1C1F1D", muted: "#5C6660", faint: "#8A938D" },
        line: "#E3DFD5",
        sev: { critical: "#B42318", high: "#C2410C", medium: "#A16207", low: "#4B5563", good: "#15803D" },
      },
      fontFamily: { sans: ["Inter", "system-ui", "Segoe UI", "sans-serif"] },
      boxShadow: { card: "0 1px 2px rgba(16,24,20,.06), 0 1px 3px rgba(16,24,20,.04)" },
    },
  },
  plugins: [],
};
