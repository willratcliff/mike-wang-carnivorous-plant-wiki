import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';

// Emit /wiki-lookup.json — the cross-site index used by Mike's sales
// page (mikesplants.com) to attach a wiki link to each plant card.
// Generated at build time from the same content collection that powers
// the wiki itself, so it cannot drift.
export const GET: APIRoute = async () => {
  const all = await getCollection('clones');
  const data = all.map((entry) => {
    const fm = entry.data as any;
    const isHybrid = fm.hybrid === true || entry.id.includes('/hybrids/');
    const loc = fm.origin_locality ?? {};
    const photos = fm.photos ?? [];
    return {
      id: entry.id,
      genus: (fm.genus ?? '').toLowerCase(),
      species: fm.species ?? null,
      infraspecific_rank: fm.infraspecific_rank ?? null,
      infraspecific_name: fm.infraspecific_name ?? null,
      cultivar: fm.cultivar ?? null,
      hybrid: isHybrid,
      full_name: fm.full_name ?? fm.group_name ?? null,
      short_name: fm.short_name ?? null,
      state: loc.state ?? null,
      county: loc.county ?? null,
      photo_count: photos.length,
      has_favorite: photos.some((p: any) => p.favorite),
    };
  });
  return new Response(JSON.stringify(data), {
    headers: {
      'content-type': 'application/json; charset=utf-8',
      // Allow Mike's site (and any cross-site consumer) to fetch this.
      'access-control-allow-origin': '*',
    },
  });
};
