import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  base: '/',
  // Pre-bundle some dependencies that are known to ship ESM/CJS mixes and
  // can cause runtime interop issues (helps ensure React is available when
  // framer-motion or other animation libs execute).
  optimizeDeps: {
    include: ['framer-motion']
  },
  plugins: [react()],
  resolve: {
    alias: {
      react: path.resolve(__dirname, 'node_modules/react'),
      'react-dom': path.resolve(__dirname, 'node_modules/react-dom')
    }
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    open: true,
    proxy: {
      // Parking API goes directly to Python backend
      '/api/parking': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        secure: false,
        rewrite: (path) => path.replace(/^\/api/, '')
      },
      // SiteGen API goes directly to Python backend
      '/api/sitegen': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        secure: false,
        rewrite: (path) => path.replace(/^\/api\/sitegen/, '/sitegen')
      },
      // Other API requests to Node.js backend
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
        secure: false
      }
      ,
      '/me': {
        target: 'http://localhost:5000',
        changeOrigin: true,
        secure: false
      }
    },
  },
  // Use ES module format for built workers so code-splitting is supported
  worker: {
    format: 'es'
  },
  build: {
    sourcemap: mode === 'development',
    // Split large vendor libraries into separate chunks to improve initial load
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('html2canvas')) return 'vendor_html2canvas';
            if (id.includes('jspdf')) return 'vendor_jspdf';
            if (id.includes('xlsx')) return 'vendor_xlsx';
            if (id.includes('file-saver')) return 'vendor_file-saver';
            // Ensure framer-motion and React live in the same vendor chunk to
            // avoid a circular ESM import where the motion runtime attempts to
            // read React before it's initialized in a separate chunk. Grouping
            // framer-motion with React prevents the "createContext of
            // undefined" runtime error seen in production builds.
            if (id.includes('framer-motion')) return 'vendor_react';
            if (id.includes('react') || id.includes('react-dom')) return 'vendor_react';
            return 'vendor_misc';
          }
        }
      }
    },
    chunkSizeWarningLimit: 800
  }
}))

