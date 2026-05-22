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

  // Production build tuning. The pre-split bundle was a single 998 KB
  // chunk — too large for first-paint on mobile. We split out the
  // common heavyweight libraries so the browser can parallelise the
  // download and cache them across deploys.
  build: {
    // Most of our screens render at the same time the user lands on
    // /signin or /dashboard, so a slightly higher per-chunk ceiling
    // is fine — but we still want vendor splits.
    chunkSizeWarningLimit: 600,
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return undefined
          // Heaviest bundles first — pin them so they cache across
          // deploys whenever their version doesn't change.
          if (id.includes('react-router')) return 'router'
          if (id.includes('react-dom')) return 'react-dom'
          if (id.includes('react/') || id.endsWith('react')) return 'react-core'
          if (id.includes('motion') || id.includes('framer-motion')) return 'motion'
          if (id.includes('lucide-react')) return 'icons'
          if (id.includes('recharts') || id.includes('d3-')) return 'charts'
          // Everything else stays in a shared vendor chunk so we don't
          // explode into hundreds of tiny files (HTTP/2 helps but
          // there's still overhead).
          return 'vendor'
        },
      },
    },
  },
})
