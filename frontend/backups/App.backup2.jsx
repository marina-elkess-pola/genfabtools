// App.backup2.jsx
// This is a backup copy of the current App.jsx file (Reference #2).
// [Insert the full content of App.jsx here as it is currently.]

import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Home from './Home';
import OccuCalc from './OccuCalc';
import Tools from './Tools';
import About from './About';

function App() {
    return (
        <Router>
            <Layout>
                <Routes>
                    <Route path="/" element={<Home />} />
                    <Route path="/occucalc" element={<OccuCalc />} />
                    <Route path="/tools" element={<Tools />} />
                    <Route path="/about" element={<About />} />
                </Routes>
            </Layout>
        </Router>
    );
}

export default App;
