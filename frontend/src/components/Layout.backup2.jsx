// Layout.backup2.jsx
// This backup file is a copy of the current Layout.jsx state (Reference #2)
// Please use this file as a backup if you need to revert to the current stage.

import React, { useState, useEffect } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import OccuCalcLogo from "../assets/occucalc-logo.png";

/**
 * Brand constants (tweak to taste)
 */
const BRAND = {
    name: "GenFabTools",
    accent: "from-teal-400 via-cyan-400 to-blue-500",
    text: "text-slate-900 dark:text-slate-100",
    subtext: "text-slate-600 dark:text-slate-400",
};

const BRANDS = {
    genfab: {
        name: "GenFabTools",
        logo: "https://via.placeholder.com/32",
        homeHref: "/",
    },
    occucalc: {
        name: "OccuCalc",
        logo: OccuCalcLogo,
        homeHref: "/occucalc",
    },
};

function useBrand() {
    const location = useLocation();
    return location.pathname.startsWith("/occucalc") ? BRANDS.occucalc : BRANDS.genfab;
}

function Header({ scrolled, onToggleTheme, theme, currentBrand, onToggleMenu }) {
    const linkClass =
        "text-sm font-medium transition-colors hover:text-slate-900 dark:hover:text-slate-100";
    const inactive = "text-slate-600 dark:text-slate-300";
    const active = "text-slate-900 dark:text-slate-50 underline underline-offset-8 decoration-2";

    return (
        <header
            className={`fixed inset-x-0 top-0 z-50 transition-all ${scrolled
                ? "backdrop-blur bg-white/70 dark:bg-slate-900/60 border-b border-slate-200/60 dark:border-slate-700/60"
                : "bg-transparent"
                }`}
        >
            <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
                <Link to="/" aria-label={currentBrand} className="flex items-center gap-3">
                    {/* Logo image */}
                    <img src="https://via.placeholder.com/32" alt="GenFab Tools" className="h-8 w-8 object-contain" />
                    <span className="font-semibold tracking-tight text-slate-900 dark:text-slate-100">
                        {currentBrand}
                    </span>
                </Link>

                <nav className="hidden md:flex items-center gap-8">
                    <NavLink
                        to="/"
                        className={({ isActive }) => `${linkClass} ${isActive ? active : inactive}`}
                        end
                    >
                        Home
                    </NavLink>
                    <NavLink
                        to="/occucalc"
                        className={({ isActive }) => `${linkClass} ${isActive ? active : inactive}`}
                    >
                        OccuCalc
                    </NavLink>
                    <NavLink
                        to="/tools"
                        className={({ isActive }) => `${linkClass} ${isActive ? active : inactive}`}
                    >
                        Tools
                    </NavLink>
                    <NavLink
                        to="/about"
                        className={({ isActive }) => `${linkClass} ${isActive ? active : inactive}`}
                    >
                        About
                    </NavLink>

                    {/* Theme toggle - minimal icon button */}
                    <button
                        onClick={onToggleTheme}
                        aria-label="Toggle theme"
                        className="rounded-full border border-slate-300/60 dark:border-slate-600/60 px-3 py-1.5 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
                    >
                        {theme === "dark" ? "Light" : "Dark"}
                    </button>

                    <Link
                        to="/register"
                        className="rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 px-4 py-2 text-sm font-semibold hover:opacity-90"
                    >
                        Get Started
                    </Link>
                </nav>

                {/* Mobile */}
                <button
                    onClick={onToggleMenu}
                    className="md:hidden inline-flex h-10 w-10 items-center justify-center rounded-full border border-slate-300/70 dark:border-slate-600/70"
                    aria-label="Open menu"
                >
                    <svg width="20" height="20" viewBox="0 0 24 24" className="text-slate-800 dark:text-slate-100">
                        <path stroke="currentColor" strokeWidth="2" strokeLinecap="round" d="M4 7h16M4 12h16M4 17h16" />
                    </svg>
                </button>
            </div>
        </header>
    );
}

// ...existing mobile menu and other components...

export default function Layout({ children, showHero = true }) {
    const [menuOpen, setMenuOpen] = useState(false);
    const [scrolled, setScrolled] = useState(false);
    const [theme, setTheme] = useState("light");

    const currentBrand = useBrand();

    useEffect(() => {
        const onScroll = () => setScrolled(window.scrollY > 6);
        onScroll();
        window.addEventListener("scroll", onScroll, { passive: true });
        return () => window.removeEventListener("scroll", onScroll);
    }, []);

    return (
        <div className="min-h-screen bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100">
            <Header
                scrolled={scrolled}
                theme={theme}
                onToggleTheme={() => setTheme(theme === "dark" ? "light" : "dark")}
                currentBrand={currentBrand}
                onToggleMenu={() => setMenuOpen(true)}
            />

            {/* Additional components like MobileMenu and Hero can go here */}
            {/* Content */}
            <main className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 pb-20">
                {children}
            </main>

            {/* Footer component can be included here */}
        </div>
    );
}
