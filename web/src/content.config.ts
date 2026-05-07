import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const photoSchema = z.object({
  path: z.string(),
  caption: z.string(),
  photographer: z.string(),
  source_post_id: z.number().int(),
  favorite: z.boolean().default(false),
  note: z.string().optional(),
});

const sourceThreadSchema = z.object({
  thread_id: z.number().int(),
  url: z.string().url(),
  role: z.string(),
  note: z.string().optional(),
});

const reviewSchema = z.object({
  ai_extracted_by: z.string(),
  ai_extracted_at: z.string().optional(),
  cluster_id: z.string().optional(),
  human_reviewed: z.boolean().default(false),
  human_reviewer: z.string().nullable().optional(),
  human_corrections: z.array(z.unknown()).default([]),
  open_questions: z.array(z.string()).default([]),
  cluster_split_note: z.string().optional(),
}).passthrough();

const localitySchema = z.object({
  country: z.string().nullable().optional(),
  state: z.string().nullable().optional(),
  county: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
}).passthrough();

const visuallySimilarSchema = z.object({
  clone: z.string(),
  note: z.string(),
});

// Year fields that are mostly int but occasionally come through as a
// string (e.g. "early 1990s") — accept either, surface as-is.
const flexibleYear = z.union([z.number().int(), z.string()]).nullable().optional();

const cloneSchema = z.object({
  // Most entries are clones (full_name + short_name). A handful are
  // disambiguation pages (type: cultivar_group, group_name + member_clones)
  // that route the reader to the right underlying clone.
  type: z.string().optional(),
  full_name: z.string().optional(),
  short_name: z.string().optional(),
  group_name: z.string().optional(),
  member_clones: z.array(z.string()).optional(),
  genus: z.string(),
  species: z.string().nullable(),
  infraspecific_rank: z.string().nullable().optional(),
  infraspecific_name: z.string().nullable().optional(),
  hybrid: z.boolean().default(false),
  cultivar: z.string().nullable().optional(),
  cultivar_group: z.string().nullable().optional(),
  accession_type: z.string().optional(),

  origin_locality: localitySchema.optional(),
  collector: z.string().nullable().optional(),
  breeder: z.string().nullable().optional(),
  year_collected: flexibleYear,
  year_into_cultivation: flexibleYear,
  year_first_described_on_forum: z.number().int().optional(),
  naming_etymology: z.string().optional(),

  standout_traits: z.array(z.string()).default([]),
  visually_similar_to: z.array(visuallySimilarSchema).default([]),
  cultivation_notes: z.string().optional(),

  source_threads: z.array(sourceThreadSchema).default([]),
  photos: z.array(photoSchema).default([]),
  photos_not_mirrored: z.array(z.object({
    source_post_id: z.number().int(),
    note: z.string().optional(),
  }).passthrough()).default([]),
  ambiguous_photos: z.array(photoSchema).default([]),

  review: reviewSchema,
}).passthrough();
// `.passthrough()` keeps the long-tail one-off fields (parentage,
// variant_register, conservation_status, etc.) so the page template
// can render them in a generic "additional metadata" section without
// the build failing on rare schemas.

export const collections = {
  clones: defineCollection({
    loader: glob({
      pattern: '**/index.md',
      base: '../wiki',
      // Strip the trailing "/index" so an entry at
      // wiki/sarracenia/flava/red-side/index.md gets id
      // "sarracenia/flava/red-side" — matches the URL we want.
      generateId: ({ entry }) => entry.replace(/\/index\.md$/, '').replace(/\.md$/, ''),
    }),
    schema: cloneSchema,
  }),
};

export type CloneFrontmatter = z.infer<typeof cloneSchema>;
