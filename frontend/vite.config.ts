import { defineConfig } from 'vite'
import path from 'path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'


function figmaAssetResolver() {
  return {
    name: 'figma-asset-resolver',
    resolveId(id: string) {
      if (id.startsWith('figma:asset/')) {
        const filename = id.replace('figma:asset/', '')
        return path.resolve(__dirname, 'src/assets', filename)
      }
      return undefined
    },
  }
}

export default defineConfig({
  // Local dev: api.ts calls same-origin /api/* (required by the production
  // CSP), so the dev server must proxy those calls to the backend. Without
  // this block every local /api request 404s against the Vite server itself.
  server: {
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  plugins: [
    figmaAssetResolver(),
    // The React and Tailwind plugins are both required for Make, even if
    // Tailwind is not being actively used – do not remove them
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      // Alias @ to the src directory
      '@': path.resolve(__dirname, './src'),
    },
  },
  // File types to support raw imports. Never add .css, .tsx, or .ts files to this.
  assetsInclude: ['**/*.svg', '**/*.csv'],

  // Production build tuning. We split heavyweight libraries so the browser can
  // parallelise downloads and cache them across deploys.
  build: {
    chunkSizeWarningLimit: 600,
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return undefined
          const m = id.replace(/\\/g, '/')
          // The React RUNTIME must be fully self-contained in ONE chunk that
          // every other chunk depends on. Splitting react-is/scheduler out, or
          // greedily matching "react/" (which pulled @sentry/react in and its
          // @sentry/core dep created a circular chunk dependency), causes a
          // "Cannot read properties of undefined (reading 'PureComponent')"
          // crash at boot. Anchor strictly to node_modules/<pkg>/.
          if (/\/node_modules\/(react|react-dom|react-is|scheduler|prop-types|use-sync-external-store|object-assign|react\/jsx-runtime)\//.test(m)) {
            return 'react-core'
          }
          if (m.includes('/node_modules/react-router')) return 'router'
          if (m.includes('/node_modules/motion') || m.includes('framer-motion')) return 'motion'
          if (m.includes('/node_modules/lucide-react')) return 'icons'
          if (m.includes('/node_modules/recharts') || m.includes('/node_modules/d3-') || m.includes('/node_modules/victory') || m.includes('/node_modules/internmap')) return 'charts'
          // Everything else (incl. @sentry/*) shares a vendor chunk that
          // cleanly imports React from react-core — one-way, no cycle.
          return 'vendor'
        },
      },
    },
  },
})
