/** @type {import('tailwindcss').Config} */
module.exports = {
    darkMode: "class",
    content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
    theme: {
        container: {
            center: true,
            padding: { DEFAULT: "1rem", sm: "1.5rem", lg: "2rem" },
        },
        extend: {
            colors: {
                neutral: {
                    graphite: "#0F172A",
                    light: "#F5F5F5",
                },
                accent: {
                    primary: "#0EA5A0",
                    dark: "#047857",
                    warm: "#F59E0B",
                },
            },
            fontFamily: {
                // merged here so nothing gets overwritten
                display: ["Inter", "ui-sans-serif", "system-ui"],
                body: ["DM Sans", "ui-sans-serif", "system-ui"],
                sans: ["Inter", "ui-sans-serif", "system-ui"],
            },
            fontSize: {
                xs: ["0.75rem", { lineHeight: "1rem" }],
                sm: ["0.875rem", { lineHeight: "1.25rem" }],
                base: ["1rem", { lineHeight: "1.6" }],
                lg: ["1.125rem", { lineHeight: "1.75" }],
                xl: ["1.25rem", { lineHeight: "1.75" }],
                "2xl": ["1.5rem", { lineHeight: "1.8" }],
                "3xl": ["1.875rem", { lineHeight: "1.2" }],
                "4xl": ["2.25rem", { lineHeight: "1.1" }],
                "5xl": ["3rem", { lineHeight: "1" }],
                "6xl": ["3.75rem", { lineHeight: "1" }],
            },
            borderRadius: { xl: "1rem" },
            boxShadow: { soft: "0 10px 30px rgba(16,24,40,0.06)" },
            keyframes: {
                "pulse-slow": {
                    "0%, 100%": { opacity: "1", transform: "scale(1)" },
                    "50%": { opacity: "0.85", transform: "scale(1.05)" },
                },
            },
            animation: { "pulse-slow": "pulse-slow 3s ease-in-out infinite" },
        },
    },
    plugins: [],
};
