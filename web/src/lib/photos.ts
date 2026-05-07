// Photo URL resolution.
//
// Wiki frontmatter stores each photo by its local content-addressed
// path: e.g. "b9/b93fab01...e21af.jpg". To render the photo on the
// site without self-hosting we look up the original Flickr/PB URL via
// the hash→URL index built by scripts/build_image_index.py.
//
// For the subset of URLs we know are broken/blocked (Photobucket,
// dead personal sites, etc — identified by scripts/probe_image_urls.py),
// we ship a local copy under web/public/img-fallback/ and serve that
// instead. The list of broken SHAs is in src/data/broken-shas.json.

import imageIndexRaw from '~/data/image-urls.json';
import brokenShasRaw from '~/data/broken-shas.json';

type ImageIndexEntry = {
  url: string;
  ext: string;
  host: string;
};

const imageIndex = imageIndexRaw as Record<string, ImageIndexEntry>;
// brokenShas: { sha256: ext } — present if we self-host a fallback.
const brokenShas = brokenShasRaw as Record<string, string>;

const FALLBACK_BASE = '/img-fallback';

export function shaFromPath(localPath: string): string | null {
  // localPath looks like "b9/b93fab01...e21af.jpg"
  const file = localPath.split('/').pop();
  if (!file) return null;
  const dot = file.lastIndexOf('.');
  return dot === -1 ? file : file.slice(0, dot);
}

export function resolveImageUrl(localPath: string): string | null {
  const sha = shaFromPath(localPath);
  if (!sha) return null;
  // If this SHA is in the broken set and we have a self-hosted copy,
  // serve from the local fallback.
  if (sha in brokenShas) {
    return `${FALLBACK_BASE}/${sha}.${brokenShas[sha]}`;
  }
  return imageIndex[sha]?.url ?? null;
}

export function imageHost(localPath: string): string | null {
  const sha = shaFromPath(localPath);
  return sha ? imageIndex[sha]?.host ?? null : null;
}
