// Layout.jsx
import React, { useState, useEffect } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
/* motion is used as a JSX namespace (e.g. <motion.div/>) — ESLint sometimes flags this as unused; disable the rule for the import line */
/* eslint-disable-next-line no-unused-vars */
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import OccuCalcLogo from "../assets/occucalc-logo-black.png";
import GenFabLogo from "../assets/genfabtools-logo-black.png";

/** Header logo height - consistent across all pages */
const HEADER_LOGO_HEIGHT = 28; // px

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
    logo: GenFabLogo,
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

// Simple body-scroll lock hook used by the mobile menu to prevent background scroll
function useBodyLock(open) {
  useEffect(() => {
    if (!open) return;
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, [open]);
}

function Header({ scrolled, onToggleTheme, theme, currentBrand, onToggleMenu }) {
  const location = useLocation();
  const [loggedIn, setLoggedIn] = useState(false);

  useEffect(() => {
    setLoggedIn(!!localStorage.getItem('token'));
  }, [location]);

  const navItems = [
    { path: '/', label: 'Home' },
    { path: '/tools', label: 'Tools' },
    { path: '/about', label: 'About' },
    { path: '/faq', label: 'FAQ' },
  ];

  return (
    <header
      className={`fixed inset-x-0 top-0 z-50 transition-all ${scrolled
        ? "backdrop-blur bg-white/80 border-b border-slate-200"
        : "bg-white"
        }`}
    >
      <div className="mx-auto max-w-7xl px-6 h-16 flex items-center justify-between">

        {/* LOGO + BRAND */}
        <Link to="/" className="flex items-center gap-3">
          <img
            src={currentBrand?.logo || GenFabLogo}
            alt="GenFabTools logo"
            style={{ height: 28 }}
          />

          {/* FULL NAME (FIXED) */}
          <span className="font-semibold text-lg text-slate-900">
            GenFabTools
          </span>
        </Link>

        {/* NAV */}
        <nav className="hidden md:flex items-center gap-8">

          {navItems.map((item) => {
            const isActive = item.path === '/' ? location.pathname === '/' : location.pathname.startsWith(item.path);

            return (
              <NavLink
                key={item.path}
                to={item.path}
                className={`text-sm font-medium transition ${isActive ? 'text-slate-900 font-semibold' : 'text-slate-600 hover:text-black'}`}
              >
                {item.label}
              </NavLink>
            );
          })}

          {/* CTA BUTTON (VISIBLE FIX) */}
          {loggedIn ? (
            <Link
              to="/account"
              className="ml-4 px-5 py-2 rounded-md bg-slate-900 text-white text-sm font-semibold hover:bg-slate-800 shadow-md transition"
            >
              Account
            </Link>
          ) : (
            <Link
              to="/register"
              className="ml-4 px-5 py-2 rounded-md bg-white text-black text-sm font-semibold hover:bg-gray-200 shadow-md transition"
            >
              Get Started
            </Link>
          )}

        </nav>

        {/* MOBILE */}
        <button
          onClick={onToggleMenu}
          className="md:hidden p-2 border rounded-md"
        >
          ☰
        </button>

      </div>
    </header>
  );
}

/**
 * Mobile Drawer
 */
function MobileMenu({ open, onClose, onToggleTheme, theme }) {
  useBodyLock(open);
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />
          <motion.aside
            className="fixed z-50 left-0 top-0 h-full w-80 bg-white dark:bg-slate-900 shadow-xl p-6"
            initial={{ x: -320 }}
            animate={{ x: 0 }}
            exit={{ x: -320 }}
            transition={{ type: "spring", stiffness: 380, damping: 30 }}
            aria-label="Mobile navigation"
          >
            <div className="flex items-center justify-between mb-8">
              <Link to="/" onClick={onClose} className="font-semibold text-slate-900 dark:text-slate-100">
                {BRAND.name}
              </Link>
              <button
                onClick={onClose}
                aria-label="Close menu"
                className="rounded-full p-2 hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                <svg width="20" height="20" viewBox="0 0 24 24">
                  <path stroke="currentColor" strokeWidth="2" strokeLinecap="round" d="M6 6l12 12M6 18L18 6" />
                </svg>
              </button>
            </div>

            <nav className="flex flex-col gap-4">
              {[
                { path: '/', label: 'Home' },
                { path: '/tools', label: 'Tools' },
                { path: '/about', label: 'About' },
                { path: '/faq', label: 'FAQ' },
              ].map((item) => {
                if (window.location.pathname.startsWith(item.path) && item.path !== '/') return null;

                return (
                  <Link key={item.path} to={item.path} onClick={onClose} className="text-lg font-medium">
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

/**
 * Ambient hero background (soft, premium)
 */
function HeroBackdrop() {
  const reduce = useReducedMotion();
  return (
    <div className="absolute inset-0 -z-10 overflow-hidden">
      {/* subtle radial glow */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(14,165,233,0.10),transparent_60%)] dark:bg-[radial-gradient(ellipse_at_center,rgba(59,130,246,0.12),transparent_60%)]" />
      {/* flowing gradient ribbon */}
      <motion.div
        aria-hidden
        className={`absolute -top-28 left-1/2 h-[42rem] w-[42rem] -translate-x-1/2 rounded-full bg-gradient-to-tr ${BRAND.accent} blur-3xl opacity-[0.12]`}
        initial={reduce ? false : { rotate: 0 }}
        animate={reduce ? {} : { rotate: 360 }}
        transition={{ duration: 60, repeat: Infinity, ease: "linear" }}
      />
    </div>
  );
}

/**
 * Hero section (Pebble-like: big type, few words, strong CTA)
 */
function Hero() {
  return (
    <section className="relative pt-28 pb-16 sm:pt-32 sm:pb-24">
      <HeroBackdrop />
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <h1 className="max-w-3xl text-4xl sm:text-6xl font-semibold tracking-tight leading-[1.05] text-slate-900 dark:text-slate-50">
          Intelligent tools for the <span className="underline decoration-2 underline-offset-8">built world</span>.
        </h1>
        <p className={`mt-6 max-w-2xl text-base sm:text-lg ${BRAND.subtext}`}>
          We merge generative design, simulation, and fabrication into calm, powerful utilities. Less noise. More outcome.
        </p>
        <div className="mt-8 flex items-center gap-3">
          <Link
            to="/tools"
            className="rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 px-5 py-2.5 text-sm font-semibold hover:opacity-95"
          >
            Explore Tools
          </Link>
          <Link to="/about" className="text-sm font-medium underline underline-offset-4">
            Our philosophy →
          </Link>
        </div>
      </div>
    </section>
  );
}

/**
 * Footer (quiet & refined)
 */
function Footer() {
  return (
    <footer className="border-t border-slate-200 dark:border-slate-800 py-10">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6">
          <div>
            <div className="flex items-center gap-3">
              <span className="inline-block h-2.5 w-2.5 rounded-full bg-slate-900 dark:bg-white" />
              <span className="font-semibold">{BRAND.name}</span>
            </div>
            <p className="mt-3 text-sm text-slate-500">
              © {new Date().getFullYear()} {BRAND.name}. All rights reserved.
            </p>
          </div>
          <nav className="flex gap-6 text-sm">
            <Link to="/privacy" className="text-slate-600 dark:text-slate-300 hover:underline">Privacy</Link>
            <Link to="/terms" className="text-slate-600 dark:text-slate-300 hover:underline">Terms</Link>
            <Link to="/contact" className="text-slate-600 dark:text-slate-300 hover:underline">Contact</Link>
          </nav>
        </div>
      </div>
    </footer>
  );
}

/**
 * Main Layout
 */
export default function Layout({ children, showHero = true, fullWidth = false }) {
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
    <div className={`min-h-screen ${fullWidth ? 'bg-white' : 'bg-white dark:bg-slate-950'} text-slate-900 dark:text-slate-100`}>
      {/* Skip link for keyboard users */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:bg-white dark:focus:bg-slate-900 focus:px-3 focus:py-2 focus:rounded focus:shadow"
      >
        Skip to content
      </a>

      <Header
        scrolled={scrolled}
        theme={theme}
        onToggleTheme={() => setTheme(theme === "dark" ? "light" : "dark")}
        currentBrand={currentBrand}
        onToggleMenu={() => setMenuOpen(true)}
      />
      <MobileMenu
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
        theme={theme}
        onToggleTheme={() => setTheme(theme === "dark" ? "light" : "dark")}
      />

      {/* Hero (optional on homepage) */}
      {showHero && !fullWidth && <Hero />}

      {/* Content */}
      <main id="main-content" className={fullWidth ? 'w-full h-[calc(100vh-4rem)] overflow-hidden' : 'mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 pb-20'}>
        {children}
      </main>

      {!fullWidth && <Footer />}
    </div>
  );
}

