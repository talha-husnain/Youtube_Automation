import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import seo from './vite-plugin-seo'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url)).replace(/\\/g, '/')

// Backend target for the dev proxy. Defaults to localhost:8000 for local dev;
// in Docker Compose, VITE_PROXY_TARGET=http://backend:8000 is passed.
const backend = process.env.VITE_PROXY_TARGET || 'http://localhost:8000'
const renderer = process.env.VITE_RENDER_TARGET || 'http://localhost:3100'

// https://vitejs.dev/config/
export default defineConfig({
  appType: 'spa',
  root: __dirname,
  plugins: [
    react(),
    seo(),
    {
      name: 'html-fallback',
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          if (req.url === '/' || req.url === '') {
            req.url = '/index.html';
          }
          next();
        });
      },
    },
  ],
  // The free tools (/youtube-transcript-generator and friends) are static
  // pages emitted by seo(); their behaviour ships as small standalone entries
  // with no React in them. vite-plugin-seo.js finds each entry's hashed file
  // name in the bundle and adds the <script> to its page.
  build: {
    rollupOptions: {
      input: {
        main: 'index.html',
        'tool-transcript': 'tools/transcript.js',
        'tool-metadata': 'tools/metadata.js',
        'tool-vertical': 'tools/vertical.js',
      },
    },
  },
  server: {
    allowedHosts: [
      'openshorts.app',
      'www.openshorts.app'
    ],
    proxy: {
      '/api': { target: backend, changeOrigin: true },
      '/videos': { target: backend, changeOrigin: true },
      '/thumbnails': { target: backend, changeOrigin: true },
      '/gallery': { target: backend, changeOrigin: true },
      '/video': { target: backend, changeOrigin: true },
      '/render': { target: renderer, changeOrigin: true },
    }
  }
})
