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
import Layout from './components/Layout';

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
      {/* Full-bleed responsive hero that adapts to viewport height */}
      <section className="relative -mx-0 sm:-mx-6 lg:-mx-8 w-full">
        <div className="relative w-full h-screen sm:h-[80vh] md:h-[90vh] lg:h-screen overflow-hidden">
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

          {/* Optional subtle overlay for contrast */}
          <div className="absolute inset-0 bg-black/25 dark:bg-black/50" />

          {/* Centered content */}
          <div className="absolute inset-0 z-10 flex items-center justify-center px-4">
            <div className="text-center max-w-4xl">
              <h1 className="text-3xl sm:text-4xl md:text-5xl lg:text-6xl font-extrabold text-white drop-shadow-md">
                Design with confidence <span className="text-white/90">| GenFab</span>
              </h1>

              <div className="mt-6 flex items-center justify-center gap-3">
                <button
                  onClick={toggleDropdown}
                  className="rounded-md bg-white/10 hover:bg-white/12 text-white dark:text-slate-900 px-3 py-1.5 flex items-center justify-center focus:outline-none focus-visible:ring-2 focus-visible:ring-white/40 focus-visible:ring-offset-2 active:shadow-none"
                  aria-expanded={isDropdownOpen}
                  aria-label="Open menu"
                >
                  {/* Use public SVG for crisp scaling */}
                  <img src="/genfabtools-logo.png" alt="GenFab Tools" loading="lazy" decoding="async" className="h-6 sm:h-8 md:h-10 w-auto" />
                </button>
              </div>

              {isDropdownOpen && (
                <div className="mt-4 bg-white/10 dark:bg-white/10 backdrop-blur-sm rounded-md shadow p-4 mx-auto w-64 max-w-full text-slate-900 dark:text-white">
                  <DropdownLink to="/tools">Tools</DropdownLink>
                  <DropdownLink to="/about">About</DropdownLink>
                  <DropdownLink to="/contact">Contact</DropdownLink>
                  <DropdownLink to="/faq">FAQ</DropdownLink>
                </div>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function App() {
  return (
    <>
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
      </Routes>
    </>
  );
}

export default App;



