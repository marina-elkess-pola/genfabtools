console.log("🔥 FRONTEND App.jsx IS LIVE 🔥");

import React, { useState, useEffect, useRef, Suspense, lazy } from 'react';
import { Routes, Route, Link } from 'react-router-dom';
// Lazy-load heavy routes to reduce initial bundle size
const ImmersiveHomepage = lazy(() => import('./ImmersiveHomepage'));
const Tools = lazy(() => import('./Tools'));
const OccuCalc = lazy(() => import('./OccuCalc'));
const ParkCore = lazy(() => import('./ParkCore'));
const ParkingGenerator = lazy(() => import('./ParkingGenerator'));
const ParkingEngine = lazy(() => import('./parking-app').then(m => ({ default: m.ParkingApp })));
const SiteGen = lazy(() => import('./SiteGen'));
const Register = lazy(() => import('./Register'));
const Login = lazy(() => import('./Login'));
const PurchaseVerify = lazy(() => import('./PurchaseVerify'));
// Scaffolded informational pages
const About = lazy(() => import('./About'));
const Contact = lazy(() => import('./Contact'));
const FAQ = lazy(() => import('./FAQ'));
const Account = lazy(() => import('./Account'));
const Support = lazy(() => import('./Support'));
const RSI = lazy(() => import('./RSI'));
import Layout from './components/Layout';
import { useLocation } from "react-router-dom";

// 🔥 SCROLL FIX COMPONENT
function ScrollToTop() {
  const { pathname } = useLocation();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return null;
}

