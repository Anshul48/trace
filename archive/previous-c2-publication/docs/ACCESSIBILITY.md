# Accessibility

Trace's public surfaces are built offline-first and operable without a
mouse, a screen, or motion. This note records what is true today and what
every new demo or doc must preserve.

## What holds now

- **Keyboard**: demos and quickstart are plain terminal commands and Python
  calls. No pointer-only step, no drag, no hover-dependent meaning, no time
  limit. Every demo prints a final `DEMO PASS` / `DEMO FAIL` verdict line
  suitable for screen-reader review and log capture.
- **Offline / static**: Phase 1 demos need no server, account, model, or
  network (`offline_by_default`, verified by `trace status`). Docs are
  static Markdown with relative links; they render without JavaScript.
- **Reduced motion**: nothing animates. The Mermaid diagram in the README
  and any SVG figures are static images; no autoplay, no parallax, no
  flashing content.
- **Contrast / text**: terminal output is plain text (no color-only
  meaning — verdicts are words, not colors). Doc figures must ship with a
  text alternative: every `assets/` image needs adjacent alt prose or a
  caption describing the same information.
- **Links**: all in-repo links are relative and must resolve from the
  file's own directory (checked before release). No link requires login.

## Rules for new contributions

1. New demos: terminal-runnable, `--quiet` verdict line, exit 0/1, fixture
   bundled in-repo, works with `PYTHONDONTWRITEBYTECODE=1` and no network.
2. New figures: SVG preferred (scalable, selectable text); PNG only with a
   `.txt`/caption twin carrying the same data; never text-as-pixels alone.
3. New docs: Markdown headings in order (h1 once), code fences with
   language tags, tables with header rows, no color-only callouts.
4. No new client-side scripting in shipped docs/demos without a static
   fallback that carries the same content.
