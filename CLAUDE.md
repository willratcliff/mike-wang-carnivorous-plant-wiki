# Project override — synthesis-loop autonomy

This project's clone-wiki synthesis is an **autonomous batch operation**.
Mike Wang reviews completed drafts later in batches; he is **not** in the
loop per-clone, per-commit, or per-decision.

The Claude Lab Assistant guidelines in `~/.claude/CLAUDE.md` and
`~/Desktop/ClaudeCode/CLAUDE.md` (human-in-the-loop, "ask before each
step", "checkpoint protocol") **DO NOT APPLY** to wiki synthesis on this
project. They were designed for scientific analysis where wrong
methodology corrupts results; that risk model does not match a
draft-then-batch-review wiki build.

## How to run the synthesis loop

When working through `data/parsed/clones/clusters.json`:

- **Do NOT pause between clones to ask permission.** Treat the cluster
  list as a queue to drain.
- **Do NOT request approval for git commits, pushes, mkdir, or file
  writes inside the project tree.** All of these are pre-allowlisted in
  `.claude/settings.local.json`.
- **Do NOT checkpoint** between split decisions, photo galleries, open-
  question lists, or related sub-steps. Apply `docs/synthesis-recipe.md`
  as written.
- **Do commit + push after each clone** (one commit per cluster) and
  proceed directly to the next cluster. Use HEREDOC commit messages.
- **Do update** `data/parsed/clones/synthesis_progress.json` per cluster.

## When to actually pause

Only stop to ask the user if you encounter one of these:

1. A new cluster pattern that's not covered by `docs/synthesis-recipe.md`
   or the `cluster_gotchas` memory file.
2. A cluster with 5+ obviously-unrelated threads merged — investigate
   for a regex bug, don't paper over.
3. Self-contradicting source content that needs an interpretive call.
4. An actual error you can't resolve.

## Stopping condition

Run autonomously until either:
- The user-specified batch size is complete (e.g., "do 30 clusters").
- All `clusters.json` entries not in `synthesis_progress.json` are done.
- Context fills (~80%); at that point, save a final session memory file
  and stop.

## Format guidance — stay efficient

- Use the synthesis recipe template from `docs/synthesis-recipe.md`.
- Caption photos minimally for non-distinctive images
  (`caption: "<clone short_name>, <date>"`).
- Reuse common open-questions across entries (when, who, distribution
  status) — don't reinvent the wording per clone.
- Skip wild-site documentation threads automatically (board name
  "Sarracenia In The Wild" or cluster patterns described in
  `cluster_gotchas` memory) — defer them in
  `synthesis_progress.json` with status `deferred-not-a-clone`.

## Memory + handoff

At the end of each batch, update
`~/.claude/projects/-Users-williamratcliff-Desktop-ClaudeCode-Carnivirous-plant-wiki/memory/`
with the session's progress so future sessions can pick up cleanly.
