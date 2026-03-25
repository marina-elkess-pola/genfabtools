import React, { useState } from 'react';
import { Link } from 'react-router-dom';
/* motion is used as a JSX namespace (e.g. <motion.div/>) — ESLint sometimes flags this as unused; disable the rule for the import line */
/* eslint-disable-next-line no-unused-vars */
import { motion, AnimatePresence } from 'framer-motion';

function ImmersiveHomepage() {
    const [menuOpen, setMenuOpen] = useState(false);

    return (
        <div className="relative min-h-screen overflow-hidden bg-black">
            {/* Animated Background */}
            <motion.div
                className="absolute inset-0"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 2 }}
            >
                <motion.div
                    className="absolute inset-0 bg-gradient-to-tr from-purple-600 via-pink-600 to-red-600 opacity-50 blur-3xl"
                    animate={{ rotate: 360 }}
                    transition={{ repeat: Infinity, duration: 60, ease: "linear" }}
                />
            </motion.div>

            {/* Content Overlay */}
            <div className="relative flex flex-col items-center justify-center min-h-screen text-white px-4">
                <h1 className="text-5xl md:text-7xl font-bold mb-4 text-center">
                    Design with Confidence | GenFab
                </h1>
                <p className="text-lg md:text-2xl mb-8 text-center">
                    Explore our immersive experience.
                </p>
                <div>
                    <button
                        onClick={() => setMenuOpen(!menuOpen)}
                        className="bg-white text-black px-4 py-2 rounded-full font-semibold"
                    >
                        Menu
                    </button>
                </div>

                <AnimatePresence>
                    {menuOpen && (
                        <motion.div
                            className="absolute top-20 bg-white text-black rounded-lg shadow-lg flex flex-col items-center py-4"
                            initial={{ opacity: 0, y: -20 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -20 }}
                            transition={{ duration: 0.3 }}
                        >
                            <Link to="/" className="px-4 py-2 hover:bg-gray-200 w-full text-center">Home</Link>
                            <Link to="/tools" className="px-4 py-2 hover:bg-gray-200 w-full text-center">Tools</Link>
                            <Link to="/about" className="px-4 py-2 hover:bg-gray-200 w-full text-center">About</Link>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        </div>
    );
}

export default ImmersiveHomepage;
