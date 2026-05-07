// @ts-check
import { defineConfig } from 'astro/config';

// Site URL is the canonical published URL — used for absolute links,
// sitemap, and SEO meta tags. Update when DNS for wiki.mikesplants.com
// is live; for now the GitHub Pages default is fine.
export default defineConfig({
  site: 'https://wiki.mikesplants.com',
  output: 'static',
  trailingSlash: 'always',
  build: {
    format: 'directory',
  },
  vite: {
    // Allow Astro's dev server to read files outside `web/` (we read
    // wiki content from `../wiki/` and the image manifest from
    // `../data/images/manifest.json`).
    server: {
      fs: {
        allow: ['..'],
      },
    },
  },
});