function HomeMain() {
  const [isDropdownOpen, setDropdownOpen] = useState(false);
  const toggleDropdown = () => setDropdownOpen(!isDropdownOpen);

  function DropdownLink({ to, children }) {
    return (
      <Link
        to={to}
        className="block py-2 px-3 font-semibold text-white/90 dark:text-slate-900 hover:text-white/60 active:text-slate-200 rounded transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/40"
      >
        {children}
      </Link>
    );
  }

  return (
    <div className="pt-0">
      {/* Full-bleed hero: 100vw × 100vh, no white borders */}
      <section className="relative w-screen h-screen overflow-hidden">
        {/* Video covers the full hero area and preserves aspect ratio.
              Lazy-load the MP4 to avoid fetching heavy media on initial load. */}
        {/* Setup a ref and IntersectionObserver to set the `src` only when near viewport */}
        {(() => {
          const videoRef = useRef(null);
          useEffect(() => {
            const vid = videoRef.current;
            if (!vid) return;
            // If already loaded or no IntersectionObserver support, set src immediately
            if (!('IntersectionObserver' in window)) {
              if (!vid.src) vid.src = '/genfabtools-logo-animation.mp4';
              return;
            }

            const io = new IntersectionObserver(
              (entries) => {
                entries.forEach((entry) => {
                  if (entry.isIntersecting) {
                    if (!vid.src) vid.src = '/genfabtools-logo-animation.mp4';
                    io.disconnect();
                  }
                });
              },
              { rootMargin: '200px' }
            );

            io.observe(vid);
            return () => io.disconnect();
          }, []);

          return (
            <video
              ref={videoRef}
              src="/genfabtools-logo-animation.mp4"
              poster="/genfabtools-logo.png"
              preload="none"
              autoPlay
              loop
              muted
              playsInline
              className="absolute inset-0 w-full h-full object-cover"
              aria-hidden="true"
            >
              {/* Explicit src plus <source> ensures the animation loads across environments. */}
              <source src="/genfabtools-logo-animation.mp4" type="video/mp4" />
            </video>
          );
        })()}

        {/* Dark gradient overlay for text readability */}
        <div className="absolute inset-0 bg-gradient-to-b from-black/40 via-black/20 to-black/50" />

        {/* Centered content — no container background, text sits directly on video */}
        <div className="absolute inset-0 z-10 flex items-center justify-center px-6">
          <div className="text-center">
            <h1 className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-extrabold text-white drop-shadow-lg tracking-tight leading-tight">
              Smarter tools for modern workflows.
            </h1>

            <p className="mt-10 text-base sm:text-lg md:text-xl text-white/75 font-light leading-relaxed mx-auto" style={{ maxWidth: '650px' }}>
              GenFabTools is a platform for intelligent utilities that simplify complex workflows across design, engineering, fabrication, and analysis.
            </p>

            <div className="mt-12 flex items-center justify-center gap-5 flex-wrap">
              <button
                onClick={() => {
                  const el = document.getElementById('platform-overview');
                  if (!el) return;
                  const start = window.scrollY;
                  const end = el.getBoundingClientRect().top + start - 60;
                  const duration = 1000;
                  let startTime = null;
                  function ease(t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }
                  function step(ts) {
                    if (!startTime) startTime = ts;
                    const progress = Math.min((ts - startTime) / duration, 1);
                    window.scrollTo(0, start + (end - start) * ease(progress));
                    if (progress < 1) requestAnimationFrame(step);
                  }
                  requestAnimationFrame(step);
                }}
                className="rounded-xl bg-white text-slate-900 font-bold px-10 py-4 text-base sm:text-lg shadow-2xl hover:bg-white/95 hover:scale-[1.02] transition-all duration-200 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-white/60 focus-visible:ring-offset-2 focus-visible:ring-offset-black/50"
              >
                Explore Tools
              </button>
              <Link
                to="/about"
                className="rounded-xl border border-white/30 text-white/80 font-normal px-9 py-4 text-base sm:text-lg hover:bg-white/10 hover:text-white transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/40 focus-visible:ring-offset-2 focus-visible:ring-offset-black/50"
              >
                Learn More
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Platform Overview — transition section */}
      <section id="platform-overview" className="px-6" style={{ background: 'linear-gradient(to bottom, #f9fafb, #ffffff)', paddingTop: '120px', paddingBottom: '120px' }}>
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="text-3xl sm:text-4xl font-bold text-slate-900 tracking-tight">
            A growing ecosystem of intelligent tools
          </h2>
          <p className="mt-6 text-lg text-slate-600 leading-relaxed mx-auto" style={{ maxWidth: '620px' }}>
            GenFabTools brings together purpose-built utilities for architects, engineers, and planners — each designed to automate tedious tasks and surface better decisions faster.
          </p>
        </div>
      </section>

      {/* Tools section */}
      <section id="tools-section" className="bg-white dark:bg-slate-900 px-6" style={{ paddingTop: '120px', paddingBottom: '120px' }}>
        <div className="max-w-5xl mx-auto text-center">
          <h2 className="text-3xl sm:text-4xl font-bold text-slate-900 dark:text-white">Our Tools</h2>
          <p className="mt-4 text-lg text-slate-600 dark:text-slate-400 mx-auto" style={{ maxWidth: '600px' }}>
            Purpose-built utilities for architecture, engineering, and site planning.
          </p>
          <div className="mt-12 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            <Link to="/sitegen" className="group rounded-2xl border border-slate-200 dark:border-slate-700 p-8 text-left hover:shadow-lg transition-shadow duration-200">
              <h3 className="text-xl font-semibold text-slate-900 dark:text-white group-hover:text-blue-600 transition-colors">SiteGen</h3>
              <p className="mt-2 text-slate-500 dark:text-slate-400 text-sm">Automated site planning with optimized building massing and parking layouts.</p>
            </Link>
            <Link to="/occucalc" className="group rounded-2xl border border-slate-200 dark:border-slate-700 p-8 text-left hover:shadow-lg transition-shadow duration-200">
              <h3 className="text-xl font-semibold text-slate-900 dark:text-white group-hover:text-blue-600 transition-colors">OccuCalc</h3>
              <p className="mt-2 text-slate-500 dark:text-slate-400 text-sm">Occupant load calculator for architects and engineers using common code rules.</p>
            </Link>
            <Link to="/parkcore" className="group rounded-2xl border border-slate-200 dark:border-slate-700 p-8 text-left hover:shadow-lg transition-shadow duration-200">
              <h3 className="text-xl font-semibold text-slate-900 dark:text-white group-hover:text-blue-600 transition-colors">ParkCore</h3>
              <p className="mt-2 text-slate-500 dark:text-slate-400 text-sm">Generate optimized parking layouts from site boundaries with smart circulation.</p>
            </Link>
          </div>
          <div className="mt-10">
            <Link to="/tools" className="text-blue-600 dark:text-blue-400 font-medium hover:underline">View all tools &rarr;</Link>
          </div>
        </div>
      </section>
    </div>
  );
}

