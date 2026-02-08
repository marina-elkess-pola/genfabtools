/**
 * v1.1 UI + Branding Freeze — Do not modify without version bump.
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
// Global styles (Tailwind + custom overrides)
import './index.css';

const rootElement = document.getElementById('root');
ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
