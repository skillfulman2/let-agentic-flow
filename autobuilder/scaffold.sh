#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR/app"

echo "=== Autobuilder Scaffold ==="

# Step 1: Create SvelteKit app structure manually
if [ -d "$APP_DIR" ]; then
  echo "app/ already exists, skipping create"
else
  echo "Creating SvelteKit app..."
  mkdir -p "$APP_DIR/src/routes" "$APP_DIR/src/lib" "$APP_DIR/static"

  # package.json — pinned to known-compatible versions
  cat > "$APP_DIR/package.json" << 'PKG'
{
  "name": "autobuilder-app",
  "version": "0.0.1",
  "private": true,
  "scripts": {
    "dev": "vite dev",
    "build": "vite build",
    "preview": "vite preview"
  },
  "devDependencies": {
    "@sveltejs/adapter-static": "^3.0.0",
    "@sveltejs/kit": "^2.15.0",
    "@sveltejs/vite-plugin-svelte": "^4.0.0",
    "svelte": "^5.0.0",
    "typescript": "^5.0.0",
    "vite": "^5.4.0"
  },
  "type": "module"
}
PKG

  # svelte.config.js
  cat > "$APP_DIR/svelte.config.js" << 'SVCONF'
import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  kit: {
    adapter: adapter({
      fallback: 'index.html'
    }),
    serviceWorker: {
      register: true
    }
  }
};

export default config;
SVCONF

  # vite.config.ts
  cat > "$APP_DIR/vite.config.ts" << 'VITE'
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()]
});
VITE

  # tsconfig.json
  cat > "$APP_DIR/tsconfig.json" << 'TSCONF'
{
  "extends": "./.svelte-kit/tsconfig.json",
  "compilerOptions": {
    "allowJs": true,
    "checkJs": true,
    "esModuleInterop": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "skipLibCheck": true,
    "sourceMap": true,
    "strict": true,
    "moduleResolution": "bundler"
  }
}
TSCONF

  # src/app.html
  cat > "$APP_DIR/src/app.html" << 'HTML'
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <link rel="icon" href="%sveltekit.assets%/favicon.png" />
    <link rel="manifest" href="/manifest.json" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    %sveltekit.head%
  </head>
  <body>
    <div style="display: contents">%sveltekit.body%</div>
  </body>
</html>
HTML

  # src/app.d.ts
  cat > "$APP_DIR/src/app.d.ts" << 'APPD'
/// <reference types="@sveltejs/kit" />
declare global {
  namespace App {}
}
export {};
APPD

  # src/routes/+layout.ts (enable prerendering for static adapter)
  cat > "$APP_DIR/src/routes/+layout.ts" << 'LAYOUT'
export const prerender = true;
export const ssr = true;
LAYOUT

  # src/routes/+page.svelte
  cat > "$APP_DIR/src/routes/+page.svelte" << 'PAGE'
<svelte:head>
  <title>Autobuilder App</title>
</svelte:head>

<main>
  <h1>Welcome</h1>
  <p>Autobuilder app is running.</p>
</main>

<style>
  main {
    max-width: 640px;
    margin: 0 auto;
    padding: 1rem;
  }
</style>
PAGE

  # src/service-worker.ts
  cat > "$APP_DIR/src/service-worker.ts" << 'SW'
/// <reference types="@sveltejs/kit" />
/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" />

import { build, files, version } from '$service-worker';

const CACHE = `cache-${version}`;
const ASSETS = [...build, ...files];

self.addEventListener('install', (event: ExtendableEvent) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(ASSETS))
  );
});

self.addEventListener('activate', (event: ExtendableEvent) => {
  event.waitUntil(
    caches.keys().then(async (keys) => {
      for (const key of keys) {
        if (key !== CACHE) await caches.delete(key);
      }
    })
  );
});

self.addEventListener('fetch', (event: FetchEvent) => {
  if (event.request.method !== 'GET') return;
  event.respondWith(
    caches.match(event.request).then((cached) => {
      return cached || fetch(event.request);
    })
  );
});
SW

  # static/manifest.json
  cat > "$APP_DIR/static/manifest.json" << 'MANIFEST'
{
  "name": "Autobuilder App",
  "short_name": "App",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#000000",
  "icons": [
    {
      "src": "/favicon.png",
      "sizes": "512x512",
      "type": "image/png"
    }
  ]
}
MANIFEST

  # Create a minimal favicon.png (1x1 transparent PNG)
  printf '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n\xb4\x00\x00\x00\x00IEND\xaeB`\x82' > "$APP_DIR/static/favicon.png"
fi

cd "$APP_DIR"

# Step 2: Install app dependencies
echo "Installing app dependencies..."
npm install

# Step 3: Install harness-level test dependencies
echo "Installing test harness dependencies..."
cd "$SCRIPT_DIR"
npm install

# Step 4: Install Playwright browsers
echo "Installing Playwright browsers (chromium)..."
npx playwright install chromium

# Step 5: Verify build
echo "Running initial build..."
cd "$APP_DIR"
npm run build

echo ""
echo "=== Scaffold complete ==="
echo "Run 'python autobuilder/evaluate.py' from the repo root to evaluate."