function App() {
  return (
    <>
      {/* ✅ THIS FIXES YOUR ISSUE */}
      <ScrollToTop />

      <Routes>
        <Route path="/" element={<HomeMain />} />

        <Route
          path="/immersive"
          element={<Layout showHero={false}><Suspense fallback={<div className="p-8 text-center">Loading…</div>}><ImmersiveHomepage /></Suspense></Layout>}
        />

        <Route
          path="/tools"
          element={<Layout showHero={false}><Suspense fallback={<div className="p-8 text-center">Loading tools…</div>}><Tools /></Suspense></Layout>}
        />

        {/* 🔥 ADD THIS (VERY IMPORTANT) */}
        <Route
          path="/tools/rsi"
          element={
            <Layout showHero={false}>
              <Suspense fallback={<div className="p-8 text-center">Loading…</div>}>
                <RSI />
              </Suspense>
            </Layout>
          }
        />

        <Route
          path="/occucalc"
          element={<Layout showHero={false}><Suspense fallback={<div className="p-8 text-center">Loading OccuCalc…</div>}><OccuCalc /></Suspense></Layout>}
        />

        <Route
          path="/parkcore"
          element={<Layout showHero={false}><Suspense fallback={<div className="p-8 text-center">Loading ParkCore…</div>}><ParkCore /></Suspense></Layout>}
        />

        <Route
          path="/parking"
          element={<Layout showHero={false}><Suspense fallback={<div className="p-8 text-center">Loading Parking…</div>}><ParkingGenerator /></Suspense></Layout>}
        />

        <Route
          path="/parking-engine"
          element={<Suspense fallback={<div className="p-8 text-center">Loading Parking Engine…</div>}><ParkingEngine /></Suspense>}
        />

        <Route
          path="/sitegen"
          element={<Layout showHero={false} fullWidth={true}><Suspense fallback={<div className="p-8 text-center text-white bg-gray-950">Loading SiteGen…</div>}><SiteGen /></Suspense></Layout>}
        />

        <Route
          path="/register"
          element={<Layout showHero={false}><Suspense fallback={<div className="p-8 text-center">Loading…</div>}><Register /></Suspense></Layout>}
        />

        <Route
          path="/about"
          element={<Layout showHero={false}><Suspense fallback={<div className="p-8 text-center">Loading…</div>}><About /></Suspense></Layout>}
        />

        <Route
          path="/contact"
          element={<Layout showHero={false}><Suspense fallback={<div className="p-8 text-center">Loading…</div>}><Contact /></Suspense></Layout>}
        />

        <Route
          path="/faq"
          element={<Layout showHero={false}><Suspense fallback={<div className="p-8 text-center">Loading…</div>}><FAQ /></Suspense></Layout>}
        />

        <Route
          path="/login"
          element={<Layout showHero={false}><Suspense fallback={<div className="p-8 text-center">Loading…</div>}><Login /></Suspense></Layout>}
        />

        <Route
          path="/account"
          element={<Layout showHero={false}><Suspense fallback={<div className="p-8 text-center">Loading account…</div>}><Account /></Suspense></Layout>}
        />

        <Route
          path="/purchase/verify"
          element={<Layout showHero={false}><Suspense fallback={<div className="p-8 text-center">Verifying…</div>}><PurchaseVerify /></Suspense></Layout>}
        />

        <Route
          path="/support"
          element={<Layout showHero={false}><Suspense fallback={<div className="p-8 text-center">Loading…</div>}><Support /></Suspense></Layout>}
        />
      </Routes>
    </>
  );
}

export default App;



