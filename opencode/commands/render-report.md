---
description: Generate and publish a mobile-friendly HTML report
---

Generate a self-contained HTML report from the source, slug, and optional view
specified in `$ARGUMENTS`.

Usage:

`/render-report <source-path> <slug> [dashboard|full|plan|results|sources]`

Requirements:

1. Parse the first argument as the source path, the second as the slug, and the
   optional third argument as the view. Resolve `~` in the source path. If an
   argument is missing or ambiguous, return only the usage line above.
2. Require the slug to match `^[a-z0-9][a-z0-9-]*$`. Reject any other slug.
3. Read the source directly from disk on every invocation. Fail clearly if it
   is unreadable; never guess a source.
4. Treat the source as canonical. Preserve every metric, date, status,
   checklist state, command, identifier, unit, and link exactly. Never invent
   a result or fill in missing data.
5. Generate a complete HTML5 document at
   `~/.local/share/opencode-reports/<slug>/index.html`. Create the slug
   directory if necessary and replace only that derived `index.html`. This is
   a disposable local build artifact, not the shared copy.
6. Do not modify the source or any other file. The generated HTML is disposable
   and must not become a second source of truth.
7. Make the document self-contained: inline all CSS and SVG; use no scripts,
   remote assets, forms, active content, or external font dependencies.
8. Optimize for a phone screen. Use responsive status cards, compact tables,
   progress bars, timelines, static SVG charts, clear typography, dark/light
   color schemes, and collapsible `<details>` sections where useful.
9. Clearly separate recorded facts from interpretation. Label every derived
   delta, comparison, trend, or progress percentage as analysis.
10. Put the report title, source path, source's last-updated value when present,
    requested view, and generated-at timestamp at the top.
11. Verify after writing that the file starts with `<!doctype html>`, contains
    no `<script` element, is non-empty, and is no larger than 5 MiB.
12. Treat here-now as company-wide internal publishing. Refuse to publish
    credentials, customer secrets, shell tokens, or content requiring narrower
    authorization.
13. Read `http://go/here-now-llm` immediately before publishing. Resolve `go/`
    links with HTTP because they use Tailscale MagicDNS. Extract the current
    here-now Tailscale base URL from that guidance; never guess or persist it.
14. Publish with:
    `~/.local/bin/here-now-publish --base-url <base-url> --alias <slug> <file>`.
    The local alias preserves the same here-now URL and adds a new version when
    this command is rerun. Fail clearly if publication fails.

Views:

- `dashboard`: Show current status, environment, progress, latest
  experiment-log entry, key metrics, blockers, and next actions. Optimize for
  a phone screen and omit long provenance details.
- `full`: Present the complete report. Preserve all source sections and facts,
  but improve navigation and visual hierarchy. Collapse secondary detail with
  `<details>` sections when useful.
- `plan`: Show objectives, decisions, protocol, experiment matrix, gates,
  checklist progress, and next actions.
- `results`: Show completed experiments, expected-versus-observed metrics,
  deltas, repeatability, anomalies, and conclusions. If no measured results
  exist, state that plainly.
- `sources`: Show provenance, source links, pinned revisions, artifacts,
  assumptions, and known reproducibility gaps.

After generating and publishing the file, return only:

- A Markdown link labeled `Open <slug> report` pointing to the URL printed by
  `here-now-publish`.
- The generated file path.
- The source path and view.
- A reminder that rerunning the command regenerates the HTML from disk and
  publishes a new version at the same share URL.
